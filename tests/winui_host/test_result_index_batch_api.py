"""Check the production WinUI batch index client, including recovery and cancellation."""
import subprocess
import threading

from modules.control_plane import result_indexing
from modules.postprocessor.result_index import (
    ResultIndexCancelled,
    build_result_index,
    index_path,
)
from tests.control_plane.test_api import running_control_plane
from tests.winui_host import test_shutdown_api

# Register the shared production-client fixture in this test module.
close_client = test_shutdown_api.close_client


def test_winui_result_index_batch_client(tmp_path, close_client, monkeypatch):
    root = tmp_path / "results"
    for folder in ("Hold/First", "Hold/Second", "Complete/Only"):
        path = root / folder
        path.mkdir(parents=True)
        (path / "load_point_raw.csv").write_text("time,force\n0,1\n", encoding="utf-8")

    entered = threading.Event()

    def build(path, classify, section, cancel_event=None, progress=None, *, only_if_missing):
        assert only_if_missing
        if path.parent.name == "Hold":
            entered.set()
            assert cancel_event.wait(15), "client did not cancel its batch"
            raise ResultIndexCancelled()
        return build_result_index(path, classify, section, cancel_event, progress, only_if_missing=True)

    monkeypatch.setattr(result_indexing, "build_result_index", build)
    with running_control_plane(tmp_path) as runtime:
        process = subprocess.run(
            ["dotnet", str(close_client), "--result-index-batch-api", str(runtime.descriptor_path), str(root)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40, check=False,
        )
        assert process.returncode == 0, (process.stdout, process.stderr)
    assert entered.is_set()
    assert index_path(root / "Complete/Only").is_file()
    assert not any(index_path(folder).exists() for folder in (root / "Hold").iterdir())
