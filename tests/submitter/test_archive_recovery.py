from __future__ import annotations

from pathlib import Path

import pytest

from modules.submitter import local_archive
from modules.submitter.local_archive_state import ArchiveBusyError, ArchiveStateStore
from modules.submitter.local_job_execution import (
    LocalJobProcessController,
    _completed_result,
    run_archive_only,
)
from tests.submitter.test_local_archive import archive_fixture, source_bytes


def recovery_fixture(tmp_path):
    source, item = archive_fixture(tmp_path, cleanup=True)
    item.attempt_id = "original-attempt"
    store = ArchiveStateStore(tmp_path / "state")
    return source, item, store


def run_initial(item, source, store):
    return _completed_result(item, source, "no solver fixture", "计算已完成", LocalJobProcessController(archive_store=store), None)


@pytest.mark.parametrize("phase", ["prepared", "ready", "published", "partial_cleanup", "empty_source", "done"])
def test_resume_original_attempt_at_each_boundary_without_solver(tmp_path, monkeypatch, phase):
    source, item, store = recovery_fixture(tmp_path)
    before = source_bytes(source)
    save, unlink, rmdir = store.save, Path.unlink, Path.rmdir

    def interrupted_save(item, state):
        save(item, state)
        if state["phase"] == phase:
            raise SystemExit("simulated process loss after durable checkpoint")

    def interrupted_unlink(path, *args, **kwargs):
        if phase == "partial_cleanup" and path == source / "case.odb":
            raise SystemExit("lost during cleanup")
        return unlink(path, *args, **kwargs)

    def interrupted_rmdir(path, *args, **kwargs):
        if phase == "empty_source" and path == source:
            raise SystemExit("lost before directory removal")
        return rmdir(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(store, "save", interrupted_save)
        patch.setattr(Path, "unlink", interrupted_unlink)
        patch.setattr(Path, "rmdir", interrupted_rmdir)
        with pytest.raises(SystemExit):
            run_initial(item, source, store)
    state = store.read(item)
    assert state["solveConfirmed"] and state["attemptId"] == item.attempt_id
    monkeypatch.setattr("subprocess.Popen", lambda *_a, **_k: pytest.fail("Recovery invoked a process"))
    result = run_archive_only(item, LocalJobProcessController(archive_store=store))
    assert result.archive_status == "已归档", result.archive_error
    assert not result.archive_recovery_available and not source.exists()
    assert all((Path(result.archive_destination) / name).read_bytes() == data for name, data in before.items())
    assert store.read(item)["phase"] == "done"


def test_interrupted_copy_reuses_verified_files_and_preserves_incomplete_payload(tmp_path, monkeypatch):
    source, item, store = recovery_fixture(tmp_path)
    copied = local_archive._copy_verified
    count = 0

    def interrupt(src, target, identity, check, tick):
        nonlocal count
        count += 1
        if count == 2:
            target.write_bytes(b"partial")
            raise SystemExit("lost during copy")
        return copied(src, target, identity, check, tick)

    with monkeypatch.context() as patch:
        patch.setattr(local_archive, "_copy_verified", interrupt)
        with pytest.raises(SystemExit):
            run_initial(item, source, store)
    state = store.read(item)
    complete_path = Path(state["stage"]) / "case.inp"
    identity = complete_path.stat().st_ino
    result = run_archive_only(item, LocalJobProcessController(archive_store=store))
    assert result.archive_status == "已归档", result.archive_error
    assert (Path(result.archive_destination) / "case.inp").stat().st_ino == identity
    evidence = store.read(item)["evidence"]
    assert len(evidence) == 1 and (Path(evidence[0]) / "case.odb").read_bytes() == b"partial"


def test_failed_root_can_be_repaired_then_archived_without_new_attempt(tmp_path):
    source, item, store = recovery_fixture(tmp_path)
    root = Path(item.archive_dir)
    root.write_bytes(b"fixture obstruction")
    first = run_initial(item, source, store)
    assert first.archive_status == "归档失败" and first.archive_recovery_available
    root.unlink()
    final = run_archive_only(item, LocalJobProcessController(archive_store=store))
    assert final.archive_status == "已归档" and item.attempt_id == "original-attempt"


def test_archive_claim_blocks_a_second_owner_and_releases_after_error(tmp_path):
    _, item, store = recovery_fixture(tmp_path)
    with store.claim(item), pytest.raises(ArchiveBusyError), store.claim(item):
        pytest.fail("second owner admitted")
    with store.claim(item):
        pass


@pytest.mark.parametrize("tamper", ["source", "attemptId", "relative", "digest", "source_change"])
def test_invalid_recovery_never_deletes_remaining_source(tmp_path, monkeypatch, tamper):
    source, item, store = recovery_fixture(tmp_path)
    save = store.save

    def stop(item, state):
        save(item, state)
        if state["phase"] == "ready":
            raise SystemExit()

    with monkeypatch.context() as patch:
        patch.setattr(store, "save", stop)
        with pytest.raises(SystemExit):
            run_initial(item, source, store)
    state = store.read(item)
    if tamper == "source":
        state["source"] = str(tmp_path)
    elif tamper == "attemptId":
        state["attemptId"] = "other-attempt"
    elif tamper == "relative":
        state["files"]["../outside"] = state["files"].pop("case.inp")
    elif tamper == "digest":
        local_archive._publish(Path(state["stage"]), Path(state["destination"]))
        (Path(state["destination"]) / "case.odb").write_bytes(b"corrupt archive")
    else:
        (source / "case.res").write_bytes(b"changed after interruption")
    save(item, state)
    before = source_bytes(source)
    result = run_archive_only(item, LocalJobProcessController(archive_store=store))
    assert result.archive_status != "已归档" and result.archive_error
    assert source_bytes(source) == before
