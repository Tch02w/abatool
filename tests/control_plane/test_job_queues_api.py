from __future__ import annotations

from pathlib import Path

from modules.common.json_io import save_json_mapping
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)


def test_job_queue_read_model_projects_candidates_dependencies_and_runtime(
    tmp_path: Path,
) -> None:
    joblist = tmp_path / "joblist.json"
    save_json_mapping(
        joblist,
        {
            "candidates": [
                {
                    "item_id": "candidate-1",
                    "inp_path": str(tmp_path / "phase1.inp"),
                    "job_name": "phase1",
                    "source": "文件",
                    "selected": True,
                    "valid": False,
                    "message": "INP 检查失败",
                }
            ],
            "queue_items": [
                {
                    "item_id": "queue-1",
                    "job_id": "job-1",
                    "inp_path": str(tmp_path / "phase2.inp"),
                    "job_name": "phase2",
                    "run_mode": "restart",
                    "oldjob_path": str(tmp_path / "phase1.odb"),
                    "fortran_path": str(tmp_path / "umat.for"),
                    "cores": 12,
                    "memory": "24gb",
                    "rss_bytes": 2147483648,
                    "priority": 10,
                    "held": True,
                    "scheduler_state": "QUEUED",
                    "status": "待运行",
                    "message": "等待资源",
                    "dependency_job_ids": ["phase1-id"],
                }
            ],
        },
    )
    with running_control_plane(tmp_path, joblist_path=joblist) as runtime:
        response = api_request(runtime, "/api/v1/job-queues")

    assert response[0] == 200
    payload = json_response(response)
    assert payload["candidateCount"] == 1
    assert payload["selectedCandidateCount"] == 1
    assert payload["invalidCandidateCount"] == 1
    assert payload["queueCount"] == 1
    assert payload["statusCounts"] == {"待运行": 1}
    candidate = payload["candidates"][0]
    assert candidate["valid"] is False
    assert candidate["message"] == "INP 检查失败"
    item = payload["queueItems"][0]
    assert item["jobId"] == "job-1"
    assert item["jobType"] == "重启动"
    assert item["oldjobName"] == "phase1"
    assert item["cores"] == 12
    assert item["runtimeMemoryBytes"] == 2147483648
    assert item["held"] is True
    assert item["dependencyJobIds"] == ["phase1-id"]
