from __future__ import annotations

from pathlib import Path

from modules.submitter.constants import STATUS_PENDING_RUN, STATUS_RUNNING
from modules.submitter.models import QueueItem
from modules.submitter.queue_store import load_joblist_state, save_joblist_state
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)


def command(action: str, **fields: object) -> dict[str, object]:
    return {"schemaVersion": 1, "action": action, **fields}


def post_command(runtime, payload: dict[str, object]):
    return api_request(
        runtime,
        "/api/v1/job-queue-commands",
        method="POST",
        payload=payload,
    )


def test_add_select_and_confirm_candidates_are_persisted_atomically(
    tmp_path: Path,
) -> None:
    joblist = tmp_path / "runtime" / "joblist.json"
    first = tmp_path / "phase1.inp"
    second = tmp_path / "phase2.inp"
    first.write_text("*Heading\n", encoding="utf-8")
    second.write_text("*Heading\n", encoding="utf-8")

    with running_control_plane(tmp_path, joblist_path=joblist) as runtime:
        added = post_command(
            runtime,
            command(
                "addCandidates",
                paths=[str(first), str(second), str(first)],
                source="文件",
                skipRestartNames=False,
                skipExistingResults=False,
            ),
        )
        assert added[0] == 200
        added_payload = json_response(added)
        assert added_payload["changed"] == 2
        assert added_payload["stats"]["duplicate"] == 1
        candidate_ids = [
            item["itemId"] for item in added_payload["snapshot"]["candidates"]
        ]

        deselected = post_command(
            runtime,
            command(
                "setCandidateSelection",
                itemIds=[candidate_ids[1]],
                selected=False,
            ),
        )
        assert json_response(deselected)["changed"] == 1
        confirmed = post_command(
            runtime,
            command("confirmCandidates", itemIds=[candidate_ids[0]]),
        )
        confirmed_payload = json_response(confirmed)
        assert confirmed_payload["snapshot"]["candidateCount"] == 1
        assert confirmed_payload["snapshot"]["queueCount"] == 1
        assert confirmed_payload["snapshot"]["queueItems"][0]["status"] == STATUS_PENDING_RUN

    candidates, queue_items, error = load_joblist_state(
        joblist,
        restore_active_state=False,
    )
    assert error == ""
    assert [item.job_name for item in candidates] == ["phase2"]
    assert [item.job_name for item in queue_items] == ["phase1"]


def test_folder_scan_filters_restart_names_and_existing_results(tmp_path: Path) -> None:
    joblist = tmp_path / "joblist.json"
    root = tmp_path / "inputs"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (root / "normal.inp").write_text("*Heading\n", encoding="utf-8")
    (root / "normal.odb").write_text("result", encoding="utf-8")
    (root / "restart_case.inp").write_text("*Heading\n", encoding="utf-8")
    (nested / "kept.inp").write_text("*Heading\n", encoding="utf-8")

    with running_control_plane(tmp_path, joblist_path=joblist) as runtime:
        response = post_command(
            runtime,
            command(
                "scanCandidates",
                root=str(root),
                recursive=True,
                skipRestartNames=True,
                skipExistingResults=True,
            ),
        )

    payload = json_response(response)
    assert payload["changed"] == 1
    assert payload["stats"]["restartName"] == 1
    assert payload["stats"]["existingResult"] == 1
    assert payload["snapshot"]["candidates"][0]["jobName"] == "kept"


def test_enqueue_draft_update_hold_move_and_remove(tmp_path: Path) -> None:
    joblist = tmp_path / "joblist.json"
    first = tmp_path / "one.inp"
    second = tmp_path / "two.inp"
    first.write_text("*Heading\n", encoding="utf-8")
    second.write_text("*Heading\n", encoding="utf-8")

    def draft(path: Path) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "inpFile": str(path),
            "jobName": path.stem,
            "cpus": 4,
            "memoryValue": "80",
            "memoryUnit": "%",
            "priority": 0,
            "maxParallel": 1,
        }

    with running_control_plane(tmp_path, joblist_path=joblist) as runtime:
        first_payload = json_response(
            post_command(runtime, command("enqueueDraft", draft=draft(first)))
        )
        second_payload = json_response(
            post_command(runtime, command("enqueueDraft", draft=draft(second)))
        )
        first_id = first_payload["stats"]["itemId"]
        second_id = second_payload["stats"]["itemId"]

        edited = post_command(
            runtime,
            command(
                "updateQueueItem",
                itemId=first_id,
                cores=12,
                memory="24gb",
                priority=10,
            ),
        )
        assert json_response(edited)["snapshot"]["queueItems"][0]["cores"] == 12
        held = post_command(
            runtime,
            command("setQueueHold", itemIds=[first_id], held=True),
        )
        assert json_response(held)["snapshot"]["queueItems"][0]["held"] is True
        moved = post_command(
            runtime,
            command("moveQueueItem", itemId=second_id, direction="up"),
        )
        assert json_response(moved)["snapshot"]["queueItems"][0]["itemId"] == second_id
        removed = post_command(
            runtime,
            command("removeQueueItems", itemIds=[second_id]),
        )
        assert json_response(removed)["snapshot"]["queueCount"] == 1


def test_running_items_are_protected_and_corrupt_state_is_not_overwritten(
    tmp_path: Path,
) -> None:
    joblist = tmp_path / "joblist.json"
    running = QueueItem(
        inp_path=str(tmp_path / "running.inp"),
        job_name="running",
        status=STATUS_RUNNING,
    )
    save_joblist_state([], [running], joblist)

    with running_control_plane(tmp_path, joblist_path=joblist) as runtime:
        protected = post_command(
            runtime,
            command("removeQueueItems", itemIds=[running.item_id]),
        )
        assert protected[0] == 409
        assert json_response(protected)["error"]["code"] == "ACTIVE_QUEUE_ITEMS_PROTECTED"

    joblist.write_text("{broken", encoding="utf-8")
    with running_control_plane(tmp_path, joblist_path=joblist) as runtime:
        refused = post_command(runtime, command("clearFinished"))
        assert refused[0] == 500
        assert json_response(refused)["error"]["code"] == "JOB_QUEUE_STATE_UNREADABLE"
    assert joblist.read_text(encoding="utf-8") == "{broken"
