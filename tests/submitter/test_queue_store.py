from __future__ import annotations

import json
from pathlib import Path

from modules.submitter.constants import STATUS_RUNNING, STATUS_UNKNOWN
from modules.submitter.models import QueueItem
from modules.submitter.queue_store import load_joblist_state, save_joblist_state


def test_queue_store_round_trip_preserves_candidate_and_formal_fields(tmp_path: Path) -> None:
    path = tmp_path / "state" / "joblist.json"
    candidate = QueueItem(inp_path="candidate.inp", job_name="candidate", selected=False)
    formal = QueueItem(
        inp_path="formal.inp",
        job_name="formal",
        cores=12,
        memory="24gb",
        dependency_job_ids=[candidate.job_id],
    )

    save_joblist_state([candidate], [formal], path)
    candidates, queue_items, error = load_joblist_state(
        path,
        restore_active_state=False,
    )

    assert error == ""
    assert candidates == [candidate]
    assert queue_items == [formal]
    assert not list(path.parent.glob("*.tmp"))


def test_queue_store_restores_active_state_as_unknown_without_rewriting_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "joblist.json"
    running = QueueItem(
        inp_path="running.inp",
        job_name="running",
        status=STATUS_RUNNING,
        active_job_key="runtime-1",
        pids=[123],
        pid_create_times={123: 4.5},
        rss_bytes=2048,
    )
    save_joblist_state([], [running], path)
    before = path.read_bytes()

    _, queue_items, error = load_joblist_state(path)

    assert error == ""
    assert queue_items[0].status == STATUS_UNKNOWN
    assert queue_items[0].active_job_key == ""
    assert queue_items[0].pids == []
    assert queue_items[0].rss_bytes == 0
    assert path.read_bytes() == before


def test_queue_store_reports_corrupt_json_and_leaves_it_untouched(tmp_path: Path) -> None:
    path = tmp_path / "joblist.json"
    path.write_text("{broken", encoding="utf-8")

    candidates, queue_items, error = load_joblist_state(path)

    assert candidates == []
    assert queue_items == []
    assert error
    assert path.read_text(encoding="utf-8") == "{broken"


def test_queue_store_ignores_unknown_fields_for_forward_compatibility(tmp_path: Path) -> None:
    path = tmp_path / "joblist.json"
    path.write_text(
        json.dumps(
            {
                "candidates": [
                    {"item_id": "one", "job_name": "case", "future_field": True}
                ],
                "queue_items": [],
            }
        ),
        encoding="utf-8",
    )

    candidates, _, error = load_joblist_state(path)

    assert error == ""
    assert candidates[0].item_id == "one"
    assert candidates[0].job_name == "case"
