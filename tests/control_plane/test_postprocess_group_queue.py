"""Exercise durable group dispatch with the real parser, child manager and publication layout."""

import json
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest

from modules.control_plane.contracts import ApiProblem
from modules.control_plane.events import EventStore
from modules.control_plane.postprocess_group_queue import TERMINAL, PostprocessGroupQueueManager
from modules.control_plane.postprocessing import PostprocessOperationManager
from modules.control_plane.results import discover_result_scopes
from modules.postprocessor.cache import abaqus_cache_version, quick_odb_fingerprint
from modules.postprocessor.file_attributes import clear_windows_hidden
from modules.postprocessor.postprocess_execution import safe_folder_name
from modules.postprocessor.process_runner import ProcessCancelled
from modules.postprocessor.result_assets import (
    GROUP_MEMBER_MANIFEST_NAME, numeric_asset_dir, write_group_member_manifest, write_numeric_asset_manifest,
)
from tests.control_plane.test_postprocessing_api import _run_payload, _settings
from tests.postprocessor.test_result_assets import write_valid_numeric_payload


@pytest.fixture
def source(tmp_path):
    if tmp_path.drive.upper() == "C:":
        pytest.skip("需要非 C 盘测试目录")
    path = tmp_path / "member.odb"
    path.write_bytes(b"synthetic")
    return path


def run(source, *groups):
    payload = _run_payload(source.parent, source, uuid4().hex)
    template = payload["groups"][0]
    payload["groups"] = [dict(template, id=f"group-{i}", name=g) for i, g in enumerate(groups, 1)]
    return payload


def publish(plan):
    group = plan.groups[0]
    outputs = []
    for source in group.members:
        root = source.parent / "AbaqusODBPostProcessor_Results"
        fingerprint = quick_odb_fingerprint(source)
        config_hash = "c" * 64
        asset = numeric_asset_dir(root, source, fingerprint, config_hash)
        if not asset.is_dir():
            write_valid_numeric_payload(asset)
            write_numeric_asset_manifest(asset, odb_path=source, content_fingerprint=fingerprint,
                                         numeric_config_hash=config_hash,
                                         abaqus_version=abaqus_cache_version(dict(plan.options.settings)))
        folder = "未分组" if group.standalone else safe_folder_name(group.name)
        output = root / folder / (plan.batch_id + "_01") / safe_folder_name(source.stem)
        (output / "frames").mkdir(parents=True)
        (output / "frames" / "frame.png").write_bytes(b"test frame")
        receipt = dict(white_png_count=1, transparent_png_count=0, animations={})
        (output / "render_postprocess_manifest.json").write_text(json.dumps(receipt), encoding="utf-8")
        write_group_member_manifest(output, asset_dir=asset, odb_path=source, comparison_group=group.name,
                                    content_fingerprint=fingerprint, numeric_config_hash=config_hash)
        outputs.append(str(output))
    return dict(outputCount=len(outputs), outputs=outputs)


@contextmanager
def manager(source, runner):
    children = PostprocessOperationManager(EventStore(), run_runner=runner, settings_provider=_settings)
    queues = PostprocessGroupQueueManager(children, source.parent / "queues.sqlite3")
    try:
        yield queues
    finally:
        queues.close()
        children.close()


def until(queues, oid, predicate=lambda s: s["status"] in TERMINAL):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = queues.get(oid)
        if predicate(state):
            return state
        time.sleep(.01)
    pytest.fail(str(state))


def command(state, **extra):
    return dict(schemaVersion=1, clientRequestId=uuid4().hex, expectedVersion=state["version"], **extra)


