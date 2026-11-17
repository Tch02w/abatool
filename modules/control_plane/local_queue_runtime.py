"""Asynchronous local queue dispatcher for the WinUI control plane."""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modules.submitter.constants import (
    ACTIVE_STATUSES,
    STATUS_COMPLETED,
    STATUS_DATACHECK_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING_CONFIRM,
    STATUS_PENDING_RUN,
    STATUS_RUNNING,
    STATUS_STARTING,
    STATUS_TERMINATED,
    STATUS_TERMINATING,
    STATUS_UNKNOWN,
    STATUS_WAITING_DEPENDENCY,
    TERMINAL_STATUSES,
)
from modules.submitter.local_job_execution import (
    LocalJobExecutionResult,
    LocalJobProcessController,
    execute_local_job,
)
from modules.submitter.models import QueueItem
from modules.submitter.queue_scheduler import (
    oldjob_name_from_item,
    queue_item_matches_oldjob_path,
)
from modules.submitter.scheduling import ExecutionEventKind

from .contracts import SCHEMA_VERSION, ApiProblem, utc_now_text
from .events import EventStore
from .job_queue_commands import JobQueueService
from .local_scheduling import LocalQueueScheduling, read_scheduling_resources

LOGGER = logging.getLogger(__name__)

LocalJobRunner = Callable[
    [
        QueueItem,
        str,
        LocalJobProcessController,
        Callable[[str, str, int, str], None] | None,
        Callable[[str], None] | None,
    ],
    LocalJobExecutionResult,
]


@dataclass
class _RuntimeRecord:
    item_id: str
    job_name: str
    controller: LocalJobProcessController
    attempt_id: str = ""
    status: str = STATUS_STARTING
    phase: str = "queued"
    message: str = "等待执行线程"
    detail: str = ""
    progress: int = 0
    started_at: str = field(default_factory=utc_now_text)
    finished_at: str = ""
    logs: list[str] = field(default_factory=list)
    paused: bool = False
    thread: threading.Thread | None = field(default=None, repr=False)

    @property
    def active(self) -> bool:
        return not self.finished_at

    def as_payload(self) -> dict[str, Any]:
        return {
            "itemId": self.item_id,
            "attemptId": self.attempt_id,
            "jobName": self.job_name,
            "status": self.status,
            "phase": self.phase,
            "message": self.message,
            "detail": self.detail,
            "progress": self.progress,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at or None,
            "active": self.active,
            "paused": self.paused,
            "logs": list(self.logs),
        }


