"""Every queue consumer must use the queue owned by its backend instance."""
from __future__ import annotations

import hashlib

import pytest

from modules.common.json_io import save_json_mapping
from modules.control_plane.restart_result_plans import build_restart_result_plan
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_odb_result_batches import publish, wait


@pytest.fixture
def queues(tmp_path, monkeypatch):
    selected = tmp_path / "selected.json"
    foreign = tmp_path / "foreign.json"
    (tmp_path / "out").mkdir()
    for name in ("base", "restart"):
        (tmp_path / f"{name}.odb").write_bytes(name.encode())
    save_json_mapping(selected, {"queue_items": [
        {"item_id": "base", "job_id": "base", "job_name": "base", "status": "已完成",
         "effective_work_dir": str(tmp_path)},
        {"item_id": "restart", "job_id": "restart", "job_name": "restart", "status": "已完成",
         "run_mode": "restart", "oldjob_name": "base", "oldjob_path": str(tmp_path / "base.odb"),
         "dependency_job_ids": ["base"], "effective_work_dir": str(tmp_path)},
    ]})
    save_json_mapping(foreign, {"queue_items": [
        {"item_id": "foreign", "job_id": "foreign", "job_name": "foreign", "status": "已完成"},
    ]})
    for module in ("job_queue_commands", "job_queues", "resources"):
        monkeypatch.setattr(f"modules.control_plane.{module}.JOBLIST_PATH", foreign)
    before = hashlib.sha256(foreign.read_bytes()).hexdigest()
    yield selected
    assert hashlib.sha256(foreign.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("consumer", ["resources", "chains", "plan"])
def test_read_models_use_the_runtime_queue(tmp_path, queues, consumer):
    with running_control_plane(tmp_path, joblist_path=queues) as runtime:
        queue = json_response(api_request(runtime, "/api/v1/job-queues"))
        assert {item["jobId"] for item in queue["queueItems"]} == {"base", "restart"}
        if consumer == "resources":
            response = api_request(runtime, "/api/v1/local-resources")
            assert response[0] == 200
            assert json_response(response)["totalJobs"] == 2
        elif consumer == "chains":
            response = api_request(runtime, "/api/v1/restart-chains")
            assert response[0] == 200
            nodes = json_response(response)["nodes"]
            assert {item["jobId"] for item in nodes} == {"restart"}
            assert nodes[0]["validationStatus"] == "valid"
        else:
            response = api_request(runtime, "/api/v1/restart-result-plans", method="POST", payload={
                "schemaVersion": 1, "itemId": "restart", "outputDirectory": str(tmp_path / "out"),
            })
            assert response[0] == 200, response
            plan = json_response(response)
            assert plan["valid"] and len(plan["steps"]) == 1
            assert plan["steps"][0]["originalOdb"] == str(tmp_path / "base.odb")


def test_restart_batch_revalidates_against_the_runtime_queue(tmp_path, queues, monkeypatch):
    # Build the selected queue's preview independently, then restore the foreign default.
    with monkeypatch.context() as scoped:
        scoped.setattr("modules.control_plane.job_queues.JOBLIST_PATH", queues)
        plan = build_restart_result_plan({
            "schemaVersion": 1, "itemId": "restart", "outputDirectory": str(tmp_path / "out"),
        })
    assert plan["valid"], plan
    with running_control_plane(tmp_path, joblist_path=queues, odb_merge_runner=publish,
                               odb_merge_command_provider=lambda: "fixture") as runtime:
        response = api_request(runtime, "/api/v1/odb-result-batches", method="POST", payload={
            "schemaVersion": 1, "clientRequestId": "selected-queue-batch",
            "source": {"kind": "restart", "expectedPlan": plan},
            "options": {"includeHistory": True, "compressResult": False, "copyOriginal": False},
        })
        assert response[0] == 202, response
        result = wait(runtime.httpd.context.odb_result_batch_manager, json_response(response)["operationId"])
        assert result["status"] == "succeeded", result
        assert result["completedSteps"] == 1
        assert (tmp_path / "base.odb").read_bytes() == b"base"
        assert (tmp_path / "restart.odb").read_bytes() == b"restart"
