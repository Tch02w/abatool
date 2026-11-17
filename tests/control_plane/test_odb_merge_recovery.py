from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from modules.control_plane.contracts import ApiProblem
from modules.control_plane.events import EventStore
from modules.control_plane.odb_merge_operations import (
    OdbMergeOperationManager,
    OdbMergeOperationRequest,
)
from modules.postprocessor.process_runner import ProcessCancelled
from modules.submitter.odb_merge_core import OdbMergeResult
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_odb_merge_operations_api import _request_payload


def request(directory, identifier="merge"):
    for name in ("original.odb", "restart.odb"):
        path = directory / name
        if not path.exists():
            path.write_bytes(name.encode())
    return OdbMergeOperationRequest.from_payload(
        _request_payload(
            directory / "original.odb",
            directory / "restart.odb",
            directory / "requested.odb",
            identifier,
        )
    )


def result(request, *args):
    return OdbMergeResult(
        request.output_odb, request.original_odb, request.restart_odb, "test command"
    )


def wait(manager, operation_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        snapshot = manager.get(operation_id)
        if snapshot["status"] in {"succeeded", "cancelled", "failed"}:
            return snapshot
        time.sleep(0.01)
    raise AssertionError("Merge did not reach a terminal state")


def manager(path, runner=result):
    return OdbMergeOperationManager(
        EventStore(),
        runner=runner,
        journal_path=path,
        command_provider=lambda: "abaqus",
    )


def test_history_and_original_idempotency_survive_source_removal(tmp_path):
    path = tmp_path / "history.sqlite3"
    original_request = request(tmp_path)
    first = manager(path)
    try:
        finished = wait(first, first.create(original_request)["operationId"])
    finally:
        first.close()
    Path(original_request.original_odb).unlink()
    calls = []
    reopened = manager(path, lambda *args: calls.append(1))
    try:
        recovered = reopened.get(finished["operationId"])
        assert {k: v for k, v in recovered.items() if k != "eventCursor"} == {
            k: v for k, v in finished.items() if k != "eventCursor"
        }
        assert (
            reopened.create(original_request)["operationId"] == finished["operationId"]
        )
        assert calls == []
        # The initial output name differs from the normalized *_joined.odb path.
        assert original_request.output_odb != recovered["request"]["outputOdb"]
    finally:
        reopened.close()


def test_actual_process_crash_recovers_without_replaying(tmp_path):
    payload = request(tmp_path)
    script = """
import sys, threading
from pathlib import Path
from modules.control_plane.events import EventStore
from modules.control_plane.odb_merge_operations import OdbMergeOperationManager, OdbMergeOperationRequest
from tests.control_plane.test_odb_merge_operations_api import _request_payload
work = Path(sys.argv[1])
def run(request, progress, log, controller):
    progress(60, "test worker active")
    (work / "ready").write_text("ready")
    threading.Event().wait()
manager = OdbMergeOperationManager(EventStore(), runner=run, journal_path=work / "history.sqlite3", command_provider=lambda: "abaqus")
snapshot = manager.create(OdbMergeOperationRequest.from_payload(_request_payload(work / "original.odb", work / "restart.odb", work / "requested.odb", "merge")))
(work / "operation-id").write_text(snapshot["operationId"])
threading.Event().wait()
"""
    child = subprocess.Popen(
        [sys.executable, "-u", "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 15
        while not (
            (tmp_path / "ready").exists() and (tmp_path / "operation-id").exists()
        ):
            assert child.poll() is None, child.communicate()[0].decode(errors="replace")
            assert time.monotonic() < deadline
            time.sleep(0.03)
        assert child.poll() is None
    finally:
        # Only the exact helper created above is terminated; no Abaqus is launched.
        if child.poll() is None:
            child.terminate()
        child.communicate(timeout=10)
    operation_id = (tmp_path / "operation-id").read_text()
    calls = []
    reopened = manager(tmp_path / "history.sqlite3", lambda *args: calls.append(1))
    try:
        recovered = reopened.get(operation_id)
        assert recovered["status"] == "failed"
        assert recovered["error"]["code"] == "ODB_MERGE_INTERRUPTED"
        assert not recovered["error"]["retryable"]
        assert recovered["result"] is None
        assert reopened.create(payload)["operationId"] == operation_id
        assert calls == []
        assert (tmp_path / "original.odb").read_bytes() == b"original.odb"
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "corruption",
    [
        "bytes",
        "version",
        "false-success",
        "progress",
        "signature",
        "private",
        "duplicate-request",
    ],
)
def test_corruption_preserves_database_and_rejects_new_work(tmp_path, corruption):
    path = tmp_path / "history.sqlite3"
    initial = manager(path)
    try:
        finished = wait(initial, initial.create(request(tmp_path))["operationId"])
    finally:
        initial.close()
    if corruption == "bytes":
        path.write_bytes(b"not a database")
    else:
        with sqlite3.connect(path) as db:
            if corruption == "version":
                db.execute("PRAGMA user_version=999")
            else:
                record = json.loads(
                    db.execute("SELECT payload FROM merge_operations").fetchone()[0]
                )
                if corruption == "false-success":
                    record["snapshot"]["result"] = None
                if corruption == "progress":
                    record["snapshot"]["progress"]["percent"] = 101
                if corruption == "signature":
                    record["signature"][0] = str(tmp_path / "wrong.odb")
                if corruption == "private":
                    record["snapshot"]["_process"] = 42
                if corruption == "duplicate-request":
                    record["snapshot"]["operationId"] = "other"
                    db.execute(
                        "INSERT INTO merge_operations VALUES (?, ?)",
                        ("other", json.dumps(record)),
                    )
                else:
                    db.execute(
                        "UPDATE merge_operations SET payload=?", (json.dumps(record),)
                    )
    before = path.read_bytes()
    reopened = manager(path)
    try:
        with pytest.raises(ApiProblem):
            reopened.list_snapshots()
        with pytest.raises(ApiProblem):
            reopened.get(finished["operationId"])
        with pytest.raises(ApiProblem):
            reopened.create(request(tmp_path, "new"))
        assert path.read_bytes() == before
    finally:
        reopened.close()


def test_single_owner_and_initial_write_failure_never_execute(tmp_path, monkeypatch):
    path = tmp_path / "history.sqlite3"
    calls = []
    first = manager(path, lambda *args: calls.append(1))
    second = manager(path)
    try:
        with pytest.raises(ApiProblem):
            second.create(request(tmp_path))

        def fail(record):
            raise sqlite3.OperationalError("disk full")

        monkeypatch.setattr(first._journal, "save", fail)
        with pytest.raises(ApiProblem):
            first.create(request(tmp_path))
        assert first.list_snapshots() == []
        assert calls == []
    finally:
        second.close()
        first.close()


@pytest.mark.parametrize("committed", [False, True])
def test_disk_failure_stops_unpublished_work_but_retains_committed_result(
    tmp_path, monkeypatch, committed
):
    entered, release = threading.Event(), threading.Event()

    def runner(req, progress, log, controller):
        entered.set()
        assert release.wait(5)
        if committed:
            return result(req)
        progress(82, "validating")
        assert controller.cancel_requested
        raise ProcessCancelled("Stopped before publication")

    active = manager(tmp_path / "history.sqlite3", runner)
    try:
        accepted = active.create(request(tmp_path))
        assert entered.wait(5)

        def fail(record):
            raise sqlite3.OperationalError("disk full")

        monkeypatch.setattr(active._journal, "save", fail)
        active._operations[accepted["operationId"]].checkpoint_at = 0
        release.set()
        finished = wait(active, accepted["operationId"])
        assert finished["status"] == ("succeeded" if committed else "cancelled")
        assert finished["persistenceWarning"]
        assert active.prepare_shutdown()["safeToStop"] is False
        with pytest.raises(ApiProblem):
            active.create(request(tmp_path, "new"))
    finally:
        release.set()
        active.close()
    recovered = manager(tmp_path / "history.sqlite3")
    try:
        assert (
            recovered.get(accepted["operationId"])["error"]["code"]
            == "ODB_MERGE_INTERRUPTED"
        )
    finally:
        recovered.close()


def test_progress_is_coalesced_and_terminal_log_tail_is_durable(tmp_path, monkeypatch):
    import modules.control_plane.odb_merge_operations as operations

    monkeypatch.setattr(operations, "time", SimpleNamespace(monotonic=lambda: 100.0))

    def runner(req, progress, log, controller):
        for index in range(600):
            log(f"line {index}")
        return result(req)

    active = manager(tmp_path / "history.sqlite3", runner)
    saves = []
    save = active._journal.save

    def counted(record):
        saves.append(record)
        save(record)

    monkeypatch.setattr(active._journal, "save", counted)
    try:
        final = wait(active, active.create(request(tmp_path))["operationId"])
        assert len(saves) == 4  # admission, starting, running, terminal
        assert final["logs"] == [f"line {index}" for index in range(400, 600)]
    finally:
        active.close()
    reopened = manager(tmp_path / "history.sqlite3")
    try:
        assert reopened.get(final["operationId"])["logs"] == final["logs"]
    finally:
        reopened.close()


def test_http_restart_and_joint_shutdown_reservation(tmp_path):
    payload = _request_payload(
        tmp_path / "original.odb",
        tmp_path / "restart.odb",
        tmp_path / "requested.odb",
        "merge",
    )
    request(tmp_path)
    with running_control_plane(
        tmp_path, odb_merge_runner=result, odb_merge_command_provider=lambda: "abaqus"
    ) as runtime:
        initial = json_response(
            api_request(
                runtime, "/api/v1/odb-merge-operations", method="POST", payload=payload
            )
        )
        wait(runtime.odb_merge_manager, initial["operationId"])
    with running_control_plane(
        tmp_path, odb_merge_runner=lambda *args: pytest.fail("Must not replay")
    ) as runtime:
        assert (
            json_response(api_request(runtime, "/api/v1/odb-merge-operations"))[
                "operations"
            ][0]["operationId"]
            == initial["operationId"]
        )
        repeated = api_request(
            runtime, "/api/v1/odb-merge-operations", method="POST", payload=payload
        )
        assert json_response(repeated)["operationId"] == initial["operationId"]
        safe = json_response(
            api_request(runtime, "/api/v1/odb-upgrade-shutdown-check", method="POST")
        )
        assert safe["safeToStop"]
        payload["clientRequestId"] = "new"
        assert (
            api_request(
                runtime, "/api/v1/odb-merge-operations", method="POST", payload=payload
            )[0]
            == 503
        )


def test_active_merge_prevents_shutdown_without_reserving_upgrade(tmp_path):
    entered, release = threading.Event(), threading.Event()

    def runner(req, *args):
        entered.set()
        assert release.wait(5)
        return result(req)

    with running_control_plane(
        tmp_path, odb_merge_runner=runner, odb_merge_command_provider=lambda: "abaqus"
    ) as runtime:
        try:
            accepted = runtime.odb_merge_manager.create(request(tmp_path))
            assert entered.wait(5)
            state = json_response(
                api_request(
                    runtime, "/api/v1/odb-upgrade-shutdown-check", method="POST"
                )
            )
            assert state["safeToStop"] is False
            assert state["operations"][0]["operationId"] == accepted["operationId"]
            assert runtime.httpd.context.odb_upgrade_manager._closed is False
            assert runtime.odb_merge_manager._closed is False
        finally:
            release.set()
