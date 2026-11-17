from __future__ import annotations

import threading
from http.client import RemoteDisconnected

import pytest

from modules.control_plane.server import ControlPlaneRequestHandler
from modules.postprocessor.process_runner import ProcessCancelled
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_local_queue_runtime_api import wait_until
from tests.control_plane.test_postprocessing_api import _scan_payload, _settings

BASE = "/api/v1/shutdown-requests"


def test_committed_idle_backend_exits_even_if_response_socket_is_lost(tmp_path, monkeypatch):
    original = ControlPlaneRequestHandler._send_json

    def lose_commit(self, status, payload, trace_id):
        if payload.get("state") == "committed":
            self.close_connection = True
            raise BrokenPipeError("client disappeared after commit")
        return original(self, status, payload, trace_id)

    monkeypatch.setattr(ControlPlaneRequestHandler, "_send_json", lose_commit)
    with running_control_plane(tmp_path) as runtime:
        prepare(runtime)
        with pytest.raises(RemoteDisconnected):
            action(runtime, "commit", mode="idle")
        wait_until(lambda: not runtime.descriptor_path.exists())
        assert runtime._closed


def prepare(runtime, request_id="close-1"):
    result = api_request(runtime, BASE, method="POST", payload={"schemaVersion": 1, "clientRequestId": request_id})
    assert result[0] == 200, result
    return json_response(result)


def action(runtime, name, *, request_id="close-1", **fields):
    return api_request(runtime, f"{BASE}/{request_id}/{name}", method="POST", payload={"schemaVersion": 1, **fields})


def test_prepare_and_abort_preserve_work_and_restore_admission(tmp_path):
    with running_control_plane(tmp_path) as runtime:
        state = prepare(runtime)
        assert state["safeToStop"] and state["state"] == "prepared"
        assert prepare(runtime) == state
        assert api_request(runtime, BASE, method="POST", payload={"schemaVersion": 1, "clientRequestId": "other"})[0] == 409
        assert api_request(runtime, "/api/v1/result-scopes", method="POST", payload={})[0] == 503
        assert action(runtime, "abort", request_id="other")[0] == 409
        assert json_response(action(runtime, "abort"))["state"] == "aborted"
        # Validation resumes; this is an invalid application request, not a close rejection.
        assert api_request(runtime, "/api/v1/result-scopes", method="POST", payload={})[0] == 400
        assert runtime.httpd.context.local_queue_runtime._closing is False
        assert prepare(runtime, "new-close")["state"] == "prepared"
        assert action(runtime, "abort", request_id="new-close")[0] == 200


def test_abandoned_prepare_expires_without_permanently_disabling_work(tmp_path):
    with running_control_plane(tmp_path) as runtime:
        now = [0.0]
        protocol = runtime.httpd.context.shutdown_protocol
        protocol._clock = lambda: now[0]
        prepare(runtime)
        now[0] = 61
        assert api_request(runtime, f"{BASE}/close-1")[0] == 409
        assert api_request(runtime, "/api/v1/result-scopes", method="POST", payload={})[0] == 400
        prepare(runtime, "after-expiry")
        action(runtime, "abort", request_id="after-expiry")


def test_pending_synchronous_write_blocks_commit_and_legacy_kill(tmp_path, monkeypatch):
    started, release = threading.Event(), threading.Event()
    replies = []

    def preview(payload):
        started.set()
        assert release.wait(10)
        return {"schemaVersion": 1}

    monkeypatch.setattr("modules.control_plane.server.preview_local_job_draft", preview)
    with running_control_plane(tmp_path) as runtime:
        thread = threading.Thread(target=lambda: replies.append(api_request(runtime,
            "/api/v1/local-job-draft-previews", method="POST", payload={"schemaVersion": 1})))
        thread.start()
        try:
            assert started.wait(5)
            state = prepare(runtime)
            assert state["pendingRequests"] == 1 and not state["safeToStop"]
            assert action(runtime, "commit", mode="background")[0] == 409
            assert action(runtime, "stop")[0] == 409
            legacy = json_response(api_request(runtime, "/api/v1/odb-upgrade-shutdown-check", method="POST"))
            assert not legacy["safeToStop"]
            release.set()
            thread.join(5)
            assert replies[0][0] == 200
            assert json_response(api_request(runtime, f"{BASE}/close-1"))["safeToStop"]
            action(runtime, "abort")
        finally:
            release.set()
            thread.join(5)


