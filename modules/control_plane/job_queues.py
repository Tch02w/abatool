"""Qt-free read model for the persisted submitter candidate and job queues."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from modules.submitter.app_paths import JOBLIST_PATH
from modules.submitter.models import QueueItem
from modules.submitter.queue_store import load_joblist_state

from .contracts import SCHEMA_VERSION


def _integer(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value or default)
    except TypeError, ValueError:
        return default


def _string(value: object) -> str:
    return str(value or "").strip()


def _project_item(raw: object, index: int) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    inp_path = _string(raw.get("source_inp_path") or raw.get("inp_path"))
    oldjob_path = _string(raw.get("oldjob_path"))
    oldjob_name = _string(raw.get("oldjob_name"))
    if not oldjob_name and oldjob_path:
        oldjob_name = Path(oldjob_path).stem
    run_mode = _string(raw.get("run_mode")) or "normal"
    return {
        "index": index,
        "itemId": _string(raw.get("item_id")),
        "jobId": _string(raw.get("job_id") or raw.get("item_id")),
        "jobName": _string(raw.get("job_name")) or Path(inp_path).stem,
        "inpPath": inp_path,
        "source": "外部接管"
        if bool(raw.get("is_external", False))
        else (_string(raw.get("source")) or "文件"),
        "selected": bool(raw.get("selected", True)),
        "valid": bool(raw.get("valid", True)),
        "message": _string(raw.get("message")),
        "runMode": run_mode,
        "jobType": _string(raw.get("job_type"))
        or ("重启动" if run_mode == "restart" else "普通"),
        "oldjobName": oldjob_name,
        "oldjobPath": oldjob_path,
        "fortranPath": _string(raw.get("fortran_path")),
        "cores": max(0, _integer(raw.get("cores"))),
        "memory": _string(raw.get("memory")),
        "runtimeMemoryBytes": max(0, _integer(raw.get("rss_bytes"))),
        "priority": _integer(raw.get("priority")),
        "held": bool(raw.get("held", False)),
        "schedulerState": _string(raw.get("scheduler_state")),
        "pendingReason": _string(raw.get("pending_reason")),
        "status": _string(raw.get("status")),
        "effectiveWorkDir": _string(raw.get("effective_work_dir")),
        "archiveDestination": _string(raw.get("archive_destination")),
        "archiveStatus": _string(raw.get("archive_status")),
        "archiveError": _string(raw.get("archive_error")),
        "elapsed": _string(raw.get("elapsed")),
        "isExternal": bool(raw.get("is_external", False)),
        "dependencyJobIds": [
            _string(value)
            for value in raw.get("dependency_job_ids", [])
            if _string(value)
        ]
        if isinstance(raw.get("dependency_job_ids", []), list)
        else [],
    }


def _project_list(raw_items: object) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []
    projected: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items, start=1):
        item = _project_item(raw, index)
        if item is not None:
            projected.append(item)
    return projected


def project_job_queues(
    candidate_items: list[QueueItem],
    formal_items: list[QueueItem],
) -> dict[str, Any]:
    candidates = _project_list([asdict(item) for item in candidate_items])
    queue_items = _project_list([asdict(item) for item in formal_items])
    status_counts = Counter(item["status"] or "未知" for item in queue_items)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "capturedAt": datetime.now(UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "candidates": candidates,
        "queueItems": queue_items,
        "candidateCount": len(candidates),
        "selectedCandidateCount": sum(item["selected"] for item in candidates),
        "invalidCandidateCount": sum(not item["valid"] for item in candidates),
        "queueCount": len(queue_items),
        "statusCounts": dict(sorted(status_counts.items())),
    }


def read_job_queues(path: str | Path | None = None) -> dict[str, Any]:
    candidates, queue_items, _error = load_joblist_state(
        path or JOBLIST_PATH,
        restore_active_state=False,
    )
    return project_job_queues(candidates, queue_items)


__all__ = ["project_job_queues", "read_job_queues"]