def test_fifo_live_append_update_skip_and_stale_commands(source):
    waiting, release = threading.Event(), threading.Event()
    started = []

    def runner(plan, progress, log, controller):
        group = plan.groups[0]
        started.append((group.name, plan.jobs[source].load_direction))
        if group.name == "A":
            waiting.set()
            assert release.wait(8)
        return publish(plan)

    with manager(source, runner) as queues:
        payload = run(source, "A", "B", "C")
        oid = queues.create(payload)["operationId"]
        assert waiting.wait(5)
        state = queues.create(payload)
        assert state["currentGroupId"] == state["groups"][0]["groupId"]
        stale_clear = command(state)
        addition = command(state, run=run(source, "A", "D"))
        state = queues.command(oid, "append", addition)
        assert [g["name"] for g in state["groups"]] == ["A", "B", "C", "D"]
        replay = queues.command(oid, "append", addition)
        assert replay == state
        with pytest.raises(ApiProblem, match="已变化"):
            queues.command(oid, "clear-pending", stale_clear)
        update = run(source, "B")
        update["jobs"][0]["loadDirection"] = "3"
        state = queues.command(oid, "update-pending", command(state, run=update))
        assert state["groups"][1]["run"]["jobs"][0]["loadDirection"] == "3"
        with pytest.raises(ApiProblem):
            queues.command(oid, "update-pending", command(state, run=run(source, "A")))
        state = queues.command(oid, "skip-pending", command(state, expectedGroupId=state["groups"][2]["groupId"]))
        release.set()
        done = until(queues, oid)
        assert started == [("A", "1+3"), ("B", "3"), ("D", "1+3")]
        assert done["status"] == "partial"
        assert [g["status"] for g in done["groups"]] == ["succeeded", "succeeded", "skipped", "succeeded"]
        assert len(done["result"]["resultRoots"]) == 1 and done["result"]["outputCount"] == 3
        scopes = discover_result_scopes({"schemaVersion": 1, "root": done["result"]["resultRoots"][0]})["nodes"]
        assert {s["path"] for s in scopes if s["kind"] == "odb"} == set(done["result"]["outputs"])
        assert all(re.fullmatch(r"[0-9]{8}_[0-9]{6}_[0-9]{6}_[0-9a-f]{8}_01", s["name"])
                   for s in scopes if s["kind"] == "batch")
        assert queues.get_if_changed(oid, done["version"]) is None
        assert queues.get_if_changed(oid, done["version"] + 1) == done
        assert queues.command(oid, "append", addition) == done
        assert queues.create(payload) == done
        with pytest.raises(ApiProblem):
            queues.create(dict(payload, animationFps=12))


def test_cancel_current_waits_for_cleanup_and_failure_continues(source):
    started, unwinding, release = [], threading.Event(), threading.Event()

    def runner(plan, progress, log, controller):
        name = plan.groups[0].name
        started.append(name)
        if name == "A":
            deadline = time.monotonic() + 6
            while not controller.cancel_requested and time.monotonic() < deadline:
                time.sleep(.01)
            assert controller.cancel_requested
            unwinding.set()
            assert release.wait(5)
            raise ProcessCancelled("fixture")
        if name == "B":
            raise ValueError("isolated failure")
        return publish(plan)

    with manager(source, runner) as queues:
        oid = queues.create(run(source, "A", "B", "C"))["operationId"]
        state = until(queues, oid, lambda s: started and s["groups"][0]["childOperationId"])
        with pytest.raises(ApiProblem):
            queues.command(oid, "cancel-current", command(state, expectedGroupId=state["groups"][1]["groupId"]))
        state = queues.command(oid, "cancel-current", command(state, expectedGroupId=state["currentGroupId"]))
        assert unwinding.wait(5)
        assert started == ["A"] and queues.get(oid)["groups"][0]["status"] == "cancelling"
        release.set()
        done = until(queues, oid)
        assert [g["status"] for g in done["groups"]] == ["cancelled", "failed", "succeeded"]
        assert done["status"] == "partial" and done["result"]["outputCount"] == 1


def _interrupt_checkpoint(source, oid):
    # Rewind only the isolated journal to a durable crash boundary: A finishing, B not yet started.
    with sqlite3.connect(source.parent / "queues.sqlite3") as conn:
        query = "SELECT payload FROM postprocess_group_queues WHERE operation_id=?"
        record = json.loads(conn.execute(query, (oid,)).fetchone()[0])
        item = record["snapshot"]
        a, b = item["groups"]
        item.update(status="running", currentGroupId=a["groupId"])
        a.update(status="running", message="")
        b.update(status="queued", childOperationId="")
        for row in (item, a, b):
            row["result"] = {"outputCount": 0, "outputs": [], "resultRoots": []}
        conn.execute("UPDATE postprocess_group_queues SET payload=? WHERE operation_id=?", (json.dumps(record), oid))


