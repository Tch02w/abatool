from __future__ import annotations

import threading
import time
from pathlib import Path

from modules.submitter.constants import (
    STATUS_COMPLETED,
    STATUS_PENDING_RUN,
    STATUS_TERMINATED,
)
from modules.submitter.local_job_execution import LocalJobExecutionResult
from modules.submitter.models import QueueItem
from modules.submitter.queue_store import save_joblist_state
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)


def runtime_control(runtime, action: str, **fields: object):
    return api_request(
        runtime,
        "/api/v1/local-queue-controls",
        method="POST",
        payload={"schemaVersion": 1, "action": action, **fields},
    )


def runtime_snapshot(runtime) -> dict:
    return json_response(api_request(runtime, "/api/v1/local-queue-runtime"))


def wait_until(predicate, timeout: float = 4.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.03)
    raise AssertionError("condition did not become true")


def queue_item(tmp_path: Path, name: str) -> QueueItem:
    inp = tmp_path / f"{name}.inp"
    inp.write_text("*Heading\n", encoding="utf-8")
    return QueueItem(
        inp_path=str(inp),
        source_inp_path=str(inp),
        job_name=name,
        status=STATUS_PENDING_RUN,
        message="待提交",
        selected=False,
        cores=1,
    )


def test_local_queue_runs_up_to_parallel_limit_and_persists_completion(
    tmp_path: Path,
) -> None:
    joblist = tmp_path / "joblist.json"
    items = [queue_item(tmp_path, "one"), queue_item(tmp_path, "two")]
    save_joblist_state([], items, joblist)
    release = threading.Event()
    active = 0
    maximum_active = 0
    gate = threading.Lock()

    def runner(item, policy, controller, progress, log):
        nonlocal active, maximum_active
        assert policy == "backup"
        with gate:
            active += 1
            maximum_active = max(maximum_active, active)
        progress("solving", "运行中", 50, "Step 1")
        log(f"running {item.job_name}")
        assert release.wait(timeout=3)
        with gate:
            active -= 1
        return LocalJobExecutionResult(
            STATUS_COMPLETED,
            "完成",
            str(Path(item.inp_path).parent),
            "fake",
        )

    with running_control_plane(
        tmp_path,
        joblist_path=joblist,
        local_job_runner=runner,
    ) as runtime:
        started = runtime_control(
            runtime,
            "start",
            maxParallel=2,
            existingResultPolicy="backup",
        )
        assert started[0] == 202
        wait_until(lambda: len(runtime_snapshot(runtime)["activeItemIds"]) == 2)
        release.set()
        wait_until(lambda: runtime_snapshot(runtime)["active"] is False)
        snapshot = runtime_snapshot(runtime)

    assert maximum_active == 2
    assert snapshot["queue"]["statusCounts"] == {STATUS_COMPLETED: 2}
    assert all(operation["logs"] for operation in snapshot["operations"])


def test_stop_prevents_new_dispatch_without_terminating_running_job(
    tmp_path: Path,
) -> None:
    joblist = tmp_path / "joblist.json"
    items = [queue_item(tmp_path, "one"), queue_item(tmp_path, "two")]
    save_joblist_state([], items, joblist)
    release = threading.Event()

    def runner(item, policy, controller, progress, log):
        progress("solving", "运行中", 50, "")
        assert release.wait(timeout=3)
        return LocalJobExecutionResult(
            STATUS_COMPLETED,
            "完成",
            str(Path(item.inp_path).parent),
            "fake",
        )

    with running_control_plane(
        tmp_path,
        joblist_path=joblist,
        local_job_runner=runner,
    ) as runtime:
        runtime_control(
            runtime,
            "start",
            maxParallel=1,
            existingResultPolicy="backup",
        )
        wait_until(lambda: len(runtime_snapshot(runtime)["activeItemIds"]) == 1)
        stopped = runtime_control(runtime, "stop")
        assert json_response(stopped)["stopRequested"] is True
        release.set()
        wait_until(lambda: not runtime_snapshot(runtime)["activeItemIds"])
        snapshot = runtime_snapshot(runtime)

    assert snapshot["active"] is False
    assert snapshot["queue"]["statusCounts"] == {
        STATUS_COMPLETED: 1,
        STATUS_PENDING_RUN: 1,
    }


def test_terminate_selected_active_job_reaches_terminated_state(tmp_path: Path) -> None:
    joblist = tmp_path / "joblist.json"
    item = queue_item(tmp_path, "one")
    save_joblist_state([], [item], joblist)

    def runner(item, policy, controller, progress, log):
        progress("solving", "运行中", 50, "")
        while not controller.cancel_requested:
            time.sleep(0.02)
        return LocalJobExecutionResult(
            STATUS_TERMINATED,
            "用户手动终止",
            str(Path(item.inp_path).parent),
            "fake",
        )

    with running_control_plane(
        tmp_path,
        joblist_path=joblist,
        local_job_runner=runner,
    ) as runtime:
        runtime_control(
            runtime,
            "start",
            maxParallel=1,
            existingResultPolicy="backup",
        )
        wait_until(lambda: runtime_snapshot(runtime)["activeItemIds"] == [item.item_id])
        terminated = runtime_control(runtime, "terminate", itemIds=[item.item_id])
        assert terminated[0] == 202
        wait_until(lambda: not runtime_snapshot(runtime)["activeItemIds"])
        snapshot = runtime_snapshot(runtime)

    assert snapshot["queue"]["statusCounts"] == {STATUS_TERMINATED: 1}
    assert snapshot["operations"][0]["status"] == STATUS_TERMINATED
