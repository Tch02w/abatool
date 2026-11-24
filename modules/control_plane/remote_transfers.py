"""Asynchronous, cancellable SFTP transfers for the native frontend."""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from modules.submitter.remote_connection import (
    RemoteConnectionError,
    RemoteTransferCancelled,
)

from .compatibility import (
    CANCELLED,
    CANCELLING,
    FAILED,
    QUEUED,
    RUNNING,
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
from .remote_servers import RemoteServerService
from .shutdown_guard import OperationShutdownGuard

TRANSFER_DIRECTIONS = frozenset({"upload", "download"})


def source_operation_id(payload: Mapping[str, Any]) -> str | None:
    """Only omission selects the unscoped resource browser."""
    if "sourceOperationId" not in payload:
        return None
    value = payload["sourceOperationId"]
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ApiProblem(400, "INVALID_SOURCE_OPERATION_ID", "远端作业标识无效。")
    return value


@dataclass(frozen=True)
class RemoteTransferRequest:
    client_request_id: str
    direction: str
    source: str
    destination: str
    overwrite: bool
    source_operation_id: str | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> RemoteTransferRequest:
        allowed = {
            "schemaVersion",
            "clientRequestId",
            "direction",
            "source",
            "destination",
            "overwrite",
        }
        unknown = sorted(set(payload) - allowed - {"sourceOperationId"})
        missing = sorted(allowed - set(payload))
        if unknown:
            raise ApiProblem(
                400,
                "UNKNOWN_FIELDS",
                "文件传输请求包含未知字段",
                details={"fields": unknown},
            )
        if missing:
            raise ApiProblem(
                400,
                "MISSING_FIELDS",
                "文件传输请求缺少必填字段",
                details={"fields": missing},
            )
        if payload.get("schemaVersion") != SCHEMA_VERSION:
            raise ApiProblem(400, "UNSUPPORTED_SCHEMA_VERSION", "不支持该请求结构版本")

        def text(name: str) -> str:
            value = payload.get(name)
            if not isinstance(value, str) or not value.strip():
                raise ApiProblem(
                    400,
                    "INVALID_TRANSFER_FIELD",
                    f"{name} 必须是非空字符串",
                    details={"field": name},
                )
            return value.strip()

        client_request_id = text("clientRequestId")
        if (
            len(client_request_id) > MAX_CLIENT_REQUEST_ID_LENGTH
            or any(ord(character) < 32 for character in client_request_id)
        ):
            raise ApiProblem(400, "INVALID_CLIENT_REQUEST_ID", "clientRequestId 无效")
        direction = text("direction")
        if direction not in TRANSFER_DIRECTIONS:
            raise ApiProblem(400, "INVALID_TRANSFER_DIRECTION", "文件传输方向无效")
        job_id = source_operation_id(payload)
        if job_id is not None and direction != "download":
            raise ApiProblem(400, "INVALID_TRANSFER_DIRECTION", "作业输出仅支持下载。")
        overwrite = payload.get("overwrite")
        if not isinstance(overwrite, bool):
            raise ApiProblem(400, "INVALID_TRANSFER_FIELD", "overwrite 必须是布尔值")
        return cls(
            client_request_id,
            direction,
            text("source"),
            text("destination"),
            overwrite,
            job_id,
        )

    @property
    def signature(self) -> tuple[str, str, str, bool, str | None]:
        return self.direction, self.source, self.destination, self.overwrite, self.source_operation_id


@dataclass
class RemoteTransferOperation:
    request: RemoteTransferRequest
    expected_profile: dict | None = None
    operation_id: str = field(default_factory=lambda: uuid4().hex)
    status: str = QUEUED
    created_at: str = field(default_factory=utc_now_text)
    updated_at: str = field(default_factory=utc_now_text)
    version: int = 1
    completed_bytes: int = 0
    total_bytes: int = 0
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    event_cursor: int = 0
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)


