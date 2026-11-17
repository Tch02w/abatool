"""Qt-free bridge from native queue transactions to the shared scheduler core."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import psutil

from modules.submitter.constants import (
    ACTIVE_STATUSES,
    STATUS_PENDING_RUN,
    STATUS_UNKNOWN,
    STATUS_WAITING_DEPENDENCY,
)
from modules.submitter.cpu_policy import local_cpu_policy
from modules.submitter.models import QueueItem
from modules.submitter.queue_scheduler import (
    effective_queue_item_work_dir,
    queue_item_conflict_key,
)
from modules.submitter.scheduler_adapter import (
    apply_scheduler_snapshot_to_queue_item,
    parse_memory_request_bytes,
    reconcile_scheduler_from_queue,
)
from modules.submitter.scheduler_repository import SQLiteSchedulerRepository
from modules.submitter.scheduling import (
    ACTIVE_JOB_STATES,
    ExecutionEvent,
    ExecutionEventKind,
    JobState,
    ResourceSnapshot,
    SchedulerCore,
)

from .contracts import ApiProblem


@dataclass(frozen=True)
class LocalSchedulingResources:
    logical_cpus: int
    available_memory_bytes: int


def read_scheduling_resources() -> LocalSchedulingResources:
    return LocalSchedulingResources(max(1, psutil.cpu_count(logical=True) or 1), int(psutil.virtual_memory().available))


class LocalQueueScheduling:
    """Caller holds the runtime lock; queue file and SQLite are persisted before launch.

    Both stores finish before launch. A crash between them is recovered as
    unknown, never as permission to replay an allocated execution attempt.
    """

    def __init__(self, queue_service, resource_provider=read_scheduling_resources):
        self.queue_service = queue_service
        self.resource_provider = resource_provider
        self.repository = SQLiteSchedulerRepository(queue_service.path.with_name("scheduler_state.db"))
        self.core = SchedulerCore(self.repository)
        self.notice = self.repository.recovery_message
        self._recovery_pending = True
        try:
            self._ensure_recovered()
        except (ApiProblem, OSError) as exc:
            # Preserve the unreadable queue without disabling unrelated APIs.
            self.notice = f"本机队列恢复未完成：{exc}。修复队列文件后重新开始；原文件未被覆盖。"

    def _ensure_recovered(self):
        if self._recovery_pending:
            self.notice = self.repository.recovery_message
            self._recover()
            self._recovery_pending = False

    def _recover(self):
        recovered = []
        directories = []

        def mutation(_candidates, items):
            known = {item.job_id for item in items}
            for stored in self.core.snapshots():
                if stored.job_id not in known and stored.state in ACTIVE_JOB_STATES:
                    spec = stored.specification
                    items.append(QueueItem(item_id=str(spec.metadata.get("item_id") or spec.job_id), job_id=spec.job_id,
                        job_name=spec.job_name, inp_path=str(Path(spec.work_dir) / (spec.job_name + ".inp")),
                        effective_work_dir=spec.work_dir, external_work_dir=spec.work_dir, is_external=True,
                        source="recovered_scheduler", status=STATUS_UNKNOWN, cores=spec.resources.cores,
                        attempt_id=stored.attempt_id, selected=False))
            for item in items:
                stored = self.core.get(item.job_id)
                if item.status in ACTIVE_STATUSES | {STATUS_UNKNOWN} or (stored is not None and stored.state in ACTIVE_JOB_STATES):
                    # Neither a saved UI status nor a PID alone proves liveness.
                    item.status = STATUS_UNKNOWN
                    item.message = "后台重启，等待核对原作业；不会自动重复提交"
                    item.active_job_key = ""
                    item.effective_work_dir = effective_queue_item_work_dir(item)
                    if stored is not None and stored.attempt_id:
                        item.attempt_id = stored.attempt_id
                    recovered.append(item.job_name)
                    directories.append(item.effective_work_dir)
            self.core.recover_orphaned_attempts({item.job_id for item in items})
            reconcile_scheduler_from_queue(self.core, items)

        with self.core.transaction():
            self.queue_service.runtime_transaction(mutation)
        self.queue_service.observe_recovered_directories(directories)
        if recovered:
            self.notice = "；".join(filter(None, [self.notice, f"已保留 {len(recovered)} 个待核对作业，自动扫描原工作目录后更新状态。未恢复自动调度。" ]))

    def reserve(self, ready_ids: list[str], max_parallel: int, finishing_ids: set[str]):
        self._ensure_recovered()
        resources = self.resource_provider()
        if resources.logical_cpus < 1 or resources.available_memory_bytes < 0:
            raise ValueError("本机资源读数无效，已暂停新作业调度")
        allocations = []

        def mutation(_candidates, items):
            by_job = {item.job_id: item for item in items}
            active = [item for item in items if item.status in ACTIVE_STATUSES or item.item_id in finishing_ids]
            # Unknown restored work is deliberately not counted as zero occupancy.
            unknown = [item for item in items if item.status == STATUS_UNKNOWN]
            policies = {}
            eligible = set()
            for item in items:
                if item.item_id not in ready_ids or item.is_external:
                    continue
                if item.cores <= 0:
                    item.message = "请先设置 Core 后再开始队列"
                    continue
                if item.abaqus_command not in policies:
                    policies[item.abaqus_command] = local_cpu_policy(item.abaqus_command)
                policy = policies[item.abaqus_command]
                if item.cores > policy["jobCpuLimit"]:
                    item.message = f"CPU 超过 {policy['jobCpuLimit']}；{policy['jobCpuPolicyNote']}，请编辑后重试"
                    continue
                eligible.add(item.job_id)
            # Keep disappeared active entries from reserving stale directory keys.
            self.core.recover_orphaned_attempts(set(by_job))
            reconcile_scheduler_from_queue(self.core, items)
            active_cores = sum(max(0, item.cores) for item in active)
            unknown_cores = any(item.cores <= 0 for item in active)
            # OS available memory already excludes RSS; reserve only each job's
            # configured absolute requirement not yet represented by observed RSS.
            unobserved_memory = sum(max(0, parse_memory_request_bytes(item.memory) - item.rss_bytes) for item in active)
            budget = ResourceSnapshot(
                available_slots=0 if unknown else max(0, max_parallel - len(active)),
                available_cores=0 if unknown_cores else max(0, resources.logical_cpus - active_cores),
                available_memory_bytes=max(0, resources.available_memory_bytes - unobserved_memory),
            )
            reserved = {queue_item_conflict_key(item) for item in active
                        if item.archive_status not in {"", "已归档"} or item.item_id in finishing_ids}
            plan = self.core.plan(budget, eligible_job_ids=eligible, archive_reserved_keys=reserved)
            for snapshot in plan.jobs:
                item = by_job.get(snapshot.job_id)
                if item is not None and item.status in {STATUS_PENDING_RUN, STATUS_WAITING_DEPENDENCY}:
                    apply_scheduler_snapshot_to_queue_item(snapshot, item)
                    if unknown and item.job_id in eligible:
                        item.message = "存在待核对的原作业，核对后再分配资源"
            allocations.extend((by_job[entry.job_id].item_id, entry.attempt_id) for entry in plan.allocations)

        # The outer transaction includes JSON replacement. If either store fails,
        # no process is launched; an interrupted dual write is recovered above.
        with self.core.transaction():
            self.queue_service.runtime_transaction(mutation)
        return allocations

    def event(self, item, kind: ExecutionEventKind, message: str):
        current = self.core.get(item.job_id)
        if current is None or current.attempt_id != item.attempt_id:
            return False
        if current.state == JobState.COMPLETING and kind == ExecutionEventKind.STARTED:
            return True
        target = {ExecutionEventKind.STARTING: JobState.STARTING, ExecutionEventKind.STARTED: JobState.RUNNING,
                  ExecutionEventKind.COMPLETING: JobState.COMPLETING, ExecutionEventKind.SUCCEEDED: JobState.COMPLETED,
                  ExecutionEventKind.FAILED: JobState.FAILED, ExecutionEventKind.CANCELED: JobState.CANCELED,
                  ExecutionEventKind.LOST: JobState.LOST}.get(kind)
        if current.state == target and current.message == message:
            return True
        if kind == ExecutionEventKind.SUCCEEDED and current.state in {JobState.DISPATCHED, JobState.STARTING}:
            self.core.apply_execution_event(ExecutionEvent(item.job_id, item.attempt_id, ExecutionEventKind.STARTED,
                                                          "执行器已返回完成结果"))
        self.core.apply_execution_event(ExecutionEvent(item.job_id, item.attempt_id, kind, message))
        return True

    def release_unlaunched(self, allocations):
        pending = dict(allocations)

        def mutation(_candidates, items):
            for item in items:
                if item.item_id not in pending or item.attempt_id != pending[item.item_id]:
                    continue
                state = self.core.get(item.job_id)
                if state is not None and state.state in {JobState.DISPATCHED, JobState.STARTING}:
                    self.core.transition(item.job_id, JobState.PENDING, message="启动已暂停，等待重新调度")
                    item.status = STATUS_PENDING_RUN
                    item.attempt_id = ""
                    item.active_job_key = ""
                    item.message = "启动已暂停，等待重新调度"
            reconcile_scheduler_from_queue(self.core, items)

        with self.core.transaction():
            self.queue_service.runtime_transaction(mutation)

    def close(self):
        self.core.close()
