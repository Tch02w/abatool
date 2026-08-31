from __future__ import annotations

import threading
import time
from pathlib import Path

from modules.postprocessor.process_runner import ProcessCancelled
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)


def _settings() -> tuple[str, str, dict]:
    return (
        "abaqus",
        "2025",
        {
            "abaqus_command": "abaqus",
            "local_abaqus_release": "2025",
            "animation_fps": 5,
            "export_white_background_png": True,
            "export_transparent_background_png": True,
        },
    )


def _wait(runtime, operation_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        response = api_request(
            runtime,
            f"/api/v1/odb-postprocess-operations/{operation_id}",
        )
        assert response[0] == 200
        latest = json_response(response)
        if latest["status"] in {"succeeded", "cancelled", "failed"}:
            return latest
        time.sleep(0.01)
    raise AssertionError(f"ODB postprocess operation timed out: {latest}")


def _scan_payload(root: Path, odb: Path, request_id: str = "scan-1") -> dict:
    return {
        "schemaVersion": 1,
        "clientRequestId": request_id,
        "root": str(root),
        "paths": [str(odb)],
        "parallelWorkers": 2,
        "forceRescan": False,
    }


def _run_payload(root: Path, odb: Path, request_id: str = "run-1") -> dict:
    return {
        "schemaVersion": 1,
        "clientRequestId": request_id,
        "root": str(root),
        "parallelWorkers": 2,
        "forceRescan": False,
        "fullTimehistoryFreebody": False,
        "rebarMethod": "element_cut",
        "expectedLongitudinalRebarCount": 0,
        "imageSizeUnit": "px",
        "imageWidth": 1500,
        "imageHeight": 1000,
        "exportWhiteBackgroundPng": True,
        "exportTransparentBackgroundPng": True,
        "animationFps": 5,
        "rebarCutToleranceMm": 0.0001,
        "jobs": [
            {
                "path": str(odb),
                "startStep": "Load-1",
                "endStep": "Load-2",
                "frameMode": "auto",
                "manualSequenceExpression": "",
                "loadDirection": "1+3",
                "loadSet": "SET-LOAD",
                "pileType": "RC",
                "pileDisplaySet": "SET-PILE",
                "pileConcreteSet": "SET-PILE_CON",
                "pileSteelSet": "",
                "soilSet": "SET-SOIL_CUT",
                "rebarSet": "SET-REBAR",
                "longitudinalMaterial": "HRB400",
                "rebarDiameterMm": 32.0,
                "prefractureSequenceIndex": -1,
            }
        ],
        "groups": [
            {
                "id": "group-1",
                "name": "对比组 A",
                "members": [str(odb)],
                "standalone": False,
                "legendOverrides": {},
            }
        ],
    }


def test_postprocess_scan_is_async_idempotent_and_returns_editable_defaults(
    tmp_path: Path,
) -> None:
    root = tmp_path / "odbs"
    root.mkdir()
    odb = root / "GJA-18-U2D-V1D-R.odb"
    odb.write_bytes(b"odb")
    calls = []

    def scanner(request, progress, log, controller):
        calls.append(request)
        assert not controller.cancel_requested
        progress(60, "正在读取 ODB 结构")
        log("SCAN_DONE|1|1|GJA-18-U2D-V1D-R.odb")
        return {
            "root": str(root),
            "count": 1,
            "cacheHits": 0,
            "parallelWorkers": 1,
            "items": [
                {
                    "path": str(odb),
                    "name": odb.name,
                    "error": "",
                    "steps": ["Load-1", "Load-2"],
                    "assemblyNodeSets": ["SET-LOAD"],
                    "assemblyElementSets": ["SET-PILE", "SET-REBAR"],
                    "fieldOutputs": ["S", "U"],
                    "historyOutputDetails": [],
                    "setDetails": {},
                    "contentFingerprint": "fingerprint",
                    "suggested": {"loadDirection": "1+3"},
                    "nameMetadata": {"condition": "U2D_V1D"},
                }
            ],
        }

    with running_control_plane(
        tmp_path,
        postprocess_scan_runner=scanner,
        postprocess_settings_provider=_settings,
    ) as runtime:
        first = api_request(
            runtime,
            "/api/v1/odb-postprocess-scans",
            method="POST",
            payload=_scan_payload(root, odb),
        )
        second = api_request(
            runtime,
            "/api/v1/odb-postprocess-scans",
            method="POST",
            payload=_scan_payload(root, odb),
        )
        assert first[0] == second[0] == 202
        accepted = json_response(first)
        assert json_response(second)["operationId"] == accepted["operationId"]

        final = _wait(runtime, accepted["operationId"])
        assert final["status"] == "succeeded"
        assert final["kind"] == "odb.postprocess.scan"
        assert final["result"]["items"][0]["suggested"]["loadDirection"] == "1+3"
        assert final["logs"] == ["SCAN_DONE|1|1|GJA-18-U2D-V1D-R.odb"]
        assert len(calls) == 1


def test_postprocess_run_preserves_group_plan_and_reports_outputs(tmp_path: Path) -> None:
    root = tmp_path / "odbs"
    root.mkdir()
    odb = root / "case.odb"
    odb.write_bytes(b"odb")
    calls = []

    def runner(plan, progress, log, controller):
        calls.append(plan)
        assert plan.groups[0].name == "对比组 A"
        assert plan.jobs[odb.resolve()].load_set == "SET-LOAD"
        assert not controller.cancel_requested
        progress(80, "正在渲染云图")
        log("INDEX_INCREMENTAL|result")
        return {
            "batchId": plan.batch_id,
            "resultRoots": [str(root / "AbaqusODBPostProcessor_Results")],
            "outputCount": 1,
            "outputs": [str(root / "result")],
            "groups": [],
        }

    with running_control_plane(
        tmp_path,
        postprocess_run_runner=runner,
        postprocess_settings_provider=_settings,
    ) as runtime:
        accepted = json_response(
            api_request(
                runtime,
                "/api/v1/odb-postprocess-operations",
                method="POST",
                payload=_run_payload(root, odb),
            )
        )
        final = _wait(runtime, accepted["operationId"])
        assert final["status"] == "succeeded"
        assert final["kind"] == "odb.postprocess.run"
        assert final["result"]["outputCount"] == 1
        assert final["request"]["groupCount"] == 1
        assert len(calls) == 1

        history = json_response(
            api_request(runtime, "/api/v1/odb-postprocess-operations")
        )
        assert [item["operationId"] for item in history["operations"]] == [
            accepted["operationId"]
        ]


def test_postprocess_cancel_is_cooperative(tmp_path: Path) -> None:
    root = tmp_path / "odbs"
    root.mkdir()
    odb = root / "case.odb"
    odb.write_bytes(b"odb")
    started = threading.Event()

    def runner(_plan, progress, log, controller):
        progress(20, "正在预扫描")
        started.set()
        deadline = time.monotonic() + 5
        while not controller.cancel_requested and time.monotonic() < deadline:
            time.sleep(0.01)
        raise ProcessCancelled("cancelled by test")

    with running_control_plane(
        tmp_path,
        postprocess_run_runner=runner,
        postprocess_settings_provider=_settings,
    ) as runtime:
        accepted = json_response(
            api_request(
                runtime,
                "/api/v1/odb-postprocess-operations",
                method="POST",
                payload=_run_payload(root, odb),
            )
        )
        assert started.wait(5)
        cancelled = api_request(
            runtime,
            f"/api/v1/odb-postprocess-operations/{accepted['operationId']}/cancel",
            method="POST",
        )
        assert cancelled[0] == 202
        final = _wait(runtime, accepted["operationId"])
        assert final["status"] == "cancelled"
        assert final["error"] is None


def test_postprocess_rejects_path_escape_and_invalid_manual_frames(tmp_path: Path) -> None:
    root = tmp_path / "odbs"
    root.mkdir()
    outside = tmp_path / "outside.odb"
    outside.write_bytes(b"odb")
    inside = root / "inside.odb"
    inside.write_bytes(b"odb")

    with running_control_plane(
        tmp_path,
        postprocess_settings_provider=_settings,
    ) as runtime:
        escaped = api_request(
            runtime,
            "/api/v1/odb-postprocess-scans",
            method="POST",
            payload=_scan_payload(root, outside),
        )
        assert escaped[0] == 400
        assert json_response(escaped)["error"]["code"] == "PATH_OUTSIDE_ROOT"

        invalid = _run_payload(root, inside)
        invalid["jobs"][0]["frameMode"] = "manual"
        invalid["jobs"][0]["manualSequenceExpression"] = ""
        response = api_request(
            runtime,
            "/api/v1/odb-postprocess-operations",
            method="POST",
            payload=invalid,
        )
        assert response[0] == 400
        assert (
            json_response(response)["error"]["code"]
            == "MANUAL_FRAME_EXPRESSION_REQUIRED"
        )
