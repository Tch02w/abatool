from __future__ import annotations

from pathlib import Path

import pytest

from modules.common.json_io import save_json_mapping
from modules.control_plane.restart_result_plans import build_restart_result_plan
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)


def _request(runtime, item_id: str, output_directory: Path):
    return api_request(
        runtime,
        "/api/v1/restart-result-plans",
        method="POST",
        payload={
            "schemaVersion": 1,
            "itemId": item_id,
            "outputDirectory": str(output_directory),
        },
    )


def test_restart_result_plan_materializes_only_the_selected_ancestry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    for name in ("base", "phase2", "phase3", "sibling"):
        (tmp_path / f"{name}.odb").write_bytes(name.encode())
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
                    "effective_work_dir": str(tmp_path),
                },
                {
                    "item_id": "item-phase2",
                    "job_id": "phase2",
                    "job_name": "phase2",
                    "run_mode": "restart",
                    "status": "已完成",
                    "oldjob_name": "base",
                    "oldjob_path": str(tmp_path / "base.odb"),
                    "effective_work_dir": str(tmp_path),
                    "dependency_job_ids": ["base"],
                },
                {
                    "item_id": "item-phase3",
                    "job_id": "phase3",
                    "job_name": "phase3",
                    "run_mode": "restart",
                    "status": "已完成",
                    "oldjob_name": "phase2",
                    "oldjob_path": str(tmp_path / "phase2.odb"),
                    "effective_work_dir": str(tmp_path),
                    "dependency_job_ids": ["phase2"],
                },
                {
                    "item_id": "item-sibling",
                    "job_id": "sibling",
                    "job_name": "sibling",
                    "run_mode": "restart",
                    "status": "已完成",
                    "oldjob_name": "base",
                    "oldjob_path": str(tmp_path / "base.odb"),
                    "effective_work_dir": str(tmp_path),
                    "dependency_job_ids": ["base"],
                },
            ]
        },
    )
    monkeypatch.setattr("modules.control_plane.job_queues.JOBLIST_PATH", joblist)

    with running_control_plane(tmp_path) as runtime:
        response = _request(runtime, "item-phase3", tmp_path)

    assert response[0] == 200
    payload = json_response(response)
    assert payload["valid"] is True
    assert payload["targetJobId"] == "phase3"
    assert [item["jobId"] for item in payload["ancestry"]] == [
        "base",
        "phase2",
        "phase3",
    ]
    assert len(payload["steps"]) == 2
    assert payload["steps"][0]["originalOdb"] == str(tmp_path / "base.odb")
    assert payload["steps"][0]["restartOdb"] == str(tmp_path / "phase2.odb")
    assert payload["steps"][1]["originalOdb"] == payload["steps"][0]["outputOdb"]
    assert payload["steps"][1]["restartOdb"] == str(tmp_path / "phase3.odb")
    assert "sibling" not in str(payload)
    assert payload["finalOutputOdb"].endswith("phase3_full_joined.odb")


def test_restart_result_plan_reports_missing_stage_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base = tmp_path / "base.odb"
    base.write_bytes(b"base")
    joblist = tmp_path / "joblist.json"
    save_json_mapping(
        joblist,
        {
            "queue_items": [
                {
                    "item_id": "base-item",
                    "job_id": "base",
                    "job_name": "base",
                    "status": "已完成",
                },
                {
                    "item_id": "restart-item",
                    "job_id": "restart",
                    "job_name": "restart",
                    "run_mode": "restart",
                    "status": "已完成",
                    "oldjob_name": "base",
                    "oldjob_path": str(base),
                    "effective_work_dir": str(tmp_path),
                    "dependency_job_ids": ["base"],
                },
            ]
        },
    )
    monkeypatch.setattr("modules.control_plane.job_queues.JOBLIST_PATH", joblist)

    with running_control_plane(tmp_path) as runtime:
        response = _request(runtime, "restart-item", tmp_path)

    payload = json_response(response)
    assert response[0] == 200
    assert payload["valid"] is False
    assert payload["steps"] == []
    assert any("restart.odb" in issue for issue in payload["issues"])


def test_restart_result_plan_rejects_unknown_fields(tmp_path: Path) -> None:
    with running_control_plane(tmp_path) as runtime:
        response = api_request(
            runtime,
            "/api/v1/restart-result-plans",
            method="POST",
            payload={"schemaVersion": 1, "itemId": "x", "future": True},
        )

    assert response[0] == 400
    assert json_response(response)["error"]["code"] == "UNKNOWN_FIELDS"


@pytest.mark.parametrize("dependencies", [["base", "other"], ["missing"], []])
def test_ambiguous_or_missing_parent_never_silently_selects_first(
    tmp_path, monkeypatch, dependencies
):
    (tmp_path / "base.odb").write_bytes(b"base")
    (tmp_path / "target.odb").write_bytes(b"target")
    items = [
        {"itemId": "one", "jobId": "base", "jobName": "base", "runMode": "normal"},
        {"itemId": "two", "jobId": "other", "jobName": "base", "runMode": "normal"},
        {
            "itemId": "target",
            "jobId": "target",
            "jobName": "target",
            "runMode": "restart",
            "dependencyJobIds": dependencies,
            "oldjobName": "base",
            "oldjobPath": str(tmp_path / "base.odb"),
            "effectiveWorkDir": str(tmp_path),
        },
    ]
    monkeypatch.setattr(
        "modules.control_plane.job_queues.read_job_queues",
        lambda: {"queueItems": items},
    )
    result = build_restart_result_plan(
        {"schemaVersion": 1, "itemId": "target", "outputDirectory": str(tmp_path)}
    )
    assert not result["valid"] and result["steps"] == [] and result["issues"]
