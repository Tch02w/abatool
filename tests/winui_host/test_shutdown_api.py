import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from modules.postprocessor.process_runner import ProcessCancelled
from tests.control_plane.test_api import api_request, running_control_plane
from tests.control_plane.test_local_queue_runtime_api import wait_until
from tests.control_plane.test_postprocessing_api import _scan_payload, _settings
from tests.control_plane.test_remote_transfers_api import FakeRemoteManager, _connect


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
