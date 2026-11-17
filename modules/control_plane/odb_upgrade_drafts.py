"""Read-only upgrade previews; execution must recheck fingerprints and compatibility."""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from modules.postprocessor.runner import upgrade_backup_path, upgrade_temporary_path

from .compatibility import load_compatibility_settings, validate_compatibility_request
from .contracts import SCHEMA_VERSION, ApiProblem, OdbCompatibilityCheckRequest


def preview_odb_upgrade(payload: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"schemaVersion", "root", "paths"}
    if set(payload) - allowed:
        raise ApiProblem(400, "UNKNOWN_FIELDS", "升级预览包含不支持的字段")
    if type(payload.get("schemaVersion")) is not int or payload["schemaVersion"] != SCHEMA_VERSION:
        raise ApiProblem(400, "UNSUPPORTED_SCHEMA_VERSION", "不支持该请求结构版本")
    request = OdbCompatibilityCheckRequest.from_payload({
        **payload, "clientRequestId": "upgrade-preview", "forceRescan": True,
    })
    validated = validate_compatibility_request(request)
    settings = load_compatibility_settings()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", settings.release):
        raise ApiProblem(400, "INVALID_ABAQUS_RELEASE", "Abaqus 版本标识不能包含路径字符")
    entries = []
    for source in validated.paths:
        if not source.is_file() or source.stat().st_size == 0:
            raise ApiProblem(400, "INVALID_UPGRADE_SOURCE", "升级源文件不存在或为空",
                             details={"path": str(source)})
        if source.with_suffix(".lck").exists():
            raise ApiProblem(409, "ODB_LOCK_PRESENT", "ODB 存在锁文件，请先关闭使用它的任务",
                             details={"path": str(source)})
        stat = source.stat()
        entries.append({
            "sourcePath": str(source), "upgradedPath": str(source),
            "backupPath": str(upgrade_backup_path(source)),
            "temporaryPath": str(upgrade_temporary_path(source, settings.release)),
            "sourceSizeBytes": stat.st_size, "sourceMtimeNs": stat.st_mtime_ns,
        })
    return {"schemaVersion": SCHEMA_VERSION, "root": str(validated.root),
            "targetRelease": settings.release, "entries": entries,
            "requiresCompatibilityCheck": True, "requiresConfirmation": True,
            "sourcePolicy": "backup-original-before-validated-replacement",
            "cancellationPolicy": "finish-active-file-then-stop"}
