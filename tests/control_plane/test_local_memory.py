import json
import threading
import time

from modules.control_plane.job_queue_commands import JobQueueService
from modules.control_plane.job_queues import _project_item
from modules.control_plane.local_memory import LocalMemoryMonitor, memory_profile_key
from modules.control_plane.local_scheduling import (
    LocalQueueScheduling,
    LocalSchedulingResources,
)
from modules.submitter.constants import STATUS_COMPLETED, STATUS_RUNNING
from modules.submitter.local_job_execution import LocalJobExecutionResult
from modules.submitter.queue_store import load_joblist_state, save_joblist_state
from modules.submitter.runtime_observation import LocalJobObservation
from modules.submitter.scheduler_repository import SQLiteSchedulerRepository
from tests.control_plane.test_api import running_control_plane
from tests.control_plane.test_local_queue_runtime_api import (
    queue_item,
    runtime_control,
    runtime_snapshot,
    wait_until,
)

GB = 1024**3


def observation(rss, stamp=None):
    return LocalJobObservation(time.time() if stamp is None else stamp, "G:/fixture", rss_bytes=rss,
                               pids=(123,), pid_create_times=((123, 10),), process_names=("standard.exe",),
                               status="observed" if rss is not None else "unavailable")


def test_history_survives_restart_and_separates_changed_input_settings_and_same_name(tmp_path):
    item = queue_item(tmp_path, "case")
    item.attempt_id = "attempt1"
    repo = SQLiteSchedulerRepository(tmp_path / "state.db")
    memory = LocalMemoryMonitor(repo)
    memory.begin(item)
    memory.apply(item, observation(4 * GB), 4 * GB)
    memory.finish(item.attempt_id)
    assert item.memory_estimated_bytes == int(4 * GB * 1.1)
    key = memory_profile_key(item)
    repo.close()
    repo = SQLiteSchedulerRepository(tmp_path / "state.db")
    try:
        restored = LocalMemoryMonitor(repo)
        estimates = restored.project_estimates([item])
        assert estimates[item.job_id] == item.memory_estimated_bytes
        assert item.memory_estimate_source == "history"
        item.cores += 1
        assert memory_profile_key(item) != key and not restored.project_estimates([item])
        item.cores -= 1
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        other = queue_item(other_dir, "case")
        assert memory_profile_key(other) != key and not restored.project_estimates([other])
        from pathlib import Path
        Path(item.inp_path).write_text("*Heading\nChanged model\n", encoding="utf-8")
        assert memory_profile_key(item) != key and not restored.project_estimates([item])
    finally:
        repo.close()


def test_peak_before_failed_sample_is_preserved_and_not_reported_as_current_zero(tmp_path):
    item = queue_item(tmp_path, "peak")
    item.attempt_id = "peak-attempt"
    repo = SQLiteSchedulerRepository(tmp_path / "state.db")
    try:
        memory = LocalMemoryMonitor(repo)
        memory.begin(item)
        memory.apply(item, observation(None), 5 * GB)
        assert item.memory_observation_status == "unavailable"
        assert item.memory_peak_bytes == 5 * GB
        assert item.memory_estimated_bytes == int(5 * GB * 1.1)
        assert item.rss_bytes == 0  # Unavailable flag, not an observed zero sample.
        count = item.memory_sample_count
        memory.apply(item, observation(None), 0)
        assert item.memory_sample_count == count
    finally:
        repo.close()


def test_invalid_history_is_preserved_and_history_write_failure_retries(tmp_path, monkeypatch):
    repo = SQLiteSchedulerRepository(tmp_path / "state.db")
    item = queue_item(tmp_path, "case")
    item.attempt_id = "try"
    try:
        repo.save_memory_profile("bad", {"peak": -1})
        memory = LocalMemoryMonitor(repo)
        assert memory.notice and not memory.profiles
        assert json.loads(repo.load_memory_profiles()["bad"]) == {"peak": -1}
        memory.begin(item)
        memory.apply(item, observation(GB), GB)
        original = repo.save_memory_profile
        def fail(*_args):
            raise OSError("locked")
        monkeypatch.setattr(repo, "save_memory_profile", fail)
        memory.flush()
        assert memory.dirty and "暂未保存" in memory.notice
        monkeypatch.setattr(repo, "save_memory_profile", original)
        memory.flush()
        assert not memory.dirty
        assert memory_profile_key(item) in repo.load_memory_profiles()
    finally:
        repo.close()


def test_live_rss_is_not_deducted_twice_but_stale_rss_is_not_used(tmp_path):
    active, pending = queue_item(tmp_path, "active"), queue_item(tmp_path, "pending")
    active.memory, pending.memory = "4 GB", "3 GB"
    path = tmp_path / "joblist.json"
    save_joblist_state([], [active, pending], path)
    service = JobQueueService(path, external_monitor_interval=999)
    scheduler = LocalQueueScheduling(service, lambda: LocalSchedulingResources(8, 4 * GB))
    def set_active(_candidates, items):
        items[0].status = STATUS_RUNNING
        items[0].rss_bytes = 4 * GB
        items[0].memory_observation_status = "observed"
        items[0].memory_observed_at = 1
    try:
        service.runtime_transaction(set_active)
        assert scheduler.reserve([pending.item_id], 2, set()) == []
        service.runtime_transaction(lambda _c, items: setattr(items[0], "memory_observed_at", time.time()))
        assert len(scheduler.reserve([pending.item_id], 2, set())) == 1
    finally:
        scheduler.close()
        service.close()


