import json
import subprocess
import time

import pytest

from modules.postprocessor.process_runner import ProcessCancelled
from tests.control_plane.test_api import running_control_plane
from tests.control_plane.test_postprocess_group_queue import publish, run
from tests.control_plane.test_postprocessing_api import _settings
from tests.winui_host.test_shutdown_api import close_client  # noqa: F401


def test_group_queue_native_client_matches_live_http_contract(tmp_path, close_client):
    if tmp_path.drive.casefold() == "c:":
        pytest.skip("请指定非 C 盘 --basetemp")
    source = tmp_path / "sample.odb"
    source.write_bytes(b"group-queue test input")
    started = []
    for prefix, names in (("initial", "AB"), ("append", "C"), ("edited", "B"), ("second", "AB")):
        request = dict(run(source, *names), clientRequestId=prefix)
        if prefix == "edited":
            request["animationFps"] = 37
        (tmp_path / (prefix + ".json")).write_text(json.dumps(request), encoding="utf-8")

    def runner(plan, progress, log, controller):
        name = plan.groups[0].name
        started.append(name)
        if name == "A":
            deadline = time.monotonic() + 20
            while not controller.cancel_requested and time.monotonic() < deadline:
                time.sleep(.02)
            assert controller.cancel_requested
            raise ProcessCancelled("test cancellation")
        assert name == "B" and plan.options.settings["animation_fps"] == 37
        return dict(publish(plan), batchId=plan.batch_id, resultRoots=[str(tmp_path / "AbaqusODBPostProcessor_Results")], groups=[])

    with running_control_plane(tmp_path, postprocess_run_runner=runner, postprocess_settings_provider=_settings) as runtime:
        checked = subprocess.run(["dotnet", str(close_client), "--postprocess-group-queue-api",
                                  str(runtime.descriptor_path), str(tmp_path)],
                                 capture_output=True, encoding="utf-8", errors="replace", timeout=50)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert started == ["A", "B", "A"]
