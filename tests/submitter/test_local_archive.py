from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from modules.control_plane.local_queue_runtime import LocalQueueRuntimeManager
from modules.submitter import local_archive
from modules.submitter.constants import STATUS_COMPLETED
from modules.submitter.local_job_execution import (
    LocalJobProcessController,
    _archive_result,
    _completed_result,
)
from modules.submitter.models import QueueItem


def archive_fixture(tmp_path, *, cleanup=False):
    source = tmp_path / "ssd" / "case"
    source.mkdir(parents=True)
    for suffix, data in ((".inp", b"input"), (".odb", b"odb data"), (".res", b"restart data")):
        (source / ("case" + suffix)).write_bytes(data)
    item = QueueItem(job_name="case", calculation_root_dir=str(source.parent),
                     archive_dir=str(tmp_path / "archive"), cleanup_after_archive=cleanup)
    return source, item


def test_archive_without_cleanup_preserves_source_and_publishes_all_files(tmp_path):
    source, item = archive_fixture(tmp_path)
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    destination, status, error = _archive_result(item, source)
    assert status == "已归档" and not error
    assert {p.name: p.read_bytes() for p in source.iterdir()} == before
    assert all((Path(destination) / name).read_bytes() == data for name, data in before.items())


def test_invalid_archive_root_is_reported_without_changing_solver_outcome(tmp_path):
    source, item = archive_fixture(tmp_path)
    root = Path(item.archive_dir)
    root.write_bytes(b"unrelated file")
    destination, status, error = _archive_result(item, source)
    assert not destination and status == "归档失败" and error
    assert (source / "case.odb").read_bytes() == b"odb data"
    assert root.read_bytes() == b"unrelated file"


def source_bytes(source):
    return {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob("*") if p.is_file()}


def test_nested_cleanup_has_verified_manifest_and_does_not_touch_original_input(tmp_path):
    source, item = archive_fixture(tmp_path, cleanup=True)
    original = tmp_path / "original.inp"
    original.write_bytes(b"original model")
    item.source_inp_path = str(original)
    (source / "reports").mkdir()
    (source / "reports" / "history.txt").write_bytes(b"history")
    (source / "empty").mkdir()
    before = source_bytes(source)
    destination, status, error = _archive_result(item, source)
    assert status == "已归档" and not error and not source.exists()
    assert original.read_bytes() == b"original model"
    manifest = json.loads((Path(destination) / local_archive.MANIFEST_NAME).read_text())
    assert manifest["state"] == "complete" and set(manifest["files"]) == set(before)
    assert (Path(destination) / "empty").is_dir()
    for name, data in before.items():
        assert (Path(destination) / name).read_bytes() == data
        assert manifest["files"][name] == {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


@pytest.mark.parametrize("failure", ["copy", "source_changed", "new_file", "target_corrupt", "publish"])
def test_failed_stage_never_publishes_or_removes_source(tmp_path, monkeypatch, failure):
    source, item = archive_fixture(tmp_path, cleanup=True)
    before = source_bytes(source)
    real = local_archive._copy_verified
    calls = 0

    def injected(src, target, identity, check, tick):
        nonlocal calls
        calls += 1
        if failure == "copy" and calls == 2:
            raise OSError("copy fixture failed")
        value = real(src, target, identity, check, tick)
        if calls == 1 and failure == "source_changed":
            src.write_bytes(b"changed by fixture")
        if calls == 1 and failure == "new_file":
            (source / "new.txt").write_bytes(b"new")
        return value

    monkeypatch.setattr(local_archive, "_copy_verified", injected)
    if failure == "target_corrupt":
        monkeypatch.setattr(local_archive, "_digest", lambda *_: "not the source digest")
    if failure == "publish":
        monkeypatch.setattr(local_archive, "_publish", lambda *_: (_ for _ in ()).throw(OSError("rename denied")))
    destination, status, error = _archive_result(item, source)
    assert not destination and status == "归档失败" and error
    after = source_bytes(source)
    assert set(before) <= set(after)  # No original file was removed, including injected source changes.
    if failure != "source_changed":
        assert all(after[key] == value for key, value in before.items())
    assert not (Path(item.archive_dir) / "case").exists()
    assert len(list(Path(item.archive_dir).glob("*.partial"))) == 1


@pytest.mark.parametrize("when", ["before", "copy", "cleanup"])
def test_cancel_preserves_source_and_distinguishes_published_archive(tmp_path, when):
    source, item = archive_fixture(tmp_path, cleanup=True)
    before = source_bytes(source)
    cancel = when == "before"

    def progress(message, *_):
        nonlocal cancel
        if (when == "copy" and "复制" in message) or (when == "cleanup" and "清理" in message):
            cancel = True

    destination, status, error = _archive_result(item, source, cancelled=lambda: cancel, progress=progress)
    assert error and source_bytes(source) == before
    assert status == ("已归档，清理未完成" if when == "cleanup" else "归档已取消")
    assert bool(destination) == (when == "cleanup")


def test_cleanup_failure_keeps_complete_archive_and_remaining_source(tmp_path, monkeypatch):
    source, item = archive_fixture(tmp_path, cleanup=True)
    before = source_bytes(source)
    unlink = Path.unlink

    def blocked(path, *args, **kwargs):
        if path == source / "case.res":
            raise PermissionError("file in use")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", blocked)
    destination, status, error = _archive_result(item, source)
    assert status == "已归档，清理未完成" and "file in use" in error
    assert (source / "case.res").is_file()
    assert all((Path(destination) / name).read_bytes() == data for name, data in before.items())


def test_detected_archive_corruption_is_not_eligible_for_restart(tmp_path):
    source, item = archive_fixture(tmp_path, cleanup=True)

    def corrupt(message, *_):
        if "清理" in message:
            (Path(item.archive_dir) / "case" / "case.odb").write_bytes(b"corrupt")

    destination, status, error = _archive_result(item, source, progress=corrupt)
    assert status == "归档需核对" and destination and error
    assert (source / "case.odb").read_bytes() == b"odb data"
    item.archive_destination, item.archive_status = destination, status
    item.effective_work_dir = str(source)
    assert LocalQueueRuntimeManager._dependency_odb_path(item) == ""


@pytest.mark.parametrize("problem", ["empty", "lck", "nested_root", "unsafe_cleanup", "original_input"])
def test_invalid_plan_does_not_move_files(tmp_path, problem):
    source, item = archive_fixture(tmp_path, cleanup=True)
    if problem == "empty":
        for path in source.iterdir():
            path.unlink()
    elif problem == "lck":
        (source / "case.lck").touch()
    elif problem == "nested_root":
        item.archive_dir = str(source / "archive")
    elif problem == "unsafe_cleanup":
        item.calculation_root_dir = str(tmp_path / "unrelated")
    else:
        item.source_inp_path = str(source / "case.inp")
    before = source_bytes(source)
    destination, status, error = _archive_result(item, source)
    assert not destination and status == "归档失败" and error
    assert source_bytes(source) == before


def test_existing_archive_is_never_overwritten(tmp_path):
    source, item = archive_fixture(tmp_path)
    existing = Path(item.archive_dir) / "case"
    existing.mkdir(parents=True)
    (existing / "case.odb").write_bytes(b"previous run")
    destination, status, error = _archive_result(item, source)
    assert status == "已归档" and not error and Path(destination) != existing
    assert (existing / "case.odb").read_bytes() == b"previous run"


def test_solve_success_survives_archive_failure(tmp_path):
    source, item = archive_fixture(tmp_path)
    Path(item.archive_dir).write_bytes(b"file")
    result = _completed_result(item, source, "fixture", "求解已完成", LocalJobProcessController(), None)
    assert result.status == STATUS_COMPLETED and result.archive_status == "归档失败"
    assert "归档失败" in result.message and result.archive_error and not result.archive_destination


@pytest.mark.parametrize("status,usable", [("已归档", True), ("已归档，清理未完成", True),
                                         ("归档失败", False), ("归档需核对", False), ("", False)])
def test_partial_legacy_archive_never_falls_back_to_split_restart_family(tmp_path, status, usable):
    source, item = archive_fixture(tmp_path)
    partial = Path(item.archive_dir) / "case"
    partial.mkdir(parents=True)
    (partial / "case.odb").write_bytes(b"partial")
    item.archive_destination = str(partial)
    item.archive_status = status
    item.effective_work_dir = str(source)
    assert bool(LocalQueueRuntimeManager._dependency_odb_path(item)) is usable


@pytest.mark.skipif(os.name != "nt", reason="NTFS junction check")
def test_nested_directory_junction_is_rejected_without_touching_target(tmp_path):
    source, item = archive_fixture(tmp_path, cleanup=True)
    other = tmp_path / "unrelated"
    other.mkdir()
    (other / "original.txt").write_bytes(b"do not touch")
    link = source / "linked"
    assert other.resolve().is_relative_to(tmp_path.resolve()) and link.absolute().is_relative_to(tmp_path.resolve())
    created = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link), str(other)],
                             capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10, check=False)
    assert created.returncode == 0 and link.is_junction()
    destination, status, error = _archive_result(item, source)
    assert not destination and status == "归档失败" and error
    assert (other / "original.txt").read_bytes() == b"do not touch"
    assert (source / "case.odb").read_bytes() == b"odb data"


