"""Asynchronous, Qt-free ODB compatibility operations for the local API."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from modules.postprocessor.cache import abaqus_cache_version
from modules.postprocessor.config import load_defaults
from modules.postprocessor.paths import scan_cache_dir
from modules.postprocessor.process_runner import ProcessCancelled, ProcessController
from modules.postprocessor.runner import check_odb_compatibility

from .contracts import (
    SCHEMA_VERSION,
    ApiProblem,
    OdbCompatibilityCheckRequest,
    utc_now_text,
)
from .events import EventStore
from .shutdown_guard import OperationShutdownGuard

ABAQUS_COMMAND_ENV = "ABAQUS_TOOLS_ABAQUS_COMMAND"
ABAQUS_RELEASE_ENV = "ABAQUS_TOOLS_ABAQUS_RELEASE"
OPERATION_KIND = "odb.compatibility.check"

QUEUED = "queued"
STARTING = "starting"
RUNNING = "running"
CANCELLING = "cancelling"
SUCCEEDED = "succeeded"
CANCELLED = "cancelled"
FAILED = "failed"

OPERATION_STATUSES = frozenset(
    {QUEUED, STARTING, RUNNING, CANCELLING, SUCCEEDED, CANCELLED, FAILED}
)
TERMINAL_STATUSES = frozenset({SUCCEEDED, CANCELLED, FAILED})
COMPATIBILITY_RESULT_STATUSES = frozenset(
    {"valid", "upgrade_required", "newer_release", "invalid", "missing", "empty"}
)


class CompatibilityRunner(Protocol):
    def __call__(
        self,
        abaqus_command: str,
        paths: Iterable[Path | str],
        cache_dir: Path,
        log: Callable[[str], None] | None = None,
        controller: ProcessController | None = None,
        *,
        force_rescan: bool = False,
        abaqus_version: str = "",
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class AbaqusCompatibilitySettings:
    command: str
    release: str
    cache_version: str


@dataclass(frozen=True)
class ValidatedCompatibilityRequest:
    client_request_id: str
    root: Path
    paths: tuple[Path, ...]
    force_rescan: bool

    @property
    def signature(self) -> tuple[str, tuple[str, ...], bool]:
        return (
            os.path.normcase(str(self.root)),
            tuple(os.path.normcase(str(path)) for path in self.paths),
            self.force_rescan,
        )


@dataclass
class CompatibilityProgress:
    completed: int
    total: int
    current_item: str = ""

    def as_payload(self) -> dict[str, Any]:
        return {
            "completed": self.completed,
            "total": self.total,
            "currentItem": self.current_item,
        }


@dataclass
class CompatibilityOperation:
    request: ValidatedCompatibilityRequest
    operation_id: str = field(default_factory=lambda: uuid4().hex)
    attempt_id: str = field(default_factory=lambda: uuid4().hex)
    status: str = QUEUED
    created_at: str = field(default_factory=utc_now_text)
    updated_at: str = field(default_factory=utc_now_text)
    version: int = 1
    progress: CompatibilityProgress = field(init=False)
    results: tuple[dict[str, Any], ...] = ()
    error: dict[str, Any] | None = None
    event_cursor: int = 0
    controller: ProcessController = field(default_factory=ProcessController, repr=False)

    def __post_init__(self) -> None:
        self.progress = CompatibilityProgress(0, len(self.request.paths))


class CompatibilityResultError(RuntimeError):
    """The existing runner returned a partial or malformed result payload."""


def load_compatibility_settings() -> AbaqusCompatibilitySettings:
    """Load the old defaults while allowing explicit control-plane overrides."""

    defaults = dict(load_defaults())
    command = os.environ.get(ABAQUS_COMMAND_ENV, "").strip() or str(
        defaults.get("abaqus_command", "")
    ).strip()
    release = os.environ.get(ABAQUS_RELEASE_ENV, "").strip() or str(
        defaults.get("local_abaqus_release", "")
    ).strip()
    if not command:
        raise RuntimeError(
            f"未配置 Abaqus 命令；请设置 {ABAQUS_COMMAND_ENV} 或 defaults.json"
        )
    if not release:
        raise RuntimeError(
            f"未配置 Abaqus 版本；请设置 {ABAQUS_RELEASE_ENV} 或 defaults.json"
        )

    effective_defaults = dict(defaults)
    effective_defaults["abaqus_command"] = command
    effective_defaults["local_abaqus_release"] = release
    return AbaqusCompatibilitySettings(
        command=command,
        release=release,
        cache_version=abaqus_cache_version(effective_defaults),
    )


def validate_compatibility_request(
    request: OdbCompatibilityCheckRequest,
) -> ValidatedCompatibilityRequest:
    """Resolve paths once and enforce that every ODB stays below its root."""

    try:
        root = Path(request.root).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ApiProblem(
            400,
            "ROOT_NOT_FOUND",
            "ODB 根目录不存在或无法解析",
            details={"root": request.root, "reason": str(exc)},
        ) from exc
    if not root.is_dir():
        raise ApiProblem(
            400,
            "ROOT_NOT_DIRECTORY",
            "ODB root 必须指向目录",
            details={"root": str(root)},
        )

    resolved_paths: list[Path] = []
    seen: set[str] = set()
    for index, raw_path in enumerate(request.paths):
        try:
            candidate = Path(raw_path).expanduser()
            if not candidate.is_absolute():
                candidate = root / candidate
            path = candidate.resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise ApiProblem(
                400,
                "INVALID_ODB_PATH",
                "ODB 路径无法解析",
                details={"index": index, "path": raw_path, "reason": str(exc)},
            ) from exc

        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ApiProblem(
                400,
                "PATH_OUTSIDE_ROOT",
                "ODB 路径必须位于 root 目录内",
                details={"index": index, "path": str(path), "root": str(root)},
            ) from exc
        if path.suffix.casefold() != ".odb":
            raise ApiProblem(
                400,
                "INVALID_ODB_EXTENSION",
                "兼容性检查只接受 .odb 文件",
                details={"index": index, "path": str(path)},
            )
        if path.exists() and not path.is_file():
            raise ApiProblem(
                400,
                "INVALID_ODB_PATH",
                "ODB 路径必须指向文件",
                details={"index": index, "path": str(path)},
            )

        key = os.path.normcase(str(path))
        if key in seen:
            raise ApiProblem(
                400,
                "DUPLICATE_ODB_PATH",
                "paths 不允许包含重复的 ODB 路径",
                details={"index": index, "path": str(path)},
            )
        seen.add(key)
        resolved_paths.append(path)

    return ValidatedCompatibilityRequest(
        client_request_id=request.client_request_id,
        root=root,
        paths=tuple(resolved_paths),
        force_rescan=request.force_rescan,
    )


class CompatibilityOperationManager(OperationShutdownGuard):
    """Own compatibility operation state, idempotency, workers, and events."""

    shutdown_kind = 'odb.compatibility.check'

    def __init__(
        self,
        event_store: EventStore,
        *,
        runner: CompatibilityRunner = check_odb_compatibility,
        settings_provider: Callable[[], AbaqusCompatibilitySettings] = (
            load_compatibility_settings
        ),
    ) -> None:
        self._events = event_store
        self._runner = runner
        self._settings_provider = settings_provider
        self._lock = threading.RLock()
        self._operations: dict[str, CompatibilityOperation] = {}
        self._client_requests: dict[str, str] = {}
        self._futures: dict[str, Future[None]] = {}
        # The reused runner owns fixed request/report names below each cache root.
        # Serial execution prevents two control-plane operations from overwriting them.
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="odb-compatibility",
        )
        self._closed = False

    def create(self, request: OdbCompatibilityCheckRequest) -> dict[str, Any]:
        validated = validate_compatibility_request(request)
        with self._lock:
            if self._closed or self._shutdown_reserved:
                raise ApiProblem(
                    503,
                    "CONTROL_PLANE_SHUTTING_DOWN",
                    "控制面正在关闭，无法创建新操作",
                    retryable=True,
                )

            existing_id = self._client_requests.get(validated.client_request_id)
            if existing_id is not None:
                existing = self._operations[existing_id]
                if existing.request.signature != validated.signature:
                    raise ApiProblem(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "clientRequestId 已用于不同的兼容性检查请求",
                        details={"operationId": existing.operation_id},
                    )
                return self._snapshot_locked(existing)

            operation = CompatibilityOperation(validated)
            self._operations[operation.operation_id] = operation
            self._client_requests[validated.client_request_id] = operation.operation_id
            self._emit_locked(operation, "odb.compatibility.queued")
            try:
                future = self._executor.submit(
                    self._run_operation,
                    operation.operation_id,
                )
            except RuntimeError as exc:
                self._operations.pop(operation.operation_id, None)
                self._client_requests.pop(validated.client_request_id, None)
                raise ApiProblem(
                    503,
                    "OPERATION_SCHEDULER_UNAVAILABLE",
                    "兼容性检查调度器不可用",
                    retryable=True,
                ) from exc
            self._futures[operation.operation_id] = future
            return self._snapshot_locked(operation)

    def get(self, operation_id: str) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked(self._require_operation_locked(operation_id))

    def list_snapshots(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        """Return newest-first snapshots so a restarted UI can reattach safely."""

        with self._lock:
            operations = reversed(tuple(self._operations.values()))
            return [
                self._snapshot_locked(operation)
                for operation in operations
                if not active_only or operation.status not in TERMINAL_STATUSES
            ]

    def cancel(self, operation_id: str) -> dict[str, Any]:
        with self._lock:
            operation = self._require_operation_locked(operation_id)
            if operation.status in TERMINAL_STATUSES:
                return self._snapshot_locked(operation)
            if operation.status != CANCELLING:
                self._transition_locked(
                    operation,
                    CANCELLING,
                    "odb.compatibility.cancelling",
                )
            future = self._futures.get(operation.operation_id)
            controller = operation.controller

        # taskkill can take time; do not hold the state lock while terminating a tree.
        controller.cancel()
        cancelled_before_start = future.cancel() if future is not None else False

        with self._lock:
            operation = self._require_operation_locked(operation_id)
            if cancelled_before_start and operation.status == CANCELLING:
                self._finish_cancelled_locked(operation)
            return self._snapshot_locked(operation)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            operation_ids = [
                operation.operation_id
                for operation in self._operations.values()
                if operation.status not in TERMINAL_STATUSES
            ]
        for operation_id in operation_ids:
            self.cancel(operation_id)
        self._executor.shutdown(wait=True, cancel_futures=True)

    def _run_operation(self, operation_id: str) -> None:
        try:
            with self._lock:
                operation = self._require_operation_locked(operation_id)
                if operation.status == CANCELLING or operation.controller.cancel_requested:
                    self._finish_cancelled_locked(operation)
                    return
                self._transition_locked(
                    operation,
                    STARTING,
                    "odb.compatibility.starting",
                )

            settings = self._settings_provider()
            cache_dir = scan_cache_dir(operation.request.root)

            with self._lock:
                operation = self._require_operation_locked(operation_id)
                if operation.status == CANCELLING or operation.controller.cancel_requested:
                    self._finish_cancelled_locked(operation)
                    return
                self._transition_locked(
                    operation,
                    RUNNING,
                    "odb.compatibility.running",
                )

            payload = self._runner(
                settings.command,
                operation.request.paths,
                cache_dir,
                lambda message: self._on_runner_log(operation_id, message),
                operation.controller,
                force_rescan=operation.request.force_rescan,
                abaqus_version=settings.cache_version,
            )
            results = self._normalize_results(operation.request.paths, payload)

            with self._lock:
                operation = self._require_operation_locked(operation_id)
                if operation.status == CANCELLING or operation.controller.cancel_requested:
                    self._finish_cancelled_locked(operation)
                    return
                operation.results = results
                operation.error = None
                operation.progress.completed = operation.progress.total
                operation.progress.current_item = ""
                self._transition_locked(
                    operation,
                    SUCCEEDED,
                    "odb.compatibility.succeeded",
                )
        except ProcessCancelled:
            with self._lock:
                operation = self._operations.get(operation_id)
                if operation is not None and operation.status not in TERMINAL_STATUSES:
                    self._finish_cancelled_locked(operation)
        # This thread is the isolation boundary around an external runner. Convert
        # every ordinary runner/config/cache failure into a terminal snapshot.
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                operation = self._operations.get(operation_id)
                if operation is None or operation.status in TERMINAL_STATUSES:
                    return
                if operation.status == CANCELLING or operation.controller.cancel_requested:
                    self._finish_cancelled_locked(operation)
                    return
                message = str(exc).strip() or exc.__class__.__name__
                operation.error = {
                    "code": "COMPATIBILITY_CHECK_FAILED",
                    "message": message[:2000],
                    "retryable": not isinstance(exc, CompatibilityResultError),
                    "details": {"exceptionType": exc.__class__.__name__},
                }
                operation.progress.current_item = ""
                self._transition_locked(
                    operation,
                    FAILED,
                    "odb.compatibility.failed",
                )

    def _on_runner_log(self, operation_id: str, message: str) -> None:
        text = str(message).strip()
        completed: int | None = None
        current_item = ""
        if text.startswith("COMPAT_CACHE_HIT|"):
            parts = text.split("|", 2)
            current_item = parts[1] if len(parts) > 1 else ""
            with self._lock:
                operation = self._operations.get(operation_id)
                if operation is not None:
                    completed = operation.progress.completed + 1
        elif text.startswith("ODB_CHECK|"):
            parts = text.split("|", 4)
            if len(parts) == 5:
                try:
                    completed = int(parts[1])
                except ValueError:
                    completed = None
                current_item = parts[4]

        if completed is None:
            return
        with self._lock:
            operation = self._operations.get(operation_id)
            if operation is None or operation.status in TERMINAL_STATUSES:
                return
            bounded = max(
                operation.progress.completed,
                min(completed, operation.progress.total),
            )
            if (
                bounded == operation.progress.completed
                and current_item == operation.progress.current_item
            ):
                return
            operation.progress.completed = bounded
            operation.progress.current_item = current_item
            operation.updated_at = utc_now_text()
            operation.version += 1
            self._emit_locked(operation, "odb.compatibility.progress")

    def _require_operation_locked(
        self,
        operation_id: str,
    ) -> CompatibilityOperation:
        operation = self._operations.get(str(operation_id))
        if operation is None:
            raise ApiProblem(
                404,
                "OPERATION_NOT_FOUND",
                "未找到指定操作",
                details={"operationId": str(operation_id)},
            )
        return operation

    def _transition_locked(
        self,
        operation: CompatibilityOperation,
        status: str,
        event_kind: str,
    ) -> None:
        if status not in OPERATION_STATUSES:
            raise ValueError(f"Unsupported operation status: {status}")
        operation.status = status
        operation.updated_at = utc_now_text()
        operation.version += 1
        self._emit_locked(operation, event_kind)

    def _finish_cancelled_locked(self, operation: CompatibilityOperation) -> None:
        if operation.status in TERMINAL_STATUSES:
            return
        operation.error = None
        operation.progress.current_item = ""
        self._transition_locked(
            operation,
            CANCELLED,
            "odb.compatibility.cancelled",
        )

    def _emit_locked(
        self,
        operation: CompatibilityOperation,
        event_kind: str,
    ) -> None:
        event = self._events.append(
            aggregate_type="operation",
            aggregate_id=operation.operation_id,
            attempt_id=operation.attempt_id,
            kind=event_kind,
            version=operation.version,
            payload={
                "operationId": operation.operation_id,
                "kind": OPERATION_KIND,
                "status": operation.status,
                "version": operation.version,
                "progress": operation.progress.as_payload(),
                "resultCount": len(operation.results),
                "error": dict(operation.error) if operation.error is not None else None,
            },
        )
        operation.event_cursor = event.sequence

    @staticmethod
    def _snapshot_locked(operation: CompatibilityOperation) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "operationId": operation.operation_id,
            "attemptId": operation.attempt_id,
            "kind": OPERATION_KIND,
            "status": operation.status,
            "createdAt": operation.created_at,
            "updatedAt": operation.updated_at,
            "version": operation.version,
            "progress": operation.progress.as_payload(),
            "request": {
                "clientRequestId": operation.request.client_request_id,
                "root": str(operation.request.root),
                "paths": [str(path) for path in operation.request.paths],
                "forceRescan": operation.request.force_rescan,
            },
            "results": [dict(item) for item in operation.results],
            "error": dict(operation.error) if operation.error is not None else None,
            "eventCursor": operation.event_cursor,
        }

    @staticmethod
    def _normalize_results(
        requested_paths: tuple[Path, ...],
        payload: Mapping[str, Any],
    ) -> tuple[dict[str, Any], ...]:
        if not isinstance(payload, Mapping):
            raise CompatibilityResultError("兼容性 runner 未返回 JSON 对象")
        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            raise CompatibilityResultError("兼容性 runner 缺少 results 数组")

        requested_by_key = {
            os.path.normcase(str(path)): path for path in requested_paths
        }
        normalized_by_key: dict[str, dict[str, Any]] = {}
        for index, raw_item in enumerate(raw_results):
            if not isinstance(raw_item, Mapping):
                raise CompatibilityResultError(
                    f"兼容性结果第 {index} 项不是 JSON 对象"
                )
            raw_path = raw_item.get("path")
            status = raw_item.get("status")
            if not isinstance(raw_path, str) or not raw_path:
                raise CompatibilityResultError(
                    f"兼容性结果第 {index} 项缺少 path"
                )
            if status not in COMPATIBILITY_RESULT_STATUSES:
                raise CompatibilityResultError(
                    f"兼容性结果第 {index} 项状态无效：{status}"
                )
            path = Path(raw_path).expanduser().resolve(strict=False)
            key = os.path.normcase(str(path))
            if key not in requested_by_key or key in normalized_by_key:
                raise CompatibilityResultError(
                    f"兼容性 runner 返回了未请求或重复的路径：{path}"
                )

            size_bytes = raw_item.get("size_bytes", raw_item.get("sizeBytes", 0))
            step_count = raw_item.get("step_count", raw_item.get("stepCount"))
            try:
                normalized_size = max(0, int(size_bytes or 0))
            except (TypeError, ValueError) as exc:
                raise CompatibilityResultError(
                    f"兼容性结果第 {index} 项 sizeBytes 无效"
                ) from exc
            if step_count is None:
                normalized_step_count: int | None = None
            else:
                try:
                    normalized_step_count = max(0, int(step_count))
                except (TypeError, ValueError) as exc:
                    raise CompatibilityResultError(
                        f"兼容性结果第 {index} 项 stepCount 无效"
                    ) from exc

            normalized_by_key[key] = {
                "path": str(requested_by_key[key]),
                "status": str(status),
                "message": str(raw_item.get("message", "")),
                "sizeBytes": normalized_size,
                "stepCount": normalized_step_count,
            }

        missing = [
            str(path)
            for key, path in requested_by_key.items()
            if key not in normalized_by_key
        ]
        if missing:
            raise CompatibilityResultError(
                "兼容性 runner 未返回全部请求路径：" + ", ".join(missing)
            )
        return tuple(
            normalized_by_key[os.path.normcase(str(path))]
            for path in requested_paths
        )


__all__ = [
    "ABAQUS_COMMAND_ENV",
    "ABAQUS_RELEASE_ENV",
    "CANCELLED",
    "CANCELLING",
    "COMPATIBILITY_RESULT_STATUSES",
    "FAILED",
    "OPERATION_KIND",
    "OPERATION_STATUSES",
    "QUEUED",
    "RUNNING",
    "STARTING",
    "SUCCEEDED",
    "TERMINAL_STATUSES",
    "AbaqusCompatibilitySettings",
    "CompatibilityOperationManager",
    "CompatibilityRunner",
    "load_compatibility_settings",
    "validate_compatibility_request",
]
