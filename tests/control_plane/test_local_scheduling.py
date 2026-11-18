from __future__ import annotations

import threading

import pytest

from modules.control_plane import job_queue_commands
from modules.control_plane.job_queue_commands import JobQueueService
from modules.control_plane.local_scheduling import (
    LocalQueueScheduling,
    LocalSchedulingResources,
)
from modules.submitter.constants import (
    STATUS_COMPLETED,
    STATUS_PENDING_CONFIRM,
    STATUS_PENDING_RUN,
    STATUS_RUNNING,
    STATUS_UNKNOWN,
    STATUS_WAITING_DEPENDENCY,
)
from modules.submitter.local_job_execution import LocalJobExecutionResult
from modules.submitter.queue_store import load_joblist_state, save_joblist_state
from modules.submitter.scheduling import JobState
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_local_queue_runtime_api import (
    queue_item,
    runtime_control,
    runtime_snapshot,
    wait_until,
)

GB = 1024**3


def test_archive_only_work_reserves_overlapping_directory_even_for_another_job_name(tmp_path):
    archive, waiting = queue_item(tmp_path, "archive"), queue_item(tmp_path, "other")
    archive.status, archive.archive_status = STATUS_COMPLETED, "归档中"
    path = tmp_path / "joblist.json"
    save_joblist_state([], [archive, waiting], path)
    service = JobQueueService(path, external_monitor_interval=999)
    scheduler = LocalQueueScheduling(service, lambda: LocalSchedulingResources(8, 16 * GB))
    try:
        assert scheduler.reserve([waiting.item_id], 2, set()) == []
        assert "归档" in load_joblist_state(path, restore_active_state=False)[1][1].message
    finally:
        scheduler.close()
        service.close()


def configure(runtime, cores=8, memory=16 * GB):
    runtime.local_queue_runtime._scheduling.resource_provider = lambda: LocalSchedulingResources(cores, memory)


def test_priority_and_shared_cpu_budget_control_actual_dispatch(tmp_path):
    low, high = queue_item(tmp_path, "low"), queue_item(tmp_path, "high")
    high.priority, high.cores = 10, 2
    path = tmp_path / "joblist.json"
    save_joblist_state([], [low, high], path)
    started = []
    release = threading.Event()

    def runner(item, policy, controller, progress, log):
        started.append((item.job_name, item.attempt_id))
        progress("solving", "running", 50, "")
        assert release.wait(8)
        return LocalJobExecutionResult(STATUS_COMPLETED, "done", str(tmp_path), "test")

    with running_control_plane(tmp_path, joblist_path=path, local_job_runner=runner) as runtime:
        try:
            configure(runtime, cores=2)
            assert runtime_control(runtime, "start", maxParallel=3)[0] == 202
            wait_until(lambda: len(started) == 1)
            assert started[0][0] == "high" and started[0][1]
            waiting = next(item for item in runtime_snapshot(runtime)["queue"]["queueItems"] if item["itemId"] == low.item_id)
            assert waiting["pendingReason"] == "CPU_LIMIT"
            release.set()
            wait_until(lambda: not runtime_snapshot(runtime)["active"])
            assert [name for name, _attempt in started] == ["high", "low"]
            assert len({attempt for _name, attempt in started}) == 2
            assert all(item.scheduler_state == "COMPLETED" for item in
                       load_joblist_state(path, restore_active_state=False)[1])
            for item in (low, high):
                stored = runtime.local_queue_runtime._scheduling.core.get(item.job_id)
                assert stored.state == JobState.COMPLETED
                assert any(event["attempt_id"] == stored.attempt_id for event in
                           runtime.local_queue_runtime._scheduling.repository.load_events(job_id=item.job_id))
        finally:
            release.set()


