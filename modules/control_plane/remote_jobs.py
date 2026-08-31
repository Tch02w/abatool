"""Remote Windows Abaqus job operations over the verified SSH session."""

from __future__ import annotations

import base64
import json
import ntpath
import threading
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from modules.submitter.command import validate_job_name, validate_memory_argument
from modules.submitter.constants import (
    COMPLETE_MARKERS,
    ERROR_MARKERS,
    TERMINATE_MARKERS,
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
from .remote_servers import RemoteServerService

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

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> RemoteJobRequest:
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
            memory=memory,
            datacheck=_flag(payload, "datacheck"),
        )
        if request.input_mode == "upload":
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
    paused: bool = False
    logs: list[str] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    error: dict[str, str] | None = None
    event_cursor: int = 0
    inactive_polls: int = 0
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)


class RemoteJobOperationManager:
    """Create, monitor and cooperatively control remote Abaqus jobs."""

    def __init__(self, events: EventStore, service: RemoteServerService) -> None:
        self._events = events
        self._service = service
        self._lock = threading.RLock()
        self._operations: dict[str, RemoteJobOperation] = {}
        self._client_requests: dict[str, str] = {}
        self._futures: dict[str, Future[None]] = {}
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="remote-job")
        self._stop_event = threading.Event()
        self._closed = False

    def create(self, request: RemoteJobRequest) -> dict[str, Any]:
        with self._lock:
            if self._closed:
                raise ApiProblem(503, "CONTROL_PLANE_SHUTTING_DOWN", "控制面正在关闭")
            existing_id = self._client_requests.get(request.client_request_id)
            if existing_id is not None:
                existing = self._operations[existing_id]
                if existing.request.signature != request.signature:
                    raise ApiProblem(409, "IDEMPOTENCY_CONFLICT", "请求标识已用于不同远端作业")
                return self._snapshot_locked(existing)
            operation = RemoteJobOperation(request)
            self._operations[operation.operation_id] = operation
            self._client_requests[request.client_request_id] = operation.operation_id
            self._emit_locked(operation, "remote.job.queued")
            self._futures[operation.operation_id] = self._executor.submit(
                self._run,
                operation.operation_id,
            )
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

    def control(self, operation_id: str, action: str) -> dict[str, Any]:
        if action not in REMOTE_JOB_CONTROLS:
            raise ApiProblem(400, "INVALID_REMOTE_JOB_CONTROL", "远端作业控制无效")
        with self._lock:
            operation = self._require_locked(operation_id)
            if operation.status in TERMINAL_STATUSES:
                return self._snapshot_locked(operation)
            if action == "cancel":
                operation.cancel_event.set()
                operation.status = CANCELLING
                operation.phase = "正在请求 Abaqus 温和终止"
            else:
                if not operation.work_directory:
                    raise ApiProblem(409, "REMOTE_JOB_NOT_STARTED", "远端作业尚未启动")
                self._execute_control(operation, action)
                operation.paused = action == "pause"
                operation.phase = "已暂停" if operation.paused else "运行中"
            operation.updated_at = utc_now_text()
            operation.version += 1
            self._emit_locked(operation, f"remote.job.{action}")
            return self._snapshot_locked(operation)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._stop_event.set()
        # Closing the desktop app must not terminate remote solver jobs.
        self._executor.shutdown(wait=False, cancel_futures=True)

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
        except (RemoteConnectionError, OSError, ValueError) as exc:
            with self._lock:
                operation.status = FAILED
                operation.phase = "远端作业失败"
                operation.error = {
                    "code": "REMOTE_JOB_FAILED",
                    "message": str(exc).strip() or "远端作业失败",
                }
                self._append_log_locked(operation, operation.error["message"])
                self._touch_locked(operation, "remote.job.failed")

    def _prepare_and_start(self, operation: RemoteJobOperation) -> None:
        profile = self._service.connected_profile()
        if not profile.compute_root:
            raise RemoteConnectionError("服务器配置缺少计算根目录。")
        workspace_payload = self._run_json_script(
            _workspace_script(),
            {"compute_root": profile.compute_root, "job_name": operation.request.job_name},
        )
        work_directory = self._service.validate_remote_path(str(workspace_payload["work_directory"]))
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
                "memory": operation.request.memory,
                "datacheck": operation.request.datacheck,
            },
        )
        with self._lock:
            operation.process_id = int(start_payload.get("process_id") or 0)
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
            )
            return local.name

        validated = self._service.validate_remote_path(source)
        name = ntpath.basename(validated)
        self._run_json_script(
            _copy_remote_file_script(),
            {"source": validated, "destination": ntpath.join(work_directory, name)},
        )
        return name

    def _stage_restart_family(
        self,
        operation: RemoteJobOperation,
        oldjob_path: str,
        work_directory: str,
    ) -> None:
        if operation.request.input_mode == "existing":
            validated = self._service.validate_remote_path(oldjob_path)
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
            )
            with self._lock:
                operation.percent = 30 + round(8 * index / max(1, len(total_files)))
                operation.updated_at = utc_now_text()

    def _monitor(self, operation: RemoteJobOperation) -> None:
        terminate_sent = False
        while True:
            if self._stop_event.is_set():
                return
            if operation.cancel_event.is_set() and not terminate_sent:
                self._execute_control(operation, "cancel")
                terminate_sent = True
            snapshot = self._run_json_script(
                _job_status_script(),
                {
                    "work_directory": operation.work_directory,
                    "job_name": operation.request.job_name,
                    "process_id": operation.process_id,
                },
            )
            sta_tail = str(snapshot.get("sta_tail") or "")
            log_tail = str(snapshot.get("log_tail") or "")
            combined = f"{sta_tail}\n{log_tail}".upper()
            with self._lock:
                self._merge_log_tail_locked(operation, sta_tail)
                active = bool(snapshot.get("process_active") or snapshot.get("lock_exists"))
                if active:
                    operation.inactive_polls = 0
                    operation.percent = min(95, max(operation.percent, 55))
                else:
                    operation.inactive_polls += 1
                operation.phase = "已暂停" if operation.paused else "远端 Abaqus 运行中"
                operation.updated_at = utc_now_text()
                operation.version += 1

                if any(marker in combined for marker in COMPLETE_MARKERS):
                    operation.status = SUCCEEDED
                    operation.phase = "远端作业完成"
                    operation.percent = 100
                    self._touch_locked(operation, "remote.job.succeeded")
                    return
                if any(marker in combined for marker in TERMINATE_MARKERS):
                    operation.status = CANCELLED if operation.cancel_event.is_set() else FAILED
                    operation.phase = "远端作业已终止"
                    operation.percent = min(operation.percent, 99)
                    self._touch_locked(operation, f"remote.job.{operation.status}")
                    return
                if any(marker in combined for marker in ERROR_MARKERS):
                    operation.status = FAILED
                    operation.phase = "远端作业失败"
                    operation.error = {
                        "code": "ABAQUS_REMOTE_ERROR",
                        "message": "Abaqus 远端输出包含失败标记",
                    }
                    self._touch_locked(operation, "remote.job.failed")
                    return
                if operation.request.datacheck and operation.inactive_polls >= 3:
                    operation.status = SUCCEEDED
                    operation.phase = "远端数据检查完成"
                    operation.percent = 100
                    self._touch_locked(operation, "remote.job.succeeded")
                    return
                if operation.cancel_event.is_set() and not active and operation.inactive_polls >= 2:
                    operation.status = CANCELLED
                    operation.phase = "远端作业已取消"
                    self._touch_locked(operation, "remote.job.cancelled")
                    return
                if not active and operation.inactive_polls >= 5:
                    operation.status = FAILED
                    operation.phase = "远端进程结束，未发现成功标记"
                    operation.error = {
                        "code": "REMOTE_JOB_EXIT_UNCONFIRMED",
                        "message": operation.phase,
                    }
                    self._touch_locked(operation, "remote.job.failed")
                    return
            self._stop_event.wait(1)

    def _execute_control(self, operation: RemoteJobOperation, action: str) -> None:
        profile = self._service.connected_profile()
        abaqus_action = {"cancel": "terminate", "pause": "suspend", "resume": "resume"}[action]
        self._run_json_script(
            _control_job_script(),
            {
                "abaqus_command": profile.abaqus_command or "abaqus.bat",
                "work_directory": operation.work_directory,
                "job_name": operation.request.job_name,
                "action": abaqus_action,
            },
        )

    def _run_json_script(self, script: str, config: Mapping[str, Any]) -> dict[str, Any]:
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
        output = self._service.execute_powershell(wrapped, timeout=45)
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
        self._emit_locked(operation, kind)

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
    def _merge_log_tail_locked(cls, operation: RemoteJobOperation, tail: str) -> None:
        for line in tail.splitlines():
            cleaned = line.strip()
            if cleaned and (not operation.logs or operation.logs[-1] != cleaned):
                cls._append_log_locked(operation, cleaned)

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
        }


