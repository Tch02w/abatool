"""Scheduler Core 的 SQLite Repository Adapter。"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from .scheduling import (
    JobSpecification,
    JobState,
    PendingReason,
    ResourceRequest,
    SchedulerJobSnapshot,
)

SCHEMA_VERSION = 1


class _InvalidSchedulerSchema(sqlite3.DatabaseError):
    """A scheduler table has an incompatible type or is missing a required column."""


class SQLiteSchedulerRepository:
    """以事务保存调度快照和事件历史，进程崩溃后仍可恢复。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._transaction_depth = 0
        self.recovery_message = ""
        try:
            self._connect_and_initialize()
        except sqlite3.DatabaseError as exc:
            code = getattr(exc, "sqlite_errorcode", 0) & 0xFF
            if not isinstance(exc, _InvalidSchedulerSchema) and code not in (
                sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB,
            ):
                raise
            recovered_paths = self._preserve_corrupt_database()
            preserved_name = recovered_paths[0].name if recovered_paths else self.path.name
            self.recovery_message = (
                f"调度状态库损坏，已新建状态库；原文件保留为 {preserved_name}：{exc}"
            )
            self._connect_and_initialize()

    def _connect_and_initialize(self) -> None:
        self._connection = self._open_connection()
        try:
            self._initialize()
        except BaseException:
            self._connection.close()
            raise

    def _open_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.path),
            timeout=5.0,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        return connection

    def _preserve_corrupt_database(self) -> list[Path]:
        timestamp = time.time_ns()
        recovered_paths: list[Path] = []
        for source in (self.path, Path(f"{self.path}-wal"), Path(f"{self.path}-shm")):
            if not source.exists():
                continue
            target = source.with_name(f"{source.name}.corrupt-{timestamp}")
            source.replace(target)
            recovered_paths.append(target)
        return recovered_paths

    def _initialize(self) -> None:
        with self._lock, self._connection:
            ready = self._schema_ready()
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=NORMAL")
            self._connection.execute("PRAGMA foreign_keys=ON")
            if ready:
                return
            self._connection.execute("BEGIN IMMEDIATE")
            # Another process may have finished creating the database while we waited.
            if self._schema_ready():
                return
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduler_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduler_jobs (
                    job_id TEXT PRIMARY KEY,
                    specification_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    pending_reason TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduler_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    state TEXT NOT NULL,
                    message TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    occurred_at REAL NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS scheduler_events_job_sequence
                ON scheduler_events(job_id, sequence)
                """
            )
            self._connection.execute(
                """
                INSERT INTO scheduler_meta(key, value)
                VALUES('schema_version', ?)
                ON CONFLICT(key) DO NOTHING
                """,
                (str(SCHEMA_VERSION),),
            )

    def _schema_ready(self) -> bool:
        # Triggers have a separate SQLite namespace and may share a table name.
        objects = {
            name: kind for name, kind in self._connection.execute(
                "SELECT lower(name), type FROM sqlite_schema WHERE type IN ('table', 'view', 'index')"
            )
        }
        required_columns = {
            "scheduler_meta": {"key", "value"},
            "scheduler_jobs": {
                "job_id",
                "specification_json",
                "state",
                "pending_reason",
                "attempt_id",
                "message",
                "version",
                "updated_at",
            },
            "scheduler_events": {
                "sequence",
                "job_id",
                "event_type",
                "state",
                "message",
                "attempt_id",
                "occurred_at",
            },
        }
        version = None
        for table, required in required_columns.items():
            if table not in objects:
                continue
            if objects[table] != "table":
                raise _InvalidSchedulerSchema(f"调度状态库对象 {table} 的类型不正确：{objects[table]}")
            rows = self._connection.execute("SELECT lower(name) FROM pragma_table_info(?)", (table,))
            actual = {name for (name,) in rows}
            missing = required - actual
            if missing:
                raise _InvalidSchedulerSchema(
                    f"调度状态库表 {table} 缺少字段：{', '.join(sorted(missing))}"
                )
            if table == "scheduler_meta":
                version = self._connection.execute(
                    "SELECT value FROM scheduler_meta WHERE key='schema_version'"
                ).fetchone()
                if version is not None and version["value"] != str(SCHEMA_VERSION):
                    raise ValueError(f"无法打开调度状态库版本 {version['value']}，当前支持版本 {SCHEMA_VERSION}。")
        return (version is not None and required_columns.keys() <= objects.keys()
                and objects.get("scheduler_events_job_sequence") == "index")

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            outermost = self._transaction_depth == 0
            if outermost:
                self._connection.execute("BEGIN IMMEDIATE")
            self._transaction_depth += 1
            try:
                yield
            except BaseException:
                self._transaction_depth -= 1
                if outermost:
                    self._connection.rollback()
                raise
            else:
                self._transaction_depth -= 1
                if outermost:
                    self._connection.commit()

    def load_jobs(self) -> list[SchedulerJobSnapshot]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT specification_json, state, pending_reason, attempt_id,
                       message, version, updated_at
                FROM scheduler_jobs
                ORDER BY updated_at, job_id
                """
            ).fetchall()
        snapshots = []
        for row in rows:
            try:
                specification = self._decode_specification(row["specification_json"])
                snapshots.append(
                    SchedulerJobSnapshot(
                        specification=specification,
                        state=JobState(row["state"]),
                        pending_reason=PendingReason(row["pending_reason"]),
                        attempt_id=str(row["attempt_id"] or ""),
                        message=str(row["message"] or ""),
                        version=int(row["version"] or 0),
                        updated_at=float(row["updated_at"] or 0.0),
                    )
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return snapshots

    def save_job(self, snapshot: SchedulerJobSnapshot) -> None:
        payload = self._encode_specification(snapshot.specification)
        with self.transaction():
            self._connection.execute(
                """
                INSERT INTO scheduler_jobs(
                    job_id, specification_json, state, pending_reason,
                    attempt_id, message, version, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    specification_json=excluded.specification_json,
                    state=excluded.state,
                    pending_reason=excluded.pending_reason,
                    attempt_id=excluded.attempt_id,
                    message=excluded.message,
                    version=excluded.version,
                    updated_at=excluded.updated_at
                """,
                (
                    snapshot.job_id,
                    payload,
                    snapshot.state.value,
                    snapshot.pending_reason.value,
                    snapshot.attempt_id,
                    snapshot.message,
                    snapshot.version,
                    snapshot.updated_at,
                ),
            )

    def append_event(
        self,
        *,
        job_id: str,
        event_type: str,
        state: JobState,
        message: str,
        attempt_id: str,
        occurred_at: float,
    ) -> None:
        with self.transaction():
            self._connection.execute(
                """
                INSERT INTO scheduler_events(
                    job_id, event_type, state, message, attempt_id, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    event_type,
                    state.value,
                    message,
                    attempt_id,
                    occurred_at,
                ),
            )

    def load_events(
        self,
        *,
        after_sequence: int = 0,
        job_id: str = "",
    ) -> list[dict[str, object]]:
        query = (
            "SELECT sequence, job_id, event_type, state, message, attempt_id, occurred_at "
            "FROM scheduler_events WHERE sequence > ?"
        )
        params: list[object] = [max(0, int(after_sequence or 0))]
        if job_id:
            query += " AND job_id = ?"
            params.append(job_id)
        query += " ORDER BY sequence"
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            try:
                self._connection.close()
            except sqlite3.Error:
                pass

    def load_memory_profiles(self) -> dict[str, str]:
        """Additive metadata; legacy schema-1 readers can ignore these entries."""
        with self._lock:
            rows = self._connection.execute("SELECT key, value FROM scheduler_meta WHERE key LIKE 'memory_profile:%'").fetchall()
        return {str(row["key"]).removeprefix("memory_profile:"): str(row["value"]) for row in rows}

    def save_memory_profile(self, key: str, value: dict) -> None:
        with self.transaction():
            self._connection.execute(
                "INSERT INTO scheduler_meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("memory_profile:" + key, json.dumps(value, separators=(",", ":"))),
            )

    @staticmethod
    def _encode_specification(specification: JobSpecification) -> str:
        payload = asdict(specification)
        payload["dependency_job_ids"] = list(specification.dependency_job_ids)
        payload["conflict_key"] = list(specification.conflict_key)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)

    @staticmethod
    def _decode_specification(payload: str) -> JobSpecification:
        values = json.loads(payload)
        resources = ResourceRequest(**dict(values.pop("resources", {}) or {}))
        values["dependency_job_ids"] = tuple(values.get("dependency_job_ids") or ())
        values["conflict_key"] = tuple(values.get("conflict_key") or ("", ""))
        values["metadata"] = dict(values.get("metadata") or {})
        return JobSpecification(resources=resources, **values).normalized()
