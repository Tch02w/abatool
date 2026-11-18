from __future__ import annotations

import base64
import json
import ntpath
import re
from pathlib import Path
from typing import Any

from modules.submitter.remote_connection import (
    HostKeyConfirmationRequired,
    ServerConnectionRequest,
)
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)


class FakeRemoteManager:
    def __init__(self) -> None:
        self.requests: list[ServerConnectionRequest] = []
        self.connected_name = ""
        self.refresh_count = 0
        self._profile = None
        self.receipts = {}

    def connect(self, request: ServerConnectionRequest) -> dict[str, Any]:
        self.requests.append(request)
        if not request.profile.host_fingerprint:
            raise HostKeyConfirmationRequired("SHA256:test-server")
        assert request.profile.host_fingerprint == "SHA256:test-server"
        self.connected_name = request.profile.profile_name
        self._profile = request.profile
        return {
            "profile_name": request.profile.profile_name,
            "host": request.profile.host,
            "connected": True,
            "computer_name": "COMPUTE01",
            "cpu_used": 4,
            "cpu_total": 32,
            "cpu_percent": 12.5,
            "memory_used_gb": 16.0,
            "memory_total_gb": 64.0,
            "running_jobs": 0,
            "waiting_jobs": 0,
            "active_jobs": (),
            "compute_root": request.profile.compute_root,
            "compute_root_exists": True,
            "allowed_roots": request.profile.allowed_roots,
            "abaqus_command": request.profile.abaqus_command,
            "abaqus_command_available": True,
            "host_fingerprint": "SHA256:test-server",
            "updated_at": "2026-08-31T12:00:00+08:00",
        }

    def refresh(self) -> dict[str, Any]:
        self.refresh_count += 1
        return {
            "profile_name": self.connected_name,
            "connected": True,
            "cpu_total": 32,
            "memory_total_gb": 64.0,
            "host_fingerprint": "SHA256:test-server",
        }

    def disconnect(self) -> str:
        previous = self.connected_name
        self.connected_name = ""
        self._profile = None
        return previous

    @property
    def connected_profile(self):
        return self._profile

    def validate_remote_path(self, remote_path: str) -> str:
        return remote_path

    def execute_powershell(self, script: str, *, timeout: float = 30) -> str:
        del timeout
        match = re.search(r"FromBase64String\('([^']+)'\)", script)
        config = json.loads(base64.b64decode(match[1])) if match else {}
        if "$base=Join-Path" in script:
            return json.dumps({"work_directory": ntpath.join(config["compute_root"], config["job_name"] + "_" + config["operation_id"])})
        if "process_id=[int]$process.Id" in script:
            result = {"process_id": 4321, "process_start_ticks": "1234", "state": "started", "operation_id": config["operation_id"]}
            self.receipts[config["work_directory"]] = result
            return json.dumps(result)
        if "$existing|ConvertTo-Json -Compress" in script:
            return json.dumps(self.receipts.get(config["work_directory"], {"state": "unknown"}))
        if "process_active=$active" in script:
            return json.dumps(
                {
                    "process_active": False,
                    "probe_complete": True,
                    "output_signature": "sta:stable",
                    "lock_exists": False,
                    "sta_tail": "THE ANALYSIS HAS COMPLETED SUCCESSFULLY",
                    "log_tail": "",
                }
            )
        if "exit_code=[int]$process.ExitCode" in script:
            return json.dumps({"exit_code": 0})
        return json.dumps({"copied": True})

    def list_directory(self, remote_path: str = "") -> dict[str, Any]:
        return {
            "profileName": self.connected_name,
            "path": remote_path or r"D:\Abaqus_Cal",
            "parentPath": "",
            "entries": [
                {
                    "name": "models",
                    "path": r"D:\Abaqus_Cal\models",
                    "kind": "directory",
                    "sizeBytes": 0,
                    "modifiedAt": "2026-08-31T12:00:00+08:00",
                },
                {
                    "name": "case.inp",
                    "path": r"D:\Abaqus_Cal\case.inp",
                    "kind": "file",
                    "sizeBytes": 128,
                    "modifiedAt": "2026-08-31T12:00:00+08:00",
                },
            ],
        }

    def upload_file(
        self,
        local_path: str,
        remote_path: str,
        *,
        overwrite: bool = False,
        progress=None,
        cancel_requested=None,
    ) -> dict[str, Any]:
        del overwrite
        if progress is not None:
            progress(64, 128)
            progress(128, 128)
        return {
            "profileName": self.connected_name,
            "direction": "upload",
            "source": local_path,
            "destination": remote_path,
            "sizeBytes": 128,
        }

    def download_file(
        self,
        remote_path: str,
        local_path: str,
        *,
        overwrite: bool = False,
        progress=None,
        cancel_requested=None,
    ) -> dict[str, Any]:
        del overwrite
        if progress is not None:
            progress(256, 256)
        return {
            "profileName": self.connected_name,
            "direction": "download",
            "source": remote_path,
            "destination": local_path,
            "sizeBytes": 256,
        }


