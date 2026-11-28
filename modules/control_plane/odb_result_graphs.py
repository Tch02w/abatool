"""Persist independent ODB result forests and build read-only branch merge plans."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from modules.common.json_io import json_file_lock
from modules.submitter.app_paths import APP_DATA_DIR
from modules.submitter.queue_store import atomic_write_json

from .contracts import SCHEMA_VERSION, ApiProblem

_NODE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_NODE_FIELDS = {"nodeId", "name", "parentNodeId", "odbPath", "inpPath"}
_SAVE_FIELDS = {
    "schemaVersion",
    "action",
    "expectedRevision",
    "outputDirectory",
    "nodes",
}
_PLAN_FIELDS = {"schemaVersion", "targetNodeIds"}


def _text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field, "")
    if not isinstance(value, str) or "\0" in value:
        raise ApiProblem(400, "INVALID_RESULT_GRAPH_FIELD", f"{field} 必须是有效字符串")
    return value.strip()


def _validate_request(payload: Mapping[str, Any], fields: set[str]) -> None:
    if set(payload) - fields:
        raise ApiProblem(400, "UNKNOWN_FIELDS", "结果链请求包含不支持的字段")
    if (
        type(payload.get("schemaVersion")) is not int
        or payload["schemaVersion"] != SCHEMA_VERSION
    ):
        raise ApiProblem(400, "UNSUPPORTED_SCHEMA_VERSION", "不支持该请求结构版本")


def _nodes(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list) or len(raw) > 2000:
        raise ApiProblem(
            400, "INVALID_RESULT_GRAPH_NODES", "节点必须是列表，且不得超过 2000 个"
        )
    nodes: list[dict[str, str]] = []
    ids: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or set(item) - _NODE_FIELDS:
            raise ApiProblem(400, "INVALID_RESULT_GRAPH_NODE", "节点包含无效字段")
        node = {field: _text(item, field) for field in _NODE_FIELDS}
        node_id = node["nodeId"]
        if not _NODE_ID.fullmatch(node_id):
            raise ApiProblem(
                400,
                "INVALID_RESULT_GRAPH_NODE_ID",
                "节点 ID 必须是 1–64 位字母、数字、下划线或连字符",
            )
        if node_id.casefold() in ids:
            raise ApiProblem(
                400, "DUPLICATE_RESULT_GRAPH_NODE", f"节点 ID 重复：{node_id}"
            )
        ids.add(node_id.casefold())
        nodes.append(node)
    by_id = {node["nodeId"]: node for node in nodes}
    for node in nodes:
        parent_id = node["parentNodeId"]
        if parent_id and parent_id not in by_id:
            raise ApiProblem(
                400,
                "RESULT_GRAPH_PARENT_NOT_FOUND",
                f"找不到节点 {node['nodeId']} 的父节点",
            )
    visited: set[str] = set()
    for node in nodes:
        path: set[str] = set()
        current_id = node["nodeId"]
        while current_id and current_id not in visited:
            if current_id in path:
                raise ApiProblem(400, "RESULT_GRAPH_CYCLE", "结果链不能包含循环依赖")
            path.add(current_id)
            current_id = by_id[current_id]["parentNodeId"]
        visited.update(path)
    return nodes


def _path_key(path: Path) -> str:
    return str(path.resolve()).casefold()


def _source(node: Mapping[str, str]) -> Path | None:
    if node["odbPath"]:
        return Path(node["odbPath"]).expanduser()
    if node["inpPath"]:
        candidate = Path(node["inpPath"]).expanduser().with_suffix(".odb")
        if candidate.is_file():
            return candidate
    return None


def _name(node: Mapping[str, str]) -> str:
    return node["name"] or node["nodeId"]


class OdbResultGraphService:
    """A result-only document; never reads or changes the calculation queue."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = (
            Path(path) if path is not None else APP_DATA_DIR / "odb_result_graph.json"
        )

    def snapshot(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {
                "schemaVersion": SCHEMA_VERSION,
                "revision": 0,
                "outputDirectory": "",
                "nodes": [],
            }
        except (OSError, ValueError) as exc:
            raise ApiProblem(
                409,
                "INVALID_SAVED_RESULT_GRAPH",
                "结果链文件无法读取，请检查原文件后再保存",
            ) from exc
        try:
            if not isinstance(payload, dict):
                raise ValueError("not an object")  # noqa: TRY004 - persisted JSON uses value-error recovery
            _validate_request(
                payload, {"schemaVersion", "revision", "outputDirectory", "nodes"}
            )
            revision = payload.get("revision")
            if type(revision) is not int or revision < 0:
                raise ValueError("invalid revision")
            return {
                "schemaVersion": SCHEMA_VERSION,
                "revision": revision,
                "outputDirectory": _text(payload, "outputDirectory"),
                "nodes": _nodes(payload.get("nodes")),
            }
        except (ApiProblem, ValueError) as exc:
            raise ApiProblem(
                409, "INVALID_SAVED_RESULT_GRAPH", "结果链文件结构无效，已保留原文件"
            ) from exc

    def command(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        _validate_request(payload, _SAVE_FIELDS)
        if payload.get("action") != "save":
            raise ApiProblem(400, "INVALID_RESULT_GRAPH_ACTION", "不支持该结果链操作")
        revision = payload.get("expectedRevision")
        if type(revision) is not int or revision < 0:
            raise ApiProblem(
                400, "INVALID_RESULT_GRAPH_REVISION", "expectedRevision 必须是非负整数"
            )
        nodes = _nodes(payload.get("nodes"))
        output_directory = _text(payload, "outputDirectory")
        with json_file_lock(self.path):
            current = self.snapshot()
            if revision != current["revision"]:
                raise ApiProblem(
                    409,
                    "RESULT_GRAPH_REVISION_CONFLICT",
                    "结果链已被其他窗口修改，请重新载入后再保存",
                    details={"currentRevision": current["revision"]},
                )
            result = {
                "schemaVersion": SCHEMA_VERSION,
                "revision": revision + 1,
                "outputDirectory": output_directory,
                "nodes": nodes,
            }
            atomic_write_json(self.path, result)
            return result

    def plans(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        _validate_request(payload, _PLAN_FIELDS)
        raw_targets = payload.get("targetNodeIds")
        if (
            not isinstance(raw_targets, list)
            or not raw_targets
            or any(
                not isinstance(value, str) or not _NODE_ID.fullmatch(value)
                for value in raw_targets
            )
        ):
            raise ApiProblem(
                400, "INVALID_RESULT_GRAPH_TARGETS", "请选择至少一个有效的目标节点"
            )
        target_ids = list(dict.fromkeys(raw_targets))
        graph = self.snapshot()
        issues: list[str] = []
        by_id = {node["nodeId"]: node for node in graph["nodes"]}
        directory = Path(graph["outputDirectory"]).expanduser()
        if (
            not graph["outputDirectory"]
            or not directory.is_absolute()
            or not directory.is_dir()
        ):
            issues.append("请选择存在的完整结果输出目录。")

        # Reserve every source, including unselected branches, before allocating outputs.
        sources: dict[str, Path | None] = {}
        reserved: set[str] = set()
        for node_id, node in by_id.items():
            try:
                source = _source(node)
                sources[node_id] = source
                if source is not None:
                    reserved.add(_path_key(source))
            except OSError, ValueError:
                sources[node_id] = None

        plans: list[dict[str, Any]] = []
        output_by_node: dict[str, Path] = {}
        for target_id in target_ids:
            target = by_id.get(target_id)
            if target is None:
                issues.append(f"找不到目标节点：{target_id}")
                continue
            if not target["parentNodeId"]:
                issues.append(f"{_name(target)} 是基础节点，无需链式合并。")
                continue
            ancestry = [target]
            while ancestry[-1]["parentNodeId"]:
                ancestry.append(by_id[ancestry[-1]["parentNodeId"]])
            ancestry.reverse()
            branch_issues: list[str] = []
            seen_sources: set[str] = set()
            for node in ancestry:
                source = sources[node["nodeId"]]
                try:
                    if (
                        source is None
                        or not source.is_absolute()
                        or source.suffix.lower() != ".odb"
                        or not source.is_file()
                        or source.stat().st_size == 0
                    ):
                        branch_issues.append(f"{_name(node)} 缺少有效的 ODB 文件。")
                    elif _path_key(source) in seen_sources:
                        branch_issues.append(
                            f"{_name(node)} 与前置节点重复使用同一个 ODB。"
                        )
                    else:
                        seen_sources.add(_path_key(source))
                except OSError, ValueError:
                    branch_issues.append(f"{_name(node)} 的 ODB 文件无法访问。")
            if branch_issues:
                issues.extend(branch_issues)
                continue
            if issues:
                continue
            current_full = str(sources[ancestry[0]["nodeId"]])
            steps: list[dict[str, Any]] = []
            for index, node in enumerate(ancestry[1:], 1):
                slug = (
                    re.sub(r"[^\w-]+", "_", _name(node), flags=re.UNICODE).strip("_")[
                        :40
                    ]
                    or "odb"
                )
                output = output_by_node.get(node["nodeId"])
                if output is None:
                    stem = f"result_{slug}_{node['nodeId']}_full_joined"
                    output = directory / f"{stem}.odb"
                    number = 2
                    while _path_key(output) in reserved or output.exists():
                        output = directory / f"{stem}_{number}.odb"
                        number += 1
                    reserved.add(_path_key(output))
                    output_by_node[node["nodeId"]] = output
                steps.append(
                    {
                        "index": index,
                        "jobId": node["nodeId"],
                        "jobName": _name(node),
                        "originalOdb": current_full,
                        "restartOdb": str(sources[node["nodeId"]]),
                        "outputOdb": str(output),
                        "status": "ready",
                    }
                )
                current_full = str(output)
            plans.append(
                {
                    "schemaVersion": SCHEMA_VERSION,
                    "planKind": "restart-result-materialization",
                    "targetItemId": target_id,
                    "targetJobId": target_id,
                    "targetJobName": _name(target),
                    "valid": True,
                    "issues": [],
                    "ancestry": [
                        {
                            "itemId": node["nodeId"],
                            "jobId": node["nodeId"],
                            "jobName": _name(node),
                            "runMode": "restart" if node["parentNodeId"] else "normal",
                            "status": "可用",
                            "outputOdb": str(sources[node["nodeId"]]),
                        }
                        for node in ancestry
                    ],
                    "steps": steps,
                    "finalOutputOdb": current_full,
                }
            )
        return {
            "schemaVersion": SCHEMA_VERSION,
            "graphRevision": graph["revision"],
            "valid": not issues and bool(plans),
            "issues": list(dict.fromkeys(issues)),
            "plans": plans if not issues else [],
        }


__all__ = ["OdbResultGraphService"]
