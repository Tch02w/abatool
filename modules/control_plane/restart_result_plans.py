"""Build read-only materialization plans for one selected restart result."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import job_queues
from .contracts import SCHEMA_VERSION, ApiProblem

_FIELDS = {"schemaVersion", "itemId", "outputDirectory"}


def _text(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name, "")
    if not isinstance(value, str):
        raise ApiProblem(
            400,
            "INVALID_RESTART_RESULT_PLAN_FIELD",
            f"{name} 必须是字符串",
            details={"field": name},
        )
    return value.strip()


def _output_odb(item: Mapping[str, Any]) -> Path:
    job_name = str(item.get("jobName") or "").strip()
    candidates: list[Path] = []
    for field in ("archiveDestination", "effectiveWorkDir"):
        directory = str(item.get(field) or "").strip()
        if directory and job_name:
            candidates.append(Path(directory) / f"{job_name}.odb")
    inp_path = str(item.get("inpPath") or "").strip()
    if inp_path and job_name:
        candidates.append(Path(inp_path).parent / f"{job_name}.odb")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0] if candidates else Path(f"{job_name}.odb")


def _parent(
    item: Mapping[str, Any],
    by_id: Mapping[str, Mapping[str, Any]],
    by_name: Mapping[str, list[Mapping[str, Any]]],
) -> Mapping[str, Any] | None:
    dependency_ids = item.get("dependencyJobIds")
    if isinstance(dependency_ids, list):
        identifiers = list(dict.fromkeys(str(value or "").strip() for value in dependency_ids))
        identifiers = [value for value in identifiers if value]
        if len(identifiers) > 1:
            raise ValueError(f"{item.get('jobName')} 有多个前置作业，无法确定唯一祖先路径。")
        if identifiers:
            parent = by_id.get(identifiers[0])
            if parent is None:
                raise ValueError(f"{item.get('jobName')} 指定的前置作业不存在。")
            return parent
    oldjob_name = str(item.get("oldjobName") or "").strip().casefold()
    candidates = by_name.get(oldjob_name, [])
    if len(candidates) > 1:
        raise ValueError(f"{item.get('jobName')} 的前置名称对应多个作业，请先指定唯一前置作业。")
    return candidates[0] if candidates else None


def build_restart_result_plan(payload: Mapping[str, Any]) -> dict[str, Any]:
    unknown_fields = sorted(set(payload) - _FIELDS)
    if unknown_fields:
        raise ApiProblem(
            400,
            "UNKNOWN_FIELDS",
            "完整结果计划包含 v1 协议不支持的字段",
            details={"fields": unknown_fields},
        )
    if payload.get("schemaVersion") != SCHEMA_VERSION:
        raise ApiProblem(
            400,
            "UNSUPPORTED_SCHEMA_VERSION",
            "不支持该请求结构版本",
            details={"supported": [SCHEMA_VERSION]},
        )
    item_id = _text(payload, "itemId")
    if not item_id:
        raise ApiProblem(400, "MISSING_ITEM_ID", "请选择重启动作业节点")

    queue = job_queues.read_job_queues()
    items = list(queue["queueItems"])
    target = next(
        (
            item
            for item in items
            if item.get("itemId") == item_id or item.get("jobId") == item_id
        ),
        None,
    )
    if target is None:
        raise ApiProblem(404, "RESTART_JOB_NOT_FOUND", "正式队列中找不到目标作业")
    if target.get("runMode") != "restart":
        raise ApiProblem(409, "NOT_A_RESTART_JOB", "只有重启动作业需要生成完整结果")

    by_id = {str(item.get("jobId") or ""): item for item in items}
    by_name: dict[str, list[Mapping[str, Any]]] = {}
    for item in items:
        name = str(item.get("jobName") or "").strip().casefold()
        if name:
            by_name.setdefault(name, []).append(item)

    reversed_ancestry: list[Mapping[str, Any]] = [target]
    seen: set[str] = set()
    current = target
    issues: list[str] = []
    while current.get("runMode") == "restart":
        job_id = str(current.get("jobId") or "")
        if job_id in seen:
            issues.append("重启动依赖存在循环，无法生成完整结果。")
            break
        seen.add(job_id)
        try:
            parent = _parent(current, by_id, by_name)
        except ValueError as error:
            issues.append(str(error))
            break
        if parent is None:
            external_path = Path(str(current.get("oldjobPath") or ""))
            if external_path.is_file() and external_path.suffix.lower() == ".odb":
                reversed_ancestry.append(
                    {
                        "itemId": "",
                        "jobId": f"external:{external_path.stem}",
                        "jobName": external_path.stem,
                        "runMode": "external",
                        "status": "可用",
                        "effectiveWorkDir": str(external_path.parent),
                        "inpPath": "",
                    }
                )
            else:
                issues.append(f"找不到 {current.get('jobName')} 的前置作业。")
            break
        reversed_ancestry.append(parent)
        current = parent

    ancestry = list(reversed(reversed_ancestry))
    output_directory_text = _text(payload, "outputDirectory")
    if output_directory_text:
        output_directory = Path(output_directory_text)
    else:
        target_output = _output_odb(target)
        output_directory = target_output.parent
    if not output_directory.is_dir():
        issues.append(f"完整结果输出目录不存在：{output_directory}")

    steps: list[dict[str, Any]] = []
    current_full = Path(str(ancestry[1].get("oldjobPath") or "")) if len(ancestry) > 1 else _output_odb(target)
    if len(ancestry) > 1 and not current_full.is_file():
        issues.append(f"前置 ODB 不存在：{current_full}")

    for index, node in enumerate(ancestry[1:], start=1):
        restart_odb = _output_odb(node)
        if not restart_odb.is_file():
            issues.append(f"阶段结果 ODB 不存在：{restart_odb}")
        output_odb = output_directory / f"{node.get('jobName')}_full_joined.odb"
        steps.append(
            {
                "index": index,
                "jobId": str(node.get("jobId") or ""),
                "jobName": str(node.get("jobName") or ""),
                "originalOdb": str(current_full),
                "restartOdb": str(restart_odb),
                "outputOdb": str(output_odb),
                "status": "ready" if not issues else "blocked",
            }
        )
        current_full = output_odb

    projected_ancestry = [
        {
            "itemId": str(item.get("itemId") or ""),
            "jobId": str(item.get("jobId") or ""),
            "jobName": str(item.get("jobName") or ""),
            "runMode": str(item.get("runMode") or "normal"),
            "status": str(item.get("status") or ""),
            "outputOdb": str(_output_odb(item)),
        }
        for item in ancestry
    ]
    valid = not issues and bool(steps)
    if not valid:
        steps = []
    return {
        "schemaVersion": SCHEMA_VERSION,
        "planKind": "restart-result-materialization",
        "targetItemId": str(target.get("itemId") or ""),
        "targetJobId": str(target.get("jobId") or ""),
        "targetJobName": str(target.get("jobName") or ""),
        "valid": valid,
        "issues": issues,
        "ancestry": projected_ancestry,
        "steps": steps,
        "finalOutputOdb": str(current_full) if valid else "",
    }


__all__ = ["build_restart_result_plan"]
