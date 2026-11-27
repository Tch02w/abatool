from __future__ import annotations

import threading
import time
from functools import partial
from pathlib import Path

from modules.control_plane.events import EventStore
from modules.control_plane.result_indexing import (
    ResultIndexBuildRequest,
    ResultIndexOperationManager,
)
from modules.postprocessor.result_assets import (
    INCOMPLETE_OUTPUT_MARKER,
    SHARED_DATA_ROOT_NAME,
)
from modules.postprocessor.result_catalog import classify_result, result_section
from modules.postprocessor.result_index import (
    ResultIndexCancelled,
    build_result_index,
    index_path,
    load_result_index,
)
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)


def request(root, scope, request_id="group-index"):
    return {
        "schemaVersion": 1,
        "clientRequestId": request_id,
        "root": str(root),
        "scopeDirectory": str(scope),
    }


def until_done(read):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        snapshot = read()
        if snapshot["status"] in {"succeeded", "cancelled", "failed"}:
            return snapshot
        time.sleep(0.01)
    raise AssertionError(snapshot)


def test_scope_batch_handles_missing_existing_hidden_and_retries_over_http(
    tmp_path: Path,
):
    root = tmp_path / "results"
    first = root / "Group" / "Batch2"
    second = first.with_name("Batch10")
    third = root / "Another" / "Batch3"
    excluded = [
        root / SHARED_DATA_ROOT_NAME / "Model",
        root / "_internal" / "Batch",
        first.with_name("_draft"),
        first.with_name("incomplete"),
    ]
    for path in [first, second, third, *excluded]:
        path.mkdir(parents=True)
        (path / "load_point_raw.csv").write_text("x,y\n0,1")
    (excluded[-1] / INCOMPLETE_OUTPUT_MARKER).touch()
    build_result_index(first, classify_result, result_section)
    original = index_path(first).stat().st_mtime_ns, index_path(first).read_bytes()

    with running_control_plane(tmp_path) as runtime:
        endpoint = "/api/v1/result-index-batches"

        def submit(scope, key="group-index"):
            return api_request(
                runtime, endpoint, method="POST", payload=request(root, scope, key)
            )

        acceptance = submit(first.parent)
        assert acceptance[0] == 202
        batch_id = json_response(acceptance)["batchId"]
        read = lambda: json_response(api_request(runtime, endpoint + "/" + batch_id))
        result = until_done(read)
        assert result["status"] == "succeeded"
        assert (
            result["total"],
            result["succeeded"],
            result["skipped"],
            result["processed"],
        ) == (2, 1, 1, 2)
        assert int(load_result_index(second).metadata["record_count"]) == 1
        assert not index_path(third).exists()
        assert json_response(submit(first.parent)) == result
        assert submit(root)[0] == 409
        assert (
            submit(first)[0]
            == submit(tmp_path)[0]
            == submit(excluded[0].parent)[0]
            == 400
        )
        batch_id = json_response(submit(root, "all"))["batchId"]
        again = until_done(read)
        assert (again["total"], again["succeeded"], again["skipped"]) == (3, 1, 2)
        batch_id = json_response(submit(root, "repeat-all"))["batchId"]
        assert read()["skipped"] == 3
        assert (
            json_response(
                api_request(
                    runtime, endpoint + "/" + batch_id + "/cancel", method="POST"
                )
            )
            == read()
        )
        assert all(not index_path(path).exists() for path in excluded)
        assert (
            index_path(first).stat().st_mtime_ns,
            index_path(first).read_bytes(),
        ) == original


