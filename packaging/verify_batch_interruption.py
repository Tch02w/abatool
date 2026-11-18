"""Crash an isolated frozen backend while its fixture worker remains alive.

The three-node inputs are bytes, not engineering ODBs. No Abaqus executable is
invoked. Only processes created under this verifier are stopped, with captured
PID/create-time identities. All fixtures and receipts are retained in GPTWork.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from http.client import HTTPConnection
from pathlib import Path
from uuid import uuid4

import psutil

ROOT = Path(__file__).resolve().parents[1]


def fixture_worker(work: Path) -> int:
    # Invoked only by the generated command in the isolated backend environment.
    with (work / "invocations.txt").open("a", encoding="utf-8") as stream:
        stream.write(f"{os.getpid()}\n")
    (work / "worker.json").write_text(
        json.dumps({"pid": os.getpid(), "createTime": psutil.Process().create_time()}),
        encoding="utf-8",
    )
    deadline = time.monotonic() + 120
    while not (work / "release-worker").exists():
        if time.monotonic() >= deadline:
            return 9
        time.sleep(0.05)
    (work / "worker-ended").write_text("released", encoding="utf-8")
    return 7


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def call(descriptor, path, payload=None, *, expected=(200, 202)):
    connection = HTTPConnection("127.0.0.1", descriptor["port"], timeout=5)
    try:
        connection.request(
            "POST" if payload is not None else "GET",
            path,
            body=json.dumps(payload) if payload is not None else None,
            headers={
                "Authorization": "Bearer " + descriptor["token"],
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        result = json.loads(response.read())
        if response.status not in expected:
            raise RuntimeError(f"Unexpected HTTP {response.status} for {path}")
        return result
    finally:
        connection.close()


def wait_until(check, label, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.05)
    raise TimeoutError(label)


def verify(bundle: Path) -> Path:
    bundle = bundle.resolve(strict=True)
    executable = bundle / "control-plane/AbaqusTools.ControlPlane.exe"
    if not executable.is_file():
        raise ValueError("Frozen control-plane executable is missing")
    work = ROOT / "GPTWork" / ("frozen-batch-interruption-" + uuid4().hex[:12])
    work.mkdir()
    (work / "results").mkdir()
    print(work, flush=True)
    descriptor_path = work / "control-plane.json"
    command = work / "fixture-worker.cmd"
    command.write_text(
        '@echo off\r\n'
        + subprocess.list2cmdline(
            [sys.executable, str(Path(__file__).resolve()), "--worker", str(work)]
        )
        + '\r\nexit /b %errorlevel%\r\n',
        encoding="ascii",
    )
    sources = [work / (name + ".odb") for name in ("base", "restart", "later")]
    for source in sources:
        source.write_bytes(b"Non-ODB interruption fixture: " + source.stem.encode())
    source_hashes = {str(source): digest(source) for source in sources}
    graph = {
        "schemaVersion": 1, "action": "save", "expectedRevision": 0,
        "outputDirectory": str(work / "results"),
        "nodes": [
            {"nodeId": path.stem, "name": path.stem, "parentNodeId": parent,
             "odbPath": str(path), "inpPath": ""}
            for path, parent in zip(sources, ("", "base", "restart"), strict=True)
        ],
    }
    request = {
        "schemaVersion": 1, "clientRequestId": "frozen-interruption-check",
        "source": {"kind": "graph", "revision": 1, "targetNodeIds": ["later"]},
        "options": {"includeHistory": True, "compressResult": False, "copyOriginal": False},
    }
    environment = dict(os.environ)
    for key in ("PYTHONHOME", "PYTHONPATH", "ABAQUS_TOOLS_PYTHON",
                "ABAQUS_TOOLS_ROOT", "ABAQUS_TOOLS_LAUNCH_TOKEN"):
        environment.pop(key, None)
    environment.update(
        ABAQUS_SUBMITTER_DATA_DIR=str(work / "submitter"),
        ABAQUS_POSTPROCESSOR_DATA_DIR=str(work / "postprocessor"),
        ABAQUS_TOOLS_ABAQUS_COMMAND=str(command),
        ABAQUS_TOOLS_ABAQUS_RELEASE="2025",
        MPLCONFIGDIR=str(work / "mpl"),
        PATH=str(Path(os.environ["SystemRoot"]) / "System32"),
    )
    processes, owned_workers = [], []
    report = {"status": "failed", "bundle": str(bundle), "abaqusLaunched": False}
    receipt = work / "verification.json"

    def start_backend(iteration):
        with (work / f"backend-{iteration}.log").open("wb") as output:
            child = subprocess.Popen(
                [str(executable), "--descriptor", str(descriptor_path)],
                cwd=bundle, env=environment, stdout=output, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        processes.append(child)

        def ready():
            if child.poll() is not None:
                raise RuntimeError("Fixture backend exited before readiness")
            try:
                descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
                if descriptor["pid"] == child.pid and descriptor["host"] == "127.0.0.1":
                    call(descriptor, "/healthz")
                    return descriptor
            except (OSError, ValueError, KeyError):
                return None
            return None

        return child, wait_until(ready, "Backend readiness timed out")

    def finish_backend(child, descriptor):
        assert call(descriptor, "/api/v1/odb-upgrade-shutdown-check", {})["safeToStop"]
        child.terminate()
        child.wait(timeout=10)
        descriptor_path.unlink(missing_ok=True)

    try:
        first, descriptor = start_backend(0)
        call(descriptor, "/api/v1/odb-result-graph-commands", graph)
        initial = call(descriptor, "/api/v1/odb-result-batches", request)
        operation_id = initial["operationId"]
        path = "/api/v1/odb-result-batches/" + operation_id

        def worker_started():
            if first.poll() is not None:
                raise RuntimeError("Backend exited before the fixture worker started")
            snapshot = call(descriptor, path)
            if snapshot["status"] in {"failed", "cancelled", "succeeded"}:
                raise RuntimeError(f"Fixture ended before interruption: {snapshot['error']}")
            if (work / "worker.json").exists() and snapshot["stages"][0]["childOperationId"]:
                return snapshot
            return None

        running = wait_until(worker_started, "Fixture worker did not start")
        assert running["status"] == "running" and running["totalSteps"] == 2
        child_id = running["stages"][0]["childOperationId"]
        worker_record = json.loads((work / "worker.json").read_text(encoding="utf-8"))
        worker = psutil.Process(worker_record["pid"])
        assert worker.create_time() == worker_record["createTime"]
        assert str(work) in worker.cmdline() and "--worker" in worker.cmdline()
        owned_workers.extend(psutil.Process(first.pid).children(recursive=True))
        assert any(item.pid == worker.pid for item in owned_workers)
        for item in owned_workers:
            item.create_time()  # Cache identity before the intentional parent crash.
        assert not call(descriptor, "/api/v1/odb-upgrade-shutdown-check", {})["safeToStop"]
        first.kill()  # Our exact Popen handle; deliberately leave its fixture alive.
        first.wait(timeout=10)
        assert worker.is_running(), "Test requires a surviving child, not graceful shutdown"
        descriptor_path.unlink(missing_ok=True)

        second, descriptor = start_backend(1)
        restored = call(descriptor, path)
        assert restored["status"] == "suspended" and restored["completedSteps"] == 0
        children = call(descriptor, "/api/v1/odb-merge-operations")["operations"]
        assert len(children) == 1 and children[0]["operationId"] == child_id
        assert children[0]["error"]["code"] == "ODB_MERGE_INTERRUPTED"
        assert call(descriptor, "/api/v1/odb-result-batches", request)["operationId"] == operation_id
        call(descriptor, path + "/resume", {})

        def recovery_finished():
            item = call(descriptor, path)
            return item if item["status"] not in {"queued", "running", "cancelling"} else None

        failed = wait_until(recovery_finished, "Recovery did not finish")
        assert failed["status"] == "failed" and failed["error"]["code"] == "ODB_BATCH_FAILED"
        assert failed["completedSteps"] == 0 and failed["stages"][1]["childOperationId"] is None
        assert worker.is_running(), "Orphan must remain alive throughout recovery verification"
        assert len((work / "invocations.txt").read_text().splitlines()) == 1
        assert len(call(descriptor, "/api/v1/odb-merge-operations")["operations"]) == 1
        call(descriptor, path + "/resume", {}, expected=(409,))
        (work / "release-worker").touch()
        _, alive = psutil.wait_procs(owned_workers, timeout=10)
        assert not alive and (work / "worker-ended").read_text() == "released"
        finish_backend(second, descriptor)

        third, descriptor = start_backend(2)
        persisted = call(descriptor, "/api/v1/odb-result-batches", request)
        assert persisted["operationId"] == operation_id and persisted["status"] == "failed"
        assert len(call(descriptor, "/api/v1/odb-result-batches")["operations"]) == 1
        assert len(call(descriptor, "/api/v1/odb-merge-operations")["operations"]) == 1
        assert len((work / "invocations.txt").read_text().splitlines()) == 1
        assert source_hashes == {str(source): digest(source) for source in sources}
        assert not list((work / "results").glob("*.odb"))
        finish_backend(third, descriptor)
        report.update(
            status="verified", coldStarts=3, operationId=operation_id, childOperationId=child_id,
            plannedStages=2, admittedChildOperations=1, testCommandInvocations=1,
            backendKilledWhileWorkerAlive=True, workerAliveDuringResume=True,
            restoredStatus="suspended", childErrorCode="ODB_MERGE_INTERRUPTED",
            resumedStatus="failed", descendantsSkipped=True, failedHistoryRestored=True,
            sourcesUnchanged=source_hashes, resultPublished=False, fixtureWorkerReleased=True,
            realContinuousOdbChainVerified=False,
        )
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (work / "release-worker").touch()
        for child in processes:
            if child.poll() is None:
                # Failures must also capture any still-owned descendants before stopping.
                owned_workers.extend(psutil.Process(child.pid).children(recursive=True))
                child.kill()
            child.wait(timeout=10)
        _, alive = psutil.wait_procs(owned_workers, timeout=10)
        for item in alive:
            item.kill()  # psutil checks the captured PID/create-time identity.
        _, alive = psutil.wait_procs(alive, timeout=10)
        report["backendPids"] = [child.pid for child in processes]
        report["workerPids"] = sorted({item.pid for item in owned_workers})
        report["ownedProcessesEnded"] = not alive and all(child.poll() is not None for child in processes)
        if not report["ownedProcessesEnded"]:
            report["status"] = "failed"
        descriptor_path.unlink(missing_ok=True)
        receipt.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not report["ownedProcessesEnded"]:
        raise RuntimeError(f"Fixture cleanup incomplete; inspect {receipt}")
    return receipt


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        raise SystemExit(fixture_worker(Path(sys.argv[2])))
    print(verify(Path(sys.argv[1])), flush=True)
