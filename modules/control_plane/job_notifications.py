"""Durable, deduplicated job completion inbox; never infer success from inactivity."""
from __future__ import annotations

import copy
import hashlib
import math
import sqlite3
import threading
import time
from datetime import datetime

from modules.submitter.constants import (
    STATUS_COMPLETED,
    STATUS_DATACHECK_COMPLETED,
    STATUS_FAILED,
    STATUS_TERMINATED,
)
from modules.submitter.local_archive import archive_published

from .contracts import ApiProblem, utc_now_text
from .operation_journal import OperationJournal

LOCAL_TERMINAL = {STATUS_COMPLETED: "succeeded", STATUS_DATACHECK_COMPLETED: "succeeded",
                  STATUS_FAILED: "failed", STATUS_TERMINATED: "cancelled"}


def validate_record(record):
    if not isinstance(record, dict) or type(record.get("schemaVersion")) is not int or record["schemaVersion"] != 1:
        raise ValueError("作业提醒记录格式无效")
    if record.get("id") == "baseline":
        if (set(record) != {"id", "schemaVersion", "createdAt"} or type(record["createdAt"]) not in (int, float)
                or not math.isfinite(record["createdAt"]) or record["createdAt"] <= 0):
            raise ValueError("作业提醒起点无效")
        return
    if set(record) != {"schemaVersion", "id", "source", "executionId", "jobId", "jobName", "status",
                       "message", "workDirectory", "observedAt", "read"}:
        raise ValueError("作业提醒字段无效")
    if record["source"] not in {"local", "remote"} or record["status"] not in {"succeeded", "failed", "cancelled"}:
        raise ValueError("作业提醒状态无效")
    if type(record["read"]) is not bool or any(not isinstance(record[key], str) for key in
            ("id", "executionId", "jobId", "jobName", "message", "workDirectory", "observedAt")):
        raise ValueError("作业提醒内容无效")
    expected = hashlib.sha256((record["source"] + ":" + record["executionId"]).encode()).hexdigest()
    if not record["executionId"] or record["id"] != expected:
        raise ValueError("作业提醒执行身份无效")
    datetime.fromisoformat(record["observedAt"])


