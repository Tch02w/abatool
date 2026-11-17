"""Shared, read-only process observations for Qt-free local execution."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from .process_scanner import get_psutil_process_snapshot


@dataclass(frozen=True)
class ProcessSnapshot:
    rows: tuple[dict, ...] | None
    observed_at: float
    error: str = ""


class ProcessSnapshotCache:
    """One scan per interval across concurrent workers; failures are not empty scans."""

    def __init__(self, scanner=None, *, interval=0.75, clock=time.monotonic):
        self.scanner = scanner or (lambda: get_psutil_process_snapshot(force=True, include_details=True))
        self.interval = interval
        self.clock = clock
        self._lock = threading.Lock()
        self._snapshot = None
        self._next_scan = 0.0

    def capture(self):
        with self._lock:
            if self._snapshot is None or self.clock() >= self._next_scan:
                try:
                    self._snapshot = ProcessSnapshot(tuple(self.scanner()), time.time())
                except Exception as exc:  # noqa: BLE001 - preserve monitoring on scanner failure
                    self._snapshot = ProcessSnapshot(None, time.time(), str(exc))
                self._next_scan = self.clock() + self.interval
            return self._snapshot


@dataclass(frozen=True)
class LocalJobObservation:
    observed_at: float
    work_dir: str
    rss_bytes: int | None = None
    pids: tuple[int, ...] = ()
    pid_create_times: tuple[tuple[int, float], ...] = ()
    process_names: tuple[str, ...] = ()
    step: str = "unknown"
    status: str = "unavailable"
    message: str = ""


def observe_local_job(snapshot, evidence, *, work_dir, submitted_at, launcher_pid=0):
    """Count verified solver roots or the owned launcher and their descendants.

    Never aggregate by job name alone, count ancestors, or treat inaccessible
    memory as zero. Creation times reject old/reused PID ancestry.
    """
    base = {"observed_at": snapshot.observed_at, "work_dir": str(work_dir),
            "step": str(evidence.get("sta_last_step") or "unknown")}
    if snapshot.rows is None:
        return LocalJobObservation(**base, message=snapshot.error)
    rows = {int(row.get("ProcessId") or 0): row for row in snapshot.rows}
    roots = set(evidence.get("solver_pids") or ()) if evidence.get("solver_pid_confidence") == "high" else set()
    if launcher_pid:
        roots.add(launcher_pid)
    roots = {pid for pid in roots if pid in rows and
             float(rows[pid].get("CreateTime") or 0) >= submitted_at - 2}
    if not roots:
        return LocalJobObservation(**base, status="waiting", message="尚未取得本次作业的进程内存")
    matched = set(roots)
    incomplete = False
    while True:
        incomplete |= any(int(row.get("ParentProcessId") or 0) in matched and
                          float(row.get("CreateTime") or 0) <= 0 for row in rows.values())
        children = {pid for pid, row in rows.items() if pid not in matched and
                    int(row.get("ParentProcessId") or 0) in matched and
                    float(row.get("CreateTime") or 0) >= float(rows[int(row["ParentProcessId"])].get("CreateTime") or 0)}
        if not children:
            break
        matched.update(children)
    pids = tuple(sorted(matched))
    times = tuple((pid, float(rows[pid].get("CreateTime") or 0)) for pid in pids)
    names = tuple(sorted({str(rows[pid].get("Name") or "") for pid in pids}))
    rss = [int(rows[pid].get("WorkingSetSize") or 0) for pid in pids]
    if incomplete or any(value <= 0 for value in rss):
        return LocalJobObservation(**base, pids=pids, pid_create_times=times, process_names=names,
                                   message="部分作业进程的内存暂不可读")
    return LocalJobObservation(**base, pids=pids, pid_create_times=times, process_names=names,
                               rss_bytes=sum(rss), status="observed")


SHARED_PROCESS_SNAPSHOTS = ProcessSnapshotCache()
