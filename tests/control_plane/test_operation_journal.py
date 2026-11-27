import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from modules.control_plane.operation_journal import OperationJournal


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
    options = {"table": "job_notifications", "validator": lambda _: None, "id_field": "id"}
    with closing(OperationJournal(path, **options)) as journal:
        [(pending, settings, published)] = observed
        assert pending.parent == tmp_path and pending.suffix == ".tmp" and not published
        assert settings == ("memory", 2)  # synchronous=FULL
        assert modes(journal._database) == ("delete", 2)
        journal.save({"id": "one", "attempt": 1})
        journal.save({"id": "one", "attempt": 2})
    with closing(OperationJournal(path, **options)) as reopened:
        assert modes(reopened._database) == ("delete", 2)
        assert reopened._database.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert reopened.load() == [{"id": "one", "attempt": 2}]
    assert len(observed) == 1


def test_failed_first_initialization_can_retry_without_replacing_existing_history(tmp_path, monkeypatch):
    path = tmp_path / "history.sqlite3"
    connect = sqlite3.connect

    def deny_version_write(action, pragma, value, *_):
        if action == sqlite3.SQLITE_PRAGMA and pragma == "user_version" and value is not None:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def failing_connect(*args, **kwargs):
        db = connect(*args, **kwargs)
        db.set_authorizer(deny_version_write)
        return db

    options = {"table": "job_notifications", "validator": lambda _: None, "id_field": "id"}
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", failing_connect)
        with pytest.raises(sqlite3.DatabaseError, match="authorized"):
            OperationJournal(path, **options)
    assert not path.exists()
    with closing(OperationJournal(path, **options)) as journal:
        journal.save({"id": "one"})
    with closing(OperationJournal(path, **options)) as journal:
        assert journal.load() == [{"id": "one"}]


def test_existing_empty_journal_is_preserved_as_invalid(tmp_path):
    path = tmp_path / "history.sqlite3"
    path.touch()
    with pytest.raises(ValueError, match="版本无效"):
        OperationJournal(path, table="job_notifications", validator=lambda _: None, id_field="id")
    assert path.read_bytes() == b""
