"""Transactional, Qt-free mutations for the local submitter queue."""

from __future__ import annotations

import os
import logging
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from modules.submitter.app_paths import JOBLIST_PATH
from modules.submitter.command import (
    derive_job_name,
    derive_oldjob_name,
    inp_has_restart_keyword,
    validate_job_name,
    validate_memory_argument,
    validate_options,
)
from modules.submitter.constants import (
    ACTIVE_STATUSES,
    STATUS_CANCELED,
    STATUS_DATACHECK_FAILED,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
    STATUS_PENDING_CONFIRM,
    STATUS_PENDING_RUN,
    STATUS_TERMINATED,
    STATUS_UNKNOWN,
    STATUS_WAITING_DEPENDENCY,
    TERMINAL_STATUSES,
)
from modules.submitter.external_job_scan_core import (
    collect_known_external_jobs,
    merge_external_scan_results,
    scan_external_jobs,
)
from modules.submitter.job_draft import LocalJobDraft
from modules.submitter.models import QueueItem
from modules.submitter.queue_scheduler import (
    effective_queue_item_work_dir,
    queue_item_conflict_key,
)
from modules.submitter.queue_store import load_joblist_state, save_joblist_state

from .contracts import SCHEMA_VERSION, ApiProblem
from .job_drafts import LocalJobDraftPreviewRequest
from modules.submitter.cpu_policy import validate_local_cpus
from .job_queues import project_job_queues

LOGGER = logging.getLogger(__name__)
ExternalJobScanner = Callable[[str, list[dict]], tuple[list[dict], list[int]]]

RESULT_EXTENSIONS = (".odb", ".sta", ".msg", ".dat", ".log")
EDITABLE_STATUSES = frozenset({STATUS_PENDING_RUN, STATUS_WAITING_DEPENDENCY})
REQUEUEABLE_STATUSES = frozenset(
    {
        STATUS_FAILED,
        STATUS_DATACHECK_FAILED,
        STATUS_CANCELED,
        STATUS_TERMINATED,
        STATUS_INTERRUPTED,
        STATUS_UNKNOWN,
    }
)
SUPPORTED_ACTIONS = frozenset(
    {
        "addCandidates",
        "scanCandidates",
        "scanExternalJobs",
        "setCandidateSelection",
        "invertCandidateSelection",
        "removeCandidates",
        "updateCandidate",
        "confirmCandidates",
        "enqueueDraft",
        "updateQueueItem",
        "setQueueHold",
        "requeueQueueItems",
        "removeQueueItems",
        "clearFinished",
        "moveQueueItem",
    }
)


def _normal_path(value: str) -> str:
    return os.path.normpath(os.path.abspath(value))


def _path_key(value: str) -> str:
    return os.path.normcase(_normal_path(value))


def _text(payload: Mapping[str, Any], name: str, default: str = "") -> str:
    value = payload.get(name, default)
    if not isinstance(value, str):
        raise ApiProblem(
            400,
            "INVALID_QUEUE_COMMAND_FIELD",
            f"{name} 必须是字符串",
            details={"field": name},
        )
    return value.strip()


def _flag(payload: Mapping[str, Any], name: str, default: bool = False) -> bool:
    value = payload.get(name, default)
    if not isinstance(value, bool):
        raise ApiProblem(
            400,
            "INVALID_QUEUE_COMMAND_FIELD",
            f"{name} 必须是布尔值",
            details={"field": name},
        )
    return value


def _integer(payload: Mapping[str, Any], name: str, default: int = 0) -> int:
    value = payload.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiProblem(
            400,
            "INVALID_QUEUE_COMMAND_FIELD",
            f"{name} 必须是整数",
            details={"field": name},
        )
    return value


