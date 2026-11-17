from __future__ import annotations

import threading
from concurrent.futures import Future

import pytest

from modules.submitter.constants import STATUS_COMPLETED, STATUS_PENDING_RUN
from modules.submitter.local_job_execution import LocalJobExecutionResult
from modules.submitter.queue_store import save_joblist_state
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_local_queue_runtime_api import (
    queue_item,
    runtime_control,
    wait_until,
)
from tests.control_plane.test_postprocessing_api import _scan_payload, _settings
from tests.control_plane.test_remote_servers_api import FakeRemoteManager
from tests.control_plane.test_remote_transfers_api import _connect


def shutdown(runtime):
    response = api_request(runtime, "/api/v1/odb-upgrade-shutdown-check", method="POST")
    assert response[0] == 200
    state = json_response(response)
    assert state["scope"] == "all-workers-v1"
    return state


def assert_unreserved(runtime):
    context = runtime.httpd.context
    assert not context.odb_merge_manager._closed
    assert not context.odb_upgrade_manager._closed
    assert not context.odb_result_batch_manager._closed
    assert not context.local_queue_runtime._closing
    assert not context.postprocess_manager._shutdown_reserved


def test_running_local_job_and_final_persistence_prevent_shutdown(tmp_path, monkeypatch):
    item = queue_item(tmp_path, "case")
    joblist = tmp_path / "joblist.json"
    save_joblist_state([], [item], joblist)
    solving, release_solver = threading.Event(), threading.Event()
    saving, release_save = threading.Event(), threading.Event()

    def runner(item, policy, controller, progress, log):
        solving.set()
        assert release_solver.wait(10)
        assert not controller.cancel_requested
        return LocalJobExecutionResult(STATUS_COMPLETED, "done", str(tmp_path), "test")

    with running_control_plane(tmp_path, joblist_path=joblist, local_job_runner=runner) as runtime:
        manager = runtime.local_queue_runtime
        update = manager._update_queue_item

        def persist(*args, **kwargs):
            if kwargs.get("clear_active"):
                saving.set()
                assert release_save.wait(10)
            update(*args, **kwargs)

        monkeypatch.setattr(manager, "_update_queue_item", persist)
        try:
            assert runtime_control(runtime, "start")[0] == 202
            assert solving.wait(5)
            assert runtime_control(runtime, "stop")[0] == 202
            active = shutdown(runtime)
            assert not active["safeToStop"]
            assert any(x["kind"] == "local.job" for x in active["operations"])
            assert_unreserved(runtime)
            release_solver.set()
            assert saving.wait(5)
            assert not shutdown(runtime)["safeToStop"]  # Terminal status, live saving thread.
            release_save.set()
            wait_until(lambda: shutdown(runtime)["safeToStop"])
            assert runtime_control(runtime, "start")[0] == 503
        finally:
            release_solver.set()
            release_save.set()
            for record in manager._runs.values():
                if record.thread is not None:
                    record.thread.join(5)


def test_stop_between_dispatch_selection_and_launch_does_not_start_job(tmp_path, monkeypatch):
    item = queue_item(tmp_path, "pending")
    joblist = tmp_path / "joblist.json"
    save_joblist_state([], [item], joblist)
    selected, release = threading.Event(), threading.Event()
    calls = []

    def runner(*args):
        calls.append(args)
        return LocalJobExecutionResult(STATUS_COMPLETED, "done", str(tmp_path), "test")

    with running_control_plane(tmp_path, joblist_path=joblist, local_job_runner=runner) as runtime:
        manager = runtime.local_queue_runtime
        refresh = manager._refresh_dependencies

        def select():
            result = refresh()
            selected.set()
            assert release.wait(10)
            return result

        monkeypatch.setattr(manager, "_refresh_dependencies", select)
        try:
            assert runtime_control(runtime, "start")[0] == 202
            assert selected.wait(5)
            assert runtime_control(runtime, "stop")[0] == 202
            assert not shutdown(runtime)["safeToStop"]
            release.set()
            wait_until(lambda: shutdown(runtime)["safeToStop"])
            assert not calls
            assert manager.queue_service.runtime_items()[1][0].status == STATUS_PENDING_RUN
        finally:
            release.set()


@pytest.mark.parametrize("manager_name", ["operation_manager", "result_index_manager",
                                        "postprocess_manager", "remote_transfer_manager",
                                        "remote_job_manager"])
