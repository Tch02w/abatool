from __future__ import annotations

import base64
import json
import subprocess
import sys
import threading
import time

import pytest

from modules.control_plane.events import EventStore
from modules.control_plane.remote_job_monitoring import (
    RemoteCompletionState,
    new_tail_lines,
)
from modules.control_plane.remote_jobs import (
    RemoteJobOperation,
    RemoteJobOperationManager,
    RemoteJobRequest,
    _job_status_script,
    _start_job_script,
)


def sample(**changes):
    return dict(process_active=False, lock_exists=False, probe_complete=True, output_signature="sta:1",
                sta_tail="", log_tail="", dat_tail="", msg_tail="", **changes)


def evaluate(state, snapshot, **options):
    return state.observe(snapshot, job_name="case", **options)


@pytest.mark.parametrize("datacheck", [False, True])
def test_disappearance_without_success_is_never_reported_as_success(datacheck):
    state = RemoteCompletionState()
    for _ in range(4):
        assert evaluate(state, sample(), datacheck=datacheck)[0] == "running"
    assert evaluate(state, sample(), datacheck=datacheck)[2] == "REMOTE_JOB_EXIT_UNCONFIRMED"


@pytest.mark.parametrize("reason", ["process_active", "lock_exists"])
def test_completion_waits_for_inactive_stable_outputs(reason):
    state = RemoteCompletionState()
    view = sample()
    view.update(sta_tail="THE ANALYSIS HAS COMPLETED SUCCESSFULLY", **{reason: True})
    for _ in range(8):
        assert evaluate(state, view)[0] == "running"
    view[reason] = False
    assert evaluate(state, view)[0] == "running"
    view["output_signature"] = "sta:2"
    assert evaluate(state, view)[0] == "running"
    assert evaluate(state, view)[0] == "running"
    assert evaluate(state, view)[0] == "succeeded"


@pytest.mark.parametrize("field", ["sta_tail", "log_tail", "dat_tail", "msg_tail"])
def test_error_beats_success_and_remains_after_rolling_out_of_tail(field):
    state = RemoteCompletionState()
    view = sample()
    view.update(sta_tail="THE ANALYSIS HAS COMPLETED SUCCESSFULLY", process_active=True)
    view[field] += "\n***ERROR: bad input"
    assert evaluate(state, view)[0] == "running"
    view[field] = ""
    view["process_active"] = False
    for _ in range(3):
        result = evaluate(state, view)
    assert result[0] == "failed" and result[2] == "ABAQUS_REMOTE_ERROR"


@pytest.mark.parametrize("patch", [{"probe_complete": False}, {"process_active": "false"}, {"output_signature": ""}])
def test_unreadable_or_malformed_probe_cannot_finish_and_resets_confirmation(patch):
    state = RemoteCompletionState()
    view = sample()
    view["log_tail"] = "Abaqus JOB case COMPLETED"
    evaluate(state, view)
    evaluate(state, view)
    unknown = dict(view, **patch)
    for _ in range(8):
        assert evaluate(state, unknown)[0] == "running"
    assert evaluate(state, view)[0] == "running"
    assert evaluate(state, view)[0] == "running"
    assert evaluate(state, view)[0] == "succeeded"


def test_datacheck_requires_its_own_explicit_completion_line():
    state = RemoteCompletionState()
    view = sample()
    view["log_tail"] = "End Analysis Input File Processor\nAbaqus JOB different COMPLETED"
    for _ in range(3):
        assert evaluate(state, view, datacheck=True)[0] == "running"
    view.update(log_tail="End Analysis Input File Processor\nAbaqus JOB case COMPLETED", output_signature="log:2")
    for _ in range(2):
        assert evaluate(state, view, datacheck=True)[0] == "running"
    assert evaluate(state, view, datacheck=True)[:2] == ("succeeded", "远端数据检查完成")


@pytest.mark.parametrize("diagnostic", ["NUMERICAL SINGULARITY", "ZERO PIVOT", "EXCESSIVE DISTORTION"])
def test_warning_diagnostics_and_iteration_termination_do_not_override_explicit_success(diagnostic):
    state = RemoteCompletionState()
    view = sample()
    view.update(msg_tail=f"***WARNING: {diagnostic}\nIteration terminated normally",
                log_tail="Abaqus JOB case COMPLETED")
    for _ in range(3):
        result = evaluate(state, view)
    assert result[0] == "succeeded"
    state = RemoteCompletionState()
    view["msg_tail"] = f"***ERROR: {diagnostic}"
    for _ in range(3):
        result = evaluate(state, view)
    assert result[0] == "failed"


@pytest.mark.parametrize("cancelling,expected", [(True, "cancelled"), (False, "failed")])
def test_termination_waits_until_process_releases(cancelling, expected):
    state = RemoteCompletionState()
    view = sample()
    view.update(log_tail="THE ANALYSIS HAS BEEN TERMINATED", process_active=True)
    for _ in range(4):
        assert evaluate(state, view, cancelling=cancelling)[0] == "running"
    view["process_active"] = False
    for _ in range(3):
        result = evaluate(state, view, cancelling=cancelling)
    assert result[0] == expected


