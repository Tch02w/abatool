"""Single-owner SQLite checkpoints shared by durable operation managers."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
from contextlib import closing
from pathlib import Path


class OperationJournal:
    def __init__(self, path: Path, *, table: str, validator, id_field=None):
        if table not in {"merge_operations", "batch_operations", "remote_operations", "job_notifications", "postprocess_group_queues"}:
            raise ValueError("Unknown operation journal table")
        self._table = table
        self._validate = validator
        self._id_field = id_field
        self.path = Path(path)
        self._lock = threading.RLock()
        self._owner = None
        self._database = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        owner = self.path.with_name(self.path.name + ".lock").open("a+b")
        try:
            if owner.tell() == 0:
                owner.write(b"\0")
                owner.flush()
            owner.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._owner = owner
            self._published = self._path_exists()
            if self._published:
                self._open_existing()
        except BaseException:
            self.close()
            owner.close()
            raise

    def _path_exists(self) -> bool:
        try:
            self.path.lstat()
        except FileNotFoundError:
            return False
        return True

    def _open_existing(self) -> None:
        # mode=rw prevents SQLite from recreating a missing history. Use an
        # empty URI authority for a Windows UNC path, as required by SQLite.
        uri = self.path.absolute().as_uri()
        if self.path.drive.startswith("\\\\"):
            uri = "file:////" + uri.removeprefix("file://")
        database = sqlite3.connect(uri + "?mode=rw", uri=True, timeout=0, check_same_thread=False)
        try:
            if database.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("任务记录版本无效")
            if database.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ValueError("任务记录完整性检查失败")
            database.execute("PRAGMA synchronous=FULL")
        except BaseException:
            database.close()
            raise
        self._database = database

    def _current_database(self):
        if self._owner is None:
            raise OSError("任务记录写入锁已关闭")
        if self._database is None:
            if self._published:
                self._open_existing()
            elif self._path_exists():
                raise FileExistsError("任务记录文件在启动后出现，请重新打开以读取已有记录")
        return self._database

    def _publish_first_record(self, values) -> None:
        # Publish the schema and its first durable record together. A competing
        # file or a failed commit must never be mistaken for our new journal.
        fd, filename = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp")
        os.close(fd)
        pending = Path(filename)
        try:
            with closing(sqlite3.connect(pending, timeout=0)) as database, database:
                # Only the unpublished database uses an in-memory rollback journal.
                database.execute("PRAGMA journal_mode=MEMORY")
                database.execute("PRAGMA synchronous=FULL")
                database.execute("BEGIN IMMEDIATE")
                database.execute(
                    f"CREATE TABLE {self._table} (operation_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
                )
                database.execute("PRAGMA user_version=1")
                database.execute(f"INSERT INTO {self._table} VALUES (?, ?)", values)
            if os.name == "nt":
                os.rename(pending, self.path)  # Fails if the destination exists.
            else:
                os.link(pending, self.path)
            self._published = True
        finally:
            pending.unlink(missing_ok=True)

    def load(self) -> list[dict]:
        with self._lock:
            database = self._current_database()
            if database is None:
                return []
            rows = database.execute(
                f"SELECT operation_id, payload FROM {self._table} ORDER BY rowid"
            ).fetchall()
        records = []
        for operation_id, payload in rows:
            record = json.loads(payload)
            self._validate(record)
            if operation_id != self._record_id(record):
                raise ValueError("任务记录标识不一致")
            records.append(record)
        return records

    def save(self, record: dict) -> None:
        with self._lock:
            database = self._current_database()
            self._validate(record)
            values = (self._record_id(record), json.dumps(record, ensure_ascii=False))
            if database is None:
                self._publish_first_record(values)
                return
            with database:
                database.execute(
                    f"INSERT INTO {self._table}(operation_id, payload) VALUES (?, ?) "
                    "ON CONFLICT(operation_id) DO UPDATE SET payload=excluded.payload",
                    values,
                )

    def _record_id(self, record):
        return record[self._id_field] if self._id_field else record["snapshot"]["operationId"]

    def close(self) -> None:
        with self._lock:
            try:
                if self._database is not None:
                    self._database.close()
                    self._database = None
            finally:
                if self._owner is not None:
                    self._owner.close()
                    self._owner = None
