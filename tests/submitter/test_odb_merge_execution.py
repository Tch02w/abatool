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
from modules.submitter.odb_merge_publication import (
    PREPARED_RECEIPT,
    PREVIOUS_TARGET,
    file_identity,
    recover_publication,
)


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


@pytest.mark.parametrize("copy_original", [True, False])
@pytest.mark.parametrize("fail_at", [None, "restore", "final_check", "disk", "cancel"])
def test_extra_zero_fallback_checks_reopened_result_before_publication(
    tmp_path, monkeypatch, copy_original, fail_at
):
    original, restart, output = [
        tmp_path / s for s in ("base.odb", "restart.odb", "full_joined.odb")
    ]
    original.write_bytes(b"base")
    restart.write_bytes(b"child")
    output.write_bytes(b"previous")
    calls = []
    controller = ProcessController()
    if fail_at == "disk":
        from types import SimpleNamespace

        monkeypatch.setattr(
            "modules.submitter.odb_merge_execution.shutil.disk_usage",
            lambda path: SimpleNamespace(free=0),
        )

    def run(args, cwd, log, controller):
        if args[1] == "restartjoin":
            work = cwd / next(
                arg.split("=", 1)[1] for arg in args if arg.startswith("originalodb=")
            )
            assert work.read_bytes() == b"base"
            assert ("copyoriginal" in args) == copy_original
            if copy_original:
                work = cwd / ("Restart_" + work.name)
            data = b"extra zero" if "history" in args else b"fields"
            calls.append(data)
            work.write_bytes(data)
        elif args[2] == "restore_odb_history.py":
            calls.append("restore")
            assert (cwd / args[5]).read_bytes() == b"fields"
            if fail_at == "restore":
                log('ABASUB_ODB_RESTORE_FAILED|"unsupported load case"')
                return
            (cwd / args[5]).write_bytes(b"restored")
            log("ABASUB_ODB_HISTORY_RESTORED")
        elif args[-1] == "--restored":
            calls.append("final check")
            assert (cwd / args[5]).read_bytes() == b"restored"
            if fail_at == "final_check":
                log('ABASUB_ODB_VALIDATION_FAILED|"saved location differs"')
                return
            write_validation_receipt(args, cwd)
            path = cwd / args[7]
            payload = json.loads(path.read_text())
            payload["historyMethod"] = "source-samples"
            path.write_text(json.dumps(payload))
            log("ABASUB_ODB_VALIDATION_OK")
        else:
            calls.append("extra zero")
            log('ABASUB_ODB_EXTRA_INITIAL_ZERO|"U / region / RF / data"')

    monkeypatch.setattr("modules.submitter.odb_merge_execution.run_process", run)
    request = OdbMergeRequest(
        original,
        restart,
        output,
        copy_original=copy_original,
        conflict_policy=MergeConflictPolicy.OVERWRITE,
    )
    if fail_at:

        def progress(percent, phase):
            if fail_at == "cancel" and percent == 84:
                controller.cancel()

        with pytest.raises(
            ProcessCancelled if fail_at == "cancel" else OdbMergeError
        ) as error:
            execute_odb_merge(request, progress=progress, controller=controller)
        if fail_at == "disk":
            assert "磁盘空间不足" in str(error.value)
        assert output.read_bytes() == b"previous"
        assert not list(tmp_path.glob("*.merge-validation.json"))
    else:
        execute_odb_merge(request)
        assert output.read_bytes() == b"restored"
        assert calls == [
            b"extra zero",
            "extra zero",
            b"fields",
            "restore",
            "final check",
        ]
    assert original.read_bytes() == b"base"
    assert restart.read_bytes() == b"child"
    assert not list(tmp_path.glob(".abasub-odb-merge-*"))


@pytest.mark.parametrize(
    "previous,deny_old_link", [(False, False), (True, False), (True, True)]
)
def test_receipt_link_failure_restores_existing_target_or_removes_new_target(
    tmp_path, monkeypatch, previous, deny_old_link
):
    import os

    original, restart, output = [
        tmp_path / name for name in ("base.odb", "restart.odb", "full_joined.odb")
    ]
    original.write_bytes(b"base")
    restart.write_bytes(b"restart")
    if previous:
        output.write_bytes(b"previous")
    if deny_old_link:
        real_link = os.link

        def link(source, dest):
            if dest.name == PREVIOUS_TARGET:
                raise PermissionError("old target forbids hard links")
            real_link(source, dest)

        monkeypatch.setattr(os, "link", link)
    old_receipt = tmp_path / "previous.merge-validation.json"
    old_receipt.write_text("previous receipt")

    def run(args, cwd, log, controller):
        if args[1] == "restartjoin":
            (cwd / "abasub_join_working.odb").write_bytes(b"validated new")
        else:
            write_validation_receipt(args, cwd)
            log("ABASUB_ODB_VALIDATION_OK")

    def fail_receipt(prepared, destination, joined, stamp):
        assert joined.read_bytes() == b"validated new"
        assert file_identity(joined) == stamp and not destination.exists()
        raise OSError("Receipt unavailable")

    monkeypatch.setattr("modules.submitter.odb_merge_execution.run_process", run)
    monkeypatch.setattr(
        "modules.submitter.odb_merge_execution.publish_receipt", fail_receipt
    )
    with pytest.raises(OSError, match="Receipt unavailable"):
        execute_odb_merge(
            OdbMergeRequest(
                original, restart, output, conflict_policy=MergeConflictPolicy.OVERWRITE
            )
        )
    assert (output.read_bytes() if output.exists() else None) == (
        b"previous" if previous else None
    )
    assert old_receipt.read_text() == "previous receipt"
    assert not list(tmp_path.glob(".abasub-*")) and not list(
        tmp_path.glob("*_original.odb")
    )


