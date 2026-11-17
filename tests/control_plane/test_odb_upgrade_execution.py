from pathlib import Path

import pytest

from modules.control_plane import odb_upgrade_execution as execution
from modules.control_plane.contracts import ApiProblem
from modules.control_plane.odb_upgrade_drafts import preview_odb_upgrade
from modules.postprocessor.process_runner import ProcessCancelled, ProcessController
from modules.postprocessor.runner import UpgradeBatchController


def arrange(tmp_path, monkeypatch):
    monkeypatch.setenv("ABAQUS_TOOLS_ABAQUS_COMMAND", "abaqus")
    monkeypatch.setenv("ABAQUS_TOOLS_ABAQUS_RELEASE", "2025")
    source = tmp_path / "case.odb"
    source.write_bytes(b"original")
    preview = preview_odb_upgrade({"schemaVersion": 1, "root": str(tmp_path), "paths": [str(source)]})
    calls = []
    monkeypatch.setattr(execution, "check_odb_compatibility", lambda *a, **kw:
        {"results": [{"path": str(source), "status": "upgrade_required"}]})
    monkeypatch.setattr(execution, "upgrade_odb_files", lambda *a, **kw: calls.append((a, kw)) or {"results": []})
    return source, preview, calls


def test_confirmed_upgrade_reuses_safe_runner(tmp_path, monkeypatch):
    source, preview, calls = arrange(tmp_path, monkeypatch)
    controller = UpgradeBatchController()
    execution.execute_confirmed_upgrade(preview, confirmed=True, controller=controller)
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[1] == [(source, Path(preview["entries"][0]["backupPath"]))]
    assert args[4] is controller and kwargs["parallel_workers"] == 1
    assert source.read_bytes() == b"original"  # worker mocked; adapter itself cannot swap the ODB


@pytest.mark.parametrize("failure", ["unconfirmed", "stale", "backup", "valid", "during-check", "cancelled", "unsafe-controller"])
def test_upgrade_refuses_unconfirmed_or_changed_inputs(tmp_path, monkeypatch, failure):
    source, preview, calls = arrange(tmp_path, monkeypatch)
    controller = UpgradeBatchController()
    if failure == "stale": source.write_bytes(b"changed model")
    if failure == "backup": Path(preview["entries"][0]["backupPath"]).write_bytes(b"existing backup")
    if failure == "valid":
        monkeypatch.setattr(execution, "check_odb_compatibility", lambda *a, **kw:
            {"results": [{"path": str(source), "status": "valid"}]})
    if failure == "during-check":
        def check(*a, **kw):
            source.write_bytes(b"changed during check")
            return {"results": [{"path": str(source), "status": "upgrade_required"}]}
        monkeypatch.setattr(execution, "check_odb_compatibility", check)
    if failure == "cancelled": controller.cancel()
    if failure == "unsafe-controller": controller = ProcessController()
    with pytest.raises((ApiProblem, ProcessCancelled, TypeError)):
        execution.execute_confirmed_upgrade(preview, confirmed=failure != "unconfirmed", controller=controller)
    assert calls == []
