"""Use the production WinUI queue client against a real, isolated local server."""
import subprocess

from modules.submitter.queue_store import load_joblist_state
from tests.control_plane.test_api import running_control_plane
from tests.winui_host.test_shutdown_api import close_client


def test_edit_queue_directories_through_production_client(tmp_path, close_client):
    for name in ("source", "ssd", "archive"):
        (tmp_path / name).mkdir()
    for name in ("A.inp", "B.inp"):
        (tmp_path / "source" / name).write_text("*Heading\n", encoding="ascii")
    queue = tmp_path / "joblist.json"
    with running_control_plane(tmp_path, joblist_path=queue) as runtime:
        result = subprocess.run(
            ["dotnet", str(close_client), "--queue-directories-api", str(runtime.descriptor_path), str(tmp_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45, check=False,
        )
        assert result.returncode == 0, (result.stdout, result.stderr)
    candidates, formal, error = load_joblist_state(queue)
    assert not error and len(candidates) == len(formal) == 1
    assert not candidates[0].cleanup_after_archive and not formal[0].cleanup_after_archive
    assert formal[0].calculation_root_dir == "" and candidates[0].archive_dir == str(tmp_path / "archive")
    assert not candidates[0].attempt_id and not formal[0].attempt_id
