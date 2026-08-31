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
        "/api/v1/odb-merge-draft-previews",
        method="POST",
        payload={"schemaVersion": 1} | payload,
    )


def test_odb_merge_preview_reuses_safe_planning_and_auto_numbering(
    tmp_path: Path,
) -> None:
    original = tmp_path / "phase1.odb"
    restart = tmp_path / "phase2.odb"
    output = tmp_path / "phase2_joined.odb"
    original.write_bytes(b"original")
    restart.write_bytes(b"restart")
    output.write_bytes(b"existing")

    with running_control_plane(tmp_path) as runtime:
        response = _preview(
            runtime,
            {
                "originalOdb": str(original),
                "restartOdb": str(restart),
                "outputOdb": str(output),
                "includeHistory": True,
                "compressResult": True,
                "copyOriginal": True,
                "conflictPolicy": "auto_number",
            },
        )

    assert response[0] == 200
    payload = json_response(response)
    assert payload["valid"] is True
    assert payload["normalizedOutputOdb"] == str(tmp_path / "phase2_joined_002.odb")
    assert payload["originalBackup"] == str(tmp_path / "phase1_original.odb")
    assert payload["restartBackup"] == str(tmp_path / "phase2_original.odb")
    assert payload["autoNumbered"] is True
    assert payload["sourceTotalBytes"] == 15
    assert "history" in payload["command"]
    assert "compressresult" in payload["command"]
    assert "copyoriginal" in payload["command"]
    assert len(payload["executionSteps"]) == 4


def test_odb_merge_preview_returns_actionable_invalid_state(tmp_path: Path) -> None:
    original = tmp_path / "phase1.odb"
    original.write_bytes(b"original")

    with running_control_plane(tmp_path) as runtime:
        response = _preview(
            runtime,
            {
                "originalOdb": str(original),
                "restartOdb": str(tmp_path / "missing.odb"),
                "outputOdb": str(tmp_path / "joined.odb"),
                "includeHistory": True,
                "compressResult": False,
                "copyOriginal": False,
                "conflictPolicy": "auto_number",
            },
        )

    assert response[0] == 200
    payload = json_response(response)
    assert payload["valid"] is False
    assert "重启动 ODB 不存在" in payload["validationMessage"]
    assert payload["command"] == ""


def test_odb_merge_preview_rejects_unknown_and_invalid_contract_fields(
    tmp_path: Path,
) -> None:
    with running_control_plane(tmp_path) as runtime:
        unknown = _preview(runtime, {"future": True})
        assert unknown[0] == 400
        assert json_response(unknown)["error"]["code"] == "UNKNOWN_FIELDS"

        invalid = _preview(runtime, {"includeHistory": "yes"})
        assert invalid[0] == 400
        assert json_response(invalid)["error"]["code"] == (
            "INVALID_ODB_MERGE_DRAFT_FIELD"
        )

        command_injection = _preview(runtime, {"abaqusCommand": "cmd.exe /c whoami"})
        assert command_injection[0] == 400
        assert json_response(command_injection)["error"]["code"] == "UNKNOWN_FIELDS"
