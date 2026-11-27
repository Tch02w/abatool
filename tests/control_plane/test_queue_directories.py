from pathlib import Path

import pytest

from modules.control_plane.contracts import ApiProblem
from modules.control_plane.job_queue_commands import JobQueueService
from modules.submitter.constants import (
    STATUS_COMPLETED,
    STATUS_PENDING_RUN,
    STATUS_RUNNING,
)
from modules.submitter.models import QueueItem
from modules.submitter.queue_store import load_joblist_state, save_joblist_state


@pytest.fixture
def service(tmp_path):
    service = JobQueueService(tmp_path / "queue.json", external_monitor_interval=120)
    try:
        yield service
    finally:
        service.close()


def edit(service, action, **fields):
    return service.execute({"schemaVersion": 1, "action": action, **fields})


def job(tmp_path, folder, name, **kwargs):
    directory = tmp_path / folder
    directory.mkdir(exist_ok=True)
    source = directory / f"{name}.inp"
    source.write_text("*Heading\n", encoding="ascii")
    return QueueItem(inp_path=str(source), source_inp_path=str(source), job_name=name, **kwargs)


def test_selective_batch_preserves_invalid_candidate_and_untouched_row(tmp_path, service):
    root, archive = tmp_path / "ssd", tmp_path / "saved"
    root.mkdir()
    archive.mkdir()
    a = job(tmp_path, "sourceA", "A", selected=False)
    b = job(tmp_path, "sourceB", "B", fortran_path=str(tmp_path / "missing.for"))
    untouched = job(tmp_path, "sourceC", "C")
    save_joblist_state([a, b, untouched], [], service.path)
    fields = {"itemIds": [a.item_id, b.item_id], "calculationRootDir": str(root), "archiveDir": str(archive)}
    response = edit(service, "setCandidateDirectories", **fields)
    assert response["changed"] == 2
    A, B, C = response["snapshot"]["candidates"]
    assert not A["selected"] and B["selected"]
    assert not B["valid"] and "FOR" in B["message"]
    assert not C["calculationRootDir"] and not C["archiveDir"]
    for row in (A, B):
        assert row["calculationRootDir"] == str(root) and row["archiveDir"] == str(archive)
        assert row["archiveAfterComplete"] and not row["cleanupAfterArchive"]
        assert Path(row["effectiveWorkDir"]) == root / row["jobName"]
    snapshot = service.path.read_bytes()
    assert edit(service, "setCandidateDirectories", **fields)["changed"] == 0
    assert service.path.read_bytes() == snapshot
    edit(service, "setCandidateDirectories", itemIds=[a.item_id], cleanupAfterArchive=True)
    edit(service, "setCandidateDirectories", itemIds=[a.item_id, b.item_id], archiveDir="")
    saved = load_joblist_state(service.path)[0]
    assert saved[2] == untouched
    for row in saved[:2]:
        assert not (row.archive_dir or row.archive_after_complete or row.cleanup_after_archive)
        assert row.calculation_root_dir == str(root)
    assert not list(root.iterdir()) and not list(archive.iterdir())


@pytest.mark.parametrize("other_kind", ["selected", "unselected", "queue", "terminal"])
def test_batch_checks_final_locations_against_live_rows(tmp_path, service, other_kind):
    root = tmp_path / "ssd"
    root.mkdir()
    a = job(tmp_path, "first", "Same")
    b = job(tmp_path, "second", "SAME", calculation_root_dir=str(root))
    active = other_kind in {"queue", "terminal"}
    b.status = STATUS_COMPLETED if other_kind == "terminal" else STATUS_PENDING_RUN
    selected = [a.item_id, b.item_id] if other_kind == "selected" else [a.item_id]
    if other_kind == "selected":
        b.calculation_root_dir = ""
    save_joblist_state([a] if active else [a, b], [b] if active else [], service.path)
    snapshot = service.path.read_bytes()
    if other_kind == "terminal":
        assert edit(service, "setCandidateDirectories", itemIds=selected, calculationRootDir=str(root))["changed"] == 1
    else:
        with pytest.raises(ApiProblem, match="同名作业") as rejected:
            edit(service, "setCandidateDirectories", itemIds=selected, calculationRootDir=str(root))
        assert rejected.value.code == "QUEUE_DIRECTORY_CONFLICT" and service.path.read_bytes() == snapshot


def test_batch_rejects_stale_selection_invalid_path_and_unsafe_cleanup_atomically(tmp_path, service):
    a = job(tmp_path, "source", "A")
    b = job(tmp_path, "B", "B")
    archive = tmp_path / "archive"
    archive.mkdir()
    save_joblist_state([a, b], [], service.path)
    snapshot = service.path.read_bytes()
    # B's original source already lies in <root>/B.
    for fields, code in [
        ({"itemIds": [a.item_id, "vanished"], "archiveDir": str(archive)}, "QUEUE_ITEM_NOT_FOUND"),
        ({"itemIds": [a.item_id, ""], "archiveDir": str(archive)}, "INVALID_QUEUE_COMMAND_FIELD"),
        ({"itemIds": []}, "EMPTY_QUEUE_COMMAND_SELECTION"),
        ({"itemIds": [a.item_id]}, "EMPTY_DIRECTORY_EDIT"),
        ({"itemIds": [a.item_id], "calculationRootDir": a.inp_path}, "INVALID_QUEUE_DIRECTORY"),
        ({"itemIds": [a.item_id], "archiveDir": "."}, "INVALID_QUEUE_DIRECTORY"),
        ({"itemIds": [a.item_id], "archiveDir": str(tmp_path / "missing")}, "INVALID_QUEUE_DIRECTORY"),
        ({"itemIds": [a.item_id], "archiveDir": str(Path(a.inp_path).parent)}, "INVALID_QUEUE_DIRECTORY"),
        ({"itemIds": [a.item_id], "cleanupAfterArchive": True}, "INVALID_QUEUE_CLEANUP"),
        ({"itemIds": [a.item_id], "cleanupAfterArchive": "true"}, "INVALID_QUEUE_COMMAND_FIELD"),
        ({"itemIds": [a.item_id, b.item_id], "calculationRootDir": str(tmp_path),
              "archiveDir": str(archive), "cleanupAfterArchive": True}, "INVALID_QUEUE_CLEANUP"),
    ]:
        with pytest.raises(ApiProblem) as rejected:
            edit(service, "setCandidateDirectories", **fields)
        assert rejected.value.code == code
        assert service.path.read_bytes() == snapshot


