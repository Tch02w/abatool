"""Qt-free external Abaqus job discovery and queue merge helpers."""

from __future__ import annotations

import os

from .abaqus_diagnostics import inspect_job_files
from .constants import (
    ACTIVE_STATUSES,
    STATUS_PENDING_CONFIRM,
    STATUS_UNKNOWN,
    TERMINAL_STATUSES,
)
from .models import QueueItem
from .process_scanner import (
    EXTERNAL_SCAN_MAX_CHILD_DEPTH,
    classify_external_job_runtime,
    fetch_psutil_process_rows_for_external_scan,
    normalize_work_dir,
    scan_running_abaqus_jobs_by_psutil,
    work_dir_matches_scan_root,
)
from .queue_scheduler import (
    effective_queue_item_work_dir,
    managed_job_key,
    queue_item_conflict_key,
)


def collect_known_external_jobs(
    queue_items: list[QueueItem],
    work_dir: str,
) -> list[dict]:
    jobs = []
    for item in queue_items:
        if (
            not item.is_external
            and item.status not in ACTIVE_STATUSES
            and item.status != STATUS_UNKNOWN
        ):
            continue
        item_work_dir = effective_queue_item_work_dir(item)
        if not item_work_dir:
            continue
        if not item.is_external and item.status == STATUS_UNKNOWN:
            pass
        elif not work_dir_matches_scan_root(
            item_work_dir,
            work_dir,
            EXTERNAL_SCAN_MAX_CHILD_DEPTH,
        ):
            continue
        jobs.append(
            {
                "item_id": item.item_id,
                "job_name": item.job_name,
                "work_dir": item_work_dir,
                "inp_path": item.inp_path,
                "is_external": bool(item.is_external),
            }
        )
    return jobs


def build_queue_item_index(
    queue_items: list[QueueItem],
) -> dict[tuple[str, str], QueueItem]:
    index = {}
    for item in queue_items:
        key = queue_item_conflict_key(item)
        if key[0]:
            index[key] = item
    return index


def resolve_unmatched_restored_unknown_items(
    *,
    queue_items: list[QueueItem],
    scanned_keys: set[tuple[str, str]],
) -> tuple[list[QueueItem], list[dict]]:
    updated_items = []
    terminal_records = []
    for item in queue_items:
        if item.status != STATUS_UNKNOWN:
            continue
        key = queue_item_conflict_key(item)
        if not key[0] or key in scanned_keys:
            continue
        work_dir = effective_queue_item_work_dir(item)
        if not work_dir:
            item.status = STATUS_PENDING_CONFIRM
            item.message = "程序重启后缺少运行目录，请人工确认"
            updated_items.append(item)
            continue
        diagnostics_status, diagnostics_detail = inspect_job_files(
            work_dir, item.job_name
        )
        runtime = classify_external_job_runtime(
            job_name=item.job_name,
            work_dir=work_dir,
            process_names=[],
            process_cmdlines=[],
            diagnostics_status=diagnostics_status,
            diagnostics_detail=diagnostics_detail,
        )
        status = runtime["status"]
        if status == STATUS_UNKNOWN:
            item.status = STATUS_PENDING_CONFIRM
            item.message = "程序重启后未发现运行进程或终态证据，请人工确认"
            updated_items.append(item)
            continue
        item.status = status
        item.message = runtime["message"]
        updated_items.append(item)
        if item.status in TERMINAL_STATUSES:
            terminal_records.append(
                {
                    "item": item,
                    "job": {},
                    "key": key,
                    "work_dir": work_dir,
                    "previous_status": STATUS_UNKNOWN,
                    "status": item.status,
                }
            )
    return updated_items, terminal_records


def scan_external_jobs(
    work_dir: str,
    known_external_jobs: list[dict] | None = None,
    *,
    process_rows: list[dict] | None = None,
) -> tuple[list[dict], list[int]]:
    known_external_jobs = known_external_jobs or []
    scan_roots = [work_dir]
    seen_roots = {normalize_work_dir(work_dir)}
    for known in known_external_jobs:
        known_work_dir = known.get("work_dir") or os.path.dirname(
            known.get("inp_path", "")
        )
        if not known_work_dir or work_dir_matches_scan_root(
            known_work_dir,
            work_dir,
            EXTERNAL_SCAN_MAX_CHILD_DEPTH,
        ):
            continue
        normalized_known_root = normalize_work_dir(known_work_dir)
        if not normalized_known_root or normalized_known_root in seen_roots:
            continue
        seen_roots.add(normalized_known_root)
        scan_roots.append(known_work_dir)

    rows = process_rows
    if rows is None:
        rows = fetch_psutil_process_rows_for_external_scan(force=True)
    merged_jobs: dict[tuple[str, str], dict] = {}
    skipped: list[int] = []
    for scan_root in scan_roots:
        root_jobs, root_skipped = scan_running_abaqus_jobs_by_psutil(
            scan_root,
            force=True,
            known_external_jobs=known_external_jobs,
            process_rows=rows,
        )
        skipped.extend(root_skipped)
        for job in root_jobs:
            job_name = str(job.get("job_name") or "").strip().lower()
            job_work_dir = normalize_work_dir(job.get("work_dir") or scan_root)
            if job_name and job_work_dir:
                merged_jobs[(job_work_dir, job_name)] = job
    return list(merged_jobs.values()), sorted(set(skipped))


