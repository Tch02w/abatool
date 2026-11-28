from concurrent.futures import ThreadPoolExecutor
import json
import threading

import pytest

from modules.control_plane import local_queue_termination as termination
from modules.submitter.constants import (
    STATUS_CANCELED, STATUS_COMPLETED, STATUS_FAILED, STATUS_PENDING_CONFIRM, STATUS_PENDING_RUN,
    STATUS_TERMINATING, STATUS_UNKNOWN, STATUS_WAITING_DEPENDENCY,
)
from modules.submitter.local_job_execution import LocalJobExecutionResult
from modules.submitter.queue_store import save_joblist_state
from modules.submitter.scheduling import JobState
from tests.control_plane.test_api import json_response, running_control_plane
from tests.control_plane.test_local_queue_runtime_api import queue_item, runtime_control, runtime_snapshot, wait_until


def preview(runtime):
    answer = runtime_control(runtime, "previewTerminateAll")
    assert answer[0] == 202
    return json_response(answer)


def confirm(runtime, proposal):
    return runtime_control(runtime, "terminateAll", confirmationId=proposal["confirmationId"])


def queue_status(runtime):
    return {item["jobName"]: item["status"] for item in runtime_snapshot(runtime)["queue"]["queueItems"]}


def append_item(runtime, item):
    runtime.local_queue_runtime.queue_service.runtime_transaction(lambda _c, items: items.append(item))


def test_whole_queue_confirm_exact_scope_replay_and_restart(tmp_path):
    pending, held, waiting, done, failed, outside, unknown, unconfirmed = [
        queue_item(tmp_path, name) for name in
        ("pending", "held", "waiting", "done", "failed", "outside", "unknown", "unconfirmed")]
    held.held, waiting.status = True, STATUS_WAITING_DEPENDENCY
    done.status, failed.status = STATUS_COMPLETED, STATUS_FAILED
    outside.is_external, outside.status = True, STATUS_PENDING_RUN
    unknown.status, unconfirmed.status = STATUS_UNKNOWN, STATUS_PENDING_CONFIRM
    save_joblist_state([queue_item(tmp_path, "candidate")],
                       [pending, held, waiting, done, failed, outside, unknown, unconfirmed], tmp_path / "joblist.json")
    with running_control_plane(tmp_path) as runtime:
        first = preview(runtime)
        assert {row["jobName"] for row in first["pending"]} == {"pending", "held", "waiting"}
        assert first["untouchedCount"] == 5 and not first["running"] and not first["schedulingActive"]
        assert all(row["attemptId"] == "" for row in first["pending"])
        assert {row["inpPath"] for row in first["pending"]} == {item.inp_path for item in (pending, held, waiting)}
        before = queue_status(runtime)
        late = queue_item(tmp_path, "late")
        append_item(runtime, late)
        stale = confirm(runtime, first)
        assert stale[0] == 409 and json_response(stale)["error"]["code"] == "LOCAL_QUEUE_TERMINATION_SCOPE_CHANGED"
        assert queue_status(runtime) == dict(before, late=STATUS_PENDING_RUN)
        proposal = preview(runtime)
        with ThreadPoolExecutor(max_workers=2) as pool:
            answers = list(pool.map(lambda _: confirm(runtime, proposal), range(2)))
        receipt = json_response(answers[0])
        assert all(answer[0] == 202 and json_response(answer) == receipt for answer in answers)
        assert receipt == {"schemaVersion": 1, "status": "accepted", "confirmationId": proposal["confirmationId"],
                           "pendingCancelled": 4, "terminationRequested": 0, "untouchedCount": 5}
        states = queue_status(runtime)
        assert states == {**before, **dict.fromkeys(("pending", "held", "waiting", "late"), STATUS_CANCELED)}
        assert runtime.local_queue_runtime._scheduling.core.get(late.job_id).state == JobState.CANCELED
        assert runtime_snapshot(runtime)["queue"]["candidates"][0]["jobName"] == "candidate"
        after = queue_item(tmp_path, "after")
        append_item(runtime, after)
        assert json_response(confirm(runtime, proposal)) == receipt
        assert queue_status(runtime)["after"] == STATUS_PENDING_RUN
    with running_control_plane(tmp_path) as runtime:
        assert json_response(confirm(runtime, proposal)) == receipt
        assert queue_status(runtime)["after"] == STATUS_PENDING_RUN
    with running_control_plane(tmp_path, joblist_path=tmp_path / "other-list.json") as runtime:
        assert confirm(runtime, proposal)[0] == 409


