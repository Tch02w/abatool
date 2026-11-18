"""Verify queue admission and responsiveness with owned, non-solver processes.

Uses real hardware capacity, production dispatch/client and isolated GPTWork
state. Declared CPU/memory requests test admission; helpers do not consume those
quantities. This is not an Abaqus/MPI or CPU stress benchmark.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
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

from modules.submitter.constants import (
    STATUS_DATACHECK_COMPLETED,
    STATUS_DATACHECK_FAILED,
    STATUS_PENDING_RUN,
    STATUS_TERMINATED,
)
from modules.submitter.models import QueueItem
from modules.submitter.queue_store import load_joblist_state, save_joblist_state


def worker(work: Path, arguments: list[str]):
    name = next(argument[4:] for argument in arguments if argument.startswith("job="))
    assert name in {"case0", "case1", "case2", "case3", "memory_gate"}
    flag = work / "helpers" / (name + ".release")
    if "terminate" in arguments:
        flag.write_text("0")
        return 0
    pages = bytearray(8 * 1024**2)
    for offset in range(0, len(pages), 4096):
        pages[offset] = 1
    receipt = work / "helpers" / (name + ".json")
    assert not receipt.exists(), "Fixture must never be replayed"
    receipt.write_text(json.dumps({"pid": os.getpid(), "createTime": psutil.Process().create_time(), "name": name}))
    deadline = time.monotonic() + 180
    while not flag.exists() and time.monotonic() < deadline:
        time.sleep(.05)
    if not flag.exists():
        raise TimeoutError("Fixture parent did not release this worker")
    return int(flag.read_text())


def verify(bundle: str, client: Path, *, trace=False):
    if os.name != "nt" or Path(sys.executable).resolve() != ROOT / ".venv/Scripts/python.exe":
        raise RuntimeError("Use the project .venv Python on Windows")
    logical, physical = psutil.cpu_count() or 1, psutil.cpu_count(logical=False) or 1
    cores = min(physical, max(1, logical // 2))
    # Four bounded helpers: two capacity slots and two jobs waiting for CPU.
    if logical // cores != 2:
        raise RuntimeError("This acceptance fixture requires a two-job CPU capacity; no processes were started")
    work = ROOT / "GPTWork" / ("scheduler-load-live-" + uuid4().hex[:12])
    work.mkdir()
    (work / "helpers").mkdir()
    print("WORK=" + str(work), flush=True)
    command = work / "abaqus-scheduler-fixture.cmd"
    command.write_text(f'@echo off\n"{sys.executable}" "{Path(__file__).resolve()}" --worker "{work}" %*\nexit /b %errorlevel%\n', encoding="utf-8")
    items, inputs = [], {}
    for index, name in enumerate(["case0", "case1", "case2", "case3", "memory_gate", "held_source"]):
        directory = work / "jobs" / name
        directory.mkdir(parents=True)
        source = directory / (name + ".inp")
        source.write_bytes(b"*Heading\nSynthetic scheduler fixture; no engineering model.\n")
        inputs[str(source)] = digest(source)
        if name == "held_source":
            for number in range(256):
                items.append(QueueItem(inp_path=str(source), source_inp_path=str(source), job_name=f"held_{number}",
                    status=STATUS_PENDING_RUN, held=True, cores=1, memory="64 MB", datacheck_only=True,
                    abaqus_command=str(command)))
            continue
        memory = f"{math.ceil(psutil.virtual_memory().total * 2 / 1024**2)} MB" if name == "memory_gate" else "64 MB"
        items.append(QueueItem(inp_path=str(source), source_inp_path=str(source), job_name=name,
            status=STATUS_PENDING_RUN, cores=1 if name == "memory_gate" else cores, memory=memory,
            priority=100 if name == "memory_gate" else 10-index, datacheck_only=True,
            abaqus_command=str(command), complete_notify=True))
    joblist = work / "submitter/joblist.json"
    save_joblist_state([], items, joblist)
    ids = {item.job_name: item.item_id for item in items}
    descriptor_path = work / "control-plane.json"
    environment = dict(os.environ)
    for key in ("PYTHONHOME", "PYTHONPATH", "ABAQUS_TOOLS_ROOT", "ABAQUS_TOOLS_PYTHON", "ABAQUS_TOOLS_LAUNCH_TOKEN"):
        environment.pop(key, None)
    environment.update(ABAQUS_SUBMITTER_DATA_DIR=str(joblist.parent),
                       ABAQUS_POSTPROCESSOR_DATA_DIR=str(work / "postprocessor"), PYTHONUTF8="1")
    backend_command = [sys.executable, "-m", "modules.control_plane"] if bundle == "--source" else [str(Path(bundle).resolve() / "control-plane/AbaqusTools.ControlPlane.exe")]
    if trace:
        if bundle != "--source":
            raise ValueError("Thread tracing is only available for a source backend")
        backend_command = [sys.executable, "-c", "import faulthandler,runpy; faulthandler.dump_traceback_later(3,repeat=True); runpy.run_module('modules.control_plane',run_name='__main__')"]
    backend_command += ["--port", "0", "--descriptor", str(descriptor_path)]
    processes, backend_owners, helper_owners, samples = [], [], {}, []
    descriptor, backend = None, None
    report = {"status": "failed", "bundle": bundle, "solverStarted": False, "queueSize": len(items),
              "logicalCpus": logical, "requestedCoresPerJob": cores, "maxParallel": 3}

    def start_backend(index):
        with (work / f"backend-{index}.log").open("wb") as output:
            child = subprocess.Popen(backend_command, cwd=ROOT, env=environment, stdout=output,
                                     stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        processes.append(child)

        def ready():
            assert child.poll() is None, "Backend exited before readiness"
            try:
                value = json.loads(descriptor_path.read_text(encoding="utf-8"))
                owner = next((p for p in [psutil.Process(child.pid), *psutil.Process(child.pid).children(recursive=True)]
                              if p.pid == value["pid"]), None)
                if owner is not None:
                    call(value, "/healthz")
                    backend_owners.append(owner)
                    return value
            except (OSError, ValueError, KeyError):
                return None
        return child, wait_until(ready, "Backend did not start")

    def snapshot():
        started = time.perf_counter()
        view = call(descriptor, "/api/v1/local-queue-runtime")
        samples.append(round((time.perf_counter() - started) * 1000, 3))
        assert len(view["queue"]["queueItems"]) == len(items)
        assert not view["schedulerMessage"], view["schedulerMessage"]
        return view

    def rows():
        return {row["jobName"]: row for row in snapshot()["queue"]["queueItems"]}

    def helper_names():
        names = set()
        for path in (work / "helpers").glob("*.json"):
            try:
                value = json.loads(path.read_text())
            except ValueError:
                continue
            name = value["name"]
            names.add(name)
            if name not in helper_owners:
                owner = psutil.Process(value["pid"])
                assert abs(owner.create_time() - value["createTime"]) < .01
                assert descriptor["pid"] in {p.pid for p in owner.parents()}, "Not a child of this owned backend"
                helper_owners[name] = owner
        return names

    def release(name, code=0):
        (work / "helpers" / (name + ".release")).write_text(str(code))

    def client_action(action, argument="_"):
        number = len(list(work.glob("client-*.json")))
        with (work / f"client-{number}.log").open("wb") as output:
            result = subprocess.run([str(client), "--scheduler-command", str(descriptor_path), action, str(argument),
                                     str(work / f"client-{number}.json")], cwd=ROOT, stdout=output,
                                    stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW, timeout=45, check=False)
        assert result.returncode == 0, f"Production client {action} failed; see client-{number}.log"

    try:
        backend, descriptor = start_backend(0)
        client_action("start", 3)
        wait_until(lambda: helper_names() == {"case0", "case1"}, "CPU capacity did not start exactly the first two jobs")
        wait_until(lambda: rows()["case2"]["pendingReason"] == "CPU_LIMIT", "Third CPU request was not blocked")
        # CPU is fully reserved now, so the displayed first blocking reason may
        # be CPU_LIMIT. Check the memory-specific reason after CPUs are free.
        assert "memory_gate" not in helper_names()
        client_action("stop")
        release("case0")
        wait_until(lambda: rows()["case0"]["status"] == STATUS_DATACHECK_COMPLETED, "Released job did not complete")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            assert helper_names() == {"case0", "case1"} and not snapshot()["active"]
            time.sleep(.1)
        assert helper_owners["case1"].is_running(), "Stopping dispatch killed active work"
        client_action("terminate", ids["case1"])
        wait_until(lambda: rows()["case1"]["status"] == STATUS_TERMINATED and not helper_owners["case1"].is_running(),
                   "Cancellation did not finish owned work")
        client_action("start", 3)
        wait_until(lambda: helper_names() == {"case0", "case1", "case2", "case3"}, "CPU budget was not released after completion/cancellation")
        release("case2", 7)
        wait_until(lambda: rows()["case2"]["status"] == STATUS_DATACHECK_FAILED, "Failure result did not settle")
        assert helper_owners["case3"].is_running(), "Failure stopped unrelated work"
        wait_until(lambda: rows()["memory_gate"]["pendingReason"] == "MEMORY_LIMIT", "Released CPU capacity was not recognized")
        assert "memory_gate" not in helper_names()
        call(descriptor, "/api/v1/job-queue-commands", {"schemaVersion": 1, "action": "updateQueueItem",
             "itemId": ids["memory_gate"], "memory": "64 MB"})
        wait_until(lambda: "memory_gate" in helper_names(), "Edited memory request was not admitted")
        assert helper_owners["case3"].is_running(), "Failure capacity was not reused while another job was running"
        release("memory_gate")
        release("case3")
        wait_until(lambda: rows()["memory_gate"]["status"] == STATUS_DATACHECK_COMPLETED
                   and rows()["case3"]["status"] == STATUS_DATACHECK_COMPLETED and not snapshot()["active"],
                   "Final job did not settle")
        assert len(helper_names()) == 5 and all(not owner.is_running() for owner in helper_owners.values())
        stored = load_joblist_state(joblist, restore_active_state=False)[1]
        attempts = {item.attempt_id for item in stored if item.job_name in helper_owners}
        assert len(attempts) == 5 and "" not in attempts
        assert all(item.held and not item.attempt_id for item in stored if item.job_name.startswith("held_"))
        wait_until(lambda: {entry["executionId"] for entry in call(descriptor, "/api/v1/job-notifications")["items"]} == attempts,
                   "Terminal notices did not cover all five attempts")
        shutdown(descriptor, backend)
        backend, descriptor = start_backend(1)
        restarted = snapshot()
        assert not restarted["active"] and not restarted["operations"]
        assert {entry["executionId"] for entry in call(descriptor, "/api/v1/job-notifications")["items"]} == attempts
        assert len(helper_names()) == 5
        shutdown(descriptor, backend)
        assert all(digest(Path(path)) == value for path, value in inputs.items())
        with sqlite3.connect(joblist.with_name("scheduler_state.db")) as database:
            report["schedulerEvents"] = database.execute("SELECT count(*) FROM scheduler_events").fetchone()[0]
        report.update(status="verified", cpuAdmission=True, memoryAdmission=True, stopPreservedActiveJob=True,
                      cancellationReleasedCapacity=True, failurePreserved=True, failureCapacityReusedWhileOtherJobActive=True,
                      heldJobsNeverStarted=True,
                      originalInputsUnchanged=True, restartDidNotReplay=True, notificationCount=len(attempts))
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        for name in ("case0", "case1", "case2", "case3", "memory_gate"):
            release(name)
        for owner in [*helper_owners.values(), *backend_owners]:
            if owner.is_running():
                owner.terminate()
                owner.wait(timeout=15)
        for child in processes:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=15)
        report["readMilliseconds"] = samples
        report["ownedProcesses"] = [{"pid": p.pid, "exitCode": p.poll()} for p in processes]
        report["actualOwners"] = [{"pid": p.pid, "createTime": p.create_time(), "ended": not p.is_running()}
                                  for p in [*helper_owners.values(), *backend_owners]]
        (work / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("RECEIPT=" + str(work / "verification.json"), flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "--worker":
        sys.exit(worker(Path(sys.argv[2]), sys.argv[3:]))
    verify(sys.argv[1], Path(sys.argv[2]).resolve(strict=True), trace="--trace" in sys.argv[3:])
