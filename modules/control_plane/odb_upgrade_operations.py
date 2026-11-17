"""Asynchronous upgrade state with safe cancellation and retry identity."""
from __future__ import annotations

import copy
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from modules.postprocessor.process_runner import ProcessCancelled
from modules.postprocessor.runner import UpgradeBatchController

from .contracts import ApiProblem, utc_now_text
from .odb_upgrade_execution import execute_confirmed_upgrade
from .odb_upgrade_journal import UpgradeJournal

TERMINAL = {"succeeded", "failed", "cancelled"}


class OdbUpgradeOperationManager:
    def __init__(self, *, runner=execute_confirmed_upgrade, journal_path=None, event_store=None):
        self._runner = runner
        self._events = event_store
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="odb-upgrade-operation")
        self._operations = {}
        self._requests = {}
        self._closed = False
        self._journal = None
        self._storage_error = None
        self._history_unavailable = False
        if journal_path is not None:
            try:
                self._journal = UpgradeJournal(Path(journal_path))
                records = self._journal.load()
                interrupted = False
                for item in records:
                    if item['status'] not in TERMINAL:
                        item['status'] = 'failed'
                        item['error'] = {'code': 'UPGRADE_INTERRUPTED', 'message':
                            '后台进程在升级完成确认前中断；未自动重跑。请确认原升级进程已退出，核查源文件、备份及临时文件，再重新检查兼容性。'}
                        item['version'] += 1
                        item['updatedAt'] = utc_now_text()
                        interrupted = True
                    item['_controller'] = UpgradeBatchController()
                    self._operations[item['operationId']] = item
                    self._requests[item['clientRequestId']] = item['operationId']
                if interrupted:
                    self._persist()
                for item in self._operations.values():
                    self._emit(item, 'odb.upgrade.recovered')
            except (OSError, ValueError, TypeError) as exc:
                self._storage_error = str(exc)
                self._history_unavailable = True

    def _require_history(self):
        if self._history_unavailable:
            raise ApiProblem(503, 'UPGRADE_HISTORY_UNAVAILABLE', '升级记录无法读取或被其他后台占用；已禁止新升级，请保留记录并检查后台。')

    def _emit(self, item, kind):
        if self._events is not None:
            self._events.append(aggregate_type='operation', aggregate_id=item['operationId'],
                kind=kind, version=item['version'], payload=copy.deepcopy({
                    key: item.get(key) for key in ('operationId', 'kind', 'status', 'version', 'progress', 'error', 'persistenceWarning')
                }))

    def _persist(self):
        if self._journal is None:
            return not self._storage_error
        try:
            self._journal.save([self._snapshot(item) for item in self._operations.values()])
            return True
        except (OSError, ValueError, TypeError) as exc:
            self._storage_error = str(exc)
            for item in self._operations.values():
                item['persistenceWarning'] = '升级记录写入失败；已请求安全停止。请保留当前后台，检查磁盘后重连核查，不要重复升级。'
                if item['status'] not in TERMINAL:
                    item['_controller'].cancel()
            return False

    def create(self, payload):
        if set(payload) != {"schemaVersion", "clientRequestId", "preview", "confirmed"}:
            raise ApiProblem(400, "INVALID_UPGRADE_REQUEST", "升级请求字段不完整或包含未知字段")
        if type(payload["schemaVersion"]) is not int or payload["schemaVersion"] != 1:
            raise ApiProblem(400, "UNSUPPORTED_SCHEMA_VERSION", "不支持该请求结构版本")
        request_id = payload["clientRequestId"]
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 200:
            raise ApiProblem(400, "INVALID_CLIENT_REQUEST_ID", "请求标识无效")
        if payload["confirmed"] is not True or not isinstance(payload["preview"], dict):
            raise ApiProblem(400, "UPGRADE_CONFIRMATION_REQUIRED", "必须确认有效的升级预览")
        preview = copy.deepcopy(payload["preview"])
        entries = preview.get("entries")
        if not isinstance(entries, list) or not entries or any(
            not isinstance(entry, dict) or not isinstance(entry.get("sourcePath"), str) for entry in entries
        ):
            raise ApiProblem(400, "INVALID_UPGRADE_PREVIEW", "升级预览没有有效源文件")
        with self._lock:
            self._require_history()
            if self._storage_error:
                raise ApiProblem(503, 'UPGRADE_HISTORY_UNAVAILABLE', '升级记录写入失败，已禁止新升级；请检查磁盘和现有任务。')
            if self._closed:
                raise ApiProblem(503, "CONTROL_PLANE_SHUTTING_DOWN", "控制面正在关闭")
            if request_id in self._requests:
                existing = self._operations[self._requests[request_id]]
                if existing["preview"] != preview:
                    raise ApiProblem(409, "IDEMPOTENCY_CONFLICT", "请求标识已用于其他升级计划")
                return self._snapshot(existing)
            operation_id = uuid4().hex
            item = {"schemaVersion": 1, "operationId": operation_id, "kind": "odb.upgrade",
                    "clientRequestId": request_id, "preview": preview, "status": "queued", "version": 1,
                    "createdAt": utc_now_text(), "updatedAt": utc_now_text(), "results": [], "logs": [],
                    "progress": {"completed": 0, "total": len(entries), "currentFile": ""},
                    "error": None, "_controller": UpgradeBatchController()}
            self._operations[operation_id] = item
            self._requests[request_id] = operation_id
            if not self._persist():
                del self._operations[operation_id]
                del self._requests[request_id]
                raise ApiProblem(503, 'UPGRADE_HISTORY_UNAVAILABLE', '升级记录无法保存，未启动此任务。')
            self._emit(item, 'odb.upgrade.queued')
            self._pool.submit(self._run, operation_id)
            return self._snapshot(item)

    @staticmethod
    def _snapshot(item):
        return copy.deepcopy({key: value for key, value in item.items() if not key.startswith("_")})

    def _require(self, operation_id):
        if operation_id not in self._operations:
            raise ApiProblem(404, "OPERATION_NOT_FOUND", "未找到升级操作")
        return self._operations[operation_id]

    def get(self, operation_id):
        with self._lock:
            self._require_history()
            return self._snapshot(self._require(operation_id))

    def list_snapshots(self, *, active_only=False):
        with self._lock:
            self._require_history()
            return [self._snapshot(item) for item in reversed(list(self._operations.values()))
                    if not active_only or item["status"] not in TERMINAL]

    def _touch(self, item, status=None, *, persist=True):
        if status is not None: item["status"] = status
        item["version"] += 1
        item["updatedAt"] = utc_now_text()
        saved = self._persist() if persist else True
        if persist:
            self._emit(item, f'odb.upgrade.{status or "updated"}')
        return saved

    def cancel(self, operation_id):
        with self._lock:
            item = self._require(operation_id)
            if item["status"] not in TERMINAL:
                item["_controller"].cancel()
                self._touch(item, "cancelled" if item["status"] == "queued" else "cancelling")
            return self._snapshot(item)

    def _run(self, operation_id):
        with self._lock:
            item = self._require(operation_id)
            if item["status"] in TERMINAL: return
            if not self._touch(item, "running"):
                item['error'] = {'code': 'UPGRADE_HISTORY_UNAVAILABLE', 'message': '升级记录无法保存，未开始执行。'}
                self._touch(item, 'failed')
                return
            controller = item["_controller"]

        def log(message):
            with self._lock:
                item["logs"].append(str(message)[:4000])
                item["logs"] = item["logs"][-1000:]
                parts = str(message).split("|", 4)
                checkpoint = False
                if len(parts) >= 4 and parts[0] in {"ODB_UPGRADE_START", "ODB_UPGRADE_DONE"}:
                    try:
                        count = int(parts[1])
                        total = int(parts[2])
                    except ValueError:
                        pass
                    else:
                        if total == item["progress"]["total"] and 0 <= count <= total:
                            checkpoint = True
                            if parts[0] == "ODB_UPGRADE_START":
                                item["progress"]["currentFile"] = "|".join(parts[3:])[:1000]
                            elif len(parts) == 5:
                                item["progress"]["completed"] = max(item["progress"]["completed"], count)
                # Flush ordinary logs at file/status checkpoints, not on every
                # launcher output line (which would rewrite all history).
                self._touch(item, persist=checkpoint)
        expected = {os.path.normcase(str(Path(entry["sourcePath"]).resolve())) for entry in item["preview"]["entries"]}

        def record_result(result):
            if not isinstance(result, dict) or not isinstance(result.get('source_path'), str):
                controller.cancel()
                raise ValueError('升级器返回了无效的逐文件回执')  # noqa: TRY004 - malformed worker output is an operation failure
            key = os.path.normcase(str(Path(result['source_path']).resolve()))
            if key not in expected or not isinstance(result.get('status'), str):
                controller.cancel()
                raise ValueError('升级回执不属于本次任务')
            with self._lock:
                previous = next((r for r in item['results'] if os.path.normcase(str(Path(r['source_path']).resolve())) == key), None)
                if previous is not None:
                    if previous != result:
                        controller.cancel()
                        raise ValueError('同一文件的升级回执发生冲突')
                    return
                item['results'].append(copy.deepcopy(result))
                item['progress']['completed'] = len(item['results'])
                self._touch(item)

        try:
            report = self._runner(copy.deepcopy(item["preview"]), confirmed=True, controller=controller, log=log, on_result=record_result)
            results = report.get("results", [])
            if not isinstance(results, list) or any(not isinstance(result, dict) for result in results):
                raise ValueError("升级器返回了无效的逐文件结果")
            returned = {os.path.normcase(str(Path(result.get("source_path", "")).resolve())) for result in results}
            # Invalid final reports must not overwrite previously saved receipts.
            if returned - expected or len(results) != len(returned):
                raise ValueError('升级器返回了重复或非本次任务的文件回执')
            for result in results:
                record_result(result)
            with self._lock:
                item["progress"]["currentFile"] = ""
                if controller.stop_requested:
                    self._touch(item, "cancelled")
                elif returned != expected or len(results) != len(item["preview"]["entries"]) or any(
                    result.get("status") != "upgraded" for result in results
                ):
                    item["error"] = {"code": "UPGRADE_INCOMPLETE", "message": "部分文件未升级成功，请检查逐文件结果"}
                    self._touch(item, "failed")
                else:
                    self._touch(item, "succeeded")
        except ProcessCancelled:
            with self._lock: self._touch(item, "cancelled")
        except Exception as exc:  # noqa: BLE001 - worker boundary persists failures for UI recovery
            with self._lock:
                item["error"] = {"code": "UPGRADE_FAILED", "message": str(exc)[:2000]}
                self._touch(item, "failed")

    def prepare_shutdown(self, *, reserve=True):
        """Atomically reserve an idle manager for exit; never kill an active file.

        An active manager remains usable if its UI disconnects. A successful
        reservation rejects further submissions, closing the check/kill race.
        """
        with self._lock:
            active = self.list_snapshots(active_only=True)
            safe = not active and not self._storage_error
            if safe and reserve:
                self._closed = True
            return {"schemaVersion": 1, "safeToStop": bool(safe), "operations": active}

    def close(self):
        with self._lock:
            self._closed = True
            for item in self._operations.values():
                if item["status"] not in TERMINAL: self.cancel(item["operationId"])
        # Never kill an active upgrade during file replacement.
        try:
            self._pool.shutdown(wait=True)
        finally:
            if self._journal is not None:
                self._journal.close()
