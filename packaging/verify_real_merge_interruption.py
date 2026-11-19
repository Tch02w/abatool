"""Exercise cancellation and worker loss against real Abaqus merge validation.

Uses an isolated frozen backend and existing GPTWork ODB copies. Never solves a
model, edits source ODBs, or stops a process outside this verifier's ancestry.
The only deliberately killed process is the positively identified Abaqus Python
validator in this run's private staging directory. All evidence stays on G:.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from http.client import HTTPConnection
from pathlib import Path
from uuid import uuid4

import psutil

ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = ROOT / "GPTWork"


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def call(descriptor, path, body=None):
    connection = HTTPConnection("127.0.0.1", descriptor["port"], timeout=15)
    try:
        connection.request("POST" if body is not None else "GET", path,
            json.dumps(body) if body is not None else None,
            {"Authorization": "Bearer " + descriptor["token"], "Content-Type": "application/json"})
        response = connection.getresponse()
        value = json.loads(response.read())
        if response.status not in (200, 202):
            raise RuntimeError(f"HTTP {response.status} at {path}: {value}")
        return value
    finally:
        connection.close()


def same_alive(identity):
    try:
        return abs(psutil.Process(identity["pid"]).create_time() - identity["created"]) < .001
    except psutil.NoSuchProcess:
        return False


def identity(process):
    return {"pid": process.pid, "created": process.create_time(), "executable": process.exe(),
            "arguments": process.cmdline(), "cwd": process.cwd()}


def wait_terminal(descriptor, operation_path, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = call(descriptor, operation_path)
        if snapshot["status"] in ("succeeded", "failed", "cancelled"):
            return snapshot
        time.sleep(.1)
    raise TimeoutError("Original operation is not terminal; preserve its backend and files")


def verify(bundle: Path, original: Path, restart: Path, existing: Path) -> Path:
    paths = [path.resolve(strict=True) for path in (bundle, original, restart, existing)]
    bundle, original, restart, existing = paths
    if any(not p.is_relative_to(WORK_ROOT.resolve()) for p in paths):
        raise ValueError("Use existing GPTWork package and ODB copies only")
    if any(p.drive.casefold() == "c:" for p in paths):
        raise ValueError("C: is not permitted for ODB acceptance")
    executable = bundle / "control-plane/AbaqusTools.ControlPlane.exe"
    if not executable.is_file():
        raise ValueError("Frozen backend missing")
    # Each case temporarily needs two original copies and one restart copy.
    required = 2 * original.stat().st_size + restart.stat().st_size + 2 * 1024**3
    if psutil.disk_usage(str(WORK_ROOT)).free < required:
        raise RuntimeError("Insufficient G: space for protected staging")
    work = WORK_ROOT / ("real-merge-interruption-" + uuid4().hex[:12])
    work.mkdir()
    temp = work / "temp"
    temp.mkdir()
    print("WORK=" + str(work), flush=True)
    descriptor_path = work / "control-plane.json"
    before = {str(p): digest(p) for p in (original, restart, existing)}
    save(work / "sources-before.json", before)
    environment = dict(os.environ)
    for key in ("PYTHONHOME", "PYTHONPATH", "ABAQUS_TOOLS_PYTHON", "ABAQUS_TOOLS_ROOT", "ABAQUS_TOOLS_LAUNCH_TOKEN"):
        environment.pop(key, None)
    environment.update(ABAQUS_SUBMITTER_DATA_DIR=str(work / "submitter"),
        ABAQUS_POSTPROCESSOR_DATA_DIR=str(work / "postprocessor"),
        ABAQUS_TOOLS_ABAQUS_COMMAND=r"D:\SIMULIA\Commands\abaqus.bat",
        ABAQUS_TOOLS_ABAQUS_RELEASE="2025", TEMP=str(temp), TMP=str(temp),
        MPLCONFIGDIR=str(work / "mpl"), PATH=str(Path(os.environ["SystemRoot"]) / "System32"))
    processes, cases = [], []
    report = {"status": "failed", "bundle": str(bundle), "solverStarted": False, "cases": cases}

    def start_backend(index):
        with (work / f"backend-{index}.log").open("wb") as stream:
            process = subprocess.Popen([str(executable), "--descriptor", str(descriptor_path)],
                cwd=bundle, env=environment, stdout=stream, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW)
        record = identity(psutil.Process(process.pid))
        processes.append(record)
        save(work / "processes.json", processes)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Frozen backend exited before ready")
            if descriptor_path.exists():
                descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
                if descriptor["pid"] == process.pid and descriptor["host"] == "127.0.0.1":
                    call(descriptor, "/healthz")
                    return process, descriptor, record
            time.sleep(.1)
        raise TimeoutError("Backend readiness; preserve recorded original PID")

    def close_idle(process, descriptor, record):
        if process.poll() is not None:
            raise RuntimeError("Backend exited before intentional idle shutdown")
        request_id = str(uuid4())
        route = "/api/v1/shutdown-requests"
        state = call(descriptor, route, {"schemaVersion": 1, "clientRequestId": request_id})
        if not state["safeToStop"] or state.get("operations") or state.get("pendingRequests"):
            call(descriptor, route + f"/{request_id}/abort", {"schemaVersion": 1})
            raise RuntimeError("Backend busy; preserve the owned process instead of forcing shutdown")
        call(descriptor, route + f"/{request_id}/commit", {"schemaVersion": 1, "mode": "idle"})
        record["exitCode"] = process.wait(timeout=30)
        record["descriptorRemoved"] = not descriptor_path.exists()
        save(work / "processes.json", processes)
        assert record["exitCode"] == 0 and record["descriptorRemoved"]

    try:
        backend, descriptor, backend_record = start_backend(0)
        for mode in ("cancel-validation", "crash-validation"):
            output = work / mode
            output.mkdir()
            destination = output / "existing-result.odb"
            destination.write_bytes(existing.read_bytes())
            old_hash = digest(destination)
            body = {"schemaVersion": 1, "clientRequestId": str(uuid4()),
                "originalOdb": str(original), "restartOdb": str(restart), "outputOdb": str(destination),
                "includeHistory": True, "compressResult": False, "copyOriginal": False, "conflictPolicy": "overwrite"}
            snapshot = call(descriptor, "/api/v1/odb-merge-operations", body)
            route = "/api/v1/odb-merge-operations/" + snapshot["operationId"]
            case = {"mode": mode, "request": body, "operationId": snapshot["operationId"],
                    "oldOutputSha256": old_hash, "observedProcesses": [], "progress": []}
            cases.append(case)
            save(work / "verification.json", report)
            seen, owned = set(), []
            deadline, selected = time.monotonic() + 300, None
            print("STARTED=" + mode, flush=True)
            while time.monotonic() < deadline:
                snapshot = call(descriptor, route)
                percent = snapshot["progress"]["percent"]
                if not case["progress"] or case["progress"][-1] != percent:
                    case["progress"].append(percent)
                    save(work / "verification.json", report)
                    print(f"{mode} progress={percent}", flush=True)
                if snapshot["status"] in ("succeeded", "failed", "cancelled"):
                    raise RuntimeError("Operation ended before real validator was observed; test not accepted")
                for child in psutil.Process(backend.pid).children(recursive=True):
                    try:
                        record = identity(child)
                        key = (record["pid"], record["created"])
                        if key not in seen:
                            seen.add(key)
                            owned.append(record)
                            case["observedProcesses"].append(record)
                        args = record["arguments"]
                        validation_args = [arg for arg in args if Path(arg).name.casefold() == "validate_joined_odb.py"]
                        if percent == 82 and len(validation_args) == 1:
                            script = (Path(record["cwd"]) / validation_args[0]).resolve()
                            binary = Path(record["executable"]).resolve()
                            if (binary.is_relative_to(Path(r"D:\SIMULIA")) and "python" in binary.name.casefold()
                                and script.is_relative_to(output) and script.parent.name.startswith(".abasub-odb-merge-")
                                and Path(record["cwd"]).resolve() == script.parent):
                                selected = record
                                break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                if selected:
                    break
                time.sleep(.03)
            if selected is None:
                # Preserve the still-owned task. Do not launch another on a timeout.
                raise TimeoutError("Real Abaqus validator not identified; original operation preserved")
            case["selectedWorker"] = selected
            case["snapshotBeforeInterruption"] = snapshot
            save(work / "verification.json", report)
            assert same_alive(selected), "Observed worker ended before intervention"
            if mode == "cancel-validation":
                case["cancelResponse"] = call(descriptor, route + "/cancel", {})
            else:
                worker = psutil.Process(selected["pid"])
                assert worker.create_time() == selected["created"]
                assert any(p.pid == backend.pid for p in worker.parents()), "Worker no longer has the owned backend ancestor"
                worker.kill()  # Exact owned validator; intentionally simulate an unexpected worker exit.
                worker.wait(timeout=15)
            final = wait_terminal(descriptor, route)
            case["finalSnapshot"] = final
            save(work / "verification.json", report)
            assert final["status"] == ("cancelled" if mode == "cancel-validation" else "failed"), final["status"]
            assert final.get("result") is None
            end = time.monotonic() + 15
            while same_alive(selected) and time.monotonic() < end:
                time.sleep(.1)
            assert not same_alive(selected), "Actual validator survived the completed operation"
            assert digest(destination) == old_hash, "Existing output was changed by interrupted work"
            assert sorted(p.name for p in output.iterdir()) == [destination.name], "Partial output or staging leaked"
            # Backend's own bootloader children stay alive, but every observed Abaqus child must end.
            abaqus = [p for p in owned if Path(p["executable"]).is_relative_to(Path(r"D:\SIMULIA"))]
            assert abaqus and not any(same_alive(p) for p in abaqus)
            case["workerEnded"] = True
            case["oldOutputUnchanged"] = True
            case["partialOutputsAbsent"] = True
            save(work / "verification.json", report)
            print("VERIFIED=" + mode, flush=True)
        close_idle(backend, descriptor, backend_record)
        backend, descriptor, backend_record = start_backend(1)
        restored = call(descriptor, "/api/v1/odb-merge-operations")["operations"]
        assert len(restored) == 2
        for case in cases:
            final = call(descriptor, "/api/v1/odb-merge-operations", case["request"])
            assert final["operationId"] == case["operationId"]
            assert final["status"] == case["finalSnapshot"]["status"] and final.get("result") is None
            assert digest(Path(case["request"]["outputOdb"])) == case["oldOutputSha256"]
        assert len(call(descriptor, "/api/v1/odb-merge-operations")["operations"]) == 2
        close_idle(backend, descriptor, backend_record)
        after = {str(p): digest(p) for p in (original, restart, existing)}
        assert before == after
        report.update(status="verified", sourcesBefore=before, sourcesAfter=after, coldStarts=2,
                      terminalHistoryRestoredWithoutReplay=True, remainingOwnedBackendPids=[])
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        report["preservedLiveBackendPids"] = [p["pid"] for p in processes if same_alive(p)]
        raise
    finally:
        save(work / "verification.json", report)
    return work / "verification.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bundle", "original", "restart", "existing-result"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(verify(args.bundle, args.original, args.restart, args.existing_result), flush=True)