def test_current_attempt_only_and_natural_terminal_wins(tmp_path):
    work, held = (queue_item(tmp_path, name) for name in ("work", "held"))
    held.held = True
    save_joblist_state([], [work, held], tmp_path / "joblist.json")
    started, finish = threading.Event(), threading.Event()
    controllers = []

    def runner(item, policy, controller, progress, log):
        controllers.append(controller)
        progress("solving", "运行中", 50, "")
        started.set()
        assert finish.wait(10)
        return LocalJobExecutionResult(STATUS_COMPLETED, "求解已完成", str(tmp_path), "")

    with running_control_plane(tmp_path, local_job_runner=runner) as runtime:
        try:
            earlier = preview(runtime)
            assert runtime_control(runtime, "start")[0] == 202 and started.wait(5)
            stale = confirm(runtime, earlier)
            assert stale[0] == 409 and not controllers[0].cancel_requested
            assert runtime_snapshot(runtime)["active"] and queue_status(runtime)["held"] == STATUS_PENDING_RUN
            proposal = preview(runtime)
            assert proposal["running"][0]["itemId"] == work.item_id and proposal["running"][0]["attemptId"]
            assert not proposal["running"][0]["archiveOnly"]
            receipt = json_response(confirm(runtime, proposal))
            assert (receipt["pendingCancelled"], receipt["terminationRequested"]) == (1, 1)
            assert controllers[0].cancel_requested and not runtime_snapshot(runtime)["active"]
            assert queue_status(runtime) == {"work": STATUS_TERMINATING, "held": STATUS_CANCELED}
            append_item(runtime, queue_item(tmp_path, "after"))
        finally:
            finish.set()
        wait_until(lambda: not runtime_snapshot(runtime)["activeItemIds"])
        assert queue_status(runtime) == {"work": STATUS_COMPLETED, "held": STATUS_CANCELED, "after": STATUS_PENDING_RUN}
        assert json_response(confirm(runtime, proposal)) == receipt


@pytest.mark.parametrize("stage,expected", [("applying", STATUS_PENDING_RUN), ("accepted", STATUS_CANCELED)])
def test_receipt_write_failure_never_authorizes_repeat(tmp_path, monkeypatch, stage, expected):
    item = queue_item(tmp_path, "one")
    save_joblist_state([], [item], tmp_path / "joblist.json")
    write = termination.save_json_mapping

    def fail(path, data):
        if data["status"] == stage:
            raise OSError("fixture write failed")
        write(path, data)

    with running_control_plane(tmp_path) as runtime:
        proposal = preview(runtime)
        with monkeypatch.context() as patch:
            patch.setattr(termination, "save_json_mapping", fail)
            failed = confirm(runtime, proposal)
            assert failed[0] == 409 and json_response(failed)["error"]["code"] == "LOCAL_QUEUE_TERMINATION_INTERRUPTED"
        assert queue_status(runtime)["one"] == expected
        if stage == "accepted":
            append_item(runtime, queue_item(tmp_path, "after"))
            assert confirm(runtime, proposal)[0] == 409 and queue_status(runtime)["after"] == STATUS_PENDING_RUN
    with running_control_plane(tmp_path) as runtime:
        assert confirm(runtime, proposal)[0] == 409


def test_inactive_empty_scope_and_malformed_tokens(tmp_path):
    with running_control_plane(tmp_path) as runtime:
        empty = preview(runtime)
        assert not empty["running"] and not empty["pending"]
        assert confirm(runtime, empty)[0] == 409
        for token in ("../invalid", None, 7):
            assert runtime_control(runtime, "terminateAll", confirmationId=token)[0] == 400
        assert runtime_control(runtime, "terminateAll", confirmationId="f" * 32)[0] == 409


def test_result_persistence_is_not_a_cancellable_attempt(tmp_path, monkeypatch):
    item = queue_item(tmp_path, "one")
    save_joblist_state([], [item], tmp_path / "joblist.json")
    started, finish = threading.Event(), threading.Event()
    writing, release = threading.Event(), threading.Event()
    controllers = []

    def runner(_item, _policy, controller, _progress, _log):
        controllers.append(controller)
        started.set()
        assert finish.wait(10)
        return LocalJobExecutionResult(STATUS_FAILED, "求解已失败", str(tmp_path), "")

    with running_control_plane(tmp_path, local_job_runner=runner) as runtime:
        manager = runtime.local_queue_runtime
        flush = manager._flush_observations

        def gated_flush(*, force=False):
            if force:
                writing.set()
                assert release.wait(10)
            return flush(force=force)

        monkeypatch.setattr(manager, "_flush_observations", gated_flush)
        try:
            assert runtime_control(runtime, "start")[0] == 202 and started.wait(5)
            previous = preview(runtime)
            finish.set()
            assert writing.wait(5)
            assert confirm(runtime, previous)[0] == 409
            assert runtime_control(runtime, "terminate", itemIds=[item.item_id])[0] == 409
            current = preview(runtime)
            assert not current["running"] and current["schedulingActive"]
            assert json_response(confirm(runtime, current))["terminationRequested"] == 0
            assert not controllers[0].cancel_requested
        finally:
            release.set()
            finish.set()
        wait_until(lambda: not runtime_snapshot(runtime)["activeItemIds"])
        assert queue_status(runtime)["one"] == STATUS_FAILED


def test_damaged_accepted_receipt_never_returns_success(tmp_path):
    item = queue_item(tmp_path, "one")
    save_joblist_state([], [item], tmp_path / "joblist.json")
    with running_control_plane(tmp_path) as runtime:
        proposal = preview(runtime)
        original = json_response(confirm(runtime, proposal))
        path = tmp_path / "local-queue-terminations" / "joblist.json" / (proposal["confirmationId"] + ".json")
        for changed in ({"terminationRequested": -1}, {"pendingCancelled": False}, {"untouchedCount": None}):
            path.write_text(json.dumps(original | changed), encoding="utf-8")
            response = confirm(runtime, proposal)
            assert response[0] == 409 and json_response(response)["error"]["code"] == "LOCAL_QUEUE_TERMINATION_INTERRUPTED"
