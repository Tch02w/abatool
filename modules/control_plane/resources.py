"""Read-only local resource snapshot for native clients."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from modules.common.json_io import load_json_mapping
from modules.postprocessor.config import load_defaults
from modules.submitter.app_paths import JOBLIST_PATH
from modules.submitter.app_settings import load_app_settings
from modules.submitter.constants import ACTIVE_STATUSES
from modules.submitter.cpu_policy import local_cpu_policy

from .contracts import SCHEMA_VERSION

_CPU_PERCENT_INITIALIZED = False


def _abaqus_snapshot() -> tuple[str, str, bool]:
    """Read the configured local Abaqus identity without launching it."""

    defaults = load_defaults()
    settings = load_app_settings()
    command = str(
        settings.get("abaqus_command")
        or defaults.get("abaqus_command")
        or "abaqus"
    ).strip()
    release = str(
        settings.get("local_abaqus_release")
        or defaults.get("local_abaqus_release")
        or ""
    ).strip()
    executable = command.strip('"')
    try:
        available = Path(executable).is_file() or shutil.which(executable) is not None
    except (OSError, ValueError):
        available = False
    return command, release, available


def _queue_snapshot() -> tuple[list[str], int, int]:
    payload = load_json_mapping(JOBLIST_PATH)
    raw_items = payload.get("queue_items", [])
    if not isinstance(raw_items, list):
        return [], 0, 0
    active_jobs: list[str] = []
    waiting_jobs = 0
    total_jobs = 0
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        total_jobs += 1
        status = str(raw_item.get("status") or "")
        name = str(raw_item.get("job_name") or "未命名作业")
        if status in ACTIVE_STATUSES:
            active_jobs.append(name)
        elif "等待" in status or status in {"待运行", "待确认"}:
            waiting_jobs += 1
    return active_jobs, waiting_jobs, total_jobs


def capture_local_resource(command: str = "") -> dict[str, Any]:
    global _CPU_PERCENT_INITIALIZED
    memory = psutil.virtual_memory()
    logical_cpus = psutil.cpu_count(logical=True) or 1
    cpu_percent = psutil.cpu_percent(
        interval=None if _CPU_PERCENT_INITIALIZED else 0.05
    )
    _CPU_PERCENT_INITIALIZED = True
    cpu_percent = max(0.0, min(100.0, float(cpu_percent)))
    active_jobs, waiting_jobs, total_jobs = _queue_snapshot()
    abaqus_command, abaqus_release, abaqus_available = _abaqus_snapshot()
    return {
        **local_cpu_policy(command),
        "schemaVersion": SCHEMA_VERSION,
        "capturedAt": datetime.now(UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "resourceId": "local",
        "name": "本机",
        "status": "online",
        "logicalCpus": logical_cpus,
        "busyCpus": min(logical_cpus, round(logical_cpus * cpu_percent / 100)),
        "cpuPercent": round(cpu_percent, 1),
        "memoryUsedBytes": int(memory.used),
        "memoryTotalBytes": int(memory.total),
        "memoryPercent": round(float(memory.percent), 1),
        "runningJobs": len(active_jobs),
        "waitingJobs": waiting_jobs,
        "totalJobs": total_jobs,
        "activeJobs": active_jobs,
        "abaqusCommand": abaqus_command,
        "abaqusRelease": abaqus_release,
        "abaqusAvailable": abaqus_available,
    }


__all__ = ["capture_local_resource"]
