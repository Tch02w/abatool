"""Cold-process recovery using production PowerShell on owned local fixtures, not SSH."""
from __future__ import annotations

import base64
import json
import multiprocessing
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest

from modules.submitter.remote_connection import RemoteConnectionError
from tests.control_plane.test_api import (
    api_request,
    running_control_plane,
)
from tests.control_plane.test_remote_job_recovery import create, view, wait_for
from tests.control_plane.test_remote_servers_api import (
    FakeRemoteManager,
    command,
    profile_payload,
)


class LocalPowerShellTransport(FakeRemoteManager):
    def __init__(self, root, lose_ack):
        super().__init__()
        self.root = Path(root).resolve()
        self.lose_ack = lose_ack

    def validate_remote_path(self, remote_path):
        path = Path(remote_path).resolve()
        assert path.is_relative_to(self.root), "Fixture command escaped its isolated directory"
        return str(path)

    def execute_powershell(self, script, *, timeout=30):
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True, timeout=timeout, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RemoteConnectionError(result.stderr.decode(errors="replace"))
        if "process_id=[int]$process.Id" in script:
            with (self.root / "launch-rpc-count.txt").open("a", encoding="ascii") as stream:
                stream.write("start\n")
            if self.lose_ack:
                self.lose_ack = False
                raise RemoteConnectionError("Fixture dropped the real launch acknowledgement")
        return result.stdout.decode("utf-8-sig")


def backend(root, stop, ready, lose_ack):
    root = Path(root)
    with running_control_plane(root, remote_manager=LocalPowerShellTransport(root, lose_ack),
                               server_profiles_path=root / "profiles.json") as runtime:
        ready.send(runtime.base_url)
        ready.close()
        if not stop.wait(120):
            raise RuntimeError("Fixture backend exceeded its lifetime")
        if lose_ack:
            # Deliberate crash of this test-owned process: no manager.close or cancellation.
            os._exit(0)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows production PowerShell integration")
def test_real_launcher_survives_backend_exit_and_is_recovered_without_resubmission(tmp_path):
    root = tmp_path.resolve()
    helper = root / "wait_fixture.py"
    helper.write_text(
        "import json, os, time\nfrom pathlib import Path\nimport psutil\n"
        "Path('helper.json').write_text(json.dumps({'pid':os.getpid(),'created':psutil.Process().create_time()}))\n"
        "Path('case.lck').touch()\n"
        "deadline=time.monotonic()+120\n"
        "while not Path('release').exists() and time.monotonic()<deadline: time.sleep(.05)\n"
        "Path('case.log').write_text('Abaqus JOB case COMPLETED' if Path('release').exists() else '***ERROR: fixture expired')\n"
        "Path('case.lck').unlink()\n", encoding="utf-8")
    launcher = root / "fixture command.cmd"
    launcher.write_text(f'@echo off\necho called>>launch-count.txt\n"{sys.executable}" "{helper}"\n', encoding="ascii")
    input_path = root / "case.inp"
    input_path.write_text("*Heading\n", encoding="ascii")
    profile = profile_payload()
    profile.update(host="local-fixture.invalid", hostFingerprint="SHA256:test-server", computeRoot=str(root),
                   allowedRoots=[str(root)], abaqusCommand=str(launcher))
    request = {"schemaVersion": 1, "clientRequestId": "cold-recovery", "jobName": "case", "inputMode": "existing",
               "inputPath": str(input_path), "oldjobPath": "", "fortranPath": "", "cpus": 1, "memory": "90%", "datacheck": False}
    context = multiprocessing.get_context("spawn")
    children = []
    helper_identity = None

    def boot(lose_ack):
        stop = context.Event()
        receive, send = context.Pipe(duplex=False)
        process = context.Process(target=backend, args=(str(root), stop, send, lose_ack))
        process.start()
        send.close()
        children.append((process, stop))
        assert receive.poll(25), "Owned backend did not report its endpoint"
        runtime = SimpleNamespace(base_url=receive.recv())
        receive.close()
        return runtime, process, stop

    def connect(runtime):
        result = api_request(runtime, "/api/v1/remote-server-commands", method="POST",
                             payload=command("connect", profile=profile))
        assert result[0] == 200, result

    try:
        first, process, stop = boot(True)
        connect(first)
        operation_id = create(first, request)
        wait_for(lambda: view(first, operation_id)["trackingState"] == "reconnecting", seconds=25)
        work = root / ("case_" + operation_id)
        wait_for(lambda: (work / "helper.json").exists(), seconds=10)
        helper_identity = json.loads((work / "helper.json").read_text())
        original_receipt = json.loads((work / ".abaqus-tools-launch.json").read_text())
        stop.set()
        process.join(15)
        assert not process.is_alive() and process.exitcode == 0
        observed = psutil.Process(helper_identity["pid"])
        assert observed.create_time() == helper_identity["created"] and observed.is_running()
        second, second_process, second_stop = boot(False)
        assert view(second, operation_id)["trackingState"] == "reconnecting"
        connect(second)
        wait_for(lambda: view(second, operation_id)["trackingState"] == "tracking", seconds=25)
        assert view(second, operation_id)["processId"] == original_receipt["process_id"]
        (work / "release").touch()
        wait_for(lambda: view(second, operation_id)["status"] == "succeeded", seconds=25)
        terminal = view(second, operation_id)
        assert (root / "launch-rpc-count.txt").read_text().splitlines() == ["start"]
        assert (work / "launch-count.txt").read_text().splitlines() == ["called"]
        assert json.loads((work / ".abaqus-tools-launch.json").read_text()) == original_receipt
        second_stop.set()
        second_process.join(15)
        assert not second_process.is_alive() and second_process.exitcode == 0
        (root / "verification.json").write_text(json.dumps({"status": "verified", "operationId": operation_id,
            "backendPids": [p.pid for p, _ in children], "receipt": original_receipt, "helper": helper_identity,
            "launchCount": 1, "terminalStatus": terminal["status"], "scope": "local production scripts; no SSH or solver"},
            indent=2), encoding="utf-8")
    finally:
        for work in root.glob("case_*"):
            if work.is_dir():
                (work / "release").touch()
        for process, stop in children:
            stop.set()
            process.join(15)
            assert not process.is_alive(), f"Owned backend still active: {process.pid}"
        if helper_identity is not None:
            try:
                owned_helper = psutil.Process(helper_identity["pid"])
                if owned_helper.create_time() == helper_identity["created"]:
                    owned_helper.wait(timeout=15)
            except psutil.NoSuchProcess:
                pass
