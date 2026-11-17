"""Read-only model/role checks shared by native post-processing execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from .postprocess_execution import PostprocessJob


def job_scan_issues(job: PostprocessJob, scan: Mapping[str, Any]) -> list[str]:
    """Return actionable issues without silently replacing user-selected roles."""
    if scan.get("error"):
        return [f"ODB 无法读取：{scan['error']}"]
    issues: list[str] = []
    if job.reinforcement_mode not in ("required", "none"):
        issues.append("请选择有效的纵筋配置")
    has_rebar = job.reinforcement_mode != "none"
    # The legacy worker requires longitudinal T3D2 bars for both pile types.
    # Only reject when every instance supplied type metadata; old cached scans
    # without it are inconclusive, not evidence that bars are absent.
    instances = scan.get("instances", {})
    if has_rebar and instances and all("element_types" in item for item in instances.values()):
        if not any(
            str(kind).upper().startswith("T3D2") and count > 0
            for item in instances.values()
            for kind, count in item["element_types"].items()
        ):
            issues.append("模型中没有 T3D2 纵筋单元；当前旧版提取流程不支持无纵筋模型，不能用实体钢管或根键集合替代")
    steps = list(scan.get("steps", []))
    for label, name in (("起始分析步", job.start_step), ("结束分析步", job.end_step)):
        if name not in steps:
            issues.append(f"{label}不存在：{name or '未选择'}")
    if job.start_step in steps and job.end_step in steps:
        start, end = steps.index(job.start_step), steps.index(job.end_step)
        if start > end:
            issues.append("起始分析步不能晚于结束分析步")
        else:
            details = {item["name"]: item for item in scan.get("step_details", [])}
            selected = steps[start:end + 1]
            if all(name in details for name in selected) and not any(
                details[name].get("frame_count", 0) > 0 for name in selected
            ):
                issues.append("所选分析步范围没有可用帧")

    roles = [
        ("加载节点集", job.load_set, "assembly_node_sets", "node_count", True),
        ("桩体显示集合", job.pile_display_set, "assembly_element_sets", "element_count", True),
        ("混凝土集合", job.pile_concrete_set, "assembly_element_sets", "element_count", True),
        # Legacy extraction adds steel to CFST FreeBody only when configured.
        ("钢构件集合", job.pile_steel_set, "assembly_element_sets", "element_count", False),
        ("土体集合", job.soil_set, "assembly_element_sets", "element_count", True),
    ]
    if has_rebar:
        roles.append(("纵筋集合", job.rebar_set, "assembly_element_sets", "element_count", True))
    for label, name, names_key, count_key, required in roles:
        if not name and not required:
            continue
        if name not in scan.get(names_key, []):
            issues.append(f"{label}不存在：{name or '未选择'}")
            continue
        count = scan.get("set_details", {}).get(name, {}).get(count_key)
        if count is not None and count <= 0:
            issues.append(f"{label}为空：{name}")
    return issues
