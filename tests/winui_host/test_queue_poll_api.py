"""Native automatic polling can defer; explicit reads wait for the committed queue."""

import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from modules.submitter.constants import STATUS_FAILED
from modules.submitter.queue_store import save_joblist_state
from tests.control_plane.test_api import api_request, running_control_plane
from tests.control_plane.test_remote_job_recovery import RecoverableRemote, request_for
from tests.control_plane.test_remote_submission_reconcile import connect
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


def test_overview_poll_reads_local_while_remote_journal_is_saving(tmp_path, monkeypatch, queue_client):
    row = job(tmp_path, "Example")
    queue = tmp_path / "joblist.json"
    save_joblist_state([], [row], queue)
    remote = RecoverableRemote()
    with running_control_plane(tmp_path, joblist_path=queue, remote_manager=remote) as runtime, ThreadPoolExecutor(max_workers=2) as pool:
        request = request_for(tmp_path / "withdrawn.inp") | {"expectedProfile": connect(runtime, "127.0.0.1")}
        saving, release, strict_read = threading.Event(), threading.Event(), threading.Event()
        manager = runtime.remote_job_manager
        save = manager._journal.save
        snapshot = manager.list_snapshots

        def hold_write(record):
            saving.set()
            assert release.wait(30)
            return save(record)

        def observe_request(*, active_only=False, wait=True):
            if wait:
                strict_read.set()
            return snapshot(active_only=active_only, wait=wait)

        monkeypatch.setattr(manager._journal, "save", hold_write)
        monkeypatch.setattr(manager, "list_snapshots", observe_request)
        writer = pool.submit(api_request, runtime, "/api/v1/remote-job-withdrawals",
                             method="POST", payload=request, timeout=35)
        try:
            assert saving.wait(5)
            client = pool.submit(subprocess.run,
                ["dotnet", str(queue_client), "--remote-poll-api", str(runtime.descriptor_path), row.job_name],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20, check=False)
            assert strict_read.wait(15), "Automatic reads must reach the explicit read while the write is held"
            assert not client.done()
        finally:
            release.set()
        assert writer.result()[0] == 200 and remote.starts == 0
        result = client.result()
        assert result.returncode == 0, (result.stdout, result.stderr)
