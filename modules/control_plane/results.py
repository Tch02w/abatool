"""Qt-free result scope, catalog, and preview API services."""

from __future__ import annotations

import csv
import heapq
import os
import stat
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from operator import itemgetter
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from modules.postprocessor.naming import natural_sort_key
from modules.postprocessor.result_assets import (
    ASSET_MANIFEST_NAME,
    INCOMPLETE_OUTPUT_MARKER,
    SHARED_DATA_ROOT_NAME,
    is_incomplete_output,
)
from modules.postprocessor.result_catalog import (
    SECTION_TABS,
    ResultRecord,
    classify_result,
    collect_result_records,
    collect_shared_asset_records,
    preview_row_limit,
    read_csv_preview,
    read_xlsx_preview,
    result_section,
)
from modules.postprocessor.result_index import (
    ResultIndexInvalid,
    index_path,
    is_result_index_artifact,
    load_result_index,
)

from .contracts import SCHEMA_VERSION, ApiProblem

MAX_RESULT_PAGE_SIZE = 500
MAX_TEXT_PREVIEW_BYTES = 256 * 1024
TEXT_SUFFIXES = frozenset({".json", ".ndjson", ".log", ".rpy", ".txt"})
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif"})
RESULT_SECTIONS = frozenset(key for key, _label in SECTION_TABS) | {"other"}