class JobNotificationManager:
    def __init__(self, path):
        self._lock = threading.RLock()
        self._records = {}
        self._pending = set()
        self._journal = None
        self._history_error = ""
        self._closed = False
        self._shutdown_reserved = False
        self._next_reconcile = 0
        self._reconcile_warning = ""
        self._stop = threading.Event()
        self.since = time.time()
        try:
            self._journal = OperationJournal(path, table="job_notifications", validator=validate_record, id_field="id")
            records = self._journal.load()
            baseline = next((item for item in records if item["id"] == "baseline"), None)
            if baseline is None:
                if records:
                    raise ValueError("作业提醒缺少起点，已保留原记录")
                self._journal.save({"schemaVersion": 1, "id": "baseline", "createdAt": self.since})
            else:
                self.since = baseline["createdAt"]
            self._records = {item["id"]: item for item in records if item["id"] != "baseline"}
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError) as exc:
            self._history_error = str(exc)
        self._maintenance = threading.Thread(target=self._retry, daemon=True, name="job-notification-writer")
        self._maintenance.start()

    def publish(self, *, source, execution_id, job_id, job_name, status, message="", work_directory=""):
        if not execution_id or status not in {"succeeded", "failed", "cancelled"}:
            return
        identifier = hashlib.sha256((source + ":" + execution_id).encode()).hexdigest()
        with self._lock:
            if self._closed or self._shutdown_reserved or identifier in self._records:
                return
            record = {"schemaVersion": 1, "id": identifier, "source": source, "executionId": execution_id,
                      "jobId": job_id, "jobName": job_name, "status": status, "message": message[:2000],
                      "workDirectory": work_directory, "observedAt": utc_now_text(), "read": False}
            validate_record(record)
            self._records[identifier] = record
            self._save_locked(record)

    def local_finished(self, item, record, result):
        if item.complete_notify and getattr(record, "archive_only", False):
            self.publish(source="local", execution_id=f"{record.attempt_id}:archive:{record.archive_operation_id}",
                         job_id=item.item_id, job_name=item.job_name,
                         status=("succeeded" if result.archive_status == "已归档" else
                                 "cancelled" if record.controller.cancel_requested else "failed"),
                         message="归档处理：" + result.archive_status + ("；" + result.archive_error if result.archive_error else ""),
                         work_directory=result.archive_destination if archive_published(result.archive_status, result.archive_destination)
                         else result.work_dir)
            return
        if item.complete_notify and result.status in LOCAL_TERMINAL:
            detail = result.message
            if result.archive_error:
                detail += "；归档未完成：" + result.archive_error
            self.publish(source="local", execution_id=record.attempt_id, job_id=item.item_id,
                         job_name=item.job_name, status=LOCAL_TERMINAL[result.status], message=detail,
                         work_directory=result.archive_destination if archive_published(result.archive_status, result.archive_destination)
                         else result.work_dir)

    def remote_finished(self, operation):
        if operation.request.notify and operation.status in {"succeeded", "failed", "cancelled"}:
            self.publish(source="remote", execution_id=operation.operation_id, job_id=operation.operation_id,
                         job_name=operation.request.job_name, status=operation.status, message=operation.phase,
                         work_directory=operation.work_directory)

    def reconcile(self, queue_service, remote_manager):
        # No inbox lock while reading other managers (completion takes the opposite direction).
        with self._lock:
            if self._closed or self._shutdown_reserved or time.monotonic() < self._next_reconcile:
                return
            self._next_reconcile = time.monotonic() + 30
        warnings = []
        try:
            _candidates, items = queue_service.runtime_items()
        except (ApiProblem, OSError, ValueError):
            items = []
            warnings.append("本机历史暂无法核对")
        for item in items:
            if item.complete_notify and item.attempt_id and item.submitted_at >= self.since and item.status in LOCAL_TERMINAL:
                self.publish(source="local", execution_id=item.attempt_id, job_id=item.item_id, job_name=item.job_name,
                             status=LOCAL_TERMINAL[item.status],
                             message=item.message + ("；归档问题：" + item.archive_error if item.archive_error else ""),
                             work_directory=item.archive_destination if archive_published(item.archive_status, item.archive_destination)
                             else item.effective_work_dir)
        # Remote history may be independently unreadable; do not hide local notifications.
        try:
            snapshots = remote_manager.list_snapshots()
        except ApiProblem:
            snapshots = []
            warnings.append("远端历史暂无法核对")
        for item in snapshots:
            if (item["status"] in {"succeeded", "failed", "cancelled"} and item["request"].get("notify", True)
                    and datetime.fromisoformat(item["createdAt"]).timestamp() >= self.since):
                self.publish(source="remote", execution_id=item["operationId"], job_id=item["operationId"],
                             job_name=item["request"]["jobName"], status=item["status"], message=item["phase"],
                             work_directory=item["workDirectory"])
        with self._lock:
            self._reconcile_warning = "；".join(warnings)

    def snapshot(self):
        with self._lock:
            self._check_history()
            unread = [item for item in self._records.values() if not item["read"]]
            unread.sort(key=lambda item: (item["observedAt"], item["id"]), reverse=True)
            return {"schemaVersion": 1, "unreadCount": len(unread), "items": copy.deepcopy(unread[:50]),
                    "persistenceWarning": "提醒尚未保存，请保留后台并检查磁盘。" if self._pending else self._reconcile_warning or None}

    def acknowledge(self, payload):
        if (not isinstance(payload, dict) or set(payload) != {"schemaVersion", "ids"}
                or type(payload["schemaVersion"]) is not int or payload["schemaVersion"] != 1
                or not isinstance(payload["ids"], list) or not 1 <= len(payload["ids"]) <= 50
                or any(not isinstance(item, str) for item in payload["ids"])):
            raise ApiProblem(400, "INVALID_JOB_NOTIFICATION_ACK", "请选择 1–50 条有效提醒")
        with self._lock:
            self._check_history()
            if self._closed or self._shutdown_reserved:
                raise ApiProblem(503, "CONTROL_PLANE_SHUTTING_DOWN", "后台已准备关闭，暂不修改提醒")
            if any(identifier not in self._records for identifier in payload["ids"]):
                raise ApiProblem(404, "JOB_NOTIFICATION_NOT_FOUND", "提醒不存在，请刷新后重试")
            for identifier in payload["ids"]:
                changed = dict(self._records[identifier], read=True)
                if not self._save_locked(changed):
                    # Keep unread until the acknowledgement is durable; retry must not acknowledge on its own.
                    self._pending.add(identifier)
                    raise ApiProblem(503, "JOB_NOTIFICATION_STORAGE_UNAVAILABLE", "已读状态未保存，请重试")
                self._records[identifier] = changed
            return self.snapshot()

    def _check_history(self):
        if self._history_error:
            raise ApiProblem(503, "JOB_NOTIFICATION_HISTORY_UNAVAILABLE", "提醒记录无法读取，原记录已保留；作业状态请查看作业概览")

    def _save_locked(self, record):
        try:
            if self._history_error or self._journal is None:
                raise OSError("提醒存储不可用")
            self._journal.save(record)
        except (OSError, sqlite3.Error, ValueError):
            self._pending.add(record["id"])
            return False
        self._pending.discard(record["id"])
        return True

    def _retry(self):
        while not self._stop.wait(1):
            with self._lock:
                if not self._history_error:
                    for identifier in tuple(self._pending):
                        self._save_locked(self._records[identifier])

    def prepare_shutdown(self, *, reserve=True):
        with self._lock:
            safe = not self._pending
            if safe and reserve:
                self._shutdown_reserved = True
            return {"schemaVersion": 1, "safeToStop": safe, "operations": [] if safe else [
                {"kind": "job.notifications", "operationId": "pending-notifications", "status": "saving"}]}

    def close(self):
        self._stop.set()
        self._maintenance.join(timeout=2)
        with self._lock:
            self._closed = True
            if self._journal is not None:
                self._journal.close()
                self._journal = None