@pytest.mark.parametrize("damage", ["none", "ack-intact", "missing-image", "empty-folder", "missing-csv", "external-asset", "changed-source"])
def test_cold_restart_verifies_original_outputs_and_never_resubmits_attempt(source, damage):
    started = []

    def runner(plan, *args):
        name = plan.groups[0].name
        started.append(name)
        if name == "B" and started == ["A", "B"]:
            raise ValueError("first B not published")
        return publish(plan)

    with manager(source, runner) as first:
        oid = first.create(run(source, "A", "B"))["operationId"]
        done = until(first, oid)
    member = Path(done["result"]["outputs"][0])
    manifest = member / GROUP_MEMBER_MANIFEST_NAME
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if damage == "missing-image":
        (member / "frames").rename(member / "removed-frames")
    elif damage == "empty-folder":
        (member / "frames" / "frame.png").rename(member / "missing.png")
    elif damage == "changed-source":
        source.write_bytes(b"different")
    elif damage == "missing-csv":
        asset = Path(data["shared_data_absolute_path"])
        (asset / "data" / "timeline_alignment.csv").rename(asset / "timeline-removed.csv")
    elif damage == "external-asset":
        wrong = source.parent / "external"
        wrong.mkdir()
        data.update(shared_data_relative_path="", shared_data_absolute_path=str(wrong))
        clear_windows_hidden(manifest)
        manifest.write_text(json.dumps(data), encoding="utf-8")
    _interrupt_checkpoint(source, oid)
    with manager(source, runner) as restored:
        state = restored.get(oid)
        assert not restored.list_snapshots(active_only=True)
        assert state["status"] == "suspended" and state["groups"][0]["status"] == "interrupted"
        assert state["groups"][1]["run"]["groups"][0]["name"] == "B"
        if damage in {"none", "ack-intact"}:
            if damage == "ack-intact":
                state = restored.command(oid, "acknowledge-interrupted", command(state, expectedGroupId=state["currentGroupId"]))
                assert state["groups"][0]["status"] == "succeeded" and not state["currentGroupId"]
            restored.command(oid, "resume", command(state))
            done = until(restored, oid)
            assert done["status"] == "succeeded" and done["result"]["outputCount"] == 2
            assert started == ["A", "B", "B"]
        else:
            for action in ("resume", "stop"):
                with pytest.raises(ApiProblem):
                    restored.command(oid, action, command(state))
            ack = command(state, expectedGroupId=state["currentGroupId"])
            state = restored.command(oid, "acknowledge-interrupted", ack)
            assert restored.command(oid, "acknowledge-interrupted", ack) == state
            assert not state["currentGroupId"] and state["groups"][0]["status"] == "interrupted"
            assert state["result"]["outputCount"] == 0
            done = restored.command(oid, "stop", command(state))
            assert done["status"] == "failed" and started == ["A", "B"]


def test_clear_pending_keeps_current_and_source_changes_fail_only_affected_group(source):
    hold, release = threading.Event(), threading.Event()
    started = []

    def runner(plan, *args):
        started.append(plan.groups[0].name)
        hold.set()
        assert release.wait(6)
        return publish(plan)

    other = source.with_name("changed.odb")
    other.write_bytes(b"before")
    payload = run(source, "A")
    pending = run(other, "B")
    payload["jobs"] += pending["jobs"]
    payload["groups"] += pending["groups"]
    with manager(source, runner) as queues:
        oid = queues.create(payload)["operationId"]
        assert hold.wait(5)
        other.write_bytes(b"after")
        release.set()
        done = until(queues, oid)
        assert started == ["A"] and done["status"] == "partial"
        assert "ODB" in done["groups"][1]["message"]
        hold.clear()
        release.clear()
        oid = queues.create(run(source, "kept", "removed"))["operationId"]
        assert hold.wait(5)
        state = queues.get(oid)
        state = queues.command(oid, "clear-pending", command(state))
        assert state["groups"][0]["status"] == "running" and state["groups"][1]["status"] == "cancelled"
        release.set()
        assert until(queues, oid)["status"] == "partial" and started == ["A", "kept"]


