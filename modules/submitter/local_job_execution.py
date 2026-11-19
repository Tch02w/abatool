"""Qt-free local Abaqus execution used by the WinUI control plane."""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from .abaqus_diagnostics import (
    build_diagnostic_file_baseline,
    classify_job_text,
    inspect_job_files,
)
from .command import build_abaqus_command, queue_item_to_options, validate_options, quote_job_argument, literal_windows_command
from .constants import (
    MAX_CPUS,
    STATUS_COMPLETED,
    STATUS_DATACHECK_COMPLETED,
    STATUS_DATACHECK_FAILED,
    STATUS_FAILED,
    STATUS_TERMINATED,
    STATUS_UNKNOWN,
)
from .cpu_policy import validate_local_cpus
from .execution_options import validate_execution_options
from .local_archive import ARCHIVE_EXTENSIONS, archive_job_files
from .local_archive_recovery import resume_archive
from .local_archive_state import ArchiveStateError
from .local_workspace import (
    RESTART_EXTENSIONS,
    WorkspacePreparationCancelled,
    check_existing_results,
    check_plan_available,
    plan_workspace,
    prepare_workspace,
)
from .models import QueueItem
from .runtime_evidence import (
    collect_runtime_evidence,
    runtime_completion_ready,
    runtime_termination_ready,
    update_file_stability,
    update_runtime_phase,
)
from .runtime_observation import SHARED_PROCESS_SNAPSHOTS, observe_local_job

LogCallback = Callable[[str], None]
ProgressCallback = Callable[[str, str, int, str], None]
LOGGER = logging.getLogger(__name__)
EXISTING_RESULT_EXTENSIONS = (".odb", ".sta")
RESTART_DEPENDENCY_EXTENSIONS = RESTART_EXTENSIONS


@dataclass(frozen=True)
class LocalJobExecutionResult:
    status: str
    message: str
    work_dir: str
    command: str
    archive_destination: str = ""
    archive_status: str = ""
    archive_error: str = ""
    archive_recovery_available: bool = False


