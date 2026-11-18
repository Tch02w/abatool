"""Verify an archive notice survives loss of its producer and removal of its queue row."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from verify_archive_recovery import shutdown
from verify_batch_interruption import call, digest, wait_until

from modules.control_plane.job_notifications import JobNotificationManager
from modules.submitter.archive_notifications import ArchiveNoticeStore
from modules.submitter.constants import STATUS_RUNNING
from modules.submitter.local_archive_state import ArchiveStateStore
from modules.submitter.local_job_execution import (
    LocalJobProcessController,
    _completed_result,
)
from modules.submitter.models import QueueItem
from modules.submitter.queue_store import load_joblist_state, save_joblist_state


def producer(work):
    _, items, _ = load_joblist_state(work / "submitter/joblist.json", restore_active_state=False)
    item = items[0]
    archives = ArchiveStateStore(work / "submitter/archive-state")
    with archives.claim(item):
        notices = ArchiveNoticeStore(archives)
        receipt = notices.begin(item, uuid4().hex)
        controller = LocalJobProcessController(archive_store=archives)
        controller.archive_claimed = True
        controller.archive_notice = (notices, receipt)
        source = Path(item.calculation_root_dir) / item.job_name
        result = _completed_result(item, source, "synthetic completed solve", "fixture completed", controller, None)
        assert result.archive_status == "已归档", result.archive_error
        (work / "producer-ready.json").write_text(json.dumps({"pid": os.getpid(), "operationId": receipt["operationId"],
            "destination": result.archive_destination}), encoding="utf-8")
        # No completion callback or inbox write takes place in this process.
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            time.sleep(0.05)
        raise RuntimeError("Fixture producer was not interrupted")


def verify(bundle, client):
    work = ROOT / "GPTWork" / ("archive-notice-live-" + uuid4().hex[:12])
    work.mkdir()
    print("WORK=" + str(work), flush=True)
    processes, owners = [], []
    report = {"status": "failed", "bundle": bundle, "solverStarted": False}
    descriptor_path = work / "control-plane.json"
    joblist = work / "submitter/joblist.json"
    try:
        source = work / "ssd/case"
        source.mkdir(parents=True)
        inp = work / "case.inp"
        inp.write_bytes(b"*Heading\nSynthetic fixture only\n")
        original_hash = digest(inp)
        (source / "case.inp").write_bytes(inp.read_bytes())
        (source / "case.odb").write_bytes(b"Synthetic bytes, not engineering ODB\n")
        item = QueueItem(job_name="case", inp_path=str(source / "case.inp"), source_inp_path=str(inp), cores=1,
            calculation_root_dir=str(work / "ssd"), archive_dir=str(work / "archive"), cleanup_after_archive=True,
            status=STATUS_RUNNING, attempt_id="original-attempt", complete_notify=True, abaqus_command="cmd.exe /c exit 17")
        save_joblist_state([], [item], joblist)
        JobNotificationManager(work / "job-notifications.sqlite3").close()
        with (work / "producer.log").open("wb") as output:
            child = subprocess.Popen([sys.executable, __file__, "--producer", str(work)], cwd=ROOT,
                stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        processes.append(child)

        def producer_ready():
            assert child.poll() is None
            try:
                return json.loads((work / "producer-ready.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
        ready = wait_until(producer_ready, "Producer did not reach persisted outcome")
        owner = next(p for p in [psutil.Process(child.pid), *psutil.Process(child.pid).children(recursive=True)] if p.pid == ready["pid"])
        owners.append(owner)
        owner.kill()
        child.wait(timeout=15)
        save_joblist_state([], [], joblist)  # Acknowledged queue cleanup cannot erase a pending notice.
        env = dict(os.environ)
        for key in ("PYTHONHOME", "PYTHONPATH", "ABAQUS_TOOLS_PYTHON", "ABAQUS_TOOLS_ROOT", "ABAQUS_TOOLS_LAUNCH_TOKEN"):
            env.pop(key, None)
        env.update(ABAQUS_SUBMITTER_DATA_DIR=str(joblist.parent), ABAQUS_POSTPROCESSOR_DATA_DIR=str(work / "postprocessor"),
                   ABAQUS_TOOLS_ABAQUS_RELEASE="2025", MPLCONFIGDIR=str(work / "mpl"))
        command = [sys.executable, "-m", "modules.control_plane"] if bundle == "--source" else [str(Path(bundle) / "control-plane/AbaqusTools.ControlPlane.exe")]
        for index in range(2):
            with (work / f"backend-{index}.log").open("wb") as output:
                child = subprocess.Popen([*command, "--port", "0", "--descriptor", str(descriptor_path)], cwd=ROOT, env=env,
                    stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            processes.append(child)

            def backend_ready(child=child):
                assert child.poll() is None
                try:
                    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
                    owner = next((p for p in [psutil.Process(child.pid), *psutil.Process(child.pid).children(recursive=True)]
                                  if p.pid == descriptor["pid"]), None)
                    if owner is not None:
                        call(descriptor, "/healthz")
                        owners.append(owner)
                        return descriptor
                except (OSError, ValueError, KeyError):
                    return None
            descriptor = wait_until(backend_ready, "Backend did not start")
            assert not call(descriptor, "/api/v1/local-queue-runtime")["queue"]["queueItems"]
            inbox = call(descriptor, "/api/v1/job-notifications")
            assert inbox["unreadCount"] == (1 if index == 0 else 0)
            if index == 0:
                notice = inbox["items"][0]
                assert notice["executionId"] == "original-attempt:archive:" + ready["operationId"]
                assert notice["status"] == "succeeded" and notice["workDirectory"] == ready["destination"]
                with (work / "client.log").open("wb") as output:
                    result = subprocess.run([str(client), "--archive-notifications-api", str(descriptor_path)], cwd=ROOT,
                        stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30, check=False)
                assert result.returncode == 0
            shutdown(descriptor, child)
        assert digest(inp) == original_hash and not source.exists()
        manifest = json.loads((Path(ready["destination"]) / ".abaqustools-archive.json").read_text(encoding="utf-8"))
        assert all(digest(Path(ready["destination"]) / name) == value["sha256"] for name, value in manifest["files"].items())
        report.update(status="verified", lostCallbackRecovered=True, queueRemovedBeforeRecovery=True,
                      productionClientAcknowledged=True, secondRestartRemainsRead=True, sourceInputUnchanged=True,
                      fullArchiveHashesVerified=True)
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        for owner in owners:
            if owner.is_running():
                owner.terminate()
                owner.wait(timeout=15)
        for child in processes:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=15)
        report["ownedProcesses"] = [{"pid": p.pid, "exitCode": p.poll()} for p in processes]
        report["actualOwners"] = [{"pid": p.pid, "createTime": p.create_time(), "ended": not p.is_running()} for p in owners]
        (work / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("RECEIPT=" + str(work / "verification.json"), flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "--producer":
        producer(Path(sys.argv[2]))
    else:
        verify(sys.argv[1], Path(sys.argv[2]).resolve(strict=True))
