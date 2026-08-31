from __future__ import annotations

import threading
import time
from pathlib import Path

from modules.postprocessor.process_runner import ProcessCancelled
from modules.submitter.odb_merge_core import OdbMergeResult
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)


def _request_payload(
    original: Path,
    restart: Path,
    output: Path,
    request_id: str = "merge-request",
) -> dict:
    return {
        "schemaVersion": 1,
        "clientRequestId": request_id,
        "originalOdb": str(original),
        "restartOdb": str(restart),
        "outputOdb": str(output),
        "includeHistory": True,
        "compressResult": False,
        "copyOriginal": False,
        "conflictPolicy": "auto_number",
    }


def _wait(runtime, operation_id: str, statuses: set[str], timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        response = api_request(runtime, f"/api/v1/odb-merge-operations/{operation_id}")
        assert response[0] == 200
        latest = json_response(response)
        if latest["status"] in statuses:
            return latest
        time.sleep(0.01)
    raise AssertionError(f"ODB merge operation timed out: {latest}")


def test_odb_merge_operation_is_async_idempotent_and_observable(tmp_path: Path) -> None:
    original = tmp_path / "phase1.odb"
    restart = tmp_path / "phase2.odb"
    output = tmp_path / "phase2_joined.odb"
    original.write_bytes(b"original")
    restart.write_bytes(b"restart")
    calls = []

    def runner(request, progress=None, log=None, controller=None):
        calls.append(request)
        assert progress is not None
        assert log is not None
        assert controller is not None
        progress(60, "正在执行 Abaqus restartjoin…")
        log("restartjoin completed")
        progress(100, "ODB 合并与只读验证完成。")
        return OdbMergeResult(
            output_odb=request.output_odb,
            original_backup=tmp_path / "phase1_original.odb",
            restart_backup=tmp_path / "phase2_original.odb",
            command="abaqus restartjoin",
        )

    with running_control_plane(
        tmp_path,
        odb_merge_runner=runner,
        odb_merge_command_provider=lambda: "abaqus",
    ) as runtime:
        first = api_request(
            runtime,
            "/api/v1/odb-merge-operations",
            method="POST",
            payload=_request_payload(original, restart, output),
        )
        second = api_request(
            runtime,
            "/api/v1/odb-merge-operations",
            method="POST",
            payload=_request_payload(original, restart, output),
        )
        assert first[0] == second[0] == 202
        accepted = json_response(first)
        assert json_response(second)["operationId"] == accepted["operationId"]

        succeeded = _wait(runtime, accepted["operationId"], {"succeeded"})
        assert succeeded["kind"] == "odb.merge"
        assert succeeded["progress"]["percent"] == 100
        assert succeeded["logs"] == ["restartjoin completed"]
        assert succeeded["result"]["outputOdb"] == str(output.resolve())
        assert len(calls) == 1

        active = json_response(
            api_request(runtime, "/api/v1/odb-merge-operations?activeOnly=true")
        )
        assert active["operations"] == []
        history = json_response(api_request(runtime, "/api/v1/odb-merge-operations"))
        assert [item["operationId"] for item in history["operations"]] == [
            accepted["operationId"]
        ]

        conflict = api_request(
            runtime,
            "/api/v1/odb-merge-operations",
            method="POST",
            payload=_request_payload(
                original,
                restart,
                tmp_path / "different_joined.odb",
            ),
        )
        assert conflict[0] == 409
        assert json_response(conflict)["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_odb_merge_operation_cancel_is_cooperative_and_terminal(tmp_path: Path) -> None:
    original = tmp_path / "phase1.odb"
    restart = tmp_path / "phase2.odb"
    output = tmp_path / "joined.odb"
    original.write_bytes(b"original")
    restart.write_bytes(b"restart")
    started = threading.Event()

    def runner(_request, progress=None, log=None, controller=None):
        assert progress is not None
        assert controller is not None
        progress(45, "正在创建隔离合并工作副本…")
        started.set()
        deadline = time.monotonic() + 5
        while not controller.cancel_requested and time.monotonic() < deadline:
            time.sleep(0.01)
        raise ProcessCancelled("cancelled by test")

    with running_control_plane(
        tmp_path,
        odb_merge_runner=runner,
        odb_merge_command_provider=lambda: "abaqus",
    ) as runtime:
        accepted = json_response(
            api_request(
                runtime,
                "/api/v1/odb-merge-operations",
                method="POST",
                payload=_request_payload(original, restart, output),
            )
        )
        assert started.wait(5)
        response = api_request(
            runtime,
            f"/api/v1/odb-merge-operations/{accepted['operationId']}/cancel",
            method="POST",
        )
        assert response[0] == 202
        cancelled = _wait(runtime, accepted["operationId"], {"cancelled"})
        assert cancelled["error"] is None
        assert cancelled["progress"]["percent"] == 45
        assert "源 ODB 未被修改" in cancelled["progress"]["phase"]


def test_odb_merge_operation_reports_runner_failure(tmp_path: Path) -> None:
    original = tmp_path / "phase1.odb"
    restart = tmp_path / "phase2.odb"
    output = tmp_path / "joined.odb"
    original.write_bytes(b"original")
    restart.write_bytes(b"restart")

    def runner(*_args, **_kwargs):
        raise RuntimeError("Abaqus license unavailable")

    with running_control_plane(
        tmp_path,
        odb_merge_runner=runner,
        odb_merge_command_provider=lambda: "abaqus",
    ) as runtime:
        accepted = json_response(
            api_request(
                runtime,
                "/api/v1/odb-merge-operations",
                method="POST",
                payload=_request_payload(original, restart, output),
            )
        )
        failed = _wait(runtime, accepted["operationId"], {"failed"})
        assert failed["error"]["code"] == "ODB_MERGE_FAILED"
        assert failed["error"]["message"] == "Abaqus license unavailable"