def test_validation_allows_concurrent_reads_and_commands_without_losing_append(source, monkeypatch):
    from modules.control_plane import postprocess_group_queue as backend

    entered, release = threading.Event(), threading.Event()
    original = backend._outputs_on_disk

    def gated(record, group):
        if group["name"] == "A":
            entered.set()
            assert release.wait(6)
        return original(record, group)

    monkeypatch.setattr(backend, "_outputs_on_disk", gated)
    with manager(source, lambda plan, *args: publish(plan)) as queues:
        oid = queues.create(run(source, "A"))["operationId"]
        assert entered.wait(5)
        try:
            current = queues.get(oid)
            assert current["status"] == "running"
            queued = queues.command(oid, "append", command(current, run=run(source, "B")))
            assert queued["groups"][1]["status"] == "queued"
        finally:
            release.set()
        done = until(queues, oid)
        assert done["status"] == "succeeded" and done["result"]["outputCount"] == 2


def test_unavailable_child_suspends_without_dispatching_another_group(source, monkeypatch):
    release = threading.Event()
    started = []

    def runner(plan, *args):
        started.append(plan.groups[0].name)
        assert release.wait(6)
        return publish(plan)

    with manager(source, runner) as queues:
        def unavailable(_):
            raise ApiProblem(404, "UNKNOWN_CHILD", "missing")

        monkeypatch.setattr(queues._children, "get", unavailable)
        oid = queues.create(run(source, "A", "B"))["operationId"]
        try:
            state = until(queues, oid, lambda s: s["status"] == "suspended")
            assert state["currentGroupId"] == state["groups"][0]["groupId"]
            assert [g["status"] for g in state["groups"]] == ["interrupted", "queued"]
            with pytest.raises(ApiProblem):
                queues.command(oid, "stop", command(state))
        finally:
            release.set()
        assert "B" not in started


def test_history_corruption_blocks_admission_and_idle_shutdown(source):
    journal = source.parent / "queues.sqlite3"
    journal.write_bytes(b"invalid sqlite journal")
    with manager(source, lambda *args: pytest.fail("No dispatch for unreadable history")) as queues:
        with pytest.raises(ApiProblem) as error:
            queues.create(run(source, "A"))
        assert error.value.status == 503
        shutdown = queues.prepare_shutdown()
        assert not shutdown["safeToStop"] and shutdown["operations"][0]["status"] == "unavailable"


def test_stopping_a_waiting_workspace_does_not_wait_for_another_workspace(source):
    entered, release = threading.Event(), threading.Event()
    started = []

    def runner(plan, *args):
        started.append(plan.groups[0].name)
        entered.set()
        assert release.wait(6)
        return publish(plan)

    other = source.parent / "other" / "other.odb"
    other.parent.mkdir()
    other.write_bytes(b"a separate workspace")
    with manager(source, runner) as queues:
        first = queues.create(run(source, "A"))
        assert entered.wait(5)
        try:
            second = queues.create(run(other, "B"))
            done = queues.command(second["operationId"], "stop", command(second))
            assert done["status"] == "cancelled" and not done["currentGroupId"]
        finally:
            release.set()
        assert until(queues, first["operationId"])["status"] == "succeeded"
        assert started == ["A"]


def test_partial_multi_member_result_retains_only_verified_outputs(source):
    other = source.parent / "nested" / "second.odb"
    other.parent.mkdir()
    other.write_bytes(b"second synthetic source")
    payload = run(source, "mixed")
    payload["jobs"] += run(other, "mixed")["jobs"]
    payload["groups"][0]["members"].append(str(other))

    def runner(plan, *args):
        publish(plan)
        other.write_bytes(b"changed during processing")
        raise ValueError("interrupted after publication")

    with manager(source, runner) as queues:
        oid = queues.create(payload)["operationId"]
        done = until(queues, oid)
        assert done["status"] == "partial" and done["groups"][0]["status"] == "failed"
        assert done["result"]["outputCount"] == 1
        assert Path(done["result"]["outputs"][0]).name == source.stem
        assert Path(done["result"]["resultRoots"][0]).parent == source.parent