def _workspace_script() -> str:
    return r"""
$root=[string]$config.compute_root
if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw '服务器计算根目录不存在。' }
$base=Join-Path $root ([string]$config.job_name)
$candidate=$base
$index=2
while (Test-Path -LiteralPath $candidate) { $candidate="${base}_$index"; $index++ }
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
$arguments=@("job=$($config.job_name)","input=$($config.input_name)","ask_delete=OFF")
if ([int]$config.cpus -gt 0) { $arguments += "cpus=$($config.cpus)" }
if ([string]$config.memory) { $arguments += "memory=$($config.memory)" }
if ([string]$config.oldjob_name) { $arguments += "oldjob=$($config.oldjob_name)" }
if ([string]$config.fortran_name) { $arguments += "user=$($config.fortran_name)" }
if ([bool]$config.datacheck) { $arguments += 'datacheck' }
$quoted=$arguments | ForEach-Object { if ($_ -match '\s') { '"'+($_ -replace '"','\"')+'"' } else { $_ } }
$command='call "'+([string]$config.abaqus_command -replace '"','""')+'" '+($quoted -join ' ')
$process=Start-Process -FilePath 'cmd.exe' -ArgumentList @('/d','/s','/c',$command) -WorkingDirectory ([string]$config.work_directory) -WindowStyle Hidden -PassThru
[ordered]@{ process_id=[int]$process.Id } | ConvertTo-Json -Compress
"""