def _string_list(
    payload: Mapping[str, Any],
    name: str,
    *,
    required: bool = True,
    limit: int = 2000,
    deduplicate: bool = True,
) -> list[str]:
    value = payload.get(name)
    if value is None and not required:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ApiProblem(
            400,
            "INVALID_QUEUE_COMMAND_FIELD",
            f"{name} 必须是字符串数组",
            details={"field": name},
        )
    cleaned = [item.strip() for item in value if item.strip()]
    if deduplicate:
        cleaned = list(dict.fromkeys(cleaned))
    if required and not cleaned:
        raise ApiProblem(
            400,
            "EMPTY_QUEUE_COMMAND_SELECTION",
            f"{name} 不能为空",
            details={"field": name},
        )
    if len(cleaned) > limit:
        raise ApiProblem(413, "QUEUE_COMMAND_TOO_LARGE", f"{name} 项目过多")
    return cleaned


def _require_fields(payload: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(payload) - {"schemaVersion", "action"} - allowed)
    if unknown:
        raise ApiProblem(
            400,
            "UNKNOWN_FIELDS",
            "队列命令包含 v1 协议不支持的字段",
            details={"fields": unknown},
        )


class JobQueueService:
    """Own safe queue-file transactions for one control-plane instance."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        external_job_scanner: ExternalJobScanner = scan_external_jobs,
        external_monitor_interval: float = 5.0,
    ) -> None:
        self.path = Path(path) if path is not None else Path(JOBLIST_PATH)
        self._lock = threading.RLock()
        self._external_job_scanner = external_job_scanner
        self._external_monitor_interval = max(0.05, float(external_monitor_interval))
        self._external_scan_roots: set[str] = set()
        self._external_monitor_closing = threading.Event()
        self._external_monitor = threading.Thread(
            target=self._external_monitor_loop,
            name="AbaqusExternalJobMonitor",
            daemon=True,
        )
        self._external_monitor.start()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            candidates, queue_items = self._load()
            return project_job_queues(candidates, queue_items)

    def runtime_transaction(self, mutation) -> Any:
        """Run one trusted runtime mutation inside the queue-file transaction."""

        with self._lock:
            candidates, queue_items = self._load()
            result = mutation(candidates, queue_items)
            save_joblist_state(candidates, queue_items, self.path)
            return result

    def runtime_items(self) -> tuple[list[QueueItem], list[QueueItem]]:
        """Return detached queue objects for the runtime dispatcher."""

        with self._lock:
            return self._load()

    def execute(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if payload.get("schemaVersion") != SCHEMA_VERSION:
            raise ApiProblem(
                400,
                "UNSUPPORTED_SCHEMA_VERSION",
                "不支持该队列命令结构版本",
                details={
                    "received": payload.get("schemaVersion"),
                    "supported": [SCHEMA_VERSION],
                },
            )
        action = _text(payload, "action")
        if action not in SUPPORTED_ACTIONS:
            raise ApiProblem(
                400,
                "UNSUPPORTED_QUEUE_ACTION",
                "不支持该队列操作",
                details={"action": action, "supported": sorted(SUPPORTED_ACTIONS)},
            )

        with self._lock:
            candidates, queue_items = self._load()
            changed, message, stats = self._dispatch(
                action,
                payload,
                candidates,
                queue_items,
            )
            if changed:
                save_joblist_state(candidates, queue_items, self.path)
            return {
                "schemaVersion": SCHEMA_VERSION,
                "action": action,
                "changed": changed,
                "message": message,
                "stats": stats,
                "snapshot": project_job_queues(candidates, queue_items),
            }

    def _load(self) -> tuple[list[QueueItem], list[QueueItem]]:
        candidates, queue_items, error = load_joblist_state(
            self.path,
            restore_active_state=False,
        )
        if error:
            raise ApiProblem(
                500,
                "JOB_QUEUE_STATE_UNREADABLE",
                "无法读取本地作业队列；为避免覆盖，未执行任何修改",
                details={"reason": error},
            )
        return candidates, queue_items

    def _dispatch(
        self,
        action: str,
        payload: Mapping[str, Any],
        candidates: list[QueueItem],
        queue_items: list[QueueItem],
    ) -> tuple[int, str, dict[str, Any]]:
        if action in {"addCandidates", "scanCandidates"}:
            return self._add_candidates(action, payload, candidates, queue_items)
        if action == "scanExternalJobs":
            return self._scan_external_jobs(payload, queue_items)
        if action == "setCandidateSelection":
            _require_fields(payload, {"itemIds", "selected"})
            return self._set_candidate_selection(payload, candidates)
        if action == "invertCandidateSelection":
            _require_fields(payload, set())
            for item in candidates:
                item.selected = not item.selected
            return len(candidates), "已反选全部候选作业", {}
        if action == "removeCandidates":
            _require_fields(payload, {"itemIds"})
            return self._remove_candidates(payload, candidates)
        if action == "updateCandidate":
            return self._update_candidate(payload, candidates, queue_items)
        if action == "confirmCandidates":
            _require_fields(payload, {"itemIds"})
            return self._confirm_candidates(payload, candidates, queue_items)
        if action == "enqueueDraft":
            _require_fields(payload, {"draft"})
            return self._enqueue_draft(payload, candidates, queue_items)
        if action == "updateQueueItem":
            return self._update_queue_item(payload, candidates, queue_items)
        if action == "setQueueHold":
            _require_fields(payload, {"itemIds", "held"})
            return self._set_queue_hold(payload, queue_items)
        if action == "requeueQueueItems":
            _require_fields(payload, {"itemIds"})
            return self._requeue(payload, queue_items)
        if action == "removeQueueItems":
            _require_fields(payload, {"itemIds"})
            return self._remove_queue_items(payload, queue_items)
        if action == "clearFinished":
            _require_fields(payload, set())
            previous = len(queue_items)
            queue_items[:] = [
                item for item in queue_items if item.status not in TERMINAL_STATUSES
            ]
            changed = previous - len(queue_items)
            return changed, f"已清理 {changed} 条完成或终止记录", {}
        if action == "moveQueueItem":
            _require_fields(payload, {"itemId", "direction"})
            return self._move_queue_item(payload, queue_items)
        raise AssertionError(f"unhandled queue action: {action}")

    def _scan_external_jobs(
        self,
        payload: Mapping[str, Any],
        queue_items: list[QueueItem],
    ) -> tuple[int, str, dict[str, Any]]:
        _require_fields(payload, {"root"})
        root = _normal_path(_text(payload, "root"))
        if not Path(root).is_dir():
            raise ApiProblem(
                400, "INVALID_EXTERNAL_SCAN_ROOT", "外部作业工作目录不存在或不可读"
            )
        self._external_scan_roots.add(os.path.normcase(root))
        return self._scan_external_roots(queue_items, [root])

    def _scan_external_roots(
        self,
        queue_items: list[QueueItem],
        roots: list[str],
    ) -> tuple[int, str, dict[str, Any]]:
        jobs_by_key: dict[tuple[str, str], dict] = {}
        skipped_pids: set[int] = set()
        for root in roots:
            known = collect_known_external_jobs(queue_items, root)
            jobs, skipped = self._external_job_scanner(root, known)
            skipped_pids.update(int(pid) for pid in skipped)
            for job in jobs:
                job_name = str(job.get("job_name") or "").strip()
                job_root = str(job.get("work_dir") or root).strip()
                if job_name and job_root:
                    jobs_by_key[
                        (os.path.normcase(_normal_path(job_root)), job_name.casefold())
                    ] = job
        merge = merge_external_scan_results(
            queue_items=queue_items,
            work_dir=roots[0],
            jobs=list(jobs_by_key.values()),
        )
        added = int(merge["added"])
        updated = int(merge["updated"])
        status_only = int(merge["status_only_updates"])
        scanned = len(jobs_by_key)
        changed = added + updated + status_only
        return (
            changed,
            f"外部作业扫描完成：发现 {scanned} 个，新增 {added} 个，更新 {updated + status_only} 个",
            {
                "scanned": scanned,
                "added": added,
                "updated": updated,
                "statusOnlyUpdates": status_only,
                "skippedPids": sorted(skipped_pids),
            },
        )

    def _external_monitor_loop(self) -> None:
        while not self._external_monitor_closing.wait(self._external_monitor_interval):
            try:
                self.refresh_external_jobs()
            except Exception:
                LOGGER.exception("External Abaqus job monitor refresh failed")

    def refresh_external_jobs(self) -> None:
        with self._lock:
            candidates, queue_items = self._load()
            roots = set(self._external_scan_roots)
            roots.update(
                os.path.normcase(
                    _normal_path(item.external_work_dir or item.effective_work_dir)
                )
                for item in queue_items
                if item.is_external
                and (item.external_work_dir or item.effective_work_dir)
            )
            valid_roots = sorted(root for root in roots if Path(root).is_dir())
            if not valid_roots:
                return
            before = project_job_queues(candidates, queue_items)
            self._scan_external_roots(queue_items, valid_roots)
            after = project_job_queues(candidates, queue_items)
            if before != after:
                save_joblist_state(candidates, queue_items, self.path)

    def close(self) -> None:
        self._external_monitor_closing.set()
        self._external_monitor.join(timeout=2)

    def _add_candidates(
        self,
        action: str,
        payload: Mapping[str, Any],
        candidates: list[QueueItem],
        queue_items: list[QueueItem],
    ) -> tuple[int, str, dict[str, Any]]:
        common = {"skipRestartNames", "skipExistingResults"}
        if action == "addCandidates":
            _require_fields(payload, common | {"paths", "source"})
            paths = _string_list(payload, "paths", deduplicate=False)
            source = _text(payload, "source", "文件") or "文件"
        else:
            _require_fields(payload, common | {"root", "recursive"})
            root = Path(_text(payload, "root"))
            if not root.is_dir():
                raise ApiProblem(400, "INVALID_SCAN_ROOT", "扫描目录不存在或不可读")
            recursive = _flag(payload, "recursive")
            pattern = "**/*.inp" if recursive else "*.inp"
            try:
                paths = [
                    str(path) for path in sorted(root.glob(pattern)) if path.is_file()
                ]
            except OSError as exc:
                raise ApiProblem(400, "SCAN_FAILED", "扫描 INP 目录失败") from exc
            if len(paths) > 2000:
                raise ApiProblem(
                    413, "SCAN_RESULT_TOO_LARGE", "单次扫描的 INP 文件超过 2000 个"
                )
            source = "文件夹"

        skip_restart = _flag(payload, "skipRestartNames")
        skip_existing = _flag(payload, "skipExistingResults")
        existing = {
            _path_key(item.inp_path)
            for item in candidates + queue_items
            if item.inp_path
        }
        stats: dict[str, int] = {
            "scanned": len(paths),
            "added": 0,
            "duplicate": 0,
            "restartName": 0,
            "existingResult": 0,
            "invalid": 0,
        }
        for raw_path in paths:
            normalized = _normal_path(raw_path)
            if (
                not normalized.lower().endswith(".inp")
                or not Path(normalized).is_file()
            ):
                stats["invalid"] += 1
                continue
            if skip_restart and "restart" in Path(normalized).name.lower():
                stats["restartName"] += 1
                continue
            if skip_existing and self._has_result_files(normalized):
                stats["existingResult"] += 1
                continue
            key = _path_key(normalized)
            if key in existing:
                stats["duplicate"] += 1
                continue
            item = QueueItem(
                inp_path=normalized,
                source_inp_path=normalized,
                job_name=derive_job_name(normalized),
                source=source,
                status=STATUS_PENDING_CONFIRM,
                selected=True,
                valid=True,
                message="可加入",
                job_type="普通",
            )
            self._validate_item(item, candidates, queue_items)
            candidates.append(item)
            existing.add(key)
            stats["added"] += 1
        return stats["added"], f"已新增 {stats['added']} 个候选作业", stats

    @staticmethod
    def _set_candidate_selection(
        payload: Mapping[str, Any],
        candidates: list[QueueItem],
    ) -> tuple[int, str, dict[str, Any]]:
        item_ids = set(_string_list(payload, "itemIds"))
        selected = _flag(payload, "selected")
        changed = 0
        for item in candidates:
            if item.item_id in item_ids and item.selected != selected:
                item.selected = selected
                changed += 1
        return changed, f"已更新 {changed} 个候选作业的选择状态", {}

    @staticmethod
    def _remove_candidates(
        payload: Mapping[str, Any],
        candidates: list[QueueItem],
    ) -> tuple[int, str, dict[str, Any]]:
        item_ids = set(_string_list(payload, "itemIds"))
        previous = len(candidates)
        candidates[:] = [item for item in candidates if item.item_id not in item_ids]
        changed = previous - len(candidates)
        return changed, f"已移除 {changed} 个候选作业", {}

    def _update_candidate(
        self,
        payload: Mapping[str, Any],
        candidates: list[QueueItem],
        queue_items: list[QueueItem],
    ) -> tuple[int, str, dict[str, Any]]:
        allowed = {
            "itemId",
            "jobName",
            "cores",
            "memory",
            "priority",
            "oldjobPath",
            "fortranPath",
            "calculationRootDir",
            "archiveDir",
        }
        _require_fields(payload, allowed)
        item = self._find_item(candidates, _text(payload, "itemId"), "候选作业")
        self._apply_edits(item, payload)
        self._validate_item(item, candidates, queue_items)
        return 1, "候选作业设置已更新", {}

    def _confirm_candidates(
        self,
        payload: Mapping[str, Any],
        candidates: list[QueueItem],
        queue_items: list[QueueItem],
    ) -> tuple[int, str, dict[str, Any]]:
        requested = set(_string_list(payload, "itemIds", required=False))
        selected = [
            item
            for item in candidates
            if item.item_id in requested or (not requested and item.selected)
        ]
        if not selected:
            raise ApiProblem(400, "NO_CANDIDATES_SELECTED", "没有可加入的候选作业")
        blocked: list[dict[str, str]] = []
        for item in selected:
            self._validate_item(item, candidates, queue_items)
            if item.run_mode == "restart" and not (
                item.oldjob_name or derive_oldjob_name(item.oldjob_path)
            ):
                item.valid = False
                item.message = "请先设置 Restart 前置 ODB"
            if not item.valid:
                blocked.append({"itemId": item.item_id, "message": item.message})
        if blocked:
            raise ApiProblem(
                409,
                "CANDIDATES_NOT_READY",
                "部分候选作业尚不能加入正式队列",
                details={"items": blocked},
            )

        selected_ids = {item.item_id for item in selected}
        existing_paths = {
            _path_key(item.inp_path) for item in queue_items if item.inp_path
        }
        added = 0
        for item in selected:
            if _path_key(item.inp_path) in existing_paths:
                continue
            item.source_inp_path = item.source_inp_path or item.inp_path
            item.effective_work_dir = effective_queue_item_work_dir(item)
            item.status = STATUS_PENDING_RUN
            item.message = "用户暂停调度" if item.held else "待提交"
            item.source = item.source or "候选"
            item.selected = False
            queue_items.append(item)
            existing_paths.add(_path_key(item.inp_path))
            added += 1
        candidates[:] = [
            item for item in candidates if item.item_id not in selected_ids
        ]
        return added, f"已将 {added} 个候选作业加入正式队列", {}

    def _enqueue_draft(
        self,
        payload: Mapping[str, Any],
        candidates: list[QueueItem],
        queue_items: list[QueueItem],
    ) -> tuple[int, str, dict[str, Any]]:
        raw_draft = payload.get("draft")
        if not isinstance(raw_draft, Mapping):
            raise ApiProblem(400, "INVALID_JOB_DRAFT", "draft 必须是 JSON 对象")
        draft = LocalJobDraftPreviewRequest.from_payload(raw_draft).draft
        self._validate_draft(draft)
        normalized = _normal_path(draft.inp_file)
        if any(
            item.inp_path and _path_key(item.inp_path) == _path_key(normalized)
            for item in candidates + queue_items
        ):
            raise ApiProblem(
                409, "DUPLICATE_JOB_INPUT", "该 INP 已存在于候选区或正式队列"
            )
        item = QueueItem(
            inp_path=normalized,
            source_inp_path=normalized,
            source="WinUI 单作业",
            status=STATUS_PENDING_RUN,
            selected=False,
            valid=True,
            message="待提交",
        )
        draft.apply_to_queue_item(item)
        item.job_type = "重启动" if item.run_mode == "restart" else "普通"
        item.effective_work_dir = effective_queue_item_work_dir(item)
        conflict = self._conflicting_item(item, candidates, queue_items)
        if conflict is not None:
            raise ApiProblem(
                409,
                "JOB_CONFLICT",
                "同一计算目录中已存在同名作业",
                details={"conflictingItemId": conflict.item_id},
            )
        queue_items.append(item)
        return 1, f"作业 {item.job_name} 已加入正式队列", {"itemId": item.item_id}

    def _update_queue_item(
        self,
        payload: Mapping[str, Any],
        candidates: list[QueueItem],
        queue_items: list[QueueItem],
    ) -> tuple[int, str, dict[str, Any]]:
        allowed = {
            "itemId",
            "jobName",
            "cores",
            "memory",
            "priority",
            "oldjobPath",
            "fortranPath",
            "calculationRootDir",
            "archiveDir",
        }
        _require_fields(payload, allowed)
        item = self._find_item(queue_items, _text(payload, "itemId"), "正式队列作业")
        self._require_editable(item)
        self._apply_edits(item, payload)
        self._validate_item(item, candidates, queue_items)
        if item.run_mode == "restart" and not item.oldjob_name:
            item.status = STATUS_WAITING_DEPENDENCY
            item.message = "未选择有效的 Restart 前置作业"
        else:
            item.status = STATUS_PENDING_RUN if item.valid else STATUS_FAILED
            item.message = (
                "用户暂停调度"
                if item.valid and item.held
                else ("待提交" if item.valid else item.message)
            )
        return 1, "正式队列作业设置已更新", {}

    @staticmethod
    def _set_queue_hold(
        payload: Mapping[str, Any],
        queue_items: list[QueueItem],
    ) -> tuple[int, str, dict[str, Any]]:
        item_ids = set(_string_list(payload, "itemIds"))
        held = _flag(payload, "held")
        selected = [item for item in queue_items if item.item_id in item_ids]
        blocked = [
            item.item_id for item in selected if item.status not in EDITABLE_STATUSES
        ]
        if blocked:
            raise ApiProblem(
                409,
                "QUEUE_ITEMS_NOT_EDITABLE",
                "只能暂停或恢复待运行和等待前置的作业",
                details={"itemIds": blocked},
            )
        changed = 0
        for item in selected:
            if item.held != held:
                item.held = held
                item.message = "用户暂停调度" if held else "待提交"
                changed += 1
        return changed, f"已{'暂停' if held else '恢复'} {changed} 个作业", {}

    @staticmethod
    def _requeue(
        payload: Mapping[str, Any],
        queue_items: list[QueueItem],
    ) -> tuple[int, str, dict[str, Any]]:
        item_ids = set(_string_list(payload, "itemIds"))
        selected = [item for item in queue_items if item.item_id in item_ids]
        blocked = [
            item.item_id for item in selected if item.status not in REQUEUEABLE_STATUSES
        ]
        if blocked:
            raise ApiProblem(
                409,
                "QUEUE_ITEMS_NOT_REQUEUEABLE",
                "所选作业中包含不能重新排队的状态",
                details={"itemIds": blocked},
            )
        for item in selected:
            item.status = STATUS_PENDING_RUN
            item.scheduler_state = ""
            item.pending_reason = ""
            item.active_job_key = ""
            item.pids = []
            item.pid_create_times = {}
            item.rss_bytes = 0
            item.message = "用户暂停调度" if item.held else "待提交"
        return len(selected), f"已重新排队 {len(selected)} 个作业", {}

    @staticmethod
    def _remove_queue_items(
        payload: Mapping[str, Any],
        queue_items: list[QueueItem],
    ) -> tuple[int, str, dict[str, Any]]:
        item_ids = set(_string_list(payload, "itemIds"))
        selected = [item for item in queue_items if item.item_id in item_ids]
        blocked = [item.item_id for item in selected if item.status in ACTIVE_STATUSES]
        if blocked:
            raise ApiProblem(
                409,
                "ACTIVE_QUEUE_ITEMS_PROTECTED",
                "运行中的作业不能从队列删除，请先终止作业",
                details={"itemIds": blocked},
            )
        previous = len(queue_items)
        queue_items[:] = [item for item in queue_items if item.item_id not in item_ids]
        changed = previous - len(queue_items)
        return changed, f"已移除 {changed} 个正式队列作业", {}

    @staticmethod
    def _move_queue_item(
        payload: Mapping[str, Any],
        queue_items: list[QueueItem],
    ) -> tuple[int, str, dict[str, Any]]:
        item_id = _text(payload, "itemId")
        direction = _text(payload, "direction")
        if direction not in {"up", "down"}:
            raise ApiProblem(
                400, "INVALID_MOVE_DIRECTION", "direction 必须是 up 或 down"
            )
        index = next(
            (
                position
                for position, item in enumerate(queue_items)
                if item.item_id == item_id
            ),
            None,
        )
        if index is None:
            raise ApiProblem(404, "QUEUE_ITEM_NOT_FOUND", "未找到正式队列作业")
        item = queue_items[index]
        if item.status in ACTIVE_STATUSES:
            raise ApiProblem(
                409, "ACTIVE_QUEUE_ITEMS_PROTECTED", "运行中的作业不能重新排序"
            )
        target = index - 1 if direction == "up" else index + 1
        if target < 0 or target >= len(queue_items):
            return 0, "作业已位于队列边界", {}
        queue_items[index], queue_items[target] = (
            queue_items[target],
            queue_items[index],
        )
        return 1, "队列顺序已更新", {}

    @staticmethod
    def _find_item(items: list[QueueItem], item_id: str, label: str) -> QueueItem:
        for item in items:
            if item.item_id == item_id:
                return item
        raise ApiProblem(404, "QUEUE_ITEM_NOT_FOUND", f"未找到{label}")

    @staticmethod
    def _require_editable(item: QueueItem) -> None:
        if item.status not in EDITABLE_STATUSES:
            raise ApiProblem(409, "QUEUE_ITEM_NOT_EDITABLE", "当前状态不允许编辑该作业")

    def _apply_edits(self, item: QueueItem, payload: Mapping[str, Any]) -> None:
        if "jobName" in payload:
            item.job_name = _text(payload, "jobName")
        if "cores" in payload:
            cores = _integer(payload, "cores")
            try:
                validate_local_cpus(cores, item.abaqus_command)
            except ValueError as exc:
                raise ApiProblem(400, "INVALID_CPUS", str(exc)) from exc
            item.cores = cores
        if "memory" in payload:
            memory = _text(payload, "memory")
            valid, message = validate_memory_argument(memory)
            if not valid:
                raise ApiProblem(400, "INVALID_MEMORY", message)
            item.memory = memory
        if "priority" in payload:
            priority = _integer(payload, "priority")
            if not -10000 <= priority <= 10000:
                raise ApiProblem(400, "INVALID_PRIORITY", "priority 超出允许范围")
            item.priority = priority
        if "oldjobPath" in payload:
            item.oldjob_path = _text(payload, "oldjobPath")
            item.oldjob_name = derive_oldjob_name(item.oldjob_path)
            item.oldjob_dir = (
                str(Path(item.oldjob_path).parent) if item.oldjob_path else ""
            )
        if "fortranPath" in payload:
            item.fortran_path = _text(payload, "fortranPath")
        if "calculationRootDir" in payload:
            item.calculation_root_dir = _text(payload, "calculationRootDir")
        if "archiveDir" in payload:
            item.archive_dir = _text(payload, "archiveDir")
        item.archive_after_complete = bool(item.archive_dir)
        item.cleanup_after_archive = bool(
            item.calculation_root_dir and item.archive_dir
        )
        item.effective_work_dir = effective_queue_item_work_dir(item)

    def _validate_item(
        self,
        item: QueueItem,
        candidates: list[QueueItem],
        queue_items: list[QueueItem],
    ) -> None:
        item.run_mode = (
            "restart"
            if inp_has_restart_keyword(item.inp_path)
            else ("restart" if item.oldjob_path else "normal")
        )
        item.job_type = "重启动" if item.run_mode == "restart" else "普通"
        if not Path(item.inp_path).is_file():
            item.valid = False
            item.message = "INP 文件不存在"
            return
        try:
            validate_local_cpus(item.cores, item.abaqus_command)
        except ValueError as exc:
            item.valid = False
            item.message = str(exc)
            return
        valid, message = validate_job_name(item.job_name)
        if not valid:
            item.valid = False
            item.message = f"作业名不合法：{message}"
            return
        if item.fortran_path and not Path(item.fortran_path).is_file():
            item.valid = False
            item.message = "FOR 文件不存在"
            return
        for label, value in (
            ("SSD 工作目录", item.calculation_root_dir),
            ("结果归档目录", item.archive_dir),
        ):
            if value and not Path(value).is_dir():
                item.valid = False
                item.message = f"{label}不存在或不是文件夹"
                return
        oldjob_name = item.oldjob_name or derive_oldjob_name(item.oldjob_path)
        item.oldjob_name = oldjob_name
        if oldjob_name:
            valid, message = validate_job_name(oldjob_name)
            if not valid or oldjob_name.casefold() == item.job_name.casefold():
                item.valid = False
                item.message = "Restart 依赖作业名无效"
                return
        conflict = self._conflicting_item(item, candidates, queue_items)
        if conflict is not None:
            item.valid = False
            item.message = f"同一计算目录中已存在同名作业：{conflict.job_name}"
            return
        item.valid = True
        item.message = (
            "确认加入前设置 Restart 依赖"
            if item.run_mode == "restart" and not oldjob_name
            else "可加入"
        )

    @staticmethod
    def _conflicting_item(
        item: QueueItem,
        candidates: list[QueueItem],
        queue_items: list[QueueItem],
    ) -> QueueItem | None:
        key = queue_item_conflict_key(item)
        if not key[0] or not key[1]:
            return None
        queue_ids = {entry.item_id for entry in queue_items}
        for other in candidates + queue_items:
            if other.item_id == item.item_id:
                continue
            if other.item_id in queue_ids and other.status in TERMINAL_STATUSES:
                continue
            if queue_item_conflict_key(other) == key:
                return other
        return None

    @staticmethod
    def _validate_draft(draft: LocalJobDraft) -> None:
        valid, message = validate_options(draft.to_submit_options())
        if valid:
            valid, message = draft.validate_local_paths()
        if valid and draft.fortran_path and not Path(draft.fortran_path).is_file():
            valid, message = False, "Fortran 用户子程序不存在。"
        if not valid:
            raise ApiProblem(400, "INVALID_JOB_DRAFT", message)

    @staticmethod
    def _has_result_files(inp_path: str) -> bool:
        base = Path(inp_path).with_suffix("")
        return any(
            base.with_suffix(extension).exists() for extension in RESULT_EXTENSIONS
        )


__all__ = ["SUPPORTED_ACTIONS", "JobQueueService"]
