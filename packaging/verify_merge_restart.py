"""Verify frozen merge-history recovery with tiny fixtures and a failing test command.

This launches only the supplied control-plane executable and a generated .cmd
that exits with code 7. It never launches Abaqus or reads user models/configs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from http.client import HTTPConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify(bundle: Path) -> Path:
    bundle = bundle.resolve()
    executable = bundle / "control-plane/AbaqusTools.ControlPlane.exe"
    if not executable.is_file():
        raise ValueError("Control-plane bundle executable is missing")
    work = Path(tempfile.mkdtemp(prefix="frozen-merge-recovery-", dir=ROOT / "GPTWork"))
    descriptor_path = work / "control-plane.json"
    command = work / "test-failure.cmd"
    command.write_text(
        '@echo off\necho invoked>>"%~dp0invocations.txt"\nexit /b 7\n', encoding="ascii"
    )
    original, restart = work / "original.odb", work / "restart.odb"
    original.write_bytes(b"test fixture original")
    restart.write_bytes(b"test fixture restart")
    payload = {
        "schemaVersion": 1,
        "clientRequestId": "frozen-history-check",
        "originalOdb": str(original),
        "restartOdb": str(restart),
        "outputOdb": str(work / "output.odb"),
        "includeHistory": True,
        "compressResult": False,
        "copyOriginal": False,
        "conflictPolicy": "auto_number",
    }
    environment = dict(os.environ)
    for name in (
        "PYTHONHOME",
        "PYTHONPATH",
        "ABAQUS_TOOLS_PYTHON",
        "ABAQUS_TOOLS_ROOT",
        "ABAQUS_TOOLS_LAUNCH_TOKEN",
    ):
        environment.pop(name, None)
    environment.update(
        ABAQUS_SUBMITTER_DATA_DIR=str(work / "submitter"),
        ABAQUS_POSTPROCESSOR_DATA_DIR=str(work / "postprocessor"),
        ABAQUS_TOOLS_ABAQUS_COMMAND=str(command),
        ABAQUS_TOOLS_ABAQUS_RELEASE="2025",
        MPLCONFIGDIR=str(work / "mpl"),
        PATH=str(Path(os.environ["SystemRoot"]) / "System32"),
    )

    def call(descriptor, path, body=None):
        connection = HTTPConnection("127.0.0.1", descriptor["port"], timeout=5)
        try:
            connection.request(
                "POST" if body is not None else "GET",
                path,
                body=json.dumps(body) if body is not None else None,
                headers={
                    "Authorization": "Bearer " + descriptor["token"],
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            data = json.loads(response.read())
            if response.status not in (200, 202):
                raise AssertionError((response.status, data))
            return data
        finally:
            connection.close()

    operation_id = None
    for iteration in range(2):
        with (work / f"backend-{iteration}.log").open("wb") as output:
            child = subprocess.Popen(
                [str(executable), "--descriptor", str(descriptor_path)],
                cwd=bundle,
                env=environment,
                stdout=output,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            try:
                deadline = time.monotonic() + 30
                descriptor = None
                while time.monotonic() < deadline:
                    if child.poll() is not None:
                        raise RuntimeError(
                            "Frozen control plane exited; inspect backend log"
                        )
                    if descriptor_path.exists():
                        try:
                            current = json.loads(
                                descriptor_path.read_text(encoding="utf-8")
                            )
                            if (
                                current["pid"] == child.pid
                                and current["host"] == "127.0.0.1"
                            ):
                                call(current, "/healthz")
                                descriptor = current
                                break
                        except OSError, ValueError, KeyError:
                            pass
                    time.sleep(0.05)
                if descriptor is None:
                    raise TimeoutError("Frozen backend readiness timed out")
                snapshot = call(descriptor, "/api/v1/odb-merge-operations", payload)
                if iteration == 0:
                    operation_id = snapshot["operationId"]
                    deadline = time.monotonic() + 30
                    while snapshot["status"] not in {
                        "succeeded",
                        "failed",
                        "cancelled",
                    }:
                        if time.monotonic() > deadline:
                            raise TimeoutError("Test merge did not finish")
                        time.sleep(0.05)
                        snapshot = call(
                            descriptor, "/api/v1/odb-merge-operations/" + operation_id
                        )
                else:
                    assert snapshot["operationId"] == operation_id
                    history = call(descriptor, "/api/v1/odb-merge-operations")[
                        "operations"
                    ]
                    assert (
                        len(history) == 1 and history[0]["operationId"] == operation_id
                    )
                assert (
                    snapshot["status"] == "failed"
                    and snapshot["error"]["code"] == "ODB_MERGE_FAILED"
                )
                assert "exit code 7" in snapshot["error"]["message"]
                assert call(descriptor, "/api/v1/odb-upgrade-shutdown-check", {})[
                    "safeToStop"
                ]
            finally:
                # The child is our isolated, known process. Its test command has no descendants.
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=10)
                # Do not retain generated authentication tokens in acceptance artifacts.
                descriptor_path.unlink(missing_ok=True)
    assert (work / "invocations.txt").read_text().splitlines() == ["invoked"]
    assert original.read_bytes() == b"test fixture original"
    assert restart.read_bytes() == b"test fixture restart"
    assert not list(work.glob(".abasub-odb-merge-*"))
    report = {
        "status": "verified",
        "bundle": str(bundle),
        "coldStarts": 2,
        "operationId": operation_id,
        "testCommandInvocations": 1,
        "historyRestored": True,
        "sourceFixturesUnchanged": True,
        "failedWorkspaceCleaned": True,
        "abaqusLaunched": False,
        "checks": [
            "frozen-sqlite",
            "failure-persistence",
            "idempotent-restart",
            "shutdown-reservation",
        ],
    }
    destination = work / "verification.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return destination


if __name__ == "__main__":
    print(verify(Path(sys.argv[1])), flush=True)
