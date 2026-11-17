from pathlib import Path

import pytest

from modules.control_plane.contracts import ApiProblem
from modules.control_plane.odb_upgrade_drafts import preview_odb_upgrade
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)


def setup_source(tmp_path, monkeypatch):
    monkeypatch.setenv("ABAQUS_TOOLS_ABAQUS_COMMAND", "abaqus")
    monkeypatch.setenv("ABAQUS_TOOLS_ABAQUS_RELEASE", "2025")
    source = tmp_path / "model.odb"
    source.write_bytes(b"original")
    return source, {"schemaVersion": 1, "root": str(tmp_path), "paths": [str(source)]}


def test_upgrade_preview_http_is_read_only_and_preserves_existing_backup(tmp_path, monkeypatch):
    source, payload = setup_source(tmp_path, monkeypatch)
    backup = tmp_path / "model-old.odb"
    backup.write_bytes(b"previous")
    with running_control_plane(tmp_path / "state") as runtime:
        response = api_request(runtime, "/api/v1/odb-upgrade-previews", method="POST", payload=payload)
        assert response[0] == 200, response
        preview = json_response(response)
    entry = preview["entries"][0]
    assert Path(entry["backupPath"]).name == "model-old-2.odb"
    assert not Path(entry["backupPath"]).exists() and not Path(entry["temporaryPath"]).exists()
    assert source.read_bytes() == b"original" and backup.read_bytes() == b"previous"
    assert preview["requiresConfirmation"] and preview["requiresCompatibilityCheck"]
    assert entry["sourceMtimeNs"] == source.stat().st_mtime_ns


@pytest.mark.parametrize("case", ["empty", "missing", "locked", "outside", "duplicate", "schema"])
def test_upgrade_preview_rejects_unsafe_inputs(tmp_path, monkeypatch, case):
    source, payload = setup_source(tmp_path, monkeypatch)
    if case == "empty": source.write_bytes(b"")
    if case == "missing": payload["paths"] = [str(tmp_path / "missing.odb")]
    if case == "locked": source.with_suffix(".lck").write_bytes(b"lock")
    if case == "outside": payload["paths"] = [str(tmp_path.parent / "outside.odb")]
    if case == "duplicate": payload["paths"] *= 2
    if case == "schema": payload["schemaVersion"] = True
    with pytest.raises(ApiProblem): preview_odb_upgrade(payload)
    assert not list(tmp_path.glob("*-old*.odb"))
    assert not list(tmp_path.glob("*-upgrading*.odb"))
