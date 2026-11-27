"""Transactional, Qt-free mutations for the local submitter queue."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

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
from modules.submitter.cpu_policy import validate_local_cpus
from modules.submitter.execution_options import (
    parse_execution_options,
    validate_execution_options,
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
from modules.submitter.restart_dependency import RestartDependencyLifecycle
from modules.submitter.restart_topology import (
    RestartTopology,
    legacy_restart_edit_failure,
)

from .contracts import SCHEMA_VERSION, ApiProblem
from .job_drafts import LocalJobDraftPreviewRequest
from .job_queues import project_job_queues

LOGGER = logging.getLogger(__name__)
ExternalJobScanner = Callable[[str, list[dict]], tuple[list[dict], list[int]]]

RESULT_EXTENSIONS = (".odb", ".sta", ".msg", ".dat", ".log")
DIRECTORY_FIELDS = {"calculationRootDir", "archiveDir", "cleanupAfterArchive"}
EDITABLE_STATUSES = frozenset({STATUS_PENDING_RUN, STATUS_WAITING_DEPENDENCY})
REQUEUEABLE_STATUSES = frozenset(
    {
        STATUS_FAILED,
        STATUS_DATACHECK_FAILED,
        STATUS_CANCELED,
        STATUS_TERMINATED,
        STATUS_INTERRUPTED,
        STATUS_PENDING_CONFIRM,
    }
)
SUPPORTED_ACTIONS = frozenset(
    {
        "addCandidates",
        "scanCandidates",
        "scanExternalJobs",
        "setCandidateSelection",
        "setCandidateDirectories",
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


def _directory_edits(payload: Mapping[str, Any]) -> tuple[str | None, str | None, bool | None]:
    def read_folder(key: str, label: str) -> str | None:
        if key not in payload:
            return None
        value = _text(payload, key)
        try:
            valid = not value or (Path(value).is_absolute() and Path(value).is_dir())
        except (ValueError, OSError):
            valid = False
        if not valid:
            raise ApiProblem(400, "INVALID_QUEUE_DIRECTORY", f"{label}须为已存在的文件夹绝对路径",
                             details={"field": key})
        return value

    return (read_folder("calculationRootDir", "计算根目录"), read_folder("archiveDir", "归档根目录"),
            _flag(payload, "cleanupAfterArchive") if "cleanupAfterArchive" in payload else None)


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
        self._external_scan_lock = threading.Lock()
        self._external_manual_scan_active = False
        self._external_job_scanner = external_job_scanner
        self._external_monitor_interval = max(0.05, float(external_monitor_interval))
        self._external_scan_roots: set[str] = set()
        self._recovered_scan_roots: set[str] = set()
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
            return self._project(candidates, queue_items)

    def _project(self, candidates, items, *, scan_active=None):
        snapshot = project_job_queues(candidates, items)
        snapshot["externalScanActive"] = self._external_scan_lock.locked() if scan_active is None else scan_active
        snapshot["externalManualScanActive"] = self._external_manual_scan_active if scan_active is None else False
        return snapshot

    def runtime_transaction(self, mutation) -> Any:
        """Run one trusted runtime mutation inside the queue-file transaction."""

        with self._lock:
            candidates, queue_items = self._load()
            before = ([asdict(item) for item in candidates], [asdict(item) for item in queue_items])
            result = mutation(candidates, queue_items)
            after = ([asdict(item) for item in candidates], [asdict(item) for item in queue_items])
            if before != after:
                save_joblist_state(candidates, queue_items, self.path)
            return result

    def observe_recovered_directories(self, directories):
        with self._lock:
            self._recovered_scan_roots.update(os.path.normcase(_normal_path(root)) for root in directories if root)

    def runtime_items(self) -> tuple[list[QueueItem], list[QueueItem]]:
        """Return detached queue objects for the runtime dispatcher."""

        with self._lock:
            return self._load()

    def execute(self, payload: Mapping[str, Any], *, scheduling=False) -> dict[str, Any]:
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

        if action == "scanExternalJobs":
            return self._scan_external_jobs(payload)

        with self._lock:
            candidates, queue_items = self._load()
            changed, message, stats = self._dispatch(
                action,
                payload,
                candidates,
                queue_items,
                scheduling=scheduling,
            )
            if changed:
                save_joblist_state(candidates, queue_items, self.path)
            return {
                "schemaVersion": SCHEMA_VERSION,
                "action": action,
                "changed": changed,
                "message": message,
                "stats": stats,
                "snapshot": self._project(candidates, queue_items),
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
        *, scheduling=False,
    ) -> tuple[int, str, dict[str, Any]]:
        if action in {"updateQueueItem", "requeueQueueItems", "removeQueueItems", "moveQueueItem", "clearFinished"}:
            requested = {value for value in payload.get("itemIds", []) if isinstance(value, str)} if isinstance(payload.get("itemIds", []), list) else set()
            if isinstance(payload.get("itemId"), str):
                requested.add(payload["itemId"])
            if any(item.archive_status == "归档中" and (action == "clearFinished" or item.item_id in requested)
                   for item in queue_items):
                raise ApiProblem(409, "ACTIVE_ARCHIVE_PROTECTED", "归档正在执行，请先取消并等待归档收尾")
        if action in {"addCandidates", "scanCandidates"}:
            return self._add_candidates(action, payload, candidates, queue_items)
        if action == "setCandidateSelection":
            _require_fields(payload, {"itemIds", "selected"})
            return self._set_candidate_selection(payload, candidates)
        if action == "setCandidateDirectories":
            return self._set_candidate_directories(payload, candidates, queue_items)
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
            return self._update_queue_item(payload, candidates, queue_items, scheduling=scheduling)
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
                item for item in queue_items if item.status not in TERMINAL_STATUSES or item.status == STATUS_UNKNOWN
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
    ) -> dict[str, Any]:
        _require_fields(payload, {"root"})
        root = _normal_path(_text(payload, "root"))
        if not Path(root).is_dir():
            raise ApiProblem(
                400, "INVALID_EXTERNAL_SCAN_ROOT", "外部作业工作目录不存在或不可读"
            )
        return self._run_external_scan([root])

    def _run_external_scan(self, requested_roots=None):
        manual = requested_roots is not None
        if not self._external_scan_lock.acquire(blocking=False):
            if manual:
                raise ApiProblem(409, "EXTERNAL_SCAN_BUSY", "已有外部作业扫描正在进行，请稍后刷新")
            return None
        try:
            with self._lock:
                self._external_manual_scan_active = manual
                if self._external_monitor_closing.is_set():
                    if manual:
                        raise ApiProblem(503, "CONTROL_PLANE_SHUTTING_DOWN", "后台正在关闭，未开始扫描")
                    return None
                _, scanned_items = self._load()
                before = {item.item_id: asdict(item) for item in scanned_items}
                if manual:
                    self._external_scan_roots.update(os.path.normcase(root) for root in requested_roots)
                    roots = requested_roots
                else:
                    roots = set(self._external_scan_roots)
                    unresolved_roots = {
                        os.path.normcase(_normal_path(item.external_work_dir or item.effective_work_dir))
                        for item in scanned_items if item.status in ACTIVE_STATUSES | {STATUS_UNKNOWN}
                        and (item.external_work_dir or item.effective_work_dir)
                    }
                    roots.update(self._recovered_scan_roots & unresolved_roots)
                    roots.update(os.path.normcase(_normal_path(item.external_work_dir or item.effective_work_dir))
                                 for item in scanned_items if item.is_external
                                 and (item.external_work_dir or item.effective_work_dir))
            # Directory checks, process inspection, diagnostics and detached merge
            # must not hold the queue lock used by reads, edits or execution.
            roots = sorted(root for root in roots if Path(root).is_dir())
            if not roots:
                if manual:
                    raise ApiProblem(400, "INVALID_EXTERNAL_SCAN_ROOT", "扫描目录已不可读，未更新队列")
                return None
            stats, kinds = self._scan_external_roots(scanned_items, roots)
            with self._lock:
                if self._external_monitor_closing.is_set():
                    if manual:
                        raise ApiProblem(503, "CONTROL_PLANE_SHUTTING_DOWN", "后台正在关闭，未合并扫描结果")
                    return None
                candidates, current = self._load()
                positions = {item.item_id: index for index, item in enumerate(current)}
                keys = {queue_item_conflict_key(item) for item in current}
                applied = {"added": 0, "updated": 0, "statusOnlyUpdates": 0}
                stale = 0
                for observed in scanned_items:
                    baseline = before.get(observed.item_id)
                    if baseline is not None:
                        if asdict(observed) == baseline:
                            continue
                        index = positions.get(observed.item_id)
                        if (index is None or asdict(current[index]) != baseline
                                or current[index].active_job_key or current[index].archive_status == "归档中"):
                            stale += 1
                            continue
                        current[index] = observed
                        applied[kinds.get(queue_item_conflict_key(observed), "statusOnlyUpdates")] += 1
                    elif observed.item_id in positions or queue_item_conflict_key(observed) in keys:
                        stale += 1
                    else:
                        current.append(observed)
                        positions[observed.item_id] = len(current) - 1
                        keys.add(queue_item_conflict_key(observed))
                        applied["added"] += 1
                changed = sum(applied.values())
                if changed:
                    save_joblist_state(candidates, current, self.path)
                stats.update(applied)
                message = f"外部作业扫描完成：发现 {stats['scanned']} 个，新增 {applied['added']} 个，更新 {applied['updated'] + applied['statusOnlyUpdates']} 个"
                if stale:
                    stats["staleResultsSkipped"] = stale
                    message += f"；{stale} 条记录已变化或由本机执行器管理，未覆盖，请稍后刷新"
                return {"schemaVersion": SCHEMA_VERSION, "action": "scanExternalJobs", "changed": changed,
                        "message": message, "stats": stats, "snapshot": self._project(candidates, current, scan_active=False)}
        finally:
            with self._lock:
                self._external_manual_scan_active = False
                self._external_scan_lock.release()

    def _scan_external_roots(
        self,
        queue_items: list[QueueItem],
        roots: list[str],
    ) -> tuple[dict[str, Any], dict[tuple[str, str], str]]:
        jobs_by_key: dict[tuple[str, str], dict] = {}
        skipped_pids: set[int] = set()
        if self._external_job_scanner is scan_external_jobs:
            known = {entry["item_id"]: entry for root in roots for entry in collect_known_external_jobs(queue_items, root)}
            batches = [(roots[0], self._external_job_scanner(roots[0], list(known.values()), additional_roots=roots[1:]))]
        else:
            batches = [(root, self._external_job_scanner(root, collect_known_external_jobs(queue_items, root))) for root in roots]
        for root, (jobs, skipped) in batches:
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
        for record in merge.get("memory_records", []):
            item, job = record["item"], record["job"]
            item.memory_observed_at = time.time()
            if item.status not in ACTIVE_STATUSES:
                item.memory_observation_status = "ended"
                item.rss_bytes = 0
            elif int(job.get("rss_bytes") or 0) > 0 and item.pids and all(
                float(item.pid_create_times.get(str(pid)) or 0) > 0 for pid in item.pids
            ):
                item.memory_observation_status = "observed"
            else:
                item.memory_observation_status = "unavailable"
        return ({"scanned": len(jobs_by_key), "skippedPids": sorted(skipped_pids)},
                {key: "statusOnlyUpdates" if job.get("status_only_update") else "updated" for key, job in jobs_by_key.items()})

    def _external_monitor_loop(self) -> None:
        while not self._external_monitor_closing.wait(self._external_monitor_interval):
            try:
                self.refresh_external_jobs()
            except Exception:
                LOGGER.exception("External Abaqus job monitor refresh failed")

    def refresh_external_jobs(self) -> None:
        self._run_external_scan()

    def close(self) -> None:
        with self._lock:
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

    def _set_candidate_directories(
        self, payload: Mapping[str, Any], candidates: list[QueueItem], queue_items: list[QueueItem],
    ) -> tuple[int, str, dict[str, Any]]:
        _require_fields(payload, {"itemIds"} | DIRECTORY_FIELDS)
        item_ids = set(_string_list(payload, "itemIds"))
        if any(not value.strip() for value in payload["itemIds"]):
            raise ApiProblem(400, "INVALID_QUEUE_COMMAND_FIELD", "所选候选作业标识不能为空")
        if not DIRECTORY_FIELDS.intersection(payload):
            raise ApiProblem(400, "EMPTY_DIRECTORY_EDIT", "请选择需要修改的目录或清理设置")
        selected = [item for item in candidates if item.item_id in item_ids]
        missing = sorted(item_ids.difference(item.item_id for item in selected))
        if missing:
            raise ApiProblem(404, "QUEUE_ITEM_NOT_FOUND", "部分候选作业已不存在，请刷新后重新选择",
                             details={"itemIds": missing})
        edits = _directory_edits(payload)
        changed = []
        for item in selected:
            if self._apply_directory_edits(item, *edits):
                changed.append(item)
        # Check final paths together, including collisions between two items in this very edit.
        by_location: dict[tuple[str, str], QueueItem] = {}
        for item in [*candidates, *(job for job in queue_items if job.status not in TERMINAL_STATUSES)]:
            key = queue_item_conflict_key(item)
            if not all(key):
                continue
            other = by_location.get(key)
            if other is not None and (item.item_id in item_ids or other.item_id in item_ids):
                raise ApiProblem(409, "QUEUE_DIRECTORY_CONFLICT", f"同一计算目录中存在同名作业：{item.job_name}",
                                 details={"itemIds": [other.item_id, item.item_id], "workDir": key[0]})
            by_location[key] = item
        for item in changed:
            self._validate_item(item, candidates, queue_items, check_conflicts=False)
        return len(changed), f"已更新 {len(changed)} 个候选作业的目录设置", {}

    def _update_candidate(
        self,
        payload: Mapping[str, Any],
        candidates: list[QueueItem],
        queue_items: list[QueueItem],
    ) -> tuple[int, str, dict[str, Any]]:
        allowed = {
            "itemId",
            "jobName",
            "cores", "gpuCount", "explicitPrecision", "outputPrecision",
            "memory",
            "priority",
            "oldjobPath",
            "fortranPath",
        } | DIRECTORY_FIELDS
        _require_fields(payload, allowed)
        item = self._find_item(candidates, _text(payload, "itemId"), "候选作业")
        self._apply_edits(item, payload)
        if "calculationRootDir" in payload and self._conflicting_item(item, candidates, queue_items):
            raise ApiProblem(409, "QUEUE_DIRECTORY_CONFLICT", f"同一计算目录中存在同名作业：{item.job_name}")
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
        added: list[QueueItem] = []
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
            added.append(item)
        candidates[:] = [
            item for item in candidates if item.item_id not in selected_ids
        ]
        restart_items = [item for item in added if item.run_mode == "restart" or item.dependency_job_ids]
        if restart_items:
            topology = RestartTopology(queue_items)
            for item in restart_items:
                self._require_valid_dependency(topology, item)
        return len(added), f"已将 {len(added)} 个候选作业加入正式队列", {}

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
        if item.run_mode == "restart":
            self._require_valid_dependency(RestartTopology(queue_items), item)
        return 1, f"作业 {item.job_name} 已加入正式队列", {"itemId": item.item_id}

    def _update_queue_item(
        self,
        payload: Mapping[str, Any],
        candidates: list[QueueItem],
        queue_items: list[QueueItem],
        *, scheduling=False,
    ) -> tuple[int, str, dict[str, Any]]:
        allowed = {
            "itemId",
            "jobName",
            "cores", "gpuCount", "explicitPrecision", "outputPrecision",
            "memory",
            "priority",
            "oldjobPath",
            "fortranPath",
        } | DIRECTORY_FIELDS
        _require_fields(payload, allowed)
        item = self._find_item(queue_items, _text(payload, "itemId"), "正式队列作业")
        before = asdict(item)
        repair = legacy_restart_edit_failure(item)
        if not repair and item.status not in EDITABLE_STATUSES:
            raise ApiProblem(409, "QUEUE_ITEM_NOT_EDITABLE", "当前状态不允许编辑该作业")
        relocated = any(field in payload and _text(payload, field) != getattr(item, attr)
                        for field, attr in (("jobName", "job_name"), ("calculationRootDir", "calculation_root_dir")))
        dependency_only = "oldjobPath" in payload and set(payload) <= {"schemaVersion", "action", "itemId", "oldjobPath"}
        reselect = dependency_only and item.dependency_job_ids and _text(payload, "oldjobPath") == item.oldjob_path
        prior_topology = RestartTopology(queue_items) if relocated or reselect else None
        if reselect and item.job_id in prior_topology.issues:
            item.dependency_job_ids = []
            RestartDependencyLifecycle.clear_queue_item(item)
        self._apply_edits(item, payload)
        dependency_changed = relocated or any(getattr(item, key) != before[key] for key in (
            "oldjob_name", "oldjob_path", "dependency_job_ids"))
        if scheduling and (dependency_changed or repair):
            raise ApiProblem(409, "RESTART_EDIT_DURING_DISPATCH", "请先停止队列调度，再修改重启动依赖")
        if repair and ("oldjobPath" not in payload or item.oldjob_path == before["oldjob_path"]
                       or any(getattr(item, key) != before[key] for key in (
                           "job_name", "cores", "gpu_count", "explicit_precision", "output_precision",
                           "memory", "priority", "fortran_path", "calculation_root_dir", "archive_dir",
                           "archive_after_complete", "cleanup_after_archive"))):
            raise ApiProblem(409, "QUEUE_ITEM_NOT_EDITABLE", "该历史记录仅允许纠正前置作业 ODB")
        if dependency_changed or repair or dependency_only:
            topology = RestartTopology(queue_items)
            self._require_valid_dependency(topology, item, allow_unassigned=True)
            if relocated:
                for child, parent in prior_topology.parents.items():
                    if parent == item.job_id and child != parent:
                        self._require_valid_dependency(topology, topology.by_id[child])
        self._validate_item(item, candidates, queue_items)
        if not item.valid:
            raise ApiProblem(400, "INVALID_QUEUE_ITEM_EDIT", item.message)
        if repair:
            item.scheduler_state = "PENDING"
            item.pending_reason = ""
        if item.run_mode == "restart" and not item.oldjob_name:
            item.status = STATUS_WAITING_DEPENDENCY
            item.message = "未选择有效的 Restart 前置作业"
        else:
            item.status = STATUS_PENDING_RUN
            item.message = "用户暂停调度" if item.held else "待提交"
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
                "所选作业中包含不能重新排队的状态；状态未知的原作业请先扫描核对",
                details={"itemIds": blocked},
            )
        restart_items = [item for item in selected if item.run_mode == "restart" or item.dependency_job_ids]
        if restart_items:
            topology = RestartTopology(queue_items)
            for item in restart_items:
                JobQueueService._require_valid_dependency(topology, item)
        for item in selected:
            item.status = STATUS_PENDING_RUN
            item.scheduler_state = ""
            item.pending_reason = ""
            item.attempt_id = ""
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
        blocked = [item.item_id for item in selected if item.status in ACTIVE_STATUSES | {STATUS_UNKNOWN}]
        if blocked:
            raise ApiProblem(
                409,
                "ACTIVE_QUEUE_ITEMS_PROTECTED",
                "运行中或状态未知的作业不能删除，请先停止作业或扫描核对状态",
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
    def _require_valid_dependency(topology: RestartTopology, item: QueueItem, *, allow_unassigned=False) -> None:
        issue = topology.edit_issue(item, allow_unassigned=allow_unassigned)
        if issue:
            raise ApiProblem(409, "INVALID_RESTART_DEPENDENCY", issue, details={"itemId": item.item_id})

    def _apply_edits(self, item: QueueItem, payload: Mapping[str, Any]) -> None:
        previous_name = item.job_name
        try:
            execution = parse_execution_options({"gpuCount": item.gpu_count,
                "explicitPrecision": item.explicit_precision, "outputPrecision": item.output_precision, **payload})
        except ValueError as exc:
            raise ApiProblem(400, "INVALID_EXECUTION_OPTIONS", str(exc)) from exc
        item.gpu_count, item.explicit_precision, item.output_precision = (
            execution.gpu_count, execution.explicit_precision, execution.output_precision)
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
        if "oldjobPath" in payload and (_text(payload, "oldjobPath") != item.oldjob_path or (
            not item.oldjob_path and set(payload) <= {"schemaVersion", "action", "itemId", "oldjobPath"}
        )):
            item.dependency_job_ids = []
            RestartDependencyLifecycle.clear_queue_item(item)
            item.oldjob_path = _text(payload, "oldjobPath")
            item.oldjob_name = derive_oldjob_name(item.oldjob_path)
            item.oldjob_dir = (
                str(Path(item.oldjob_path).parent) if item.oldjob_path else ""
            )
        if "fortranPath" in payload:
            item.fortran_path = _text(payload, "fortranPath")
        self._apply_directory_edits(item, *_directory_edits(payload), renamed=item.job_name != previous_name)
        if not item.effective_work_dir:
            item.effective_work_dir = effective_queue_item_work_dir(item)

    @staticmethod
    def _apply_directory_edits(item: QueueItem, root: str | None, archive: str | None, cleanup: bool | None,
                               *, renamed: bool = False) -> bool:
        previous_archive_enabled = item.archive_after_complete
        previous_cleanup = item.cleanup_after_archive
        moved = root is not None and root != item.calculation_root_dir
        archive_changed = archive is not None and archive != item.archive_dir
        if root is not None:
            item.calculation_root_dir = root
        if archive is not None:
            item.archive_dir = archive
            if archive_changed or not archive:
                item.archive_after_complete = bool(archive)
        if moved or renamed:
            item.effective_work_dir = ""
            item.effective_work_dir = effective_queue_item_work_dir(item)
        if cleanup is not None:
            item.cleanup_after_archive = cleanup
        elif root == "" or archive == "":
            item.cleanup_after_archive = False
        check_cleanup = item.cleanup_after_archive and (cleanup is not None or moved or renamed or archive_changed)
        if check_cleanup and not (item.calculation_root_dir and item.archive_dir and item.archive_after_complete):
            raise ApiProblem(400, "INVALID_QUEUE_CLEANUP", f"{item.job_name}：清理须同时设置独立计算目录并启用归档")
        if item.archive_dir and (moved or renamed or archive_changed or check_cleanup):
            try:
                if check_cleanup and not (Path(item.calculation_root_dir).is_dir() and Path(item.archive_dir).is_dir()):
                    raise ApiProblem(400, "INVALID_QUEUE_DIRECTORY", f"{item.job_name}：清理需要已存在的计算和归档根目录")
                work = Path(effective_queue_item_work_dir(item)).resolve()
                if Path(item.archive_dir).resolve().is_relative_to(work):
                    raise ApiProblem(400, "INVALID_QUEUE_DIRECTORY", f"{item.job_name}：归档根目录不能位于作业计算目录内")
                if check_cleanup and (work != Path(item.calculation_root_dir).resolve() / item.job_name or
                                      Path(item.source_inp_path or item.inp_path).resolve().is_relative_to(work)):
                    raise ApiProblem(400, "INVALID_QUEUE_CLEANUP", f"{item.job_name}：仅可清理独立作业目录，原始 INP 所在目录须保留")
            except (OSError, RuntimeError, ValueError) as exc:
                raise ApiProblem(400, "INVALID_QUEUE_DIRECTORY", "无法解析计算或归档目录") from exc
        changed = (moved or archive_changed or item.cleanup_after_archive != previous_cleanup
                   or item.archive_after_complete != previous_archive_enabled)
        if changed and not item.effective_work_dir:
            item.effective_work_dir = effective_queue_item_work_dir(item)
        return changed

    def _validate_item(
        self,
        item: QueueItem,
        candidates: list[QueueItem],
        queue_items: list[QueueItem],
        *, check_conflicts: bool = True,
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
            validate_execution_options(item)
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
        conflict = self._conflicting_item(item, candidates, queue_items) if check_conflicts else None
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
