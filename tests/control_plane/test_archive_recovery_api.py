from __future__ import annotations

import json
import threading

import pytest

from modules.submitter import local_archive_recovery
from modules.submitter.constants import STATUS_COMPLETED, STATUS_RUNNING, STATUS_UNKNOWN
from modules.submitter.local_archive_state import ArchiveStateStore
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
from tests.submitter.test_archive_recovery import recovery_fixture, run_initial
from tests.submitter.test_local_archive import source_bytes


def interrupted_fixture(tmp_path, monkeypatch, phase="prepared"):
    source, item, _ = recovery_fixture(tmp_path)
    item.inp_path = str(source / "case.inp")
    item.status, item.cores = STATUS_RUNNING, 1
    item.abaqus_command = "cmd.exe /c exit 17"  # Even an accidental control cannot invoke Abaqus.
    store = ArchiveStateStore(tmp_path / "archive-state")
    original = store.save

    def stop(item, state):
        original(item, state)
        if state["phase"] == phase:
            raise SystemExit("fixture interruption")

    with monkeypatch.context() as patch:
        patch.setattr(store, "save", stop)
        with pytest.raises(SystemExit):
            run_initial(item, source, store)
    joblist = tmp_path / "joblist.json"
    save_joblist_state([], [item], joblist)
    return source, item, store, joblist


def test_http_archive_recovery_cancel_close_and_edit_guards_without_resolving(tmp_path, monkeypatch):
    source, item, store, joblist = interrupted_fixture(tmp_path, monkeypatch)
    before = source_bytes(source)
    entered, release = threading.Event(), threading.Event()
    original_copy = local_archive_recovery._copy_verified
    solver_calls = []

    def no_solver(*_):
        solver_calls.append(True)
        raise RuntimeError("Archive recovery must never invoke the solve runner")

    def blocking_copy(*args, **kwargs):
        entered.set()
        assert release.wait(15)
        return original_copy(*args, **kwargs)

    monkeypatch.setattr(local_archive_recovery, "_copy_verified", blocking_copy)
    options = {"joblist_path": joblist, "local_job_runner": no_solver,
               "server_profiles_path": tmp_path / "profiles.json", "odb_result_graph_path": tmp_path / "graph.json"}
    with running_control_plane(tmp_path, **options) as runtime:
        row = runtime_snapshot(runtime)["queue"]["queueItems"][0]
        assert row["status"] == STATUS_COMPLETED and row["archiveStatus"] == "归档待恢复"
        assert row["archiveRecoveryAvailable"] and row["attemptId"] == item.attempt_id
        assert runtime_control(runtime, "start")[0] == 409
        try:
            assert runtime_control(runtime, "retryArchive", itemIds=[item.item_id])[0] == 202
            assert entered.wait(10)
            snapshot = runtime_snapshot(runtime)
            assert snapshot["operations"][0]["archiveOnly"] and snapshot["operations"][0]["active"]
            assert snapshot["queue"]["queueItems"][0]["status"] == STATUS_COMPLETED
            assert runtime_control(runtime, "retryArchive", itemIds=[item.item_id])[0] == 409
            assert runtime_control(runtime, "suspend", itemIds=[item.item_id])[0] == 409
            for action, fields in [("removeQueueItems", {"itemIds": [item.item_id]}),
                                   ("requeueQueueItems", {"itemIds": [item.item_id]}), ("clearFinished", {})]:
                result = api_request(runtime, "/api/v1/job-queue-commands", method="POST",
                                     payload={"schemaVersion": 1, "action": action, **fields})
                assert result[0] == 409
            closing = api_request(runtime, "/api/v1/odb-upgrade-shutdown-check", method="POST", payload={})
            assert not json_response(closing)["safeToStop"]
            assert runtime_control(runtime, "terminate", itemIds=[item.item_id])[0] == 202
        finally:
            release.set()
        wait_until(lambda: not any(o["active"] for o in runtime_snapshot(runtime)["operations"]), timeout=10)
        row = runtime_snapshot(runtime)["queue"]["queueItems"][0]
        assert row["status"] == STATUS_COMPLETED and row["archiveStatus"] == "归档已取消"
        assert row["archiveRecoveryAvailable"] and source_bytes(source) == before
        assert runtime_control(runtime, "retryArchive", itemIds=[item.item_id])[0] == 202
        wait_until(lambda: runtime_snapshot(runtime)["queue"]["queueItems"][0]["archiveStatus"] == "已归档", timeout=10)
        wait_until(lambda: not any(o["active"] for o in runtime_snapshot(runtime)["operations"]))
        final = runtime_snapshot(runtime)["queue"]["queueItems"][0]
        assert not final["archiveRecoveryAvailable"] and final["attemptId"] == item.attempt_id
    from modules.control_plane.local_archiving import LocalArchiveRecoveryMixin
    updates = []
    original_update = LocalArchiveRecoveryMixin._set_archive_state

    def tracked_update(self, *args, **kwargs):
        updates.append(args[0].item_id)
        return original_update(self, *args, **kwargs)

    monkeypatch.setattr(LocalArchiveRecoveryMixin, "_set_archive_state", tracked_update)
    with running_control_plane(tmp_path, **options) as runtime:
        restored = runtime_snapshot(runtime)["queue"]["queueItems"][0]
        assert restored["archiveStatus"] == "已归档" and restored["attemptId"] == item.attempt_id
        assert runtime_control(runtime, "retryArchive", itemIds=[item.item_id])[0] == 409
    assert not solver_calls and not source.exists() and store.read(item)["phase"] == "done"
    assert not updates, "Unchanged completed archives must not be rewritten during startup"


@pytest.mark.parametrize("tamper", ["json", "identity", "escape", "files_type", "directories_type"])
def test_corrupt_checkpoint_never_upgrades_unknown_to_success_or_enables_retry(tmp_path, monkeypatch, tamper):
    source, item, store, joblist = interrupted_fixture(tmp_path, monkeypatch)
    before = source_bytes(source)
    state = store.read(item)
    if tamper == "json":
        store.path(item).write_text("broken")
    else:
        if tamper == "identity":
            state["attemptId"] = "other"
        elif tamper == "escape":
            state["files"]["../outside"] = state["files"].pop("case.inp")
        elif tamper == "files_type":
            state["files"] = []
        else:
            state["directories"] = None
        store.path(item).write_text(json.dumps(state))
    with running_control_plane(tmp_path, joblist_path=joblist, server_profiles_path=tmp_path / "profiles.json",
                               odb_result_graph_path=tmp_path / "graph.json") as runtime:
        row = runtime_snapshot(runtime)["queue"]["queueItems"][0]
        assert row["status"] == STATUS_UNKNOWN and row["archiveStatus"] == "归档记录异常"
        assert not row["archiveRecoveryAvailable"]
        assert runtime_control(runtime, "retryArchive", itemIds=[item.item_id])[0] == 409
    assert source_bytes(source) == before