def merge_external_scan_results(
    *,
    queue_items: list[QueueItem],
    work_dir: str,
    jobs: list[dict],
) -> dict:
    queue_item_by_key = build_queue_item_index(queue_items)
    added = 0
    updated = 0
    status_only_updates = 0
    updated_items: list[QueueItem] = []
    active_external_items: list[QueueItem] = []
    terminal_external_records: list[dict] = []
    debug_records: list[dict] = []
    memory_records: list[dict] = []
    scanned_keys: set[tuple[str, str]] = set()

    for job in jobs:
        job_name = job.get("job_name", "")
        job_work_dir = job.get("work_dir") or work_dir
        if not job_name:
            continue
        key = managed_job_key(job_work_dir, job_name)
        scanned_keys.add(key)
        matched = queue_item_by_key.get(key)
        runtime_status = job.get("runtime_status") or STATUS_UNKNOWN
        runtime_message = job.get("runtime_message") or "外部作业状态待确认"
        previous_status = matched.status if matched is not None else ""

        if job.get("status_only_update"):
            if matched is not None:
                matched.pids = job.get("pids", [])
                matched.pid_create_times = job.get("pid_create_times", {})
                matched.rss_bytes = int(job.get("rss_bytes") or 0)
                matched.status = runtime_status
                matched.message = runtime_message
                status_only_updates += 1
                updated_items.append(matched)
                memory_records.append(
                    {"item": matched, "job": job, "key": key, "work_dir": job_work_dir}
                )
                restored_active_without_run = (
                    previous_status in ACTIVE_STATUSES and not matched.active_job_key
                )
                track_scan_runtime = (
                    matched.is_external
                    or previous_status == STATUS_UNKNOWN
                    or restored_active_without_run
                )
                if track_scan_runtime and matched.status in ACTIVE_STATUSES:
                    active_external_items.append(matched)
                if (
                    track_scan_runtime
                    and (
                        previous_status in ACTIVE_STATUSES
                        or previous_status == STATUS_UNKNOWN
                    )
                    and matched.status in TERMINAL_STATUSES
                ):
                    terminal_external_records.append(
                        {
                            "item": matched,
                            "job": job,
                            "key": key,
                            "work_dir": job_work_dir,
                            "previous_status": previous_status,
                            "status": matched.status,
                        }
                    )
                debug_records.append(
                    {
                        "job_name": job_name,
                        "job_work_dir": job_work_dir,
                        "job": job,
                        "runtime_status": runtime_status,
                        "runtime_message": runtime_message,
                    }
                )
            continue

        if matched is None:
            target_item = QueueItem(
                inp_path=job.get("inp_path")
                or os.path.join(job_work_dir, f"{job_name}.inp"),
                job_name=job_name,
                source="external_psutil",
                status=runtime_status,
                selected=False,
                valid=True,
                message=runtime_message,
                run_mode="restart" if job.get("oldjob_path") else "normal",
                oldjob_name=job.get("restart_dependency", ""),
                oldjob_path=job.get("oldjob_path", ""),
                fortran_path=job.get("for_file", ""),
                cores=int(job.get("cores") or 0)
                if str(job.get("cores") or "").isdigit()
                else 0,
                memory=job.get("memory_setting", ""),
                job_type=job.get("job_type", "Abaqus"),
                is_external=True,
                external_work_dir=job_work_dir,
                effective_work_dir=job_work_dir,
                pids=job.get("pids", []),
                pid_create_times=job.get("pid_create_times", {}),
                rss_bytes=int(job.get("rss_bytes") or 0),
            )
            queue_items.append(target_item)
            queue_item_by_key[key] = target_item
            added += 1
        else:
            matched.pids = job.get("pids", matched.pids)
            matched.pid_create_times = job.get(
                "pid_create_times", matched.pid_create_times
            )
            matched.rss_bytes = int(job.get("rss_bytes") or matched.rss_bytes or 0)
            matched.status = runtime_status
            matched.message = runtime_message
            if matched.is_external:
                matched.external_work_dir = job_work_dir
            matched.effective_work_dir = job_work_dir
            target_item = matched
            updated += 1

        updated_items.append(target_item)
        restored_active_without_run = (
            previous_status in ACTIVE_STATUSES and not target_item.active_job_key
        )
        track_scan_runtime = (
            target_item.is_external
            or previous_status == STATUS_UNKNOWN
            or restored_active_without_run
        )
        if track_scan_runtime:
            memory_records.append(
                {"item": target_item, "job": job, "key": key, "work_dir": job_work_dir}
            )
            if target_item.status in ACTIVE_STATUSES:
                active_external_items.append(target_item)
            if (
                previous_status in ACTIVE_STATUSES or previous_status == STATUS_UNKNOWN
            ) and target_item.status in TERMINAL_STATUSES:
                terminal_external_records.append(
                    {
                        "item": target_item,
                        "job": job,
                        "key": key,
                        "work_dir": job_work_dir,
                        "previous_status": previous_status,
                        "status": target_item.status,
                    }
                )
        debug_records.append(
            {
                "job_name": job_name,
                "job_work_dir": job_work_dir,
                "job": job,
                "runtime_status": runtime_status,
                "runtime_message": runtime_message,
            }
        )

    restored_updates, restored_terminal_records = (
        resolve_unmatched_restored_unknown_items(
            queue_items=queue_items,
            scanned_keys=scanned_keys,
        )
    )
    if restored_updates:
        status_only_updates += len(restored_updates)
        updated_items.extend(restored_updates)
    terminal_external_records.extend(restored_terminal_records)
    return {
        "added": added,
        "updated": updated,
        "status_only_updates": status_only_updates,
        "updated_items": updated_items,
        "active_external_items": active_external_items,
        "terminal_external_records": terminal_external_records,
        "debug_records": debug_records,
        "memory_records": memory_records,
    }


__all__ = [
    "build_queue_item_index",
    "collect_known_external_jobs",
    "merge_external_scan_results",
    "resolve_unmatched_restored_unknown_items",
    "scan_external_jobs",
]