@pytest.mark.parametrize("candidate", [True, False])
def test_single_edit_preserves_historical_options_and_recomputes_changed_locations(tmp_path, service, candidate):
    root, second_root, archive = (tmp_path / name for name in ("root", "second", "saved"))
    for directory in (root, second_root, archive):
        directory.mkdir()
    a = job(tmp_path, "source", "A", calculation_root_dir=str(root), archive_dir=str(archive),
            effective_work_dir=str(root / "A"), archive_after_complete=False,
            archive_destination=str(archive / "prior-A"), status=STATUS_PENDING_RUN)
    save_joblist_state([a] if candidate else [], [] if candidate else [a], service.path)
    action = "updateCandidate" if candidate else "updateQueueItem"
    collection = "candidates" if candidate else "queueItems"

    def update(**fields):
        return edit(service, action, itemId=a.item_id, **fields)["snapshot"][collection][0]

    untouched = update(priority=1, archiveDir=str(archive))
    assert not untouched["archiveAfterComplete"] and not untouched["cleanupAfterArchive"]
    assert untouched["archiveDestination"] == str(archive / "prior-A")
    with pytest.raises(ApiProblem) as disabled:
        update(cleanupAfterArchive=True)
    assert disabled.value.code == "INVALID_QUEUE_CLEANUP"
    update(archiveDir="")
    enabled = update(archiveDir=str(archive), calculationRootDir=str(second_root))
    assert enabled["archiveAfterComplete"] and not enabled["cleanupAfterArchive"]
    assert Path(enabled["effectiveWorkDir"]) == second_root / "A"
    assert update(cleanupAfterArchive=True)["cleanupAfterArchive"]
    assert update(priority=2)["cleanupAfterArchive"]
    assert Path(update(jobName="Renamed")["effectiveWorkDir"]) == second_root / "Renamed"
    cleared = update(calculationRootDir="")
    assert cleared["archiveAfterComplete"] and not cleared["cleanupAfterArchive"]
    assert Path(cleared["effectiveWorkDir"]) == Path(a.inp_path).parent
    assert load_joblist_state(service.path)[0 if candidate else 1][0].archive_destination == a.archive_destination


def test_running_queue_item_protected_from_directory_edits(tmp_path, service):
    a = job(tmp_path, "source", "A", status=STATUS_RUNNING)
    save_joblist_state([], [a], service.path)
    before = service.path.read_bytes()
    with pytest.raises(ApiProblem) as rejected:
        edit(service, "updateQueueItem", itemId=a.item_id, calculationRootDir=str(tmp_path))
    assert rejected.value.code == "QUEUE_ITEM_NOT_EDITABLE" and before == service.path.read_bytes()


def test_partial_batch_preserves_unassigned_restart_and_blocks_cleanup_for_missing_root(tmp_path, service):
    root, archive = tmp_path / "ssd", tmp_path / "output"
    root.mkdir()
    archive.mkdir()
    a = job(tmp_path, "source", "Restart")
    Path(a.inp_path).write_text("*Heading\n*RESTART, READ\n", encoding="ascii")
    save_joblist_state([a], [], service.path)
    fields = {"itemIds": [a.item_id], "calculationRootDir": str(root), "archiveDir": str(archive)}
    row = edit(service, "setCandidateDirectories", **fields)["snapshot"]["candidates"][0]
    assert row["runMode"] == "restart" and not row["oldjobName"]
    with pytest.raises(ApiProblem) as unassigned:
        edit(service, "confirmCandidates", itemIds=[a.item_id])
    assert unassigned.value.code == "CANDIDATES_NOT_READY"
    archive.rmdir()
    before = service.path.read_bytes()
    with pytest.raises(ApiProblem) as missing:
        edit(service, "setCandidateDirectories", itemIds=[a.item_id], cleanupAfterArchive=True)
    assert missing.value.code == "INVALID_QUEUE_DIRECTORY" and service.path.read_bytes() == before


def test_enqueue_from_original_draft_keeps_existing_defaults_and_explicit_cleanup_override(tmp_path, service):
    source = job(tmp_path, "source", "Draft").inp_path
    root, archive = tmp_path / "ssd", tmp_path / "output"
    root.mkdir()
    archive.mkdir()
    draft = {"schemaVersion": 1, "inpFile": source, "jobName": "Draft", "cpus": 1, "memoryValue": "80", "memoryUnit": "%",
                 "priority": 0, "maxParallel": 1, "useSsdCalculation": True, "calculationRootDir": str(root), "archiveDir": str(archive)}
    row = edit(service, "enqueueDraft", draft=draft)["snapshot"]["queueItems"][0]
    assert row["archiveAfterComplete"] and row["cleanupAfterArchive"]
    edit(service, "updateQueueItem", itemId=row["itemId"], cleanupAfterArchive=False)
    assert not edit(service, "updateQueueItem", itemId=row["itemId"], cores=1)["snapshot"]["queueItems"][0]["cleanupAfterArchive"]
