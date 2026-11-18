from __future__ import annotations

import json
import sqlite3
import time

import pytest

from modules.submitter.remote_connection import RemoteConnectionError
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_remote_servers_api import (
    FakeRemoteManager,
    command,
    profile_payload,
)
from tests.control_plane.test_remote_transfers_api import _connect


class RecoverableRemote(FakeRemoteManager):
    def __init__(self):
        super().__init__()
        self.starts = 0
        self.probes = 0
        self.fail_probe = False
        self.lose_ack = False
        self.complete = False
        self.controls = 0
        self.probe_complete = True

    def execute_powershell(self, script, *, timeout=30):
        if "process_id=[int]$process.Id" in script:
            self.starts += 1
            result = super().execute_powershell(script, timeout=timeout)
            if self.lose_ack:
                self.lose_ack = False
                raise RemoteConnectionError("start acknowledgement lost")
            return result
        if "process_active=$active" in script:
            self.probes += 1
            if self.fail_probe:
                raise RemoteConnectionError("connection interrupted")
            return json.dumps({"process_active": not self.complete, "lock_exists": not self.complete,
                "probe_complete": self.probe_complete, "output_signature": "stable", "sta_tail":
                "THE ANALYSIS HAS COMPLETED SUCCESSFULLY" if self.complete else "increment 1", "log_tail": ""})
        if "exit_code=[int]$process.ExitCode" in script:
            self.controls += 1
            self.complete = True
        return super().execute_powershell(script, timeout=timeout)


def wait_for(check, seconds=7):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(.03)
    pytest.fail("remote recovery condition did not complete")


def request_for(path, identifier="durable"):
    path.write_text("*Heading\n", encoding="ascii")
    return {"schemaVersion": 1, "clientRequestId": identifier, "jobName": "case", "inputMode": "upload",
            "inputPath": str(path), "oldjobPath": "", "fortranPath": "", "cpus": 1, "memory": "90%", "datacheck": False}


def create(runtime, request):
    result = api_request(runtime, "/api/v1/remote-jobs", method="POST", payload=request)
    assert result[0] == 202, result
    return json_response(result)["operationId"]


def view(runtime, operation_id):
    result = api_request(runtime, "/api/v1/remote-jobs/" + operation_id)
    assert result[0] == 200, result
    return json_response(result)


@pytest.mark.parametrize("lose_ack", [False, True])
def test_restart_restores_tracking_without_upload_or_launch_and_without_local_input(tmp_path, lose_ack):
    remote = RecoverableRemote()
    remote.lose_ack = lose_ack
    request = request_for(tmp_path / "case.inp")
    options = {"remote_manager": remote, "server_profiles_path": tmp_path / "profiles.json"}
    with running_control_plane(tmp_path, **options) as runtime:
        _connect(runtime)
        operation_id = create(runtime, request)
        wait_for(lambda: view(runtime, operation_id)["trackingState"] == ("reconnecting" if lose_ack else "tracking"))
        assert remote.starts == 1
    (tmp_path / "case.inp").unlink()  # Owned fixture; uploaded inputs are not needed for tracking.
    with running_control_plane(tmp_path, **options) as runtime:
        restored = view(runtime, operation_id)
        assert restored["status"] == "running" and restored["trackingState"] == "reconnecting"
        assert create(runtime, request) == operation_id  # Retry must not require a local file or connection.
        assert not runtime.httpd.context.remote_job_manager.prepare_shutdown(reserve=False)["safeToStop"]
        assert remote.starts == 1
        _connect(runtime)
        wait_for(lambda: view(runtime, operation_id)["trackingState"] == "tracking")
        remote.complete = True
        wait_for(lambda: view(runtime, operation_id)["status"] == "succeeded")
        assert remote.starts == 1
    with running_control_plane(tmp_path, **options) as runtime:
        assert view(runtime, operation_id)["status"] == "succeeded"
        assert remote.starts == 1