@pytest.mark.parametrize("constraint", ["memory", "directory"])
def test_memory_and_directory_conflicts_wait_without_starting_second_worker(tmp_path, constraint):
    one, two = queue_item(tmp_path, "one"), queue_item(tmp_path, "two")
    if constraint == "memory":
        one.memory = two.memory = "4 GB"
    else:
        two.job_name, two.inp_path, two.source_inp_path = one.job_name, one.inp_path, one.source_inp_path
    path = tmp_path / "joblist.json"
    save_joblist_state([], [one, two], path)
    calls = []
    release = threading.Event()

    def runner(item, policy, controller, progress, log):
        calls.append(item.item_id)
        assert release.wait(8)
        return LocalJobExecutionResult(STATUS_COMPLETED, "done", str(tmp_path), "test")

    with running_control_plane(tmp_path, joblist_path=path, local_job_runner=runner) as runtime:
        try:
            configure(runtime, memory=6 * GB)
            assert runtime_control(runtime, "start", maxParallel=2)[0] == 202
            wait_until(lambda: len(calls) == 1)
            _candidates, items, _error = load_joblist_state(path, restore_active_state=False)
            assert items[1].pending_reason == ("MEMORY_LIMIT" if constraint == "memory" else "ACTIVE_CONFLICT")
            release.set()
            wait_until(lambda: not runtime_snapshot(runtime)["active"])
            assert calls == [one.item_id, two.item_id]
        finally:
            release.set()


def test_zero_core_requires_editing_before_dispatch(tmp_path):
    item = queue_item(tmp_path, "unset")
    item.cores = 0
    path = tmp_path / "joblist.json"
    save_joblist_state([], [item], path)
    with running_control_plane(tmp_path, joblist_path=path) as runtime:
        response = runtime_control(runtime, "start")
        assert response[0] == 409
        assert json_response(response)["error"]["code"] == "LOCAL_QUEUE_CORE_REQUIRED"
        assert not runtime_snapshot(runtime)["operations"]


def test_persistence_failure_pauses_dispatch_and_recovers_on_explicit_start(tmp_path, monkeypatch):
    item = queue_item(tmp_path, "persist")
    path = tmp_path / "joblist.json"
    save_joblist_state([], [item], path)
    calls = []

    def runner(item, *_args):
        calls.append(item.attempt_id)
        return LocalJobExecutionResult(STATUS_COMPLETED, "done", str(tmp_path), "test")

    with running_control_plane(tmp_path, joblist_path=path, local_job_runner=runner) as runtime:
        configure(runtime)
        original = runtime.local_queue_runtime._scheduling.repository.save_job

        def fail(snapshot):
            if snapshot.state == JobState.DISPATCHED:
                raise OSError("simulated full disk")
            return original(snapshot)

        monkeypatch.setattr(runtime.local_queue_runtime._scheduling.repository, "save_job", fail)
        assert runtime_control(runtime, "start")[0] == 202
        wait_until(lambda: "simulated full disk" in runtime_snapshot(runtime)["schedulerMessage"])
        assert not calls and not runtime_snapshot(runtime)["active"]
        assert load_joblist_state(path, restore_active_state=False)[1][0].status == STATUS_PENDING_RUN
        monkeypatch.setattr(runtime.local_queue_runtime._scheduling.repository, "save_job", original)
        assert runtime_control(runtime, "start")[0] == 202
        wait_until(lambda: not runtime_snapshot(runtime)["active"])
        assert len(calls) == 1


def test_result_save_failure_is_retried_without_rerunning_job(tmp_path, monkeypatch):
    item = queue_item(tmp_path, "result")
    path = tmp_path / "joblist.json"
    save_joblist_state([], [item], path)
    calls = []

    def runner(item, *_args):
        calls.append(item.item_id)
        return LocalJobExecutionResult(STATUS_COMPLETED, "done", str(tmp_path), "test")

    with running_control_plane(tmp_path, joblist_path=path, local_job_runner=runner) as runtime:
        manager = runtime.local_queue_runtime
        original = manager._update_queue_item

        def fail(*args, **kwargs):
            if kwargs.get("clear_active"):
                raise OSError("result file locked")
            return original(*args, **kwargs)

        monkeypatch.setattr(manager, "_update_queue_item", fail)
        assert runtime_control(runtime, "start")[0] == 202
        wait_until(lambda: manager._pending_results)
        assert not manager.prepare_shutdown(reserve=False)["safeToStop"]
        monkeypatch.setattr(manager, "_update_queue_item", original)
        manager._retry_results_after = 0
        manager._wake.set()
        wait_until(lambda: not manager._pending_results)
        assert load_joblist_state(path, restore_active_state=False)[1][0].status == STATUS_COMPLETED
        assert calls == [item.item_id]


