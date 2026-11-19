import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from modules.postprocessor.process_runner import ProcessCancelled
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_local_queue_runtime_api import wait_until
from tests.control_plane.test_postprocessing_api import _scan_payload, _settings
from tests.control_plane.test_remote_transfers_api import FakeRemoteManager, _connect


def test_remote_observation_separates_readiness_timeout_and_cancellation(close_client):
    result = subprocess.run(
        ["dotnet", str(close_client), "--remote-observation-checks"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=65, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "6 remote observation checks passed" in result.stdout


def test_cancelling_native_observation_keeps_original_transfer_running(tmp_path, close_client):
    started, release = threading.Event(), threading.Event()

    class Remote(FakeRemoteManager):
        def upload_file(self, *args, **kwargs):
            started.set()
            assert release.wait(30)
            assert not kwargs["cancel_requested"]()
            return super().upload_file(*args, **kwargs)

    with running_control_plane(tmp_path, remote_manager=Remote(), server_profiles_path=tmp_path / "profiles.json") as runtime:
        try:
            _connect(runtime)
            payload = {"schemaVersion": 1, "clientRequestId": "observe-once", "direction": "upload",
                       "source": str(tmp_path / "case.inp"), "destination": r"D:\Abaqus_Cal\case.inp", "overwrite": False}
            response = api_request(runtime, "/api/v1/remote-transfers", method="POST", payload=payload)
            assert response[0] == 202
            operation_id = json_response(response)["operationId"]
            assert started.wait(5)
            result = subprocess.run(
                ["dotnet", str(close_client), "--remote-observation-api", str(runtime.descriptor_path), operation_id],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20, check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            listing = json_response(api_request(runtime, "/api/v1/remote-transfers"))["operations"]
            assert len(listing) == 1 and listing[0]["operationId"] == operation_id and listing[0]["status"] == "running"
        finally:
            release.set()
        wait_until(lambda: json_response(api_request(runtime, "/api/v1/remote-transfers/" + operation_id))["status"] == "succeeded")


def test_workbench_profile_isolates_paths_and_instance_identity(tmp_path, close_client):
    result = subprocess.run(
        ["dotnet", str(close_client), "--profile-checks", str(tmp_path / "profiles")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "14 profile isolation checks passed" in result.stdout


def test_job_postprocess_route_respects_attempt_archive_and_missing_results(tmp_path, close_client):
    result = subprocess.run(
        ["dotnet", str(close_client), "--job-route-checks", str(tmp_path / "routes")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "30 job postprocess route checks passed" in result.stdout


@pytest.mark.parametrize("archive_status", ["", "已归档", "已归档，清理未完成", "归档失败"])
def test_production_job_route_and_discovery_use_published_result_location(tmp_path, close_client, archive_status):
    from modules.submitter.models import QueueItem
    from modules.submitter.queue_store import save_joblist_state

    source, work, archive = (tmp_path / name for name in ("输入目录", "计算 目录", "归档 目录"))
    for directory in (source, work, archive):
        directory.mkdir()
        (directory / "实际运行名.odb").write_bytes(directory.name.encode("utf-8"))
    inp = source / "不同输入名.inp"
    inp.write_text("*Heading\n", encoding="utf-8")
    item = QueueItem(inp_path=str(inp), source_inp_path=str(inp), job_name="实际运行名",
                     status="已完成", effective_work_dir=str(work), archive_destination=str(archive),
                     archive_status=archive_status, attempt_id="completed-attempt", cores=1)
    joblist = tmp_path / "joblist.json"
    save_joblist_state([], [item], joblist)
    before = {file: file.read_bytes() for file in tmp_path.rglob("*.odb")}
    expected = archive if archive_status in {"已归档", "已归档，清理未完成"} else work
    with running_control_plane(tmp_path, joblist_path=joblist) as runtime:
        result = subprocess.run(
            ["dotnet", str(close_client), "--job-route-api", str(runtime.descriptor_path), str(expected / "实际运行名.odb")],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "2 production-client/live-HTTP job route checks passed" in result.stdout
    assert {file: file.read_bytes() for file in tmp_path.rglob("*.odb")} == before


@pytest.fixture(scope="module")
def close_client(tmp_path_factory):
    if shutil.which("dotnet") is None:
        pytest.skip("Requires .NET 10")
    output = tmp_path_factory.mktemp("close-client")
    built = subprocess.run(["dotnet", "build", str(Path(__file__).with_name("ControlPlaneHost.Tests.csproj")),
                            "--no-restore", "-o", str(output), "-v:q"], capture_output=True, timeout=120, check=False)
    assert built.returncode == 0, built.stdout + built.stderr
    return output / "ControlPlaneHost.Tests.dll"


@pytest.mark.parametrize("mode", ["background", "abort", "stop", "idle"])
def test_production_close_client_against_live_http_backend(tmp_path, close_client, mode):
    started, release = threading.Event(), threading.Event()
    controllers = []
    source = tmp_path / "model.odb"
    source.write_bytes(b"fixture")

    def scanner(request, progress, log, controller):
        controllers.append(controller)
        started.set()
        while not release.wait(.03):
            if controller.cancel_requested:
                raise ProcessCancelled("closed by explicit stop")
        return {"items": [], "count": 0}

    with running_control_plane(tmp_path, postprocess_scan_runner=scanner, postprocess_settings_provider=_settings) as runtime:
        try:
            if mode != "idle":
                assert api_request(runtime, "/api/v1/odb-postprocess-scans", method="POST",
                                   payload=_scan_payload(tmp_path, source))[0] == 202
                assert started.wait(5)
            completed = subprocess.run(["dotnet", str(close_client), "--close-api", str(runtime.descriptor_path), mode],
                                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40, check=False)
            assert completed.returncode == 0, completed.stdout + completed.stderr
            if mode in {"background", "abort"}:
                assert not controllers[0].cancel_requested
                assert api_request(runtime, "/healthz")[0] == 200
                assert api_request(runtime, "/api/v1/result-scopes", method="POST", payload={})[0] == 400
            else:
                wait_until(lambda: not runtime.descriptor_path.exists())
                assert runtime._closed
                if mode == "stop":
                    assert controllers[0].cancel_requested
        finally:
            release.set()


def test_production_graph_draft_never_commits_or_overwrites_a_newer_revision(tmp_path, close_client):
    with running_control_plane(tmp_path) as runtime:
        completed = subprocess.run(
            ["dotnet", str(close_client), "--graph-draft-api", str(runtime.descriptor_path), str(tmp_path / "draft")],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40, check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "4 production-client/live-HTTP graph draft checks passed" in completed.stdout
        assert api_request(runtime, "/healthz")[0] == 200


def test_new_job_reset_confirms_and_persists_before_replacing_inputs(tmp_path, close_client):
    result = subprocess.run(
        ["dotnet", str(close_client), "--new-job-reset-checks", str(tmp_path / "reset")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "16 new-job reset checks passed" in result.stdout


def test_shared_command_state_rejects_stale_busy_and_mismatched_targets(close_client):
    result = subprocess.run(
        ["dotnet", str(close_client), "--command-state-checks"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "26 shared command-state checks passed" in result.stdout


def test_command_state_observation_never_refreshes_or_disconnects_remote(tmp_path, close_client):
    manager = FakeRemoteManager()
    with running_control_plane(tmp_path, remote_manager=manager, server_profiles_path=tmp_path / "profiles.json") as runtime:
        _connect(runtime)
        before = (manager.connected_name, manager.refresh_count, len(manager.requests))
        result = subprocess.run(
            ["dotnet", str(close_client), "--command-state-api", str(runtime.descriptor_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "4 production-client/live-HTTP command-state checks passed" in result.stdout
        assert (manager.connected_name, manager.refresh_count, len(manager.requests)) == before


def test_command_target_is_checked_by_backend_before_refresh_or_disconnect(tmp_path, close_client):
    manager = FakeRemoteManager()
    with running_control_plane(tmp_path, remote_manager=manager, server_profiles_path=tmp_path / "profiles.json") as runtime:
        _connect(runtime)
        result = subprocess.run(
            ["dotnet", str(close_client), "--command-target-api", str(runtime.descriptor_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "5 production-client/live-HTTP target identity checks passed" in result.stdout
        assert manager.refresh_count == 1
        assert not manager.connected_name


def test_production_client_lists_and_preserves_active_transfer(tmp_path, close_client):
    started, release = threading.Event(), threading.Event()

    class Remote(FakeRemoteManager):
        def upload_file(self, *args, **kwargs):
            started.set()
            assert release.wait(30)
            assert not kwargs["cancel_requested"]()
            return super().upload_file(*args, **kwargs)

    with running_control_plane(tmp_path, remote_manager=Remote(), server_profiles_path=tmp_path / "profiles.json") as runtime:
        try:
            _connect(runtime)
            payload = {"schemaVersion": 1, "clientRequestId": "background-transfer", "direction": "upload",
                       "source": str(tmp_path / "case.inp"), "destination": r"D:\Abaqus_Cal\case.inp", "overwrite": False}
            assert api_request(runtime, "/api/v1/remote-transfers", method="POST", payload=payload)[0] == 202
            assert started.wait(5)
            result = subprocess.run(["dotnet", str(close_client), "--close-api", str(runtime.descriptor_path), "background"],
                                    capture_output=True, timeout=20, check=False)
            assert result.returncode == 0, result.stdout + result.stderr
            assert api_request(runtime, "/api/v1/remote-transfers?activeOnly=true")[0] == 200
        finally:
            release.set()
