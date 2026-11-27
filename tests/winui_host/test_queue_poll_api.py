"""Native automatic polling can defer; explicit reads wait for the committed queue."""

import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from modules.submitter.constants import STATUS_FAILED
from modules.submitter.queue_store import save_joblist_state
from tests.control_plane.test_api import running_control_plane
from tests.control_plane.test_restart_dependency_edits import job
from tests.winui_host import test_shutdown_api

queue_client = test_shutdown_api.close_client


@pytest.mark.parametrize("owner", ["job_queue_service", "local_queue_runtime"])
def test_native_poll_defers_on_either_lock_then_reads_committed_failure(tmp_path, monkeypatch, queue_client, owner):
    row = job(tmp_path, "Example")
    queue = tmp_path / "joblist.json"
    save_joblist_state([], [row], queue)
    row.status = STATUS_FAILED
    row.message = "Workspace refused"
    with running_control_plane(tmp_path, joblist_path=queue) as runtime, ThreadPoolExecutor(max_workers=1) as pool:
        strict_read = threading.Event()
        snapshot = runtime.local_queue_runtime.snapshot

        def observe_request(*, wait=True):
            if wait:
                strict_read.set()
            return snapshot(wait=wait)

        monkeypatch.setattr(runtime.local_queue_runtime, "snapshot", observe_request)
        with getattr(runtime, owner)._lock:
            client = pool.submit(subprocess.run,
                ["dotnet", str(queue_client), "--queue-poll-api", str(runtime.descriptor_path), row.message],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20, check=False)
            assert strict_read.wait(8), "Client must reach its strict request while the writer still holds the lock"
            assert not client.done()
            save_joblist_state([], [row], queue)
        result = client.result()
        assert result.returncode == 0, (result.stdout, result.stderr)
