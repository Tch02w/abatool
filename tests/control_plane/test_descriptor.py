from __future__ import annotations

import json
from pathlib import Path

from modules.control_plane.contracts import ControlPlaneDescriptor
from modules.control_plane.descriptor import (
    remove_descriptor_if_owned,
    write_descriptor_atomic,
)
from modules.control_plane.server import ControlPlaneRuntime


def descriptor(instance_id: str, port: int) -> ControlPlaneDescriptor:
    return ControlPlaneDescriptor(
        instance_id=instance_id,
        pid=1234,
        host="127.0.0.1",
        port=port,
        base_url=f"http://127.0.0.1:{port}",
        token="测试-token",
        started_at="2026-08-20T12:00:00.000Z",
        launch_token="launch-nonce",
    )


def test_descriptor_is_atomically_replaced_without_partial_files(
    tmp_path: Path,
) -> None:
    path = tmp_path / "中文 runtime" / "control-plane.json"

    write_descriptor_atomic(path, descriptor("first", 5001))
    write_descriptor_atomic(path, descriptor("second", 5002))

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "schemaVersion": 1,
        "apiVersion": "v1",
        "instanceId": "second",
        "pid": 1234,
        "host": "127.0.0.1",
        "port": 5002,
        "baseUrl": "http://127.0.0.1:5002",
        "token": "测试-token",
        "startedAt": "2026-08-20T12:00:00.000Z",
        "launchToken": "launch-nonce",
    }
    assert list(path.parent.glob(".control-plane.json.*.tmp")) == []


def test_descriptor_cleanup_requires_matching_instance(tmp_path: Path) -> None:
    path = tmp_path / "control-plane.json"
    write_descriptor_atomic(path, descriptor("owner", 5001))

    assert not remove_descriptor_if_owned(path, "another-instance")
    assert path.exists()
    assert remove_descriptor_if_owned(path, "owner")
    assert not path.exists()


def test_runtime_publishes_the_cold_start_launch_token(tmp_path: Path) -> None:
    path = tmp_path / "runtime.json"
    runtime = ControlPlaneRuntime(
        descriptor_path=path,
        launch_token="cold-start-nonce",
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["launchToken"] == "cold-start-nonce"
    finally:
        runtime.close()
