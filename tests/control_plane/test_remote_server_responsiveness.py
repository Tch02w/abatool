"""Slow remote I/O must not hold the read-only connection view hostage."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from modules.control_plane.events import EventStore
from modules.control_plane.remote_servers import RemoteServerService
from modules.submitter.remote_connection import RemoteConnectionError
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_remote_servers_api import (
    FakeRemoteManager,
    command,
    profile_payload,
)


class WaitingRemote(FakeRemoteManager):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block = "refresh"
        self.fail = False

    def wait(self, action):
        if self.block == action:
            self.entered.set()
            assert self.release.wait(10), "Fixture I/O was not released"
            if self.fail:
                raise RemoteConnectionError("isolated network failure")

    def connect(self, request):
        self.wait("connect")
        return super().connect(request)

    def refresh(self):
        self.wait("refresh")
        return super().refresh()

    def execute_powershell(self, script, *, timeout=30):
        self.wait("probe")
        return "{}"

    def list_directory(self, remote_path=""):
        self.wait("browse")
        return {"path": remote_path, "entries": []}

    def upload_file(self, *args, **kwargs):
        self.wait("upload")
        return {"copied": True}


def connect_payload():
    profile = profile_payload()
    profile["hostFingerprint"] = "SHA256:test-server"
    return command("connect", profile=profile)


@pytest.mark.parametrize("fail", [False, True])
def test_http_snapshot_returns_previous_complete_sample_during_remote_refresh(tmp_path, fail):
    manager = WaitingRemote()
    manager.fail = fail
    with running_control_plane(tmp_path, remote_manager=manager,
                               server_profiles_path=tmp_path / "profiles.json") as runtime:
        assert api_request(runtime, "/api/v1/remote-server-commands", method="POST",
                           payload=connect_payload())[0] == 200
        before = json_response(api_request(runtime, "/api/v1/remote-servers"))
        with ThreadPoolExecutor(max_workers=2) as pool:
            refreshing = pool.submit(api_request, runtime, "/api/v1/remote-server-commands",
                                     method="POST", payload=command("refresh"))
            try:
                assert manager.entered.wait(3)
                reading = pool.submit(api_request, runtime, "/api/v1/remote-servers")
                response = reading.result(timeout=2)
                snapshot = json_response(response)
                assert response[0] == 200 and not refreshing.done()
                assert snapshot["connection"]["busy"] is True
                assert snapshot["connection"]["activity"] == "正在刷新远端资源"
                assert snapshot["connection"]["resource"] == before["connection"]["resource"]
                assert snapshot["profiles"] == before["profiles"]
            finally:
                manager.release.set()
            assert refreshing.result(timeout=3)[0] == (502 if fail else 200)
        after = json_response(api_request(runtime, "/api/v1/remote-servers"))["connection"]
        assert after["busy"] is False and after["activity"] == ""
        assert after["status"] == ("error" if fail else "connected")
        if fail:
            assert after["lastError"] == "isolated network failure"


def test_connection_view_is_detached_from_transport_and_other_readers(tmp_path):
    service = RemoteServerService(EventStore(), tmp_path / "profiles.json", FakeRemoteManager())
    try:
        service.execute(connect_payload())
        original = service.snapshot()
        changed = service.snapshot()
        changed["connection"]["resource"]["cpu_total"] = -1
        changed["profiles"].clear()
        assert service.snapshot() == original
    finally:
        service.close()


def test_connecting_snapshot_does_not_show_previous_servers_resources(tmp_path):
    manager = WaitingRemote()
    service = RemoteServerService(EventStore(), tmp_path / "profiles.json", manager)
    service.execute(connect_payload())
    manager.block = "connect"
    with ThreadPoolExecutor(max_workers=2) as pool:
        connecting = pool.submit(service.execute, connect_payload())
        try:
            assert manager.entered.wait(3)
            connection = pool.submit(service.snapshot).result(timeout=2)["connection"]
            assert connection["status"] == "connecting" and connection["busy"]
            assert connection["resource"] is None
        finally:
            manager.release.set()
            connecting.result(timeout=3)
            service.close()


def test_snapshot_stays_responsive_without_releasing_server_identity_lock(tmp_path):
    manager = WaitingRemote()
    service = RemoteServerService(EventStore(), tmp_path / "profiles.json", manager)
    service.execute(connect_payload())
    manager.block = "probe"
    with ThreadPoolExecutor(max_workers=3) as pool:
        probing = pool.submit(service.execute_powershell, "fixture probe")
        try:
            assert manager.entered.wait(3)
            # Disconnect remains serialized behind the in-flight command.
            disconnecting = pool.submit(service.execute, command("disconnect"))
            snapshot = pool.submit(service.snapshot).result(timeout=2)
            assert snapshot["connection"]["busy"] and not probing.done()
            assert not disconnecting.done() and manager.connected_profile is not None
        finally:
            manager.release.set()
            probing.result(timeout=3)
            service.close()
        assert disconnecting.result(timeout=3)["connection"]["status"] == "disconnected"


@pytest.mark.parametrize("action", ["browse", "upload"])
def test_snapshot_remains_available_during_file_operations(tmp_path, action):
    manager = WaitingRemote()
    service = RemoteServerService(EventStore(), tmp_path / "profiles.json", manager)
    service.execute(connect_payload())
    manager.block = action
    with ThreadPoolExecutor(max_workers=2) as pool:
        operation = (
            pool.submit(service.browse, {"schemaVersion": 1, "path": "fixture"}) if action == "browse"
            else pool.submit(service.transfer_file, direction="upload", source="fixture", destination="fixture",
                             overwrite=False, progress=lambda *_: None, cancel_requested=lambda: False)
        )
        try:
            assert manager.entered.wait(3)
            snapshot = pool.submit(service.snapshot).result(timeout=2)
            assert snapshot["connection"]["busy"] and not operation.done()
            assert snapshot["connection"]["resource"]["cpu_total"] == 32
        finally:
            manager.release.set()
            operation.result(timeout=3)
            service.close()
