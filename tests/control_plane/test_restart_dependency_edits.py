from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from modules.submitter.constants import (
    STATUS_FAILED,
    STATUS_PENDING_RUN,
    STATUS_RUNNING,
)
from modules.submitter.models import QueueItem
from modules.submitter.queue_store import save_joblist_state
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_job_queue_commands_api import command, post_command
from tests.control_plane.test_local_queue_runtime_api import runtime_control, wait_until


def job(root: Path, name: str, parent="") -> QueueItem:
    inp = root / f"{name}.inp"
    inp.write_text("*Heading\n" + ("*Restart, read\n" if parent else ""), encoding="ascii")
    return QueueItem(
        item_id=name,
        inp_path=str(inp),
        job_name=name,
        cores=1,
        held=True,
        run_mode="restart" if parent else "normal",
        status=STATUS_PENDING_RUN,
        oldjob_name=parent,
        oldjob_path=str(root / f"{parent}.odb") if parent else "",
    )


def test_invalid_edit_is_atomic_and_valid_future_parent_is_allowed(tmp_path):
    root = job(tmp_path, "root")
    child = job(tmp_path, "child", "root")
    leaf = job(tmp_path, "leaf", "child")
    state = tmp_path / "joblist.json"
    save_joblist_state([], [root, child, leaf], state)
    with running_control_plane(tmp_path) as runtime:
        before = state.read_bytes()
        for name in ("child.odb", "leaf.odb", "unknown.odb", "root.txt"):
            if name != "unknown.odb":
                (tmp_path / name).write_bytes(b"test only")
            invalid = post_command(
                runtime, command("updateQueueItem", itemId="child", oldjobPath=str(tmp_path / name), cores=2)
            )
            assert invalid[0] == 409
            assert json_response(invalid)["error"]["code"] == "INVALID_RESTART_DEPENDENCY"
            assert state.read_bytes() == before
        assert not (tmp_path / "root.odb").exists()
        result = post_command(
            runtime, command("updateQueueItem", itemId="leaf", oldjobPath=str(tmp_path / "root.odb"))
        )
        assert result[0] == 200
        graph = json_response(api_request(runtime, "/api/v1/restart-chains"))
        assert not graph["hasIssues"]
        assert {n["jobId"]: n["parentJobId"] for n in graph["nodes"]} == {"child": "root", "leaf": "root"}


def test_legacy_invalid_edit_can_be_repaired_without_requeuing_or_changing_settings(tmp_path):
    root = job(tmp_path, "root")
    child = job(tmp_path, "child", "child")
    child.status, child.valid, child.message = STATUS_FAILED, False, "Restart 依赖作业名无效"
    child.scheduler_state = "PENDING"
    child.resolved_oldjob_arg = "stale-oldjob"
    child.dependency_job_ids = [child.job_id]
    state = tmp_path / "joblist.json"
    save_joblist_state([], [root, child], state)
    with running_control_plane(tmp_path) as runtime:
        before = state.read_bytes()
        new_path = str(tmp_path / "root.odb")
        retry = post_command(runtime, command("requeueQueueItems", itemIds=["child"]))
        assert retry[0] == 409 and json_response(retry)["error"]["code"] == "INVALID_RESTART_DEPENDENCY"
        assert state.read_bytes() == before
        mixed = post_command(
            runtime, command("updateQueueItem", itemId="child", oldjobPath=new_path, cores=3)
        )
        assert mixed[0] == 409 and state.read_bytes() == before
        invalid = post_command(
            runtime, command("updateQueueItem", itemId="child", oldjobPath=str(tmp_path / "none.odb"))
        )
        assert invalid[0] == 409 and state.read_bytes() == before
        result = post_command(runtime, command("updateQueueItem", itemId="child", oldjobPath=new_path))
        assert result[0] == 200
        item = json_response(result)["snapshot"]["queueItems"][1]
        assert item["status"] == STATUS_PENDING_RUN and item["held"] and item["valid"] and item["cores"] == 1
        graph = json_response(api_request(runtime, "/api/v1/restart-chains"))
        assert graph["checks"]["cycleCount"] == 0 and graph["nodes"][0]["parentJobId"] == "root"
        assert b"stale-oldjob" not in state.read_bytes()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("attempt_id", "already-ran"),
        ("elapsed", "00:12:00"),
        ("is_external", True),
        ("status", STATUS_RUNNING),
        ("message", "Abaqus exited with code 1"),
        ("valid", True),
    ],
)
def test_real_runtime_and_external_records_are_protected(tmp_path, field, value):
    root, child = job(tmp_path, "root"), job(tmp_path, "child", "child")
    child.status, child.valid, child.message = STATUS_FAILED, False, "Restart 依赖作业名无效"
    setattr(child, field, value)
    state = tmp_path / "joblist.json"
    save_joblist_state([], [root, child], state)
    with running_control_plane(tmp_path) as runtime:
        before = state.read_bytes()
        response = post_command(
            runtime, command("updateQueueItem", itemId="child", oldjobPath=str(tmp_path / "root.odb"))
        )
        assert response[0] == 409 and json_response(response)["error"]["code"] == "QUEUE_ITEM_NOT_EDITABLE"
        assert state.read_bytes() == before


