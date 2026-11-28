import json
import os
import sqlite3
import stat
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest

from modules.control_plane.operation_journal import OperationJournal

OPTIONS = {"table": "job_notifications", "validator": lambda _: None, "id_field": "id"}


def test_rollback_journal_is_in_memory_only_during_unpublished_schema_creation(tmp_path, monkeypatch):
    path = tmp_path / "notifications.sqlite3"
    observed = []
    connect = sqlite3.connect

    def modes(db):
        return db.execute("PRAGMA journal_mode").fetchone()[0], db.execute("PRAGMA synchronous").fetchone()[0]

    class ObserveSchemaConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql.startswith("CREATE TABLE "):
                filename = self.execute("PRAGMA database_list").fetchone()[2]
                observed.append((Path(filename), modes(self), path.exists()))
            return super().execute(sql, parameters)

    def observing_connect(*args, **kwargs):
        return connect(*args, **kwargs, factory=ObserveSchemaConnection)

    monkeypatch.setattr(sqlite3, "connect", observing_connect)
    with closing(OperationJournal(path, **OPTIONS)) as journal:
        assert not observed and journal.load() == [] and not path.exists()
        journal.save({"id": "one", "attempt": 1})
        [(pending, settings, published)] = observed
        assert pending.parent == tmp_path and pending.suffix == ".tmp" and not published
        assert settings == ("memory", 2)  # synchronous=FULL
        assert journal.load() == [{"id": "one", "attempt": 1}]
        assert modes(journal._database) == ("delete", 2)
        journal.save({"id": "one", "attempt": 2})
    with closing(OperationJournal(path, **OPTIONS)) as reopened:
        assert modes(reopened._database) == ("delete", 2)
        assert reopened._database.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert reopened.load() == [{"id": "one", "attempt": 2}]
    assert len(observed) == 1


@pytest.mark.parametrize("denied", ["version", "insert", "commit"])
def test_failed_first_initialization_can_retry_without_replacing_existing_history(tmp_path, monkeypatch, denied):
    path = tmp_path / "history.sqlite3"
    connect = sqlite3.connect

    def deny_operation(action, argument, value, *_):
        if ((denied == "version" and action == sqlite3.SQLITE_PRAGMA and argument == "user_version" and value is not None)
                or (denied == "insert" and action == sqlite3.SQLITE_INSERT and argument == "job_notifications")
                or (denied == "commit" and action == sqlite3.SQLITE_TRANSACTION and argument == "COMMIT")):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def failing_connect(*args, **kwargs):
        db = connect(*args, **kwargs)
        db.set_authorizer(deny_operation)
        return db

    with closing(OperationJournal(path, **OPTIONS)) as journal:
        with monkeypatch.context() as patch:
            patch.setattr(sqlite3, "connect", failing_connect)
            with pytest.raises(sqlite3.DatabaseError, match="authorized"):
                journal.save({"id": "one"})
        assert journal.load() == [] and not path.exists() and not list(tmp_path.glob("*.tmp"))
        journal.save({"id": "one"})
    with closing(OperationJournal(path, **OPTIONS)) as journal:
        assert journal.load() == [{"id": "one"}]


def test_existing_empty_journal_is_preserved_as_invalid(tmp_path):
    path = tmp_path / "history.sqlite3"
    path.touch()
    with pytest.raises(ValueError, match="版本无效"):
        OperationJournal(path, **OPTIONS)
    assert path.read_bytes() == b""


def test_empty_preview_only_takes_owner_lock_and_close_releases_it(tmp_path, monkeypatch):
    path = tmp_path / "empty.sqlite3"
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **kw: pytest.fail("unexpected SQLite access"))
    with closing(OperationJournal(path, **OPTIONS)) as journal:
        assert journal.load() == journal.load() == []
        with pytest.raises(OSError):
            OperationJournal(path, **OPTIONS)
        with pytest.raises(TypeError):
            journal.save({"id": "one", "bad": object()})
    with pytest.raises(OSError, match="已关闭"):
        journal.load()
    with pytest.raises(OSError, match="已关闭"):
        journal.save({"id": "one"})
    with closing(OperationJournal(path, **OPTIONS)) as reopened:
        assert reopened.load() == []
    assert [item.name for item in tmp_path.iterdir()] == ["empty.sqlite3.lock"]


@pytest.mark.parametrize("during_publish", [False, True])
def test_late_history_survives_first_write_and_is_loaded_on_reopen(tmp_path, monkeypatch, during_publish):
    path = tmp_path / "history.sqlite3"
    existing = tmp_path / "external.sqlite3"
    with closing(OperationJournal(existing, **OPTIONS)) as external:
        external.save({"id": "one", "value": "external"})
    original = existing.read_bytes()
    with closing(OperationJournal(path, **OPTIONS)) as journal:
        assert journal.load() == []
        if during_publish:
            action = "rename" if os.name == "nt" else "link"
            publish = getattr(os, action)

            def competing_publish(source, target):
                path.write_bytes(original)
                publish(source, target)

            monkeypatch.setattr(os, action, competing_publish)
        else:
            path.write_bytes(original)
        with pytest.raises(FileExistsError):
            journal.save({"id": "one", "value": "local"})
        assert path.read_bytes() == original and not list(tmp_path.glob("*.tmp"))
        with pytest.raises(FileExistsError):
            journal.load()
    with closing(OperationJournal(path, **OPTIONS)) as reopened:
        assert reopened.load() == [{"id": "one", "value": "external"}]


def test_first_committed_row_survives_without_reopening_and_concurrent_saves(tmp_path):
    path = tmp_path / "历史 #1.sqlite3"
    with closing(OperationJournal(path, **OPTIONS)) as journal:
        with ThreadPoolExecutor(max_workers=4) as threads:
            list(threads.map(journal.save, [{"id": str(i)} for i in range(8)]))
        with closing(sqlite3.connect(path)) as observer:
            rows = observer.execute("SELECT payload FROM job_notifications").fetchall()
            assert {json.loads(payload)["id"] for payload, in rows} == {str(i) for i in range(8)}
    with closing(OperationJournal(path, **OPTIONS)) as reopened:
        assert len(reopened.load()) == 8


def test_readonly_existing_database_cannot_acknowledge_an_update(tmp_path, monkeypatch):
    path = tmp_path / "history.sqlite3"
    with closing(OperationJournal(path, **OPTIONS)) as journal:
        journal.save({"id": "one", "value": "saved"})
    original = path.read_bytes()
    previous_mode = path.stat().st_mode
    path.chmod(stat.S_IREAD)
    try:
        if os.access(path, os.W_OK):
            # A privileged POSIX identity may bypass file permissions. Open the
            # same actual database read-only in SQLite to exercise that case.
            connect = sqlite3.connect
            monkeypatch.setattr(sqlite3, "connect", lambda _, **kwargs: connect(path.as_uri() + "?mode=ro", **kwargs))
        with pytest.raises((OSError, sqlite3.OperationalError)), closing(OperationJournal(path, **OPTIONS)) as journal:
            journal.save({"id": "one", "value": "read-only"})
        assert path.read_bytes() == original
    finally:
        path.chmod(previous_mode)
