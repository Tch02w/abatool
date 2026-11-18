"""Non-secret server identity and single-owner remote job checkpoints."""
from __future__ import annotations

import ntpath
import re

from .operation_journal import OperationJournal


def server_identity(profile):
    return {"host": profile.host.strip().lower(), "port": profile.port,
            "username": profile.username, "fingerprint": profile.host_fingerprint,
            "computeRoot": ntpath.normcase(ntpath.normpath(profile.compute_root)),
            "abaqusCommand": profile.abaqus_command,
            "allowedRoots": sorted(ntpath.normcase(ntpath.normpath(path)) for path in profile.allowed_roots)}


class RemoteJobJournal(OperationJournal):
    def __init__(self, path):
        super().__init__(path, table="remote_operations", validator=validate_record)


def validate_record(record):
    if not isinstance(record, dict) or set(record) != {
        "schemaVersion", "snapshot", "request", "serverIdentity", "launchState", "processStartTicks",
        "cancelRequested", "completion", "logTails",
    } or type(record["schemaVersion"]) is not int or record["schemaVersion"] != 1:
        raise ValueError("远端任务记录结构无效")
    item = record["snapshot"]
    if not isinstance(item, dict) or not re.fullmatch(r"[a-f0-9]{32}", str(item.get("operationId", ""))):
        raise ValueError("远端任务身份无效")
    if item.get("status") not in {"queued", "starting", "running", "cancelling", "succeeded", "failed", "cancelled"}:
        raise ValueError("远端任务状态无效")
    for key in ("createdAt", "updatedAt", "phase", "workDirectory", "trackingState"):
        if not isinstance(item.get(key), str):
            raise ValueError("远端任务字段无效")  # noqa: TRY004 - persisted data corruption uses ValueError
    for key in ("version", "percent", "processId", "eventCursor"):
        if type(item.get(key)) is not int or item[key] < 0:
            raise ValueError("远端任务数值无效")
    if item["percent"] > 100 or not isinstance(item.get("logs"), list) or len(item["logs"]) > 250:
        raise ValueError("远端任务进度或日志无效")
    if any(not isinstance(line, str) for line in item["logs"]) or type(item.get("paused")) is not bool:
        raise ValueError("远端任务日志或暂停状态无效")
    error = item.get("error")
    if error is not None and (not isinstance(error, dict) or set(error) != {"code", "message"}
                              or any(not isinstance(value, str) for value in error.values())):
        raise ValueError("远端任务错误记录无效")
    identity = record["serverIdentity"]
    if not isinstance(identity, dict) or set(identity) != {
        "host", "port", "username", "fingerprint", "computeRoot", "abaqusCommand", "allowedRoots",
    } or any(not isinstance(identity[key], str) or not identity[key] for key in ("host", "username", "fingerprint", "computeRoot")):
        raise ValueError("远端服务器身份无效")
    if (type(identity["port"]) is not int or not 1 <= identity["port"] <= 65535
        or not isinstance(identity["abaqusCommand"], str) or not isinstance(identity["allowedRoots"], list)
        or any(not isinstance(path, str) for path in identity["allowedRoots"])):
        raise ValueError("远端服务器范围无效")
    if record["launchState"] not in {"preparing", "intent", "started"}:
        raise ValueError("远端启动阶段无效")
    if not isinstance(record["processStartTicks"], str) or type(record["cancelRequested"]) is not bool:
        raise ValueError("远端执行状态无效")
    if record["launchState"] == "started" and (item["processId"] <= 0 or not record["processStartTicks"]):
        raise ValueError("远端启动身份缺失")
    if not isinstance(record["completion"], dict) or set(record["completion"]) != {"error_seen", "termination_seen"}:
        raise ValueError("远端完成证据无效")
    if any(type(value) is not bool for value in record["completion"].values()):
        raise ValueError("远端完成标志无效")
    if not isinstance(record["logTails"], dict) or any(not isinstance(value, str) for value in record["logTails"].values()):
        raise ValueError("远端日志片段无效")
