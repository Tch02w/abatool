"""Single-owner, transactional merge history. Never opens or changes an ODB."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path


class MergeJournal:
    def __init__(self, path: Path):
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
            is_new = not self.path.exists()
            self._database = sqlite3.connect(
                self.path, timeout=0, check_same_thread=False
            )
            if is_new:
                with self._database:
                    self._database.execute(
                        "CREATE TABLE merge_operations (operation_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
                    )
                    self._database.execute("PRAGMA user_version=1")
            if self._database.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("合并记录版本无效")
            if self._database.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ValueError("合并记录完整性检查失败")
            self._database.execute("PRAGMA synchronous=FULL")
        except BaseException:
            self.close()
            owner.close()
            raise

    def load(self) -> list[dict]:
        rows = self._database.execute(
            "SELECT operation_id, payload FROM merge_operations ORDER BY rowid"
        ).fetchall()
        records = []
        for operation_id, payload in rows:
            record = json.loads(payload)
            validate_record(record)
            if operation_id != record["snapshot"]["operationId"]:
                raise ValueError("合并记录标识不一致")
            records.append(record)
        return records

    def save(self, record: dict) -> None:
        validate_record(record)
        if self._database is None:
            raise OSError("合并记录写入锁已关闭")
        # Update one operation, not the whole history, for each durable checkpoint.
        with self._database:
            self._database.execute(
                "INSERT INTO merge_operations(operation_id, payload) VALUES (?, ?) "
                "ON CONFLICT(operation_id) DO UPDATE SET payload=excluded.payload",
                (
                    record["snapshot"]["operationId"],
                    json.dumps(record, ensure_ascii=False),
                ),
            )

    def close(self) -> None:
        if self._database is not None:
            self._database.close()
            self._database = None
        if self._owner is not None:
            self._owner.close()
            self._owner = None


def validate_record(record: dict) -> None:
    if not isinstance(record, dict) or set(record) != {
        "schemaVersion",
        "snapshot",
        "signature",
        "abaqusCommand",
    }:
        raise ValueError("合并记录结构无效")
    if type(record["schemaVersion"]) is not int or record["schemaVersion"] != 1:
        raise ValueError("合并记录版本无效")
    if (
        not isinstance(record["abaqusCommand"], str)
        or not record["abaqusCommand"].strip()
    ):
        raise ValueError("合并记录命令无效")
    signature = record["signature"]
    if (
        not isinstance(signature, list)
        or len(signature) != 7
        or any(
            not isinstance(value, str) or not Path(value).is_absolute()
            for value in signature[:3]
        )
        or any(type(value) is not bool for value in signature[3:6])
        or signature[6] not in {"auto_number", "overwrite"}
    ):
        raise ValueError("合并请求身份无效")
    item = record["snapshot"]
    fields = {
        "schemaVersion",
        "operationId",
        "attemptId",
        "kind",
        "status",
        "createdAt",
        "updatedAt",
        "version",
        "request",
        "progress",
        "logs",
        "result",
        "error",
        "eventCursor",
    }
    if not isinstance(item, dict) or set(item) != fields:
        raise ValueError("合并快照结构无效")
    if (
        type(item["schemaVersion"]) is not int
        or item["schemaVersion"] != 1
        or item["kind"] != "odb.merge"
    ):
        raise ValueError("合并快照类型无效")
    if any(
        not isinstance(item[key], str) or not item[key]
        for key in ("operationId", "attemptId", "createdAt", "updatedAt")
    ):
        raise ValueError("合并记录标识或时间无效")
    if (
        type(item["version"]) is not int
        or item["version"] < 1
        or type(item["eventCursor"]) is not int
        or item["eventCursor"] < 0
    ):
        raise ValueError("合并记录修订号无效")
    if item["status"] not in {
        "queued",
        "starting",
        "running",
        "cancelling",
        "failed",
        "cancelled",
        "succeeded",
    }:
        raise ValueError("合并记录状态无效")
    progress = item["progress"]
    if (
        not isinstance(progress, dict)
        or set(progress) != {"percent", "phase"}
        or type(progress["percent"]) is not int
        or not 0 <= progress["percent"] <= 100
        or not isinstance(progress["phase"], str)
    ):
        raise ValueError("合并进度无效")
    if not isinstance(item["request"], dict):
        raise ValueError("合并请求无效")  # noqa: TRY004 - persisted-data corruption uses ValueError consistently.
    if (
        not isinstance(item["logs"], list)
        or len(item["logs"]) > 200
        or any(not isinstance(line, str) for line in item["logs"])
    ):
        raise ValueError("合并日志无效")
    error = item["error"]
    if error is not None and (
        not isinstance(error, dict)
        or any(not isinstance(error.get(key), str) for key in ("code", "message"))
    ):
        raise ValueError("合并错误信息无效")
    result = item["result"]
    if result is not None and (
        not isinstance(result, dict)
        or not {"outputOdb", "originalBackup", "restartBackup", "command"}.issubset(
            result
        )
        or set(result)
        - {
            "outputOdb",
            "originalBackup",
            "restartBackup",
            "command",
            "validationReport",
        }
        or any(not isinstance(value, str) or not value for value in result.values())
    ):
        raise ValueError("合并结果记录无效")
    if item["status"] == "succeeded" and (
        result is None or error is not None or progress["percent"] != 100
    ):
        raise ValueError("合并成功记录不完整")
