import subprocess

from tests.control_plane.test_api import running_control_plane
from tests.control_plane.test_remote_job_recovery import RecoverableRemote, wait_for
from tests.control_plane.test_remote_submission_reconcile import connect
from tests.winui_host.test_shutdown_api import close_client


def test_native_client_retrieves_same_remote_request_and_withdraws_only_unaccepted(tmp_path, close_client):
    remote = RecoverableRemote()
    remote.complete = True
    with running_control_plane(tmp_path, remote_manager=remote) as runtime:
        connect(runtime, "127.0.0.1")
        result = subprocess.run(
            ["dotnet", str(close_client), "--remote-submission-api", str(runtime.descriptor_path)],
            capture_output=True, timeout=75, check=False,
        )
        assert result.returncode == 0, (result.stdout, result.stderr)
        wait_for(lambda: remote.starts == 1)
        assert len(runtime.remote_job_manager.list_snapshots()) == 1
