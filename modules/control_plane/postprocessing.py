"""Asynchronous ODB post-processing operations for the native client."""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from modules.postprocessor.cache import abaqus_cache_version
from modules.postprocessor.config import load_defaults
from modules.postprocessor.postprocess_execution import (
    PostprocessGroup,
    PostprocessJob,
    PostprocessOptions,
    PostprocessPlan,
    analyze_postprocess_inputs,
    execute_postprocess_plan,
)
from modules.postprocessor.process_runner import ProcessCancelled
from modules.postprocessor.runner_parallel import MultiProcessController
from modules.submitter.cpu_policy import logical_cpu_count

from .compatibility import ABAQUS_COMMAND_ENV, ABAQUS_RELEASE_ENV
from .contracts import (
    MAX_CLIENT_REQUEST_ID_LENGTH,
    SCHEMA_VERSION,
    ApiProblem,
    utc_now_text,
)
from .events import EventStore
from .region_extraction import (
    REGION_KIND,
    RegionExtractionRequest,
    execute_region_extraction,
    finalize_region_extraction,
)
from .shutdown_guard import OperationShutdownGuard

SCAN_KIND = "odb.postprocess.scan"
RUN_KIND = "odb.postprocess.run"
MAX_OPERATION_LOG_LINES = 500
TERMINAL_STATUSES = frozenset({"succeeded", "cancelled", "failed"})
OPERATION_STATUSES = frozenset(
    {"queued", "starting", "running", "cancelling", *TERMINAL_STATUSES}
)
FRAME_MODES = frozenset({"auto", "all", "manual"})
LOAD_DIRECTIONS = frozenset({"1", "3", "1+3"})
PILE_TYPES = frozenset({"RC", "CFST"})
REBAR_METHODS = frozenset({"element_cut", "legacy_interpolation"})
IMAGE_UNITS = frozenset({"px", "mm"})


class PostprocessScanRunner(Protocol):
    def __call__(
        self,
        request: PostprocessScanRequest,
        progress: Callable[[int, str], None] | None,
        log: Callable[[str], None] | None,
        controller: MultiProcessController,
    ) -> dict[str, Any]: ...


class PostprocessRunRunner(Protocol):
    def __call__(
        self,
        plan: PostprocessPlan,
        progress: Callable[[int, str], None] | None,
        log: Callable[[str], None] | None,
        controller: MultiProcessController,
    ) -> dict[str, Any]: ...


def _text(payload: Mapping[str, Any], name: str, *, allow_empty: bool = False) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        qualifier = "字符串" if allow_empty else "非空字符串"
        raise ApiProblem(
            400,
            "INVALID_POSTPROCESS_FIELD",
            f"{name} 必须是{qualifier}",
            details={"field": name},
        )
    return value.strip()


def _flag(payload: Mapping[str, Any], name: str) -> bool:
    value = payload.get(name)
    if not isinstance(value, bool):
        raise ApiProblem(
            400,
            "INVALID_POSTPROCESS_FIELD",
            f"{name} 必须是布尔值",
            details={"field": name},
        )
    return value


