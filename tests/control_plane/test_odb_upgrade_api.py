import threading
import time

from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_odb_upgrade_operations import request

BASE = "/api/v1/odb-upgrade-operations"


def terminal(runtime, operation_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = api_request(runtime, f"{BASE}/{operation_id}")
        assert response[0] == 200
        result = json_response(response)
        if result["status"] in {"succeeded", "failed", "cancelled"}:
            return result
        time.sleep(.01)
    raise AssertionError("upgrade did not finish")


def test_upgrade_http_lifecycle_and_atomic_shutdown_reservation(tmp_path):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def runner(preview, *, controller, **kwargs):
        calls.append(preview)
        entered.set()
        assert release.wait(5)
        assert controller.stop_requested and not controller.cancel_requested
        return {"results": [{"source_path": "case.odb", "status": "upgraded"}]}

    with running_control_plane(tmp_path, odb_upgrade_runner=runner) as runtime:
        try:
            assert "odb.upgrade.safe-v1" in json_response(api_request(runtime, "/healthz"))["capabilities"]
            assert api_request(runtime, BASE, method="POST", payload=request(), token=None)[0] == 401
            assert not calls
            created = api_request(runtime, BASE, method="POST", payload=request())
            assert created[0] == 202
            operation_id = json_response(created)["operationId"]
            assert entered.wait(5)
            again = api_request(runtime, BASE, method="POST", payload=request())
            assert json_response(again)["operationId"] == operation_id
            active = json_response(api_request(runtime, BASE + "?activeOnly=true"))
            assert [row["operationId"] for row in active["operations"]] == [operation_id]
            blocked = json_response(api_request(runtime, "/api/v1/odb-upgrade-shutdown-check", method="POST"))
            assert blocked["safeToStop"] is False
            assert blocked["operations"][0]["status"] == "running"
            cancelled = api_request(runtime, f"{BASE}/{operation_id}/cancel", method="POST")
            assert cancelled[0] == 202 and json_response(cancelled)["status"] == "cancelling"
            release.set()
            done = terminal(runtime, operation_id)
            assert done["status"] == "cancelled" and done["results"][0]["status"] == "upgraded"
            assert len(calls) == 1
            safe = json_response(api_request(runtime, "/api/v1/odb-upgrade-shutdown-check", method="POST"))
            assert safe == {"schemaVersion": 1, "safeToStop": True, "operations": []}
            assert api_request(runtime, BASE, method="POST", payload=request("later"))[0] == 503
        finally:
            release.set()


def test_upgrade_http_validation_and_failed_receipts(tmp_path):
    with running_control_plane(tmp_path, odb_upgrade_runner=lambda *a, **kw: {"results": []}) as runtime:
        for path in [BASE, BASE + "/unknown", "/api/v1/odb-upgrade-shutdown-check"]:
            assert api_request(runtime, path, method="POST" if "shutdown" in path else "GET", token=None)[0] == 401
        assert api_request(runtime, BASE + "?unsupported=true")[0] == 400
        assert api_request(runtime, BASE + "/missing")[0] == 404
        assert api_request(runtime, BASE + "/missing/cancel", method="POST")[0] == 404
        assert api_request(runtime, BASE + "/nested/invalid")[0] == 404
        assert api_request(runtime, BASE, method="POST", payload={})[0] == 400
        unconfirmed = request()
        unconfirmed["confirmed"] = False
        assert api_request(runtime, BASE, method="POST", payload=unconfirmed)[0] == 400
        created = json_response(api_request(runtime, BASE, method="POST", payload=request()))
        assert terminal(runtime, created["operationId"])["status"] == "failed"
        assert json_response(api_request(runtime, BASE + "?activeOnly=true"))["operations"] == []


def test_runtime_close_waits_for_active_upgrade_without_force_cancel(tmp_path):
    from modules.control_plane.server import ControlPlaneRuntime

    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    controllers = []

    def runner(preview, *, controller, **kwargs):
        controllers.append(controller)
        entered.set()
        assert release.wait(5)
        return {"results": [{"source_path": "case.odb", "status": "upgraded"}]}

    runtime = ControlPlaneRuntime(descriptor_path=tmp_path / "descriptor.json", odb_upgrade_runner=runner)
    runtime.odb_upgrade_manager.create(request())
    assert entered.wait(5)

    def close():
        runtime.close()
        closed.set()

    closer = threading.Thread(target=close)
    closer.start()
    try:
        assert not closed.wait(.1)
        assert not controllers[0].cancel_requested
        release.set()
        assert closed.wait(5)
        assert controllers[0].stop_requested
        assert not runtime.descriptor_path.exists()
    finally:
        release.set()
        closer.join(5)
        runtime.close()
