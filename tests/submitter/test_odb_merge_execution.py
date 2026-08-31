from __future__ import annotations

from pathlib import Path

from modules.submitter.odb_merge_core import OdbMergeRequest
from modules.submitter.odb_merge_execution import execute_odb_merge


def test_qt_free_merge_execution_preserves_sources_and_cleans_staging(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original = tmp_path / "phase1.odb"
    restart = tmp_path / "phase2.odb"
    output = tmp_path / "phase2_joined.odb"
    original.write_bytes(b"original-source")
    restart.write_bytes(b"restart-source")
    calls = []

    def fake_run_process(arguments, cwd, log=None, controller=None):
        calls.append(tuple(arguments))
        if arguments[1] == "restartjoin":
            (cwd / "abasub_join_working.odb").write_bytes(b"joined-result")
        else:
            assert arguments[1] == "python"
            assert log is not None
            log("ABASUB_ODB_VALIDATION_OK")

    monkeypatch.setattr(
        "modules.submitter.odb_merge_execution.run_process",
        fake_run_process,
    )
    progress = []
    result = execute_odb_merge(
        OdbMergeRequest(original, restart, output),
        lambda percent, phase: progress.append((percent, phase)),
    )

    assert original.read_bytes() == b"original-source"
    assert restart.read_bytes() == b"restart-source"
    assert output.read_bytes() == b"joined-result"
    assert result.original_backup.read_bytes() == b"original-source"
    assert result.restart_backup.read_bytes() == b"restart-source"
    assert [call[1] for call in calls] == ["restartjoin", "python"]
    assert progress[-1][0] == 100
    assert list(tmp_path.glob(".abasub-odb-merge-*")) == []
