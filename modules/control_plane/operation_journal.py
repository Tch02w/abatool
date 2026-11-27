"""Single-owner SQLite checkpoints shared by durable operation managers."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
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
            if not self.path.exists():
                self._create_database()
            self._database = sqlite3.connect(
                self.path, timeout=0, check_same_thread=False
            )
            if self._database.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("任务记录版本无效")
            if self._database.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ValueError("任务记录完整性检查失败")
            self._database.execute("PRAGMA synchronous=FULL")
        except BaseException:
            self.close()
            owner.close()
            raise

    def _create_database(self) -> None:
        # Publish a complete schema while holding the owner lock. A failed first
        # launch must not leave a partial database that looks like damaged history.
        fd, filename = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp")
        os.close(fd)
        pending = Path(filename)
        try:
            with closing(sqlite3.connect(pending, timeout=0)) as database, database:
                database.execute("PRAGMA synchronous=FULL")
                database.execute("BEGIN IMMEDIATE")
                database.execute(
                    f"CREATE TABLE {self._table} (operation_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
                )
                database.execute("PRAGMA user_version=1")
            pending.replace(self.path)
        finally:
            pending.unlink(missing_ok=True)

    def load(self) -> list[dict]:
        rows = self._database.execute(
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
        self._validate(record)
        if self._database is None:
            raise OSError("任务记录写入锁已关闭")
        # Update one operation, not the whole history, for each durable checkpoint.
        with self._database:
            self._database.execute(
                f"INSERT INTO {self._table}(operation_id, payload) VALUES (?, ?) "
                "ON CONFLICT(operation_id) DO UPDATE SET payload=excluded.payload",
                (
                    self._record_id(record),
                    json.dumps(record, ensure_ascii=False),
                ),
            )

    def _record_id(self, record):
        return record[self._id_field] if self._id_field else record["snapshot"]["operationId"]

    def close(self) -> None:
        if self._database is not None:
            self._database.close()
            self._database = None
        if self._owner is not None:
            self._owner.close()
            self._owner = None
