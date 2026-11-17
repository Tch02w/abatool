from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import psutil
import pytest

from modules.control_plane.contracts import ApiProblem
from modules.control_plane.events import EventStore
from modules.control_plane.odb_merge_operations import OdbMergeOperationManager
from modules.control_plane.odb_result_batches import OdbResultBatchManager
from modules.control_plane.odb_result_graphs import OdbResultGraphService
from modules.postprocessor.process_runner import ProcessCancelled
from modules.submitter.odb_merge_core import OdbMergeResult
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_odb_result_graphs_api import node, save


def graph(directory):
    service = OdbResultGraphService(directory / "graph.json")
    save(
        service,
        [
            node(directory, "base"),
            node(directory, "common", "base"),
            node(directory, "left", "common"),
            node(directory, "right", "common"),
        ],
        directory,
    )
    return service


def request():
    return {
        "schemaVersion": 1,
        "clientRequestId": "batch-test",
        "source": {"kind": "graph", "revision": 1, "targetNodeIds": ["left", "right"]},
        "options": {
            "includeHistory": True,
            "compressResult": False,
            "copyOriginal": False,
        },
    }


def publish(req, *args):
    req.output_odb.write_bytes(
        req.original_odb.read_bytes() + b"+" + req.restart_odb.read_bytes()
    )
    report = req.output_odb.with_suffix(".merge-validation.json")
    report.write_text('{"testReceipt": true}', encoding="utf-8")
    return OdbMergeResult(
        req.output_odb, req.original_odb, req.restart_odb, "fixture", report
    )


@contextmanager
def managers(directory, service, runner=publish):
    merge = OdbMergeOperationManager(
        EventStore(),
        runner=runner,
        command_provider=lambda: "fixture",
        journal_path=directory / "merge.sqlite3",
    )
    batch = OdbResultBatchManager(merge, service, directory / "batch.sqlite3")
    try:
        yield batch, merge
    finally:
        batch.close()
        merge.close()


def wait(manager, identifier):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        item = manager.get(identifier)
        if item["status"] in {"succeeded", "failed", "cancelled"}:
            return item
        time.sleep(0.01)
    raise AssertionError("Batch did not finish")


def test_shares_only_ancestors_uses_actual_output_and_freezes_options(tmp_path):
    service = graph(tmp_path)
    calls = []
    started, release = threading.Event(), threading.Event()

    def runner(req, *args):
        calls.append(req)
        if len(calls) == 1:
            started.set()
            assert release.wait(5)
            # Actual publication may choose another name after admission.
            from dataclasses import replace

            req = replace(req, output_odb=tmp_path / "numbered.odb")
        return publish(req)

    with managers(tmp_path, service, runner) as (batch, _):
        payload = request()
        initial = batch.create(payload)
        assert started.wait(5)
        payload["options"]["includeHistory"] = False
        release.set()
        done = wait(batch, initial["operationId"])
        assert done["status"] == "succeeded"
        assert done["completedSteps"] == done["totalSteps"] == 3
        assert len(done["results"]) == 2
        assert len(calls) == 3 and all(r.include_history for r in calls)
        assert (
            calls[1].original_odb == calls[2].original_odb == tmp_path / "numbered.odb"
        )
        assert [r.restart_odb.stem for r in calls] == ["common", "left", "right"]
        assert batch.create(request())["operationId"] == initial["operationId"]
    with managers(tmp_path, service, lambda *a: pytest.fail("Must not replay")) as (
        batch,
        _,
    ):
        assert batch.create(request())["status"] == "succeeded"


@pytest.mark.parametrize("fault", ["revision", "source", "options", "unknown"])
def test_bad_request_starts_nothing(tmp_path, fault):
    service = graph(tmp_path)
    payload = request()
    if fault == "revision":
        payload["source"]["revision"] = 0
    elif fault == "source":
        (tmp_path / "common.odb").unlink()
    elif fault == "options":
        payload["options"]["compressResult"] = "true"
    else:
        payload["future"] = True
    with managers(tmp_path, service, lambda *a: pytest.fail("Must not run")) as (
        batch,
        merge,
    ):
        with pytest.raises(ApiProblem):
            batch.create(payload)
        assert merge.list_snapshots() == []


def test_cancel_waits_for_cleanup_and_does_not_start_descendants(tmp_path):
    service = graph(tmp_path)
    started, cleanup, release = threading.Event(), threading.Event(), threading.Event()

    def runner(req, progress, log, controller):
        started.set()
        while not controller.cancel_requested:
            time.sleep(0.01)
        cleanup.set()
        assert release.wait(5)
        raise ProcessCancelled()

    with managers(tmp_path, service, runner) as (batch, merge):
        initial = batch.create(request())
        assert started.wait(5)
        batch.cancel(initial["operationId"])
        assert cleanup.wait(5)
        assert batch.get(initial["operationId"])["status"] == "cancelling"
        assert batch.prepare_shutdown()["safeToStop"] is False
        release.set()
        assert wait(batch, initial["operationId"])["status"] == "cancelled"
        assert len(merge.list_snapshots()) == 1