@pytest.mark.parametrize("phase", ["before_publish", "after_publish"])
def test_real_process_interruption_preserves_source_and_explicit_publication_boundary(tmp_path, phase):
    source, item = archive_fixture(tmp_path, cleanup=True)
    before = source_bytes(source)
    marker = tmp_path / "phase-ready"
    worker = tmp_path / "archive_worker.py"
    worker.write_text('''import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from modules.submitter import local_archive
from modules.submitter.models import QueueItem
source, root, marker, phase = map(str, sys.argv[2:])
def stop():
    Path(marker).write_text("ready")
    time.sleep(120)
if phase == "before_publish":
    local_archive._publish = lambda *_: stop()
def progress(message, *_):
    if phase == "after_publish" and "清理" in message: stop()
item = QueueItem(job_name="case", calculation_root_dir=str(Path(source).parent),
                 archive_dir=root, cleanup_after_archive=True)
local_archive.archive_job_files(item, Path(source), progress=progress)
''', encoding="utf-8")
    child = subprocess.Popen([sys.executable, str(worker), str(Path(__file__).resolve().parents[2]),
                              str(source), item.archive_dir, str(marker), phase],
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        deadline = time.monotonic() + 15
        while not marker.exists() and time.monotonic() < deadline:
            assert child.poll() is None
            time.sleep(.03)
        assert marker.exists()
    finally:
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=10)
    assert source_bytes(source) == before
    destination = Path(item.archive_dir) / "case"
    assert destination.exists() is (phase == "after_publish")
    if phase == "after_publish":
        manifest = json.loads((destination / local_archive.MANIFEST_NAME).read_text())
        assert manifest["state"] == "complete" and set(manifest["files"]) == set(before)
        assert all((destination / name).read_bytes() == data for name, data in before.items())
    else:
        assert len(list(Path(item.archive_dir).glob("*.partial"))) == 1
