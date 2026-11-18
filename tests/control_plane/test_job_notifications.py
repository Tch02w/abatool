from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from modules.control_plane.contracts import ApiProblem
from modules.control_plane.job_notifications import JobNotificationManager
from modules.submitter.constants import STATUS_COMPLETED, STATUS_UNKNOWN
from modules.submitter.local_job_execution import LocalJobExecutionResult
from modules.submitter.queue_store import save_joblist_state
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_local_queue_runtime_api import (
    queue_item,
    runtime_control,
    wait_until,
)
from tests.control_plane.test_remote_job_recovery import (
    RecoverableRemote,
    create,
    request_for,
    view,
    wait_for,
)
from tests.control_plane.test_remote_transfers_api import _connect


def unread(runtime):
    response = api_request(runtime, "/api/v1/job-notifications")
    assert response[0] == 200, response
    return json_response(response)


def publish(manager, attempt="one", **options):
    manager.publish(source="local", execution_id=attempt, job_id="item", job_name="case",
                    status="succeeded", **options)


def test_inbox_ack_survives_restart_and_replayed_completion(tmp_path):
    path = tmp_path / "notifications.sqlite3"
    manager = JobNotificationManager(path)
    publish(manager)
    first = manager.snapshot()["items"][0]
    publish(manager)
    assert manager.snapshot()["unreadCount"] == 1
    manager.acknowledge({"schemaVersion": 1, "ids": [first["id"]]})
    manager.close()
    manager = JobNotificationManager(path)
    try:
        publish(manager)
        assert manager.snapshot()["unreadCount"] == 0
        publish(manager, "new-attempt")
        assert manager.snapshot()["unreadCount"] == 1
    finally:
        manager.close()


def test_storage_failure_retains_unread_and_retries_without_false_ack(tmp_path, monkeypatch):
    manager = JobNotificationManager(tmp_path / "notifications.sqlite3")
    original = manager._journal.save
    try:
        def fail(record):
            raise sqlite3.OperationalError("disk unavailable")
        monkeypatch.setattr(manager._journal, "save", fail)
        publish(manager)
        snapshot = manager.snapshot()
        assert snapshot["persistenceWarning"] and snapshot["unreadCount"] == 1
        assert not manager.prepare_shutdown()["safeToStop"]
        with pytest.raises(ApiProblem, match="已读状态未保存"):
            manager.acknowledge({"schemaVersion": 1, "ids": [snapshot["items"][0]["id"]]})
        monkeypatch.setattr(manager._journal, "save", original)
        wait_until(lambda: manager.snapshot()["persistenceWarning"] is None)
        assert manager.snapshot()["unreadCount"] == 1
        assert manager.prepare_shutdown()["safeToStop"]
    finally:
        manager.close()


def test_unknown_outcome_and_opt_out_do_not_generate_completion(tmp_path):
    manager = JobNotificationManager(tmp_path / "notifications.sqlite3")
    item = queue_item(tmp_path, "case")
    record = SimpleNamespace(attempt_id="owned-attempt")
    try:
        item.complete_notify = True
        manager.local_finished(item, record, LocalJobExecutionResult(STATUS_UNKNOWN, "unknown", str(tmp_path), "test"))
        item.complete_notify = False
        manager.local_finished(item, record, LocalJobExecutionResult(STATUS_COMPLETED, "done", str(tmp_path), "test"))
        assert manager.snapshot()["unreadCount"] == 0
    finally:
        manager.close()


def test_corrupt_inbox_preserved_with_explicit_error_and_healthy_backend(tmp_path):
    folder = tmp_path / "runtime"
    folder.mkdir()
    journal = folder / "job-notifications.sqlite3"
    journal.write_bytes(b"corrupt fixture")
    with running_control_plane(tmp_path) as runtime:
        assert api_request(runtime, "/healthz")[0] == 200
        response = api_request(runtime, "/api/v1/job-notifications")
        assert response[0] == 503
        assert json_response(response)["error"]["code"] == "JOB_NOTIFICATION_HISTORY_UNAVAILABLE"
        assert journal.read_bytes() == b"corrupt fixture"


