"""Remote Windows Abaqus job operations over the verified SSH session."""

from __future__ import annotations

import base64
import json
import ntpath
import threading
import time
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from modules.submitter.command import validate_job_name, validate_memory_argument
from modules.submitter.execution_options import (
    execution_arguments,
    parse_execution_options,
)
from modules.submitter.local_job_execution import RESTART_DEPENDENCY_EXTENSIONS
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
from .remote_job_journal import server_identity
from .remote_job_monitoring import RemoteCompletionState, new_tail_lines
from .remote_job_recovery import REQUEST_NAMES, RemoteJobRecovery
from .remote_servers import RemoteServerService
from .shutdown_guard import OperationShutdownGuard

REMOTE_INPUT_MODES = frozenset({"upload", "existing"})
REMOTE_JOB_CONTROLS = frozenset({"cancel", "pause", "resume"})
MAX_REMOTE_JOB_LOG_LINES = 250


def preview_remote_job(
    payload: Mapping[str, Any],
    service: RemoteServerService,
) -> dict[str, Any]:
    request = RemoteJobRequest.from_payload(payload)
    profile = service.connected_profile()
    if not profile.compute_root:
        raise ApiProblem(409, "REMOTE_COMPUTE_ROOT_MISSING", "服务器未配置计算根目录")
    if request.input_mode == "existing":
        try:
            service.validate_remote_path(request.input_path)
            if request.oldjob_path:
                service.validate_remote_path(request.oldjob_path)
            if request.fortran_path:
                service.validate_remote_path(request.fortran_path)
        except RemoteConnectionError as exc:
            raise ApiProblem(400, "REMOTE_JOB_PATH_NOT_ALLOWED", str(exc)) from exc
    arguments = [
        f"job={request.job_name}",
        f"input={Path(request.input_path).name if request.input_mode == 'upload' else ntpath.basename(request.input_path)}",
        "ask_delete=OFF",
    ]
    if request.cpus:
        arguments.append(f"cpus={request.cpus}")
    if request.memory:
        arguments.append(f"memory={request.memory}")
    arguments.extend(execution_arguments(request))
    if request.oldjob_path:
        oldjob_name = (
            Path(request.oldjob_path).stem
            if request.input_mode == "upload"
            else ntpath.splitext(ntpath.basename(request.oldjob_path))[0]
        )
        arguments.append(f"oldjob={oldjob_name}")
    if request.fortran_path:
        arguments.append(
            "user="
            + (
                Path(request.fortran_path).name
                if request.input_mode == "upload"
                else ntpath.basename(request.fortran_path)
            )
        )
    if request.datacheck:
        arguments.append("datacheck")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "valid": True,
        "profileName": profile.profile_name,
        "inputMode": request.input_mode,
        "computeRoot": profile.compute_root,
        "command": " ".join([profile.abaqus_command or "abaqus.bat", *arguments]),
    }


def _text(payload: Mapping[str, Any], name: str, *, required: bool = False) -> str:
    value = payload.get(name, "")
    if not isinstance(value, str):
        raise ApiProblem(400, "INVALID_REMOTE_JOB_FIELD", f"{name} 必须是字符串")
    value = value.strip()
    if required and not value:
        raise ApiProblem(400, "MISSING_REMOTE_JOB_FIELD", f"{name} 不能为空")
    return value


def _flag(payload: Mapping[str, Any], name: str, default: bool = False) -> bool:
    value = payload.get(name, default)
    if not isinstance(value, bool):
        raise ApiProblem(400, "INVALID_REMOTE_JOB_FIELD", f"{name} 必须是布尔值")
    return value


