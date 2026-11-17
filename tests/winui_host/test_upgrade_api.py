"""Native production client over real HTTP; no actual ODB upgrade is run."""
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from tests.control_plane.test_api import running_control_plane


@pytest.mark.skipif(shutil.which("dotnet") is None, reason="Requires .NET 10 SDK")
def test_native_upgrade_http_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("ABAQUS_TOOLS_ABAQUS_COMMAND", "abaqus")
    monkeypatch.setenv("ABAQUS_TOOLS_ABAQUS_RELEASE", "2025")
    source = tmp_path / "测试 model.odb"
    source.write_bytes(b"unchanged-test-source")
    calls = []

    def runner(preview, *, controller, log, **kwargs):
        calls.append(preview)
        log("ODB_UPGRADE_START|1|1|测试 model.odb")
        deadline = time.monotonic() + 15
        while not controller.stop_requested and time.monotonic() < deadline:
            time.sleep(.01)
        assert controller.stop_requested and not controller.cancel_requested
        entry = preview["entries"][0]
        log("ODB_UPGRADE_DONE|1|1|upgraded|测试 model.odb")
        return {"results": [{"source_path": entry["sourcePath"], "status": "upgraded",
                             "upgraded_path": entry["upgradedPath"], "backup_path": entry["backupPath"]}]}

    with running_control_plane(tmp_path / "state", odb_upgrade_runner=runner) as runtime:
        result = subprocess.run([
            "dotnet", "run", "--project", str(Path(__file__).with_name("ControlPlaneHost.Tests.csproj")),
            "-c", "Release", "--", "--upgrade-api", str(runtime.descriptor_path), str(tmp_path), str(source),
        ], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Native HTTP upgrade workflow passed" in result.stdout
    assert len(calls) == 1
    assert source.read_bytes() == b"unchanged-test-source"
    assert not list(tmp_path.glob("*-old*.odb"))
