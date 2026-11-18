import json
import subprocess
from pathlib import Path


def test_production_export_preserves_sources_and_reports_partial_results(tmp_path):
    project = Path(__file__).with_name("ResultBrowser.Tests.csproj")
    evidence = tmp_path / "export"
    result = subprocess.run(
        ["dotnet", "run", "--project", str(project), "--artifacts-path", str(tmp_path / "build"),
         "--", "--export-checks", str(evidence)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "24 result export checks passed" in result.stdout
    report = json.loads((evidence / "verification.json").read_text(encoding="utf-8"))
    assert report["status"] == "verified" and report["sourceUnchanged"]
    assert report["cancelledInsideFile"] and report["completedFilesRetained"]
