from __future__ import annotations

from pathlib import Path

import pytest

from modules.submitter.constants import STATUS_COMPLETED, STATUS_PENDING_RUN
from modules.submitter.local_job_execution import _completed_result
from modules.submitter.queue_store import save_joblist_state
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_local_queue_runtime_api import (
    runtime_control,
    runtime_snapshot,
    wait_until,
)
from tests.submitter.test_local_archive import archive_fixture


@pytest.mark.parametrize("fail", [False, True])
def test_archive_outcome_and_output_location_survive_http_restart(tmp_path, fail):
    source, item = archive_fixture(tmp_path, cleanup=True)
    item.inp_path = str(source / "case.inp")
    item.status, item.cores, item.complete_notify = STATUS_PENDING_RUN, 1, True
    item.archive_status, item.archive_destination, item.archive_error = "已归档", "old-archive", "old error"
    if fail:
        Path(item.archive_dir).write_bytes(b"unrelated file")
    joblist = tmp_path / "joblist.json"
    save_joblist_state([], [item], joblist)
    calls = []

    def runner(item, policy, controller, progress, log):
        assert not item.archive_status and not item.archive_destination and not item.archive_error
        calls.append(item.attempt_id)
        return _completed_result(item, source, "no solver fixture", "计算已完成", controller, progress)

    options = {"joblist_path": joblist, "local_job_runner": runner,
               "server_profiles_path": tmp_path / "profiles.json", "odb_result_graph_path": tmp_path / "graph.json"}
    with running_control_plane(tmp_path, **options) as runtime:
        assert runtime_control(runtime, "start")[0] == 202
        wait_until(lambda: runtime_snapshot(runtime)["queue"]["statusCounts"] == {STATUS_COMPLETED: 1}, timeout=10)
        wait_until(lambda: not runtime_snapshot(runtime)["active"])
        row = runtime_snapshot(runtime)["queue"]["queueItems"][0]
        assert row["archiveStatus"] == ("归档失败" if fail else "已归档")
        assert bool(row["archiveError"]) is fail
        assert bool(row["archiveDestination"]) is not fail
        wait_until(lambda: json_response(api_request(runtime, "/api/v1/job-notifications"))["unreadCount"] == 1)
        notice = json_response(api_request(runtime, "/api/v1/job-notifications"))["items"][0]
        assert notice["status"] == "succeeded"  # Computation outcome is independent of archive outcome.
        assert notice["workDirectory"] == (str(source) if fail else row["archiveDestination"])
        if fail:
            assert "归档" in notice["message"] and (source / "case.odb").exists()
    with running_control_plane(tmp_path, **options) as runtime:
        restored = runtime_snapshot(runtime)["queue"]["queueItems"][0]
        for name in ("status", "attemptId", "archiveStatus", "archiveDestination", "archiveError"):
            assert restored[name] == row[name]
        assert runtime_control(runtime, "start")[0] == 409
        assert calls == [row["attemptId"]]