class RemoteTransferOperationManager(OperationShutdownGuard):
    """Own a serial SFTP queue for the single verified SSH session."""

    shutdown_kind = 'remote.transfer'

    def __init__(self, event_store: EventStore, service: RemoteServerService) -> None:
        self._events = event_store
        self._service = service
        self._lock = threading.RLock()
        self._operations: dict[str, RemoteTransferOperation] = {}
        self._client_requests: dict[str, str] = {}
        self._futures: dict[str, Future[None]] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="remote-transfer")
        self._closed = False

    def create(self, request: RemoteTransferRequest, *, expected_profile: dict | None = None) -> dict[str, Any]:
        with self._lock:
            if self._closed or self._shutdown_reserved:
                raise ApiProblem(
                    503,
                    "CONTROL_PLANE_SHUTTING_DOWN",
                    "控制面正在关闭，无法创建文件传输",
                    retryable=True,
                )
            existing_id = self._client_requests.get(request.client_request_id)
            if existing_id is not None:
                existing = self._operations[existing_id]
                if existing.request.signature != request.signature:
                    raise ApiProblem(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "clientRequestId 已用于不同的文件传输请求",
                    )
                return self._snapshot_locked(existing)
            if request.source_operation_id is not None and not expected_profile:
                raise ApiProblem(409, "REMOTE_JOB_WORKSPACE_UNAVAILABLE", "无法核对原作业的服务器身份。")
            operation = RemoteTransferOperation(request, expected_profile=expected_profile)
            self._operations[operation.operation_id] = operation
            self._client_requests[request.client_request_id] = operation.operation_id
            self._emit_locked(operation, "remote.transfer.queued")
            try:
                self._futures[operation.operation_id] = self._executor.submit(
                    self._run,
                    operation.operation_id,
                )
            except RuntimeError as exc:
                self._operations.pop(operation.operation_id, None)
                self._client_requests.pop(request.client_request_id, None)
                raise ApiProblem(
                    503,
                    "OPERATION_SCHEDULER_UNAVAILABLE",
                    "文件传输调度器不可用",
                    retryable=True,
                ) from exc
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
            operation.cancel_event.set()
            operation.status = CANCELLING
            operation.updated_at = utc_now_text()
            operation.version += 1
            self._emit_locked(operation, "remote.transfer.cancelling")
            return self._snapshot_locked(operation)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for operation in self._operations.values():
                if operation.status not in TERMINAL_STATUSES:
                    operation.cancel_event.set()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(self, operation_id: str) -> None:
        with self._lock:
            operation = self._require_locked(operation_id)
            if operation.cancel_event.is_set():
                self._finish_cancelled_locked(operation)
                return
            operation.status = RUNNING
            operation.updated_at = utc_now_text()
            operation.version += 1
            self._emit_locked(operation, "remote.transfer.running")

        def progress(completed: int, total: int) -> None:
            with self._lock:
                current = self._require_locked(operation_id)
                current.completed_bytes = max(current.completed_bytes, completed)
                current.total_bytes = max(current.total_bytes, total)
                current.updated_at = utc_now_text()
                current.version += 1

        try:
            result = self._service.transfer_file(
                direction=operation.request.direction,
                source=operation.request.source,
                destination=operation.request.destination,
                overwrite=operation.request.overwrite,
                progress=progress,
                cancel_requested=operation.cancel_event.is_set,
                expected_profile=operation.expected_profile,
            )
        except RemoteTransferCancelled:
            with self._lock:
                self._finish_cancelled_locked(operation)
            return
        except (RemoteConnectionError, OSError) as exc:
            with self._lock:
                operation.status = FAILED
                operation.error = {
                    "code": "REMOTE_TRANSFER_FAILED",
                    "message": str(exc).strip() or "文件传输失败",
                }
                operation.updated_at = utc_now_text()
                operation.version += 1
                self._emit_locked(operation, "remote.transfer.failed")
            return

        with self._lock:
            # The service checks cancellation before publishing. Its successful
            # return means the file is committed; a later cancel must not hide it.
            operation.status = SUCCEEDED
            operation.result = result
            operation.completed_bytes = max(
                operation.completed_bytes,
                int(result.get("sizeBytes") or 0),
            )
            operation.total_bytes = max(operation.total_bytes, operation.completed_bytes)
            operation.updated_at = utc_now_text()
            operation.version += 1
            self._emit_locked(operation, "remote.transfer.succeeded")

    def _finish_cancelled_locked(self, operation: RemoteTransferOperation) -> None:
        operation.status = CANCELLED
        operation.error = None
        operation.updated_at = utc_now_text()
        operation.version += 1
        self._emit_locked(operation, "remote.transfer.cancelled")

    def _require_locked(self, operation_id: str) -> RemoteTransferOperation:
        operation = self._operations.get(operation_id)
        if operation is None:
            raise ApiProblem(404, "REMOTE_TRANSFER_NOT_FOUND", "文件传输操作不存在")
        return operation

    def _emit_locked(self, operation: RemoteTransferOperation, kind: str) -> None:
        event = self._events.append(
            aggregate_type="remoteTransfer",
            aggregate_id=operation.operation_id,
            kind=kind,
            version=operation.version,
            payload={
                "status": operation.status,
                "direction": operation.request.direction,
                "completedBytes": operation.completed_bytes,
                "totalBytes": operation.total_bytes,
            },
        )
        operation.event_cursor = event.sequence

    @staticmethod
    def _snapshot_locked(operation: RemoteTransferOperation) -> dict[str, Any]:
        total = operation.total_bytes
        percent = min(100, round(operation.completed_bytes * 100 / total)) if total else 0
        return {
            "schemaVersion": SCHEMA_VERSION,
            "operationId": operation.operation_id,
            "kind": "remote.transfer",
            "status": operation.status,
            "createdAt": operation.created_at,
            "updatedAt": operation.updated_at,
            "version": operation.version,
            "request": {
                "clientRequestId": operation.request.client_request_id,
                "direction": operation.request.direction,
                "source": operation.request.source,
                "destination": operation.request.destination,
                "overwrite": operation.request.overwrite,
                **({"sourceOperationId": operation.request.source_operation_id} if operation.request.source_operation_id else {}),
            },
            "progress": {
                "completedBytes": operation.completed_bytes,
                "totalBytes": total,
                "percent": percent,
            },
            "result": operation.result,
            "error": operation.error,
            "eventCursor": operation.event_cursor,
        }


__all__ = ["RemoteTransferOperationManager", "RemoteTransferRequest"]
