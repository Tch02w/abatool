"""Submission overrides survive validation, persistence and actual Windows launch."""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
from dataclasses import replace

import psutil
import pytest

from modules.control_plane.job_drafts import LocalJobDraftPreviewRequest
from modules.control_plane.local_memory import memory_profile_key
from modules.control_plane.remote_jobs import RemoteJobRequest, _start_job_script
from modules.submitter.command import SubmitOptions, build_abaqus_command
from modules.submitter.execution_options import execution_arguments
from modules.submitter.job_draft import LocalJobDraft
from modules.submitter.local_job_execution import (
    LocalJobProcessController,
    _execution_command,
    execute_local_job,
)
from modules.submitter.models import QueueItem
from modules.submitter.queue_store import load_joblist_state
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_job_queue_commands_api import command, post_command
from tests.control_plane.test_remote_job_recovery import (
    RecoverableRemote,
    create,
    request_for,
    view,
    wait_for,
)
from tests.control_plane.test_remote_jobs_api import _connect


def test_old_defaults_are_unchanged_and_gpu_zero_is_an_explicit_override():
    assert build_abaqus_command(SubmitOptions(job_name="case", cpus=1)) == "abaqus job=case cpus=1"
    assert execution_arguments(SubmitOptions(gpu_count=0)) == ["gpus=0"]
    assert execution_arguments(SubmitOptions(gpu_count=2, explicit_precision="both", output_precision="full")) == [
        "gpus=2", "double=both", "output_precision=full"]


@pytest.mark.parametrize("change", [{"gpuCount": True}, {"gpuCount": 1.5}, {"gpuCount": "1"},
    {"gpuCount": -1}, {"gpuCount": 1025}, {"explicitPrecision": None}, {"explicitPrecision": []},
    {"explicitPrecision": "both & calc"}, {"outputPrecision": "double"}, {"outputPrecision": False}])
def test_local_and_remote_reject_malformed_options_before_launch(tmp_path, change):
    from modules.control_plane.contracts import ApiProblem
    with pytest.raises(ApiProblem) as local:
        LocalJobDraftPreviewRequest.from_payload({"schemaVersion": 1, **change})
    assert local.value.code == "INVALID_EXECUTION_OPTIONS"
    with pytest.raises(ApiProblem) as remote:
        RemoteJobRequest.from_payload({**request_for(tmp_path / "case.inp"), **change})
    assert remote.value.code == "INVALID_EXECUTION_OPTIONS"


def test_local_preview_queue_cold_restart_edit_and_reset(tmp_path):
    source = tmp_path / "case.inp"
    source.write_text("*Heading\n", encoding="ascii")
    path = tmp_path / "queue.json"
    options = {"joblist_path": path}
    draft = {"schemaVersion": 1, "inpFile": str(source), "jobName": "case", "cpus": 1,
             "gpuCount": 2, "explicitPrecision": "both", "outputPrecision": "full"}
    with running_control_plane(tmp_path, **options) as runtime:
        preview = api_request(runtime, "/api/v1/local-job-draft-previews", method="POST", payload=draft)
        assert preview[0] == 200 and json_response(preview)["valid"]
        assert "gpus=2 double=both output_precision=full" in json_response(preview)["command"]
        response = post_command(runtime, command("enqueueDraft", draft=draft))
        assert response[0] == 200
        identifier = json_response(response)["stats"]["itemId"]
    assert load_joblist_state(path)[1][0].gpu_count == 2
    with running_control_plane(tmp_path, **options) as runtime:
        # An older client updating another field must preserve all three overrides.
        result = post_command(runtime, command("updateQueueItem", itemId=identifier, memory="2GB"))
        assert result[0] == 200
        item = json_response(result)["snapshot"]["queueItems"][0]
        assert (item["gpuCount"], item["explicitPrecision"], item["outputPrecision"]) == (2, "both", "full")
        result = post_command(runtime, command("updateQueueItem", itemId=identifier,
            gpuCount=None, explicitPrecision="default", outputPrecision="default"))
        assert result[0] == 200
    saved = load_joblist_state(path)[1][0]
    assert saved.gpu_count is None and saved.explicit_precision == saved.output_precision == "default"


def test_invalid_persisted_options_fail_before_workspace_or_backup(tmp_path):
    source = tmp_path / "case.inp"
    source.write_text("source", encoding="ascii")
    old_result = tmp_path / "case.odb"
    old_result.write_bytes(b"existing result")
    target = tmp_path / "ssd"
    target.mkdir()
    item = QueueItem(inp_path=str(source), job_name="case", cores=1, gpu_count="1 & calc",
                     calculation_root_dir=str(target))
    with pytest.raises(ValueError, match="GPU"):
        execute_local_job(item, "backup", LocalJobProcessController())
    assert not list(target.iterdir()) and old_result.read_bytes() == b"existing result"


