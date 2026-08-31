"""Asynchronous result-index operations for the native result browser."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from modules.postprocessor.result_catalog import classify_result, result_section
from modules.postprocessor.result_index import (
    ResultIndexCancelled,
    ResultIndexLocked,
    build_result_index,
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
        allowed = {"schemaVersion", "clientRequestId", "root", "timeDirectory"}
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
        if (
            len(client_request_id) > MAX_CLIENT_REQUEST_ID_LENGTH
            or any(ord(character) < 32 for character in client_request_id)
        ):
            raise ApiProblem(
                400,
                "INVALID_CLIENT_REQUEST_ID",
                "clientRequestId 长度或字符不符合 v1 约束",
            )
        root = payload.get("root")
        time_directory = payload.get("timeDirectory")
        if not isinstance(root, str) or not root.strip():
            raise ApiProblem(400, "INVALID_ROOT", "root 必须是非空路径字符串")
        if not isinstance(time_directory, str) or not time_directory.strip():
            raise ApiProblem(
                400,
                "INVALID_TIME_DIRECTORY",
                "timeDirectory 必须是非空路径字符串",
            )
        return cls(client_request_id, root.strip(), time_directory.strip())


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


class ResultIndexOperationManager:
    """Own one serial queue because each time directory has one atomic index."""

    def __init__(
        self,
        event_store: EventStore,
        *,
        builder: ResultIndexBuilder = build_result_index,
    ) -> None:
        self._events = event_store
        self._builder = builder
        self._lock = threading.RLock()
        self._operations: dict[str, ResultIndexOperation] = {}
        self._client_requests: dict[str, str] = {}
        self._futures: dict[str, Future[None]] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="result-index")
        self._closed = False

    def create(self, request: ResultIndexBuildRequest) -> dict[str, Any]:
        validated = validate_result_index_request(request)
        with self._lock:
            if self._closed:
                raise ApiProblem(
                    503,
                    "CONTROL_PLANE_SHUTTING_DOWN",
                    "控制面正在关闭，无法创建结果索引",
                    retryable=True,
                )
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
            self._operations[operation.operation_id] = operation
            self._client_requests[validated.client_request_id] = operation.operation_id
            self._emit_locked(operation, "result.index.queued")
            try:
                future = self._executor.submit(self._run_operation, operation.operation_id)
            except RuntimeError as exc:
                self._operations.pop(operation.operation_id, None)
                self._client_requests.pop(validated.client_request_id, None)
                raise ApiProblem(
                    503,
                    "OPERATION_SCHEDULER_UNAVAILABLE",
                    "结果索引调度器不可用",
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
            if operation.status != CANCELLING:
                self._transition_locked(operation, CANCELLING, "result.index.cancelling")
            operation.cancel_event.set()
            future = self._futures.get(operation.operation_id)
            cancelled_before_start = future.cancel() if future is not None else False
            if cancelled_before_start:
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

            metadata = self._builder(
                operation.request.time_directory,
                classify_result,
                result_section,
                operation.cancel_event,
                lambda count, current: self._on_progress(operation_id, count, current),
            )
            with self._lock:
                operation = self._require_locked(operation_id)
                if operation.cancel_event.is_set() or operation.status == CANCELLING:
                    self._finish_cancelled_locked(operation)
                    return
                operation.metadata = {str(key): str(value) for key, value in metadata.items()}
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
                if operation.cancel_event.is_set() or operation.status == CANCELLING:
                    self._finish_cancelled_locked(operation)
                    return
                operation.current_item = ""
                operation.error = {
                    "code": "RESULT_INDEX_BUILD_FAILED",
                    "message": (str(exc).strip() or exc.__class__.__name__)[:2000],
                    "retryable": not isinstance(exc, ResultIndexLocked),
                    "details": {"exceptionType": exc.__class__.__name__},
                }
                self._transition_locked(operation, FAILED, "result.index.failed")

    def _on_progress(self, operation_id: str, processed: int, current_item: str) -> None:
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
