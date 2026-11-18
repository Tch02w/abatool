from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from modules.control_plane.job_notifications import JobNotificationManager
from modules.submitter.archive_notifications import ArchiveNoticeStore
from modules.submitter.local_archive_state import ArchiveStateStore
from modules.submitter.local_job_execution import LocalJobExecutionResult
from modules.submitter.queue_store import load_joblist_state, save_joblist_state
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_archive_recovery_api import interrupted_fixture
from tests.control_plane.test_local_queue_runtime_api import (
    runtime_control,
    runtime_snapshot,
    wait_until,
)


def test_archive_notice_recovers_missing_callback_after_queue_removal_and_stays_read(tmp_path, monkeypatch):
    _, original, _, joblist = interrupted_fixture(tmp_path, monkeypatch)
    candidates, items, _ = load_joblist_state(joblist, restore_active_state=False)
    items[0].complete_notify = True
    save_joblist_state(candidates, items, joblist)
    options = {"joblist_path": joblist, "server_profiles_path": tmp_path / "profiles.json",
               "odb_result_graph_path": tmp_path / "graph.json"}
    with running_control_plane(tmp_path, **options) as runtime:
        # Durable operation finishes, but the application completion callback is lost.
        monkeypatch.setattr(runtime.local_queue_runtime, "_completion_sink", None)
        assert runtime_control(runtime, "retryArchive", itemIds=[original.item_id])[0] == 202
        wait_until(lambda: runtime_snapshot(runtime)["queue"]["queueItems"][0]["archiveStatus"] == "已归档", timeout=15)
        wait_until(lambda: not any(o["active"] for o in runtime_snapshot(runtime)["operations"]), timeout=15)
        removed = api_request(runtime, "/api/v1/job-queue-commands", method="POST",
                              payload={"schemaVersion": 1, "action": "clearFinished"})
        assert removed[0] == 200 and not runtime_snapshot(runtime)["queue"]["queueItems"]
    with running_control_plane(tmp_path, **options) as runtime:
        result = json_response(api_request(runtime, "/api/v1/job-notifications"))
        assert result["unreadCount"] == 1
        notice = result["items"][0]
        assert notice["status"] == "succeeded" and notice["jobId"] == original.item_id
        assert notice["executionId"].startswith(original.attempt_id + ":archive:")
        assert "已归档" in notice["message"]
        ack = api_request(runtime, "/api/v1/job-notification-acknowledgements", method="POST",
                          payload={"schemaVersion": 1, "ids": [notice["id"]]})
        assert ack[0] == 200 and json_response(ack)["unreadCount"] == 0
    with running_control_plane(tmp_path, **options) as runtime:
        assert json_response(api_request(runtime, "/api/v1/job-notifications"))["unreadCount"] == 0


def notice_fixture(tmp_path):
    manager = JobNotificationManager(tmp_path / "notifications.sqlite3")
    archives = ArchiveStateStore(tmp_path / "archive-state")
    receipts = ArchiveNoticeStore(archives)
    item = SimpleNamespace(item_id="item", attempt_id="attempt", job_name="case", complete_notify=True,
                           calculation_root_dir="", effective_work_dir=str(tmp_path), inp_path=str(tmp_path / "case.inp"))
    return manager, archives, receipts, item


def test_live_owner_is_not_reported_interrupted_but_abandoned_operation_is(tmp_path):
    manager, archives, receipts, item = notice_fixture(tmp_path)
    try:
        with archives.claim(item):
            receipts.begin(item, uuid4().hex)
            assert not receipts.recover(manager.since, manager.publish)
            assert manager.snapshot()["unreadCount"] == 0
        assert not receipts.recover(manager.since, manager.publish)
        notice = manager.snapshot()["items"][0]
        assert notice["status"] == "failed" and "中断" in notice["message"]
        assert notice["workDirectory"] == str(tmp_path)
    finally:
        manager.close()


def test_cancel_opt_out_corrupt_receipt_and_unchanged_history_cache(tmp_path, monkeypatch):
    manager, archives, receipts, item = notice_fixture(tmp_path)
    try:
        item.complete_notify = False
        assert receipts.begin(item, uuid4().hex) is None
        assert not receipts.root.exists()
        item.complete_notify = True
        with archives.claim(item):
            receipt = receipts.begin(item, uuid4().hex)
            receipts.finish(receipt, "", "归档已取消", "user cancellation", True)
        assert not receipts.recover(manager.since, manager.publish)
        assert manager.snapshot()["items"][0]["status"] == "cancelled"
        monkeypatch.setattr(receipts, "_read", lambda *_: (_ for _ in ()).throw(AssertionError("Unchanged receipt reread")))
        assert not receipts.recover(manager.since, manager.publish)
        assert manager.snapshot()["unreadCount"] == 1
        monkeypatch.undo()
        corrupt = receipts.root / (uuid4().hex + ".json")
        corrupt.write_bytes(b"broken receipt")
        assert receipts.recover(manager.since, manager.publish)
        assert corrupt.read_bytes() == b"broken receipt"
        assert manager.snapshot()["unreadCount"] == 1
    finally:
        manager.close()


def test_corrupt_pending_receipt_is_preserved_when_worker_finishes(tmp_path):
    manager, archives, receipts, item = notice_fixture(tmp_path)
    try:
        with archives.claim(item):
            record = receipts.begin(item, uuid4().hex)
            path = receipts.root / (record["operationId"] + ".json")
            path.write_bytes(b"damaged pending receipt")
            with pytest.raises(ValueError):
                receipts.finish(record, "", "已归档", "")
            assert path.read_bytes() == b"damaged pending receipt"
    finally:
        manager.close()


def test_durable_archive_outcome_is_not_relabelled_by_later_metadata_failure(tmp_path):
    manager, archives, receipts, item = notice_fixture(tmp_path)
    try:
        with archives.claim(item):
            operation = uuid4().hex
            receipt = receipts.begin(item, operation)
            receipts.finish(receipt, str(tmp_path / "archive"), "已归档", "")
        record = SimpleNamespace(archive_only=True, attempt_id=item.attempt_id, archive_operation_id=operation,
                                 controller=SimpleNamespace(archive_notice=(receipts, receipt), cancel_requested=False))
        manager.local_finished(item, record, LocalJobExecutionResult("已完成", "metadata failed", str(tmp_path), "",
                               archive_status="归档待恢复", archive_error="queue state write failed"))
        assert manager.snapshot()["items"][0]["status"] == "succeeded"
        receipts.recover(manager.since, manager.publish)
        assert manager.snapshot()["unreadCount"] == 1
    finally:
        manager.close()
