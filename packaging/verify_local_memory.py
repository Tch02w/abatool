"""Verify real Windows process sampling and memory history without Abaqus solving.

Run with this checkout's .venv Python; optionally pass --bundle <AbaqusTools>.
All fixtures and backend state are isolated under a new GPTWork directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from modules.submitter.constants import STATUS_PENDING_RUN
from modules.submitter.models import QueueItem
from modules.submitter.queue_store import (
    load_joblist_state,
    save_joblist_state,
)


def wait_for(check, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(.2)
    raise TimeoutError("Memory verification condition did not complete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--notifications", action="store_true", help="Also verify durable notices from the owned attempts")
    parser.add_argument("--host-client", type=Path, help="Production C# client test DLL for notification HTTP checks")
    args = parser.parse_args()
    if os.name != "nt" or Path(sys.executable).resolve() != ROOT / ".venv/Scripts/python.exe":
        raise RuntimeError("Use this project's .venv Python on Windows")
    work = ROOT / "GPTWork" / ("local-memory-live-" + uuid4().hex[:12])
    work.mkdir()
    print("WORK=" + str(work), flush=True)
    source = work / "memory-case.inp"
    source.write_text("*Heading\nFixture only: no model and no solver.\n", encoding="ascii")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    helper = work / "memory_fixture.py"
    helper.write_text('''from pathlib import Path
import json, os, sys, time
from uuid import uuid4
root = Path(__file__).resolve().parent
if len(sys.argv) > 1 and sys.argv[1] == "terminate":
    latest = json.loads((root / "latest-helper.json").read_text())
    flag = (root / latest["release"]).resolve()
    assert flag.parent == root and flag.name.startswith("release-")
    flag.touch()
    sys.exit(0)
flag = root / ("release-" + uuid4().hex + ".txt")
pages = bytearray(96 * 1024 * 1024)
for offset in range(0, len(pages), 4096): pages[offset] = 1
(root / "latest-helper.json").write_text(json.dumps({"pid": os.getpid(), "release": flag.name}))
with (root / "invocations.txt").open("a") as stream: stream.write(str(os.getpid()) + "\\n")
deadline = time.monotonic() + 90
while not flag.exists() and time.monotonic() < deadline: time.sleep(.1)
''', encoding="utf-8")
    command = work / "abaqus-memory-fixture.cmd"
    command.write_text(f'@echo off\n"{sys.executable}" "{helper}" %*\nexit /b %errorlevel%\n', encoding="utf-8")
    item = QueueItem(inp_path=str(source), source_inp_path=str(source), job_name="memory-case",
                     status=STATUS_PENDING_RUN, cores=1, memory="90%", datacheck_only=True,
                     abaqus_command=str(command), complete_notify=args.notifications)
    joblist = work / "submitter/joblist.json"
    save_joblist_state([], [item], joblist)
    descriptor_path = work / "control-plane.json"
    environment = dict(os.environ, ABAQUS_SUBMITTER_DATA_DIR=str(joblist.parent),
                       ABAQUS_POSTPROCESSOR_DATA_DIR=str(work / "postprocessor"), PYTHONUTF8="1")
    backend_args = [sys.executable, "-m", "modules.control_plane"]
    if args.bundle:
        backend_args = [str(args.bundle.resolve() / "control-plane/AbaqusTools.ControlPlane.exe")]
    backend_args += ["--port", "0", "--descriptor", str(descriptor_path)]
    descriptor = None
    child = None
    receipts = []

    def call(path, payload=None):
        request = Request(descriptor["baseUrl"] + path,
                          data=json.dumps(payload).encode() if payload is not None else None,
                          headers={"Authorization": "Bearer " + descriptor["token"], "Content-Type": "application/json"})
        with urlopen(request, timeout=10) as response:
            return json.load(response)

    def shutdown(request_id):
        base = "/api/v1/shutdown-requests"
        call(base, {"schemaVersion": 1, "clientRequestId": request_id})
        call(base + "/" + request_id + "/stop", {"schemaVersion": 1})
        wait_for(lambda: call(base + "/" + request_id)["safeToStop"], 90)
        terminal = call("/api/v1/local-queue-runtime")
        call(base + "/" + request_id + "/commit", {"schemaVersion": 1, "mode": "stop"})
        assert child.wait(20) == 0 and not descriptor_path.exists()
        assert not psutil.pid_exists(descriptor["pid"])
        return terminal

    try:
        for index in range(2):
            descriptor = None
            with (work / f"backend-{index}.log").open("w", encoding="utf-8") as log:
                child = subprocess.Popen(backend_args, cwd=ROOT, env=environment, stdout=log,
                                         stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            (work / f"owned-backend-{index}.json").write_text(json.dumps({"pid": child.pid, "args": backend_args}))

            def ready(child=child):
                assert child.poll() is None, "Backend exited before readiness"
                if descriptor_path.exists():
                    return json.loads(descriptor_path.read_text(encoding="utf-8"))
                return None

            descriptor = wait_for(ready)
            assert call("/healthz")["instanceId"] == descriptor["instanceId"]
            initial = call("/api/v1/local-queue-runtime")
            if index:
                assert not initial["operations"] and not initial["active"]
                if args.notifications:
                    inbox = call("/api/v1/job-notifications")
                    assert inbox["unreadCount"] == 1 and inbox["items"][0]["executionId"] == receipts[0]["attemptId"]
                    assert inbox["items"][0]["status"] == "cancelled"
                    if args.host_client:
                        checked = subprocess.run(["dotnet", str(args.host_client.resolve()), "--notifications-api", str(descriptor_path)],
                            cwd=ROOT, env=environment, capture_output=True, text=True, timeout=30, check=False,
                            creationflags=subprocess.CREATE_NO_WINDOW)
                        (work / "notification-client.log").write_text(checked.stdout + checked.stderr, encoding="utf-8")
                        assert checked.returncode == 0, "Production client check failed; see notification-client.log"
                    else:
                        call("/api/v1/job-notification-acknowledgements", {"schemaVersion": 1, "ids": [inbox["items"][0]["id"]]})
                    assert call("/api/v1/job-notifications")["unreadCount"] == 0
                restored = initial["queue"]["queueItems"][0]
                assert restored["memoryEstimateSource"] == "history" and restored["memoryEstimatedBytes"] > 96 * 1024**2
                assert len((work / "invocations.txt").read_text().splitlines()) == 1
                call("/api/v1/job-queue-commands", {"schemaVersion": 1, "action": "requeueQueueItems", "itemIds": [item.item_id]})
            call("/api/v1/local-queue-controls", {"schemaVersion": 1, "action": "start"})

            def observed():
                runtime = call("/api/v1/local-queue-runtime")
                view = runtime["queue"]["queueItems"][0]
                return runtime if view["memoryObservationStatus"] == "observed" and view["runtimeMemoryBytes"] >= 96 * 1024**2 else None

            runtime = wait_for(observed)
            view = runtime["queue"]["queueItems"][0]
            stored = load_joblist_state(joblist, restore_active_state=False)[1][0]
            helper_info = json.loads((work / "latest-helper.json").read_text())
            assert helper_info["pid"] in stored.pids
            assert descriptor["pid"] not in stored.pids and os.getpid() not in stored.pids
            created = psutil.Process(helper_info["pid"]).create_time()
            assert abs(stored.pid_create_times[str(helper_info["pid"])] - created) < .01
            assert view["memoryPeakBytes"] >= view["runtimeMemoryBytes"]
            assert view["memoryEstimatedBytes"] >= view["memoryPeakBytes"]
            terminal = shutdown("memory-stop-" + str(index))
            assert terminal["queue"]["queueItems"][0]["memoryObservationStatus"] == "ended"
            receipts.append({"attemptId": runtime["operations"][0]["attemptId"],
                             "rssBytes": view["runtimeMemoryBytes"], "estimatedBytes": view["memoryEstimatedBytes"],
                             "helperPid": helper_info["pid"], "backendExited": True})
            child = None
        assert receipts[0]["attemptId"] != receipts[1]["attemptId"]
        assert len((work / "invocations.txt").read_text().splitlines()) == 2
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
        notices = []
        if args.notifications:
            with sqlite3.connect(work / "job-notifications.sqlite3") as database:
                notices = [json.loads(row[0]) for row in database.execute("SELECT payload FROM job_notifications")]
            notices = [notice for notice in notices if notice["id"] != "baseline"]
            assert {notice["executionId"] for notice in notices} == {entry["attemptId"] for entry in receipts}
            assert len(notices) == 2 and sum(notice["read"] for notice in notices) == 1
            assert all(notice["status"] == "cancelled" for notice in notices)
        report = {"status": "verified", "runs": receipts, "historyRestored": True, "noAutomaticReplay": True,
                  "sourceUnchanged": True, "solverStarted": False, "notificationsVerified": args.notifications,
                  "notificationCount": len(notices), "productionNotificationClient": bool(args.notifications and args.host_client),
                  "scope": "Real Windows process working-set sampling through backend API, isolated 96 MiB Python helper"}
        (work / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("VERIFIED=" + str(work / "verification.json"), flush=True)
    finally:
        if child is not None and child.poll() is None:
            try:
                shutdown("memory-cleanup")
            except Exception:  # noqa: BLE001 - preserve owned backend when cleanup cannot be confirmed
                print("BACKEND_PRESERVED pid=" + str(child.pid), flush=True)


if __name__ == "__main__":
    main()
