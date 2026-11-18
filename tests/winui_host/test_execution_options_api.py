"""Exercise the production C# submission client against a real local HTTP backend."""
import subprocess

import pytest

from modules.submitter.queue_store import load_joblist_state
from tests.control_plane.test_api import running_control_plane
from tests.winui_host.test_shutdown_api import close_client as build_client_fixture


@pytest.fixture(scope="module")
def execution_client(tmp_path_factory):
    return build_client_fixture.__wrapped__(tmp_path_factory)


@pytest.mark.parametrize("unsupported", [False, True])
def test_production_execution_options_client_preview_save_preserve_and_reset(tmp_path, execution_client, monkeypatch, unsupported):
    from modules.control_plane.server import ControlPlaneRequestHandler
    original = ControlPlaneRequestHandler._send_json
    posts = []
    def send(handler, status, payload, *args, **kwargs):
        if handler.path == "/healthz" and unsupported:
            payload = dict(payload, capabilities=[item for item in payload["capabilities"] if item != "job.execution-options-v1"])
        if handler.command == "POST":
            posts.append(handler.path)
        return original(handler, status, payload, *args, **kwargs)
    monkeypatch.setattr(ControlPlaneRequestHandler, "_send_json", send)
    source = tmp_path / "client_case.inp"
    source.write_text("*Heading\nNo solver fixture\n", encoding="ascii")
    queue = tmp_path / "joblist.json"
    with running_control_plane(tmp_path, joblist_path=queue) as runtime:
        completed = subprocess.run(["dotnet", str(execution_client), "--execution-options-api",
            str(runtime.descriptor_path), str(source), *(["unsupported"] if unsupported else [])], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30, check=False)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        if unsupported:
            assert not posts and not load_joblist_state(queue)[1]
            return
        item = load_joblist_state(queue)[1][0]
        assert item.gpu_count is None and item.explicit_precision == item.output_precision == "default"
        assert item.attempt_id == "", "The fixture must not start a solver"