def test_monitor_keeps_guard_active_and_only_appends_new_remote_log_lines():
    request = RemoteJobRequest.from_payload({"schemaVersion": 1, "clientRequestId": "monitor", "jobName": "case",
        "inputMode": "existing", "inputPath": r"D:\case.inp", "datacheck": False, "cpus": 1, "memory": "90%"})
    operation = RemoteJobOperation(request, status="running", process_id=42, work_directory=r"D:\case")
    manager = RemoteJobOperationManager(EventStore(), None)
    manager._operations[operation.operation_id] = operation
    live = sample()
    live.update(process_active=True, sta_tail="1\n2\nTHE ANALYSIS HAS COMPLETED SUCCESSFULLY")
    done = dict(live, process_active=False)
    sequence = iter([live, live, done, done, done])
    calls = []

    class NoWait:
        def is_set(self):
            return False

        def wait(self, _seconds):
            calls.append((operation.status, list(operation.logs)))

    manager._stop_event = NoWait()
    manager._run_json_script = lambda *_args, **_kwargs: next(sequence)
    try:
        manager._monitor(operation)
        assert len(calls) == 4 and all(status == "running" for status, _logs in calls)
        assert operation.status == "succeeded"
        assert operation.logs == ["1", "2", "THE ANALYSIS HAS COMPLETED SUCCESSFULLY"]
    finally:
        manager._stop_event = threading.Event()
        manager.close()


def test_tail_overlap_rotation_and_rewrite():
    assert new_tail_lines("1\n2", "1\n2") == []
    assert new_tail_lines("1\n2", "2\n3") == ["3"]
    assert new_tail_lines("1\n2", "new") == ["new"]
    assert new_tail_lines("", "1\n1") == ["1", "1"]


@pytest.mark.skipif(sys.platform != "win32", reason="Production server probe is Windows PowerShell")
def test_production_powershell_probe_observes_real_files_and_pid_identity(tmp_path):
    script = tmp_path / "probe.ps1"
    # The current PowerShell process gives a real creation time and no new solver.
    template = ("$ErrorActionPreference='Stop'\n$configJson=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{config}'))\n"
                "$config=$configJson|ConvertFrom-Json\n"
                "if ($config.process_start_ticks -eq 'self') { $config.process_id=$PID; "
                "$config.process_start_ticks=(Get-Process -Id $PID).StartTime.ToUniversalTime().Ticks.ToString() }\n"
                "if ($config.process_start_ticks -eq 'mismatch') { $config.process_id=$PID; $config.process_start_ticks='1' }\n")

    def probe(ticks, directory=tmp_path):
        config = {"work_directory": str(directory), "job_name": "case", "process_id": 0, "process_start_ticks": ticks}
        encoded = base64.b64encode(json.dumps(config).encode()).decode()
        script.write_text(template.replace("{config}", encoded) + _job_status_script(), encoding="utf-8-sig")
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                 "-File", str(script)], capture_output=True, text=True, timeout=20, check=False,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    (tmp_path / "case.log").write_text("Abaqus JOB case COMPLETED", encoding="ascii")
    first = probe("self")
    assert first["probe_complete"] and first["process_active"] and not first["lock_exists"]
    assert first["log_tail"] == "Abaqus JOB case COMPLETED"
    ended = probe("exited")
    assert ended["probe_complete"] and not ended["process_active"]
    assert ended["output_signature"] == first["output_signature"]
    mismatch = probe("mismatch")
    assert mismatch["probe_complete"] and not mismatch["process_active"]
    (tmp_path / "case.msg").write_text("***ERROR: real fixture", encoding="ascii")
    (tmp_path / "case.lck").touch()
    changed = probe("exited")
    assert changed["lock_exists"] and changed["msg_tail"] == "***ERROR: real fixture"
    assert changed["output_signature"] != first["output_signature"]
    assert not probe("")["probe_complete"]
    assert not probe("exited", tmp_path / "missing")["probe_complete"]


@pytest.mark.skipif(sys.platform != "win32", reason="Production remote starter is Windows PowerShell")
def test_production_start_and_monitor_fast_fixture_without_solver(tmp_path):
    command = tmp_path / "fixture command.cmd"
    command.write_text('@echo off\necho called>>calls.txt\necho Abaqus JOB case COMPLETED>case.log\nexit /b 0\n', encoding="ascii")
    config = {"work_directory": str(tmp_path), "job_name": "case", "abaqus_command": str(command),
              "input_name": "fixture.inp", "cpus": 1, "memory": "90%", "datacheck": True, "operation_id": "a" * 32}

    def run(body):
        encoded = base64.b64encode(json.dumps(config).encode()).decode()
        script = tmp_path / "job.ps1"
        script.write_text("$ErrorActionPreference='Stop'\n$config=[Text.Encoding]::UTF8.GetString("
            f"[Convert]::FromBase64String('{encoded}'))|ConvertFrom-Json\n" + body, encoding="utf-8-sig")
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                 "-File", str(script)], capture_output=True, text=True, timeout=20, check=False,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    start = run(_start_job_script())
    assert start["process_id"] > 0 and start["process_start_ticks"]
    config.update(start)
    state = RemoteCompletionState()
    for _ in range(8):
        result = evaluate(state, run(_job_status_script()), datacheck=True)
        if result[0] == "succeeded":
            break
        time.sleep(.1)
    assert result[0] == "succeeded"
    assert run(_start_job_script()) == start
    assert (tmp_path / "calls.txt").read_text().splitlines() == ["called"]
