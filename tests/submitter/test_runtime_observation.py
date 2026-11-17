import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from modules.submitter.runtime_observation import (
    ProcessSnapshot,
    ProcessSnapshotCache,
    observe_local_job,
)


def row(pid, parent=0, created=100, rss=1000, name="standard.exe"):
    return {"ProcessId": pid, "ParentProcessId": parent, "CreateTime": created,
            "WorkingSetSize": rss, "Name": name}


def observe(rows, **kwargs):
    return observe_local_job(ProcessSnapshot(tuple(rows), 110),
                             {"solver_pid_confidence": "high", "solver_pids": (2,)},
                             work_dir="G:/fixture", submitted_at=100, **kwargs)


def test_process_cache_coalesces_concurrent_workers_and_refreshes_after_interval():
    clock = [0]
    calls = []
    gate = threading.Barrier(8)
    cache = ProcessSnapshotCache(lambda: calls.append(True) or [row(2)], clock=lambda: clock[0])

    def capture():
        gate.wait()
        return cache.capture()

    with ThreadPoolExecutor(max_workers=8) as pool:
        snapshots = list(pool.map(lambda _index: capture(), range(8)))
    assert len(calls) == 1 and all(value is snapshots[0] for value in snapshots)
    clock[0] = 1
    assert cache.capture() is not snapshots[0]
    assert len(calls) == 2


def test_scan_failure_is_unavailable_and_recovers_not_an_empty_snapshot():
    clock = [0]
    def fail():
        raise OSError("denied")
    cache = ProcessSnapshotCache(fail, clock=lambda: clock[0])
    failed = cache.capture()
    assert failed.rows is None and "denied" in failed.error
    cache.scanner = list
    clock[0] = 1
    assert cache.capture().rows == ()


def test_counts_job_subtree_without_ancestors_or_same_name_other_jobs():
    result = observe([row(1, created=50, rss=9000), row(2, parent=1), row(3, parent=2, rss=500),
                      row(4, parent=1, rss=7000), row(5, parent=2, created=30, rss=8000)])
    assert result.rss_bytes == 1500 and result.pids == (2, 3)
    assert result.pid_create_times == ((2, 100.0), (3, 100.0))


@pytest.mark.parametrize("child", [row(3, parent=2, rss=0), row(3, parent=2, created=0)])
def test_partial_memory_or_unknown_creation_time_is_not_zero_usage(child):
    result = observe([row(2), child])
    assert result.rss_bytes is None and result.status == "unavailable"


def test_old_pid_and_unrelated_pid_are_not_reused_as_current_attempt():
    result = observe([row(2, created=10), row(3, rss=9000)])
    assert result.rss_bytes is None and not result.pids


def test_owned_launcher_descendants_can_be_observed_without_solver_name():
    result = observe([row(7, name="cmd.exe"), row(8, parent=7, name="python.exe")], launcher_pid=7)
    assert result.pids == (7, 8) and result.rss_bytes == 2000
