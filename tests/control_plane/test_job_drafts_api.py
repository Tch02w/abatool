from __future__ import annotations

from pathlib import Path

from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)


def _preview(runtime, payload: dict):
    return api_request(
        runtime,
        "/api/v1/local-job-draft-previews",
        method="POST",
        payload={"schemaVersion": 1} | payload,
    )


def test_local_job_draft_preview_reuses_submitter_validation_and_command(
    tmp_path: Path,
) -> None:
    source = tmp_path / "输入 文件" / "phase2.inp"
    source.parent.mkdir()
    source.write_text("*Heading\n", encoding="utf-8")
    calculation_root = tmp_path / "ssd"
    archive_root = tmp_path / "archive"
    calculation_root.mkdir()
    archive_root.mkdir()

    with running_control_plane(tmp_path) as runtime:
        response = _preview(
            runtime,
            {
                "inpFile": str(source),
                "jobName": "phase2_run",
                "cpus": 8,
                "memoryValue": "80",
                "memoryUnit": "%",
                "oldjobPath": str(tmp_path / "phase1.odb"),
                "fortranPath": str(tmp_path / "umat.for"),
                "interactive": True,
                "datacheck": False,
                "notify": True,
                "abaqusCommand": r"C:\Program Files\SIMULIA\abaqus.bat",
                "priority": 10,
                "maxParallel": 2,
                "useSsdCalculation": True,
                "calculationRootDir": str(calculation_root),
                "archiveDir": str(archive_root),
            },
        )

        assert response[0] == 200
        payload = json_response(response)
        assert payload["valid"] is True
        assert payload["effectiveJobName"] == "phase2_run"
        assert payload["oldjobName"] == "phase1"
        assert payload["hasRestartInput"] is True
        assert payload["workDirectory"] == str(calculation_root / "phase2_run")
        assert payload["archivePath"] == str(archive_root / "phase2_run")
        assert payload["command"] == (
            '"C:\\Program Files\\SIMULIA\\abaqus.bat" '
            'job=phase2_run oldjob=phase1 '
            f'user="{tmp_path / "umat.for"}" cpus=8 memory=80% interactive'
        )


def test_local_job_draft_preview_returns_actionable_invalid_state(
    tmp_path: Path,
) -> None:
    with running_control_plane(tmp_path) as runtime:
        response = _preview(
            runtime,
            {
                "inpFile": str(tmp_path / "missing.inp"),
                "jobName": "missing",
                "cpus": 0,
                "memoryValue": "",
                "memoryUnit": "%",
                "interactive": False,
                "datacheck": False,
                "notify": True,
                "abaqusCommand": "abaqus",
                "priority": 0,
                "maxParallel": 1,
                "useSsdCalculation": False,
            },
        )

        assert response[0] == 200
        payload = json_response(response)
        assert payload["valid"] is False
        assert payload["validationMessage"] == "INP 文件不存在。"
        assert payload["command"] == ""


def test_local_job_draft_preview_rejects_invalid_contract_fields(
    tmp_path: Path,
) -> None:
    with running_control_plane(tmp_path) as runtime:
        bad_type = _preview(runtime, {"inpFile": [], "cpus": 1})
        assert bad_type[0] == 400
        assert json_response(bad_type)["error"]["code"] == (
            "INVALID_JOB_DRAFT_FIELD"
        )

        unknown = _preview(runtime, {"inpFile": "x.inp", "future": True})
        assert unknown[0] == 400
        assert json_response(unknown)["error"]["code"] == "UNKNOWN_FIELDS"
