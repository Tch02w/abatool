"""Reversible close preparation and backend-owned graceful shutdown."""

from __future__ import annotations

import re
import threading
import time
from contextlib import contextmanager
from typing import Any

from .contracts import ApiProblem


class ShutdownProtocol:
    def __init__(self, *, clock=time.monotonic, lease_seconds: float = 60):
        self._lock = threading.RLock()
        self._clock = clock
        self._lease_seconds = lease_seconds
        self._lease: dict[str, Any] | None = None
        self._receipts: dict[str, dict[str, Any]] = {}
        self._requests = 0
        self._sealed = False

    def _expire(self):
        if self._lease is not None and self._clock() >= self._lease["expires"]:
            # Stops already requested are not undone. Admission becomes usable
            # again if the UI disappears before committing a close.
            self._lease = None

    @contextmanager
    def request(self):
        with self._lock:
            self._expire()
            if self._sealed:
                raise ApiProblem(503, "CONTROL_PLANE_SHUTTING_DOWN", "后台正在退出")
            if self._lease is not None:
                raise ApiProblem(503, "CONTROL_PLANE_CLOSE_PENDING", "正在确认关闭，暂不接受新操作", retryable=True)
            self._requests += 1
        try:
            yield
        finally:
            with self._lock:
                self._requests -= 1

    @staticmethod
    def validate(payload, *, fields=()):
        if payload.get("schemaVersion") != 1 or set(payload) - {"schemaVersion", *fields}:
            raise ApiProblem(400, "INVALID_SHUTDOWN_REQUEST", "关闭请求字段或版本无效")

    def _require(self, request_id):
        self._expire()
        if self._lease is None or self._lease["requestId"] != request_id:
            raise ApiProblem(409, "SHUTDOWN_REQUEST_EXPIRED", "关闭准备已失效，请重新关闭窗口")
        self._lease["expires"] = self._clock() + self._lease_seconds
        return self._lease

    def _snapshot(self, context):
        status = context.prepare_odb_shutdown(reserve=False)
        assert self._lease is not None
        # The close dialog lists work the user can identify. The safety decision
        # above includes every child worker, including final cleanup.
        group_children = {group["childOperationId"] for item in status["operations"]
                          if item.get("kind") == "odb.postprocess.group-queue"
                          for group in item.get("groups", ()) if group.get("childOperationId")}
        return {"schemaVersion": 1, "kind": "controlPlane.shutdown",
                "requestId": self._lease["requestId"], "state": self._lease["state"],
                "safeToStop": bool(status["safeToStop"] and self._requests == 0),
                "pendingRequests": self._requests, "stopBackend": False,
                "operations": [{"operationId": item.get("operationId", ""),
                                "kind": item.get("kind", "operation"),
                                "name": item.get("jobName") or item.get("phase") or item.get("kind", "后台任务"),
                                "status": item.get("status", "unknown")}
                               for item in status["operations"]
                               if item.get("operationId") not in group_children]}

    def prepare(self, context, payload):
        self.validate(payload, fields=("clientRequestId",))
        request_id = payload.get("clientRequestId")
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", request_id):
            raise ApiProblem(400, "INVALID_SHUTDOWN_REQUEST", "关闭请求标识无效")
        with self._lock:
            self._expire()
            if request_id in self._receipts:
                return dict(self._receipts[request_id])
            if self._sealed:
                raise ApiProblem(503, "CONTROL_PLANE_SHUTTING_DOWN", "后台正在退出")
            if self._lease is not None and self._lease["requestId"] != request_id:
                raise ApiProblem(409, "SHUTDOWN_ALREADY_PREPARED", "已有窗口正在确认关闭")
            if self._lease is None:
                self._lease = {"requestId": request_id, "state": "prepared", "expires": 0}
            self._lease["expires"] = self._clock() + self._lease_seconds
            return self._snapshot(context)

    def get(self, context, request_id):
        with self._lock:
            if request_id in self._receipts:
                return dict(self._receipts[request_id])
            self._require(request_id)
            return self._snapshot(context)

    def abort(self, context, request_id):
        with self._lock:
            if request_id in self._receipts:
                return dict(self._receipts[request_id])
            self._require(request_id)
            snapshot = self._snapshot(context)
            snapshot["state"] = "aborted"
            self._lease = None
            self._remember(request_id, snapshot)
            return snapshot

    def stop(self, context, request_id):
        with self._lock:
            lease = self._require(request_id)
            lease["state"] = "stopping"
            if self._requests:
                raise ApiProblem(409, "SHUTDOWN_REQUESTS_BUSY", "请等待当前提交或文件操作结束后再停止任务")
            # Stop dispatch first; never infer solver ownership from a process name.
            local = context.local_queue_runtime
            local.control({"schemaVersion": 1, "action": "stop"})
            managers = (context.postprocess_group_queue, context.odb_result_batch_manager, context.odb_merge_manager,
                        context.odb_upgrade_manager, context.postprocess_manager,
                        context.operation_manager, context.result_index_manager,
                        context.remote_transfer_manager)
            for manager in managers:
                for item in manager.list_snapshots(active_only=True):
                    manager.cancel(item["operationId"])
            for item in context.remote_job_manager.list_snapshots(active_only=True):
                context.remote_job_manager.control(item["operationId"], "cancel")
            ids = local.snapshot()["activeItemIds"]
            if ids:
                try:
                    local.control({"schemaVersion": 1, "action": "terminate", "itemIds": ids})
                except ApiProblem as problem:
                    if problem.code != "NO_ACTIVE_LOCAL_JOBS":
                        raise
            return self._snapshot(context)

    def commit(self, context, request_id, mode):
        if mode not in {"idle", "background", "stop"}:
            raise ApiProblem(400, "INVALID_SHUTDOWN_MODE", "关闭方式无效")
        with self._lock:
            if request_id in self._receipts:
                receipt = self._receipts[request_id]
                if receipt.get("mode") != mode or receipt["state"] != "committed":
                    raise ApiProblem(409, "SHUTDOWN_COMMIT_CONFLICT", "关闭决定与已有回执不一致")
                return dict(receipt)
            lease = self._require(request_id)
            state = self._snapshot(context)
            if self._requests:
                raise ApiProblem(409, "SHUTDOWN_REQUESTS_BUSY", "仍有未完成的提交或文件操作，不能关闭")
            if mode != "background" and not state["safeToStop"]:
                raise ApiProblem(409, "SHUTDOWN_WORK_ACTIVE", "后台工作尚未安全结束，关闭已取消")
            if mode == "stop" and lease["state"] != "stopping":
                raise ApiProblem(409, "SHUTDOWN_STOP_NOT_REQUESTED", "尚未请求停止任务")
            state.update(state="committed", mode=mode, stopBackend=mode != "background")
            # Existing dispatch/batch work is included in the idle check. New
            # HTTP work is fenced. The backend exits itself; no stale client
            # response can later kill a newly admitted task or replacement PID.
            self._sealed = state["stopBackend"]
            self._lease = None
            self._remember(request_id, state)
            return state

    def _remember(self, request_id, state):
        self._receipts[request_id] = dict(state)
        while len(self._receipts) > 32:
            self._receipts.pop(next(iter(self._receipts)))

    def legacy_reserve(self, context):
        with self._lock:
            self._expire()
            if self._requests or self._lease is not None:
                return {"schemaVersion": 1, "scope": "all-workers-v1", "safeToStop": False,
                        "operations": [{"kind": "controlPlane.request", "operationId": "pending", "status": "active"}]}
            state = context.prepare_odb_shutdown()
            if state["safeToStop"]:
                self._sealed = True
            return state
