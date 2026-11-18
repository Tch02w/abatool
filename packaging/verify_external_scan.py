"""Exercise production scanning of one owned, non-solver Windows fixture."""
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

from modules.submitter.constants import ACTIVE_STATUSES, STATUS_COMPLETED
from modules.submitter.queue_store import load_joblist_state, save_joblist_state


def worker(work):
    (work / "worker.json").write_text(json.dumps({"pid": os.getpid()}))
    deadline = time.monotonic() + 120
    while not (work / "release").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not (work / "release").exists():
        raise RuntimeError("Fixture parent did not release worker")
    Path("case.sta").write_text("THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n")


def verify(bundle, client):
    work = ROOT / "GPTWork" / ("external-scan-live-" + uuid4().hex[:12])
    work.mkdir()
    jobs = work / "jobs"
    jobs.mkdir()
    inp = jobs / "case.inp"
    inp.write_bytes(b"*Heading\nSynthetic process fixture only\n")
    before = digest(inp)
    descriptor_path = work / "control-plane.json"
    joblist = work / "submitter/joblist.json"
    save_joblist_state([], [], joblist)
    report = {"status": "failed", "bundle": bundle, "solverStarted": False}
    processes, owners = [], []
    print("WORK=" + str(work), flush=True)
    try:
        with (work / "worker.log").open("wb") as output:
            helper = subprocess.Popen([sys.executable, __file__, "--worker", str(work), "job=case", f"input={inp}"],
                cwd=jobs, stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        processes.append(helper)

        def ready_worker():
            assert helper.poll() is None
            try:
                return json.loads((work / "worker.json").read_text())
            except (OSError, ValueError):
                return None
        actual = wait_until(ready_worker, "Fixture worker did not start")
        owner = next(p for p in [psutil.Process(helper.pid), *psutil.Process(helper.pid).children(recursive=True)] if p.pid == actual["pid"])
        owners.append(owner)
        env = dict(os.environ)
        for key in ("PYTHONHOME", "PYTHONPATH", "ABAQUS_TOOLS_PYTHON", "ABAQUS_TOOLS_ROOT", "ABAQUS_TOOLS_LAUNCH_TOKEN"):
            env.pop(key, None)
        env.update(ABAQUS_SUBMITTER_DATA_DIR=str(joblist.parent), ABAQUS_POSTPROCESSOR_DATA_DIR=str(work / "postprocessor"),
                   ABAQUS_TOOLS_ABAQUS_RELEASE="2025", MPLCONFIGDIR=str(work / "mpl"))
        command = [sys.executable, "-m", "modules.control_plane"] if bundle == "--source" else [str(Path(bundle) / "control-plane/AbaqusTools.ControlPlane.exe")]
        with (work / "backend.log").open("wb") as output:
            backend = subprocess.Popen([*command, "--port", "0", "--descriptor", str(descriptor_path)], cwd=ROOT, env=env,
                stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        processes.append(backend)

        def ready_backend():
            assert backend.poll() is None
            try:
                descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
                owner = next((p for p in [psutil.Process(backend.pid), *psutil.Process(backend.pid).children(recursive=True)]
                              if p.pid == descriptor["pid"]), None)
                if owner is not None:
                    call(descriptor, "/healthz")
                    owners.append(owner)
                    return descriptor
            except (OSError, ValueError, KeyError):
                return None
        descriptor = wait_until(ready_backend, "Backend did not start")
        with (work / "client.log").open("wb") as output:
            result = subprocess.run([str(client), "--external-scan-api", str(descriptor_path), str(jobs)], cwd=ROOT,
                stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW, timeout=60, check=False)
        assert result.returncode == 0, "Production scan/read client failed"
        timings = json.loads((work / "client.log").read_text(encoding="utf-8").splitlines()[-1])
        row = next(r for r in call(descriptor, "/api/v1/job-queues")["queueItems"] if r["jobName"] == "case")
        stored = next(r for r in load_joblist_state(joblist, restore_active_state=False)[1] if r.item_id == row["itemId"])
        assert row["isExternal"] and row["status"] in ACTIVE_STATUSES and actual["pid"] in stored.pids
        (work / "release").touch()
        assert helper.wait(timeout=15) == 0
        # The periodic monitor may already be scanning. Observe that existing
        # work instead of racing it with a second manual scan (which must 409).
        def completed_row():
            final = next(r for r in call(descriptor, "/api/v1/job-queues")["queueItems"] if r["itemId"] == row["itemId"])
            return final if final["status"] == STATUS_COMPLETED else None

        final = wait_until(completed_row, "Automatic monitoring did not observe fixture completion")
        stored = next(r for r in load_joblist_state(joblist, restore_active_state=False)[1] if r.item_id == row["itemId"])
        assert final["status"] == STATUS_COMPLETED and not stored.pids
        assert digest(inp) == before
        shutdown(descriptor, backend)
        report.update(status="verified", productionClient=timings, originalInputUnchanged=True,
                      ownedProcessIdentified=True, completionObservedWithoutReplay=True, automaticCompletionObserved=True)
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        (work / "release").touch()
        for owner in owners:
            if owner.is_running():
                owner.terminate()
                owner.wait(timeout=15)
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
        report["ownedProcesses"] = [{"pid": p.pid, "exitCode": p.poll()} for p in processes]
        report["actualOwners"] = [{"pid": p.pid, "createTime": p.create_time(), "ended": not p.is_running()} for p in owners]
        (work / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("RECEIPT=" + str(work / "verification.json"), flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "--worker":
        worker(Path(sys.argv[2]))
    else:
        verify(sys.argv[1], Path(sys.argv[2]).resolve(strict=True))
