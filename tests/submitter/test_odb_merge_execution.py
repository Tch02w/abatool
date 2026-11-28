from __future__ import annotations

import json
from pathlib import Path

import pytest

from modules.postprocessor.process_runner import ProcessCancelled, ProcessController
from modules.submitter.odb_merge_core import (
    MergeConflictPolicy,
    OdbMergeError,
    OdbMergeRequest,
)
from modules.submitter.odb_merge_execution import execute_odb_merge


def write_validation_receipt(arguments, cwd):
    payload = {
        "schemaVersion": 1,
        "status": "verified",
        "includeHistory": arguments[6] == "1",
        "originalPath": str(cwd / arguments[3]),
        "restartPath": str(cwd / arguments[4]),
        "joinedPath": str(cwd / arguments[5]),
        "steps": [{"name": "step", "frames": 1}],
    }
    (cwd / arguments[7]).write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize("empty_future", [False, True])
def test_qt_free_merge_execution_preserves_sources_and_cleans_staging(
    tmp_path: Path,
    monkeypatch,
    empty_future,
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
            write_validation_receipt(arguments, cwd)
            if empty_future:
                receipt = cwd / arguments[7]
                payload = json.loads(receipt.read_text())
                payload["steps"].append({"name": "future", "frames": 0})
                receipt.write_text(json.dumps(payload))
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
    assert result.validation_report.is_file()
    assert json.loads(result.validation_report.read_text())["joinedPath"] == str(output)
    assert list(tmp_path.glob(".abasub-odb-merge-*")) == []
    assert result.empty_frame_steps == (("future",) if empty_future else ())


@pytest.mark.parametrize("cancel_at", [82, 92])
def test_cancel_before_commit_rejects_but_commit_finishes_atomically(
    tmp_path, monkeypatch, cancel_at
):
    original, restart, output = (
        tmp_path / name for name in ("base.odb", "restart.odb", "joined.odb")
    )
    original.write_bytes(b"base")
    restart.write_bytes(b"restart")
    controller = ProcessController()

    def run(arguments, cwd, log=None, controller=None):
        if arguments[1] == "restartjoin":
            (cwd / "abasub_join_working.odb").write_bytes(b"joined")
        else:
            write_validation_receipt(arguments, cwd)
            log("ABASUB_ODB_VALIDATION_OK")

    def progress(percent, phase):
        if percent == cancel_at:
            controller.cancel()

    monkeypatch.setattr("modules.submitter.odb_merge_execution.run_process", run)
    request = OdbMergeRequest(original, restart, output)
    if cancel_at == 82:
        with pytest.raises(ProcessCancelled):
            execute_odb_merge(request, progress, controller=controller)
        assert not output.exists()
        assert not list(tmp_path.glob("*.merge-validation.json"))
    else:
        result = execute_odb_merge(request, progress, controller=controller)
        assert result.output_odb.read_bytes() == b"joined"
        assert result.validation_report.exists()


@pytest.mark.parametrize(
    "problem",
    [
        "missing_receipt",
        "wrong_path",
        "source_changed",
        "validation_failed",
        "unrecorded_history",
        "unrecorded_history_nonzero",
        "publish_failed",
    ],
)
def test_bad_merge_cannot_replace_prior_result(tmp_path, monkeypatch, problem):
    original, restart, output = [
        tmp_path / name for name in ("base.odb", "restart.odb", "full_joined.odb")
    ]
    original.write_bytes(b"base")
    restart.write_bytes(b"restart")
    output.write_bytes(b"prior-result")
    prior_report = tmp_path / "full_joined.prior.merge-validation.json"
    prior_report.write_text("prior-report")

    def run(arguments, cwd, log=None, controller=None):
        if arguments[1] == "restartjoin":
            (cwd / "abasub_join_working.odb").write_bytes(b"joined")
            if problem == "source_changed":
                original.write_bytes(b"changed source")
        else:
            if problem == "validation_failed":
                raise RuntimeError("field mismatch")
            if problem.startswith("unrecorded_history"):
                log(
                    'ABASUB_ODB_VALIDATION_FAILED|"History contains samples not present in the source: U40D / A / RF / data"'
                )
                if problem.endswith("nonzero"):
                    raise RuntimeError("Command failed with exit code 1")
                return
            if problem != "missing_receipt":
                write_validation_receipt(arguments, cwd)
            if problem == "wrong_path":
                payload = json.loads((cwd / arguments[7]).read_text())
                payload["joinedPath"] = str(original)
                (cwd / arguments[7]).write_text(json.dumps(payload))
            log("ABASUB_ODB_VALIDATION_OK")

    monkeypatch.setattr("modules.submitter.odb_merge_execution.run_process", run)
    if problem == "publish_failed":

        def fail_replace(*_):
            raise OSError("target locked")

        monkeypatch.setattr(
            "modules.submitter.odb_merge_execution.os.replace", fail_replace
        )
    with pytest.raises((OdbMergeError, RuntimeError, OSError)) as caught:
        execute_odb_merge(
            OdbMergeRequest(
                original, restart, output, conflict_policy=MergeConflictPolicy.OVERWRITE
            )
        )
    if problem.startswith("unrecorded_history"):
        assert "合并后的历史含源文件未记录的样本：U40D / A / RF / data" in str(
            caught.value
        )
    assert output.read_bytes() == b"prior-result"
    assert prior_report.read_text() == "prior-report"
    assert list(tmp_path.glob("*_original.odb")) == []
    assert list(tmp_path.glob(".abasub-odb-merge-*")) == []
    assert list(tmp_path.glob("*.merge-validation.json")) == [prior_report]
