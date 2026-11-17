import threading
import time

import pytest

from modules.control_plane.contracts import ApiProblem
from modules.control_plane.odb_upgrade_operations import OdbUpgradeOperationManager, TERMINAL


def request(key="one"):
    return {"schemaVersion": 1, "clientRequestId": key, "confirmed": True,
            "preview": {"entries": [{"sourcePath": "case.odb"}]}}


def wait(manager, key):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = manager.get(key)
        if result["status"] in TERMINAL: return result
        time.sleep(.01)
    raise AssertionError("operation failed to finish")


def test_upgrade_operation_idempotency_snapshot_and_partial_failure():
    calls = []
    def runner(preview, **kwargs):
        calls.append(preview)
        return {"results": [{"status": "upgrade_failed", "source_path": "case.odb"}]}
    manager = OdbUpgradeOperationManager(runner=runner)
    try:
        first = manager.create(request())
        first["preview"]["entries"].clear()
        again = manager.create(request())
        assert again["operationId"] == first["operationId"]
        result = wait(manager, again["operationId"])
        assert result["status"] == "failed" and len(result["results"]) == 1 and len(calls) == 1
        changed = request()
        changed["preview"]["entries"][0]["sourcePath"] = "changed.odb"
        with pytest.raises(ApiProblem): manager.create(changed)
    finally: manager.close()


def test_upgrade_safe_cancel_preserves_completed_results_and_skips_queued_work():
    entered, release = threading.Event(), threading.Event()
    calls = []
    def runner(preview, *, controller, **kwargs):
        calls.append(preview)
        entered.set()
        assert release.wait(5)
        assert controller.stop_requested and not controller.cancel_requested
        return {"results": [{"status": "upgraded", "source_path": "case.odb"}]}
    manager = OdbUpgradeOperationManager(runner=runner)
    try:
        first = manager.create(request())
        assert entered.wait(5)
        second = manager.create(request("two"))
        assert manager.cancel(second["operationId"])["status"] == "cancelled"
        assert manager.cancel(first["operationId"])["status"] == "cancelling"
        release.set()
        result = wait(manager, first["operationId"])
        assert result["status"] == "cancelled" and result["results"][0]["status"] == "upgraded"
        assert manager.list_snapshots(active_only=True) == [] and len(calls) == 1
    finally:
        release.set()
        manager.close()


@pytest.mark.parametrize("path,status", [("case.odb", "succeeded"), ("wrong.odb", "failed")])
def test_upgrade_success_requires_exact_source_receipts(path, status):
    manager = OdbUpgradeOperationManager(runner=lambda *a, **kw:
        {"results": [{"status": "upgraded", "source_path": path}]})
    try:
        operation = manager.create(request())
        assert wait(manager, operation["operationId"])["status"] == status
    finally: manager.close()


def test_upgrade_progress_is_bounded_and_observable_while_running():
    entered, release = threading.Event(), threading.Event()
    def runner(preview, *, log, **kwargs):
        log("ODB_UPGRADE_START|1|1|case.odb")
        log("ODB_UPGRADE_DONE|wrong|1|upgraded|case.odb")
        log("ODB_UPGRADE_DONE|99|1|upgraded|case.odb")
        entered.set()
        assert release.wait(5)
        log("ODB_UPGRADE_DONE|1|1|upgraded|case.odb")
        return {"results": [{"status": "upgraded", "source_path": "case.odb"}]}
    manager = OdbUpgradeOperationManager(runner=runner)
    try:
        operation = manager.create(request())
        assert entered.wait(5)
        snapshot = manager.get(operation["operationId"])
        assert snapshot["status"] == "running"
        assert snapshot["progress"] == {"completed": 0, "total": 1, "currentFile": "case.odb"}
        release.set()
        assert wait(manager, operation["operationId"])["progress"] == {"completed": 1, "total": 1, "currentFile": ""}
    finally:
        release.set()
        manager.close()