def test_observations_reach_api_queue_and_persisted_profile_without_new_scanner(tmp_path):
    item = queue_item(tmp_path, "observe")
    path = tmp_path / "joblist.json"
    save_joblist_state([], [item], path)
    release = threading.Event()
    callbacks = []
    def runner(item, policy, controller, progress, log):
        callbacks.append(controller.observer)
        controller.observer(observation(2 * GB))
        progress("solving", "running", 50, "")
        assert release.wait(30)
        return LocalJobExecutionResult(STATUS_COMPLETED, "done", str(tmp_path), "fixture")
    with running_control_plane(tmp_path, joblist_path=path, local_job_runner=runner) as runtime:
        try:
            assert runtime_control(runtime, "start")[0] == 202
            wait_until(lambda: runtime_snapshot(runtime)["queue"]["queueItems"][0]["runtimeMemoryBytes"] == 2 * GB)
            view = runtime_snapshot(runtime)["queue"]["queueItems"][0]
            assert view["memoryObservationStatus"] == "observed" and view["memoryEstimateSource"] == "observed"
            release.set()
            wait_until(lambda: not runtime_snapshot(runtime)["active"])
            saved = load_joblist_state(path, restore_active_state=False)[1][0]
            assert saved.rss_bytes == 0 and saved.memory_peak_bytes == 2 * GB
            assert saved.memory_observation_status == "ended"
            before = path.read_bytes()
            callbacks[0](observation(10 * GB))
            runtime.local_queue_runtime._flush_observations(force=True)
            assert path.read_bytes() == before
        finally:
            release.set()


def test_stale_or_future_timestamp_is_not_displayed_as_current_rss():
    for stamp in (1, time.time() + 60):
        item = _project_item({"job_name": "sample", "memory_observation_status": "observed",
                              "memory_observed_at": stamp, "rss_bytes": 12}, 1)
        assert item["memoryObservationStatus"] == "stale"


def test_learned_memory_controls_actual_allocation_by_job_identity(tmp_path):
    from dataclasses import replace
    from uuid import uuid4

    first_dir, second_dir = tmp_path / "one", tmp_path / "two"
    first_dir.mkdir()
    second_dir.mkdir()
    high, low = queue_item(first_dir, "same"), queue_item(second_dir, "same")
    path = tmp_path / "joblist.json"
    save_joblist_state([], [high, low], path)
    service = JobQueueService(path, external_monitor_interval=999)
    scheduler = LocalQueueScheduling(service, lambda: LocalSchedulingResources(8, 3 * GB))
    try:
        for item, size in ((high, 4 * GB), (low, GB)):
            sample = replace(item, attempt_id=uuid4().hex)
            scheduler.memory.begin(sample)
            scheduler.memory.apply(sample, observation(size), size)
            scheduler.memory.finish(sample.attempt_id)
        allocations = scheduler.reserve([high.item_id, low.item_id], 2, set())
        assert [item_id for item_id, _attempt in allocations] == [low.item_id]
        saved = load_joblist_state(path, restore_active_state=False)[1]
        assert saved[0].pending_reason == "MEMORY_LIMIT"
        assert saved[0].memory_estimate_source == saved[1].memory_estimate_source == "history"
    finally:
        scheduler.close()
        service.close()


def test_recovered_external_samples_refresh_freshness_without_owning_process(tmp_path):
    item = queue_item(tmp_path, "external")
    item.status, item.attempt_id = STATUS_RUNNING, "original-attempt"
    path = tmp_path / "joblist.json"
    save_joblist_state([], [item], path)
    scan = {"job_name": item.job_name, "work_dir": str(tmp_path), "runtime_status": STATUS_RUNNING,
            "rss_bytes": GB, "pids": [101], "pid_create_times": {"101": 1.0}}
    with running_control_plane(tmp_path, joblist_path=path, external_job_scanner=lambda *_args: ([scan], []),
                               external_monitor_interval=999) as runtime:
        runtime.job_queue_service.refresh_external_jobs()
        first = load_joblist_state(path, restore_active_state=False)[1][0].memory_observed_at
        runtime.job_queue_service.refresh_external_jobs()
        assert load_joblist_state(path, restore_active_state=False)[1][0].memory_observed_at > first
        runtime.local_queue_runtime._flush_observations(force=True)
        saved = load_joblist_state(path, restore_active_state=False)[1][0]
        assert saved.memory_peak_bytes == GB and saved.memory_estimated_bytes > GB
        assert not runtime_snapshot(runtime)["operations"]
        scan["rss_bytes"] = 0
        runtime.job_queue_service.refresh_external_jobs()
        assert load_joblist_state(path, restore_active_state=False)[1][0].memory_observation_status == "unavailable"