@pytest.mark.parametrize("missing_json_row,second_restart", [(False, False), (True, False), (False, True)])
def test_allocated_attempt_is_preserved_and_reconciled_after_restart(tmp_path, missing_json_row, second_restart):
    item = queue_item(tmp_path, "recover")
    path = tmp_path / "joblist.json"
    save_joblist_state([], [item], path)
    service = JobQueueService(path, external_monitor_interval=999)
    scheduler = LocalQueueScheduling(service, lambda: LocalSchedulingResources(8, 16 * GB))
    allocation = scheduler.reserve([item.item_id], 1, set())[0]
    scheduler.close()
    service.close()
    if missing_json_row:
        save_joblist_state([], [], path)
    if second_restart:
        service = JobQueueService(path, external_monitor_interval=999)
        scheduler = LocalQueueScheduling(service)
        scheduler.close()
        service.close()
    calls = []

    def scanner(root, known):
        calls.append((root, known))
        return [{"job_name": item.job_name, "work_dir": str(tmp_path), "runtime_status": STATUS_RUNNING,
                 "runtime_message": "observed running", "pids": [101], "pid_create_times": {"101": 123.0}}], []

    with running_control_plane(tmp_path, joblist_path=path, external_job_scanner=scanner,
                               external_monitor_interval=999) as runtime:
        restored = load_joblist_state(path, restore_active_state=False)[1][0]
        assert restored.job_id == item.job_id and restored.attempt_id == allocation[1]
        assert restored.status == STATUS_UNKNOWN
        assert not runtime.local_queue_runtime.prepare_shutdown(reserve=False)["safeToStop"]
        assert runtime_control(runtime, "start")[0] == 409
        clear = {"schemaVersion": 1, "action": "clearFinished"}
        assert api_request(runtime, "/api/v1/job-queue-commands", method="POST", payload=clear)[0] == 200
        assert len(load_joblist_state(path, restore_active_state=False)[1]) == 1
        runtime.job_queue_service.refresh_external_jobs()
        assert calls and calls[0][1][0]["job_name"] == item.job_name
        assert load_joblist_state(path, restore_active_state=False)[1][0].status == STATUS_RUNNING
        assert runtime_snapshot(runtime)["operations"] == []  # Observe; never resubmit/recreate ownership.


def test_restart_waits_for_active_parent_even_if_old_odb_exists(tmp_path):
    parent, child = queue_item(tmp_path, "base"), queue_item(tmp_path, "child")
    parent.status = STATUS_RUNNING
    odb = tmp_path / "base.odb"
    odb.write_bytes(b"existing result, still in use")
    child.run_mode, child.oldjob_name, child.oldjob_path = "restart", "base", str(odb)
    path = tmp_path / "joblist.json"
    save_joblist_state([], [parent, child], path)
    with running_control_plane(tmp_path, joblist_path=path, external_monitor_interval=999) as runtime:
        assert runtime.local_queue_runtime._refresh_dependencies() == []
        state = load_joblist_state(path, restore_active_state=False)[1]
        assert state[1].status == STATUS_WAITING_DEPENDENCY
        assert state[0].job_id in state[1].dependency_job_ids


def test_unchanged_runtime_refresh_does_not_replace_queue_file(tmp_path, monkeypatch):
    item = queue_item(tmp_path, "quiet")
    path = tmp_path / "joblist.json"
    save_joblist_state([], [item], path)
    service = JobQueueService(path, external_monitor_interval=999)
    writes = []
    monkeypatch.setattr(job_queue_commands, "save_joblist_state", lambda *_args: writes.append(True))
    try:
        service.runtime_transaction(lambda _candidates, _items: None)
        assert not writes
    finally:
        service.close()


def test_percent_memory_is_a_solver_ceiling_not_an_absolute_reservation(tmp_path):
    items = [queue_item(tmp_path, name) for name in ("one", "two")]
    for item in items:
        item.memory = "90%"
    path = tmp_path / "joblist.json"
    save_joblist_state([], items, path)
    service = JobQueueService(path, external_monitor_interval=999)
    scheduler = LocalQueueScheduling(service, lambda: LocalSchedulingResources(8, GB))
    try:
        allocations = scheduler.reserve([item.item_id for item in items], 2, set())
        assert len(allocations) == 2
        assert all(job.specification.resources.memory_bytes == 0 for job in scheduler.core.snapshots())
    finally:
        scheduler.close()
        service.close()