class LocalJobProcessController:
    """Request Abaqus termination without force-killing the solver tree."""

    def __init__(self, *, observer=None, snapshots=SHARED_PROCESS_SNAPSHOTS, archive_store=None) -> None:
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self.archive_store = archive_store
        self.archive_notice = None
        self.archive_claimed = False
        self.cancel_requested = False
        self.observer = observer
        self.snapshots = snapshots

    def attach(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._process = process

    def start(self, *args, **kwargs):
        # Decide admission and register the launcher under the same cancellation
        # lock. A cancellation already accepted cannot race into a new process.
        with self._lock:
            if self.cancel_requested:
                return None
            process = subprocess.Popen(*args, **kwargs)
            self._process = process
            return process

    def detach(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            if self._process is process:
                self._process = None

    def cancel(self) -> None:
        with self._lock:
            self.cancel_requested = True


def _emit(
    callback: ProgressCallback | None,
    phase: str,
    message: str,
    progress: int,
    detail: str = "",
) -> None:
    if callback is not None:
        callback(phase, message, max(0, min(100, int(progress))), detail)


def _unique_backup_path(path: Path) -> Path:
    tag = datetime.now(UTC).astimezone().strftime("%Y%m%d_%H%M%S")
    candidate = path.with_name(f"{path.stem}_bak_{tag}{path.suffix}")
    index = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_bak_{tag}_{index}{path.suffix}")
        index += 1
    return candidate


def _prepare_existing_results(work_dir: Path, job_name: str, policy: str) -> None:
    check_existing_results(work_dir, job_name, policy)
    existing = [
        work_dir / f"{job_name}{extension}"
        for extension in EXISTING_RESULT_EXTENSIONS
        if (work_dir / f"{job_name}{extension}").exists()
    ]
    if not existing:
        return
    if policy == "cancel":
        raise RuntimeError("检测到同名结果文件，当前策略为取消提交")
    if policy == "overwrite":
        for path in existing:
            path.unlink()
        return
    if policy != "backup":
        raise ValueError("existing result policy must be backup, overwrite, or cancel")
    for path in existing:
        path.replace(_unique_backup_path(path))


def _prepare_workspace(item: QueueItem, **kwargs) -> tuple[Path, Path, str]:
    return prepare_workspace(item, **kwargs)


def _execution_command(item: QueueItem, prepared_inp: Path, oldjob_arg: str, *, validation_inp=None) -> str:
    validate_local_cpus(item.cores, item.abaqus_command)
    options = queue_item_to_options(item, default_cpus=MAX_CPUS)
    options = replace(
        options,
        inp_file=str(prepared_inp),
        for_file=str(Path(options.for_file).resolve()) if options.for_file else "",
        oldjob_arg=oldjob_arg,
        ask_delete_off=True,
    )
    valid, message = validate_options(replace(options, inp_file=str(validation_inp or prepared_inp)))
    if not valid:
        raise ValueError(message)
    command = build_abaqus_command(options)
    if " input=" not in command.casefold():
        command += f' input="{prepared_inp.name}"'
    return command


def _archive_result(
    item: QueueItem,
    work_dir: Path,
    **kwargs,
) -> tuple[str, str, str]:
    return archive_job_files(item, work_dir, **kwargs)


def _completed_result(item, work_dir, command, message, controller, progress, *, recover=False):
    def report(detail, copied, total):
        percent = 92 + min(6, int(6 * copied / max(1, total)))
        _emit(progress, "archiving", "计算已完成，正在归档", percent, detail)

    destination, status, error = "", "", ""
    if item.archive_dir:
        report("正在检查归档目录", 0, 1)
    store = controller.archive_store
    try:
        if item.archive_dir and store is not None:
            with (nullcontext() if controller.archive_claimed else store.claim(item)):
                state = store.read(item) if recover else store.begin(item, work_dir, command, message)
                if state is None:
                    raise ArchiveStateError("没有可核对的归档记录，未重新计算")
                work_dir, command, message = Path(state["source"]), state["command"], state["solveMessage"]
                store.save(item, state)

                def checkpoint(phase, fields):
                    state.update(fields, phase=phase, result=None)
                    if phase == "done" and controller.archive_notice is not None:
                        notices, receipt = controller.archive_notice
                        notices.finish(receipt, state["destination"], "已归档", "")
                    store.save(item, state)

                options = {"cancelled": lambda: controller.cancel_requested, "progress": report, "checkpoint": checkpoint}
                destination, status, error = (resume_archive(item, state, **options) if recover
                                               else _archive_result(item, work_dir, **options))
                if controller.archive_notice is not None:
                    notices, receipt = controller.archive_notice
                    notices.finish(receipt, destination, status, error, controller.cancel_requested)
                state["result"] = {"destination": destination, "status": status, "error": error}
                store.save(item, state)
        else:
            destination, status, error = _archive_result(
                item, work_dir, cancelled=lambda: controller.cancel_requested, progress=report)
    except (OSError, RuntimeError, ValueError) as exc:
        LOGGER.exception("归档记录或恢复失败，未改变已经确认的求解结果")
        status, error = "归档待恢复", str(exc)
    if status:
        message += "；" + status
    return LocalJobExecutionResult(STATUS_COMPLETED, message, str(work_dir), command, destination, status, error,
                                   bool(store is not None and status and status != "已归档"))


def run_archive_only(item, controller, progress=None):
    """Resume only the archive; execution admission is not reachable from this entry."""
    return _completed_result(item, Path(item.effective_work_dir or Path(item.inp_path).parent), "",
                             "计算已完成", controller, progress, recover=True)


def _terminate_abaqus(item: QueueItem, work_dir: Path, log: LogCallback | None) -> None:
    command = f'{item.abaqus_command or "abaqus"} terminate job={quote_job_argument(item.job_name)}'
    if log:
        log(f"发送终止命令：{command}")
    launch_command, environment = literal_windows_command(command)
    subprocess.run(
        launch_command,
        env=environment,
        cwd=str(work_dir),
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def execute_local_job(
    item: QueueItem,
    existing_result_policy: str,
    controller: LocalJobProcessController,
    progress: ProgressCallback | None = None,
    log: LogCallback | None = None,
) -> LocalJobExecutionResult:
    """Execute and monitor one queue item until a defensible terminal state."""

    if controller.cancel_requested:
        return LocalJobExecutionResult(STATUS_TERMINATED, "已取消准备，未启动 Abaqus", "", "")
    _emit(progress, "preparing", "正在准备计算工作目录", 4)
    validate_local_cpus(item.cores, item.abaqus_command)
    validate_execution_options(item)
    plan = plan_workspace(item, existing_result_policy)
    command = _execution_command(item, plan.prepared_inp, plan.oldjob_arg, validation_inp=plan.source_inp)
    try:
        _prepared_inp, work_dir, _oldjob_arg = _prepare_workspace(
            item, plan=plan, policy=existing_result_policy, cancelled=lambda: controller.cancel_requested)
    except WorkspacePreparationCancelled as exc:
        return LocalJobExecutionResult(STATUS_TERMINATED, str(exc), str(plan.work_dir), command)
    if controller.cancel_requested:
        return LocalJobExecutionResult(STATUS_TERMINATED, "已取消准备，未启动 Abaqus", str(work_dir), command)
    _prepare_existing_results(work_dir, item.job_name, existing_result_policy)
    check_plan_available(plan, existing_result_policy)
    baseline = build_diagnostic_file_baseline(str(work_dir), item.job_name)
    submitted_at = time.time()
    run: dict[str, object] = {
        "work_dir": str(work_dir),
        "job_name": item.job_name,
        "diagnostic_baseline": baseline,
        "submitted_at": submitted_at,
        "datacheck_only": item.datacheck_only,
        "runtime_phase": "STARTING",
        "process_snapshot_available": False,
        "known_solver_pids": (),
    }
    if log:
        log(f"工作目录：{work_dir}")
        log(f"执行命令：{command}")
    _emit(progress, "starting", "正在启动 Abaqus launcher", 10, command)
    check_plan_available(plan, existing_result_policy)
    launch_command, environment = literal_windows_command(command)
    process = controller.start(
        launch_command,
        env=environment,
        cwd=str(work_dir),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="gbk" if os.name == "nt" else "utf-8",
        errors="replace",
        bufsize=1,
    )
    if process is None:
        return LocalJobExecutionResult(STATUS_TERMINATED, "已取消准备，未启动 Abaqus", str(work_dir), command)
    output_parts: list[str] = []

    def read_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            message = line.rstrip()
            if not message:
                continue
            output_parts.append(message)
            if len(output_parts) > 500:
                del output_parts[:100]
            if log:
                log(message)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    terminate_sent = False
    terminal_stable = 0
    latest_status = ""
    latest_detail = ""
    try:
        while True:
            time.sleep(1.0)
            exit_code = process.poll()
            if exit_code is not None:
                run["launcher_finished"] = True
                run.setdefault("launcher_finished_monotonic", time.monotonic())
            if controller.cancel_requested and not terminate_sent:
                terminate_sent = True
                run["terminating"] = True
                _emit(progress, "terminating", "正在终止 Abaqus 作业", 92)
                _terminate_abaqus(item, work_dir, log)

            snapshot = controller.snapshots.capture()
            rows = snapshot.rows or ()
            run["process_snapshot"] = rows
            run["process_snapshot_by_pid"] = {
                int(row.get("ProcessId") or 0): row for row in rows
            }
            run["process_snapshot_solver_rows"] = rows
            run["process_snapshot_available"] = snapshot.rows is not None
            evidence = collect_runtime_evidence(run)
            if controller.observer is not None:
                try:
                    controller.observer(observe_local_job(snapshot, evidence, work_dir=work_dir,
                                                          submitted_at=submitted_at, launcher_pid=process.pid))
                except Exception:
                    LOGGER.exception("Memory observation failed; continuing to monitor the owned job")
            sta_delta = str(evidence.get("sta_delta") or "").strip()
            if sta_delta and log:
                for line in sta_delta.splitlines():
                    if line.strip():
                        log(line.rstrip())
            update_file_stability(run, evidence)
            update_runtime_phase(run, evidence)
            latest_status = str(evidence.get("diagnostic_status") or latest_status)
            latest_detail = str(evidence.get("diagnostic_detail") or latest_detail)
            phase = str(run.get("runtime_phase") or "running").lower()
            step = evidence.get("sta_last_step")
            increment = evidence.get("sta_last_increment")
            detail = ""
            if step is not None:
                detail = f"Step {step} · Increment {increment}"
            _emit(progress, phase, "Abaqus 作业运行中", 50, detail)

            if terminate_sent:
                if runtime_termination_ready(run, evidence):
                    return LocalJobExecutionResult(
                        STATUS_TERMINATED,
                        latest_detail or "用户手动终止",
                        str(work_dir),
                        command,
                    )
                continue

            active = bool(evidence.get("lck_exists") or evidence.get("solver_pid_active"))
            if latest_status in {"失败", "终止"} and not active:
                terminal_stable += 1
                if terminal_stable >= 3:
                    status = STATUS_FAILED if latest_status == "失败" else STATUS_TERMINATED
                    return LocalJobExecutionResult(
                        status,
                        latest_detail or latest_status,
                        str(work_dir),
                        command,
                    )
            else:
                terminal_stable = 0

            if item.datacheck_only and exit_code is not None and not active:
                console_status, console_detail = classify_job_text("\n".join(output_parts))
                status = latest_status or console_status
                if status == "失败" or exit_code != 0:
                    return LocalJobExecutionResult(
                        STATUS_DATACHECK_FAILED,
                        latest_detail or console_detail or f"返回码 {exit_code}",
                        str(work_dir),
                        command,
                    )
                return LocalJobExecutionResult(
                    STATUS_DATACHECK_COMPLETED,
                    latest_detail or "Datacheck 已完成",
                    str(work_dir),
                    command,
                )

            if latest_status == "完成" and not active:
                terminal_stable += 1
                if terminal_stable >= 3 or runtime_completion_ready(run, evidence):
                    return _completed_result(item, work_dir, command, latest_detail or "Abaqus 作业已完成",
                                             controller, progress)

            launcher_finished_at = run.get("launcher_finished_monotonic")
            if (
                exit_code is not None
                and not active
                and not run.get("activity_seen")
                and launcher_finished_at is not None
                and time.monotonic() - float(launcher_finished_at) >= 30.0
            ):
                console_status, console_detail = classify_job_text("\n".join(output_parts))
                if exit_code != 0 or console_status == "失败":
                    return LocalJobExecutionResult(
                        STATUS_FAILED,
                        console_detail or f"Abaqus launcher 返回码 {exit_code}",
                        str(work_dir),
                        command,
                    )
                file_status, file_detail = inspect_job_files(
                    str(work_dir),
                    item.job_name,
                    submitted_at,
                    baseline,
                )
                if file_status == "完成":
                    return _completed_result(item, work_dir, command, file_detail or "Abaqus 作业已完成",
                                             controller, progress)
                return LocalJobExecutionResult(
                    STATUS_UNKNOWN,
                    file_detail or "launcher 已退出，但未获得足够的求解完成证据",
                    str(work_dir),
                    command,
                )
    finally:
        controller.detach(process)
        reader.join(timeout=2)


__all__ = [
    "ARCHIVE_EXTENSIONS",
    "LocalJobExecutionResult",
    "LocalJobProcessController",
    "execute_local_job",
]
