import threading
from pathlib import Path

import pytest

from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_remote_job_recovery import (
    create,
    request_for,
    view,
    wait_for,
)
from tests.control_plane.test_remote_servers_api import (
    FakeRemoteManager,
    command,
    profile_payload,
)
from tests.control_plane.test_remote_transfers_api import _connect


class OutputServers(FakeRemoteManager):
    """Both machines expose the same paths, with distinguishable output bytes."""

    def __init__(self):
        super().__init__()
        self.reads = []

    def list_directory(self, remote_path=""):
        self.reads.append(("list", self.connected_profile.host))
        return super().list_directory(remote_path)

    def download_file(self, remote_path, local_path, **kwargs):
        self.reads.append(("download", self.connected_profile.host))
        Path(local_path).write_text(self.connected_profile.host, encoding="ascii")
        return super().download_file(remote_path, local_path, **kwargs)


def post(runtime, route, payload):
    response = api_request(runtime, "/api/v1/" + route, method="POST", payload=payload)
    return response[0], json_response(response)


def test_recovered_job_browses_and_downloads_only_from_its_original_server(tmp_path):
    remote = OutputServers()
    options = {"remote_manager": remote, "server_profiles_path": tmp_path / "profiles.json"}
    with running_control_plane(tmp_path, **options) as runtime:
        _connect(runtime)
        original_host = remote.connected_profile.host
        job = create(runtime, request_for(tmp_path / "case.inp"))
        wait_for(lambda: view(runtime, job)["status"] == "succeeded")
    with running_control_plane(tmp_path, **options) as runtime:
        alternate = {**profile_payload(), "host": "10.0.0.99", "hostFingerprint": "SHA256:test-server"}
        assert post(runtime, "remote-server-commands", command("connect", profile=alternate))[0] == 200
        recovered = view(runtime, job)
        listing = {"schemaVersion": 1, "sourceOperationId": job, "path": recovered["workDirectory"]}
        target = tmp_path / "saved.sta"
        target.write_text("previous", encoding="ascii")
        transfer = {"schemaVersion": 1, "clientRequestId": "wrong-server", "sourceOperationId": job,
                    "direction": "download", "source": recovered["files"]["sta"], "destination": str(target),
                    "overwrite": True}

        def download(request):
            status, data = post(runtime, "remote-transfers", request)
            assert status == 202, data
            def terminal():
                state = json_response(api_request(runtime, "/api/v1/remote-transfers/" + data["operationId"]))
                return state if state["status"] in {"succeeded", "failed", "cancelled"} else None
            return wait_for(terminal)

        code, problem = post(runtime, "remote-file-listings", listing)
        assert (code, problem["error"]["code"]) == (409, "REMOTE_CONNECTION_CHANGED")
        failure = download(transfer)
        assert failure["status"] == "failed" and failure["request"]["sourceOperationId"] == job
        assert f"原服务器 {original_host}:22" in failure["error"]["message"] and failure["result"] is None
        assert not remote.reads and target.read_bytes() == b"previous"
        _connect(runtime)
        assert post(runtime, "remote-file-listings", listing)[0] == 200
        retry = {**transfer, "clientRequestId": "right-server"}
        success = download(retry)
        assert success["status"] == "succeeded" and target.read_bytes() == original_host.encode("ascii")
        assert download(retry)["operationId"] == success["operationId"]
        assert remote.reads == [("list", original_host), ("download", original_host)]
        assert post(runtime, "remote-transfers", {k: v for k, v in retry.items() if k != "sourceOperationId"})[0] == 409
        bad_path = {**retry, "source": recovered["workDirectory"] + r"\unrecorded.sta"}
        assert post(runtime, "remote-transfers", bad_path)[1]["error"]["code"] == "REMOTE_JOB_OUTPUT_UNKNOWN"
        assert post(runtime, "remote-transfers", {**retry, "direction": "upload"})[0] == 400
        assert post(runtime, "remote-file-listings", {**listing, "sourceOperationId": "f" * 32})[0] == 404
        assert len(remote.reads) == 2


@pytest.mark.parametrize("invalid", [None, "", 3, "not-a-job-id"])
def test_invalid_job_binding_never_falls_back_to_general_browser(tmp_path, invalid):
    with running_control_plane(tmp_path, remote_manager=OutputServers()) as runtime:
        body = {"schemaVersion": 1, "sourceOperationId": invalid}
        assert post(runtime, "remote-file-listings", body)[1]["error"]["code"] == "INVALID_SOURCE_OPERATION_ID"
        body.update(clientRequestId="bad", direction="download", source="remote", destination="local", overwrite=False)
        assert post(runtime, "remote-transfers", body)[1]["error"]["code"] == "INVALID_SOURCE_OPERATION_ID"


def test_queued_download_rechecks_identity_when_it_reaches_the_transport(tmp_path, monkeypatch):
    remote = OutputServers()
    with running_control_plane(tmp_path, remote_manager=remote, server_profiles_path=tmp_path / "profiles.json") as runtime:
        _connect(runtime)
        job = create(runtime, request_for(tmp_path / "case.inp"))
        wait_for(lambda: view(runtime, job)["status"] == "succeeded")
        service = runtime.httpd.context.remote_server_service
        transfer = service.transfer_file
        ready, release = threading.Event(), threading.Event()

        def delayed(**kwargs):
            ready.set()
            assert release.wait(10)
            return transfer(**kwargs)

        monkeypatch.setattr(service, "transfer_file", delayed)
        target = tmp_path / "queued.sta"
        try:
            code, data = post(runtime, "remote-transfers", {
                "schemaVersion": 1, "clientRequestId": "queued", "sourceOperationId": job, "direction": "download",
                "source": view(runtime, job)["files"]["sta"], "destination": str(target), "overwrite": False,
            })
            assert code == 202 and ready.wait(5)
            # Swap the verified transport after acceptance but before any file I/O.
            alternate = {**profile_payload(), "host": "10.0.0.99", "hostFingerprint": "SHA256:test-server"}
            service.execute(command("connect", profile=alternate))
        finally:
            release.set()
        wait_for(lambda: json_response(api_request(runtime, "/api/v1/remote-transfers/" + data["operationId"]))["status"] == "failed")
        assert not target.exists() and not remote.reads