@dataclass(frozen=True)
class RemoteJobRequest:
    client_request_id: str
    job_name: str
    input_mode: str
    input_path: str
    oldjob_path: str
    fortran_path: str
    cpus: int
    memory: str
    datacheck: bool
    notify: bool = True
    gpu_count: int | None = None
    explicit_precision: str = "default"
    output_precision: str = "default"

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], *, validate_local_files=True) -> RemoteJobRequest:
        allowed = {
            "schemaVersion",
            "clientRequestId",
            "jobName",
            "inputMode",
            "inputPath",
            "oldjobPath",
            "fortranPath",
            "cpus",
            "memory",
            "datacheck",
            "notify", "gpuCount", "explicitPrecision", "outputPrecision",
        }
        unknown = sorted(set(payload) - allowed)
        missing = sorted(
            {
                "schemaVersion",
                "clientRequestId",
                "jobName",
                "inputMode",
                "inputPath",
                "cpus",
                "memory",
                "datacheck",
            }
            - set(payload)
        )
        if unknown:
            raise ApiProblem(
                400,
                "UNKNOWN_FIELDS",
                "远端作业请求包含未知字段",
                details={"fields": unknown},
            )
        if missing:
            raise ApiProblem(
                400,
                "MISSING_FIELDS",
                "远端作业请求缺少必填字段",
                details={"fields": missing},
            )
        if payload.get("schemaVersion") != SCHEMA_VERSION:
            raise ApiProblem(400, "UNSUPPORTED_SCHEMA_VERSION", "不支持该请求结构版本")
        client_request_id = _text(payload, "clientRequestId", required=True)
        if (
            len(client_request_id) > MAX_CLIENT_REQUEST_ID_LENGTH
            or any(ord(character) < 32 for character in client_request_id)
        ):
            raise ApiProblem(400, "INVALID_CLIENT_REQUEST_ID", "clientRequestId 无效")
        job_name = _text(payload, "jobName", required=True)
        valid_name, name_error = validate_job_name(job_name)
        if not valid_name:
            raise ApiProblem(400, "INVALID_REMOTE_JOB_NAME", name_error)
        input_mode = _text(payload, "inputMode", required=True)
        if input_mode not in REMOTE_INPUT_MODES:
            raise ApiProblem(400, "INVALID_REMOTE_INPUT_MODE", "远端输入模式无效")
        try:
            execution = parse_execution_options(payload)
        except ValueError as exc:
            raise ApiProblem(400, "INVALID_EXECUTION_OPTIONS", str(exc)) from exc
        cpus = payload.get("cpus")
        if isinstance(cpus, bool) or not isinstance(cpus, int) or not 0 <= cpus <= 1024:
            raise ApiProblem(400, "INVALID_REMOTE_JOB_CPUS", "CPU 数必须在 0–1024 之间")
        memory = _text(payload, "memory")
        valid_memory, memory_error = validate_memory_argument(memory)
        if not valid_memory:
            raise ApiProblem(400, "INVALID_REMOTE_JOB_MEMORY", memory_error)
        request = cls(
            client_request_id=client_request_id,
            job_name=job_name,
            input_mode=input_mode,
            input_path=_text(payload, "inputPath", required=True),
            oldjob_path=_text(payload, "oldjobPath"),
            fortran_path=_text(payload, "fortranPath"),
            cpus=cpus,
            gpu_count=execution.gpu_count,
            explicit_precision=execution.explicit_precision,
            output_precision=execution.output_precision,
            memory=memory,
            datacheck=_flag(payload, "datacheck"),
            notify=_flag(payload, "notify", True),
        )
        if request.input_mode == "upload" and validate_local_files:
            for name, value in (
                ("inputPath", request.input_path),
                ("oldjobPath", request.oldjob_path),
                ("fortranPath", request.fortran_path),
            ):
                if value and not Path(value).expanduser().is_file():
                    raise ApiProblem(
                        400,
                        "LOCAL_REMOTE_JOB_FILE_NOT_FOUND",
                        f"{name} 指向的本机文件不存在",
                    )
        return request

    @property
    def signature(self) -> tuple[Any, ...]:
        return (
            self.job_name,
            self.input_mode,
            self.input_path,
            self.oldjob_path,
            self.fortran_path,
            self.cpus,
            self.memory,
            self.datacheck,
            self.notify, self.gpu_count, self.explicit_precision, self.output_precision,
        )


@dataclass
class RemoteJobOperation:
    request: RemoteJobRequest
    operation_id: str = field(default_factory=lambda: uuid4().hex)
    status: str = QUEUED
    created_at: str = field(default_factory=utc_now_text)
    updated_at: str = field(default_factory=utc_now_text)
    version: int = 1
    percent: int = 0
    phase: str = "等待远端执行"
    work_directory: str = ""
    process_id: int = 0
    process_start_ticks: str = ""
    paused: bool = False
    logs: list[str] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    error: dict[str, str] | None = None
    event_cursor: int = 0
    completion: RemoteCompletionState = field(default_factory=RemoteCompletionState)
    log_tails: dict[str, str] = field(default_factory=dict)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    server_identity: dict = field(default_factory=dict)
    launch_state: str = "preparing"
    tracking_state: str = "preparing"
    persistence_warning: str = ""
    last_saved_at: float = 0