@pytest.mark.parametrize("lose_ack", [False, True])
def test_connection_or_ack_loss_stays_active_and_only_original_identity_can_reconnect(tmp_path, lose_ack):
    remote = RecoverableRemote()
    remote.lose_ack = lose_ack
    with running_control_plane(tmp_path, remote_manager=remote, server_profiles_path=tmp_path / "profiles.json") as runtime:
        _connect(runtime)
        operation_id = create(runtime, request_for(tmp_path / "case.inp"))
        if not lose_ack:
            wait_for(lambda: view(runtime, operation_id)["trackingState"] == "tracking")
            remote.fail_probe = True
        wait_for(lambda: view(runtime, operation_id)["trackingState"] == "reconnecting")
        assert view(runtime, operation_id)["status"] == "running"
        assert not runtime.httpd.context.remote_job_manager.prepare_shutdown(reserve=False)["safeToStop"]
        wrong = profile_payload()
        wrong.update(host="different.example", hostFingerprint="SHA256:test-server")
        result = api_request(runtime, "/api/v1/remote-server-commands", method="POST", payload=command("connect", profile=wrong))
        assert result[0] == 409 and json_response(result)["error"]["code"] == "REMOTE_SESSION_BUSY"
        remote.fail_probe = False
        _connect(runtime)
        wait_for(lambda: view(runtime, operation_id)["trackingState"] == "tracking")
        assert remote.starts == 1
        remote.complete = True
        wait_for(lambda: view(runtime, operation_id)["status"] == "succeeded")


def test_offline_cancel_is_persisted_and_delivered_only_after_reconnect(tmp_path):
    remote = RecoverableRemote()
    options = {"remote_manager": remote, "server_profiles_path": tmp_path / "profiles.json"}
    with running_control_plane(tmp_path, **options) as runtime:
        _connect(runtime)
        operation_id = create(runtime, request_for(tmp_path / "case.inp"))
        wait_for(lambda: view(runtime, operation_id)["trackingState"] == "tracking")
        remote.fail_probe = True
        wait_for(lambda: view(runtime, operation_id)["trackingState"] == "reconnecting")
        cancelled = api_request(runtime, f"/api/v1/remote-jobs/{operation_id}/control", method="POST",
                                payload={"schemaVersion": 1, "action": "cancel"})
        assert cancelled[0] == 202 and remote.controls == 0
    with running_control_plane(tmp_path, **options) as runtime:
        remote.fail_probe = False
        _connect(runtime)
        wait_for(lambda: view(runtime, operation_id)["status"] == "cancelled")
        assert remote.controls == 1 and remote.starts == 1


def test_unreadable_probe_keeps_job_active_and_defers_controls(tmp_path):
    remote = RecoverableRemote()
    remote.probe_complete = False
    with running_control_plane(tmp_path, remote_manager=remote, server_profiles_path=tmp_path / "profiles.json") as runtime:
        _connect(runtime)
        operation_id = create(runtime, request_for(tmp_path / "case.inp"))
        wait_for(lambda: view(runtime, operation_id)["trackingState"] == "unverified")
        result = api_request(runtime, f"/api/v1/remote-jobs/{operation_id}/control", method="POST",
                             payload={"schemaVersion": 1, "action": "pause"})
        assert result[0] == 409 and remote.controls == 0
        result = api_request(runtime, f"/api/v1/remote-jobs/{operation_id}/control", method="POST",
                             payload={"schemaVersion": 1, "action": "cancel"})
        assert result[0] == 202 and remote.controls == 0
        remote.probe_complete = True
        wait_for(lambda: view(runtime, operation_id)["status"] == "cancelled")
        assert remote.controls == 1


def test_unknown_remote_receipt_never_relaunches_or_claims_success(tmp_path):
    remote = RecoverableRemote()
    remote.lose_ack = True
    with running_control_plane(tmp_path, remote_manager=remote, server_profiles_path=tmp_path / "profiles.json") as runtime:
        _connect(runtime)
        operation_id = create(runtime, request_for(tmp_path / "case.inp"))
        wait_for(lambda: view(runtime, operation_id)["trackingState"] == "reconnecting")
        remote.receipts.clear()
        _connect(runtime)
        wait_for(lambda: view(runtime, operation_id)["trackingState"] == "submission_unknown")
        assert view(runtime, operation_id)["status"] == "running" and remote.starts == 1


def test_corrupt_journal_is_preserved_and_does_not_break_health(tmp_path):
    folder = tmp_path / "runtime"
    folder.mkdir()
    journal = folder / "remote-jobs.sqlite3"
    journal.write_bytes(b"corrupt evidence")
    with running_control_plane(tmp_path) as runtime:
        assert api_request(runtime, "/healthz")[0] == 200
        assert api_request(runtime, "/api/v1/remote-jobs")[0] == 503
        assert journal.read_bytes() == b"corrupt evidence"