def test_later_failure_preserves_completed_target(tmp_path):
    service = graph(tmp_path)

    def runner(req, *args):
        if req.restart_odb.stem == "right":
            raise RuntimeError("fixture failure")
        return publish(req)

    with managers(tmp_path, service, runner) as (batch, _):
        done = wait(batch, batch.create(request())["operationId"])
        assert done["status"] == "failed"
        assert done["completedSteps"] == 2
        assert (
            len(done["results"]) == 1
            and Path(done["results"][0]["outputOdb"]).is_file()
        )


def test_empty_frame_warning_survives_batch_completion_and_restart(tmp_path):
    from dataclasses import replace

    service = graph(tmp_path)

    def partial(req, *args):
        return replace(publish(req), empty_frame_steps=("future-step",))

    with managers(tmp_path, service, partial) as (batch, _):
        done = wait(batch, batch.create(request())["operationId"])
        assert done["status"] == "succeeded" and "无结果帧" in done["warnings"][0]
    with managers(tmp_path, service) as (batch, _):
        assert batch.get(done["operationId"])["warnings"] == done["warnings"]


# The child process exits after a *real persisted child completion*, before the
# batch completion checkpoint. This is not a saved JSON imitation of a restart.
CRASH_WORKER = r"""
import os, sys, threading
from pathlib import Path
from tests.control_plane.test_odb_result_batches import graph, managers, request, publish
directory = Path(sys.argv[1])
service = graph(directory)
def runner(req, *args):
    with (directory / "calls.txt").open("a") as out: out.write(req.restart_odb.stem + "\n")
    if sys.argv[2] == "running":
        (directory / "started").write_text("started")
        threading.Event().wait()
    return publish(req)
with managers(directory, service, runner) as (batch, merge):
    print(os.getpid(), flush=True)
    original = batch._save
    def checkpoint(record):
        if record["snapshot"]["stages"][0]["result"] is not None:
            os._exit(77)
        return original(record)
    batch._save = checkpoint
    batch.create(request())
    threading.Event().wait()
"""


def crash(directory, mode="published"):
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", CRASH_WORKER, str(directory), mode],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    worker = None
    try:
        # Windows .venv python.exe is a launcher, not necessarily the worker PID.
        worker = psutil.Process(int(process.stdout.readline().strip()))
        command = worker.cmdline()
        assert CRASH_WORKER in command and str(directory) in command
        if mode == "running":
            deadline = time.monotonic() + 15
            while not (directory / "started").exists():
                assert process.poll() is None and time.monotonic() < deadline
                time.sleep(0.01)
            worker.kill()  # Exactly the verified isolated test worker, no Abaqus.
            worker.wait(timeout=10)
        assert process.wait(timeout=20) != 0
    finally:
        if worker is not None and worker.is_running():
            worker.kill()
            worker.wait(timeout=10)
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)


def test_real_restart_reuses_published_child_then_continues(tmp_path):
    crash(tmp_path)
    calls = []

    def runner(req, *args):
        calls.append(req.restart_odb.stem)
        return publish(req)

    with managers(tmp_path, OdbResultGraphService(tmp_path / "graph.json"), runner) as (
        batch,
        merge,
    ):
        initial = batch.list_snapshots()[0]
        assert initial["status"] == "suspended"
        done = wait(batch, batch.resume(initial["operationId"])["operationId"])
        assert done["status"] == "succeeded"
        assert calls == ["left", "right"]
        assert len(merge.list_snapshots()) == 3
        assert (tmp_path / "calls.txt").read_text().splitlines() == ["common"]


def test_interrupted_child_is_never_relaunched(tmp_path):
    crash(tmp_path, "running")
    with managers(
        tmp_path,
        OdbResultGraphService(tmp_path / "graph.json"),
        lambda *a: pytest.fail("Uncertain child replayed"),
    ) as (batch, merge):
        assert batch._storage_error is None, batch._storage_error
        item = batch.list_snapshots()[0]
        done = wait(batch, batch.resume(item["operationId"])["operationId"])
        assert done["status"] == "failed"
        assert len(merge.list_snapshots()) == 1
        assert merge.list_snapshots()[0]["error"]["code"] == "ODB_MERGE_INTERRUPTED"


def test_missing_child_history_cannot_turn_submitted_stage_into_new_work(tmp_path):
    crash(tmp_path)
    # Keep the original history intact; simulate unavailable history by using a
    # separate, empty merge journal after a backend restart.
    merge = OdbMergeOperationManager(
        EventStore(),
        runner=lambda *a: pytest.fail("Missing child replayed"),
        command_provider=lambda: "fixture",
        journal_path=tmp_path / "empty-merge.sqlite3",
    )
    batch = OdbResultBatchManager(
        merge,
        OdbResultGraphService(tmp_path / "graph.json"),
        tmp_path / "batch.sqlite3",
    )
    try:
        item = batch.list_snapshots()[0]
        done = wait(batch, batch.resume(item["operationId"])["operationId"])
        assert done["status"] == "failed" and "记录缺失" in done["phase"]
        assert merge.list_snapshots() == []
    finally:
        batch.close()
        merge.close()


