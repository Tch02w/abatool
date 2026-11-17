from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from tests.abaqus import verify_region_fixture


def test_incomplete_fixture_stops_before_any_extraction_even_when_exit_zero(tmp_path, monkeypatch):
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"incomplete ODB")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(verify_region_fixture.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["verify", "--abaqus", "fake.bat", "--output-parent", str(tmp_path)])
    with pytest.raises(RuntimeError, match="Fixture creation did not finish"):
        verify_region_fixture.main()
    assert len(commands) == 1