def _integer(
    payload: Mapping[str, Any],
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ApiProblem(
            400,
            "INVALID_POSTPROCESS_FIELD",
            f"{name} 必须是 {minimum} 到 {maximum} 的整数",
            details={"field": name},
        )
    return value


def _number(
    payload: Mapping[str, Any],
    name: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ApiProblem(
            400,
            "INVALID_POSTPROCESS_FIELD",
            f"{name} 必须是数值",
            details={"field": name},
        )
    number = float(value)
    if not minimum <= number <= maximum:
        raise ApiProblem(
            400,
            "INVALID_POSTPROCESS_FIELD",
            f"{name} 必须在 {minimum:g} 到 {maximum:g} 之间",
            details={"field": name},
        )
    return number


def _client_request_id(payload: Mapping[str, Any]) -> str:
    value = _text(payload, "clientRequestId")
    if len(value) > MAX_CLIENT_REQUEST_ID_LENGTH or any(ord(character) < 32 for character in value):
        raise ApiProblem(
            400,
            "INVALID_CLIENT_REQUEST_ID",
            "clientRequestId 长度或字符不符合 v1 约束",
        )
    return value


def _validate_fields(
    payload: Mapping[str, Any],
    allowed: set[str],
    *,
    required: set[str] | None = None,
    check_schema: bool = True,
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ApiProblem(
            400,
            "UNKNOWN_FIELDS",
            "ODB 后处理请求包含 v1 协议不支持的字段",
            details={"fields": unknown},
        )
    missing = sorted((required or allowed) - set(payload))
    if missing:
        raise ApiProblem(
            400,
            "MISSING_FIELDS",
            "ODB 后处理请求缺少必填字段",
            details={"fields": missing},
        )
    if check_schema and payload.get("schemaVersion") != SCHEMA_VERSION:
        raise ApiProblem(400, "UNSUPPORTED_SCHEMA_VERSION", "不支持该请求结构版本")


def _resolve_root(value: str) -> Path:
    try:
        root = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ApiProblem(
            400,
            "ROOT_NOT_FOUND",
            "ODB 根目录不存在或无法解析",
            details={"root": value, "reason": str(exc)},
        ) from exc
    if not root.is_dir():
        raise ApiProblem(400, "ROOT_NOT_DIRECTORY", "ODB root 必须指向目录")
    return root


def _resolve_odb_path(root: Path, value: str, index: int) -> Path:
    try:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        path = candidate.resolve(strict=True)
        path.relative_to(root)
    except ValueError as exc:
        raise ApiProblem(
            400,
            "PATH_OUTSIDE_ROOT",
            "ODB 路径必须位于 root 目录内",
            details={"index": index, "path": value, "root": str(root)},
        ) from exc
    except (OSError, RuntimeError) as exc:
        raise ApiProblem(
            400,
            "ODB_NOT_FOUND",
            "ODB 文件不存在或无法解析",
            details={"index": index, "path": value, "reason": str(exc)},
        ) from exc
    if not path.is_file() or path.suffix.casefold() != ".odb":
        raise ApiProblem(
            400,
            "INVALID_ODB_PATH",
            "后处理输入必须是存在的 .odb 文件",
            details={"index": index, "path": str(path)},
        )
    return path


def _resolve_paths(root: Path, raw_paths: Any) -> tuple[Path, ...]:
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ApiProblem(400, "INVALID_POSTPROCESS_PATHS", "paths 必须是非空数组")
    paths: list[Path] = []
    seen: set[str] = set()
    for index, value in enumerate(raw_paths):
        if not isinstance(value, str) or not value.strip():
            raise ApiProblem(
                400,
                "INVALID_ODB_PATH",
                "paths 中的每一项必须是非空字符串",
                details={"index": index},
            )
        path = _resolve_odb_path(root, value, index)
        key = os.path.normcase(str(path))
        if key in seen:
            raise ApiProblem(
                400,
                "DUPLICATE_ODB_PATH",
                "paths 不允许包含重复的 ODB 路径",
                details={"index": index, "path": str(path)},
            )
        seen.add(key)
        paths.append(path)
    return tuple(paths)


@dataclass(frozen=True)
class PostprocessScanRequest:
    client_request_id: str
    root: Path
    paths: tuple[Path, ...]
    parallel_workers: int
    force_rescan: bool

    @property
    def signature(self) -> tuple[Any, ...]:
        return (
            SCAN_KIND,
            os.path.normcase(str(self.root)),
            tuple(os.path.normcase(str(path)) for path in self.paths),
            self.parallel_workers,
            self.force_rescan,
        )

    def summary(self) -> dict[str, Any]:
        return {
            "clientRequestId": self.client_request_id,
            "root": str(self.root),
            "paths": [str(path) for path in self.paths],
            "parallelWorkers": self.parallel_workers,
            "forceRescan": self.force_rescan,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> PostprocessScanRequest:
        allowed = {
            "schemaVersion",
            "clientRequestId",
            "root",
            "paths",
            "parallelWorkers",
            "forceRescan",
        }
        _validate_fields(payload, allowed)
        root = _resolve_root(_text(payload, "root"))
        return cls(
            client_request_id=_client_request_id(payload),
            root=root,
            paths=_resolve_paths(root, payload.get("paths")),
            parallel_workers=_integer(
                payload, "parallelWorkers", minimum=1, maximum=logical_cpu_count()
            ),
            force_rescan=_flag(payload, "forceRescan"),
        )


@dataclass(frozen=True)
class PostprocessRunRequest:
    client_request_id: str
    plan: PostprocessPlan

    @property
    def signature(self) -> tuple[Any, ...]:
        options = self.plan.options
        return (
            RUN_KIND,
            os.path.normcase(str(options.root)),
            tuple(
                sorted(
                    (
                        os.path.normcase(str(path)),
                        repr(job),
                    )
                    for path, job in self.plan.jobs.items()
                )
            ),
            tuple(repr(group) for group in self.plan.groups),
            repr(options),
        )

    def summary(self) -> dict[str, Any]:
        options = self.plan.options
        return {
            "clientRequestId": self.client_request_id,
            "root": str(options.root),
            "jobCount": len(self.plan.jobs),
            "groupCount": len(self.plan.groups),
            "parallelWorkers": options.parallel_workers,
            "forceRescan": options.force_rescan,
            "batchId": self.plan.batch_id,
        }

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        abaqus_command: str,
        defaults: Mapping[str, Any],
    ) -> PostprocessRunRequest:
        allowed = {
            "schemaVersion",
            "clientRequestId",
            "root",
            "parallelWorkers",
            "forceRescan",
            "fullTimehistoryFreebody",
            "rebarMethod",
            "expectedLongitudinalRebarCount",
            "imageSizeUnit",
            "imageWidth",
            "imageHeight",
            "exportWhiteBackgroundPng",
            "exportTransparentBackgroundPng",
            "animationFps",
            "animationDurationSeconds",
            "rebarCutToleranceMm",
            "jobs",
            "groups",
        }
        _validate_fields(payload, allowed, required=allowed - {"animationDurationSeconds"})
        root = _resolve_root(_text(payload, "root"))
        settings = dict(defaults)
        image_unit = _text(payload, "imageSizeUnit")
        if image_unit not in IMAGE_UNITS:
            raise ApiProblem(400, "INVALID_IMAGE_UNIT", "imageSizeUnit 必须是 px 或 mm")
        width_limits = (320, 4096) if image_unit == "px" else (30, 500)
        height_limits = width_limits
        settings.update(
            {
                "abaqus_command": abaqus_command,
                "image_size_unit": image_unit,
                "image_width": _integer(
                    payload, "imageWidth", minimum=width_limits[0], maximum=width_limits[1]
                ),
                "image_height": _integer(
                    payload,
                    "imageHeight",
                    minimum=height_limits[0],
                    maximum=height_limits[1],
                ),
                "export_white_background_png": _flag(
                    payload, "exportWhiteBackgroundPng"
                ),
                "export_transparent_background_png": _flag(
                    payload, "exportTransparentBackgroundPng"
                ),
                "animation_fps": _integer(
                    payload, "animationFps", minimum=1, maximum=60
                ),
                "rebar_cut_tolerance_mm": _number(
                    payload, "rebarCutToleranceMm", minimum=0.0, maximum=100.0
                ),
            }
        )
        if "animationDurationSeconds" in payload:
            settings["animation_duration_seconds"] = _number(
                payload, "animationDurationSeconds", minimum=0.01, maximum=sys.float_info.max
            )
        else:
            settings.pop("animation_duration_seconds", None)
        if not settings["export_white_background_png"] and not settings[
            "export_transparent_background_png"
        ]:
            raise ApiProblem(
                400,
                "NO_IMAGE_OUTPUT",
                "白底 PNG 与透明底 PNG 至少启用一项",
            )
        rebar_method = _text(payload, "rebarMethod")
        if rebar_method not in REBAR_METHODS:
            raise ApiProblem(400, "INVALID_REBAR_METHOD", "rebarMethod 不受支持")

        raw_jobs = payload.get("jobs")
        if not isinstance(raw_jobs, list) or not raw_jobs:
            raise ApiProblem(400, "INVALID_POSTPROCESS_JOBS", "jobs 必须是非空数组")
        jobs: dict[Path, PostprocessJob] = {}
        for index, raw_job in enumerate(raw_jobs):
            job = _parse_job(root, raw_job, index)
            key = os.path.normcase(str(job.path))
            if any(os.path.normcase(str(path)) == key for path in jobs):
                raise ApiProblem(
                    400,
                    "DUPLICATE_POSTPROCESS_JOB",
                    "同一 ODB 不能在 jobs 中重复出现",
                    details={"path": str(job.path)},
                )
            jobs[job.path] = job

        raw_groups = payload.get("groups")
        if not isinstance(raw_groups, list) or not raw_groups:
            raise ApiProblem(400, "INVALID_POSTPROCESS_GROUPS", "groups 必须是非空数组")
        groups = tuple(_parse_group(root, raw, jobs, index) for index, raw in enumerate(raw_groups))
        represented = {path for group in groups for path in group.members}
        missing_jobs = [str(path) for path in jobs if path not in represented]
        if missing_jobs:
            raise ApiProblem(
                400,
                "UNGROUPED_POSTPROCESS_JOBS",
                "每个 ODB 必须至少属于一个对比组或独立结果",
                details={"paths": missing_jobs},
            )

        options = PostprocessOptions(
            abaqus_command=abaqus_command,
            root=root,
            parallel_workers=_integer(
                payload, "parallelWorkers", minimum=1, maximum=logical_cpu_count()
            ),
            force_rescan=_flag(payload, "forceRescan"),
            full_timehistory_freebody=_flag(payload, "fullTimehistoryFreebody"),
            rebar_method=rebar_method,
            expected_longitudinal_rebar_count=_integer(
                payload,
                "expectedLongitudinalRebarCount",
                minimum=0,
                maximum=10000,
            ),
            settings=settings,
        )
        return cls(
            client_request_id=_client_request_id(payload),
            plan=PostprocessPlan(jobs=jobs, groups=groups, options=options),
        )


def _parse_job(root: Path, raw: Any, index: int) -> PostprocessJob:
    if not isinstance(raw, Mapping):
        raise ApiProblem(
            400,
            "INVALID_POSTPROCESS_JOB",
            "jobs 中的每一项必须是对象",
            details={"index": index},
        )
    allowed = {
        "path",
        "startStep",
        "endStep",
        "frameMode",
        "manualSequenceExpression",
        "loadDirection",
        "loadSet",
        "pileType",
        "pileDisplaySet",
        "pileConcreteSet",
        "pileSteelSet",
        "soilSet",
        "rebarSet",
        "reinforcementMode",
        "longitudinalMaterial",
        "rebarDiameterMm",
        "prefractureSequenceIndex",
    }
    _validate_fields(raw, allowed, required=allowed - {"reinforcementMode"}, check_schema=False)
    reinforcement_mode = raw.get("reinforcementMode", "required")
    if reinforcement_mode not in ("required", "none"):
        raise ApiProblem(400, "INVALID_REINFORCEMENT_MODE", "reinforcementMode 必须是 required 或 none")
    frame_mode = _text(raw, "frameMode")
    if frame_mode not in FRAME_MODES:
        raise ApiProblem(400, "INVALID_FRAME_MODE", "frameMode 不受支持")
    manual_expression = _text(raw, "manualSequenceExpression", allow_empty=True)
    if frame_mode == "manual" and not manual_expression:
        raise ApiProblem(
            400,
            "MANUAL_FRAME_EXPRESSION_REQUIRED",
            "手动帧模式必须填写帧序号表达式",
            details={"index": index},
        )
    direction = _text(raw, "loadDirection")
    if direction not in LOAD_DIRECTIONS:
        raise ApiProblem(
            400,
            "INVALID_LOAD_DIRECTION",
            "loadDirection 必须是 1、3 或 1+3",
            details={"index": index},
        )
    pile_type = _text(raw, "pileType").upper()
    if pile_type not in PILE_TYPES:
        raise ApiProblem(400, "INVALID_PILE_TYPE", "pileType 必须是 RC 或 CFST")
    return PostprocessJob(
        path=_resolve_odb_path(root, _text(raw, "path"), index),
        start_step=_text(raw, "startStep"),
        end_step=_text(raw, "endStep"),
        frame_mode=frame_mode,
        manual_sequence_expression=manual_expression,
        load_direction=direction,
        load_set=_text(raw, "loadSet"),
        pile_type=pile_type,
        pile_display_set=_text(raw, "pileDisplaySet"),
        pile_concrete_set=_text(raw, "pileConcreteSet"),
        pile_steel_set=_text(raw, "pileSteelSet", allow_empty=True),
        soil_set=_text(raw, "soilSet"),
        reinforcement_mode=reinforcement_mode,
        rebar_set=_text(raw, "rebarSet", allow_empty=reinforcement_mode == "none"),
        longitudinal_material=_text(raw, "longitudinalMaterial", allow_empty=reinforcement_mode == "none"),
        rebar_diameter_mm=_number(
            raw, "rebarDiameterMm", minimum=1.0, maximum=100.0
        ),
        prefracture_sequence_index=_integer(
            raw,
            "prefractureSequenceIndex",
            minimum=-1,
            maximum=1_000_000,
        ),
    )


def _parse_group(
    root: Path,
    raw: Any,
    jobs: Mapping[Path, PostprocessJob],
    index: int,
) -> PostprocessGroup:
    if not isinstance(raw, Mapping):
        raise ApiProblem(400, "INVALID_POSTPROCESS_GROUP", "groups 中的每一项必须是对象")
    allowed = {"id", "name", "members", "standalone", "legendOverrides"}
    _validate_fields(raw, allowed, required=allowed, check_schema=False)
    members = _resolve_paths(root, raw.get("members"))
    unknown = [str(path) for path in members if path not in jobs]
    if unknown:
        raise ApiProblem(
            400,
            "UNKNOWN_GROUP_MEMBERS",
            "对比组包含不在 jobs 中的 ODB",
            details={"paths": unknown},
        )
    overrides = raw.get("legendOverrides")
    if not isinstance(overrides, Mapping):
        raise ApiProblem(400, "INVALID_LEGEND_OVERRIDES", "legendOverrides 必须是对象")
    normalized_overrides: dict[str, dict[str, Any]] = {}
    for field_name, rule in overrides.items():
        if not isinstance(field_name, str) or not field_name.strip() or not isinstance(rule, Mapping):
            raise ApiProblem(400, "INVALID_LEGEND_OVERRIDE", "图例覆盖项格式无效")
        if set(rule) != {"mode", "min", "max"} or rule.get("mode") != "manual":
            raise ApiProblem(400, "INVALID_LEGEND_OVERRIDE", "图例覆盖项必须提供 manual、min 与 max")
        minimum = _number(rule, "min", minimum=-1.0e30, maximum=1.0e30)
        maximum = _number(rule, "max", minimum=-1.0e30, maximum=1.0e30)
        if minimum >= maximum:
            raise ApiProblem(400, "INVALID_LEGEND_OVERRIDE", "图例最小值必须小于最大值")
        normalized_overrides[field_name.strip()] = {
            "mode": "manual",
            "min": minimum,
            "max": maximum,
        }
    standalone = _flag(raw, "standalone")
    if standalone and len(members) != 1:
        raise ApiProblem(400, "INVALID_STANDALONE_GROUP", "独立结果必须且只能包含一个 ODB")
    return PostprocessGroup(
        group_id=_text(raw, "id"),
        name=_text(raw, "name"),
        members=members,
        standalone=standalone,
        legend_overrides=normalized_overrides,
    )


@dataclass
class PostprocessOperation:
    request: PostprocessScanRequest | PostprocessRunRequest | RegionExtractionRequest
    kind: str
    operation_id: str = field(default_factory=lambda: uuid4().hex)
    attempt_id: str = field(default_factory=lambda: uuid4().hex)
    status: str = "queued"
    created_at: str = field(default_factory=utc_now_text)
    updated_at: str = field(default_factory=utc_now_text)
    version: int = 1
    percent: int = 0
    phase: str = "等待执行"
    logs: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    event_cursor: int = 0
    controller: MultiProcessController = field(default_factory=MultiProcessController, repr=False)


class PostprocessOperationManager(OperationShutdownGuard):
    """Own cancellable scan and extraction operations for the native UI."""

    shutdown_kind = 'odb.postprocess'

    def __init__(
        self,
        event_store: EventStore,
        *,
        scan_runner: PostprocessScanRunner | None = None,
        run_runner: PostprocessRunRunner = execute_postprocess_plan,
        settings_provider: Callable[[], tuple[str, str, dict[str, Any]]] | None = None,
    ) -> None:
        self._events = event_store
        self._scan_runner = scan_runner or self._default_scan_runner
        self._run_runner = run_runner
        self._settings_provider = settings_provider or load_postprocess_settings
        self._lock = threading.RLock()
        self._operations: dict[str, PostprocessOperation] = {}
        self._client_requests: dict[str, str] = {}
        self._futures: dict[str, Future[None]] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="odb-postprocess")
        self._closed = False

    def parse_run_request(self, payload: Mapping[str, Any]) -> PostprocessRunRequest:
        command, _release, defaults = self._settings_provider()
        return PostprocessRunRequest.from_payload(
            payload,
            abaqus_command=command,
            defaults=defaults,
        )

    def create_scan(self, request: PostprocessScanRequest) -> dict[str, Any]:
        return self._create(request, SCAN_KIND)

    def create_run(self, request: PostprocessRunRequest) -> dict[str, Any]:
        return self._create(request, RUN_KIND)

    def create_region(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        command, _release, _defaults = self._settings_provider()
        request = RegionExtractionRequest.from_payload(payload, command)
        return self._create(request, REGION_KIND)

    def _create(
        self,
        request: PostprocessScanRequest | PostprocessRunRequest | RegionExtractionRequest,
        kind: str,
    ) -> dict[str, Any]:
        with self._lock:
            if self._closed or self._shutdown_reserved:
                raise ApiProblem(
                    503,
                    "CONTROL_PLANE_SHUTTING_DOWN",
                    "控制面正在关闭，无法创建 ODB 后处理操作",
                    retryable=True,
                )
            existing_id = self._client_requests.get(request.client_request_id)
            if existing_id is not None:
                existing = self._operations[existing_id]
                if existing.request.signature != request.signature:
                    raise ApiProblem(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "clientRequestId 已用于不同的 ODB 后处理请求",
                        details={"operationId": existing.operation_id},
                    )
                return self._snapshot_locked(existing)
            operation = PostprocessOperation(request=request, kind=kind)
            self._operations[operation.operation_id] = operation
            self._client_requests[request.client_request_id] = operation.operation_id
            self._emit_locked(operation, f"{kind}.queued")
            try:
                future = self._executor.submit(self._run_operation, operation.operation_id)
            except RuntimeError as exc:
                self._operations.pop(operation.operation_id, None)
                self._client_requests.pop(request.client_request_id, None)
                raise ApiProblem(
                    503,
                    "OPERATION_SCHEDULER_UNAVAILABLE",
                    "ODB 后处理调度器不可用",
                    retryable=True,
                ) from exc
            self._futures[operation.operation_id] = future
            return self._snapshot_locked(operation)

    def get(self, operation_id: str) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked(self._require_locked(operation_id))

    def list_snapshots(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            return [
                self._snapshot_locked(operation)
                for operation in reversed(tuple(self._operations.values()))
                if not active_only or operation.status not in TERMINAL_STATUSES
            ]

    def cancel(self, operation_id: str) -> dict[str, Any]:
        with self._lock:
            operation = self._require_locked(operation_id)
            if operation.status in TERMINAL_STATUSES:
                return self._snapshot_locked(operation)
            if operation.status != "cancelling":
                self._transition_locked(operation, "cancelling", f"{operation.kind}.cancelling")
            future = self._futures.get(operation.operation_id)
            controller = operation.controller
        controller.cancel()
        cancelled_before_start = future.cancel() if future is not None else False
        with self._lock:
            operation = self._require_locked(operation_id)
            if cancelled_before_start and operation.status == "cancelling":
                self._finish_cancelled_locked(operation)
            return self._snapshot_locked(operation)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            active_ids = [
                operation.operation_id
                for operation in self._operations.values()
                if operation.status not in TERMINAL_STATUSES
            ]
        for operation_id in active_ids:
            self.cancel(operation_id)
        self._executor.shutdown(wait=True, cancel_futures=True)

    def _run_operation(self, operation_id: str) -> None:
        try:
            with self._lock:
                operation = self._require_locked(operation_id)
                if operation.controller.cancel_requested:
                    self._finish_cancelled_locked(operation)
                    return
                self._transition_locked(operation, "starting", f"{operation.kind}.starting")
                self._transition_locked(operation, "running", f"{operation.kind}.running")

            if isinstance(operation.request, RegionExtractionRequest):
                result = execute_region_extraction(
                    operation.request,
                    lambda percent, phase: self._on_progress(operation_id, percent, phase),
                    lambda message: self._on_log(operation_id, message),
                    operation.controller,
                )
            elif isinstance(operation.request, PostprocessScanRequest):
                result = self._scan_runner(
                    operation.request,
                    lambda percent, phase: self._on_progress(operation_id, percent, phase),
                    lambda message: self._on_log(operation_id, message),
                    operation.controller,
                )
            else:
                result = self._run_runner(
                    operation.request.plan,
                    lambda percent, phase: self._on_progress(operation_id, percent, phase),
                    lambda message: self._on_log(operation_id, message),
                    operation.controller,
                )
            with self._lock:
                operation = self._require_locked(operation_id)
                if operation.controller.cancel_requested or operation.status == "cancelling":
                    self._finish_cancelled_locked(operation)
                    return
                if isinstance(operation.request, RegionExtractionRequest):
                    finalize_region_extraction(operation.request, result)
                operation.percent = 100
                operation.phase = (
                    "ODB 结构读取完成" if operation.kind == SCAN_KIND else "ODB 后处理完成"
                )
                operation.result = dict(result)
                operation.error = None
                self._transition_locked(operation, "succeeded", f"{operation.kind}.succeeded")
        except ProcessCancelled:
            with self._lock:
                operation = self._operations.get(operation_id)
                if operation is not None and operation.status not in TERMINAL_STATUSES:
                    self._finish_cancelled_locked(operation)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                operation = self._operations.get(operation_id)
                if operation is None or operation.status in TERMINAL_STATUSES:
                    return
                # Worker failure also cancels the shared controller to stop siblings.
                # Only an explicit operation cancellation should hide that failure.
                if operation.status == "cancelling":
                    self._finish_cancelled_locked(operation)
                    return
                operation.phase = "ODB 结构读取失败" if operation.kind == SCAN_KIND else "ODB 后处理失败"
                operation.error = {
                    "code": "ODB_POSTPROCESS_SCAN_FAILED"
                    if operation.kind == SCAN_KIND
                    else "ODB_POSTPROCESS_FAILED",
                    "message": (str(exc).strip() or exc.__class__.__name__)[:4000],
                    "retryable": True,
                    "details": {"exceptionType": exc.__class__.__name__},
                }
                self._transition_locked(operation, "failed", f"{operation.kind}.failed")

    def _default_scan_runner(
        self,
        request: PostprocessScanRequest,
        progress: Callable[[int, str], None] | None,
        log: Callable[[str], None] | None,
        controller: MultiProcessController,
    ) -> dict[str, Any]:
        command, release, defaults = self._settings_provider()
        effective_defaults = dict(defaults)
        effective_defaults["abaqus_command"] = command
        effective_defaults["local_abaqus_release"] = release
        return analyze_postprocess_inputs(
            abaqus_command=command,
            abaqus_version=abaqus_cache_version(effective_defaults),
            root=request.root,
            paths=request.paths,
            defaults=effective_defaults,
            parallel_workers=request.parallel_workers,
            force_rescan=request.force_rescan,
            progress=progress,
            log=log,
            controller=controller,
        )

    def _on_progress(self, operation_id: str, percent: int, phase: str) -> None:
        with self._lock:
            operation = self._operations.get(operation_id)
            if operation is None or operation.status in TERMINAL_STATUSES:
                return
            normalized = max(operation.percent, min(100, max(0, int(percent))))
            normalized_phase = str(phase).strip()[:1000]
            if normalized == operation.percent and normalized_phase == operation.phase:
                return
            operation.percent = normalized
            operation.phase = normalized_phase
            operation.updated_at = utc_now_text()
            operation.version += 1
            self._emit_locked(operation, f"{operation.kind}.progress")

    def _on_log(self, operation_id: str, message: str) -> None:
        text = str(message).strip()[:4000]
        if not text:
            return
        with self._lock:
            operation = self._operations.get(operation_id)
            if operation is None or operation.status in TERMINAL_STATUSES:
                return
            operation.logs.append(text)
            del operation.logs[:-MAX_OPERATION_LOG_LINES]
            operation.updated_at = utc_now_text()
            operation.version += 1
            self._emit_locked(operation, f"{operation.kind}.log")

    def _require_locked(self, operation_id: str) -> PostprocessOperation:
        operation = self._operations.get(str(operation_id))
        if operation is None:
            raise ApiProblem(
                404,
                "ODB_POSTPROCESS_OPERATION_NOT_FOUND",
                "未找到指定 ODB 后处理操作",
                details={"operationId": str(operation_id)},
            )
        return operation

    def _transition_locked(
        self,
        operation: PostprocessOperation,
        status: str,
        event_kind: str,
    ) -> None:
        if status not in OPERATION_STATUSES:
            raise ValueError(f"Unsupported operation status: {status}")
        operation.status = status
        operation.updated_at = utc_now_text()
        operation.version += 1
        self._emit_locked(operation, event_kind)

    def _finish_cancelled_locked(self, operation: PostprocessOperation) -> None:
        if operation.status in TERMINAL_STATUSES:
            return
        operation.phase = "ODB 后处理操作已取消"
        operation.error = None
        self._transition_locked(operation, "cancelled", f"{operation.kind}.cancelled")

    def _emit_locked(self, operation: PostprocessOperation, event_kind: str) -> None:
        event = self._events.append(
            aggregate_type="operation",
            aggregate_id=operation.operation_id,
            attempt_id=operation.attempt_id,
            kind=event_kind,
            version=operation.version,
            payload={
                "operationId": operation.operation_id,
                "kind": operation.kind,
                "status": operation.status,
                "version": operation.version,
                "progress": {"percent": operation.percent, "phase": operation.phase},
                "error": dict(operation.error) if operation.error is not None else None,
            },
        )
        operation.event_cursor = event.sequence

    @staticmethod
    def _snapshot_locked(operation: PostprocessOperation) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "operationId": operation.operation_id,
            "attemptId": operation.attempt_id,
            "kind": operation.kind,
            "status": operation.status,
            "createdAt": operation.created_at,
            "updatedAt": operation.updated_at,
            "version": operation.version,
            "request": operation.request.summary(),
            "progress": {"percent": operation.percent, "phase": operation.phase},
            "logs": list(operation.logs),
            "result": dict(operation.result) if operation.result is not None else None,
            "error": dict(operation.error) if operation.error is not None else None,
            "eventCursor": operation.event_cursor,
        }


def load_postprocess_settings() -> tuple[str, str, dict[str, Any]]:
    defaults = dict(load_defaults())
    command = os.environ.get(ABAQUS_COMMAND_ENV, "").strip() or str(
        defaults.get("abaqus_command", "")
    ).strip()
    release = os.environ.get(ABAQUS_RELEASE_ENV, "").strip() or str(
        defaults.get("local_abaqus_release", "")
    ).strip()
    if not command:
        raise RuntimeError("未配置 Abaqus 命令")
    if not release:
        raise RuntimeError("未配置 Abaqus 版本")
    defaults["abaqus_command"] = command
    defaults["local_abaqus_release"] = release
    return command, release, defaults


__all__ = [
    "RUN_KIND",
    "SCAN_KIND",
    "PostprocessOperationManager",
    "PostprocessRunRequest",
    "PostprocessRunRunner",
    "PostprocessScanRequest",
    "PostprocessScanRunner",
    "load_postprocess_settings",
]
