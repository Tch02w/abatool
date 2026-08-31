"""Read-only restart dependency topology and diagnostics."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .contracts import SCHEMA_VERSION
from .job_queues import read_job_queues


def _path_compatible(oldjob_path: str, oldjob_name: str) -> bool:
    if not oldjob_path:
        return True
    try:
        path = Path(oldjob_path)
    except (OSError, ValueError):
        return False
    return path.suffix.lower() == ".odb" and path.stem.casefold() == oldjob_name.casefold()


def _cycle_ids(parent_by_child: dict[str, str]) -> set[str]:
    cycle_nodes: set[str] = set()
    visited: set[str] = set()
    for start in parent_by_child:
        if start in visited:
            continue
        path: list[str] = []
        positions: dict[str, int] = {}
        current = start
        while current and current not in visited:
            if current in positions:
                cycle_nodes.update(path[positions[current] :])
                break
            positions[current] = len(path)
            path.append(current)
            current = parent_by_child.get(current, "")
        visited.update(path)
    return cycle_nodes


def _stage(job_id: str, parent_by_child: dict[str, str], cycle_ids: set[str]) -> int:
    if job_id in cycle_ids:
        return 0
    depth = 1
    seen = {job_id}
    current = parent_by_child.get(job_id, "")
    while current and current not in seen:
        depth += 1
        seen.add(current)
        current = parent_by_child.get(current, "")
    return depth


def read_restart_chains() -> dict[str, Any]:
    queue = read_job_queues()
    items = list(queue["queueItems"])
    by_id = {item["jobId"]: item for item in items if item["jobId"]}
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        if item["jobName"]:
            by_name[item["jobName"].casefold()].append(item)

    parent_by_child: dict[str, str] = {}
    parent_name_by_child: dict[str, str] = {}
    missing_children: set[str] = set()
    incompatible_children: set[str] = set()
    restart_items: list[dict[str, Any]] = []
    for item in items:
        oldjob_name = item["oldjobName"]
        dependency_ids = [value for value in item["dependencyJobIds"] if value]
        if not oldjob_name and not dependency_ids and item["runMode"] != "restart":
            continue
        restart_items.append(item)
        parent = next((by_id.get(value) for value in dependency_ids if value in by_id), None)
        if parent is None and oldjob_name:
            candidates = by_name.get(oldjob_name.casefold(), [])
            parent = candidates[0] if candidates else None
        if parent is not None:
            parent_by_child[item["jobId"]] = parent["jobId"]
            parent_name_by_child[item["jobId"]] = parent["jobName"]
        elif oldjob_name:
            try:
                external_exists = bool(item["oldjobPath"] and Path(item["oldjobPath"]).is_file())
            except OSError:
                external_exists = False
            if not external_exists:
                missing_children.add(item["jobId"])
            parent_name_by_child[item["jobId"]] = oldjob_name
        if oldjob_name and not _path_compatible(item["oldjobPath"], oldjob_name):
            incompatible_children.add(item["jobId"])

    cycle_ids = _cycle_ids(parent_by_child)
    nodes: list[dict[str, Any]] = []
    for item in restart_items:
        job_id = item["jobId"]
        if job_id in cycle_ids:
            validation_status = "cycle"
            message = "检测到循环依赖"
        elif job_id in missing_children:
            validation_status = "missing_parent"
            message = f"未找到前置作业：{parent_name_by_child.get(job_id, '')}"
        elif job_id in incompatible_children:
            validation_status = "incompatible_path"
            message = "oldjob 路径与前置作业名称不兼容"
        else:
            validation_status = "valid"
            message = "依赖有效"
        nodes.append(
            {
                "itemId": item["itemId"],
                "jobId": job_id,
                "jobName": item["jobName"],
                "parentJobId": parent_by_child.get(job_id, ""),
                "parentJobName": parent_name_by_child.get(job_id, ""),
                "stage": _stage(job_id, parent_by_child, cycle_ids),
                "jobStatus": item["status"],
                "validationStatus": validation_status,
                "validationMessage": message,
                "inpPath": item["inpPath"],
                "oldjobPath": item["oldjobPath"],
            }
        )
    nodes.sort(key=lambda node: (node["stage"], node["jobName"].casefold()))
    roots = {
        parent_id
        for parent_id in parent_by_child.values()
        if parent_id not in parent_by_child
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "nodes": nodes,
        "nodeCount": len(nodes),
        "chainCount": len(roots),
        "checks": {
            "cycleCount": len(cycle_ids),
            "missingParentCount": len(missing_children),
            "incompatiblePathCount": len(incompatible_children),
            "validCount": sum(node["validationStatus"] == "valid" for node in nodes),
        },
        "hasIssues": bool(cycle_ids or missing_children or incompatible_children),
    }


__all__ = ["read_restart_chains"]
