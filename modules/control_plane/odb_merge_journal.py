"""Single-owner, transactional merge history. Never opens or changes an ODB."""

from __future__ import annotations

from pathlib import Path

from .operation_journal import OperationJournal


class MergeJournal(OperationJournal):
    def __init__(self, path: Path):
        super().__init__(path, table="merge_operations", validator=validate_record)


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
