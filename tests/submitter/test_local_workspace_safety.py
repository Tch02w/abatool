"""Preparation rejection must leave existing model and restart files intact."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from modules.submitter import local_job_execution as execution
from modules.submitter import local_workspace as workspace
from modules.submitter.models import QueueItem


def fixture(tmp_path):
    source = tmp_path / "source"
    work = tmp_path / "ssd" / "case"
    source.mkdir()
    work.mkdir(parents=True)
    (source / "case.inp").write_bytes(b"new input")
    (source / "parent.odb").write_bytes(b"new parent odb")
    (source / "parent.res").write_bytes(b"new parent restart")
    (work / "case.inp").write_bytes(b"existing input")
    (work / "parent.odb").write_bytes(b"existing parent odb")
    (work / "parent.res").write_bytes(b"existing parent restart")
    item = QueueItem(inp_path=str(source / "case.inp"), source_inp_path=str(source / "case.inp"),
                     job_name="case", oldjob_path=str(source / "parent.odb"),
                     calculation_root_dir=str(work.parent), cores=1, abaqus_command="abaqus2025.bat")
    return source, work, item


def content(directory):
    return {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob("*") if path.is_file()}


@pytest.mark.parametrize("reason", ["target_lock", "parent_lock", "cancel_results", "bad_policy",
                                    "missing_parent", "missing_subroutine", "invalid_memory", "same_job"])
def test_rejected_execution_preserves_all_existing_files(tmp_path, monkeypatch, reason):
    source, work, item = fixture(tmp_path)
    policy = "backup"
    if reason == "target_lock":
        (work / "case.lck").touch()
    elif reason == "parent_lock":
        (source / "parent.lck").touch()
    elif reason == "cancel_results":
        (work / "case.odb").write_bytes(b"old result")
        policy = "cancel"
    elif reason == "bad_policy":
        policy = "unknown"
    elif reason == "missing_parent":
        item.oldjob_path = str(source / "missing.odb")
    elif reason == "missing_subroutine":
        item.fortran_path = str(source / "missing.for")
    elif reason == "invalid_memory":
        item.memory = "not memory"
    else:
        item.job_name = "parent"
    original_source, original_work = content(source), content(work)
    original_tree = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))
    monkeypatch.setattr(execution.subprocess, "Popen", lambda *a, **k: pytest.fail("Rejected input launched a process"))
    with pytest.raises((RuntimeError, ValueError, FileNotFoundError)):
        execution.execute_local_job(item, policy, execution.LocalJobProcessController())
    assert content(source) == original_source
    assert content(work) == original_work
    assert sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*")) == original_tree


@pytest.mark.parametrize("name", ["../escaped", "..\\escaped",
                                 pytest.param("CON", marks=pytest.mark.skipif(os.name != "nt", reason="Windows reserved name"))])
def test_rejects_unsafe_job_path_before_creating_directories(tmp_path, monkeypatch, name):
    _source, work, item = fixture(tmp_path)
    item.job_name = name
    monkeypatch.setattr(execution.subprocess, "Popen", lambda *a, **k: pytest.fail("Invalid job launched"))
    before = content(tmp_path)
    with pytest.raises(ValueError):
        execution.execute_local_job(item, "backup", execution.LocalJobProcessController())
    assert content(tmp_path) == before
    assert not (work.parent.parent / "escaped").exists()


def test_preparing_input_in_its_own_calculation_directory_is_not_a_copy_error(tmp_path):
    _, work, item = fixture(tmp_path)
    item.inp_path = item.source_inp_path = str(work / "case.inp")
    item.oldjob_path = ""
    before = content(work)
    prepared, directory, oldjob = execution._prepare_workspace(item)
    assert prepared == work / "case.inp" and directory == work and oldjob == ""
    assert content(work) == before


def test_cancel_before_preparation_does_not_change_files_or_start_solver(tmp_path, monkeypatch):
    _source, _work, item = fixture(tmp_path)
    controller = execution.LocalJobProcessController()
    controller.cancel()
    before = content(tmp_path)
    monkeypatch.setattr(execution.subprocess, "Popen", lambda *a, **k: pytest.fail("Cancelled preparation launched"))
    result = execution.execute_local_job(item, "backup", controller)
    assert result.status == execution.STATUS_TERMINATED
    assert content(tmp_path) == before


@pytest.mark.parametrize("stage", ["copy", "starting"])
def test_cancel_during_preparation_or_at_launch_gate_never_starts_solver(tmp_path, monkeypatch, stage):
    _source, work, item = fixture(tmp_path)
    controller = execution.LocalJobProcessController()
    before = content(work)
    original_copy = workspace.shutil.copy2

    def copy(*args, **kwargs):
        result = original_copy(*args, **kwargs)
        if stage == "copy":
            controller.cancel()
        return result

    def progress(phase, *_):
        if stage == "starting" and phase == "starting":
            controller.cancel()

    monkeypatch.setattr(workspace.shutil, "copy2", copy)
    monkeypatch.setattr(execution.subprocess, "Popen", lambda *a, **k: pytest.fail("Cancelled preparation launched"))
    result = execution.execute_local_job(item, "backup", controller, progress=progress)
    assert result.status == execution.STATUS_TERMINATED
    if stage == "copy":
        assert content(work) == before


@pytest.mark.parametrize("kind", ["input", "restart"])
def test_failed_copy_keeps_preexisting_target(tmp_path, monkeypatch, kind):
    _source, work, item = fixture(tmp_path)
    if kind == "restart":
        item.source_inp_path = item.inp_path = str(work / "case.inp")
        monkeypatch.setattr(workspace.os, "link", lambda *a: (_ for _ in ()).throw(OSError("no hardlinks")))
    before = content(work)

    def fail_copy(source_path, target):
        Path(target).write_bytes(b"partial transfer")
        raise OSError("fixture copy failed")

    monkeypatch.setattr(workspace.shutil, "copy2", fail_copy)
    with pytest.raises(OSError, match="fixture copy failed"):
        execution._prepare_workspace(item)
    assert content(work) == before


def test_replacing_hardlinked_input_does_not_write_through_to_another_original(tmp_path):
    source, work, item = fixture(tmp_path)
    other = tmp_path / "other-original.inp"
    other.write_bytes(b"another original")
    (work / "case.inp").unlink()
    os.link(other, work / "case.inp")
    execution._prepare_workspace(item)
    assert other.read_bytes() == b"another original"
    assert (work / "case.inp").read_bytes() == (source / "case.inp").read_bytes()
    assert not other.samefile(work / "case.inp")


def test_changed_source_is_not_published(tmp_path, monkeypatch):
    _source, work, item = fixture(tmp_path)
    original_copy = workspace.shutil.copy2
    before = content(work)

    def changing_copy(source_path, target):
        original_copy(source_path, target)
        Path(source_path).write_bytes(b"changed by fixture during transfer")

    monkeypatch.setattr(workspace.shutil, "copy2", changing_copy)
    with pytest.raises(RuntimeError, match="源文件发生变化"):
        execution._prepare_workspace(item)
    assert content(work) == before


def test_result_directory_is_rejected_before_copying(tmp_path):
    _source, work, item = fixture(tmp_path)
    (work / "case.odb").mkdir()
    before = content(tmp_path)
    with pytest.raises(ValueError, match="同名结果不是普通文件"):
        execution._prepare_workspace(item)
    assert content(tmp_path) == before


@pytest.mark.skipif(os.name != "nt", reason="Windows NTFS junction boundary")
def test_calculation_job_junction_is_rejected_without_touching_target(tmp_path):
    _source, work, item = fixture(tmp_path)
    actual = tmp_path / "unrelated-directory"
    assert work.resolve().is_relative_to(tmp_path.resolve()) and actual.resolve().is_relative_to(tmp_path.resolve())
    work.rename(actual)
    result = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(work), str(actual)],
                            capture_output=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    before = content(actual)
    with pytest.raises(ValueError, match="作业目录"):
        execution._prepare_workspace(item)
    assert content(actual) == before


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows command argument parsing")
@pytest.mark.parametrize("filename", ["载荷 输入.inp", "load&set.inp"], ids=["spaces", "ampersand"])
def test_datacheck_input_filename_reaches_launcher_as_one_literal_argument(tmp_path, filename):
    source = tmp_path / filename
    source.write_text("*Heading\n", encoding="utf-8")
    helper = tmp_path / "capture.py"
    helper.write_text("import sys,json\nfrom pathlib import Path\n"
                      "Path(__file__).with_suffix('.json').write_text(json.dumps(sys.argv[1:]),encoding='utf-8')\n",
                      encoding="ascii")
    launcher = tmp_path / "arguments.cmd"
    launcher.write_text(f'@echo off\n"{sys.executable}" "%~dp0capture.py" %*\n', encoding="ascii")
    item = QueueItem(job_name="case", inp_path=str(source), cores=1, datacheck_only=True,
                     abaqus_command=str(launcher))
    command_line = execution._execution_command(item, source, "")
    result = subprocess.run(command_line, shell=True, cwd=tmp_path, capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW, check=False, timeout=10)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    args = json.loads(helper.with_suffix(".json").read_text(encoding="utf-8"))
    assert "input=" + filename in args
    assert "datacheck" in args and source.read_text(encoding="utf-8") == "*Heading\n"


def test_relative_subroutine_is_resolved_before_changing_working_directory(tmp_path, monkeypatch):
    source, _work, item = fixture(tmp_path)
    (source / "material.for").write_text("fixture", encoding="ascii")
    item.fortran_path = "material.for"
    monkeypatch.chdir(source)
    plan = workspace.plan_workspace(item)
    command_line = execution._execution_command(item, plan.prepared_inp, plan.oldjob_arg, validation_inp=plan.source_inp)
    assert f'user="{source / "material.for"}"' in command_line


@pytest.mark.parametrize("restart", [False, True])
def test_existing_temporary_name_is_neither_overwritten_nor_cleaned(tmp_path, monkeypatch, restart):
    _source, work, item = fixture(tmp_path)
    if restart:
        item.source_inp_path = item.inp_path = str(work / "case.inp")
    filename = "parent.odb" if restart else "case.inp"
    temporary = work / f".{filename}.prepare-fixed.tmp"
    temporary.write_bytes(b"belongs to another operation")
    monkeypatch.setattr(workspace, "uuid4", lambda: SimpleNamespace(hex="fixed"))
    before = content(work)
    with pytest.raises(FileExistsError):
        execution._prepare_workspace(item)
    assert content(work) == before
