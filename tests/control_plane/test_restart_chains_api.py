from __future__ import annotations

from pathlib import Path

from modules.common.json_io import save_json_mapping
from modules.control_plane.restart_chains import _resolve_paths, read_restart_chains
from modules.control_plane.restart_result_plans import build_restart_result_plan
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)


def test_restart_chain_endpoint_reports_valid_missing_and_cycle_nodes(
    tmp_path: Path,
) -> None:
    joblist = tmp_path / "joblist.json"
    save_json_mapping(
        joblist,
        {
            "queue_items": [
                {
                    "item_id": "item-base",
                    "job_id": "base",
                    "job_name": "base",
                    "status": "已完成",
                },
                {
                    "item_id": "item-phase2",
                    "job_id": "phase2",
                    "job_name": "phase2",
                    "run_mode": "restart",
                    "oldjob_name": "base",
                    "oldjob_path": str(tmp_path / "base.odb"),
                    "dependency_job_ids": ["base"],
                },
                {
                    "job_id": "missing",
                    "job_name": "missing",
                    "run_mode": "restart",
                    "oldjob_name": "unknown",
                    "oldjob_path": str(tmp_path / "unknown.txt"),
                },
                {
                    "job_id": "cycle-a",
                    "job_name": "cycle-a",
                    "run_mode": "restart",
                    "oldjob_name": "cycle-b",
                    "dependency_job_ids": ["cycle-b"],
                },
                {
                    "job_id": "cycle-b",
                    "job_name": "cycle-b",
                    "run_mode": "restart",
                    "oldjob_name": "cycle-a",
                    "dependency_job_ids": ["cycle-a"],
                },
            ]
        },
    )
    with running_control_plane(tmp_path, joblist_path=joblist) as runtime:
        response = api_request(runtime, "/api/v1/restart-chains")

    assert response[0] == 200
    payload = json_response(response)
    by_id = {node["jobId"]: node for node in payload["nodes"]}
    assert by_id["phase2"]["itemId"] == "item-phase2"
    assert by_id["phase2"]["validationStatus"] == "valid"
    assert by_id["phase2"]["stage"] == 2
    assert by_id["missing"]["validationStatus"] == "missing_parent"
    assert by_id["cycle-a"]["validationStatus"] == "cycle"
    assert by_id["cycle-b"]["validationStatus"] == "cycle"
    assert payload["checks"] == {
        "cycleCount": 2,
        "missingParentCount": 1,
        "incompatiblePathCount": 1,
        "upstreamInvalidCount": 0,
        "validCount": 1,
    }
    assert payload["hasIssues"] is True
    graph_by_id = {node["jobId"]: node for node in payload["graphNodes"]}
    assert graph_by_id["base"]["isRestart"] is False
    assert graph_by_id["phase2"]["isRestart"] is True
    assert payload["nodeCount"] == len(by_id) == 4
    assert len(graph_by_id) == 5
    assert payload["graphNodeCount"] == len(payload["graphNodes"])


def test_upstream_failures_follow_each_branch_without_hiding_the_direct_reason(tmp_path):
    root = tmp_path / "original"
    root.mkdir()
    later = tmp_path / "later"
    later.mkdir()

    def job(name, parent=None, path=None):
        row = {"item_id": name, "job_id": name, "job_name": name, "inp_path": str(root / f"{name}.inp")}
        if parent:
            row.update(run_mode="restart", dependency_job_ids=[parent], oldjob_name=parent,
                       oldjob_path=str(path or root / f"{parent}.odb"))
        return row

    jobs = [
        job("a"), job("middle", "a", later / "a.odb"), job("first", "middle"), job("second", "middle"),
        job("grandchild", "first"), job("sibling", "a"), job("missing", "absent"),
        job("under-missing", "missing"), job("cycle1", "cycle2"), job("cycle2", "cycle1"),
        job("under-cycle", "cycle2"), job("second-error", "middle", later / "middle.odb"),
        job("nearer", "second-error"),
    ]
    # A same-named existing ODB must not satisfy an explicit parent from another run.
    for name in ("a", "middle", "sibling"):
        (root / f"{name}.odb").touch()
    (later / "a.odb").touch()
    queue = tmp_path / "queue.json"
    save_json_mapping(queue, {"queue_items": list(reversed(jobs))})
    state = read_restart_chains(queue)
    nodes = {row["jobId"]: row for row in state["nodes"]}
    rendered = {row["jobId"]: row for row in state["graphNodes"]}
    assert {key: nodes[key]["validationStatus"] for key in ("middle", "second-error", "missing", "cycle1", "cycle2", "sibling")} == {
        "middle": "incompatible_path", "second-error": "incompatible_path", "missing": "missing_parent",
        "cycle1": "cycle", "cycle2": "cycle", "sibling": "valid",
    }
    for leaf, cause in (("first","middle"), ("second","middle"), ("grandchild","middle"),
                       ("under-missing","missing"), ("under-cycle","cycle2"), ("nearer","second-error")):
        row = nodes[leaf]
        assert row["validationStatus"] == rendered[leaf]["validationStatus"] == "upstream_invalid"
        assert cause in row["validationMessage"] and nodes[cause]["validationMessage"] in row["validationMessage"]
        plan = build_restart_result_plan({"schemaVersion": 1, "itemId": leaf}, joblist_path=queue)
        assert not plan["valid"] and not plan["steps"]
    assert nodes["grandchild"]["stage"] == 4
    assert nodes["under-cycle"]["stage"] == nodes["cycle1"]["stage"] == 0
    assert build_restart_result_plan({"schemaVersion": 1, "itemId": "sibling"}, joblist_path=queue)["valid"]
    assert state["checks"] == {"cycleCount": 2, "missingParentCount": 1, "incompatiblePathCount": 2,
                               "upstreamInvalidCount": 6, "validCount": 1}


def test_deep_restart_paths_are_iterative_and_each_parent_is_resolved_once():
    class CountedParents(dict):
        lookups = 0

        def get(self, *args):
            self.lookups += 1
            return super().get(*args)

    count = 4000
    parents = CountedParents((str(i), str(i - 1)) for i in range(1, count))
    ids = [str(i) for i in reversed(range(count))]
    paths = _resolve_paths(ids, parents, set(), {"20": ("missing_parent", "missing ancestor")})
    assert paths[str(count-1)] == (count, "20")
    assert paths["19"] == (20, "")
    assert parents.lookups == count