class LocalQueueRuntimeManager:
    """Dispatch persisted queue items while keeping execution outside the UI."""

    def __init__(
        self,
        queue_service: JobQueueService,
        event_store: EventStore,
        *,
        runner: LocalJobRunner = execute_local_job,
        resource_provider=read_scheduling_resources,
    ) -> None:
        self.queue_service = queue_service
        self.event_store = event_store
        self.runner = runner
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._closing = False
        self._active = False
        self._dispatching = False
        self._stop_requested = False
        self._max_parallel = 1
        self._existing_result_policy = "backup"
        self._started_at = ""
        self._runs: dict[str, _RuntimeRecord] = {}
        self._scheduler_error = ""
        self._scheduling = LocalQueueScheduling(queue_service, resource_provider)
        self._scheduler_closed = False
        self._pending_results = {}
        self._retry_results_after = 0.0
        self._dispatcher = threading.Thread(
            target=self._dispatch_loop,
            name="AbaqusLocalQueueDispatcher",
            daemon=True,
        )
        self._dispatcher.start()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            operations = [
                record.as_payload()
                for record in sorted(
                    self._runs.values(),
                    key=lambda entry: entry.started_at,
                    reverse=True,
                )[:100]
            ]
            return {
                "schemaVersion": SCHEMA_VERSION,
                "active": self._active,
                "stopRequested": self._stop_requested,
                "maxParallel": self._max_parallel,
                "existingResultPolicy": self._existing_result_policy,
                "startedAt": self._started_at or None,
                "schedulerMessage": self._scheduler_error or self._scheduling.notice,
                "activeItemIds": [
                    record.item_id for record in self._runs.values() if record.active
                ],
                "operations": operations,
                "queue": self.queue_service.snapshot(),
            }

    def control(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._closing:
                raise ApiProblem(503, "CONTROL_PLANE_SHUTTING_DOWN", "控制面正在关闭，无法控制队列")
        if payload.get("schemaVersion") != SCHEMA_VERSION:
            raise ApiProblem(
                400,
                "UNSUPPORTED_SCHEMA_VERSION",
                "不支持该本机队列控制结构版本",
            )
        action = payload.get("action")
        if not isinstance(action, str):
            raise ApiProblem(400, "INVALID_LOCAL_QUEUE_ACTION", "action 必须是字符串")
        if action == "start":
            self._start(payload)
        elif action == "stop":
            self._stop(payload)
        elif action == "terminate":
            self._terminate(payload)
        elif action == "suspend":
            self._pause_resume(payload, paused=True)
        elif action == "resume":
            self._pause_resume(payload, paused=False)
        else:
            raise ApiProblem(400, "INVALID_LOCAL_QUEUE_ACTION", "不支持该本机队列控制操作")
        return self.snapshot()

    def _start(self, payload: Mapping[str, Any]) -> None:
        unknown = sorted(
            set(payload)
            - {
                "schemaVersion",
                "action",
                "maxParallel",
                "existingResultPolicy",
            }
        )
        if unknown:
            raise ApiProblem(400, "UNKNOWN_FIELDS", "本机队列启动请求包含未知字段")
        max_parallel = payload.get("maxParallel", 1)
        if isinstance(max_parallel, bool) or not isinstance(max_parallel, int):
            raise ApiProblem(400, "INVALID_MAX_PARALLEL", "maxParallel 必须是整数")
        if not 1 <= max_parallel <= 999:
            raise ApiProblem(400, "INVALID_MAX_PARALLEL", "maxParallel 必须在 1 到 999 之间")
        policy = payload.get("existingResultPolicy", "backup")
        if policy not in {"backup", "overwrite", "cancel"}:
            raise ApiProblem(
                400,
                "INVALID_EXISTING_RESULT_POLICY",
                "同名结果策略必须是 backup、overwrite 或 cancel",
            )
        _candidates, queue_items = self.queue_service.runtime_items()
        missing_cores = [item.job_name for item in queue_items
                         if item.status in {STATUS_PENDING_RUN, STATUS_WAITING_DEPENDENCY}
                         and not item.held and not item.is_external and item.cores <= 0]
        if missing_cores:
            raise ApiProblem(409, "LOCAL_QUEUE_CORE_REQUIRED", "请先为待运行作业设置 Core",
                             details={"jobNames": missing_cores})
        if not any(
            item.status in {STATUS_PENDING_RUN, STATUS_WAITING_DEPENDENCY}
            and not item.held
            for item in queue_items
        ) and not any(record.active for record in self._runs.values()):
            raise ApiProblem(409, "NO_PENDING_LOCAL_JOBS", "正式队列中没有可调度作业")
        with self._lock:
            if self._closing:
                raise ApiProblem(503, "CONTROL_PLANE_SHUTTING_DOWN", "控制面正在关闭，无法启动队列")
            self._max_parallel = max_parallel
            self._existing_result_policy = str(policy)
            self._active = True
            self._stop_requested = False
            self._started_at = self._started_at or utc_now_text()
            self._scheduler_error = ""
        self.event_store.append(
            aggregate_type="localQueue",
            aggregate_id="local",
            kind="local.queue.started",
            version=1,
            payload={"maxParallel": max_parallel, "existingResultPolicy": policy},
        )
        self._wake.set()

    def _stop(self, payload: Mapping[str, Any]) -> None:
        unknown = sorted(set(payload) - {"schemaVersion", "action"})
        if unknown:
            raise ApiProblem(400, "UNKNOWN_FIELDS", "本机队列停止请求包含未知字段")
        with self._lock:
            self._active = False
            self._stop_requested = True
        self.event_store.append(
            aggregate_type="localQueue",
            aggregate_id="local",
            kind="local.queue.stopped",
            version=1,
            payload={},
        )
        self._wake.set()

    def _terminate(self, payload: Mapping[str, Any]) -> None:
        unknown = sorted(set(payload) - {"schemaVersion", "action", "itemIds"})
        if unknown:
            raise ApiProblem(400, "UNKNOWN_FIELDS", "本机作业终止请求包含未知字段")
        item_ids = payload.get("itemIds")
        if not isinstance(item_ids, list) or any(
            not isinstance(item_id, str) for item_id in item_ids
        ):
            raise ApiProblem(400, "INVALID_ITEM_IDS", "itemIds 必须是字符串数组")
        requested = {item_id.strip() for item_id in item_ids if item_id.strip()}
        if not requested:
            raise ApiProblem(400, "EMPTY_ITEM_IDS", "请选择要终止的运行中作业")
        with self._lock:
            records = [
                record
                for item_id, record in self._runs.items()
                if item_id in requested and record.active
            ]
        if not records:
            raise ApiProblem(409, "NO_ACTIVE_LOCAL_JOBS", "所选作业当前未在本机运行")
        for record in records:
            record.controller.cancel()
            with self._lock:
                record.status = STATUS_TERMINATING
                record.phase = "terminating"
                record.message = "已发送终止请求"
            self._update_queue_item(
                record.item_id,
                status=STATUS_TERMINATING,
                message="已发送终止请求",
            )
        self._wake.set()

    def _pause_resume(self, payload: Mapping[str, Any], *, paused: bool) -> None:
        unknown = sorted(set(payload) - {"schemaVersion", "action", "itemIds"})
        if unknown:
            raise ApiProblem(400, "UNKNOWN_FIELDS", "本机作业暂停请求包含未知字段")
        raw_ids = payload.get("itemIds")
        if not isinstance(raw_ids, list) or any(
            not isinstance(item_id, str) for item_id in raw_ids
        ):
            raise ApiProblem(400, "INVALID_ITEM_IDS", "itemIds 必须是字符串数组")
        item_ids = {item_id.strip() for item_id in raw_ids if item_id.strip()}
        _candidates, queue_items = self.queue_service.runtime_items()
        items = {item.item_id: item for item in queue_items if item.item_id in item_ids}
        with self._lock:
            records = [
                record
                for item_id, record in self._runs.items()
                if item_id in item_ids and record.active
            ]
        if not records:
            raise ApiProblem(409, "NO_ACTIVE_LOCAL_JOBS", "所选作业当前未在本机运行")
        action = "suspend" if paused else "resume"
        for record in records:
            item = items.get(record.item_id)
            if item is None:
                continue
            if item.calculation_root_dir:
                work_dir = Path(item.calculation_root_dir) / item.job_name
            elif item.effective_work_dir:
                work_dir = Path(item.effective_work_dir)
            else:
                work_dir = Path(item.inp_path).parent
            command = f'{item.abaqus_command or "abaqus"} {action} job={item.job_name}'
            creationflags = 0
            if os.name == "nt":
                creationflags = (
                    subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                )
            subprocess.Popen(
                command,
                cwd=str(work_dir),
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            with self._lock:
                record.paused = paused
                record.phase = "suspended" if paused else "solving"
                record.message = "作业已暂停" if paused else "作业已恢复"
            self._update_queue_item(
                record.item_id,
                status=STATUS_RUNNING,
                message=record.message,
            )

    def _dispatch_loop(self) -> None:
        while True:
            self._wake.wait(timeout=0.5)
            self._wake.clear()
            with self._lock:
                retry_results = []
                if not self._closing and self._pending_results and time.monotonic() >= self._retry_results_after:
                    self._retry_results_after = time.monotonic() + 5
                    retry_results = list(self._pending_results.values())
            for item, record, result in retry_results:
                self._store_result(item, record, result)
            with self._lock:
                if self._closing:
                    return
                active = self._active
                available = self._max_parallel - sum(
                    record.active for record in self._runs.values()
                )
                self._dispatching = active and available > 0
            if not active or available <= 0:
                continue

            try:
                ready_ids = self._refresh_dependencies()
                with self._lock:
                    if self._closing or not self._active:
                        continue
                    finishing = {record.item_id for record in self._runs.values()
                                 if record.active or (record.thread is not None and record.thread.is_alive())}
                    allocations = self._scheduling.reserve(ready_ids, self._max_parallel, finishing)
                    unlaunched = list(allocations)
                    try:
                        for item_id, attempt_id in allocations:
                            if self._launch(item_id, attempt_id):
                                unlaunched.remove((item_id, attempt_id))
                    finally:
                        if unlaunched:
                            self._scheduling.release_unlaunched(unlaunched)

                with self._lock:
                    has_active = any(record.active for record in self._runs.values())
                _candidates, queue_items = self.queue_service.runtime_items()
                has_pending = any(
                    item.status in {STATUS_PENDING_RUN, STATUS_WAITING_DEPENDENCY}
                    and not item.held
                    for item in queue_items
                )
                if not has_active and not has_pending:
                    with self._lock:
                        self._active = False
            except Exception as exc:
                LOGGER.exception("Local scheduling paused after an error")
                with self._lock:
                    self._active = False
                    self._scheduler_error = f"调度已暂停：{exc}。请处理后重新开始队列。"
            finally:
                with self._lock:
                    self._dispatching = False

    def _refresh_dependencies(self) -> list[str]:
        ready_ids: list[str] = []

        def mutation(_candidates: list[QueueItem], queue_items: list[QueueItem]) -> None:
            for item in queue_items:
                if item.status not in {STATUS_PENDING_RUN, STATUS_WAITING_DEPENDENCY}:
                    continue
                if item.held:
                    continue
                if item.run_mode != "restart":
                    item.status = STATUS_PENDING_RUN
                    if not item.pending_reason:
                        item.message = "等待本机调度"
                    ready_ids.append(item.item_id)
                    continue
                dependencies = [candidate for candidate in queue_items
                                if candidate.item_id != item.item_id
                                and candidate.job_name.casefold() == oldjob_name_from_item(item).casefold()]
                if item.oldjob_path:
                    dependencies = [candidate for candidate in dependencies if queue_item_matches_oldjob_path(item, candidate)]
                if len(dependencies) > 1:
                    item.status = STATUS_WAITING_DEPENDENCY
                    item.message = "存在同名 Restart 前置作业，请指定唯一的前置 ODB 路径"
                    continue
                dependency = dependencies[0] if dependencies else None
                if dependency is None and item.oldjob_path and Path(item.oldjob_path).is_file():
                    if Path(item.oldjob_path).with_suffix(".lck").exists():
                        item.status = STATUS_WAITING_DEPENDENCY
                        item.message = "前置 ODB 仍有锁文件，请等待原作业完成"
                        continue
                    item.status = STATUS_PENDING_RUN
                    item.message = "Restart 依赖已就绪"
                    ready_ids.append(item.item_id)
                    continue
                if dependency is None:
                    item.status = STATUS_WAITING_DEPENDENCY
                    item.message = "未找到 Restart 前置作业或 ODB"
                    continue
                if dependency.job_id not in item.dependency_job_ids:
                    item.dependency_job_ids.append(dependency.job_id)
                if dependency.status in {STATUS_COMPLETED, STATUS_DATACHECK_COMPLETED}:
                    odb_path = self._dependency_odb_path(dependency)
                    if odb_path:
                        item.oldjob_path = odb_path
                        item.oldjob_dir = str(Path(odb_path).parent)
                        item.status = STATUS_PENDING_RUN
                        item.message = "Restart 依赖已就绪"
                        ready_ids.append(item.item_id)
                    else:
                        item.status = STATUS_WAITING_DEPENDENCY
                        item.message = f"前置作业已完成，但未找到 ODB：{dependency.job_name}"
                    continue
                if dependency.status in ACTIVE_STATUSES or dependency.status in {
                    STATUS_PENDING_RUN,
                    STATUS_WAITING_DEPENDENCY,
                    STATUS_UNKNOWN,
                    STATUS_PENDING_CONFIRM,
                }:
                    item.status = STATUS_WAITING_DEPENDENCY
                    item.message = f"等待前置作业完成：{dependency.job_name}"
                    continue
                if dependency.status in TERMINAL_STATUSES:
                    item.status = STATUS_FAILED
                    item.message = f"前置作业未成功完成：{dependency.job_name}"

        self.queue_service.runtime_transaction(mutation)
        return ready_ids

    @staticmethod
    def _dependency_odb_path(item: QueueItem) -> str:
        candidates = []
        if item.archive_destination:
            candidates.append(Path(item.archive_destination) / f"{item.job_name}.odb")
        if item.effective_work_dir:
            candidates.append(Path(item.effective_work_dir) / f"{item.job_name}.odb")
        if item.inp_path:
            candidates.append(Path(item.inp_path).parent / f"{item.job_name}.odb")
        for path in candidates:
            if path.is_file() and not path.with_suffix(".lck").exists():
                return str(path)
        return ""

    def _launch(self, item_id: str, attempt_id: str) -> bool:
        # Keep admission, persisted STARTING and worker registration in one fence.
        with self._lock:
            if self._closing or not self._active:
                return False
            return self._launch_locked(item_id, attempt_id)

    def _launch_locked(self, item_id: str, attempt_id: str) -> bool:
        with self._lock:
            existing = self._runs.get(item_id)
            if existing is not None and existing.active:
                return False

        selected: QueueItem | None = None

        def mutation(_candidates: list[QueueItem], queue_items: list[QueueItem]) -> None:
            nonlocal selected
            for item in queue_items:
                if item.item_id != item_id or item.status != STATUS_STARTING or item.held or item.attempt_id != attempt_id:
                    continue
                item.status = STATUS_STARTING
                item.message = "正在准备本机执行环境"
                item.active_job_key = item.item_id
                self._scheduling.event(item, ExecutionEventKind.STARTING, item.message)
                selected = deepcopy(item)
                return

        with self._scheduling.core.transaction():
            self.queue_service.runtime_transaction(mutation)
        if selected is None:
            return False
        controller = LocalJobProcessController()
        record = _RuntimeRecord(
            item_id=selected.item_id,
            job_name=selected.job_name,
            controller=controller,
            attempt_id=attempt_id,
        )
        thread = threading.Thread(
            target=self._run_item,
            args=(selected, record),
            name=f"AbaqusLocalJob-{selected.job_name}",
            daemon=True,
        )
        record.thread = thread
        with self._lock:
            self._runs[item_id] = record
        try:
            self.event_store.append(
                aggregate_type="localJob",
                aggregate_id=item_id,
                kind="local.job.starting",
                version=1,
                payload={"jobName": selected.job_name, "attemptId": attempt_id},
            )
            thread.start()
        except Exception:
            self._runs.pop(item_id, None)
            raise
        return True

    def _run_item(self, item: QueueItem, record: _RuntimeRecord) -> None:
        def progress(phase: str, message: str, value: int, detail: str) -> None:
            with self._lock:
                if self._runs.get(item.item_id) is not record or not record.active:
                    return
                record.phase = phase
                record.message = message
                record.progress = value
                record.detail = detail
                if phase not in {"queued", "preparing", "starting"}:
                    record.status = STATUS_TERMINATING if record.controller.cancel_requested else STATUS_RUNNING
            if phase not in {"queued", "preparing", "starting"}:
                try:
                    self._update_queue_item(
                        item.item_id,
                        status=record.status,
                        message=detail or message,
                        attempt_id=record.attempt_id,
                    )
                except Exception as exc:
                    # A monitoring callback must not abandon the owned process.
                    LOGGER.exception("Unable to persist local execution progress")
                    with self._lock:
                        self._active = False
                        self._scheduler_error = f"运行状态保存失败：{exc}。仍在监控原作业，已暂停新作业调度。"

        def log(message: str) -> None:
            with self._lock:
                if self._runs.get(item.item_id) is not record or not record.active:
                    return
                record.logs.append(message)
                if len(record.logs) > 300:
                    del record.logs[:50]

        try:
            result = self.runner(
                item,
                self._existing_result_policy,
                record.controller,
                progress,
                log,
            )
        except Exception as exc:  # noqa: BLE001 - isolate one worker from the dispatcher
            status = STATUS_TERMINATED if record.controller.cancel_requested else STATUS_FAILED
            result = LocalJobExecutionResult(
                status=status,
                message=str(exc) or "本机作业执行失败",
                work_dir=item.effective_work_dir or str(Path(item.inp_path).parent),
                command="",
            )
        self._store_result(item, record, result)

    def _store_result(self, item, record, result):
        try:
            self._update_queue_item(
                item.item_id,
                status=result.status,
                message=result.message,
                effective_work_dir=result.work_dir,
                archive_destination=result.archive_destination,
                archive_status=result.archive_status,
                archive_error=result.archive_error,
                clear_active=True,
                attempt_id=record.attempt_id,
            )
        except Exception as exc:
            LOGGER.exception("Unable to persist local execution result")
            with self._lock:
                record.phase = "persistence_failed"
                record.message = f"执行已返回，但状态保存失败：{exc}"
                self._scheduler_error = record.message
                self._active = False
                self._pending_results[item.item_id] = (item, record, result)
                self._retry_results_after = time.monotonic() + 5
            return
        with self._lock:
            self._pending_results.pop(item.item_id, None)
            if not self._pending_results and self._scheduler_error.startswith("执行已返回，但状态保存失败"):
                self._scheduler_error = "执行结果已重新保存；请重新开始队列以继续调度。"
            record.status = result.status
            record.phase = "completed" if result.status in {STATUS_COMPLETED, STATUS_DATACHECK_COMPLETED} else "failed"
            if result.status == STATUS_UNKNOWN:
                record.phase = "unknown"
                self.queue_service.observe_recovered_directories([result.work_dir])
            record.message = result.message
            record.progress = 100
            record.finished_at = utc_now_text()
            self._close_scheduler_if_idle(excluding=record)
        self.event_store.append(
            aggregate_type="localJob",
            aggregate_id=item.item_id,
            kind="local.job.finished",
            version=2,
            payload={"status": result.status, "message": result.message, "attemptId": record.attempt_id},
        )
        self._wake.set()

    def _update_queue_item(
        self,
        item_id: str,
        *,
        status: str,
        message: str,
        effective_work_dir: str = "",
        archive_destination: str = "",
        archive_status: str = "",
        archive_error: str = "",
        clear_active: bool = False,
        attempt_id: str = "",
    ) -> None:
        def mutation(_candidates: list[QueueItem], queue_items: list[QueueItem]) -> None:
            for item in queue_items:
                if item.item_id != item_id:
                    continue
                expected = attempt_id or (self._runs[item_id].attempt_id if item_id in self._runs else "")
                if expected and item.attempt_id != expected:
                    return
                kind = {STATUS_RUNNING: ExecutionEventKind.STARTED, STATUS_TERMINATING: ExecutionEventKind.COMPLETING,
                        STATUS_COMPLETED: ExecutionEventKind.SUCCEEDED, STATUS_DATACHECK_COMPLETED: ExecutionEventKind.SUCCEEDED,
                        STATUS_TERMINATED: ExecutionEventKind.CANCELED, STATUS_UNKNOWN: ExecutionEventKind.LOST}.get(status, ExecutionEventKind.FAILED)
                self._scheduling.event(item, kind, message)
                item.status = status
                item.message = message
                if effective_work_dir:
                    item.effective_work_dir = effective_work_dir
                if archive_destination:
                    item.archive_destination = archive_destination
                if archive_status:
                    item.archive_status = archive_status
                item.archive_error = archive_error
                if clear_active:
                    item.active_job_key = ""
                    item.pids = []
                    item.pid_create_times = {}
                    item.rss_bytes = 0
                return

        with self._lock, self._scheduling.core.transaction():
            self.queue_service.runtime_transaction(mutation)

    def prepare_shutdown(self, *, reserve: bool = True) -> dict[str, Any]:
        with self._lock:
            active = [dict(record.as_payload(), kind="local.job", operationId=record.item_id)
                      for record in self._runs.values()
                      if record.active or (record.thread is not None and record.thread.is_alive())]
            _candidates, items = self.queue_service.runtime_items()
            owned = {operation["operationId"] for operation in active}
            active.extend({"kind": "local.job", "operationId": item.item_id, "jobName": item.job_name,
                           "status": item.status} for item in items
                          if item.item_id not in owned and item.status in ACTIVE_STATUSES | {STATUS_UNKNOWN})
            if self._active or self._dispatching:
                active.append({"kind": "local.queue", "operationId": "local",
                               "status": "dispatching"})
            safe = not active
            if safe and reserve:
                self._closing = True
                self._wake.set()
            return {"schemaVersion": 1, "safeToStop": safe, "operations": active}

    def close(self) -> None:
        with self._lock:
            self._closing = True
            self._active = False
        self._wake.set()
        self._dispatcher.join(timeout=2)
        with self._lock:
            self._close_scheduler_if_idle()

    def _close_scheduler_if_idle(self, excluding=None):
        if self._closing and not self._scheduler_closed and not any(
            record is not excluding and record.thread is not None and record.thread.is_alive()
            for record in self._runs.values()
        ):
            self._scheduling.close()
            self._scheduler_closed = True


__all__ = ["LocalJobRunner", "LocalQueueRuntimeManager"]
