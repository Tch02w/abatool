"""Durable tracking and reconnect coordination. Recovery never submits a solver."""
from __future__ import annotations

import ntpath
import sqlite3
import threading
import time
from dataclasses import asdict
from datetime import datetime

from modules.submitter.remote_connection import RemoteConnectionError

from .compatibility import FAILED, RUNNING, TERMINAL_STATUSES
from .contracts import ApiProblem
from .remote_job_journal import RemoteJobJournal

REQUEST_NAMES = {"client_request_id": "clientRequestId", "job_name": "jobName", "input_mode": "inputMode",
                 "input_path": "inputPath", "oldjob_path": "oldjobPath", "fortran_path": "fortranPath",
                 "cpus": "cpus", "memory": "memory", "datacheck": "datacheck", "notify": "notify"}


class RemoteJobRecovery:
    def _init_recovery(self, path):
        self._journal = None
        self._history_error = ""
        self._storage_error = ""
        self._pending_saves = set()
        if path is not None:
            try:
                self._journal = RemoteJobJournal(path)
                recovered = [self._restore(record) for record in self._journal.load()]
                if len({op.request.client_request_id for op in recovered}) != len(recovered):
                    raise ValueError("远端记录存在重复请求身份")
                for op in recovered:
                    self._operations[op.operation_id] = op
                    self._client_requests[op.request.client_request_id] = op.operation_id
                    if op.status not in TERMINAL_STATUSES:
                        if op.launch_state == "preparing":
                            op.status, op.tracking_state = FAILED, "interrupted"
                            op.phase = "后台在提交前中断，未自动提交"
                            op.error = {"code": "REMOTE_PREPARATION_INTERRUPTED", "message": op.phase}
                        else:
                            op.status, op.tracking_state = RUNNING, "reconnecting"
                            op.phase = "已恢复原任务，连接原服务器后核对；不会重复提交"
                        self._persist_locked(op)
            except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, ApiProblem) as exc:
                self._operations.clear()
                self._client_requests.clear()
                self._history_error = str(exc)
        self._maintenance = threading.Thread(target=self._maintain, daemon=True, name="remote-job-recovery")
        self._maintenance.start()

    def _restore(self, record):
        request = self._request_type.from_payload(record["request"], validate_local_files=False)
        snapshot = record["snapshot"]
        for key in ("createdAt", "updatedAt"):
            datetime.fromisoformat(snapshot[key])
        op = self._operation_type(request, operation_id=snapshot["operationId"], status=snapshot["status"],
            created_at=snapshot["createdAt"], updated_at=snapshot["updatedAt"], version=snapshot["version"],
            percent=snapshot["percent"], phase=snapshot["phase"], work_directory=snapshot["workDirectory"],
            process_id=snapshot["processId"], process_start_ticks=record["processStartTicks"],
            paused=snapshot["paused"], logs=snapshot["logs"], error=snapshot.get("error"),
            server_identity=record["serverIdentity"], launch_state=record["launchState"],
            tracking_state=snapshot["trackingState"], log_tails=record["logTails"])
        expected = ntpath.join(op.server_identity["computeRoot"], request.job_name + "_" + op.operation_id)
        if op.work_directory and ntpath.normcase(ntpath.normpath(op.work_directory)) != ntpath.normcase(expected):
            raise ValueError("远端工作目录与任务身份不一致")
        if op.launch_state != "preparing" and not op.work_directory:
            raise ValueError("已提交的远端任务缺少工作目录")
        op.files = {ext: ntpath.join(op.work_directory, request.job_name + "." + ext)
                    for ext in ("sta", "msg", "dat", "log", "odb")} if op.work_directory else {}
        op.completion.error_seen = record["completion"]["error_seen"]
        op.completion.termination_seen = record["completion"]["termination_seen"]
        if record["cancelRequested"]:
            op.cancel_event.set()
        return op

    def _record(self, op):
        return {"schemaVersion": 1, "snapshot": self._snapshot_locked(op),
                "request": {"schemaVersion": 1, **{REQUEST_NAMES[key]: value for key, value in asdict(op.request).items()}},
                "serverIdentity": op.server_identity, "launchState": op.launch_state,
                "processStartTicks": op.process_start_ticks, "cancelRequested": op.cancel_event.is_set(),
                "completion": {"error_seen": op.completion.error_seen, "termination_seen": op.completion.termination_seen},
                "logTails": op.log_tails}

    def _persist_locked(self, op, *, required=False):
        if self._journal is None:
            return
        try:
            self._journal.save(self._record(op))
        except (OSError, sqlite3.Error, ValueError) as exc:
            self._pending_saves.add(op.operation_id)
            self._storage_error = str(exc)
            op.persistence_warning = "任务记录暂未保存，已禁止新提交；保留当前后台并检查磁盘。"
            if required:
                raise ApiProblem(503, "REMOTE_JOB_STORAGE_UNAVAILABLE", op.persistence_warning) from exc
        else:
            self._pending_saves.discard(op.operation_id)
            op.persistence_warning = ""
            op.last_saved_at = time.monotonic()
            if not self._pending_saves:
                self._storage_error = ""

    def _check_history(self):
        if self._history_error:
            raise ApiProblem(503, "REMOTE_JOB_HISTORY_UNAVAILABLE", "远端记录无法读取，已保留原文件并禁止新提交")

    def can_reconnect(self, payload):
        identity = self._service.requested_identity(payload)
        with self._lock:
            self._check_history()
            return all(op.server_identity == identity for op in self._operations.values() if op.status not in TERMINAL_STATUSES)

    def _submit_locked(self, op, *, recover=False):
        future = self._executor.submit(self._resume if recover else self._run, op.operation_id)
        self._futures[op.operation_id] = future
        future.add_done_callback(lambda _future: self._close_journal_if_idle())

    def _maintain(self):
        while not self._stop_event.wait(.5):
            with self._lock:
                for key in tuple(self._pending_saves):
                    self._persist_locked(self._operations[key])
                candidates = [op for op in self._operations.values() if op.status not in TERMINAL_STATUSES
                              and op.launch_state != "preparing" and
                              (op.operation_id not in self._futures or self._futures[op.operation_id].done())]
            for op in candidates:
                try:
                    self._service.connected_profile(op.server_identity)
                except RemoteConnectionError:
                    continue
                with self._lock:
                    if not self._closed and (op.operation_id not in self._futures or self._futures[op.operation_id].done()):
                        try:
                            self._submit_locked(op, recover=True)
                        except RuntimeError as exc:
                            self._tracking_lost(op, exc)
        self._close_journal_if_idle()

    def _close_journal_if_idle(self):
        with self._lock:
            if self._closed and all(future.done() for future in self._futures.values()) and self._journal is not None:
                self._journal.close()
                self._journal = None

    def prepare_shutdown(self, *, reserve=True):
        with self._lock:
            if self._pending_saves or self._history_error:
                return {"schemaVersion": 1, "safeToStop": False, "operations": [
                    {"operationId": "remote-records", "kind": "remote.job", "status": "records-unconfirmed"}]}
            return super().prepare_shutdown(reserve=reserve)
