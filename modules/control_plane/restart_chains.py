"""Read-only restart dependency topology and diagnostics."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from modules.submitter.app_paths import JOBLIST_PATH
from modules.submitter.queue_store import load_joblist_state
from modules.submitter.restart_topology import RestartTopology

from .contracts import SCHEMA_VERSION, ApiProblem
from .job_queues import project_job_queues


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


def _resolve_paths(
    job_ids: Iterable[str], parents: dict[str, str], cycle_ids: set[str], direct_issues: dict[str, tuple[str, str]],
) -> dict[str, tuple[int, str]]:
    """Cache the stage and nearest failing job on each path, including the job itself."""
    resolved = {job_id: (0, job_id) for job_id in cycle_ids}
    for job_id in job_ids:
        path = []
        current = job_id
        while current and current not in resolved:
            path.append(current)
            current = parents.get(current, "")
        stage, cause = resolved.get(current, (0, ""))
        reaches_cycle = bool(current) and stage == 0
        for child in reversed(path):
            if not reaches_cycle:
                stage += 1
            if child in direct_issues:
                cause = child
            resolved[child] = stage, cause
    return resolved


def _output_odb(item: dict[str, Any]) -> str:
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
            return str(candidate)
    return str(candidates[0]) if candidates else ""


def read_restart_chains(joblist_path: str | Path | None = None) -> dict[str, Any]:
    _, formal, error = load_joblist_state(joblist_path or JOBLIST_PATH, restore_active_state=False)
    if error:
        raise ApiProblem(500, "JOB_QUEUE_STATE_UNREADABLE", "无法读取重启动依赖所在的队列", details={"reason": error})
    topology = RestartTopology(formal)
    items = project_job_queues([], formal)["queueItems"]
    by_id = {item["jobId"]: item for item in items if item["jobId"]}
    parent_by_child = topology.parents
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
        parent = by_id.get(parent_by_child.get(item["jobId"], ""))
        if parent is not None:
            parent_name_by_child[item["jobId"]] = parent["jobName"]
        else:
            try:
                external_exists = bool(item["oldjobPath"] and Path(item["oldjobPath"]).is_file())
            except OSError:
                external_exists = False
            if not external_exists or topology.issues.get(item["jobId"], ("", ""))[0] == "missing_parent":
                missing_children.add(item["jobId"])
            parent_name_by_child[item["jobId"]] = oldjob_name
        if topology.issues.get(item["jobId"], ("", ""))[0] == "incompatible_path":
            incompatible_children.add(item["jobId"])

    cycle_ids = _cycle_ids(parent_by_child)
    direct_issues = {}
    for item in restart_items:
        job_id = item["jobId"]
        if job_id in cycle_ids:
            direct_issues[job_id] = ("cycle", "检测到循环依赖")
        elif job_id in missing_children:
            direct_issues[job_id] = ("missing_parent", f"未找到前置作业：{parent_name_by_child.get(job_id) or '尚未指定'}")
        elif job_id in incompatible_children:
            direct_issues[job_id] = topology.issues[job_id]
    paths = _resolve_paths(by_id, parent_by_child, cycle_ids, direct_issues)
    nodes: list[dict[str, Any]] = []
    for item in restart_items:
        job_id = item["jobId"]
        stage, cause = paths[job_id]
        if cause and cause != job_id:
            validation_status = "upstream_invalid"
            message = f"前置链在 {by_id[cause]['jobName']} 处受阻：{direct_issues[cause][1]}"
        else:
            validation_status, message = direct_issues.get(job_id, ("valid", "依赖有效"))
        nodes.append(
            {
                "itemId": item["itemId"],
                "jobId": job_id,
                "jobName": item["jobName"],
                "parentJobId": parent_by_child.get(job_id, ""),
                "parentJobName": parent_name_by_child.get(job_id, ""),
                "stage": stage,
                "jobStatus": item["status"],
                "validationStatus": validation_status,
                "validationMessage": message,
                "inpPath": item["inpPath"],
                "oldjobPath": item["oldjobPath"],
            }
        )
    nodes.sort(key=lambda node: (node["stage"], node["jobName"].casefold()))
    graph_job_ids = {
        str(item["jobId"])
        for item in restart_items
        if item.get("jobId")
    } | set(parent_by_child.values())
    graph_nodes: list[dict[str, Any]] = []
    restart_node_by_id = {node["jobId"]: node for node in nodes}
    for job_id in graph_job_ids:
        item = by_id.get(job_id)
        if item is None:
            continue
        restart_node = restart_node_by_id.get(job_id)
        graph_nodes.append(
            {
                "itemId": item["itemId"],
                "jobId": job_id,
                "jobName": item["jobName"],
                "parentJobId": parent_by_child.get(job_id, ""),
                "parentJobName": parent_name_by_child.get(job_id, ""),
                "stage": paths[job_id][0],
                "jobStatus": item["status"],
                "validationStatus": (
                    restart_node["validationStatus"] if restart_node else "valid"
                ),
                "validationMessage": (
                    restart_node["validationMessage"]
                    if restart_node
                    else "基础计算节点"
                ),
                "inpPath": item["inpPath"],
                "oldjobPath": item["oldjobPath"],
                "outputOdb": _output_odb(item),
                "isRestart": item["runMode"] == "restart",
            }
        )
    graph_nodes.sort(key=lambda node: (node["stage"], node["jobName"].casefold()))
    roots = {
        parent_id
        for parent_id in parent_by_child.values()
        if parent_id not in parent_by_child
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "nodes": nodes,
        "graphNodes": graph_nodes,
        "graphNodeCount": len(graph_nodes),
        "nodeCount": len(nodes),
        "chainCount": len(roots),
        "checks": {
            "cycleCount": len(cycle_ids),
            "missingParentCount": len(missing_children),
            "incompatiblePathCount": len(incompatible_children),
            "upstreamInvalidCount": sum(node["validationStatus"] == "upstream_invalid" for node in nodes),
            "validCount": sum(node["validationStatus"] == "valid" for node in nodes),
        },
        "hasIssues": bool(cycle_ids or missing_children or incompatible_children),
    }


__all__ = ["read_restart_chains"]
