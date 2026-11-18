"""Archive-only recovery within the existing local runtime/close fences."""
from __future__ import annotations

import logging
import threading
from copy import deepcopy

from modules.submitter.archive_notifications import ArchiveNoticeStore
from modules.submitter.constants import (
    ACTIVE_STATUSES,
    STATUS_COMPLETED,
)
from modules.submitter.local_archive_recovery import _plan
from modules.submitter.local_archive_state import (
    ArchiveBusyError,
    ArchiveStateStore,
    work_directory,
)
from modules.submitter.local_job_execution import (
    LocalJobExecutionResult,
    LocalJobProcessController,
    run_archive_only,
)

from .contracts import ApiProblem, utc_now_text

LOGGER = logging.getLogger(__name__)


class LocalArchiveRecoveryMixin:
    def _init_archive_recovery(self):
        self._archive_store = ArchiveStateStore(self.queue_service.path.parent / "archive-state")
        try:
            _, items = self.queue_service.runtime_items()
        except (OSError, ValueError, ApiProblem):
            return
        for item in items:
            if not item.attempt_id or not item.archive_dir:
                continue
            try:
                # Only an existing checkpoint can prove that the solve had finished.
                if not self._archive_store.path(item).exists():
                    continue
                with self._archive_store.claim(item):
                    state = self._archive_store.read(item)
                    if state is None:
                        continue
                    if state["phase"] != "confirmed":
                        _plan(item, state)
                    result = state.get("result")
                    if result is not None and (not isinstance(result, dict) or result.get("status") not in {
                            "已归档", "归档失败", "归档已取消", "已归档，清理未完成", "归档需核对", "归档待恢复"}
                                or not isinstance(result.get("error"), str) or not isinstance(result.get("destination"), str)
                                or (result["destination"] and result["destination"] != state.get("destination"))
                                or (result["status"] == "已归档" and state["phase"] != "done")):
                        raise ValueError("归档结果记录无效")
                    status = result["status"] if result else "归档待恢复"
                    error = result["error"] if result else "上次归档未收尾，请恢复归档以核对已有文件；不会重新求解"
                    destination = result["destination"] if result else ""
                    if (item.status == STATUS_COMPLETED and not item.active_job_key
                            and (item.archive_status, item.archive_error, item.archive_destination, item.archive_recovery_available)
                            == (status, error, destination, status != "已归档")):
                        continue
                    self._set_archive_state(item, status, error, destination, status != "已归档", confirmed=True)
            except ArchiveBusyError:
                # Another live owner still holds the operation; never take it over.
                continue
            except (OSError, ValueError, TypeError, KeyError) as exc:
                LOGGER.exception("Unable to restore archive checkpoint")
                self._set_archive_state(item, "归档记录异常", str(exc), "", False)

    def _set_archive_state(self, expected, status, error, destination, available, *, confirmed=False):
        def mutation(_candidates, items):
            for item in items:
                if item.item_id != expected.item_id or item.attempt_id != expected.attempt_id:
                    continue
                if confirmed:
                    self._scheduling.confirm_archive_solve(item)
                    item.status = STATUS_COMPLETED
                    item.active_job_key = ""
                    item.pids = []
                    item.pid_create_times = {}
                    item.rss_bytes = 0
                    item.memory_observation_status = "ended"
                item.archive_status, item.archive_error = status, error
                item.archive_destination, item.archive_recovery_available = destination, available
                item.message = "计算已完成；" + status if item.status == STATUS_COMPLETED else item.message
                return
        with self._lock, self._scheduling.core.transaction():
            self.queue_service.runtime_transaction(mutation)

    def _retry_archive(self, payload):
        if set(payload) - {"schemaVersion", "action", "itemIds"}:
            raise ApiProblem(400, "UNKNOWN_FIELDS", "归档恢复请求包含未知字段")
        ids = payload.get("itemIds")
        if not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], str) or not ids[0].strip():
            raise ApiProblem(400, "INVALID_ITEM_IDS", "每次请选择一个作业恢复归档")
        with self._lock:
            if self._closing:
                raise ApiProblem(503, "CONTROL_PLANE_SHUTTING_DOWN", "后台正在关闭")
            _, items = self.queue_service.runtime_items()
            item = next((entry for entry in items if entry.item_id == ids[0]), None)
            if item is None:
                raise ApiProblem(404, "QUEUE_ITEM_NOT_FOUND", "未找到作业")
            if item.is_external or item.status != STATUS_COMPLETED or not item.archive_recovery_available:
                raise ApiProblem(409, "ARCHIVE_RECOVERY_UNAVAILABLE", "该作业没有可恢复的已完成求解归档")
            active = [r for r in self._runs.values() if r.active or (r.thread and r.thread.is_alive())]
            if len(active) >= self._max_parallel or any(r.item_id == item.item_id for r in active):
                raise ApiProblem(409, "LOCAL_ARCHIVE_BUSY", "已有作业或归档占用运行槽位，请等待结束")
            source = work_directory(item)
            active_ids = {r.item_id for r in active}
            for other in items:
                if other.item_id == item.item_id or (other.status not in ACTIVE_STATUSES and other.item_id not in active_ids
                                                     and other.archive_status != "归档中"):
                    continue
                other_source = work_directory(other)
                if source.is_relative_to(other_source) or other_source.is_relative_to(source):
                    raise ApiProblem(409, "LOCAL_ARCHIVE_BUSY", "计算目录正在使用，未恢复归档")
            claim = self._archive_store.claim(item)
            try:
                claim.__enter__()
            except (ArchiveBusyError, OSError, ValueError) as exc:
                raise ApiProblem(409, "LOCAL_ARCHIVE_BUSY", str(exc)) from exc
            try:
                state = self._archive_store.read(item)
                if state is None:
                    raise ValueError("归档恢复记录不存在")
                if state["phase"] != "confirmed":
                    _plan(item, state)
                controller = LocalJobProcessController(archive_store=self._archive_store)
                controller.archive_claimed = True
                record = self._new_archive_record(item, controller)
                notices = ArchiveNoticeStore(self._archive_store)
                receipt = notices.begin(item, record.archive_operation_id)
                controller.archive_notice = (notices, receipt) if receipt is not None else None
                self._set_archive_state(item, "归档中", "", "", False)
                self._runs[item.item_id] = record
                selected = deepcopy(item)

                def run():
                    try:
                        def progress(phase, message, value, detail):
                            with self._lock:
                                record.phase, record.message, record.progress, record.detail = phase, message, value, detail
                        result = run_archive_only(selected, controller, progress)
                    except Exception as exc:
                        LOGGER.exception("Archive-only worker failed")
                        result = LocalJobExecutionResult(STATUS_COMPLETED, "计算已完成；归档待恢复", str(source), "",
                                                         archive_status="归档待恢复", archive_error=str(exc),
                                                         archive_recovery_available=True)
                    finally:
                        claim.__exit__(None, None, None)
                    self._store_result(selected, record, result)

                record.thread = threading.Thread(target=run, name="AbaqusArchiveRecovery", daemon=True)
                record.thread.start()
            except Exception as exc:
                LOGGER.exception("Unable to start archive-only recovery")
                claim.__exit__(None, None, None)
                if item.item_id in self._runs and self._runs[item.item_id].archive_only:
                    self._runs[item.item_id].finished_at = utc_now_text()
                self._set_archive_state(item, "归档待恢复", str(exc), "", True)
                raise ApiProblem(409, "ARCHIVE_RECOVERY_REFUSED", str(exc)) from exc
        self._wake.set()