def test_worker_cleanup_future_blocks_joint_reservation(tmp_path, manager_name):
    # Exercise the gap between a terminal result and completion of its worker.
    with running_control_plane(tmp_path) as runtime:
        manager = getattr(runtime.httpd.context, manager_name)
        future = Future()
        manager._futures["cleanup"] = future
        try:
            state = shutdown(runtime)
            assert not state["safeToStop"]
            assert state["operations"][0]["status"] == "finishing"
            assert_unreserved(runtime)
        finally:
            future.set_result(None)
        assert shutdown(runtime)["safeToStop"]
        assert manager._shutdown_reserved
        # Reserved managers still perform their normal executor cleanup.
        manager.close()
        assert manager._closed
        assert manager._executor._shutdown


def test_postprocess_cancel_waits_for_actual_worker_cleanup(tmp_path):
    source = tmp_path / "case.odb"
    source.write_bytes(b"fixture")
    started, release = threading.Event(), threading.Event()

    def scanner(request, progress, log, controller):
        started.set()
        assert release.wait(10)
        return {"items": [], "count": 0}

    with running_control_plane(tmp_path, postprocess_scan_runner=scanner,
                               postprocess_settings_provider=_settings) as runtime:
        try:
            response = api_request(runtime, "/api/v1/odb-postprocess-scans", method="POST",
                                   payload=_scan_payload(tmp_path, source))
            assert response[0] == 202
            operation_id = json_response(response)["operationId"]
            assert started.wait(5)
            assert not shutdown(runtime)["safeToStop"]
            assert api_request(runtime, f"/api/v1/odb-postprocess-operations/{operation_id}/cancel",
                               method="POST")[0] == 202
            assert not shutdown(runtime)["safeToStop"]
            assert_unreserved(runtime)
            release.set()
            wait_until(lambda: shutdown(runtime)["safeToStop"])
            assert api_request(runtime, "/api/v1/odb-postprocess-scans", method="POST",
                               payload=_scan_payload(tmp_path, source, "later"))[0] == 503
        finally:
            release.set()


def test_active_transfer_is_retained_and_new_transfer_rejected_after_reservation(tmp_path):
    started, release = threading.Event(), threading.Event()

    class Remote(FakeRemoteManager):
        def upload_file(self, *args, **kwargs):
            started.set()
            assert release.wait(10)
            assert not kwargs["cancel_requested"]()
            return super().upload_file(*args, **kwargs)

    with running_control_plane(tmp_path, remote_manager=Remote(),
                               server_profiles_path=tmp_path / "profiles.json") as runtime:
        _connect(runtime)
        payload = {"schemaVersion": 1, "clientRequestId": "upload", "direction": "upload",
                   "source": str(tmp_path / "case.inp"), "destination": r"D:\Abaqus_Cal\case.inp",
                   "overwrite": False}
        try:
            assert api_request(runtime, "/api/v1/remote-transfers", method="POST", payload=payload)[0] == 202
            assert started.wait(5)
            assert not shutdown(runtime)["safeToStop"]
            assert_unreserved(runtime)
            release.set()
            wait_until(lambda: shutdown(runtime)["safeToStop"])
            payload["clientRequestId"] = "later"
            assert api_request(runtime, "/api/v1/remote-transfers", method="POST", payload=payload)[0] == 503
        finally:
            release.set()


def test_idle_reservation_rejects_compatibility_index_and_remote_job_requests(tmp_path):
    source = tmp_path / "case.odb"
    source.write_bytes(b"fixture")
    inp = tmp_path / "case.inp"
    inp.write_text("*Heading\n", encoding="utf-8")
    batch = tmp_path / "results" / "batch"
    batch.mkdir(parents=True)
    with running_control_plane(tmp_path, remote_manager=FakeRemoteManager(),
                               server_profiles_path=tmp_path / "profiles.json") as runtime:
        _connect(runtime)
        assert shutdown(runtime)["safeToStop"]
        requests = [
            ("/api/v1/odb-compatibility-checks", {"root": str(tmp_path), "paths": [str(source)],
                                                "forceRescan": False}),
            ("/api/v1/result-index-builds", {"root": str(tmp_path), "timeDirectory": str(batch)}),
            ("/api/v1/remote-jobs", {"jobName": "case", "inputMode": "upload", "inputPath": str(inp),
                                     "oldjobPath": "", "fortranPath": "", "cpus": 4,
                                     "memory": "90%", "datacheck": False}),
        ]
        for route, fields in requests:
            response = api_request(runtime, route, method="POST",
                                   payload={"schemaVersion": 1, "clientRequestId": "later", **fields})
            assert response[0] == 503, (route, response)
            assert json_response(response)["error"]["code"] == "CONTROL_PLANE_SHUTTING_DOWN"