@pytest.mark.parametrize("extension", [".obj", ".o"])
def test_explicit_double_precision_requires_source_instead_of_one_object(tmp_path, extension):
    from modules.control_plane.contracts import ApiProblem
    payload = dict(request_for(tmp_path / "case.inp"), explicitPrecision="both", fortranPath=str(tmp_path / ("user" + extension)))
    with pytest.raises(ApiProblem, match="目标文件"):
        RemoteJobRequest.from_payload(payload)
    with pytest.raises(ValueError, match="目标文件"):
        build_abaqus_command(SubmitOptions(explicit_precision="explicit", for_file=payload["fortranPath"]))


def test_memory_history_distinguishes_overrides_but_preserves_default_key(tmp_path):
    source = tmp_path / "case.inp"
    source.write_text("source", encoding="ascii")
    item = QueueItem(inp_path=str(source), cores=1)
    baseline = memory_profile_key(item)
    assert baseline and memory_profile_key(replace(item)) == baseline
    keys = {baseline, memory_profile_key(replace(item, gpu_count=0)), memory_profile_key(replace(item, gpu_count=1)),
            memory_profile_key(replace(item, explicit_precision="both")), memory_profile_key(replace(item, output_precision="full"))}
    assert len(keys) == 5
    draft = LocalJobDraft(gpu_count=1, explicit_precision="constraint", output_precision="single")
    draft.apply_to_queue_item(item)
    assert (item.gpu_count, item.explicit_precision, item.output_precision) == (1, "constraint", "single")


def test_remote_options_survive_recovery_and_different_options_conflict(tmp_path):
    remote = RecoverableRemote()
    request = dict(request_for(tmp_path / "case.inp"), gpuCount=0, explicitPrecision="explicit", outputPrecision="full")
    options = {"remote_manager": remote, "server_profiles_path": tmp_path / "profiles.json"}
    with running_control_plane(tmp_path, **options) as runtime:
        _connect(runtime)
        identifier = create(runtime, request)
        wait_for(lambda: view(runtime, identifier)["trackingState"] == "tracking")
    with running_control_plane(tmp_path, **options) as runtime:
        snapshot = view(runtime, identifier)
        assert (snapshot["request"]["gpuCount"], snapshot["request"]["explicitPrecision"],
                snapshot["request"]["outputPrecision"]) == (0, "explicit", "full")
        assert create(runtime, request) == identifier
        conflict = api_request(runtime, "/api/v1/remote-jobs", method="POST", payload=dict(request, gpuCount=1))
        assert conflict[0] == 409


@pytest.mark.skipif(sys.platform != "win32", reason="Actual Windows command and PowerShell launch")
@pytest.mark.parametrize("gpu,precision,output", [(0, "off", "single"), (2, "both", "full")])
def test_actual_local_and_remote_launch_receive_identical_options(tmp_path, gpu, precision, output):
    fixture = tmp_path / "fixture command.cmd"
    fixture.write_text('@echo off\necho %*>received.txt\nexit /b 0\n', encoding="ascii")
    inp = tmp_path / "case.inp"
    inp.write_text("*Heading\n", encoding="ascii")
    item = QueueItem(inp_path=str(inp), job_name="case", cores=1, abaqus_command=str(fixture), gpu_count=gpu,
                     explicit_precision=precision, output_precision=output)
    local = _execution_command(item, inp, "")
    completed = subprocess.run(local, shell=True, cwd=tmp_path, timeout=15, check=False,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    assert completed.returncode == 0
    local_args = (tmp_path / "received.txt").read_text().split()
    (tmp_path / "received.txt").unlink()
    config = {"work_directory": str(tmp_path), "job_name": "case", "abaqus_command": str(fixture),
              "input_name": "case.inp", "cpus": 1, "memory": "", "datacheck": False,
              "operation_id": "b" * 32, "execution_arguments": execution_arguments(item)}
    encoded = base64.b64encode(json.dumps(config).encode()).decode()
    script = tmp_path / "launch.ps1"
    script.write_text("$ErrorActionPreference='Stop'\n$config=[Text.Encoding]::UTF8.GetString("
        f"[Convert]::FromBase64String('{encoded}'))|ConvertFrom-Json\n" + _start_job_script(), encoding="utf-8-sig")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(script)], capture_output=True, text=True, timeout=20, check=False,
        creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    deadline = time.monotonic() + 5
    while not (tmp_path / "received.txt").exists() and time.monotonic() < deadline:
        time.sleep(.05)
    remote_args = (tmp_path / "received.txt").read_text().split()
    expected = {f"gpus={gpu}", f"double={precision}", f"output_precision={output}"}
    assert expected <= set(local_args) and expected <= set(remote_args)
    try:
        psutil.Process(receipt["process_id"]).wait(timeout=5)
    except psutil.NoSuchProcess:
        pass
