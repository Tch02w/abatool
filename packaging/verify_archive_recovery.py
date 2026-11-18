"""Kill owned archive fixture processes, then recover through the production client.

All payloads are synthetic bytes under GPTWork. No Abaqus solver is invoked.
Use --source before packaging, or pass a frozen bundle directory.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from verify_batch_interruption import call, digest, wait_until

from modules.submitter import local_archive
from modules.submitter.constants import STATUS_COMPLETED, STATUS_RUNNING
from modules.submitter.local_archive_state import ArchiveBusyError, ArchiveStateStore
from modules.submitter.local_job_execution import (
    LocalJobProcessController,
    _completed_result,
)
from modules.submitter.models import QueueItem
from modules.submitter.queue_store import load_joblist_state, save_joblist_state


def producer(work, index):
    _, items, error = load_joblist_state(work / "submitter/joblist.json", restore_active_state=False)
    assert not error
    item = items[index]
    source = Path(item.calculation_root_dir) / item.job_name
    store = ArchiveStateStore(work / "submitter/archive-state")

    def barrier(path, **details):
        (work / f"ready-{index}.json").write_text(json.dumps({"path": str(path), "pid": os.getpid(), **details}))
        # Parent kills only this captured process while its native claim is held.
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            time.sleep(0.05)
        raise RuntimeError("Fixture parent did not release process")

    if index == 0:
        original = local_archive._copy_verified
        large = (work / "large-payload.json").exists()
        complete = None

        def copy(source, target, expected, check, tick):
            nonlocal complete
            copied = 0

            def partial_tick(size):
                nonlocal copied
                tick(size)
                copied += size
                if large and source.suffix == ".odb" and copied >= 2 * local_archive.CHUNK_BYTES:
                    assert complete is not None
                    barrier(complete, partialPath=str(target), partialBytes=target.stat().st_size,
                            expectedBytes=expected[2])

            result = original(source, target, expected, check, partial_tick)
            if not large:
                barrier(target)
            complete = target
            return result
        local_archive._copy_verified = copy
    else:
        original = Path.unlink

        def unlink(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path.parent == source:
                barrier(path)
            return result
        Path.unlink = unlink
    _completed_result(item, source, "synthetic completed solve", "Fixture completed", LocalJobProcessController(archive_store=store), None)


def shutdown(descriptor, child):
    request = "archive-recovery-" + uuid4().hex
    base = "/api/v1/shutdown-requests"
    call(descriptor, base, {"schemaVersion": 1, "clientRequestId": request})
    call(descriptor, base + "/" + request + "/stop", {"schemaVersion": 1})
    wait_until(lambda: call(descriptor, base + "/" + request)["safeToStop"], "Shutdown remained active")
    call(descriptor, base + "/" + request + "/commit", {"schemaVersion": 1, "mode": "stop"})
    assert child.wait(timeout=20) == 0


def verify(bundle, client, *, destination_root=None, payload_mib=0, parallel_recovery=False):
    if payload_mib != 0 and not 16 <= payload_mib <= 512:
        raise ValueError("Use 16–512 MiB per synthetic ODB, or zero for the original small fixture")
    if destination_root is not None:
        destination_root = Path(destination_root).resolve(strict=True)
        if not destination_root.is_dir() or destination_root.stat().st_dev == (ROOT / "GPTWork").stat().st_dev:
            raise ValueError("Destination root must be an existing directory on a different volume")
    work = ROOT / "GPTWork" / ("archive-recovery-live-" + uuid4().hex[:12])
    work.mkdir()
    archive_root = destination_root / work.name if destination_root is not None else work / "archive"
    archive_root.mkdir()
    if payload_mib:
        (work / "large-payload.json").write_text(json.dumps({"payloadMiB": payload_mib}))
    print("WORK=" + str(work), flush=True)
    report = {"status": "failed", "bundle": bundle, "solverStarted": False, "firstStatusReadSeconds": [],
              "archiveRoot": str(archive_root), "sourceDevice": work.stat().st_dev,
              "archiveDevice": archive_root.stat().st_dev, "payloadMiBPerOdb": payload_mib,
              "parallelRecoveryRequested": parallel_recovery}
    processes, items, expected, originals, ready_records, owners = [], [], {}, {}, [], []
    descriptor_path = work / "control-plane.json"
    try:
        for index, name in enumerate(("copy-interrupted", "cleanup-interrupted")):
            source = work / "ssd" / name
            (source / "nested/empty").mkdir(parents=True)
            original = work / (name + ".inp")
            original.write_bytes(b"*Heading\nSynthetic fixture; not a model.\n")
            originals[str(original)] = digest(original)
            (source / (name + ".inp")).write_bytes(original.read_bytes())
            if payload_mib:
                block = os.urandom(1024 * 1024)
                with (source / (name + ".odb")).open("xb") as output:
                    for _ in range(payload_mib):
                        output.write(block)
                    output.flush()
                    os.fsync(output.fileno())
            else:
                (source / (name + ".odb")).write_bytes(b"Synthetic ODB bytes\n" * 2048)
            (source / "nested/result.txt").write_bytes(b"Fixture output\n")
            expected[name] = {p.relative_to(source).as_posix(): digest(p) for p in source.rglob("*") if p.is_file()}
            items.append(QueueItem(job_name=name, inp_path=str(source / (name + ".inp")), source_inp_path=str(original),
                calculation_root_dir=str(work / "ssd"), archive_dir=str(archive_root), cleanup_after_archive=True,
                attempt_id="original-" + name, cores=1, status=STATUS_RUNNING, complete_notify=True,
                abaqus_command="cmd.exe /c exit 17"))
        joblist = work / "submitter/joblist.json"
        save_joblist_state([], items, joblist)
        for index, item in enumerate(items):
            with (work / f"producer-{index}.log").open("wb") as output:
                child = subprocess.Popen([sys.executable, __file__, "--producer", str(work), str(index)], cwd=ROOT,
                    stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            processes.append(child)
            ready_path = work / f"ready-{index}.json"

            def producer_ready(child=child, ready_path=ready_path):
                assert child.poll() is None, "Producer exited before interruption boundary"
                try:
                    return json.loads(ready_path.read_text())
                except (OSError, ValueError):
                    return None
            record = wait_until(producer_ready, "Producer boundary timeout")
            owner = next((p for p in [psutil.Process(child.pid), *psutil.Process(child.pid).children(recursive=True)]
                          if p.pid == record["pid"]), None)
            assert owner is not None, "Fixture marker did not identify an owned process"
            owners.append(owner)
            store = ArchiveStateStore(joblist.parent / "archive-state")
            try:
                with store.claim(item):
                    raise AssertionError("Cross-process archive ownership was not exclusive")
            except ArchiveBusyError:
                pass
            if index == 0:
                record["inode"] = Path(record["path"]).stat().st_ino
            else:
                assert not Path(record["path"]).exists(), "Cleanup interruption happened before deletion"
            owner.kill()
            child.wait(timeout=15)
            if index == 0 and payload_mib:
                partial = Path(record["partialPath"])
                assert 0 < partial.stat().st_size == record["partialBytes"] < record["expectedBytes"]
                record["partialSha256"] = digest(partial)
                # A killed mid-file copy must not have published or cleaned any source.
                assert all(digest(source) == value for relative, value in expected[item.job_name].items()
                           for source in [work / "ssd" / item.job_name / relative])
                report["interruptedCopyBytes"] = record["partialBytes"]
            with store.claim(item):
                pass
            ready_records.append(record)
        env = dict(os.environ)
        for key in ("PYTHONHOME", "PYTHONPATH", "ABAQUS_TOOLS_PYTHON", "ABAQUS_TOOLS_ROOT", "ABAQUS_TOOLS_LAUNCH_TOKEN"):
            env.pop(key, None)
        env.update(ABAQUS_SUBMITTER_DATA_DIR=str(joblist.parent), ABAQUS_POSTPROCESSOR_DATA_DIR=str(work / "postprocessor"),
                   ABAQUS_TOOLS_ABAQUS_RELEASE="2025", MPLCONFIGDIR=str(work / "mpl"))
        command = [sys.executable, "-m", "modules.control_plane"] if bundle == "--source" else [str(Path(bundle) / "control-plane/AbaqusTools.ControlPlane.exe")]
        notice_ids = None
        for restart in range(2):
            with (work / f"backend-{restart}.log").open("wb") as output:
                child = subprocess.Popen([*command, "--port", "0", "--descriptor", str(descriptor_path)], cwd=ROOT,
                    env=env, stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            processes.append(child)

            def ready(child=child):
                assert child.poll() is None, "Backend exited before readiness"
                try:
                    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
                    owned = [psutil.Process(child.pid), *psutil.Process(child.pid).children(recursive=True)]
                    owner = next((p for p in owned if p.pid == descriptor["pid"]), None)
                    if owner is not None:
                        call(descriptor, "/healthz")
                        owners.append(owner)
                        return descriptor
                except (OSError, ValueError, KeyError):
                    pass
            descriptor = wait_until(ready, "Backend startup timeout")
            read_started = time.monotonic()
            snapshot = call(descriptor, "/api/v1/local-queue-runtime")
            report["firstStatusReadSeconds"].append(round(time.monotonic() - read_started, 4))
            assert not snapshot["active"]
            rows = snapshot["queue"]["queueItems"]
            assert all(r["status"] == STATUS_COMPLETED for r in rows)
            assert all(r["archiveRecoveryAvailable"] == (restart == 0) for r in rows)
            call(descriptor, "/api/v1/local-queue-controls", {"schemaVersion": 1, "action": "start"}, expected=(409,))
            if restart == 0:
                client_processes = []
                for item in items:
                    with (work / (item.job_name + "-client.log")).open("wb") as output:
                        client_process = subprocess.Popen([str(client), "--archive-recovery-api", str(descriptor_path), item.item_id],
                            cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NO_WINDOW)
                    processes.append(client_process)
                    client_processes.append(client_process)
                    if not parallel_recovery:
                        assert client_process.wait(timeout=60) == 0, "Production recovery client failed"
                for client_process in client_processes:
                    assert client_process.wait(timeout=60) == 0, "Production recovery client failed"
                busy_retries = sum(int(count) for item in items for count in re.findall(r"busy retries: (\d+)",
                    (work / (item.job_name + "-client.log")).read_text(encoding="utf-8", errors="replace")))
                report["clientBusyRetries"] = busy_retries
                if parallel_recovery:
                    assert busy_retries > 0, "No rejected-busy request was observed in the parallel fixture"
            def inactive(descriptor=descriptor):
                state = call(descriptor, "/api/v1/local-queue-runtime")
                return state if not any(o["active"] for o in state["operations"]) else None
            snapshot = wait_until(inactive, "Archive worker remained active")
            for item in items:
                row = next(r for r in snapshot["queue"]["queueItems"] if r["itemId"] == item.item_id)
                assert row["attemptId"] == item.attempt_id and row["archiveStatus"] == "已归档"
                final = Path(row["archiveDestination"])
                assert final.parent == archive_root and final.stat().st_dev == report["archiveDevice"]
                manifest = json.loads((final / local_archive.MANIFEST_NAME).read_text(encoding="utf-8"))
                assert manifest["attemptId"] == item.attempt_id
                assert {name: info["sha256"] for name, info in manifest["files"].items()} == expected[item.job_name]
                assert all(digest(final / name) == value for name, value in expected[item.job_name].items())
                assert not (work / "ssd" / item.job_name).exists()
                assert (final / "nested/empty").is_dir()
                if item == items[0]:
                    assert (final / Path(ready_records[0]["path"]).name).stat().st_ino == ready_records[0]["inode"]
                    if payload_mib:
                        preserved = [path for directory in archive_root.glob(".copy-interrupted.recovery-*")
                                     for path in directory.rglob("*.odb")]
                        assert len(preserved) == 1 and preserved[0].stat().st_size == ready_records[0]["partialBytes"]
                        assert digest(preserved[0]) == ready_records[0]["partialSha256"]
                        report["partialEvidence"] = str(preserved[0])
            assert all(digest(Path(p)) == value for p, value in originals.items())
            notices = wait_until(lambda descriptor=descriptor: (n if (n := call(descriptor, "/api/v1/job-notifications"))["unreadCount"] == 4 else None), "Solve/archive notices missing")
            current_ids = sorted(n["id"] for n in notices["items"])
            assert notice_ids is None or notice_ids == current_ids
            notice_ids = current_ids
            shutdown(descriptor, child)
        report.update(status="verified", coldStarts=2, originalAttemptsRetained=True, noAutomaticSolve=True,
                      completeFileReused=True, partialCleanupResumed=True, sourceInputsUnchanged=True,
                      fullArchiveHashesVerified=True, nativeCrossProcessClaimReleased=True, noticesRetainedWithoutReplay=True)
        report.update(crossVolumeVerified=report["sourceDevice"] != report["archiveDevice"],
                      interruptedPartialFilePreserved=bool(payload_mib))
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
        producer(Path(sys.argv[2]), int(sys.argv[3]))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("bundle", nargs="?", help="Frozen directory (omit when using --source)")
        parser.add_argument("client", type=Path)
        parser.add_argument("--source", action="store_true", help="Use the source control plane")
        parser.add_argument("--destination-root", type=Path, help="Existing different-volume directory; creates a unique child")
        parser.add_argument("--payload-mib", type=int, default=0, help="MiB per synthetic ODB; 16–512 enables mid-file interruption")
        parser.add_argument("--parallel-recovery", action="store_true", help="Race two clients against one archive slot; verify explicit busy handling")
        args = parser.parse_args()
        if args.source == (args.bundle is not None):
            parser.error("Choose either a frozen bundle directory or --source")
        verify("--source" if args.source else args.bundle, args.client.resolve(strict=True),
               destination_root=args.destination_root, payload_mib=args.payload_mib, parallel_recovery=args.parallel_recovery)