def test_thread_start_failure_releases_reservation_without_running_worker(tmp_path, monkeypatch):
    item = queue_item(tmp_path, "thread_failure")
    path = tmp_path / "joblist.json"
    save_joblist_state([], [item], path)
    calls = []

    def runner(item, *_args):
        calls.append(item.item_id)
        return LocalJobExecutionResult(STATUS_COMPLETED, "done", str(tmp_path), "test")

    with running_control_plane(tmp_path, joblist_path=path, local_job_runner=runner) as runtime:
        original = threading.Thread.start

        def fail(thread):
            if thread.name.startswith("AbaqusLocalJob-"):
                raise RuntimeError("simulated thread admission failure")
            original(thread)

        monkeypatch.setattr(threading.Thread, "start", fail)
        assert runtime_control(runtime, "start")[0] == 202
        wait_until(lambda: "simulated thread admission failure" in runtime_snapshot(runtime)["schedulerMessage"])
        saved = load_joblist_state(path, restore_active_state=False)[1][0]
        assert saved.status == STATUS_PENDING_RUN and not saved.attempt_id
        assert not calls and not runtime_snapshot(runtime)["operations"]
        monkeypatch.setattr(threading.Thread, "start", original)
        assert runtime_control(runtime, "start")[0] == 202
        wait_until(lambda: not runtime_snapshot(runtime)["active"])
        assert calls == [item.item_id]


def test_duplicate_progress_is_quiet_and_finished_callback_cannot_revert_result(tmp_path):
    item = queue_item(tmp_path, "progress")
    path = tmp_path / "joblist.json"
    save_joblist_state([], [item], path)
    callbacks, event_counts = [], []

    def runner(item, policy, controller, progress, log):
        callbacks.append(progress)
        for _ in range(2):
            progress("solving", "unchanged", 50, "")
            event_counts.append(len(runtime.local_queue_runtime._scheduling.repository.load_events(job_id=item.job_id)))
        return LocalJobExecutionResult(STATUS_COMPLETED, "done", str(tmp_path), "test")

    with running_control_plane(tmp_path, joblist_path=path, local_job_runner=runner) as runtime:
        assert runtime_control(runtime, "start")[0] == 202
        wait_until(lambda: not runtime_snapshot(runtime)["active"])
        assert event_counts[0] == event_counts[1]
        before = path.read_bytes()
        callbacks[0]("solving", "late callback", 50, "")
        assert path.read_bytes() == before
        assert runtime_snapshot(runtime)["operations"][0]["status"] == STATUS_COMPLETED


def test_unknown_requires_observation_before_explicit_requeue(tmp_path):
    item = queue_item(tmp_path, "observe")
    item.status = STATUS_RUNNING
    path = tmp_path / "joblist.json"
    save_joblist_state([], [item], path)
    with running_control_plane(tmp_path, joblist_path=path, external_job_scanner=lambda *_args: ([], []),
                               external_monitor_interval=999) as runtime:
        for action in ("requeueQueueItems", "removeQueueItems"):
            payload = {"schemaVersion": 1, "action": action, "itemIds": [item.item_id]}
            assert api_request(runtime, "/api/v1/job-queue-commands", method="POST", payload=payload)[0] == 409
        runtime.job_queue_service.refresh_external_jobs()
        saved = load_joblist_state(path, restore_active_state=False)[1][0]
        assert saved.status == STATUS_PENDING_CONFIRM
        response = api_request(runtime, "/api/v1/job-queue-commands", method="POST",
                               payload={"schemaVersion": 1, "action": "requeueQueueItems", "itemIds": [item.item_id]})
        assert response[0] == 200
        assert load_joblist_state(path, restore_active_state=False)[1][0].status == STATUS_PENDING_RUN
        assert runtime_snapshot(runtime)["operations"] == []


