"""Asynchronous protected ODB merge operations for the WinUI control plane."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from modules.postprocessor.process_runner import ProcessCancelled, ProcessController
from modules.submitter.odb_merge_core import (
    MergeConflictPolicy,
    OdbMergeRequest,
    OdbMergeResult,
    build_merge_plan,
)
from modules.submitter.odb_merge_execution import execute_odb_merge

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
    load_compatibility_settings,
)
from .contracts import (
    MAX_CLIENT_REQUEST_ID_LENGTH,
    SCHEMA_VERSION,
    ApiProblem,
    utc_now_text,
)
from .events import EventStore

ODB_MERGE_OPERATION_KIND = "odb.merge"
MAX_OPERATION_LOG_LINES = 200


class OdbMergeRunner(Protocol):
    def __call__(
        self,
        request: OdbMergeRequest,
        progress: Callable[[int, str], None] | None = None,
        log: Callable[[str], None] | None = None,
        controller: ProcessController | None = None,
    ) -> OdbMergeResult: ...


@dataclass(frozen=True)
class OdbMergeOperationRequest:
    client_request_id: str
    original_odb: str
    restart_odb: str
    output_odb: str
    include_history: bool
    compress_result: bool
    copy_original: bool
    conflict_policy: MergeConflictPolicy

    @property
    def signature(self) -> tuple[Any, ...]:
        return (
            os.path.normcase(os.path.abspath(self.original_odb)),
            os.path.normcase(os.path.abspath(self.restart_odb)),
            os.path.normcase(os.path.abspath(self.output_odb)),
            self.include_history,
            self.compress_result,
            self.copy_original,
            self.conflict_policy.value,
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> OdbMergeOperationRequest:
        allowed = {
            "schemaVersion",
            "clientRequestId",
            "originalOdb",
            "restartOdb",
            "outputOdb",
            "includeHistory",
            "compressResult",
            "copyOriginal",
            "conflictPolicy",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ApiProblem(
                400,
                "UNKNOWN_FIELDS",
                "ODB 合并请求包含 v1 协议不支持的字段",
                details={"fields": unknown},
            )
        missing = sorted(allowed - set(payload))
        if missing:
            raise ApiProblem(
                400,
                "MISSING_FIELDS",
                "ODB 合并请求缺少必填字段",
                details={"fields": missing},
            )
        if payload.get("schemaVersion") != SCHEMA_VERSION:
            raise ApiProblem(400, "UNSUPPORTED_SCHEMA_VERSION", "不支持该请求结构版本")

        def text(name: str) -> str:
            value = payload.get(name)
            if not isinstance(value, str) or not value.strip():
                raise ApiProblem(
                    400,
                    "INVALID_ODB_MERGE_FIELD",
                    f"{name} 必须是非空字符串",
                    details={"field": name},
                )
            return value.strip()

        def flag(name: str) -> bool:
            value = payload.get(name)
            if not isinstance(value, bool):
                raise ApiProblem(
                    400,
                    "INVALID_ODB_MERGE_FIELD",
                    f"{name} 必须是布尔值",
                    details={"field": name},
                )
            return value

        client_request_id = text("clientRequestId")
        if len(client_request_id) > MAX_CLIENT_REQUEST_ID_LENGTH or any(
            ord(character) < 32 for character in client_request_id
        ):
            raise ApiProblem(
                400,
                "INVALID_CLIENT_REQUEST_ID",
                "clientRequestId 长度或字符不符合 v1 约束",
            )
        try:
            policy = MergeConflictPolicy(text("conflictPolicy"))
        except ValueError as exc:
            raise ApiProblem(
                400,
                "INVALID_ODB_MERGE_CONFLICT_POLICY",
                "conflictPolicy 必须是 auto_number 或 overwrite",
            ) from exc
        return cls(
            client_request_id=client_request_id,
            original_odb=text("originalOdb"),
            restart_odb=text("restartOdb"),
            output_odb=text("outputOdb"),
            include_history=flag("includeHistory"),
            compress_result=flag("compressResult"),
            copy_original=flag("copyOriginal"),
            conflict_policy=policy,
        )


@dataclass(frozen=True)
class ValidatedOdbMergeRequest:
    client_request_id: str
    signature: tuple[Any, ...]
    request: OdbMergeRequest


@dataclass
class OdbMergeOperation:
    request: ValidatedOdbMergeRequest
    operation_id: str = field(default_factory=lambda: uuid4().hex)
    attempt_id: str = field(default_factory=lambda: uuid4().hex)
    status: str = QUEUED
    created_at: str = field(default_factory=utc_now_text)
    updated_at: str = field(default_factory=utc_now_text)
    version: int = 1
    percent: int = 0
    phase: str = "等待执行"
    logs: list[str] = field(default_factory=list)
    result: dict[str, str] | None = None
    error: dict[str, Any] | None = None
    event_cursor: int = 0
    controller: ProcessController = field(default_factory=ProcessController, repr=False)


class OdbMergeOperationManager:
    """Own serial, cancellable ODB merge operations and their snapshots."""

    def __init__(
        self,
        event_store: EventStore,
        *,
        runner: OdbMergeRunner = execute_odb_merge,
        command_provider: Callable[[], str] | None = None,
    ) -> None:
        self._events = event_store
        self._runner = runner
        self._command_provider = command_provider or (
            lambda: load_compatibility_settings().command
        )
        self._lock = threading.RLock()
        self._operations: dict[str, OdbMergeOperation] = {}
        self._client_requests: dict[str, str] = {}
        self._futures: dict[str, Future[None]] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="odb-merge"
        )
        self._closed = False

    def create(self, request: OdbMergeOperationRequest) -> dict[str, Any]:
        with self._lock:
            if self._closed:
                raise ApiProblem(
                    503,
                    "CONTROL_PLANE_SHUTTING_DOWN",
                    "控制面正在关闭，无法创建 ODB 合并操作",
                    retryable=True,
                )
            existing_id = self._client_requests.get(request.client_request_id)
            if existing_id is not None:
                existing = self._operations[existing_id]
                if existing.request.signature != request.signature:
                    raise ApiProblem(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "clientRequestId 已用于不同的 ODB 合并请求",
                        details={"operationId": existing.operation_id},
                    )
                return self._snapshot_locked(existing)

        try:
            command = self._command_provider().strip()
            if not command:
                raise RuntimeError("未配置 Abaqus 命令")
            plan = build_merge_plan(
                OdbMergeRequest(
                    original_odb=Path(request.original_odb),
                    restart_odb=Path(request.restart_odb),
                    output_odb=Path(request.output_odb),
                    abaqus_command=command,
                    include_history=request.include_history,
                    compress_result=request.compress_result,
                    copy_original=request.copy_original,
                    conflict_policy=request.conflict_policy,
                )
            )
        except (OSError, RuntimeError) as exc:
            raise ApiProblem(
                400,
                "INVALID_ODB_MERGE_REQUEST",
                str(exc).strip() or "ODB 合并请求无效",
            ) from exc

        validated = ValidatedOdbMergeRequest(
            request.client_request_id,
            request.signature,
            plan.request,
        )
        with self._lock:
            # A concurrent repeat may have been admitted while paths were checked.
            if self._closed:
                raise ApiProblem(
                    503,
                    "CONTROL_PLANE_SHUTTING_DOWN",
                    "控制面正在关闭，无法创建 ODB 合并操作",
                    retryable=True,
                )
            existing_id = self._client_requests.get(request.client_request_id)
            if existing_id is not None:
                existing = self._operations[existing_id]
                if existing.request.signature != request.signature:
                    raise ApiProblem(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "clientRequestId 已用于不同的 ODB 合并请求",
                        details={"operationId": existing.operation_id},
                    )
                return self._snapshot_locked(existing)
            operation = OdbMergeOperation(validated)
            self._operations[operation.operation_id] = operation
            self._client_requests[request.client_request_id] = operation.operation_id
            self._emit_locked(operation, "odb.merge.queued")
            try:
                future = self._executor.submit(
                    self._run_operation, operation.operation_id
                )
            except RuntimeError as exc:
                self._operations.pop(operation.operation_id, None)
                self._client_requests.pop(request.client_request_id, None)
                raise ApiProblem(
                    503,
                    "OPERATION_SCHEDULER_UNAVAILABLE",
                    "ODB 合并调度器不可用",
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
                self._transition_locked(operation, CANCELLING, "odb.merge.cancelling")
            future = self._futures.get(operation.operation_id)
            controller = operation.controller

        controller.cancel()
        cancelled_before_start = future.cancel() if future is not None else False
        with self._lock:
            operation = self._require_locked(operation_id)
            if cancelled_before_start and operation.status == CANCELLING:
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
                self._transition_locked(operation, STARTING, "odb.merge.starting")
                self._transition_locked(operation, RUNNING, "odb.merge.running")

            result = self._runner(
                operation.request.request,
                lambda percent, phase: self._on_progress(operation_id, percent, phase),
                lambda message: self._on_log(operation_id, message),
                operation.controller,
            )
            with self._lock:
                operation = self._require_locked(operation_id)
                # A returned result has already passed validation and publication.
                # Late cancellation cannot relabel a committed output as cancelled.
                operation.percent = 100
                operation.phase = "ODB 合并与只读验证完成"
                if result.empty_frame_steps:
                    operation.phase += f"；{len(result.empty_frame_steps)} 个分析步无结果帧，请核对计算状态"
                operation.result = {
                    "outputOdb": str(result.output_odb),
                    "originalBackup": str(result.original_backup),
                    "restartBackup": str(result.restart_backup),
                    "command": result.command,
                }
                if result.validation_report is not None:
                    operation.result["validationReport"] = str(result.validation_report)
                operation.error = None
                self._transition_locked(operation, SUCCEEDED, "odb.merge.succeeded")
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
                if (
                    operation.controller.cancel_requested
                    or operation.status == CANCELLING
                ):
                    self._finish_cancelled_locked(operation)
                    return
                operation.phase = "ODB 合并失败"
                operation.error = {
                    "code": "ODB_MERGE_FAILED",
                    "message": (str(exc).strip() or exc.__class__.__name__)[:2000],
                    "retryable": True,
                    "details": {"exceptionType": exc.__class__.__name__},
                }
                self._transition_locked(operation, FAILED, "odb.merge.failed")

    def _on_progress(self, operation_id: str, percent: int, phase: str) -> None:
        with self._lock:
            operation = self._operations.get(operation_id)
            if operation is None or operation.status in TERMINAL_STATUSES:
                return
            normalized = max(operation.percent, min(100, max(0, int(percent))))
            normalized_phase = str(phase).strip()[:500]
            if normalized == operation.percent and normalized_phase == operation.phase:
                return
            operation.percent = normalized
            operation.phase = normalized_phase
            operation.updated_at = utc_now_text()
            operation.version += 1
            self._emit_locked(operation, "odb.merge.progress")

    def _on_log(self, operation_id: str, message: str) -> None:
        text = str(message).strip()[:2000]
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
            self._emit_locked(operation, "odb.merge.log")

    def _require_locked(self, operation_id: str) -> OdbMergeOperation:
        operation = self._operations.get(str(operation_id))
        if operation is None:
            raise ApiProblem(
                404,
                "ODB_MERGE_OPERATION_NOT_FOUND",
                "未找到指定 ODB 合并操作",
                details={"operationId": str(operation_id)},
            )
        return operation

    def _transition_locked(
        self,
        operation: OdbMergeOperation,
        status: str,
        event_kind: str,
    ) -> None:
        if status not in OPERATION_STATUSES:
            raise ValueError(f"Unsupported operation status: {status}")
        operation.status = status
        operation.updated_at = utc_now_text()
        operation.version += 1
        self._emit_locked(operation, event_kind)

    def _finish_cancelled_locked(self, operation: OdbMergeOperation) -> None:
        if operation.status in TERMINAL_STATUSES:
            return
        operation.phase = "ODB 合并已停止，源 ODB 未被修改"
        operation.error = None
        self._transition_locked(operation, CANCELLED, "odb.merge.cancelled")

    def _emit_locked(self, operation: OdbMergeOperation, event_kind: str) -> None:
        event = self._events.append(
            aggregate_type="operation",
            aggregate_id=operation.operation_id,
            attempt_id=operation.attempt_id,
            kind=event_kind,
            version=operation.version,
            payload={
                "operationId": operation.operation_id,
                "kind": ODB_MERGE_OPERATION_KIND,
                "status": operation.status,
                "version": operation.version,
                "progress": {"percent": operation.percent, "phase": operation.phase},
                "error": dict(operation.error) if operation.error is not None else None,
            },
        )
        operation.event_cursor = event.sequence

    @staticmethod
    def _snapshot_locked(operation: OdbMergeOperation) -> dict[str, Any]:
        request = operation.request.request
        return {
            "schemaVersion": SCHEMA_VERSION,
            "operationId": operation.operation_id,
            "attemptId": operation.attempt_id,
            "kind": ODB_MERGE_OPERATION_KIND,
            "status": operation.status,
            "createdAt": operation.created_at,
            "updatedAt": operation.updated_at,
            "version": operation.version,
            "request": {
                "clientRequestId": operation.request.client_request_id,
                "originalOdb": str(request.original_odb),
                "restartOdb": str(request.restart_odb),
                "outputOdb": str(request.output_odb),
                "includeHistory": request.include_history,
                "compressResult": request.compress_result,
                "copyOriginal": request.copy_original,
                "conflictPolicy": request.conflict_policy.value,
            },
            "progress": {"percent": operation.percent, "phase": operation.phase},
            "logs": list(operation.logs),
            "result": dict(operation.result) if operation.result is not None else None,
            "error": dict(operation.error) if operation.error is not None else None,
            "eventCursor": operation.event_cursor,
        }


__all__ = [
    "ODB_MERGE_OPERATION_KIND",
    "OdbMergeOperationManager",
    "OdbMergeOperationRequest",
    "OdbMergeRunner",
]