@pytest.mark.parametrize("broken", ["error", "schema", "identity"])
def test_invalid_saved_payload_preserves_evidence_and_blocks_history(tmp_path, broken):
    remote = RecoverableRemote()
    with running_control_plane(tmp_path, remote_manager=remote, server_profiles_path=tmp_path / "profiles.json") as runtime:
        _connect(runtime)
        operation_id = create(runtime, request_for(tmp_path / "case.inp"))
        wait_for(lambda: view(runtime, operation_id)["trackingState"] == "tracking")
    journal = tmp_path / "runtime" / "remote-jobs.sqlite3"
    with sqlite3.connect(journal) as database:
        record = json.loads(database.execute("SELECT payload FROM remote_operations").fetchone()[0])
        if broken == "error":
            record["snapshot"]["error"] = ["not an error object"]
        elif broken == "schema":
            record["schemaVersion"] = True
        else:
            record["snapshot"]["processId"] = 0
        payload = json.dumps(record)
        database.execute("UPDATE remote_operations SET payload=?", (payload,))
    with running_control_plane(tmp_path) as runtime:
        assert api_request(runtime, "/healthz")[0] == 200
        assert api_request(runtime, "/api/v1/remote-jobs")[0] == 503
        assert not runtime.httpd.context.remote_job_manager.prepare_shutdown(reserve=False)["safeToStop"]
    with sqlite3.connect(journal) as database:
        assert database.execute("SELECT payload FROM remote_operations").fetchone()[0] == payload


def test_storage_failure_blocks_new_launch_but_live_tracking_and_retry_continue(tmp_path, monkeypatch):
    remote = RecoverableRemote()
    with running_control_plane(tmp_path, remote_manager=remote, server_profiles_path=tmp_path / "profiles.json") as runtime:
        _connect(runtime)
        operation_id = create(runtime, request_for(tmp_path / "case.inp"))
        wait_for(lambda: view(runtime, operation_id)["trackingState"] == "tracking")
        manager = runtime.httpd.context.remote_job_manager
        original_save = manager._journal.save

        def fail(_record):
            raise sqlite3.OperationalError("disk unavailable")

        monkeypatch.setattr(manager._journal, "save", fail)
        with manager._lock:
            manager._persist_locked(manager._operations[operation_id])
        assert view(runtime, operation_id)["persistenceWarning"]
        response = api_request(runtime, "/api/v1/remote-jobs", method="POST", payload=request_for(tmp_path / "other.inp", "other"))
        assert response[0] == 503 and remote.starts == 1
        remote.complete = True
        wait_for(lambda: view(runtime, operation_id)["status"] == "succeeded")
        assert not manager.prepare_shutdown(reserve=False)["safeToStop"]
        monkeypatch.setattr(manager._journal, "save", original_save)
        wait_for(lambda: not view(runtime, operation_id)["persistenceWarning"])
        assert manager.prepare_shutdown(reserve=False)["safeToStop"]


def test_failed_dispatch_remains_in_history_without_remote_side_effect(tmp_path, monkeypatch):
    remote = RecoverableRemote()
    with running_control_plane(tmp_path, remote_manager=remote, server_profiles_path=tmp_path / "profiles.json") as runtime:
        _connect(runtime)
        manager = runtime.httpd.context.remote_job_manager

        def fail(*_args, **_kwargs):
            raise RuntimeError("thread unavailable")

        monkeypatch.setattr(manager._executor, "submit", fail)
        operation_id = create(runtime, request_for(tmp_path / "case.inp"))
        assert view(runtime, operation_id)["error"]["code"] == "REMOTE_JOB_DISPATCH_FAILED"
        assert remote.starts == 0


def test_cancel_recovery_does_not_resend_control_to_already_finished_job(tmp_path):
    remote = RecoverableRemote()
    options = {"remote_manager": remote, "server_profiles_path": tmp_path / "profiles.json"}
    with running_control_plane(tmp_path, **options) as runtime:
        _connect(runtime)
        operation_id = create(runtime, request_for(tmp_path / "case.inp"))
        wait_for(lambda: view(runtime, operation_id)["trackingState"] == "tracking")
        remote.fail_probe = True
        wait_for(lambda: view(runtime, operation_id)["trackingState"] == "reconnecting")
        api_request(runtime, f"/api/v1/remote-jobs/{operation_id}/control", method="POST",
                    payload={"schemaVersion": 1, "action": "cancel"})
    remote.complete, remote.fail_probe = True, False
    with running_control_plane(tmp_path, **options) as runtime:
        _connect(runtime)
        wait_for(lambda: view(runtime, operation_id)["status"] == "cancelled")
        assert remote.controls == 0 and remote.starts == 1