class RemoteJobOperationManager(RemoteJobRecovery, OperationShutdownGuard):
    """Create, monitor and cooperatively control remote Abaqus jobs."""

    shutdown_kind = 'remote.job'
    _operation_type = RemoteJobOperation
    _request_type = RemoteJobRequest

    def __init__(self, events: EventStore, service: RemoteServerService, journal_path=None, *, completion_sink=None) -> None:
        self._events = events
        self._service = service
        self._completion_sink = completion_sink
        self._lock = threading.RLock()
        self._operations: dict[str, RemoteJobOperation] = {}
        self._client_requests: dict[str, str] = {}
        self._futures: dict[str, Future[None]] = {}
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="remote-job")
        self._stop_event = threading.Event()
        self._closed = False
        self._init_recovery(journal_path)

    def lookup(self, request: RemoteJobRequest, expected_profile: dict | None) -> dict[str, Any]:
        with self._lock:
            self._check_history()
            if not expected_profile:
                raise ApiProblem(400, "REMOTE_JOB_TARGET_REQUIRED", "核对提交需要原服务器身份。")
            existing = self._replay_locked(request, expected_profile)
            if existing is None:
                raise ApiProblem(404, "REMOTE_JOB_REQUEST_NOT_FOUND", "尚未登记此请求。")
            return existing

    def _submission_receipt_locked(self, operation: RemoteJobOperation) -> dict[str, Any]:
        # A failed flush retains the in-memory fence. Never acknowledge withdrawal until it is durable.
        if operation.tracking_state == "withdrawn" and operation.operation_id in self._pending_saves:
            self._persist_locked(operation, required=True)
        return self._snapshot_locked(operation)

    def _replay_locked(self, request: RemoteJobRequest, expected_profile: dict | None) -> dict[str, Any] | None:
        existing_id = self._client_requests.get(request.client_request_id)
        if existing_id is None:
            return None
        existing = self._operations[existing_id]
        if existing.request.signature != request.signature or (
            expected_profile is not None and existing.server_identity != expected_profile
        ):
            raise ApiProblem(409, "IDEMPOTENCY_CONFLICT", "请求标识已用于不同远端作业或服务器")
        return self._submission_receipt_locked(existing)

    def create(self, request: RemoteJobRequest, *, expected_profile: dict | None = None, withdraw: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._closed or self._shutdown_reserved:
                raise ApiProblem(503, "CONTROL_PLANE_SHUTTING_DOWN", "控制面正在关闭")
            self._check_history()
            existing = self._replay_locked(request, expected_profile)
            if existing is not None:
                return existing
            if withdraw:
                if not expected_profile or not expected_profile["fingerprint"] or not expected_profile["computeRoot"]:
                    raise ApiProblem(400, "REMOTE_JOB_TARGET_REQUIRED", "放弃未登记请求需要原服务器身份。")
                operation = RemoteJobOperation(
                    request, server_identity=expected_profile, status=CANCELLED,
                    tracking_state="withdrawn", phase="已放弃未登记请求，未启动作业",
                )
                self._operations[operation.operation_id] = operation
                self._client_requests[request.client_request_id] = operation.operation_id
                self._persist_locked(operation, required=True)
                self._emit_locked(operation, "remote.job.withdrawn")
                return self._snapshot_locked(operation)
        # Never hold the job lock while waiting for a service lock held by an
        # upload callback. Pin identity again inside every remote service call.
        from dataclasses import asdict
        RemoteJobRequest.from_payload({"schemaVersion": 1, **{REQUEST_NAMES[key]: value for key, value in asdict(request).items()}})
        try:
            identity = server_identity(self._service.connected_profile(expected_profile))
        except RemoteConnectionError as exc:
            if expected_profile is None:
                raise
            raise ApiProblem(409, "REMOTE_CONNECTION_CHANGED", str(exc)) from exc
        with self._lock:
            if self._closed or self._shutdown_reserved or self._storage_error:
                raise ApiProblem(503, "REMOTE_JOB_STORAGE_UNAVAILABLE", "后台关闭中或记录未保存，无法提交远端作业")
            existing = self._replay_locked(request, expected_profile)
            if existing is not None:
                return existing
            operation = RemoteJobOperation(request, server_identity=identity)
            self._operations[operation.operation_id] = operation
            self._client_requests[request.client_request_id] = operation.operation_id
            try:
                self._persist_locked(operation, required=True)
            except ApiProblem:
                operation.status, operation.phase = FAILED, "提交前记录保存失败，未发送远端命令"
                self._persist_locked(operation)
                raise
            self._emit_locked(operation, "remote.job.queued")
            try:
                self._submit_locked(operation)
            except RuntimeError as exc:
                operation.status, operation.phase = FAILED, "远端提交线程未启动，未发送命令"
                operation.error = {"code": "REMOTE_JOB_DISPATCH_FAILED", "message": str(exc)}
                self._touch_locked(operation, "remote.job.dispatch.failed")
            return self._snapshot_locked(operation)

    def get(self, operation_id: str) -> dict[str, Any]:
        with self._lock:
            self._check_history()
            return self._snapshot_locked(self._require_locked(operation_id))

    def file_access_identity(self, operation_id: str, output_path: str | None = None) -> dict:
        with self._lock:
            self._check_history()
            operation = self._require_locked(operation_id)
            if not operation.server_identity or not operation.work_directory:
                raise ApiProblem(409, "REMOTE_JOB_WORKSPACE_UNAVAILABLE", "作业记录缺少原服务器或工作目录。")
            if output_path is not None:
                recorded = {ntpath.normcase(path) for path in operation.files.values()}
                if ntpath.normcase(output_path) not in recorded:
                    raise ApiProblem(400, "REMOTE_JOB_OUTPUT_UNKNOWN", "所选文件未登记在该作业的输出记录中。")
            return dict(operation.server_identity)

    def list_snapshots(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            self._check_history()
            return [
                self._snapshot_locked(operation)
                for operation in reversed(tuple(self._operations.values()))
                if operation.tracking_state != "withdrawn" and (not active_only or operation.status not in TERMINAL_STATUSES)
            ]

    def control(self, operation_id: str, action: str) -> dict[str, Any]:
        if action not in REMOTE_JOB_CONTROLS:
            raise ApiProblem(400, "INVALID_REMOTE_JOB_CONTROL", "远端作业控制无效")
        with self._lock:
            operation = self._require_locked(operation_id)
            if operation.status in TERMINAL_STATUSES:
                return self._snapshot_locked(operation)
            previous_control = (operation.cancel_event.is_set(), operation.status, operation.phase)
            if action == "cancel":
                operation.cancel_event.set()
                operation.status = CANCELLING
                operation.phase = "正在请求 Abaqus 温和终止"
            else:
                if not operation.work_directory or operation.tracking_state != "tracking":
                    raise ApiProblem(409, "REMOTE_JOB_NOT_STARTED", "远端作业尚未启动")
                # The network call below happens outside the manager lock.
            operation.updated_at = utc_now_text()
            operation.version += 1
            try:
                self._persist_locked(operation, required=True)
            except ApiProblem:
                if action == "cancel":
                    if not previous_control[0]:
                        operation.cancel_event.clear()
                    operation.status, operation.phase = previous_control[1:]
                raise
        if action != "cancel":
            self._execute_control(operation, action)
            with self._lock:
                if operation.status not in TERMINAL_STATUSES:
                    operation.paused = action == "pause"
                    operation.phase = "已暂停" if operation.paused else "运行中"
                self._persist_locked(operation)
        with self._lock:
            self._emit_locked(operation, f"remote.job.{action}")
            return self._snapshot_locked(operation)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._stop_event.set()
        # Closing the desktop app must not terminate remote solver jobs.
        self._executor.shutdown(wait=False, cancel_futures=True)
        wait(tuple(self._futures.values()), timeout=2)
        self._maintenance.join(timeout=2)
        self._close_journal_if_idle()

    def _run(self, operation_id: str) -> None:
        with self._lock:
            operation = self._require_locked(operation_id)
            operation.status = STARTING
            operation.phase = "正在准备服务器工作目录"
            operation.percent = 2
            self._touch_locked(operation, "remote.job.starting")
        try:
            self._prepare_and_start(operation)
            self._monitor(operation)
        except RemoteTransferCancelled:
            with self._lock:
                operation.status = CANCELLED
                operation.phase = "远端作业已取消"
                self._touch_locked(operation, "remote.job.cancelled")
        except (RemoteConnectionError, OSError, ValueError, ApiProblem) as exc:
            with self._lock:
                if operation.launch_state != "preparing":
                    self._tracking_lost(operation, exc)
                    return
                operation.status = FAILED
                operation.phase = "远端作业失败"
                operation.error = {
                    "code": "REMOTE_JOB_FAILED",
                    "message": str(exc).strip() or "远端作业失败",
                }
                self._append_log_locked(operation, operation.error["message"])
                self._touch_locked(operation, "remote.job.failed")

    def _tracking_lost(self, operation, error):
        operation.status = CANCELLING if operation.cancel_event.is_set() else RUNNING
        operation.tracking_state = "reconnecting"
        operation.phase = "连接中断或回执未确认，请连接原服务器继续核对；不会重复提交"
        operation.error = {"code": "REMOTE_JOB_TRACKING_INTERRUPTED", "message": str(error)}
        operation.completion.signature = ""
        operation.completion.stable_inactive_polls = 0
        self._touch_locked(operation, "remote.job.tracking.interrupted")

    def _resume(self, operation_id):
        operation = self._operations[operation_id]
        try:
            if operation.launch_state != "started":
                result = self._run_json_script(_recover_launch_script(), {
                    "work_directory": operation.work_directory, "operation_id": operation.operation_id,
                }, expected_profile=operation.server_identity)
                if result.get("state") != "started":
                    with self._lock:
                        operation.tracking_state = "submission_unknown"
                        operation.phase = "启动回执尚未确认，请在原服务器核对；未重复提交"
                        self._persist_locked(operation)
                    self._stop_event.wait(3)
                    return
                with self._lock:
                    self._accept_start(operation, result)
            self._monitor(operation)
        except (RemoteConnectionError, OSError, ValueError) as exc:
            with self._lock:
                self._tracking_lost(operation, exc)

    def _accept_start(self, operation, payload):
        if (payload.get("operation_id") != operation.operation_id or payload.get("state") != "started"
                or int(payload.get("process_id") or 0) <= 0 or not payload.get("process_start_ticks")):
            raise RemoteConnectionError("远端启动回执不完整，未重复提交")
        operation.process_id = int(payload["process_id"])
        operation.process_start_ticks = str(payload["process_start_ticks"])
        operation.launch_state, operation.tracking_state = "started", "tracking"
        operation.status = RUNNING
        operation.error = None
        self._persist_locked(operation)

    def _prepare_and_start(self, operation: RemoteJobOperation) -> None:
        profile = self._service.connected_profile(operation.server_identity)
        if not profile.compute_root:
            raise RemoteConnectionError("服务器配置缺少计算根目录。")
        work_directory = ntpath.join(profile.compute_root, operation.request.job_name + "_" + operation.operation_id)
        workspace_payload = self._run_json_script(
            _workspace_script(),
            {"compute_root": profile.compute_root, "job_name": operation.request.job_name, "operation_id": operation.operation_id},
            expected_profile=operation.server_identity,
        )
        returned = self._service.validate_remote_path(str(workspace_payload["work_directory"]), operation.server_identity)
        if ntpath.normcase(returned) != ntpath.normcase(work_directory):
            raise RemoteConnectionError("远端目录与本次任务身份不一致")
        with self._lock:
            operation.work_directory = work_directory
            operation.files = {
                "sta": ntpath.join(work_directory, f"{operation.request.job_name}.sta"),
                "msg": ntpath.join(work_directory, f"{operation.request.job_name}.msg"),
                "dat": ntpath.join(work_directory, f"{operation.request.job_name}.dat"),
                "log": ntpath.join(work_directory, f"{operation.request.job_name}.log"),
                "odb": ntpath.join(work_directory, f"{operation.request.job_name}.odb"),
            }
            operation.phase = "正在准备远端输入文件"
            operation.percent = 8
            self._touch_locked(operation, "remote.job.workspace.ready")

        input_name = self._stage_file(operation, operation.request.input_path, work_directory, 10, 30)
        oldjob_name = ""
        if operation.request.oldjob_path:
            oldjob_name = Path(operation.request.oldjob_path).stem
            self._stage_restart_family(operation, operation.request.oldjob_path, work_directory)
        fortran_name = ""
        if operation.request.fortran_path:
            fortran_name = self._stage_file(
                operation,
                operation.request.fortran_path,
                work_directory,
                38,
                48,
            )

        with self._lock:
            if operation.cancel_event.is_set() or self._stop_event.is_set():
                raise RemoteTransferCancelled("提交前已取消")
            operation.launch_state = "intent"
            try:
                self._persist_locked(operation, required=True)
            except ApiProblem:
                operation.launch_state = "preparing"
                raise
        start_payload = self._run_json_script(
            _start_job_script(),
            {
                "abaqus_command": profile.abaqus_command or "abaqus.bat",
                "work_directory": work_directory,
                "job_name": operation.request.job_name,
                "input_name": input_name,
                "oldjob_name": oldjob_name,
                "fortran_name": fortran_name,
                "cpus": operation.request.cpus,
                "execution_arguments": execution_arguments(operation.request),
                "memory": operation.request.memory,
                "datacheck": operation.request.datacheck,
                "operation_id": operation.operation_id,
            },
            expected_profile=operation.server_identity,
        )
        with self._lock:
            self._accept_start(operation, start_payload)
            operation.status = RUNNING
            operation.phase = "远端 Abaqus 运行中"
            operation.percent = 50
            self._append_log_locked(
                operation,
                f"远端作业已启动：{work_directory}",
            )
            self._touch_locked(operation, "remote.job.running")

    def _stage_file(
        self,
        operation: RemoteJobOperation,
        source: str,
        work_directory: str,
        start_percent: int,
        end_percent: int,
    ) -> str:
        if operation.request.input_mode == "upload":
            local = Path(source).expanduser().resolve()
            destination = ntpath.join(work_directory, local.name)

            def progress(completed: int, total: int) -> None:
                ratio = completed / total if total else 0
                with self._lock:
                    operation.percent = start_percent + round(
                        (end_percent - start_percent) * ratio
                    )
                    operation.updated_at = utc_now_text()
                    operation.version += 1

            self._service.transfer_file(
                direction="upload",
                source=str(local),
                destination=destination,
                overwrite=True,
                progress=progress,
                cancel_requested=operation.cancel_event.is_set,
                expected_profile=operation.server_identity,
            )
            return local.name

        validated = self._service.validate_remote_path(source, operation.server_identity)
        name = ntpath.basename(validated)
        self._run_json_script(
            _copy_remote_file_script(),
            {"source": validated, "destination": ntpath.join(work_directory, name)},
            expected_profile=operation.server_identity,
        )
        return name

    def _stage_restart_family(
        self,
        operation: RemoteJobOperation,
        oldjob_path: str,
        work_directory: str,
    ) -> None:
        if operation.request.input_mode == "existing":
            validated = self._service.validate_remote_path(oldjob_path, operation.server_identity)
            source_directory = ntpath.dirname(validated)
            source_stem = ntpath.splitext(ntpath.basename(validated))[0]
            self._run_json_script(
                _copy_restart_family_script(),
                {
                    "source_directory": source_directory,
                    "source_stem": source_stem,
                    "work_directory": work_directory,
                    "extensions": list(RESTART_DEPENDENCY_EXTENSIONS),
                },
                expected_profile=operation.server_identity,
            )
            return
        source = Path(oldjob_path).expanduser().resolve()
        total_files = [
            candidate
            for extension in RESTART_DEPENDENCY_EXTENSIONS
            if (candidate := source.with_suffix(extension)).is_file()
        ]
        for index, candidate in enumerate(total_files, start=1):
            destination = ntpath.join(work_directory, candidate.name)
            self._service.transfer_file(
                direction="upload",
                source=str(candidate),
                destination=destination,
                overwrite=True,
                progress=lambda _done, _total: None,
                cancel_requested=operation.cancel_event.is_set,
                expected_profile=operation.server_identity,
            )
            with self._lock:
                operation.percent = 30 + round(8 * index / max(1, len(total_files)))
                operation.updated_at = utc_now_text()

    def _monitor(self, operation: RemoteJobOperation) -> None:
        terminate_sent = False
        while True:
            if self._stop_event.is_set():
                return
            snapshot = self._run_json_script(
                _job_status_script(),
                {
                    "work_directory": operation.work_directory,
                    "job_name": operation.request.job_name,
                    "process_id": operation.process_id,
                    "process_start_ticks": operation.process_start_ticks,
                    "operation_id": operation.operation_id,
                },
                expected_profile=operation.server_identity or None,
            )
            # A lost terminate acknowledgement must not make us resend control
            # forever after the original job has already ended.
            if (operation.cancel_event.is_set() and not terminate_sent and snapshot.get("probe_complete") is True
                    and (snapshot.get("process_active") is True or snapshot.get("lock_exists") is True)):
                self._execute_control(operation, "cancel")
                terminate_sent = True
            with self._lock:
                tracking_state = "tracking" if snapshot.get("probe_complete") is True else "unverified"
                tracking_changed = operation.tracking_state != tracking_state
                operation.tracking_state = tracking_state
                operation.error = None
                evidence_before = (operation.completion.error_seen, operation.completion.termination_seen)
                for source in ("sta", "log", "dat", "msg"):
                    self._merge_log_tail_locked(operation, str(snapshot.get(source + "_tail") or ""), source)
                status, phase, error = operation.completion.observe(snapshot,
                    job_name=operation.request.job_name, datacheck=operation.request.datacheck,
                    cancelling=operation.cancel_event.is_set(), paused=operation.paused)
                operation.status = CANCELLING if operation.cancel_event.is_set() and status == RUNNING else status
                operation.phase = phase
                operation.updated_at = utc_now_text()
                operation.version += 1
                if status in TERMINAL_STATUSES:
                    operation.tracking_state = "finished"
                    operation.percent = 100 if status == SUCCEEDED else min(operation.percent, 99)
                    operation.error = {"code": error, "message": phase} if error else None
                    self._touch_locked(operation, f"remote.job.{status}")
                    return
                operation.percent = min(95, max(operation.percent, 55))
                if (tracking_changed or time.monotonic() - operation.last_saved_at >= 5
                    or evidence_before != (operation.completion.error_seen, operation.completion.termination_seen)):
                    self._persist_locked(operation)
            self._stop_event.wait(1)

    def _execute_control(self, operation: RemoteJobOperation, action: str) -> None:
        profile = self._service.connected_profile(operation.server_identity)
        abaqus_action = {"cancel": "terminate", "pause": "suspend", "resume": "resume"}[action]
        result = self._run_json_script(
            _control_job_script(),
            {
                "abaqus_command": profile.abaqus_command or "abaqus.bat",
                "work_directory": operation.work_directory,
                "job_name": operation.request.job_name,
                "action": abaqus_action,
                "operation_id": operation.operation_id,
            },
            expected_profile=operation.server_identity,
        )
        if result.get("exit_code") != 0:
            raise RemoteConnectionError("远端控制命令未成功，不能据此确认暂停或终止")

    def _run_json_script(self, script: str, config: Mapping[str, Any], *, expected_profile=None) -> dict[str, Any]:
        payload = base64.b64encode(
            json.dumps(config, ensure_ascii=False).encode("utf-8")
        ).decode("ascii")
        wrapped = (
            "$ErrorActionPreference='Stop'\n"
            "$ProgressPreference='SilentlyContinue'\n"
            "$utf8=New-Object System.Text.UTF8Encoding($false)\n"
            "[Console]::OutputEncoding=$utf8\n"
            f"$configJson=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{payload}'))\n"
            "$config=$configJson|ConvertFrom-Json\n"
            + script
        )
        output = self._service.execute_powershell(wrapped, timeout=45, expected_profile=expected_profile)
        try:
            result = json.loads(output.strip())
        except json.JSONDecodeError as exc:
            raise RemoteConnectionError("服务器作业命令未返回有效 JSON。") from exc
        if not isinstance(result, dict):
            raise RemoteConnectionError("服务器作业命令返回格式无效。")
        return result

    def _require_locked(self, operation_id: str) -> RemoteJobOperation:
        operation = self._operations.get(operation_id)
        if operation is None:
            raise ApiProblem(404, "REMOTE_JOB_NOT_FOUND", "远端作业不存在")
        return operation

    def _touch_locked(self, operation: RemoteJobOperation, kind: str) -> None:
        operation.updated_at = utc_now_text()
        operation.version += 1
        self._persist_locked(operation)
        self._emit_locked(operation, kind)
        if self._completion_sink is not None and operation.status in TERMINAL_STATUSES:
            self._completion_sink(operation)

    def _emit_locked(self, operation: RemoteJobOperation, kind: str) -> None:
        event = self._events.append(
            aggregate_type="remoteJob",
            aggregate_id=operation.operation_id,
            kind=kind,
            version=operation.version,
            payload={
                "status": operation.status,
                "phase": operation.phase,
                "percent": operation.percent,
                "jobName": operation.request.job_name,
            },
        )
        operation.event_cursor = event.sequence

    @staticmethod
    def _append_log_locked(operation: RemoteJobOperation, line: str) -> None:
        cleaned = line.strip()
        if not cleaned:
            return
        operation.logs.append(cleaned)
        del operation.logs[:-MAX_REMOTE_JOB_LOG_LINES]

    @classmethod
    def _merge_log_tail_locked(cls, operation: RemoteJobOperation, tail: str, source: str = "sta") -> None:
        if not tail:
            return  # A transient unreadable tail must not erase the overlap baseline.
        for line in new_tail_lines(operation.log_tails.get(source, ""), tail):
            cls._append_log_locked(operation, line)
        operation.log_tails[source] = tail

    @staticmethod
    def _snapshot_locked(operation: RemoteJobOperation) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "operationId": operation.operation_id,
            "kind": "remote.job",
            "status": operation.status,
            "createdAt": operation.created_at,
            "updatedAt": operation.updated_at,
            "version": operation.version,
            "request": {
                "clientRequestId": operation.request.client_request_id,
                "jobName": operation.request.job_name,
                "inputMode": operation.request.input_mode,
                "inputPath": operation.request.input_path,
                "cpus": operation.request.cpus,
                "memory": operation.request.memory,
                "datacheck": operation.request.datacheck,
                "notify": operation.request.notify,
                "gpuCount": operation.request.gpu_count,
                "explicitPrecision": operation.request.explicit_precision,
                "outputPrecision": operation.request.output_precision,
            },
            "phase": operation.phase,
            "percent": operation.percent,
            "workDirectory": operation.work_directory,
            "processId": operation.process_id,
            "paused": operation.paused,
            "logs": list(operation.logs),
            "files": dict(operation.files),
            "error": operation.error,
            "eventCursor": operation.event_cursor,
            "trackingState": operation.tracking_state,
            "persistenceWarning": operation.persistence_warning or None,
        }


def _workspace_script() -> str:
    return r"""
$root=[string]$config.compute_root
if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw '服务器计算根目录不存在。' }
$base=Join-Path $root (([string]$config.job_name)+'_'+([string]$config.operation_id))
$candidate=$base
if (Test-Path -LiteralPath $candidate) { throw '本次任务目录已经存在，请核对原任务，不自动复用。' }
$created=New-Item -ItemType Directory -Path $candidate -ErrorAction Stop
[ordered]@{ work_directory=[string]$created.FullName } | ConvertTo-Json -Compress
"""


def _copy_remote_file_script() -> str:
    return r"""
Copy-Item -LiteralPath ([string]$config.source) -Destination ([string]$config.destination) -Force
[ordered]@{ copied=$true } | ConvertTo-Json -Compress
"""


def _copy_restart_family_script() -> str:
    return r"""
$copied=0
foreach ($extension in @($config.extensions)) {
    $source=Join-Path ([string]$config.source_directory) (([string]$config.source_stem)+[string]$extension)
    if (Test-Path -LiteralPath $source -PathType Leaf) {
        Copy-Item -LiteralPath $source -Destination ([string]$config.work_directory) -Force
        $copied++
    }
}
[ordered]@{ copied=$copied } | ConvertTo-Json -Compress
"""


def _start_job_script() -> str:
    return r"""
$receipt=Join-Path ([string]$config.work_directory) '.abaqus-tools-launch.json'
if (Test-Path -LiteralPath $receipt) {
    $existing=Get-Content -LiteralPath $receipt -Raw -ErrorAction Stop | ConvertFrom-Json
    if ([string]$existing.operation_id -ne [string]$config.operation_id) { throw '启动回执属于另一任务。' }
    $existing | ConvertTo-Json -Compress
    return
}
# Claim before launching. A partial/uncertain claim never permits another start.
$claim=[IO.File]::Open($receipt,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
try {
    $bytes=[Text.Encoding]::UTF8.GetBytes(([ordered]@{operation_id=[string]$config.operation_id;state='starting'}|ConvertTo-Json -Compress))
    $claim.Write($bytes,0,$bytes.Length); $claim.Flush($true)
} finally { $claim.Dispose() }
$arguments=@("job=$($config.job_name)","input=$($config.input_name)","ask_delete=OFF")
if ([int]$config.cpus -gt 0) { $arguments += "cpus=$($config.cpus)" }
if ([string]$config.memory) { $arguments += "memory=$($config.memory)" }
foreach ($argument in $config.execution_arguments) {
    if ([string]$argument -notmatch '^(gpus=([0-9]|[1-9][0-9]{1,3})|double=(off|explicit|both|constraint)|output_precision=(single|full))$') { throw 'Invalid execution option' }
    $arguments += [string]$argument
}
if ([string]$config.oldjob_name) { $arguments += "oldjob=$($config.oldjob_name)" }
if ([string]$config.fortran_name) { $arguments += "user=$($config.fortran_name)" }
if ([bool]$config.datacheck) { $arguments += 'datacheck' }
$quoted=$arguments | ForEach-Object { if ($_ -match '[\s^]') { '"'+($_ -replace '"','\"')+'"' } else { $_ } }
$command='"'+([string]$config.abaqus_command -replace '"','""')+'" '+($quoted -join ' ')
$env:ABAQUS_TOOLS_LITERAL_PERCENT='%'
$command=$command.Replace('%','%ABAQUS_TOOLS_LITERAL_PERCENT%')
$process=Start-Process -FilePath 'cmd.exe' -ArgumentList @('/d','/v:off','/s','/c',('"'+$command+'"')) -WorkingDirectory ([string]$config.work_directory) -WindowStyle Hidden -PassThru
try { $started=$process.StartTime.ToUniversalTime().Ticks.ToString() }
catch { if (-not $process.HasExited) { throw }; $started='exited' }
$result=[ordered]@{ operation_id=[string]$config.operation_id; state='started'; process_id=[int]$process.Id; process_start_ticks=$started }
$temporary=$receipt+'.'+[guid]::NewGuid().ToString('N')+'.tmp'
[IO.File]::WriteAllText($temporary,($result|ConvertTo-Json -Compress),[Text.UTF8Encoding]::new($false))
[IO.File]::Replace($temporary,$receipt,[NullString]::Value)
$result | ConvertTo-Json -Compress
"""


def _recover_launch_script() -> str:
    return r"""
$receipt=Join-Path ([string]$config.work_directory) '.abaqus-tools-launch.json'
if (-not (Test-Path -LiteralPath $receipt -PathType Leaf)) { @{state='unknown'}|ConvertTo-Json -Compress; return }
$existing=Get-Content -LiteralPath $receipt -Raw -ErrorAction Stop | ConvertFrom-Json
if ([string]$existing.operation_id -ne [string]$config.operation_id) { throw '启动回执与原任务不一致。' }
$existing|ConvertTo-Json -Compress
"""


def _job_status_script() -> str:
    return r"""
$job=[string]$config.job_name
$work=[string]$config.work_directory
$complete=$true
if ([string]$config.operation_id) {
    try {
        $receipt=Get-Content -LiteralPath (Join-Path $work '.abaqus-tools-launch.json') -Raw -ErrorAction Stop | ConvertFrom-Json
        if ([string]$receipt.operation_id -ne [string]$config.operation_id -or $receipt.state -ne 'started' -or
            [string]$receipt.process_id -ne [string]$config.process_id -or
            [string]$receipt.process_start_ticks -ne [string]$config.process_start_ticks) { $complete=$false }
    } catch { $complete=$false }
}
$active=$false
$locked=$false
$expected=[string]$config.process_start_ticks
if ($expected -eq 'exited') { }
elseif (-not $expected -or [int]$config.process_id -le 0) { $complete=$false }
else {
    try {
        $current=Get-Process -Id ([int]$config.process_id) -ErrorAction Stop
        $active=$current.StartTime.ToUniversalTime().Ticks.ToString() -eq $expected
    } catch {
        if ($_.FullyQualifiedErrorId -notlike 'NoProcessFoundForGivenId*') { $complete=$false }
    }
}
try { $directory=Get-Item -LiteralPath $work -ErrorAction Stop; if (-not $directory.PSIsContainer) { $complete=$false } }
catch { $complete=$false }
try { $null=Get-Item -LiteralPath (Join-Path $work ($job+'.lck')) -ErrorAction Stop; $locked=$true }
catch { if ($_.CategoryInfo.Category -ne 'ObjectNotFound') { $complete=$false } }
$tails=@{}
$signatures=@()
foreach ($extension in @('sta','log','dat','msg')) {
    $path=Join-Path $work ($job+'.'+$extension)
    $tail=''
    $signature=$extension+':missing'
    try {
        $before=Get-Item -LiteralPath $path -ErrorAction Stop
        $tail=(Get-Content -LiteralPath $path -Tail 80 -ErrorAction Stop) -join "`n"
        $after=Get-Item -LiteralPath $path -ErrorAction Stop
        $signature=$extension+':'+$after.Length+':'+$after.LastWriteTimeUtc.Ticks
        if ($before.Length -ne $after.Length -or $before.LastWriteTimeUtc.Ticks -ne $after.LastWriteTimeUtc.Ticks) { $complete=$false }
    } catch {
        if ($_.CategoryInfo.Category -ne 'ObjectNotFound') { $complete=$false }
        elseif ($null -ne $before) { $complete=$false }
    }
    $before=$null
    $tails[$extension]=$tail
    $signatures+=$signature
}
[ordered]@{ process_active=$active; lock_exists=$locked; probe_complete=$complete;
    output_signature=($signatures -join '|'); sta_tail=$tails.sta; log_tail=$tails.log;
    dat_tail=$tails.dat; msg_tail=$tails.msg } | ConvertTo-Json -Compress
"""


def _control_job_script() -> str:
    return r"""
$receipt=Get-Content -LiteralPath (Join-Path ([string]$config.work_directory) '.abaqus-tools-launch.json') -Raw -ErrorAction Stop | ConvertFrom-Json
if ([string]$receipt.operation_id -ne [string]$config.operation_id) { throw '拒绝控制不属于原任务的目录。' }
$argument=([string]$config.action)+' job="'+([string]$config.job_name)+'"'
$command='"'+([string]$config.abaqus_command -replace '"','""')+'" '+$argument
$env:ABAQUS_TOOLS_LITERAL_PERCENT='%'
$command=$command.Replace('%','%ABAQUS_TOOLS_LITERAL_PERCENT%')
$process=Start-Process -FilePath 'cmd.exe' -ArgumentList @('/d','/v:off','/s','/c',('"'+$command+'"')) -WorkingDirectory ([string]$config.work_directory) -WindowStyle Hidden -PassThru -Wait
[ordered]@{ exit_code=[int]$process.ExitCode } | ConvertTo-Json -Compress
"""


__all__ = ["RemoteJobOperationManager", "RemoteJobRequest", "preview_remote_job"]