def test_recovered_child_must_match_frozen_options(tmp_path):
    crash(tmp_path)
    with managers(
        tmp_path,
        OdbResultGraphService(tmp_path / "graph.json"),
        lambda *a: pytest.fail("Mismatched child was replayed"),
    ) as (batch, merge):
        record = next(iter(batch._records.values()))
        # Simulate an internally consistent but incompatible batch checkpoint.
        record["request"]["options"]["includeHistory"] = False
        record["snapshot"]["options"]["includeHistory"] = False
        batch._save(record)
        done = wait(
            batch, batch.resume(record["snapshot"]["operationId"])["operationId"]
        )
        assert done["status"] == "failed" and "不一致" in done["phase"]
        assert len(merge.list_snapshots()) == 1


@pytest.mark.parametrize("change", ["source", "output", "receipt"])
def test_resume_rejects_changed_sources_or_completed_results(tmp_path, change):
    service = graph(tmp_path)
    with managers(tmp_path, service) as (batch, _):
        done = wait(batch, batch.create(request())["operationId"])
        identifier = done["operationId"]
        # Deliberately suspend the saved snapshot to exercise revalidation of all
        # completed checkpoints; crash tests above establish real restart behavior.
        record = batch._records[identifier]
        record["snapshot"]["status"] = "suspended"
        batch._save(record)
    if change == "source":
        path = tmp_path / "common.odb"
    else:
        path = Path(
            done["stages"][0]["result"][
                "outputOdb" if change == "output" else "validationReport"
            ]
        )
    before = path.stat()
    data = path.read_bytes()
    path.write_bytes(bytes([data[0] ^ 1]) + data[1:])
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    with managers(
        tmp_path, service, lambda *a: pytest.fail("Changed input replayed")
    ) as (batch, _):
        done = wait(batch, batch.resume(identifier)["operationId"])
        assert done["status"] == "failed" and "变化" in done["phase"]


def test_storage_failure_before_admission_never_starts_merge(tmp_path, monkeypatch):
    service = graph(tmp_path)
    with managers(tmp_path, service) as (batch, merge):
        monkeypatch.setattr(
            batch._journal,
            "save",
            lambda record: (_ for _ in ()).throw(OSError("disk full")),
        )
        with pytest.raises(ApiProblem, match="记录"):
            batch.create(request())
        assert merge.list_snapshots() == []


def test_single_owner_and_corrupt_history_fail_closed(tmp_path):
    service = graph(tmp_path)
    with managers(tmp_path, service) as (batch, merge):
        second = OdbResultBatchManager(merge, service, tmp_path / "batch.sqlite3")
        try:
            with pytest.raises(ApiProblem):
                second.create(request())
        finally:
            second.close()
        wait(batch, batch.create(request())["operationId"])
    database = tmp_path / "batch.sqlite3"
    with sqlite3.connect(database) as db:
        row = json.loads(
            db.execute("SELECT payload FROM batch_operations").fetchone()[0]
        )
        row["snapshot"]["stages"][0]["identity"] = {}
        db.execute("UPDATE batch_operations SET payload=?", (json.dumps(row),))
    before = database.read_bytes()
    with managers(tmp_path, service) as (batch, _), pytest.raises(ApiProblem):
        batch.list_snapshots()
    assert database.read_bytes() == before


def test_api_idempotency_auth_history_and_joint_shutdown(tmp_path):
    service = graph(tmp_path)
    with running_control_plane(
        tmp_path,
        odb_result_graph_path=service.path,
        odb_merge_runner=publish,
        odb_merge_command_provider=lambda: "fixture",
    ) as runtime:
        path = "/api/v1/odb-result-batches"
        assert api_request(runtime, path, token=None)[0] == 401
        initial = json_response(
            api_request(runtime, path, method="POST", payload=request())
        )
        done = wait(
            runtime.httpd.context.odb_result_batch_manager, initial["operationId"]
        )
        assert done["status"] == "succeeded"
        repeat = api_request(runtime, path, method="POST", payload=request())
        assert json_response(repeat)["operationId"] == done["operationId"]
        changed = deepcopy(request())
        changed["options"]["includeHistory"] = False
        assert api_request(runtime, path, method="POST", payload=changed)[0] == 409
        assert (
            json_response(api_request(runtime, path))["operations"][0]["results"]
            == done["results"]
        )
        assert (
            json_response(
                api_request(
                    runtime, "/api/v1/odb-upgrade-shutdown-check", method="POST"
                )
            )["safeToStop"]
            is True
        )
        fresh = request()
        fresh["clientRequestId"] = "new"
        assert api_request(runtime, path, method="POST", payload=fresh)[0] == 503
