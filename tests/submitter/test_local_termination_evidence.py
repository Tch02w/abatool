"""Race an in-flight termination against diagnostic evidence without starting a solver."""

import io
import time
from types import SimpleNamespace

import pytest

from modules.submitter import local_job_execution as execution
from modules.submitter.models import QueueItem


@pytest.mark.parametrize("case,expected,sends", [
    ("natural_completion", execution.STATUS_COMPLETED, 0),
    ("natural_failure", execution.STATUS_FAILED, 0),
    ("owned", execution.STATUS_TERMINATED, 1),
    ("detached", execution.STATUS_TERMINATED, 1),
    ("reused_pid", execution.STATUS_UNKNOWN, 0),
    ("other_parent", execution.STATUS_UNKNOWN, 0),
    ("command_refused", execution.STATUS_UNKNOWN, 1),
])
def test_cancel_respects_live_handle_creation_time_and_real_outcome(tmp_path, monkeypatch, case, expected, sends):
    inp = tmp_path / "WorkRun.inp"
    inp.write_text("*Heading\n", encoding="ascii")
    item = QueueItem(job_name="WorkRun", inp_path=str(inp), source_inp_path=str(inp), cores=1,
                     abaqus_command="fixture-abaqus")
    tick = 0
    sent = []
    messages = []

    def poll():
        if case in {"owned", "command_refused"} and tick <= 3:
            return None
        if case in {"detached", "reused_pid", "other_parent"} and tick <= 1:
            return None
        return 0

    def snapshot():
        rows = []
        if tick <= 1:
            rows.append({"ProcessId": 11, "CreateTime": 10.0, "ParentProcessId": 0})
        if case in {"detached", "reused_pid", "other_parent"} and tick < 5:
            parent = 51 if case == "other_parent" else 11
            stamp = 73.0 if case == "reused_pid" and tick >= 2 else 12.0
            rows.append({"ProcessId": 23, "CreateTime": stamp, "ParentProcessId": parent})
        return SimpleNamespace(rows=rows)

    controller = execution.LocalJobProcessController(snapshots=SimpleNamespace(capture=snapshot))
    process = SimpleNamespace(stdout=io.StringIO(""), pid=11, poll=poll)
    monkeypatch.setattr(controller, "start", lambda *_args, **_kwargs: process)

    def sleep(_duration):
        nonlocal tick
        tick += 1
        assert tick < 20, "the monitor must reach a defensible terminal result"
        if tick >= (2 if case in {"detached", "reused_pid", "other_parent"} else 1):
            controller.cancel()

    monkeypatch.setattr(execution, "time", SimpleNamespace(time=time.time, monotonic=lambda: tick * 20.0, sleep=sleep))

    def evidence(run):
        pids = (23,) if 23 in run["process_snapshot_by_pid"] else ()
        return {"solver_pids": pids, "solver_pid_active": bool(pids), "lck_exists": False,
                "diagnostic_status": {"natural_completion": "完成", "natural_failure": "失败"}.get(case, "")}

    def send(_item, directory, _log):
        assert directory == tmp_path
        sent.append(tick)
        return case != "command_refused"

    monkeypatch.setattr(execution, "_terminate_abaqus", send)
    monkeypatch.setattr(execution, "collect_runtime_evidence", evidence)
    monkeypatch.setattr(execution, "runtime_termination_ready", lambda _run, observed: not observed["solver_pid_active"])
    result = execution.execute_local_job(item, "backup", controller, log=messages.append)
    assert result.status == expected and len(sent) == sends
    if case in {"reused_pid", "other_parent"}:
        assert sum("暂未发送" in message for message in messages) == 1
    if case == "owned":
        assert tick >= 4, "the launched process must actually exit after the termination command"
