"""Abaqus 2025 CAE name rules, plus literal command argument preservation.

Source: SIMACAECAERefMap/simacae-c-intdialogbasic.htm (Text fields).
The tests use synthetic INP/text files and a command recorder, never a solver.
"""
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from modules.submitter.command import SubmitOptions, build_abaqus_command, literal_windows_command, validate_job_name


@pytest.mark.parametrize("name", ["GJA-8+2_U40D_V20D", "GJA-8+2_U100D", "1_case", "a-b_c", "a" * 80,
                                 "a+b", "a=b", "a@b", "a#b", "a%b", "a^b"])
def test_documented_job_names_are_accepted(name):
    assert validate_job_name(name) == (True, "")


@pytest.mark.parametrize("name", ["", "a" * 81, "Assembly", "assembly", "_a", "a_", "-a",
                                  "a b", "a\tb", "a\nb", "a\0b"]
                         + ["a" + char + "b" for char in "$&*~!()[]{}|:;'`\"”,.?/\\><"])
def test_documented_invalid_names_report_the_reason(name):
    valid, reason = validate_job_name(name)
    assert not valid and reason


def test_user_plus_names_reach_candidate_and_restart_validation(tmp_path):
    from modules.control_plane.job_queue_commands import JobQueueService
    parent = tmp_path / "GJA-8+2_U40D.inp"
    child = tmp_path / "GJA-8+2_U40D_V20D.inp"
    parent.write_text("*Heading\n", encoding="utf-8")
    child.write_text("*Heading\n*Restart, read\n", encoding="utf-8")
    service = JobQueueService(tmp_path / "joblist.json", external_monitor_interval=999)
    try:
        result = service.execute({"schemaVersion": 1, "action": "addCandidates", "paths": [str(parent), str(child)],
                                  "source": "文件", "skipRestartNames": False, "skipExistingResults": False})
        rows = result["snapshot"]["candidates"]
        assert all(row["valid"] for row in rows)
        child_id = next(row["itemId"] for row in rows if row["jobName"] == child.stem)
        result = service.execute({"schemaVersion": 1, "action": "updateCandidate", "itemId": child_id,
                                  "oldjobPath": str(parent.with_suffix('.odb'))})
        row = next(row for row in result["snapshot"]["candidates"] if row["itemId"] == child_id)
        assert row["valid"] and row["oldjobName"] == parent.stem
    finally:
        service.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows command expansion regression")
@pytest.mark.parametrize("launcher_mode", ["local", "remote", "qt"])
def test_allowed_punctuation_reaches_command_as_literal_arguments(tmp_path, launcher_mode):
    name = "GJA-8+2_%PATH%^@#=test"
    assert validate_job_name(name)[0]
    recorder = tmp_path / "record.py"
    recorder.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "pending = Path('args.pending')\n"
        "pending.write_text(json.dumps(sys.argv[1:]), encoding='utf-8')\n"
        "pending.replace('args.json')\n",
        encoding="utf-8",
    )
    launcher = tmp_path / "fake abaqus.cmd"
    launcher.write_text(f'@"{sys.executable}" "{recorder}" %*\n', encoding="utf-8")
    if launcher_mode == "remote":
        from modules.control_plane.remote_jobs import _start_job_script
        config = {"work_directory": str(tmp_path), "operation_id": "name-test", "job_name": name,
                  "input_name": name + ".inp", "oldjob_name": name + "-old", "abaqus_command": str(launcher),
                  "cpus": 1, "memory": "80%", "execution_arguments": [], "fortran_name": "", "datacheck": False}
        payload = base64.b64encode(json.dumps(config).encode()).decode()
        script = "$ErrorActionPreference='Stop'\n$config=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + payload + "'))|ConvertFrom-Json\n" + _start_job_script()
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
                        base64.b64encode(script.encode('utf-16-le')).decode()], check=True, capture_output=True, timeout=20)
    else:
        command = build_abaqus_command(SubmitOptions(job_name=name, oldjob_path=name + "-old", abaqus_command=str(launcher), cpus=1))
        if launcher_mode == "qt":
            from modules.submitter.job_runtime import start_detached_command
            assert start_detached_command(command, str(tmp_path))
        else:
            command, environment = literal_windows_command(command)
            subprocess.run(command, shell=True, cwd=tmp_path, env=environment, check=True, capture_output=True, timeout=20)
    deadline = time.monotonic() + 10
    output = tmp_path / 'args.json'
    while not output.exists() and time.monotonic() < deadline:
        time.sleep(.05)
    args = json.loads(output.read_text())
    assert "job=" + name in args and "oldjob=" + name + "-old" in args
    if launcher_mode == "remote":
        assert "input=" + name + ".inp" in args and "memory=80%" in args
        from modules.control_plane.remote_jobs import _control_job_script
        config['action'] = 'suspend'
        payload = base64.b64encode(json.dumps(config).encode()).decode()
        script = "$ErrorActionPreference='Stop'\n$config=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + payload + "'))|ConvertFrom-Json\n" + _control_job_script()
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
                        base64.b64encode(script.encode('utf-16-le')).decode()], check=True, capture_output=True, timeout=20)
        assert json.loads(output.read_text()) == ["suspend", "job=" + name]