def _reject_unknown_fields(payload: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ApiProblem(
            400,
            "UNKNOWN_FIELDS",
            "请求包含 v1 协议不支持的字段",
            details={"fields": unknown},
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


def _required_path(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ApiProblem(400, f"INVALID_{name.upper()}", f"{name} 必须是非空路径字符串")
    return value.strip()


def _resolve_directory(raw_path: str, *, code_prefix: str) -> Path:
    try:
        path = Path(raw_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ApiProblem(
            400,
            f"{code_prefix}_NOT_FOUND",
            "结果目录不存在或无法解析",
            details={"path": raw_path, "reason": str(exc)},
        ) from exc
    if not path.is_dir():
        raise ApiProblem(
            400,
            f"{code_prefix}_NOT_DIRECTORY",
            "结果路径必须指向目录",
            details={"path": str(path)},
        )
    return path


def _require_below(path: Path, root: Path, *, field: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ApiProblem(
            400,
            "PATH_OUTSIDE_RESULT_ROOT",
            f"{field} 必须位于结果根目录内",
            details={"field": field, "path": str(path), "root": str(root)},
        ) from exc


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def _child_directories(path: Path, warnings: list[str]) -> list[Path]:
    try:
        children = [
            child
            for child in path.iterdir()
            if child.is_dir() and not _is_link_or_junction(child)
        ]
    except OSError as exc:
        warnings.append(f"无法读取目录 {path}：{exc}")
        return []
    return children


def is_indexable_group(path: Path) -> bool:
    return not path.name.startswith(("_", ".")) and path.name.casefold() != SHARED_DATA_ROOT_NAME.casefold()


def index_scope_directories(root: Path, scope: Path) -> list[Path]:
    """Enumerate only ordinary group/time directories, newest time name first."""
    warnings: list[str] = []
    groups = _child_directories(root, warnings) if scope == root else [scope]
    times = [
        directory
        for group in groups
        if is_indexable_group(group)
        for directory in _child_directories(group, warnings)
        if not directory.name.startswith(("_", ".")) and not is_incomplete_output(directory)
    ]
    if warnings:
        raise ApiProblem(400, "RESULT_SCOPE_UNREADABLE", "无法完整读取索引范围", details={"warnings": warnings})
    return sorted(times, key=lambda path: (natural_sort_key(path.name), str(path)), reverse=True)


def discover_result_scopes(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return the legacy result hierarchy as a flat, stable path tree."""

    _reject_unknown_fields(payload, {"schemaVersion", "root", "includeInternal"})
    root = _resolve_directory(_required_path(payload, "root"), code_prefix="RESULT_ROOT")
    include_internal = payload.get("includeInternal", False)
    if not isinstance(include_internal, bool):
        raise ApiProblem(400, "INVALID_INCLUDE_INTERNAL", "includeInternal 必须是布尔值")

    warnings: list[str] = []
    nodes: list[dict[str, Any]] = []

    def add_node(
        path: Path,
        name: str,
        kind: str,
        parent: Path | None,
        time_directory: Path | None = None,
    ) -> None:
        nodes.append(
            {
                "path": str(path),
                "name": name,
                "kind": kind,
                "parentPath": "" if parent is None else str(parent),
                "timeDirectory": "" if time_directory is None else str(time_directory),
                "indexState": (
                    "available"
                    if time_directory is not None and index_path(time_directory).is_file()
                    else "missing"
                    if time_directory is not None
                    else "not_applicable"
                ),
            }
        )

    add_node(root, "全部结果", "root", None)
    for group in sorted(
        _child_directories(root, warnings),
        key=lambda path: natural_sort_key(path.name),
    ):
        if group.name.startswith("_") and not include_internal:
            continue
        if group.name == SHARED_DATA_ROOT_NAME:
            add_node(group, "ODB 公共数据", "shared_root", root)
            for odb_data in sorted(
                _child_directories(group, warnings),
                key=lambda path: natural_sort_key(path.name),
            ):
                add_node(odb_data, odb_data.name, "shared_odb", group)
                for asset in sorted(
                    _child_directories(odb_data, warnings),
                    key=lambda path: natural_sort_key(path.name),
                    reverse=True,
                ):
                    add_node(asset, asset.name, "shared_asset", odb_data)
            continue

        add_node(group, group.name, "group", root)
        batches = sorted(
            _child_directories(group, warnings),
            key=lambda path: natural_sort_key(path.name),
            reverse=True,
        )
        for batch in batches:
            add_node(batch, batch.name, "batch", group, batch)
            for odb in sorted(
                _child_directories(batch, warnings),
                key=lambda path: natural_sort_key(path.name),
            ):
                add_node(odb, odb.name, "odb", batch, batch)

    return {
        "schemaVersion": SCHEMA_VERSION,
        "root": str(root),
        "nodes": nodes,
        "count": len(nodes),
        "warnings": warnings,
    }


def _record_from_index(time_directory: Path, row: Mapping[str, Any]) -> ResultRecord:
    return ResultRecord(
        path=time_directory / str(row["relative_path"]),
        use_case=str(row["use_case"]),
        description=str(row["description"]),
        recommended=bool(row["recommended"]),
        section=str(row["section"]),
        size=int(row["size"]),
        mtime_ns=int(row["mtime_ns"]),
        error=str(row.get("error", "")),
    )


def _record_payload(record: ResultRecord, scope: Path) -> dict[str, Any]:
    try:
        relative_path = str(record.path.relative_to(scope))
    except ValueError:
        relative_path = str(record.path)
    modified_at = ""
    if record.mtime_ns > 0:
        modified_at = (
            datetime.fromtimestamp(record.mtime_ns / 1_000_000_000, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
    return {
        "path": str(record.path),
        "relativePath": relative_path,
        "name": record.path.name,
        "suffix": record.path.suffix.casefold(),
        "useCase": record.use_case,
        "description": record.description,
        "recommended": record.recommended,
        "section": result_section(record),
        "sizeBytes": record.size,
        "modifiedAt": modified_at,
        "error": record.error,
        "internal": record.internal,
        "isDirectory": record.is_directory,
    }


def _direct_entry_visible(path: Path, info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    return not (
        path.name.startswith((".", "_", "~$"))
        or is_result_index_artifact(path)
        or stat.S_ISLNK(info.st_mode)
        or attributes & (stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_REPARSE_POINT)
    )


def _direct_directory(payload: Mapping[str, Any], root: Path) -> Path:
    batch, scope, directory = (
        Path(_required_path(payload, key)) for key in ("timeDirectory", "scope", "directDirectory")
    )
    if not all(path.is_absolute() and ".." not in path.parts for path in (batch, scope, directory)):
        raise ApiProblem(400, "INVALID_DIRECT_DIRECTORY", "直接浏览需要无回退段的完整目录路径")
    if (
        not batch.is_relative_to(root)
        or len(batch.relative_to(root).parts) != 2
        or batch.parent.name.casefold() == SHARED_DATA_ROOT_NAME.casefold()
        or (scope != batch and scope.parent != batch)
    ):
        raise ApiProblem(400, "INVALID_DIRECT_SCOPE", "请选择当前结果根目录内的时间目录或模型结果目录")
    _require_below(directory, scope, field="directDirectory")
    current = root
    try:
        for part in directory.relative_to(root).parts:
            current /= part
            info = current.lstat()
            if not stat.S_ISDIR(info.st_mode) or not _direct_entry_visible(current, info):
                raise ApiProblem(400, "INVALID_DIRECT_DIRECTORY", "目录不可浏览或包含内部目录、链接")
        if is_incomplete_output(directory):
            raise ApiProblem(409, "RESULT_OUTPUT_INCOMPLETE", "该结果尚未完成发布，请等待提取结束")
    except OSError as exc:
        raise ApiProblem(400, "DIRECT_DIRECTORY_UNAVAILABLE", f"无法访问当前目录：{exc}") from exc
    return directory


def _direct_records(directory: Path) -> Iterator[ResultRecord]:
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                try:
                    info = entry.stat(follow_symlinks=False)
                except FileNotFoundError:
                    continue  # The writer removed the entry between enumeration and stat.
                if not _direct_entry_visible(path, info):
                    continue
                if stat.S_ISDIR(info.st_mode):
                    if not (path / INCOMPLETE_OUTPUT_MARKER).is_file():
                        yield ResultRecord(path, "文件夹", "进入此目录", section="other",
                                           mtime_ns=info.st_mtime_ns, is_directory=True)
                elif stat.S_ISREG(info.st_mode):
                    yield replace(classify_result(path), size=info.st_size, mtime_ns=info.st_mtime_ns)
    except OSError as exc:
        raise ApiProblem(400, "DIRECT_DIRECTORY_UNAVAILABLE", f"无法读取当前目录：{exc}") from exc


@dataclass(frozen=True)
class _DirectPageAnchor:
    name: str
    is_directory: bool
    before: bool


def _direct_anchor(payload: Mapping[str, Any]) -> _DirectPageAnchor | None:
    if "directAnchor" not in payload:
        return None
    value = payload["directAnchor"]
    if (
        "directDirectory" not in payload
        or not isinstance(value, dict)
        or set(value) != {"name", "isDirectory", "direction"}
        or not isinstance(name := value["name"], str)
        or not 1 <= len(name) <= 255
        or name in {".", ".."}
        or Path(name).name != name
        or "\x00" in name
        or not isinstance(value["isDirectory"], bool)
        or value["direction"] not in ("before", "after")
    ):
        raise ApiProblem(400, "INVALID_DIRECT_ANCHOR", "直接浏览翻页需要当前页边界条目的名称、类型和翻页方向")
    return _DirectPageAnchor(name, value["isDirectory"], value["direction"] == "before")


def _direct_order(name: str, is_directory: bool) -> tuple:
    return not is_directory, natural_sort_key(name), name


def _direct_page(
    records: Iterable[ResultRecord], offset: int, limit: int, anchor: _DirectPageAnchor | None,
) -> tuple[list[ResultRecord], int]:
    if anchor is None:
        prefix = heapq.nsmallest(offset + limit, records, key=lambda r: _direct_order(r.path.name, r.is_directory))
        return prefix[offset:], offset

    boundary = _direct_order(anchor.name, anchor.is_directory)
    preceding = 0

    def candidates():
        nonlocal preceding
        for record in records:
            key = _direct_order(record.path.name, record.is_directory)
            if anchor.before:
                if key < boundary:
                    preceding += 1
                    yield key, record
            elif key > boundary:
                yield key, record
            else:
                preceding += 1

    # Backward paging keeps the nearest earlier rows, then restores display order.
    if anchor.before:
        ranked = heapq.nlargest(limit, candidates(), key=itemgetter(0))
        ranked.reverse()
        return [record for _, record in ranked], preceding - len(ranked)
    ranked = heapq.nsmallest(limit, candidates(), key=itemgetter(0))
    return [record for _, record in ranked], preceding


def list_result_records(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Load an indexed time scope or a shared asset, then filter and page it."""

    allowed = {
        "schemaVersion",
        "root",
        "scope",
        "timeDirectory",
        "directDirectory",
        "directAnchor",
        "section",
        "query",
        "useCase",
        "includeInternal",
        "offset",
        "limit",
    }
    _reject_unknown_fields(payload, allowed)
    root = _resolve_directory(_required_path(payload, "root"), code_prefix="RESULT_ROOT")
    scope = _resolve_directory(_required_path(payload, "scope"), code_prefix="RESULT_SCOPE")
    _require_below(scope, root, field="scope")

    raw_time_directory = payload.get("timeDirectory", "")
    if not isinstance(raw_time_directory, str):
        raise ApiProblem(400, "INVALID_TIME_DIRECTORY", "timeDirectory 必须是路径字符串")

    anchor = _direct_anchor(payload)
    offset = payload.get("offset", 0)
    limit = payload.get("limit", 200)
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ApiProblem(400, "INVALID_OFFSET", "offset 必须是非负整数")
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= MAX_RESULT_PAGE_SIZE
    ):
        raise ApiProblem(
            400,
            "INVALID_LIMIT",
            "limit 超出允许范围",
            details={"minimum": 1, "maximum": MAX_RESULT_PAGE_SIZE},
        )
    include_internal = payload.get("includeInternal", False)
    if not isinstance(include_internal, bool):
        raise ApiProblem(400, "INVALID_INCLUDE_INTERNAL", "includeInternal 必须是布尔值")
    section = payload.get("section", "all")
    if not isinstance(section, str) or section not in RESULT_SECTIONS:
        raise ApiProblem(
            400,
            "INVALID_RESULT_SECTION",
            "section 不是受支持的结果分类",
            details={"supported": sorted(RESULT_SECTIONS)},
        )
    query = payload.get("query", "")
    use_case = payload.get("useCase", "")
    if not isinstance(query, str) or not isinstance(use_case, str):
        raise ApiProblem(400, "INVALID_RESULT_FILTER", "query 和 useCase 必须是字符串")
    query_text = query.strip().casefold()
    use_case_text = use_case.strip().casefold()

    records: Iterable[ResultRecord]
    metadata: dict[str, str] = {}
    source = "shared_asset"
    if "directDirectory" in payload:
        directory = _direct_directory(payload, root)
        records = _direct_records(directory)
        source = "direct"
    elif raw_time_directory.strip():
        time_directory = _resolve_directory(
            raw_time_directory.strip(),
            code_prefix="TIME_DIRECTORY",
        )
        _require_below(time_directory, root, field="timeDirectory")
        _require_below(scope, time_directory, field="scope")
        try:
            loaded = load_result_index(time_directory)
        except ResultIndexInvalid as exc:
            code = "RESULT_INDEX_MISSING" if not index_path(time_directory).is_file() else "RESULT_INDEX_INVALID"
            raise ApiProblem(
                409,
                code,
                str(exc),
                retryable=True,
                details={"timeDirectory": str(time_directory)},
            ) from exc
        records = [
            _record_from_index(time_directory, row)
            for row in loaded.records
            if scope == time_directory or (time_directory / str(row["relative_path"])).is_relative_to(scope)
        ]
        records.extend(collect_shared_asset_records(scope))
        metadata = loaded.metadata
        source = "index"
    else:
        records = [
            record
            for record in collect_result_records(scope)
            if record.path.name != ASSET_MANIFEST_NAME
        ]

    total_count = filtered_count = recommended_count = 0
    primary_counts: Counter[str] = Counter()
    use_cases: set[str] = set()

    def matching_records() -> Iterator[ResultRecord]:
        nonlocal total_count, filtered_count, recommended_count
        for record in records:
            if record.internal and not include_internal:
                continue
            primary = result_section(record)
            total_count += 1
            primary_counts[primary] += 1
            recommended_count += record.recommended
            use_cases.add(record.use_case)
            if section == "common" and not record.recommended:
                continue
            if section not in ("all", "common", primary):
                continue
            if use_case_text and record.use_case.casefold() != use_case_text:
                continue
            if query_text:
                haystack = "\n".join((record.path.name, str(record.path), record.use_case, record.description))
                if query_text not in haystack.casefold():
                    continue
            filtered_count += 1
            yield record

    if source == "direct":
        page, offset = _direct_page(matching_records(), offset, limit, anchor)
    else:
        ordered = sorted(
            matching_records(),
            key=lambda record: (
                not record.recommended,
                record.use_case.casefold(),
                natural_sort_key(record.path.name),
                str(record.path).casefold(),
            ),
        )
        page = ordered[offset : offset + limit]
    section_counts = {key: primary_counts[key] for key, _label in SECTION_TABS}
    section_counts["common"] = recommended_count
    section_counts["all"] = total_count
    return {
        "schemaVersion": SCHEMA_VERSION,
        "root": str(root),
        "scope": str(scope),
        "source": source,
        **({"directDirectory": str(directory)} if source == "direct" else {}),
        "records": [_record_payload(record, scope) for record in page],
        "totalCount": total_count,
        "filteredCount": filtered_count,
        "offset": offset,
        "limit": limit,
        "hasMore": offset + len(page) < filtered_count,
        "useCases": sorted(use_cases, key=str.casefold),
        "sectionCounts": section_counts,
        "indexMetadata": metadata,
    }


def preview_result(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a bounded preview descriptor without loading Qt or executing files."""

    _reject_unknown_fields(payload, {"schemaVersion", "root", "path", "maxRows"})
    root = _resolve_directory(_required_path(payload, "root"), code_prefix="RESULT_ROOT")
    raw_path = _required_path(payload, "path")
    try:
        path = Path(raw_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ApiProblem(
            404,
            "RESULT_FILE_NOT_FOUND",
            "结果文件不存在或无法解析",
            details={"path": raw_path, "reason": str(exc)},
        ) from exc
    _require_below(path, root, field="path")
    if not path.is_file():
        raise ApiProblem(400, "RESULT_PATH_NOT_FILE", "预览路径必须指向文件")

    max_rows = payload.get("maxRows", preview_row_limit(path))
    if (
        not isinstance(max_rows, int)
        or isinstance(max_rows, bool)
        or not 1 <= max_rows <= 100
    ):
        raise ApiProblem(400, "INVALID_MAX_ROWS", "maxRows 必须是 1–100 的整数")

    suffix = path.suffix.casefold()
    base = {
        "schemaVersion": SCHEMA_VERSION,
        "path": str(path),
        "name": path.name,
        "sizeBytes": path.stat().st_size,
    }
    try:
        if suffix in {".csv", ".xlsx"}:
            reader = read_csv_preview if suffix == ".csv" else read_xlsx_preview
            headers, rows = reader(path, max_rows + 1)
            return base | {
                "kind": "table", "headers": headers, "rows": rows[:max_rows],
                "truncated": len(rows) > max_rows,
            }
        if suffix in TEXT_SUFFIXES:
            with path.open("rb") as stream:
                content = stream.read(MAX_TEXT_PREVIEW_BYTES + 1)
            truncated = len(content) > MAX_TEXT_PREVIEW_BYTES
            text = content[:MAX_TEXT_PREVIEW_BYTES].decode("utf-8-sig", errors="replace")
            return base | {"kind": "text", "text": text, "truncated": truncated}
        if suffix in IMAGE_SUFFIXES:
            return base | {"kind": "image", "mediaPath": str(path)}
        return base | {
            "kind": "unsupported",
            "message": "该文件类型不支持内嵌预览，可使用打开或定位操作。",
        }
    except (OSError, ValueError, IndexError, KeyError, BadZipFile, ParseError, csv.Error) as exc:
        raise ApiProblem(
            422,
            "RESULT_PREVIEW_FAILED",
            "无法读取结果预览",
            retryable=True,
            details={"path": str(path), "reason": str(exc)},
        ) from exc


__all__ = [
    "IMAGE_SUFFIXES",
    "MAX_RESULT_PAGE_SIZE",
    "MAX_TEXT_PREVIEW_BYTES",
    "RESULT_SECTIONS",
    "TEXT_SUFFIXES",
    "discover_result_scopes",
    "list_result_records",
    "preview_result",
]