def test_candidate_admission_and_draft_detect_cycles_before_queue_write(tmp_path):
    child = job(tmp_path, "child", "future")
    future = job(tmp_path, "future", "child")
    (tmp_path / "child.odb").write_bytes(b"synthetic")
    state = tmp_path / "joblist.json"
    save_joblist_state([future], [child], state)
    with running_control_plane(tmp_path) as runtime:
        before = state.read_bytes()
        result = post_command(runtime, command("confirmCandidates", itemIds=["future"]))
        assert result[0] == 409 and state.read_bytes() == before
        assert json_response(result)["error"]["code"] == "INVALID_RESTART_DEPENDENCY"
        assert post_command(runtime, command("removeCandidates", itemIds=["future"]))[0] == 200
        before = state.read_bytes()
        draft = {
            "schemaVersion": 1,
            "inpFile": future.inp_path,
            "jobName": "future",
            "oldjobPath": str(tmp_path / "child.odb"),
            "cpus": 1,
            "memoryValue": "80",
            "memoryUnit": "%",
            "priority": 0,
            "maxParallel": 1,
        }
        result = post_command(runtime, command("enqueueDraft", draft=draft))
        assert result[0] == 409 and json_response(result)["error"]["code"] == "INVALID_RESTART_DEPENDENCY"
        assert state.read_bytes() == before


def test_active_scheduler_protects_the_dependency_until_it_is_stopped(tmp_path):
    parent, child = job(tmp_path, "parent"), job(tmp_path, "child", "parent")
    child.held = False
    external = tmp_path / "external.odb"
    external.write_bytes(b"synthetic")
    save_joblist_state([], [parent, child], tmp_path / "joblist.json")
    runner = Mock()
    with running_control_plane(tmp_path, local_job_runner=runner) as runtime:
        # The parent is held. Its child cannot dispatch or launch a solver.
        assert runtime_control(runtime, "start")[0] == 202
        request = command("updateQueueItem", itemId="child", oldjobPath=str(external))
        response = post_command(runtime, request)
        assert (
            response[0] == 409 and json_response(response)["error"]["code"] == "RESTART_EDIT_DURING_DISPATCH"
        )
        assert runtime_control(runtime, "stop")[0] == 202
        # A dispatch pass already in flight must finish before a subsequent edit can succeed.
        wait_until(lambda: post_command(runtime, request)[0] == 200)
    runner.assert_not_called()


def test_existing_self_odb_cannot_dispatch_legacy_pending_cycle(tmp_path):
    child = job(tmp_path, "child", "child")
    child.held = False
    Path(child.oldjob_path).write_bytes(b"test only")
    save_joblist_state([], [child], tmp_path / "joblist.json")
    runner = Mock()
    with running_control_plane(tmp_path, local_job_runner=runner) as runtime:
        assert runtime_control(runtime, "start")[0] == 202
        wait_until(lambda: "循环" in json_response(api_request(runtime, "/api/v1/job-queues"))["queueItems"][0]["message"])
        assert runtime_control(runtime, "stop")[0] == 202
    runner.assert_not_called()


def test_duplicate_names_choose_the_matching_directory_in_both_graph_and_plan(tmp_path):
    for folder in ("one", "two"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "root.odb").write_bytes(b"synthetic")
    first, second = job(tmp_path / "one", "root"), job(tmp_path / "two", "root")
    first.item_id = first.job_id = "first"
    second.item_id = second.job_id = "second"
    child = job(tmp_path, "child", "root")
    child.oldjob_path = str(tmp_path / "one" / "root.odb")
    (tmp_path / "child.odb").write_bytes(b"synthetic")
    save_joblist_state([], [first, second, child], tmp_path / "joblist.json")
    with running_control_plane(tmp_path) as runtime:
        assert (
            post_command(
                runtime,
                command("updateQueueItem", itemId="child", oldjobPath=str(tmp_path / "two" / "root.odb")),
            )[0]
            == 200
        )
        graph = json_response(api_request(runtime, "/api/v1/restart-chains"))
        assert graph["nodes"][0]["parentJobId"] == "second"
        result = api_request(
            runtime,
            "/api/v1/restart-result-plans",
            method="POST",
            payload={"schemaVersion": 1, "itemId": "child", "outputDirectory": str(tmp_path)},
        )
        assert result[0] == 200 and json_response(result)["valid"]


@pytest.mark.parametrize(("old_id", "issue"), [("wrong", "incompatible_path"), ("removed", "missing_parent")])
def test_legacy_parent_id_conflict_can_be_repaired_by_reselecting_the_exact_path(tmp_path, old_id, issue):
    first = job(tmp_path, "root")
    other = tmp_path / "other"
    other.mkdir()
    wrong = job(other, "root")
    wrong.item_id = wrong.job_id = "wrong"
    child = job(tmp_path, "child", "root")
    child.dependency_job_ids = [old_id]
    (tmp_path / "root.odb").write_bytes(b"synthetic")
    (tmp_path / "child.odb").write_bytes(b"synthetic")
    save_joblist_state([], [first, wrong, child], tmp_path / "joblist.json")
    with running_control_plane(tmp_path) as runtime:
        graph = json_response(api_request(runtime, "/api/v1/restart-chains"))
        assert graph["nodes"][0]["validationStatus"] == issue
        plan_request = {"schemaVersion": 1, "itemId": "child", "outputDirectory": str(tmp_path)}
        plan = json_response(
            api_request(runtime, "/api/v1/restart-result-plans", method="POST", payload=plan_request)
        )
        assert not plan["valid"]
        result = post_command(
            runtime, command("updateQueueItem", itemId="child", oldjobPath=child.oldjob_path)
        )
        assert result[0] == 200
        graph = json_response(api_request(runtime, "/api/v1/restart-chains"))
        assert not graph["hasIssues"] and graph["nodes"][0]["parentJobId"] == first.job_id
        plan = json_response(
            api_request(runtime, "/api/v1/restart-result-plans", method="POST", payload=plan_request)
        )
        assert plan["valid"]