def test_local_completion_is_durable_before_ui_connects_and_ack_is_idempotent(tmp_path):
    path = tmp_path / "joblist.json"
    item = queue_item(tmp_path, "notify")
    item.complete_notify = True
    save_joblist_state([], [item], path)
    def runner(item, *_args):
        return LocalJobExecutionResult(STATUS_COMPLETED, "done", str(tmp_path), "fixture")
    options = {"joblist_path": path, "local_job_runner": runner}
    with running_control_plane(tmp_path, **options) as runtime:
        assert runtime_control(runtime, "start", maxParallel=1, existingResultPolicy="backup")[0] == 202
        wait_until(lambda: runtime.httpd.context.job_notifications.snapshot()["unreadCount"] == 1)
    with running_control_plane(tmp_path, **options) as runtime:
        result = unread(runtime)
        assert result["unreadCount"] == 1 and result["items"][0]["jobId"] == item.item_id
        ack = {"schemaVersion": 1, "ids": [result["items"][0]["id"]]}
        for _ in range(2):
            response = api_request(runtime, "/api/v1/job-notification-acknowledgements", method="POST", payload=ack)
            assert response[0] == 200 and json_response(response)["unreadCount"] == 0
        assert unread(runtime)["unreadCount"] == 0


@pytest.mark.parametrize("notify", [False, True])
def test_remote_completion_respects_opt_out_and_stable_confirmation(tmp_path, notify):
    remote = RecoverableRemote()
    with running_control_plane(tmp_path, remote_manager=remote, server_profiles_path=tmp_path / "profiles.json") as runtime:
        _connect(runtime)
        request = dict(request_for(tmp_path / "case.inp"), notify=notify)
        operation = create(runtime, request)
        wait_for(lambda: view(runtime, operation)["trackingState"] == "tracking")
        assert unread(runtime)["unreadCount"] == 0
        remote.complete = True
        wait_for(lambda: view(runtime, operation)["status"] == "succeeded")
        assert unread(runtime)["unreadCount"] == int(notify)
    with running_control_plane(tmp_path, remote_manager=remote, server_profiles_path=tmp_path / "profiles.json") as runtime:
        assert view(runtime, operation)["request"]["notify"] is notify
        assert unread(runtime)["unreadCount"] == int(notify)


def test_more_than_one_page_remains_unread_and_old_execution_is_not_reintroduced(tmp_path):
    manager = JobNotificationManager(tmp_path / "notifications.sqlite3")
    try:
        for index in range(57):
            publish(manager, f"attempt-{index}")
        page = manager.snapshot()
        assert page["unreadCount"] == 57 and len(page["items"]) == 50
        manager.acknowledge({"schemaVersion": 1, "ids": [item["id"] for item in page["items"]]})
        assert manager.snapshot()["unreadCount"] == 7
        for index in range(57):
            publish(manager, f"attempt-{index}")
        assert manager.snapshot()["unreadCount"] == 7
        with pytest.raises(ApiProblem):
            manager.acknowledge({"schemaVersion": True, "ids": [page["items"][0]["id"]]})
        with pytest.raises(ApiProblem):
            manager.acknowledge({"schemaVersion": 1, "ids": [page["items"][0]["id"], "unknown"]})
        assert manager.snapshot()["unreadCount"] == 7
    finally:
        manager.close()


def test_reconcile_recovers_gap_without_importing_legacy_history(tmp_path):
    manager = JobNotificationManager(tmp_path / "notifications.sqlite3")
    old = queue_item(tmp_path, "old")
    current = queue_item(tmp_path, "current")
    for item in (old, current):
        item.complete_notify, item.status, item.attempt_id = True, STATUS_COMPLETED, item.job_name
    old.submitted_at = manager.since - 1
    current.submitted_at = manager.since + 1
    queue = SimpleNamespace(runtime_items=lambda: ([], [old, current]))
    remote = SimpleNamespace(list_snapshots=list)
    try:
        manager.reconcile(queue, remote)
        items = manager.snapshot()["items"]
        assert len(items) == 1 and items[0]["jobName"] == "current"
    finally:
        manager.close()


def test_pending_notification_save_blocks_whole_backend_shutdown(tmp_path, monkeypatch):
    with running_control_plane(tmp_path) as runtime:
        manager = runtime.httpd.context.job_notifications
        def fail(record):
            raise sqlite3.OperationalError("disk unavailable")
        monkeypatch.setattr(manager._journal, "save", fail)
        publish(manager)
        state = runtime.httpd.context.prepare_odb_shutdown()
        assert not state["safeToStop"]
        assert any(item["kind"] == "job.notifications" for item in state["operations"])
        assert not runtime.httpd.context.remote_job_manager._shutdown_reserved


def test_shutdown_reservation_rejects_late_acknowledgement_and_reconcile(tmp_path):
    manager = JobNotificationManager(tmp_path / "notifications.sqlite3")
    try:
        publish(manager)
        item = manager.snapshot()["items"][0]
        assert manager.prepare_shutdown()["safeToStop"]
        with pytest.raises(ApiProblem, match="后台已准备关闭"):
            manager.acknowledge({"schemaVersion": 1, "ids": [item["id"]]})
        publish(manager, "too-late")
        assert manager.snapshot()["unreadCount"] == 1
    finally:
        manager.close()
