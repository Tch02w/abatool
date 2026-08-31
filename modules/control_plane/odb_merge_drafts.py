"""Qt-free validation and command preview for protected ODB merge drafts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from modules.control_plane.compatibility import load_compatibility_settings
from modules.submitter.odb_merge_core import (
    MergeConflictPolicy,
    OdbMergeError,
    OdbMergeRequest,
    build_merge_plan,
    normalize_joined_output,
)

from .contracts import SCHEMA_VERSION, ApiProblem

_FIELDS = {
    "schemaVersion",
    "originalOdb",
    "restartOdb",
    "outputOdb",
    "includeHistory",
    "compressResult",
    "copyOriginal",
    "conflictPolicy",
}


@dataclass(frozen=True)
class OdbMergeDraftPreviewRequest:
    request: OdbMergeRequest

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
    ) -> OdbMergeDraftPreviewRequest:
        unknown_fields = sorted(set(payload) - _FIELDS)
        if unknown_fields:
            raise ApiProblem(
                400,
                "UNKNOWN_FIELDS",
                "ODB 合并草稿包含 v1 协议不支持的字段",
                details={"fields": unknown_fields},
            )
        if payload.get("schemaVersion") != SCHEMA_VERSION:
            raise ApiProblem(
                400,
                "UNSUPPORTED_SCHEMA_VERSION",
                "不支持该请求结构版本",
                details={
                    "received": payload.get("schemaVersion"),
                    "supported": [SCHEMA_VERSION],
                },
            )

        def text(name: str, default: str = "") -> str:
            value = payload.get(name, default)
            if not isinstance(value, str):
                raise ApiProblem(
                    400,
                    "INVALID_ODB_MERGE_DRAFT_FIELD",
                    f"{name} 必须是字符串",
                    details={"field": name},
                )
            return value.strip()

        def flag(name: str, default: bool = False) -> bool:
            value = payload.get(name, default)
            if not isinstance(value, bool):
                raise ApiProblem(
                    400,
                    "INVALID_ODB_MERGE_DRAFT_FIELD",
                    f"{name} 必须是布尔值",
                    details={"field": name},
                )
            return value

        raw_policy = text("conflictPolicy", MergeConflictPolicy.AUTO_NUMBER.value)
        try:
            conflict_policy = MergeConflictPolicy(raw_policy)
        except ValueError as exc:
            raise ApiProblem(
                400,
                "INVALID_ODB_MERGE_CONFLICT_POLICY",
                "conflictPolicy 必须是 auto_number 或 overwrite",
            ) from exc

        return cls(
            OdbMergeRequest(
                original_odb=Path(text("originalOdb")),
                restart_odb=Path(text("restartOdb")),
                output_odb=Path(text("outputOdb")),
                abaqus_command="abaqus",
                include_history=flag("includeHistory", True),
                compress_result=flag("compressResult"),
                copy_original=flag("copyOriginal"),
                conflict_policy=conflict_policy,
            )
        )


def preview_odb_merge_draft(payload: Mapping[str, Any]) -> dict[str, Any]:
    draft = OdbMergeDraftPreviewRequest.from_payload(payload).request
    required = (
        ("originalOdb", draft.original_odb, "请选择原始 ODB。"),
        ("restartOdb", draft.restart_odb, "请选择重启动 ODB。"),
        ("outputOdb", draft.output_odb, "请选择输出 ODB。"),
    )
    for field, path, message in required:
        if not str(path).strip() or str(path) == ".":
            return _invalid_preview(message, field=field)

    try:
        draft = replace(
            draft,
            abaqus_command=load_compatibility_settings().command,
        )
        plan = build_merge_plan(draft)
    except (OdbMergeError, OSError, RuntimeError) as exc:
        return _invalid_preview(str(exc))

    normalized_requested = normalize_joined_output(draft.output_odb)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "valid": True,
        "validationMessage": (
            "文件路径、非空源文件、源/目标隔离和结果命名已通过检查。"
            "ODB 内容将在执行阶段由 Abaqus 只读验证。"
        ),
        "validationLevel": "file-system",
        "normalizedOutputOdb": str(plan.request.output_odb),
        "originalBackup": str(plan.original_backup),
        "restartBackup": str(plan.restart_backup),
        "command": plan.command_preview(),
        "autoNumbered": plan.request.output_odb != normalized_requested,
        "willOverwrite": (
            plan.request.conflict_policy == MergeConflictPolicy.OVERWRITE
            and plan.request.output_odb.exists()
        ),
        "sourceTotalBytes": (
            plan.request.original_odb.stat().st_size
            + plan.request.restart_odb.stat().st_size
        ),
        "executionSteps": [
            "复制两个源 ODB 到隔离工作区",
            "在工作副本上执行 Abaqus restartjoin",
            "使用 Abaqus 只读打开并验证合并结果",
            "验证通过后原子发布备份和结果",
        ],
    }


def _invalid_preview(message: str, *, field: str = "") -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "valid": False,
        "validationMessage": message,
        "validationLevel": "file-system",
        "invalidField": field,
        "normalizedOutputOdb": "",
        "originalBackup": "",
        "restartBackup": "",
        "command": "",
        "autoNumbered": False,
        "willOverwrite": False,
        "sourceTotalBytes": 0,
        "executionSteps": [],
    }


__all__ = ["OdbMergeDraftPreviewRequest", "preview_odb_merge_draft"]