def test_final_notification_failure_after_overwrite_still_returns_committed_receipt(
    tmp_path, monkeypatch
):
    import errno

    original, restart, output = [
        tmp_path / name for name in ("base.odb", "restart.odb", "full_joined.odb")
    ]
    original.write_bytes(b"base")
    restart.write_bytes(b"restart")
    output.write_bytes(b"previous")
    old_receipt = tmp_path / "previous.merge-validation.json"
    old_receipt.write_text("old")

    def run(args, cwd, log, controller):
        if args[1] == "restartjoin":
            (cwd / "abasub_join_working.odb").write_bytes(b"new")
        else:
            write_validation_receipt(args, cwd)
            log("ABASUB_ODB_VALIDATION_OK")

    def progress(percent, phase):
        if percent == 100:
            raise OSError(errno.ENOSPC, "no space for observer")

    monkeypatch.setattr("modules.submitter.odb_merge_execution.run_process", run)
    result = execute_odb_merge(
        OdbMergeRequest(
            original, restart, output, conflict_policy=MergeConflictPolicy.OVERWRITE
        ),
        progress,
    )
    assert result.output_odb.read_bytes() == b"new"
    assert json.loads(result.validation_report.read_text())[
        "validatedFile"
    ] == file_identity(output)
    assert old_receipt.read_text() == "old"
    assert not list(tmp_path.glob(".abasub-*"))


@pytest.mark.parametrize(
    "situation",
    [
        "before",
        "after",
        "copy",
        "receipt_exists",
        "conflict",
        "legacy",
        "missing_backup",
        "swapped_backups",
        "renumbered",
    ],
)
def test_recovered_receipt_is_only_exposed_for_the_matching_target(tmp_path, situation):
    import os
    import shutil

    attempt = "a" * 32
    request = OdbMergeRequest(
        tmp_path / "p.odb",
        tmp_path / "r.odb",
        tmp_path / "full_joined.odb",
        attempt_id=attempt,
    )
    target = (
        request.output_odb
        if situation != "renumbered"
        else tmp_path / "full_joined_002.odb"
    )
    stage = tmp_path / (".abasub-odb-merge-" + attempt)
    stage.mkdir()
    candidate = stage / "candidate.odb"
    candidate.write_bytes(b"new")
    target.write_bytes(b"old")
    os.link(target, stage / PREVIOUS_TARGET)
    identity = file_identity(candidate)
    assert identity is not None
    document = {
        "status": "verified",
        "attemptId": attempt,
        "validatedFile": identity,
        "previousFile": file_identity(target),
        "includeHistory": True,
        "originalPath": str(request.original_odb),
        "restartPath": str(request.restart_odb),
        "joinedPath": str(target),
    }
    receipt = target.with_suffix(f".{attempt}.merge-validation.json")
    for key, stem in (("original", "p"), ("restart", "r")):
        backup = tmp_path / (stem + "_original.odb")
        backup.write_text(stem)
        document[key + "Backup"] = str(backup)
        document[key + "BackupFile"] = file_identity(backup)
    if situation == "missing_backup":
        backup.unlink()
    if situation == "swapped_backups":
        document["originalBackup"] = document["restartBackup"]
    if situation == "legacy":
        receipt.write_text(
            json.dumps({"status": "verified", "joinedPath": str(target)})
        )
    else:
        (stage / PREPARED_RECEIPT).write_text(json.dumps(document))
        if situation == "copy":
            shutil.copy2(candidate, target)
        elif situation != "before":
            os.replace(candidate, target)
    if situation == "receipt_exists":
        receipt.write_text(json.dumps(document))
    if situation == "conflict":
        receipt.write_text("unrelated")
    message = recover_publication(request, attempt)
    if situation in ("before", "copy", "missing_backup", "swapped_backups"):
        assert not receipt.exists() and "已确认目标" not in message
    elif situation in ("after", "receipt_exists", "renumbered"):
        assert "已确认目标" in message and json.loads(receipt.read_text()) == document
        assert recover_publication(request, attempt) == message
    elif situation == "conflict":
        assert "已确认目标" not in message and receipt.read_text() == "unrelated"
    else:
        assert not message and json.loads(receipt.read_text()) == {
            "status": "verified",
            "joinedPath": str(target),
        }
