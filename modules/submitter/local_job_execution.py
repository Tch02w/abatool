"""Qt-free local Abaqus execution used by the WinUI control plane."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from .abaqus_diagnostics import (
    build_diagnostic_file_baseline,
    classify_job_text,
    inspect_job_files,
)
from .command import build_abaqus_command, queue_item_to_options, validate_options
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
RESTART_DEPENDENCY_EXTENSIONS = (
    ".odb",
    ".res",
    ".stt",
    ".sim",
    ".mdl",
    ".prt",
    ".sta",
    ".msg",
    ".dat",
    ".log",
    ".com",
)
ARCHIVE_EXTENSIONS = (
    ".inp",
    ".odb",
    ".sta",
    ".msg",
    ".dat",
    ".log",
    ".com",
    ".prt",
    ".sim",
    ".res",
    ".mdl",
    ".stt",
    ".fil",
    ".pac",
)


@dataclass(frozen=True)
class LocalJobExecutionResult:
    status: str
    message: str
    work_dir: str
    command: str
    archive_destination: str = ""
    archive_status: str = ""
    archive_error: str = ""


class LocalJobProcessController:
    """Request Abaqus termination without force-killing the solver tree."""

    def __init__(self, *, observer=None, snapshots=SHARED_PROCESS_SNAPSHOTS) -> None:
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self.cancel_requested = False
        self.observer = observer
        self.snapshots = snapshots

    def attach(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._process = process

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


def _unique_destination(root: Path, job_name: str) -> Path:
    destination = root / job_name
    if not destination.exists():
        return destination
    tag = datetime.now(UTC).astimezone().strftime("%Y%m%d_%H%M%S")
    candidate = root / f"{job_name}_{tag}"
    index = 1
    while candidate.exists():
        candidate = root / f"{job_name}_{tag}_{index}"
        index += 1
    return candidate


def _prepare_existing_results(work_dir: Path, job_name: str, policy: str) -> None:
    lock_path = work_dir / f"{job_name}.lck"
    if lock_path.exists():
        raise RuntimeError(f"检测到同名 LCK 文件，拒绝重复提交：{lock_path}")
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


def _copy_restart_files(source_odb: Path, target_dir: Path) -> None:
    for extension in RESTART_DEPENDENCY_EXTENSIONS:
        source = source_odb.with_suffix(extension)
        if not source.is_file():
            continue
        target = target_dir / source.name
        if source.resolve() == target.resolve():
            continue
        if target.exists():
            target.unlink()
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)


def _prepare_workspace(item: QueueItem) -> tuple[Path, Path, str]:
    source_inp = Path(item.source_inp_path or item.inp_path).resolve()
    if not source_inp.is_file():
        raise FileNotFoundError(f"INP 文件不存在：{source_inp}")
    if item.calculation_root_dir:
        work_dir = Path(item.calculation_root_dir).resolve() / item.job_name
        work_dir.mkdir(parents=True, exist_ok=True)
        prepared_inp = work_dir / source_inp.name
        shutil.copy2(source_inp, prepared_inp)
    else:
        prepared_inp = Path(item.inp_path).resolve()
        work_dir = prepared_inp.parent

    oldjob_arg = ""
    if item.oldjob_path:
        source_odb = Path(item.oldjob_path).resolve()
        if not source_odb.is_file():
            raise FileNotFoundError(f"Restart 前置 ODB 不存在：{source_odb}")
        if item.calculation_root_dir:
            _copy_restart_files(source_odb, work_dir)
            oldjob_arg = source_odb.stem
        else:
            local_odb = work_dir / source_odb.name
            oldjob_arg = (
                source_odb.stem
                if local_odb.resolve() == source_odb
                else str(source_odb.with_suffix(""))
            )
    return prepared_inp, work_dir, oldjob_arg


def _execution_command(item: QueueItem, prepared_inp: Path, oldjob_arg: str) -> str:
    validate_local_cpus(item.cores, item.abaqus_command)
    options = queue_item_to_options(item, default_cpus=MAX_CPUS)
    options = replace(
        options,
        inp_file=str(prepared_inp),
        oldjob_arg=oldjob_arg,
        ask_delete_off=True,
    )
    valid, message = validate_options(options)
    if not valid:
        raise ValueError(message)
    command = build_abaqus_command(options)
    if " input=" not in command.casefold():
        command += f' input="{prepared_inp.name}"'
    return command


def _archive_result(
    item: QueueItem,
    work_dir: Path,
) -> tuple[str, str, str]:
    if not item.archive_dir:
        return "", "", ""
    root = Path(item.archive_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination = _unique_destination(root, item.job_name)
    try:
        if item.cleanup_after_archive and item.calculation_root_dir:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(work_dir), str(destination))
        else:
            destination.mkdir(parents=True, exist_ok=False)
            for extension in ARCHIVE_EXTENSIONS:
                source = work_dir / f"{item.job_name}{extension}"
                if source.is_file():
                    shutil.move(str(source), str(destination / source.name))
    except OSError as exc:
        return str(destination), "归档失败", str(exc)
    return str(destination), "已归档", ""


def _terminate_abaqus(item: QueueItem, work_dir: Path, log: LogCallback | None) -> None:
    command = f'{item.abaqus_command or "abaqus"} terminate job={item.job_name}'
    if log:
        log(f"发送终止命令：{command}")
    subprocess.run(
        command,
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

    _emit(progress, "preparing", "正在准备计算工作目录", 4)
    validate_local_cpus(item.cores, item.abaqus_command)
    prepared_inp, work_dir, oldjob_arg = _prepare_workspace(item)
    _prepare_existing_results(work_dir, item.job_name, existing_result_policy)
    command = _execution_command(item, prepared_inp, oldjob_arg)
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
    process = subprocess.Popen(
        command,
        cwd=str(work_dir),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="gbk" if os.name == "nt" else "utf-8",
        errors="replace",
        bufsize=1,
    )
    controller.attach(process)
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
                    destination, archive_status, archive_error = _archive_result(item, work_dir)
                    return LocalJobExecutionResult(
                        STATUS_COMPLETED,
                        latest_detail or "Abaqus 作业已完成",
                        str(work_dir),
                        command,
                        destination,
                        archive_status,
                        archive_error,
                    )

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
                    destination, archive_status, archive_error = _archive_result(item, work_dir)
                    return LocalJobExecutionResult(
                        STATUS_COMPLETED,
                        file_detail or "Abaqus 作业已完成",
                        str(work_dir),
                        command,
                        destination,
                        archive_status,
                        archive_error,
                    )
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
    "LocalJobExecutionResult",
    "LocalJobProcessController",
    "execute_local_job",
]
