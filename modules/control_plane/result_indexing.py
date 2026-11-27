"""Asynchronous result-index operations for the native result browser."""

from __future__ import annotations

import os
import threading
from collections import deque
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from modules.postprocessor.result_assets import is_incomplete_output
from modules.postprocessor.result_catalog import classify_result, result_section
from modules.postprocessor.result_index import (
    ResultIndexCancelled,
    ResultIndexLocked,
    build_result_index,
    index_path,
)

from .compatibility import (
    CANCELLED,
    CANCELLING,
    FAILED,
    OPERATION_STATUSES,
    QUEUED,
    RUNNING,
    STARTING,
    SUCCEEDED,
    TERMINAL_STATUSES,
)
from .contracts import (
    MAX_CLIENT_REQUEST_ID_LENGTH,
    SCHEMA_VERSION,
    ApiProblem,
    utc_now_text,
)
from .events import EventStore
from .results import index_scope_directories, is_indexable_group
from .shutdown_guard import OperationShutdownGuard

RESULT_INDEX_OPERATION_KIND = "result.index.build"


class ResultIndexBuilder(Protocol):
    def __call__(
        self,
        time_directory: Path | str,
        classify: Callable[[Path], Any],
        section_for: Callable[[Any], str],
        cancel_event: threading.Event | None = None,
        progress: Callable[[int, str], None] | None = None,
    ) -> dict[str, str]: ...


@dataclass(frozen=True)
class ResultIndexBuildRequest:
    client_request_id: str
    root: str
    time_directory: str
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ResultIndexBuildRequest:
        return cls(*parse_index_paths(payload, "timeDirectory"))


def parse_index_paths(
    payload: Mapping[str, Any], directory_field: str
) -> tuple[str, str, str]:
    allowed = {"schemaVersion", "clientRequestId", "root", directory_field}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ApiProblem(
            400,
            "UNKNOWN_FIELDS",
            "请求包含 v1 协议不支持的字段",
            details={"fields": unknown},
        )
    missing = sorted(allowed - set(payload))
    if missing:
        raise ApiProblem(
            400,
            "MISSING_FIELDS",
            "结果索引请求缺少必填字段",
            details={"fields": missing},
        )
    if payload.get("schemaVersion") != SCHEMA_VERSION:
        raise ApiProblem(
            400,
            "UNSUPPORTED_SCHEMA_VERSION",
            "不支持该请求结构版本",
        )
    client_request_id = payload.get("clientRequestId")
    if not isinstance(client_request_id, str) or not client_request_id.strip():
        raise ApiProblem(
            400,
            "INVALID_CLIENT_REQUEST_ID",
            "clientRequestId 必须是非空字符串",
        )
    client_request_id = client_request_id.strip()
    if len(client_request_id) > MAX_CLIENT_REQUEST_ID_LENGTH or any(
        ord(character) < 32 for character in client_request_id
    ):
        raise ApiProblem(
            400,
            "INVALID_CLIENT_REQUEST_ID",
            "clientRequestId 长度或字符不符合 v1 约束",
        )
    root = payload.get("root")
    directory = payload.get(directory_field)
    if not isinstance(root, str) or not root.strip():
        raise ApiProblem(400, "INVALID_ROOT", "root 必须是非空路径字符串")
    if not isinstance(directory, str) or not directory.strip():
        raise ApiProblem(
            400,
            "INVALID_TIME_DIRECTORY"
            if directory_field == "timeDirectory"
            else "INVALID_SCOPE_DIRECTORY",
            f"{directory_field} 必须是非空路径字符串",
        )
    return client_request_id, root.strip(), directory.strip()


@dataclass(frozen=True)
class ValidatedResultIndexRequest:
    client_request_id: str
    root: Path
    time_directory: Path

    @property
    def signature(self) -> tuple[str, str]:
        return (
            os.path.normcase(str(self.root)),
            os.path.normcase(str(self.time_directory)),
        )


def validate_result_index_request(
    request: ResultIndexBuildRequest,
) -> ValidatedResultIndexRequest:
    try:
        root = Path(request.root).expanduser().resolve(strict=True)
        time_directory = Path(request.time_directory).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ApiProblem(
            400,
            "RESULT_DIRECTORY_NOT_FOUND",
            "结果根目录或时间目录不存在",
            details={"reason": str(exc)},
        ) from exc
    if not root.is_dir() or not time_directory.is_dir():
        raise ApiProblem(
            400,
            "RESULT_DIRECTORY_NOT_DIRECTORY",
            "结果根目录和时间目录都必须指向目录",
        )
    try:
        time_directory.relative_to(root)
    except ValueError as exc:
        raise ApiProblem(
            400,
            "PATH_OUTSIDE_RESULT_ROOT",
            "timeDirectory 必须位于结果根目录内",
            details={"root": str(root), "timeDirectory": str(time_directory)},
        ) from exc
    return ValidatedResultIndexRequest(
        request.client_request_id,
        root,
        time_directory,
    )