def profile_payload() -> dict[str, Any]:
    return {
        "profileName": "compute-01",
        "host": "10.0.0.8",
        "username": "abaqus",
        "authentication": "用户名/密码",
        "hostFingerprint": "",
        "abaqusCommand": "abaqus.bat",
        "computeRoot": r"D:\Abaqus_Cal",
        "allowedRoots": [r"D:\Abaqus_Cal"],
        "port": 22,
        "privateKeyPath": "",
    }


def command(action: str, **values: Any) -> dict[str, Any]:
    return {"schemaVersion": 1, "action": action, **values}


def test_connection_requires_confirmation_then_persists_only_verified_profile(
    tmp_path: Path,
) -> None:
    manager = FakeRemoteManager()
    profiles_path = tmp_path / "server_profiles.json"
    with running_control_plane(
        tmp_path,
        server_profiles_path=profiles_path,
        remote_manager=manager,
    ) as runtime:
        first = api_request(
            runtime,
            "/api/v1/remote-server-commands",
            method="POST",
            payload=command(
                "connect",
                profile=profile_payload(),
                credentials={"password": "login-secret"},
            ),
        )
        assert first[0] == 200
        confirmation = json_response(first)
        assert confirmation["connection"]["status"] == "confirmationRequired"
        assert confirmation["connection"]["pendingFingerprint"] == (
            "SHA256:test-server"
        )
        assert not profiles_path.exists()

        second = api_request(
            runtime,
            "/api/v1/remote-server-commands",
            method="POST",
            payload=command(
                "connect",
                profile=profile_payload(),
                credentials={"password": "login-secret"},
                confirmFingerprint="SHA256:test-server",
            ),
        )
        assert second[0] == 200
        connected = json_response(second)
        assert connected["connection"]["status"] == "connected"
        assert connected["connection"]["resource"]["computer_name"] == "COMPUTE01"
        assert connected["profiles"][0]["hostFingerprint"] == (
            "SHA256:test-server"
        )

    serialized = profiles_path.read_text(encoding="utf-8")
    assert "login-secret" not in serialized
    assert "password" not in serialized.casefold()
    assert manager.requests[-1].credentials.password == "login-secret"


def test_saved_profile_connect_refresh_and_disconnect(tmp_path: Path) -> None:
    manager = FakeRemoteManager()
    profiles_path = tmp_path / "server_profiles.json"
    profile = profile_payload()
    profile["hostFingerprint"] = "SHA256:test-server"
    with running_control_plane(
        tmp_path,
        server_profiles_path=profiles_path,
        remote_manager=manager,
    ) as runtime:
        saved = api_request(
            runtime,
            "/api/v1/remote-server-commands",
            method="POST",
            payload=command("saveProfile", profile=profile),
        )
        assert saved[0] == 200

        connected = api_request(
            runtime,
            "/api/v1/remote-server-commands",
            method="POST",
            payload=command(
                "connect",
                profileName="compute-01",
                credentials={"password": "temporary"},
            ),
        )
        assert connected[0] == 200

        refreshed = api_request(
            runtime,
            "/api/v1/remote-server-commands",
            method="POST",
            payload=command("refresh"),
        )
        assert refreshed[0] == 200
        assert json_response(refreshed)["connection"]["resource"]["cpu_total"] == 32
        assert manager.refresh_count == 1

        disconnected = api_request(
            runtime,
            "/api/v1/remote-server-commands",
            method="POST",
            payload=command("disconnect"),
        )
        assert disconnected[0] == 200
        assert json_response(disconnected)["connection"]["status"] == "disconnected"


def test_corrupt_profiles_are_reported_and_never_overwritten(tmp_path: Path) -> None:
    profiles_path = tmp_path / "server_profiles.json"
    original = "{broken json"
    profiles_path.write_text(original, encoding="utf-8")
    with running_control_plane(
        tmp_path,
        server_profiles_path=profiles_path,
        remote_manager=FakeRemoteManager(),
    ) as runtime:
        snapshot = json_response(api_request(runtime, "/api/v1/remote-servers"))
        assert snapshot["profilesError"]

        save = api_request(
            runtime,
            "/api/v1/remote-server-commands",
            method="POST",
            payload=command("saveProfile", profile=profile_payload()),
        )
        assert save[0] == 409
        assert json_response(save)["error"]["code"] == "REMOTE_PROFILES_CORRUPT"

    assert profiles_path.read_text(encoding="utf-8") == original


def test_remote_responses_never_echo_credentials(tmp_path: Path) -> None:
    with running_control_plane(
        tmp_path,
        server_profiles_path=tmp_path / "profiles.json",
        remote_manager=FakeRemoteManager(),
    ) as runtime:
        response = api_request(
            runtime,
            "/api/v1/remote-server-commands",
            method="POST",
            payload=command(
                "connect",
                profile=profile_payload(),
                credentials={
                    "password": "password-secret",
                    "privateKeyPassphrase": "key-secret",
                },
            ),
        )

    body = response[2].decode("utf-8")
    assert "password-secret" not in body
    assert "key-secret" not in body
    assert "privateKeyPassphrase" not in body
