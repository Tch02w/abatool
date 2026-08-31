from __future__ import annotations

import time
from pathlib import Path

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


def _connect(runtime) -> None:
    profile = profile_payload()
    profile["hostFingerprint"] = "SHA256:test-server"
    response = api_request(
        runtime,
        "/api/v1/remote-server-commands",
        method="POST",
        payload=command(
            "connect",
            profile=profile,
            credentials={"password": "temporary"},
        ),
    )
    assert response[0] == 200


def test_remote_directory_listing_uses_the_verified_session(tmp_path: Path) -> None:
    with running_control_plane(
        tmp_path,
        server_profiles_path=tmp_path / "profiles.json",
        remote_manager=FakeRemoteManager(),
    ) as runtime:
        _connect(runtime)
        response = api_request(
            runtime,
            "/api/v1/remote-file-listings",
            method="POST",
            payload={"schemaVersion": 1, "path": r"D:\Abaqus_Cal"},
        )

    assert response[0] == 200
    payload = json_response(response)
    assert payload["path"] == r"D:\Abaqus_Cal"
    assert [entry["kind"] for entry in payload["entries"]] == ["directory", "file"]


def test_remote_transfer_reports_progress_and_terminal_result(tmp_path: Path) -> None:
    with running_control_plane(
        tmp_path,
        server_profiles_path=tmp_path / "profiles.json",
        remote_manager=FakeRemoteManager(),
    ) as runtime:
        _connect(runtime)
        created = api_request(
            runtime,
            "/api/v1/remote-transfers",
            method="POST",
            payload={
                "schemaVersion": 1,
                "clientRequestId": "upload-1",
                "direction": "upload",
                "source": str(tmp_path / "case.inp"),
                "destination": r"D:\Abaqus_Cal\case.inp",
                "overwrite": False,
            },
        )
        assert created[0] == 202
        operation_id = json_response(created)["operationId"]

        deadline = time.monotonic() + 3
        while True:
            snapshot_response = api_request(
                runtime,
                f"/api/v1/remote-transfers/{operation_id}",
            )
            snapshot = json_response(snapshot_response)
            if snapshot["status"] in {"succeeded", "failed", "cancelled"}:
                break
            assert time.monotonic() < deadline
            time.sleep(0.01)

        assert snapshot["status"] == "succeeded"
        assert snapshot["progress"] == {
            "completedBytes": 128,
            "totalBytes": 128,
            "percent": 100,
        }
        assert snapshot["result"]["direction"] == "upload"

        listed = json_response(api_request(runtime, "/api/v1/remote-transfers"))
        assert [operation["operationId"] for operation in listed["operations"]] == [
            operation_id
        ]


def test_remote_transfer_validates_direction_and_idempotency(tmp_path: Path) -> None:
    with running_control_plane(
        tmp_path,
        server_profiles_path=tmp_path / "profiles.json",
        remote_manager=FakeRemoteManager(),
    ) as runtime:
        invalid = api_request(
            runtime,
            "/api/v1/remote-transfers",
            method="POST",
            payload={
                "schemaVersion": 1,
                "clientRequestId": "bad",
                "direction": "sideways",
                "source": "a",
                "destination": "b",
                "overwrite": False,
            },
        )
        assert invalid[0] == 400
        assert json_response(invalid)["error"]["code"] == "INVALID_TRANSFER_DIRECTION"

        _connect(runtime)
        request = {
            "schemaVersion": 1,
            "clientRequestId": "same-id",
            "direction": "download",
            "source": r"D:\Abaqus_Cal\case.odb",
            "destination": str(tmp_path / "case.odb"),
            "overwrite": False,
        }
        first = api_request(
            runtime,
            "/api/v1/remote-transfers",
            method="POST",
            payload=request,
        )
        repeated = api_request(
            runtime,
            "/api/v1/remote-transfers",
            method="POST",
            payload=request,
        )
        assert json_response(first)["operationId"] == json_response(repeated)["operationId"]

        conflict = api_request(
            runtime,
            "/api/v1/remote-transfers",
            method="POST",
            payload={**request, "destination": str(tmp_path / "other.odb")},
        )
        assert conflict[0] == 409
        assert json_response(conflict)["error"]["code"] == "IDEMPOTENCY_CONFLICT"
