import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_remote_job_recovery import (
    RecoverableRemote,
    create,
    request_for,
    wait_for,
)
from tests.control_plane.test_remote_servers_api import command, profile_payload


def connect(runtime, host):
    profile = {
        **profile_payload(),
        "host": host,
        "hostFingerprint": "SHA256:test-server",
    }
    result = api_request(
        runtime,
        "/api/v1/remote-server-commands",
        method="POST",
        payload=command(
            "connect", profile=profile, credentials={"password": "fixture"}
        ),
    )
    assert result[0] == 200
    return json_response(result)["connection"]["profile"]


def find(runtime, request):
    return api_request(
        runtime, "/api/v1/remote-job-lookups", method="POST", payload=request
    )


def withdraw(runtime, request):
    return api_request(
        runtime, "/api/v1/remote-job-withdrawals", method="POST", payload=request
    )


def test_late_remote_submission_after_withdrawal_never_dispatches(
    tmp_path, monkeypatch
):
    remote = RecoverableRemote()
    with running_control_plane(tmp_path, remote_manager=remote) as runtime:
        request = request_for(tmp_path / "job.inp") | {
            "expectedProfile": connect(runtime, "127.0.0.1")
        }
        manager = runtime.remote_server_service
        connected = manager.connected_profile
        entered, released = threading.Event(), threading.Event()

        def delayed(*args):
            profile = connected(*args)
            entered.set()
            assert released.wait(10)
            return profile

        monkeypatch.setattr(manager, "connected_profile", delayed)
        with ThreadPoolExecutor(max_workers=1) as pool:
            late = pool.submit(create, runtime, request)
            try:
                assert entered.wait(5)
                assert find(runtime, request)[0] == 404
                answer = withdraw(runtime, request)
                assert answer[0] == 200
                operation = json_response(answer)
                assert operation["trackingState"] == "withdrawn"
            finally:
                released.set()
            assert late.result() == operation["operationId"]
    with running_control_plane(tmp_path, remote_manager=remote) as runtime:
        assert (
            json_response(find(runtime, request))["operationId"]
            == operation["operationId"]
        )
        assert create(runtime, request) == operation["operationId"]
        assert (
            json_response(api_request(runtime, "/api/v1/remote-jobs"))["operations"]
            == []
        )
        assert not remote.starts
        assert json_response(api_request(runtime, "/api/v1/job-notifications"))["unreadCount"] == 0


def test_reconcile_accepted_and_missing_requests_after_switch(tmp_path):
    remote = RecoverableRemote()
    remote.complete = True
    with running_control_plane(tmp_path, remote_manager=remote) as runtime:
        profile = connect(runtime, "127.0.0.1")
        request = request_for(tmp_path / "job.inp") | {"expectedProfile": profile}
        original = create(runtime, request)
        wait_for(lambda: json_response(find(runtime, request))["status"] == "succeeded", seconds=40)
        other = connect(runtime, "127.0.0.2")
        assert json_response(withdraw(runtime, request))["status"] == "succeeded"
        assert create(runtime, request) == original
        conflict = withdraw(runtime, request | {"expectedProfile": other})
        assert json_response(conflict)["error"]["code"] == "IDEMPOTENCY_CONFLICT"
        assert find(runtime, request | {"expectedProfile": other})[0] == 409
        assert find(runtime, request | {"cpus": 4})[0] == 409
        refused = api_request(
            runtime,
            "/api/v1/remote-jobs",
            method="POST",
            payload=request | {"clientRequestId": "not-delivered"},
        )
        assert refused[0] == 409 and remote.starts == 1


def test_failed_withdrawal_write_cannot_acknowledge_or_dispatch(tmp_path, monkeypatch):
    remote = RecoverableRemote()
    with running_control_plane(tmp_path, remote_manager=remote) as runtime:
        request = request_for(tmp_path / "job.inp") | {
            "expectedProfile": connect(runtime, "127.0.0.1")
        }

        def refuse(_record):
            raise sqlite3.OperationalError("test disk error")

        with monkeypatch.context() as patch:
            patch.setattr(runtime.remote_job_manager._journal, "save", refuse)
            assert withdraw(runtime, request)[0] == 503
            assert find(runtime, request)[0] == 503
            assert (
                api_request(
                    runtime, "/api/v1/remote-jobs", method="POST", payload=request
                )[0]
                == 503
            )
        assert json_response(withdraw(runtime, request))["trackingState"] == "withdrawn"
    with running_control_plane(tmp_path, remote_manager=remote) as runtime:
        assert json_response(find(runtime, request))["trackingState"] == "withdrawn"
        assert remote.starts == 0
