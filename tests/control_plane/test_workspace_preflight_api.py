"""Production preparation refusal through HTTP, queue persistence and restart."""
from __future__ import annotations

from modules.submitter.constants import STATUS_FAILED, STATUS_PENDING_RUN
from modules.submitter.local_job_execution import execute_local_job
from modules.submitter.queue_store import save_joblist_state
from tests.control_plane.test_api import json_response, running_control_plane
from tests.control_plane.test_local_queue_runtime_api import (
    runtime_control,
    runtime_snapshot,
    wait_until,
)
from tests.submitter.test_local_workspace_safety import content, fixture


def test_locked_workspace_refusal_is_persisted_without_mutation_or_automatic_retry(tmp_path):
    source, work, item = fixture(tmp_path)
    (work / "case.lck").touch()
    item.status = STATUS_PENDING_RUN
    joblist = tmp_path / "joblist.json"
    save_joblist_state([], [item], joblist)
    before_source, before_work = content(source), content(work)
    calls = []

    def guarded_runner(item, policy, controller, progress, log):
        calls.append(item.attempt_id)

        def reject_launch(*_args, **_kwargs):
            raise RuntimeError("Fixture forbids all launcher creation")

        controller.start = reject_launch
        return execute_local_job(item, policy, controller, progress, log)

    options = {
        "joblist_path": joblist, "local_job_runner": guarded_runner,
        "server_profiles_path": tmp_path / "profiles.json",
        "odb_result_graph_path": tmp_path / "graph.json",
    }
    with running_control_plane(tmp_path, **options) as runtime:
        assert runtime_control(runtime, "start", maxParallel=1, existingResultPolicy="backup")[0] == 202
        wait_until(lambda: runtime_snapshot(runtime)["queue"]["statusCounts"] == {STATUS_FAILED: 1}, timeout=10)
        wait_until(lambda: not runtime_snapshot(runtime)["active"])
        failed = runtime_snapshot(runtime)["queue"]["queueItems"][0]
        assert "同名 LCK" in failed["message"] and failed["attemptId"]
    assert content(source) == before_source and content(work) == before_work
    assert calls == [failed["attemptId"]]
    with running_control_plane(tmp_path, **options) as runtime:
        restored = runtime_snapshot(runtime)["queue"]["queueItems"][0]
        assert restored["status"] == STATUS_FAILED and restored["attemptId"] == failed["attemptId"]
        response = runtime_control(runtime, "start")
        assert response[0] == 409
        assert json_response(response)["error"]["code"] == "NO_PENDING_LOCAL_JOBS"
        wait_until(lambda: not runtime_snapshot(runtime)["active"])
        assert calls == [failed["attemptId"]]
    assert content(source) == before_source and content(work) == before_work
