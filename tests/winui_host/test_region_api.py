import json
from pathlib import Path
import shutil
import subprocess

import pytest

from tests.control_plane.test_api import running_control_plane


@pytest.mark.skipif(shutil.which("dotnet") is None, reason="Requires .NET 10 SDK")
def test_production_native_region_client_over_http(tmp_path, monkeypatch):
    from modules.control_plane import postprocessing
    source = tmp_path / "测试 model.odb"
    source.write_bytes(b"unchanged")
    calls = []
    def runner(request, progress, log, controller):
        calls.append(request)
        payload = json.loads(request.extraction_json)
        if payload["method"] == "solid_section":
            assert payload["region"]["name"] == "混凝土"
            assert payload["section"]["normal"] == [0, 0, 1]
            assert payload["section"]["offsets"] == [10, 20]
            assert payload["section"]["momentPoint"] == [1, 2, 3]
        else:
            assert payload["region"]["instance"] == "钢筋-1"
        assert payload["referenceAreaOverride"] is None
        assert payload["frames"] == [{"index": 1, "step": "Load"}]
        return dict(outputCount=1, outputs=[str(tmp_path / "result")])
    monkeypatch.setattr(postprocessing, "execute_region_extraction", runner)
    monkeypatch.setattr(postprocessing, "finalize_region_extraction", lambda *args: None)
    with running_control_plane(tmp_path / "state") as runtime:
        completed = subprocess.run([
            "dotnet", "run", "--project", str(Path(__file__).with_name("ControlPlaneHost.Tests.csproj")),
            "-c", "Release", "--", "--region-api", str(runtime.descriptor_path), str(tmp_path), str(source),
        ], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "Native HTTP region extraction workflow passed" in completed.stdout
    assert len(calls) == 2
    assert source.read_bytes() == b"unchanged"
