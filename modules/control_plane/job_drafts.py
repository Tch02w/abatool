"""Qt-free local job draft validation and command preview service."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules.submitter.command import (
    MEMORY_OPTIONS,
    build_abaqus_command,
    derive_oldjob_name,
    validate_options,
)
from modules.submitter.cpu_policy import validate_local_cpus
from modules.submitter.job_draft import LocalJobDraft

from .contracts import SCHEMA_VERSION, ApiProblem

_FIELDS = {
    "schemaVersion",
    "inpFile",
    "jobName",
    "cpus",
    "memoryValue",
    "memoryUnit",
    "oldjobPath",
    "fortranPath",
    "interactive",
    "datacheck",
    "notify",
    "abaqusCommand",
    "priority",
    "maxParallel",
    "useSsdCalculation",
    "calculationRootDir",
    "archiveDir",
}


@dataclass(frozen=True)
class LocalJobDraftPreviewRequest:
    draft: LocalJobDraft

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
    ) -> LocalJobDraftPreviewRequest:
        unknown_fields = sorted(set(payload) - _FIELDS)
        if unknown_fields:
            raise ApiProblem(
                400,
                "UNKNOWN_FIELDS",
                "作业草稿请求包含 v1 协议不支持的字段",
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
                    "INVALID_JOB_DRAFT_FIELD",
                    f"{name} 必须是字符串",
                    details={"field": name},
                )
            return value.strip()

        def flag(name: str, default: bool = False) -> bool:
            value = payload.get(name, default)
            if not isinstance(value, bool):
                raise ApiProblem(
                    400,
                    "INVALID_JOB_DRAFT_FIELD",
                    f"{name} 必须是布尔值",
                    details={"field": name},
                )
            return value

        def integer(name: str, default: int) -> int:
            value = payload.get(name, default)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ApiProblem(
                    400,
                    "INVALID_JOB_DRAFT_FIELD",
                    f"{name} 必须是整数",
                    details={"field": name},
                )
            return value

        cpus = integer("cpus", 0)
        try:
            validate_local_cpus(cpus, text("abaqusCommand", "abaqus"))
        except ValueError as exc:
            raise ApiProblem(400, "INVALID_CPUS", str(exc)) from exc
        max_parallel = integer("maxParallel", 1)
        if not 1 <= max_parallel <= 999:
            raise ApiProblem(
                400,
                "INVALID_MAX_PARALLEL",
                "maxParallel 必须在 1 到 999 之间",
            )
        priority = integer("priority", 0)
        if priority not in {-10, 0, 10}:
            raise ApiProblem(
                400,
                "INVALID_PRIORITY",
                "priority 必须是 -10、0 或 10",
            )
        memory_unit = text("memoryUnit", "%") or "%"
        if memory_unit not in MEMORY_OPTIONS:
            raise ApiProblem(
                400,
                "INVALID_MEMORY_UNIT",
                "memoryUnit 必须是 %、GB 或 MB",
            )

        return cls(
            LocalJobDraft(
                inp_file=text("inpFile"),
                job_name=text("jobName"),
                cpus=cpus,
                memory_value=text("memoryValue"),
                memory_unit=memory_unit,
                oldjob_path=text("oldjobPath"),
                fortran_path=text("fortranPath"),
                interactive=flag("interactive"),
                datacheck=flag("datacheck"),
                notify=flag("notify", True),
                abaqus_command=text("abaqusCommand", "abaqus") or "abaqus",
                priority=priority,
                max_parallel=max_parallel,
                use_ssd_calculation=flag("useSsdCalculation"),
                calculation_root_dir=text("calculationRootDir"),
                archive_dir=text("archiveDir"),
            )
        )


def preview_local_job_draft(payload: Mapping[str, Any]) -> dict[str, Any]:
    request = LocalJobDraftPreviewRequest.from_payload(payload)
    draft = request.draft
    options = draft.to_submit_options()
    valid, message = validate_options(options)
    if valid:
        valid, message = draft.validate_local_paths()

    job_name = draft.effective_job_name()
    input_path = Path(draft.inp_file) if draft.inp_file else None
    if draft.use_ssd_calculation and draft.calculation_root_dir and job_name:
        work_directory = str(Path(draft.calculation_root_dir) / job_name)
    elif input_path is not None:
        work_directory = str(input_path.parent)
    else:
        work_directory = ""
    archive_path = (
        str(Path(draft.archive_dir) / job_name)
        if draft.archive_dir and job_name
        else work_directory
    )

    return {
        "schemaVersion": SCHEMA_VERSION,
        "valid": valid,
        "validationMessage": message,
        "effectiveJobName": job_name,
        "oldjobName": derive_oldjob_name(draft.oldjob_path),
        "hasRestartInput": bool(draft.oldjob_path),
        "command": build_abaqus_command(options) if valid else "",
        "workDirectory": work_directory,
        "archivePath": archive_path,
    }


__all__ = ["LocalJobDraftPreviewRequest", "preview_local_job_draft"]