@dataclass
class ResultIndexOperation:
    request: ValidatedResultIndexRequest
    batch_id: str = ""
    operation_id: str = field(default_factory=lambda: uuid4().hex)
    attempt_id: str = field(default_factory=lambda: uuid4().hex)
    status: str = QUEUED
    created_at: str = field(default_factory=utc_now_text)
    updated_at: str = field(default_factory=utc_now_text)
    version: int = 1
    processed: int = 0
    current_item: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    error: dict[str, Any] | None = None
    event_cursor: int = 0
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)


@dataclass
class ResultIndexBatch:
    root: Path
    scope: Path
    batch_id: str = field(default_factory=lambda: uuid4().hex)
    members: list[str] = field(default_factory=list)
    skipped: int = 0
    cancel_requested: bool = False


class ResultIndexOperationManager(OperationShutdownGuard):
    """Own one serial queue because each time directory has one atomic index."""

    shutdown_kind = "result.index"

    def __init__(
        self,
        event_store: EventStore,
        *,
        builder: ResultIndexBuilder = build_result_index,
        missing_builder: ResultIndexBuilder | None = None,
    ) -> None:
        self._events = event_store
        self._builder = builder
        self._missing_builder = missing_builder or partial(
            build_result_index, only_if_missing=True
        )
        self._lock = threading.RLock()
        self._operations: dict[str, ResultIndexOperation] = {}
        self._client_requests: dict[str, str] = {}
        self._futures: dict[str, Future[None]] = {}
        self._batches: dict[str, ResultIndexBatch] = {}
        self._batch_requests: dict[str, str] = {}
        self._manual_pending: deque[str] = deque()
        self._batch_pending: deque[str] = deque()
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="result-index"
        )
        self._closed = False

    def create(self, request: ResultIndexBuildRequest) -> dict[str, Any]:
        validated = validate_result_index_request(request)
        with self._lock:
            self._check_admission_locked()
            existing_id = self._client_requests.get(validated.client_request_id)
            if existing_id is not None:
                existing = self._operations[existing_id]
                if existing.request.signature != validated.signature:
                    raise ApiProblem(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "clientRequestId 已用于不同的结果索引请求",
                        details={"operationId": existing.operation_id},
                    )
                return self._snapshot_locked(existing)

            operation = ResultIndexOperation(validated)
            self._client_requests[validated.client_request_id] = operation.operation_id
            self._enqueue_locked(operation)
            self._dispatch_locked()
            return self._snapshot_locked(operation)

    def _check_admission_locked(self) -> None:
        if self._closed or self._shutdown_reserved:
            raise ApiProblem(
                503,
                "CONTROL_PLANE_SHUTTING_DOWN",
                "控制面正在关闭，无法创建结果索引",
                retryable=True,
            )

    def _enqueue_locked(self, operation: ResultIndexOperation) -> None:
        self._operations[operation.operation_id] = operation
        queue = self._batch_pending if operation.batch_id else self._manual_pending
        queue.append(operation.operation_id)
        self._emit_locked(operation, "result.index.queued")

    def _dispatch_locked(self) -> None:
        while (
            not self._closed
            and not self._futures
            and (self._manual_pending or self._batch_pending)
        ):
            operation_id = (self._manual_pending or self._batch_pending).popleft()
            operation = self._operations[operation_id]
            if operation.status != QUEUED:
                continue
            try:
                future = self._executor.submit(self._run_operation, operation_id)
            except RuntimeError as exc:
                operation.error = {
                    "code": "OPERATION_SCHEDULER_UNAVAILABLE",
                    "message": str(exc),
                    "retryable": True,
                }
                self._transition_locked(operation, FAILED, "result.index.failed")
                continue
            self._futures[operation_id] = future
            future.add_done_callback(
                lambda _, completed=operation_id: self._worker_finished(completed)
            )

    def _worker_finished(self, operation_id: str) -> None:
        with self._lock:
            self._futures.pop(operation_id, None)
            self._dispatch_locked()

    def create_batch(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        client_id, raw_root, raw_scope = parse_index_paths(payload, "scopeDirectory")
        root_path, scope_path = Path(raw_root), Path(raw_scope)
        try:
            root, scope = (
                root_path.resolve(strict=True),
                scope_path.resolve(strict=True),
            )
        except (OSError, RuntimeError) as exc:
            raise ApiProblem(400, "RESULT_DIRECTORY_NOT_FOUND", str(exc)) from exc
        allowed_scope = scope == root or (
            scope.parent == root and is_indexable_group(scope)
        )
        if not (
            root.is_dir() and scope.is_dir() and scope_path == scope and allowed_scope
        ):
            raise ApiProblem(
                400, "INVALID_INDEX_BATCH_SCOPE", "请选择结果根目录或该目录下的对比组"
            )
        with self._lock:
            existing = self._existing_batch_locked(client_id, root, scope)
            if existing is not None:
                return existing
        directories = index_scope_directories(root, scope)
        existing_indexes = {path for path in directories if index_path(path).is_file()}
        with self._lock:
            existing = self._existing_batch_locked(client_id, root, scope)
            if existing is not None:
                return existing
            busy = {
                op.request.time_directory
                for op in self._operations.values()
                if op.status not in TERMINAL_STATUSES
            }
            batch = ResultIndexBatch(root, scope)
            self._batch_requests[client_id] = batch.batch_id
            self._batches[batch.batch_id] = batch
            for path in directories:
                if path in existing_indexes or path in busy:
                    batch.skipped += 1
                    continue
                request = ValidatedResultIndexRequest(uuid4().hex, root, path)
                operation = ResultIndexOperation(request, batch_id=batch.batch_id)
                batch.members.append(operation.operation_id)
                self._enqueue_locked(operation)
            self._dispatch_locked()
            return self._batch_snapshot_locked(batch)

    def _existing_batch_locked(
        self, client_id: str, root: Path, scope: Path
    ) -> dict[str, Any] | None:
        self._check_admission_locked()
        batch_id = self._batch_requests.get(client_id)
        if batch_id is None:
            return None
        batch = self._batches[batch_id]
        if (root, scope) != (batch.root, batch.scope):
            raise ApiProblem(
                409, "IDEMPOTENCY_CONFLICT", "clientRequestId 已用于不同的索引范围"
            )
        return self._batch_snapshot_locked(batch)

    def get_batch(self, batch_id: str, *, cancel: bool = False) -> dict[str, Any]:
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                raise ApiProblem(
                    404, "RESULT_INDEX_BATCH_NOT_FOUND", "未找到指定的批量索引任务"
                )
            if cancel:
                batch.cancel_requested = True
                for operation_id in batch.members:
                    self.cancel(operation_id)
            return self._batch_snapshot_locked(batch)

    def _batch_snapshot_locked(self, batch: ResultIndexBatch) -> dict[str, Any]:
        succeeded = cancelled = waiting = 0
        skipped = batch.skipped
        live_ids: list[str] = []
        failures: list[dict[str, str]] = []
        current = ""
        for operation_id in batch.members:
            op = self._operations[operation_id]
            if op.status == SUCCEEDED:
                if op.metadata.get("skipped") == "existing":
                    skipped += 1
                else:
                    succeeded += 1
            elif op.status == CANCELLED:
                cancelled += 1
            elif op.status == FAILED:
                failures.append(
                    {
                        "timeDirectory": str(op.request.time_directory),
                        "message": (op.error or {}).get("message", ""),
                    }
                )
            else:
                live_ids.append(operation_id)
                if op.status == QUEUED:
                    waiting += 1
                else:
                    current = str(op.request.time_directory)
        processed = succeeded + skipped + len(failures) + cancelled
        if live_ids:
            status = RUNNING if current or processed > batch.skipped else QUEUED
            if batch.cancel_requested:
                status = CANCELLING
        else:
            status = CANCELLED if cancelled else SUCCEEDED
            if failures:
                status = FAILED
        return {
            "schemaVersion": SCHEMA_VERSION,
            "batchId": batch.batch_id,
            "root": str(batch.root),
            "scopeDirectory": str(batch.scope),
            "status": status,
            "total": len(batch.members) + batch.skipped,
            "succeeded": succeeded,
            "skipped": skipped,
            "failed": len(failures),
            "cancelled": cancelled,
            "waiting": waiting,
            "active": len(live_ids) - waiting,
            "activeOperationIds": live_ids,
            "currentDirectory": current,
            "processed": processed,
            "failures": failures,
        }

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
            if operation.status != CANCELLING:
                self._transition_locked(
                    operation, CANCELLING, "result.index.cancelling"
                )
            operation.cancel_event.set()
            future = self._futures.get(operation.operation_id)
            if future is None or future.cancel():
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
                if operation.cancel_event.is_set():
                    self._finish_cancelled_locked(operation)
                    return
                self._transition_locked(operation, STARTING, "result.index.starting")
                self._transition_locked(operation, RUNNING, "result.index.running")

            builder = self._builder
            if operation.batch_id:
                directory = operation.request.time_directory
                if directory.resolve(strict=True) != directory or is_incomplete_output(
                    directory
                ):
                    raise ValueError("目录身份或发布状态已改变，请重新读取结果目录")
                builder = self._missing_builder
            metadata = builder(
                operation.request.time_directory,
                classify_result,
                result_section,
                operation.cancel_event,
                lambda count, current: self._on_progress(operation_id, count, current),
            )
            with self._lock:
                operation = self._require_locked(operation_id)
                operation.metadata = {
                    str(key): str(value) for key, value in metadata.items()
                }
                operation.current_item = ""
                operation.error = None
                self._transition_locked(operation, SUCCEEDED, "result.index.succeeded")
        except ResultIndexCancelled:
            with self._lock:
                operation = self._operations.get(operation_id)
                if operation is not None and operation.status not in TERMINAL_STATUSES:
                    self._finish_cancelled_locked(operation)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                operation = self._operations.get(operation_id)
                if operation is None or operation.status in TERMINAL_STATUSES:
                    return
                operation.current_item = ""
                operation.error = {
                    "code": "RESULT_INDEX_BUILD_FAILED",
                    "message": (str(exc).strip() or exc.__class__.__name__)[:2000],
                    "retryable": not isinstance(exc, ResultIndexLocked),
                    "details": {"exceptionType": exc.__class__.__name__},
                }
                self._transition_locked(operation, FAILED, "result.index.failed")

    def _on_progress(
        self, operation_id: str, processed: int, current_item: str
    ) -> None:
        with self._lock:
            operation = self._operations.get(operation_id)
            if operation is None or operation.status in TERMINAL_STATUSES:
                return
            normalized = max(operation.processed, max(0, int(processed)))
            current = str(current_item)
            if normalized == operation.processed and current == operation.current_item:
                return
            operation.processed = normalized
            operation.current_item = current
            operation.updated_at = utc_now_text()
            operation.version += 1
            self._emit_locked(operation, "result.index.progress")

    def _require_locked(self, operation_id: str) -> ResultIndexOperation:
        operation = self._operations.get(str(operation_id))
        if operation is None:
            raise ApiProblem(
                404,
                "RESULT_INDEX_OPERATION_NOT_FOUND",
                "未找到指定结果索引操作",
                details={"operationId": str(operation_id)},
            )
        return operation

    def _transition_locked(
        self,
        operation: ResultIndexOperation,
        status: str,
        event_kind: str,
    ) -> None:
        if status not in OPERATION_STATUSES:
            raise ValueError(f"Unsupported operation status: {status}")
        operation.status = status
        operation.updated_at = utc_now_text()
        operation.version += 1
        self._emit_locked(operation, event_kind)

    def _finish_cancelled_locked(self, operation: ResultIndexOperation) -> None:
        if operation.status in TERMINAL_STATUSES:
            return
        operation.current_item = ""
        operation.error = None
        self._transition_locked(operation, CANCELLED, "result.index.cancelled")

    def _emit_locked(self, operation: ResultIndexOperation, event_kind: str) -> None:
        event = self._events.append(
            aggregate_type="operation",
            aggregate_id=operation.operation_id,
            attempt_id=operation.attempt_id,
            kind=event_kind,
            version=operation.version,
            payload={
                "operationId": operation.operation_id,
                "kind": RESULT_INDEX_OPERATION_KIND,
                "status": operation.status,
                "version": operation.version,
                "progress": {
                    "processed": operation.processed,
                    "currentItem": operation.current_item,
                },
                "error": dict(operation.error) if operation.error is not None else None,
            },
        )
        operation.event_cursor = event.sequence

    @staticmethod
    def _snapshot_locked(operation: ResultIndexOperation) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "operationId": operation.operation_id,
            "attemptId": operation.attempt_id,
            **({"batchId": operation.batch_id} if operation.batch_id else {}),
            "kind": RESULT_INDEX_OPERATION_KIND,
            "status": operation.status,
            "createdAt": operation.created_at,
            "updatedAt": operation.updated_at,
            "version": operation.version,
            "request": {
                "clientRequestId": operation.request.client_request_id,
                "root": str(operation.request.root),
                "timeDirectory": str(operation.request.time_directory),
            },
            "progress": {
                "processed": operation.processed,
                "currentItem": operation.current_item,
            },
            "metadata": dict(operation.metadata),
            "error": dict(operation.error) if operation.error is not None else None,
            "eventCursor": operation.event_cursor,
        }


__all__ = [
    "RESULT_INDEX_OPERATION_KIND",
    "ResultIndexBuildRequest",
    "ResultIndexBuilder",
    "ResultIndexOperationManager",
    "validate_result_index_request",
]
