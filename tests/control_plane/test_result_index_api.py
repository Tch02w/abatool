from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path

from modules.postprocessor.result_index import (
    ResultIndexCancelled,
    index_path,
    lock_path,
)
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
    sse_data,
)


def _payload(root: Path, time_directory: Path, request_id: str = "index-request"):
    return {
        "schemaVersion": 1,
        "clientRequestId": request_id,
        "root": str(root),
        "timeDirectory": str(time_directory),
    }


def _wait(runtime, operation_id: str, statuses: set[str], timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        response = api_request(runtime, f"/api/v1/result-index-builds/{operation_id}")
        assert response[0] == 200
        latest = json_response(response)
        if latest["status"] in statuses:
            return latest
        time.sleep(0.01)
    raise AssertionError(f"result index operation timed out: {latest}")


def test_refresh_can_retry_after_a_legacy_writer_releases_its_marker(tmp_path: Path, monkeypatch) -> None:
    def reject_signal(*_):
        raise AssertionError("Index contention must not send a Windows process signal")

    if os.name == "nt":
        monkeypatch.setattr(os, "kill", reject_signal)
    root = tmp_path / "results"
    batch = root / "group" / "20260830_120000"
    (batch / "model").mkdir(parents=True)
    marker = lock_path(batch)
    marker.write_text(json.dumps({"pid": os.getpid(), "host": socket.gethostname()}), encoding="utf-8")

    with running_control_plane(tmp_path) as runtime:
        first = json_response(api_request(runtime, "/api/v1/result-index-builds", method="POST",
                                          payload=_payload(root, batch)))
        failure = _wait(runtime, first["operationId"], {"failed"})["error"]
        assert failure["retryable"] and failure["details"]["exceptionType"] == "ResultIndexLocked"
        assert marker.is_file() and not index_path(batch).exists()
        marker.unlink()
        second = json_response(api_request(runtime, "/api/v1/result-index-builds", method="POST",
                                           payload=_payload(root, batch, "retry-after-release")))
        _wait(runtime, second["operationId"], {"succeeded"})
        assert index_path(batch).is_file()


def test_result_index_build_is_async_idempotent_and_loadable(tmp_path: Path) -> None:
    root = tmp_path / "results"
    batch = root / "group" / "20260830_120000"
    odb = batch / "model"
    odb.mkdir(parents=True)
    (odb / "load_point_raw.csv").write_text("Time,RF3\n0,0\n", encoding="utf-8")
    (batch / "extra.csv").write_text("Time,RF3\n0,1\n", encoding="utf-8")

    with running_control_plane(tmp_path) as runtime:
        first = api_request(
            runtime,
            "/api/v1/result-index-builds",
            method="POST",
            payload=_payload(root, batch),
        )
        second = api_request(
            runtime,
            "/api/v1/result-index-builds",
            method="POST",
            payload=_payload(root, batch),
        )
        assert first[0] == second[0] == 202
        accepted = json_response(first)
        repeated = json_response(second)
        assert repeated["operationId"] == accepted["operationId"]

        succeeded = _wait(runtime, accepted["operationId"], {"succeeded"})
        assert succeeded["kind"] == "result.index.build"
        assert succeeded["request"]["timeDirectory"] == str(batch.resolve())
        assert int(succeeded["metadata"]["record_count"]) == 2
        assert succeeded["progress"] == {"processed": 2, "currentItem": ""}
        events = sse_data(api_request(runtime, "/api/v1/events?after=0")[2])
        published = next(event for event in events if event["kind"] == "result.index.succeeded")
        assert published["payload"]["progress"] == succeeded["progress"]
        assert index_path(batch).is_file()

        active = json_response(
            api_request(runtime, "/api/v1/result-index-builds?activeOnly=true")
        )
        assert active["operations"] == []
        history = json_response(api_request(runtime, "/api/v1/result-index-builds"))
        assert [item["operationId"] for item in history["operations"]] == [
            accepted["operationId"]
        ]

        records = api_request(
            runtime,
            "/api/v1/result-records",
            method="POST",
            payload={
                "schemaVersion": 1,
                "root": str(root),
                "scope": str(odb),
                "timeDirectory": str(batch),
            },
        )
        assert records[0] == 200
        assert json_response(records)["records"][0]["name"] == "load_point_raw.csv"


def test_result_index_cancel_is_cooperative_and_terminal(tmp_path: Path) -> None:
    root = tmp_path / "results"
    batch = root / "group" / "batch"
    batch.mkdir(parents=True)
    started = threading.Event()

    def builder(_directory, _classify, _section, cancel_event=None, progress=None):
        assert cancel_event is not None
        assert progress is not None
        progress(1, "model/file.csv")
        started.set()
        assert cancel_event.wait(5)
        raise ResultIndexCancelled("cancelled by test")

    with running_control_plane(tmp_path, result_index_builder=builder) as runtime:
        accepted = json_response(
            api_request(
                runtime,
                "/api/v1/result-index-builds",
                method="POST",
                payload=_payload(root, batch),
            )
        )
        assert started.wait(5)
        cancel = api_request(
            runtime,
            f"/api/v1/result-index-builds/{accepted['operationId']}/cancel",
            method="POST",
        )
        assert cancel[0] == 202
        cancelled = _wait(runtime, accepted["operationId"], {"cancelled"})
        assert cancelled["error"] is None
        assert cancelled["progress"]["processed"] == 1

        repeated = api_request(
            runtime,
            f"/api/v1/result-index-builds/{accepted['operationId']}/cancel",
            method="POST",
        )
        assert json_response(repeated)["version"] == cancelled["version"]


def test_failed_index_retains_last_observed_progress(tmp_path: Path) -> None:
    batch = tmp_path / "group" / "batch"
    batch.mkdir(parents=True)

    def fail_before_publication(_directory, _classify, _section, cancel_event, progress):
        progress(17, "model/partial.csv")
        raise OSError("fixture publication failed")

    with running_control_plane(tmp_path, result_index_builder=fail_before_publication) as runtime:
        accepted = json_response(api_request(runtime, "/api/v1/result-index-builds", method="POST",
                                             payload=_payload(tmp_path, batch)))
        failed = _wait(runtime, accepted["operationId"], {"failed"})
        assert failed["progress"] == {"processed": 17, "currentItem": ""}
        assert failed["metadata"] == {} and not index_path(batch).exists()