def test_progress_persistence_error_does_not_abandon_running_executor(tmp_path, monkeypatch):
    item = queue_item(tmp_path, "progress_write_error")
    path = tmp_path / "joblist.json"
    save_joblist_state([], [item], path)
    continued = []

    def runner(item, policy, controller, progress, log):
        progress("solving", "running", 50, "")
        continued.append(True)
        return LocalJobExecutionResult(STATUS_COMPLETED, "done", str(tmp_path), "test")

    with running_control_plane(tmp_path, joblist_path=path, local_job_runner=runner) as runtime:
        manager = runtime.local_queue_runtime
        original = manager._update_queue_item

        def fail_progress(*args, **kwargs):
            if not kwargs.get("clear_active"):
                raise OSError("progress write locked")
            return original(*args, **kwargs)

        monkeypatch.setattr(manager, "_update_queue_item", fail_progress)
        assert runtime_control(runtime, "start")[0] == 202
        wait_until(lambda: runtime_snapshot(runtime)["operations"] and
                   not runtime_snapshot(runtime)["operations"][0]["active"])
        assert continued == [True]
        assert load_joblist_state(path, restore_active_state=False)[1][0].status == STATUS_COMPLETED
        assert "progress write locked" in runtime_snapshot(runtime)["schedulerMessage"]


def test_unknown_executor_outcome_is_not_failure_or_permission_to_stop_backend(tmp_path):
    item = queue_item(tmp_path, "uncertain")
    path = tmp_path / "joblist.json"
    save_joblist_state([], [item], path)

    def runner(*_args):
        return LocalJobExecutionResult(STATUS_UNKNOWN, "no terminal evidence", str(tmp_path), "test")

    with running_control_plane(tmp_path, joblist_path=path, local_job_runner=runner,
                               external_job_scanner=lambda *_args: ([], []), external_monitor_interval=999) as runtime:
        manager = runtime.local_queue_runtime
        assert runtime_control(runtime, "start")[0] == 202
        wait_until(lambda: not runtime_snapshot(runtime)["active"])
        manager._runs[item.item_id].thread.join(2)
        assert manager._scheduling.core.get(item.job_id).state == JobState.LOST
        assert load_joblist_state(path, restore_active_state=False)[1][0].scheduler_state == "LOST"
        assert not manager.prepare_shutdown(reserve=False)["safeToStop"]
        assert runtime_snapshot(runtime)["operations"][0]["phase"] == "unknown"
        runtime.job_queue_service.refresh_external_jobs()
        assert load_joblist_state(path, restore_active_state=False)[1][0].status == STATUS_PENDING_CONFIRM
        assert manager.prepare_shutdown(reserve=False)["safeToStop"]


def test_unreadable_queue_keeps_backend_available_and_can_be_repaired(tmp_path):
    path = tmp_path / "joblist.json"
    path.write_text("{broken", encoding="utf-8")
    calls = []

    def runner(item, *_args):
        calls.append(item.item_id)
        return LocalJobExecutionResult(STATUS_COMPLETED, "done", str(tmp_path), "test")

    with running_control_plane(tmp_path, joblist_path=path, local_job_runner=runner) as runtime:
        assert api_request(runtime, "/healthz")[0] == 200
        assert api_request(runtime, "/api/v1/local-queue-runtime")[0] == 500
        assert path.read_text(encoding="utf-8") == "{broken"
        item = queue_item(tmp_path, "repaired")
        save_joblist_state([], [item], path)
        assert runtime_control(runtime, "start")[0] == 202
        wait_until(lambda: not runtime_snapshot(runtime)["active"])
        assert calls == [item.item_id]


def test_observed_active_job_with_unknown_core_count_does_not_count_as_zero(tmp_path):
    external, pending = queue_item(tmp_path, "external"), queue_item(tmp_path, "pending")
    external.is_external = True
    external.cores = 0
    path = tmp_path / "joblist.json"
    save_joblist_state([], [external, pending], path)
    service = JobQueueService(path, external_monitor_interval=999)
    scheduler = LocalQueueScheduling(service, lambda: LocalSchedulingResources(8, 16 * GB))
    try:
        service.runtime_transaction(lambda _candidates, items: setattr(items[0], "status", STATUS_RUNNING))
        assert scheduler.reserve([pending.item_id], 2, set()) == []
        assert load_joblist_state(path, restore_active_state=False)[1][1].pending_reason == "CPU_LIMIT"
    finally:
        scheduler.close()
        service.close()
