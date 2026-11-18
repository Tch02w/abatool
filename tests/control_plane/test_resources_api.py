from __future__ import annotations

from pathlib import Path

from modules.common.json_io import save_json_mapping
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)


def test_local_resource_endpoint_returns_real_bounded_metrics(
    tmp_path: Path,
) -> None:
    joblist = tmp_path / "joblist.json"
    with running_control_plane(tmp_path, joblist_path=joblist) as runtime:
        # Publish current states after startup recovery, just as the live queue does.
        save_json_mapping(joblist, {"queue_items": [
            {"job_name": "running-1", "status": "运行中"},
            {"job_name": "waiting-1", "status": "等待运行"},
        ]})
        response = api_request(runtime, "/api/v1/local-resources")

    assert response[0] == 200
    payload = json_response(response)
    assert payload["schemaVersion"] == 1
    assert payload["resourceId"] == "local"
    assert payload["status"] == "online"
    assert payload["logicalCpus"] >= 1
    assert 0 <= payload["busyCpus"] <= payload["logicalCpus"]
    assert 0 <= payload["cpuPercent"] <= 100
    assert 0 <= payload["memoryUsedBytes"] <= payload["memoryTotalBytes"]
    assert 0 <= payload["memoryPercent"] <= 100
    assert payload["activeJobs"] == ["running-1"]
    assert payload["runningJobs"] == 1
    assert payload["waitingJobs"] == 1
    assert payload["totalJobs"] == 2
    assert payload["abaqusCommand"]
    assert isinstance(payload["abaqusRelease"], str)
    assert isinstance(payload["abaqusAvailable"], bool)
