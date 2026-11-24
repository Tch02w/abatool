"""Real HTTP admission, reversible close and cancellation across a group boundary."""

from __future__ import annotations

import threading
import time
from copy import deepcopy

import pytest

from modules.postprocessor.process_runner import ProcessCancelled
from tests.control_plane.test_api import api_request, json_response, running_control_plane
from tests.control_plane.test_postprocessing_api import _run_payload, _settings


BASE = "/api/v1/odb-postprocess-group-queues"
CLOSE = "/api/v1/shutdown-requests"


def _request(runtime, path, payload=None, status=200):
    response = api_request(runtime, path, method="GET" if payload is None else "POST", payload=payload)
    assert response[0] == status, json_response(response)
    return json_response(response)


def _wait(runtime, path, predicate):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        state = _request(runtime, path)
        if predicate(state):
            return state
        time.sleep(0.02)
    pytest.fail(f"分组队列未到达预期状态：{state}")


def test_shutdown_waits_for_the_running_group_and_never_starts_the_next(tmp_path):
    if tmp_path.drive.upper() == "C:":
        pytest.skip("请使用非 C 盘的 --basetemp 运行 ODB 测试")
    source = tmp_path / "group.odb"
    source.write_bytes(b"fixture")
    entered, cancelling, release = (threading.Event() for _ in range(3))
    started = []

    def runner(plan, progress, log, controller):
        started.append(plan.groups[0].name)
        entered.set()
        deadline = time.monotonic() + 10
        while not controller.cancel_requested and time.monotonic() < deadline:
            time.sleep(0.01)
        assert controller.cancel_requested
        cancelling.set()
        assert release.wait(10)
        raise ProcessCancelled("isolated group stopped")

    payload = _run_payload(tmp_path, source)
    second = deepcopy(payload["groups"][0])
    second.update(id="group-2", name="B")
    payload["groups"].append(second)
    with running_control_plane(tmp_path, postprocess_run_runner=runner,
                               postprocess_settings_provider=_settings) as runtime:
        try:
            queue = _request(runtime, BASE, payload, 202)
            path = BASE + "/" + queue["operationId"]
            assert entered.wait(5)
            assert _request(runtime, BASE + "?activeOnly=true")["operations"][0]["operationId"] == queue["operationId"]
            current = _wait(runtime, path, lambda item: bool(item["groups"][0]["childOperationId"]))
            version = current["version"]
            assert _request(runtime, path + f"?afterVersion={version}") == {"schemaVersion": 1, "operation": None}
            assert _request(runtime, path + "?afterVersion=0")["operation"] == current
            assert _request(runtime, path + f"?afterVersion={version + 1}")["operation"] == current
            close = _request(runtime, CLOSE, {"schemaVersion": 1, "clientRequestId": "close-groups"})
            assert not close["safeToStop"]
            assert any(op["operationId"] == queue["operationId"] for op in close["operations"])
            assert not any(op["operationId"] == current["groups"][0]["childOperationId"] for op in close["operations"])
            assert payload["groups"][0]["name"] in next(op["name"] for op in close["operations"]
                                                        if op["operationId"] == queue["operationId"])
            _request(runtime, BASE, dict(payload, clientRequestId="blocked-admission"), 503)
            _request(runtime, CLOSE + "/close-groups/abort", {"schemaVersion": 1})
            assert _request(runtime, path)["currentGroupId"]
            _request(runtime, CLOSE, {"schemaVersion": 1, "clientRequestId": "stop-groups"})
            stopping = _request(runtime, CLOSE + "/stop-groups/stop", {"schemaVersion": 1})
            assert cancelling.wait(5)
            assert not stopping["safeToStop"]
            _request(runtime, CLOSE + "/stop-groups/commit", {"schemaVersion": 1, "mode": "stop"}, 409)
            release.set()
            terminal = _wait(runtime, path, lambda state: state["status"] == "cancelled")
            assert started == [payload["groups"][0]["name"]]
            assert terminal["result"]["outputCount"] == 0
            assert not _request(runtime, BASE + "?activeOnly=true")["operations"]
            _wait(runtime, CLOSE + "/stop-groups", lambda state: state["safeToStop"])
            _request(runtime, CLOSE + "/stop-groups/abort", {"schemaVersion": 1})
        finally:
            release.set()


def test_group_history_routing_and_query_contract(tmp_path):
    with running_control_plane(tmp_path) as runtime:
        assert "odb.postprocess.group-queue-v1" in _request(runtime, "/healthz")["capabilities"]
        assert _request(runtime, BASE)["operations"] == []
        assert _request(runtime, BASE + "?activeOnly=false")["operations"] == []
        _request(runtime, BASE + "?activeOnly=yes", status=400)
        _request(runtime, BASE + "/unknown", status=404)
        for query in ("afterVersion=-1", "afterVersion=", "afterVersion=1&afterVersion=1", "afterVersion=1&other=1"):
            _request(runtime, BASE + "/unknown?" + query, status=400)
        _request(runtime, BASE + "/unknown/missing/path", {}, 404)
        assert api_request(runtime, BASE, token=None)[0] == 401
