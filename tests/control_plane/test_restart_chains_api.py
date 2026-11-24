from __future__ import annotations

from pathlib import Path

from modules.common.json_io import save_json_mapping
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
        "validCount": 1,
    }
    assert payload["hasIssues"] is True
    graph_by_id = {node["jobId"]: node for node in payload["graphNodes"]}
    assert graph_by_id["base"]["isRestart"] is False
    assert graph_by_id["phase2"]["isRestart"] is True
    assert payload["nodeCount"] == len(by_id) == 4
    assert len(graph_by_id) == 5
    assert payload["graphNodeCount"] == len(payload["graphNodes"])
