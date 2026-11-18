from __future__ import annotations

import time
from pathlib import Path

from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_remote_servers_api import FakeRemoteManager
from tests.control_plane.test_remote_transfers_api import _connect


class ActiveRemoteManager(FakeRemoteManager):
    def execute_powershell(self, script: str, *, timeout: float = 30) -> str:
        if "process_active=$active" in script:
            return '{"process_active":true,"lock_exists":true,"sta_tail":"","log_tail":"","probe_complete":true,"output_signature":"empty"}'
        return super().execute_powershell(script, timeout=timeout)


def test_remote_upload_job_runs_to_a_confirmed_terminal_state(tmp_path: Path) -> None:
    inp = tmp_path / "case.inp"
    inp.write_text("*Heading\n", encoding="utf-8")
    with running_control_plane(
        tmp_path,
        server_profiles_path=tmp_path / "profiles.json",
        remote_manager=FakeRemoteManager(),
    ) as runtime:
        _connect(runtime)
        created = api_request(
            runtime,
            "/api/v1/remote-jobs",
            method="POST",
            payload={
                "schemaVersion": 1,
                "clientRequestId": "remote-job-1",
                "jobName": "case",
                "inputMode": "upload",
                "inputPath": str(inp),
                "oldjobPath": "",
                "fortranPath": "",
                "cpus": 4,
                "memory": "90%",
                "datacheck": False,
            },
        )
        assert created[0] == 202
        operation_id = json_response(created)["operationId"]

        deadline = time.monotonic() + 5
        while True:
            response = api_request(runtime, f"/api/v1/remote-jobs/{operation_id}")
            snapshot = json_response(response)
            if snapshot["status"] in {"succeeded", "failed", "cancelled"}:
                break
            assert time.monotonic() < deadline
            time.sleep(0.01)

        assert snapshot["status"] == "succeeded"
        assert snapshot["percent"] == 100
        assert snapshot["workDirectory"] == "D:\\Abaqus_Cal\\case_" + operation_id
        assert snapshot["files"]["odb"].endswith(r"\case.odb")
        assert any("COMPLETED SUCCESSFULLY" in line for line in snapshot["logs"])


def test_remote_existing_job_request_is_validated_without_local_path_lookup(
    tmp_path: Path,
) -> None:
    with running_control_plane(
        tmp_path,
        server_profiles_path=tmp_path / "profiles.json",
        remote_manager=FakeRemoteManager(),
    ) as runtime:
        _connect(runtime)
        response = api_request(
            runtime,
            "/api/v1/remote-jobs",
            method="POST",
            payload={
                "schemaVersion": 1,
                "clientRequestId": "remote-existing-1",
                "jobName": "existing_case",
                "inputMode": "existing",
                "inputPath": r"D:\Abaqus_Cal\existing_case.inp",
                "oldjobPath": "",
                "fortranPath": "",
                "cpus": 0,
                "memory": "",
                "datacheck": True,
            },
        )

        assert response[0] == 202
        listed = json_response(api_request(runtime, "/api/v1/remote-jobs"))
        assert listed["operations"][0]["request"]["inputMode"] == "existing"


def test_remote_job_rejects_invalid_names_and_unknown_controls(tmp_path: Path) -> None:
    inp = tmp_path / "case.inp"
    inp.write_text("*Heading\n", encoding="utf-8")
    with running_control_plane(
        tmp_path,
        server_profiles_path=tmp_path / "profiles.json",
        remote_manager=FakeRemoteManager(),
    ) as runtime:
        invalid = api_request(
            runtime,
            "/api/v1/remote-jobs",
            method="POST",
            payload={
                "schemaVersion": 1,
                "clientRequestId": "bad-name",
                "jobName": "bad name",
                "inputMode": "upload",
                "inputPath": str(inp),
                "cpus": 1,
                "memory": "90%",
                "datacheck": False,
            },
        )
        assert invalid[0] == 400
        assert json_response(invalid)["error"]["code"] == "INVALID_REMOTE_JOB_NAME"

        missing = api_request(
            runtime,
            "/api/v1/remote-jobs/not-found/control",
            method="POST",
            payload={"schemaVersion": 1, "action": "explode"},
        )
        assert missing[0] == 400
        assert json_response(missing)["error"]["code"] == "INVALID_REMOTE_JOB_CONTROL"


def test_active_remote_job_prevents_accidental_session_disconnect(tmp_path: Path) -> None:
    inp = tmp_path / "active.inp"
    inp.write_text("*Heading\n", encoding="utf-8")
    with running_control_plane(
        tmp_path,
        server_profiles_path=tmp_path / "profiles.json",
        remote_manager=ActiveRemoteManager(),
    ) as runtime:
        _connect(runtime)
        created = api_request(
            runtime,
            "/api/v1/remote-jobs",
            method="POST",
            payload={
                "schemaVersion": 1,
                "clientRequestId": "active-remote-job",
                "jobName": "active",
                "inputMode": "upload",
                "inputPath": str(inp),
                "oldjobPath": "",
                "fortranPath": "",
                "cpus": 1,
                "memory": "90%",
                "datacheck": False,
            },
        )
        assert created[0] == 202

        deadline = time.monotonic() + 3
        while True:
            listed = json_response(api_request(runtime, "/api/v1/remote-jobs"))
            if listed["operations"][0]["status"] == "running":
                break
            assert time.monotonic() < deadline
            time.sleep(0.01)

        disconnected = api_request(
            runtime,
            "/api/v1/remote-server-commands",
            method="POST",
            payload={"schemaVersion": 1, "action": "disconnect"},
        )
        assert disconnected[0] == 409
        assert json_response(disconnected)["error"]["code"] == "REMOTE_SESSION_BUSY"