def test_manual_index_precedes_waiting_batch_members_and_reports_each_outcome(
    tmp_path: Path,
):
    group = tmp_path / "G"
    for name in ("batch2", "batch3", "batch4", "batch10"):
        (group / name).mkdir(parents=True)
    manual = tmp_path / "manual"
    manual.mkdir()
    target = group / "batch2"
    build_result_index(target, classify_result, result_section)
    ready = index_path(target).rename(tmp_path / "ready.sqlite3")
    published = ready.stat().st_mtime_ns
    started, release = threading.Event(), threading.Event()
    order = []
    build_missing = partial(build_result_index, only_if_missing=True)

    def missing(path, *args):
        order.append(path.name)
        if path.name == "batch10":
            started.set()
            assert release.wait(5)
        if path.name == "batch3":
            raise OSError("read denied")
        # Other entries exercise dispatch ordering. Only the late index needs a disk check.
        return build_missing(path, *args) if path == target else {}

    def refresh(path, *args):
        order.append(path.name)
        return {}

    manager = ResultIndexOperationManager(
        EventStore(), builder=refresh, missing_builder=missing
    )
    try:
        batch = manager.create_batch(request(tmp_path, group))
        assert started.wait(5)
        assert not manager.prepare_shutdown(reserve=False)["safeToStop"]
        overlap = manager.create_batch(request(tmp_path, group, "overlap"))
        assert overlap["skipped"] == 4 and overlap["activeOperationIds"] == []
        manager.get_batch(overlap["batchId"], cancel=True)
        single = manager.create(
            ResultIndexBuildRequest("manual", str(tmp_path), str(manual))
        )
        # A different writer published a now-queued index after the initial scan.
        ready.replace(index_path(target))
        release.set()
        result = until_done(lambda: manager.get_batch(batch["batchId"]))
        assert order == ["batch10", "manual", "batch4", "batch3", "batch2"]
        assert manager.get(single["operationId"])["status"] == "succeeded"
        assert result["status"] == "failed" and result["activeOperationIds"] == []
        assert (result["succeeded"], result["skipped"], result["failed"]) == (2, 1, 1)
        assert result["failures"] == [
            {"timeDirectory": str(group / "batch3"), "message": "read denied"}
        ]
        assert index_path(target).stat().st_mtime_ns == published
    finally:
        release.set()
        manager.close()


def test_cancel_batch_preserves_committed_members_and_cancels_queued(tmp_path: Path):
    group = tmp_path / "group"
    for name in ("a", "b", "c"):
        (group / name).mkdir(parents=True)
    writing = threading.Event()

    def build(path, classify, section, cancel, progress):
        if path.name == "b":
            writing.set()
            assert cancel.wait(5)
            raise ResultIndexCancelled()
        return build_result_index(
            path, classify, section, cancel, progress, only_if_missing=True
        )

    manager = ResultIndexOperationManager(EventStore(), missing_builder=build)
    try:
        batch = manager.create_batch(request(tmp_path, group))
        assert writing.wait(5)
        active = manager.list_snapshots(active_only=True)
        assert (
            all(op["batchId"] == batch["batchId"] for op in active) and len(active) == 2
        )
        manager.get_batch(batch["batchId"], cancel=True)
        done = until_done(lambda: manager.get_batch(batch["batchId"]))
        assert done["status"] == "cancelled"
        assert (done["succeeded"], done["cancelled"], done["processed"]) == (1, 2, 3)
        assert index_path(group / "c").is_file()
        assert not index_path(group / "a").exists()
    finally:
        manager.close()


def test_cancel_after_atomic_publish_reports_real_result(tmp_path: Path):
    committed, release = threading.Event(), threading.Event()

    def build(*args):
        result = build_result_index(*args)
        committed.set()
        assert release.wait(5)
        return result

    manager = ResultIndexOperationManager(EventStore(), builder=build)
    try:
        operation = manager.create(
            ResultIndexBuildRequest("single", str(tmp_path), str(tmp_path))
        )
        assert committed.wait(5)
        manager.cancel(operation["operationId"])
        release.set()
        assert (
            until_done(lambda: manager.get(operation["operationId"]))["status"]
            == "succeeded"
        )
        assert load_result_index(tmp_path).metadata["record_count"] == "0"
    finally:
        release.set()
        manager.close()
