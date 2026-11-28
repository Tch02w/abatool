"""Confirm and cancel the exact set of local attempts shown to the operator."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from uuid import uuid4

from modules.common.json_io import save_json_mapping
from modules.submitter.constants import (
    ACTIVE_STATUSES, STATUS_CANCELED, STATUS_COMPLETED, STATUS_PENDING_RUN,
    STATUS_TERMINATING, STATUS_WAITING_DEPENDENCY,
)
from modules.submitter.scheduler_adapter import queue_item_to_job_specification
from modules.submitter.scheduling import ExecutionEventKind, JobState

from .contracts import SCHEMA_VERSION, ApiProblem


@dataclass(frozen=True)
class _Target:
    item_id: str
    job_id: str
    attempt_id: str
    job_name: str
    inp_path: str
    kind: str
    archive_operation: str

    def payload(self):
        data = {"itemId": self.item_id, "attemptId": self.attempt_id, "jobName": self.job_name,
                "inpPath": self.inp_path}
        if self.kind != "pending":
            data["archiveOnly"] = self.kind == "archive"
        return data


def _scope_changed():
    return ApiProblem(409, "LOCAL_QUEUE_TERMINATION_SCOPE_CHANGED",
                      "本机队列或当前执行已变化，请重新查看终止范围并确认。")


def _interrupted():
    return ApiProblem(409, "LOCAL_QUEUE_TERMINATION_INTERRUPTED",
                      "上次整队终止的执行或回执保存未完成。请刷新队列核对实际状态，再重新选择终止。")


def _is_accepted_receipt(receipt, token):
    counts = ("pendingCancelled", "terminationRequested", "untouchedCount")
    return (isinstance(receipt, dict) and type(receipt.get("schemaVersion")) is int
            and receipt["schemaVersion"] == SCHEMA_VERSION and receipt.get("status") == "accepted"
            and receipt.get("confirmationId") == token
            and all(type(receipt.get(name)) is int and receipt[name] >= 0 for name in counts))


class WholeQueueTerminationMixin:
    def _owned_cancellable(self, item):
        record = self._runs.get(item.item_id)
        if (item.is_external or record is None or not record.active or record.finishing
                or record.controller.cancel_requested or not record.attempt_id
                or record.attempt_id != item.attempt_id or record.job_name != item.job_name):
            return None
        if record.archive_only:
            return record if item.status == STATUS_COMPLETED and item.archive_status == "归档中" else None
        return record if item.status in ACTIVE_STATUSES else None

    def _termination_targets(self, items):
        targets = []
        for item in items:
            record = self._owned_cancellable(item)
            if record is not None:
                kind = "archive" if record.archive_only or record.phase == "archiving" else "running"
            elif (not item.is_external and item.status in {STATUS_PENDING_RUN, STATUS_WAITING_DEPENDENCY}
                  and not (self._runs.get(item.item_id) and self._runs[item.item_id].active)):
                kind = "pending"
            else:
                continue
            targets.append(_Target(item.item_id, item.job_id, item.attempt_id, item.job_name, item.inp_path,
                                   kind, record.archive_operation_id if record else ""))
        return targets

    def _termination_scope(self, targets):
        return self._active, self._scheduling_generation, frozenset(targets)

    def _preview_termination(self, payload):
        if set(payload) - {"action", "schemaVersion"}:
            raise ApiProblem(400, "UNKNOWN_FIELDS", "终止范围预览包含未知字段")
        with self._lock:
            _, items = self.queue_service.runtime_items()
            targets = self._termination_targets(items)
            token = uuid4().hex
            if len(self._termination_previews) >= 128:
                self._termination_previews.pop(next(iter(self._termination_previews)))
            self._termination_previews[token] = self._termination_scope(targets)
            return {"schemaVersion": SCHEMA_VERSION, "confirmationId": token, "schedulingActive": self._active,
                    "pending": [target.payload() for target in targets if target.kind == "pending"],
                    "running": [target.payload() for target in targets if target.kind != "pending"],
                    "untouchedCount": len(items) - len(targets)}

    def _cancel_pending(self, item, items, index):
        core = self._scheduling.core
        stored = core.get(item.job_id)
        # A new entry, or a terminal job explicitly requeued, may not have reached reserve() yet.
        if stored is None or stored.state != JobState.PENDING or stored.attempt_id != item.attempt_id:
            spec = queue_item_to_job_specification(item, queue_items=items, submitted_order=index)
            core.reconcile(spec, state=JobState.PENDING, attempt_id=item.attempt_id, message=item.message)
        item.status = STATUS_CANCELED
        item.message = "用户终止整个本机队列，已取消调度"
        self._scheduling.event(item, ExecutionEventKind.CANCELED, item.message)

    def _mark_running_termination(self, item, record):
        if record.archive_only:
            item.archive_error = "正在取消归档，等待当前文件检查结束"
        else:
            item.status = STATUS_TERMINATING
            item.message = "已提交终止请求，等待执行器核对"
            self._scheduling.event(item, ExecutionEventKind.COMPLETING, item.message)

    @staticmethod
    def _signal_terminations(records):
        for record in records:
            record.controller.cancel()
            record.status = STATUS_TERMINATING
            record.phase = "archive_cancelling" if record.archive_only or record.phase == "archiving" else "terminating"
            record.message = "已提交终止请求，等待执行器核对"

    def _confirm_termination(self, payload):
        if set(payload) - {"action", "schemaVersion", "confirmationId"}:
            raise ApiProblem(400, "UNKNOWN_FIELDS", "整队终止请求包含未知字段")
        token = payload.get("confirmationId")
        if not isinstance(token, str) or not re.fullmatch("[0-9a-f]{32}", token):
            raise ApiProblem(400, "INVALID_CONFIRMATION_ID", "请先预览终止范围并提交对应的确认编号")
        queue_path = self.queue_service.path
        path = queue_path.parent / "local-queue-terminations" / queue_path.name / f"{token}.json"
        with self._lock:
            try:
                receipt = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                receipt = None
            except (OSError, ValueError) as exc:
                raise _interrupted() from exc
            else:
                if _is_accepted_receipt(receipt, token):
                    return receipt
                raise _interrupted()
            if self._closing:
                raise ApiProblem(503, "CONTROL_PLANE_SHUTTING_DOWN", "控制面正在关闭")
            expected = self._termination_previews.get(token)
            if expected is None:
                raise _scope_changed()

            def apply(_candidates, items):
                targets = self._termination_targets(items)
                if self._termination_scope(targets) != expected:
                    self._termination_previews.pop(token, None)
                    raise _scope_changed()
                if not targets and not self._active:
                    raise ApiProblem(409, "NO_LOCAL_QUEUE_TARGETS", "当前没有可终止的本机作业或调度")
                # Persist intent before touching admission, queue state, or any owned controller.
                self._termination_previews.pop(token)
                save_json_mapping(path, {"schemaVersion": SCHEMA_VERSION, "confirmationId": token, "status": "applying"})
                self._active = False
                self._stop_requested = True
                self._scheduling_generation += 1
                kinds = {target.item_id: target.kind for target in targets}
                records = []
                for index, item in enumerate(items):
                    kind = kinds.get(item.item_id)
                    if kind == "pending":
                        self._cancel_pending(item, items, index)
                    elif kind is not None:
                        record = self._runs[item.item_id]
                        self._mark_running_termination(item, record)
                        records.append(record)
                return records, {"schemaVersion": SCHEMA_VERSION, "confirmationId": token, "status": "accepted",
                                 "pendingCancelled": len(targets) - len(records), "terminationRequested": len(records),
                                 "untouchedCount": len(items) - len(targets)}

            try:
                with self._scheduling.core.transaction():
                    records, receipt = self.queue_service.runtime_transaction(apply)
                self._signal_terminations(records)
                save_json_mapping(path, receipt)
            except ApiProblem:
                raise
            except Exception as exc:
                self._scheduler_error = f"整队终止未完成，请核对实际状态：{exc}"
                raise _interrupted() from exc
            finally:
                self._wake.set()
            self._termination_previews.pop(token, None)
            return receipt
