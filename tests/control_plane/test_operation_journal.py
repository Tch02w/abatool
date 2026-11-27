import sqlite3
from contextlib import closing

import pytest

from modules.control_plane.operation_journal import OperationJournal


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
