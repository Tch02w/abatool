from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from modules.control_plane.__main__ import build_parser
from modules.control_plane.server import ControlPlaneRuntime

TEST_TOKEN = "control-plane-test-token"


@contextmanager
def running_control_plane(
    tmp_path: Path,
    **runtime_options: Any,
) -> Iterator[ControlPlaneRuntime]:
    runtime = ControlPlaneRuntime(
        descriptor_path=tmp_path / "runtime" / "control-plane.json",
        port=0,
        token=TEST_TOKEN,
        **runtime_options,
    )
    thread = threading.Thread(target=runtime.serve_forever, daemon=True)
    thread.start()
    try:
        yield runtime
    finally:
        runtime.shutdown()
        thread.join(timeout=5)
        runtime.close()
        assert not thread.is_alive()


def api_request(
    runtime: ControlPlaneRuntime,
    path: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    token: str | None = TEST_TOKEN,
) -> tuple[int, dict[str, str], bytes]:
    data = None
    headers: dict[str, str] = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = Request(
        f"{runtime.base_url}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, dict(response.headers.items()), response.read()
    except HTTPError as error:
        return error.code, dict(error.headers.items()), error.read()


def json_response(response: tuple[int, dict[str, str], bytes]) -> dict:
    return json.loads(response[2].decode("utf-8"))


def sse_data(body: bytes) -> list[dict]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in body.decode("utf-8").splitlines()
        if line.startswith("data: ")
    ]


def test_health_requires_bearer_token_and_matches_descriptor(tmp_path: Path) -> None:
    with running_control_plane(tmp_path) as runtime:
        unauthorized = api_request(runtime, "/healthz", token=None)
        assert unauthorized[0] == 401
        assert json_response(unauthorized)["error"]["code"] == "UNAUTHORIZED"

        status, headers, body = api_request(runtime, "/healthz")
        descriptor = json.loads(runtime.descriptor_path.read_text(encoding="utf-8"))

        assert status == 200
        assert headers["Content-Type"] == "application/json; charset=utf-8"
        health = json.loads(body.decode("utf-8"))
        assert health["status"] == "ok"
        assert health["apiVersion"] == "v1"
        assert health["instanceId"] == descriptor["instanceId"] == runtime.instance_id
        assert descriptor["host"] == "127.0.0.1"
        assert descriptor["port"] == runtime.port
        assert descriptor["baseUrl"] == runtime.base_url
        assert descriptor["token"] == TEST_TOKEN

    assert not runtime.descriptor_path.exists()


def test_authentication_rejects_non_ascii_tokens_without_internal_error(
    tmp_path: Path,
) -> None:
    with running_control_plane(tmp_path) as runtime:
        connection = HTTPConnection(runtime.host, runtime.port, timeout=5)
        connection.request(
            "GET",
            "/healthz",
            headers={"Authorization": "Bearer é"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        connection.close()

        assert response.status == 401
        assert payload["error"]["code"] == "UNAUTHORIZED"


def test_odb_discovery_api_returns_naturally_sorted_utf8_paths(tmp_path: Path) -> None:
    root = tmp_path / "工程 A"
    root.mkdir()
    for relative in (
        "case-10.odb",
        "case-2.ODB",
        "子目录/模型 1.odb",
        ".git/ignored.odb",
        "AbaqusODBPostProcessor_Results/ignored.odb",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode("utf-8"))

    with running_control_plane(tmp_path) as runtime:
        response = api_request(
            runtime,
            "/api/v1/odb-discoveries",
            method="POST",
            payload={
                "schemaVersion": 1,
                "root": str(root),
                "recursive": True,
            },
        )

        assert response[0] == 200
        payload = json_response(response)
        assert payload["schemaVersion"] == 1
        assert payload["root"] == str(root.resolve())
        assert payload["recursive"] is True
        assert payload["count"] == 3
        assert payload["warnings"] == []
        assert [item["name"] for item in payload["odbs"]] == [
            "case-2.ODB",
            "case-10.odb",
            "模型 1.odb",
        ]
        assert all(Path(item["path"]).is_absolute() for item in payload["odbs"])
        assert "工程 A" in response[2].decode("utf-8")

        events_response = api_request(runtime, "/api/v1/events?after=0")
        assert events_response[0] == 200
        assert events_response[1]["Content-Type"] == "text/event-stream; charset=utf-8"
        events = sse_data(events_response[2])
        assert [event["kind"] for event in events] == [
            "odb.discovery.started",
            "odb.discovery.completed",
        ]
        assert all(event["aggregateId"] == payload["discoveryId"] for event in events)
        assert payload["eventCursor"] == events[-1]["sequence"]

        last_only = sse_data(
            api_request(
                runtime,
                f"/api/v1/events?after={payload['eventCursor'] - 1}",
            )[2]
        )
        assert [event["kind"] for event in last_only] == ["odb.discovery.completed"]
        no_new_events = api_request(
            runtime,
            f"/api/v1/events?after={payload['eventCursor']}",
        )
        assert sse_data(no_new_events[2]) == []
        assert no_new_events[1]["X-Event-Cursor"] == str(payload["eventCursor"])


def test_discovery_api_validates_schema_and_root(tmp_path: Path) -> None:
    with running_control_plane(tmp_path) as runtime:
        unsupported = api_request(
            runtime,
            "/api/v1/odb-discoveries",
            method="POST",
            payload={"schemaVersion": 2, "root": str(tmp_path)},
        )
        assert unsupported[0] == 400
        assert json_response(unsupported)["error"]["code"] == (
            "UNSUPPORTED_SCHEMA_VERSION"
        )

        missing = api_request(
            runtime,
            "/api/v1/odb-discoveries",
            method="POST",
            payload={
                "schemaVersion": 1,
                "root": str(tmp_path / "不存在"),
                "recursive": True,
            },
        )
        assert missing[0] == 400
        assert json_response(missing)["error"]["code"] == "ROOT_NOT_FOUND"

        events = sse_data(api_request(runtime, "/api/v1/events?after=0")[2])
        assert [event["kind"] for event in events] == [
            "odb.discovery.started",
            "odb.discovery.failed",
        ]


def test_cli_contract_and_import_graph_are_qt_free(tmp_path: Path) -> None:
    descriptor = tmp_path / "control-plane.json"
    args = build_parser().parse_args(["--port", "0", "--descriptor", str(descriptor)])
    assert args.port == 0
    assert args.descriptor == descriptor

    command = [
        sys.executable,
        "-c",
        (
            "import sys; import modules.control_plane; "
            "assert not any(name.startswith('PySide6') for name in sys.modules)"
        ),
    ]
    completed = subprocess.run(
        command,
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