def test_background_commit_does_not_cancel_existing_worker_or_stop_backend(tmp_path):
    started, release = threading.Event(), threading.Event()
    controllers = []
    source = tmp_path / "model.odb"
    source.write_bytes(b"fixture")

    def scanner(request, progress, log, controller):
        controllers.append(controller)
        started.set()
        assert release.wait(10)
        assert not controller.cancel_requested
        return {"items": [], "count": 0}

    with running_control_plane(tmp_path, postprocess_scan_runner=scanner, postprocess_settings_provider=_settings) as runtime:
        try:
            initial = api_request(runtime, "/api/v1/odb-postprocess-scans", method="POST", payload=_scan_payload(tmp_path, source))
            assert initial[0] == 202 and started.wait(5)
            state = prepare(runtime)
            assert not state["safeToStop"] and state["operations"]
            assert not controllers[0].cancel_requested
            assert action(runtime, "commit", mode="idle")[0] == 409
            committed = json_response(action(runtime, "commit", mode="background"))
            assert committed["state"] == "committed" and not committed["stopBackend"]
            assert json_response(action(runtime, "commit", mode="background")) == committed
            assert action(runtime, "commit", mode="stop")[0] == 409
            assert not controllers[0].cancel_requested
            assert api_request(runtime, "/api/v1/result-scopes", method="POST", payload={})[0] == 400
            assert api_request(runtime, "/healthz")[0] == 200
        finally:
            release.set()


def test_stop_waits_for_cleanup_and_cancel_close_does_not_undo_stop(tmp_path):
    started, release = threading.Event(), threading.Event()
    controllers = []
    source = tmp_path / "model.odb"
    source.write_bytes(b"fixture")

    def scanner(request, progress, log, controller):
        controllers.append(controller)
        started.set()
        assert release.wait(10)
        raise ProcessCancelled("test cleanup completed")

    with running_control_plane(tmp_path, postprocess_scan_runner=scanner, postprocess_settings_provider=_settings) as runtime:
        try:
            assert api_request(runtime, "/api/v1/odb-postprocess-scans", method="POST", payload=_scan_payload(tmp_path, source))[0] == 202
            assert started.wait(5)
            prepare(runtime)
            stopping = json_response(action(runtime, "stop"))
            assert stopping["state"] == "stopping" and not stopping["safeToStop"]
            assert controllers[0].cancel_requested
            assert action(runtime, "commit", mode="stop")[0] == 409
            assert json_response(action(runtime, "abort"))["state"] == "aborted"
            assert controllers[0].cancel_requested
            assert api_request(runtime, "/api/v1/result-scopes", method="POST", payload={})[0] == 400
        finally:
            release.set()


def test_idle_commit_stops_the_actual_server_and_removes_descriptor(tmp_path):
    with running_control_plane(tmp_path) as runtime:
        prepare(runtime)
        assert action(runtime, "commit", mode="stop")[0] == 409
        state = json_response(action(runtime, "commit", mode="idle"))
        assert state["stopBackend"] and state["safeToStop"]
        wait_until(lambda: not runtime.descriptor_path.exists())
        assert runtime._closed


def test_protocol_authentication_and_invalid_payloads(tmp_path):
    with running_control_plane(tmp_path) as runtime:
        for method, path in [("POST", BASE), ("GET", BASE + "/close-1"), ("POST", BASE + "/close-1/commit")]:
            assert api_request(runtime, path, method=method, payload={} if method == "POST" else None, token=None)[0] == 401
        for payload in [{}, {"schemaVersion": 1, "clientRequestId": "../../bad"},
                        {"schemaVersion": 1, "clientRequestId": "good", "extra": True}]:
            assert api_request(runtime, BASE, method="POST", payload=payload)[0] == 400
        prepare(runtime)
        assert action(runtime, "commit", mode="force")[0] == 400
        assert action(runtime, "stop", extra=True)[0] == 400
        action(runtime, "abort")