def _job_status_script() -> str:
    return r"""
$job=[string]$config.job_name
$work=[string]$config.work_directory
$sta=Join-Path $work ($job+'.sta')
$log=Join-Path $work ($job+'.log')
$lck=Join-Path $work ($job+'.lck')
$active=[bool](Get-Process -Id ([int]$config.process_id) -ErrorAction SilentlyContinue)
$staTail=if (Test-Path -LiteralPath $sta -PathType Leaf) { (Get-Content -LiteralPath $sta -Tail 80 -ErrorAction SilentlyContinue) -join "`n" } else { '' }
$logTail=if (Test-Path -LiteralPath $log -PathType Leaf) { (Get-Content -LiteralPath $log -Tail 40 -ErrorAction SilentlyContinue) -join "`n" } else { '' }
[ordered]@{ process_active=$active; lock_exists=[bool](Test-Path -LiteralPath $lck); sta_tail=$staTail; log_tail=$logTail } | ConvertTo-Json -Compress
"""


def _control_job_script() -> str:
    return r"""
$argument=([string]$config.action)+' job='+([string]$config.job_name)
$command='call "'+([string]$config.abaqus_command -replace '"','""')+'" '+$argument
$process=Start-Process -FilePath 'cmd.exe' -ArgumentList @('/d','/s','/c',$command) -WorkingDirectory ([string]$config.work_directory) -WindowStyle Hidden -PassThru -Wait
[ordered]@{ exit_code=[int]$process.ExitCode } | ConvertTo-Json -Compress
"""


__all__ = ["RemoteJobOperationManager", "RemoteJobRequest", "preview_remote_job"]
