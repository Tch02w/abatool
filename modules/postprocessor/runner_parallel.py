"""Cancellable orchestration of multiple independent Abaqus CAE processes."""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Callable

from .config import abaqus_script
from .process_runner import ProcessCancelled, run_process


LogCallback = Callable[[str], None]


class MultiProcessController:
    """Track and cancel every Abaqus subprocess belonging to one GUI batch."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processes: set[subprocess.Popen[str]] = set()
        self.cancel_requested = False

    def attach(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._processes.add(process)
            cancel_now = self.cancel_requested
        if cancel_now:
            self._terminate_tree(process)

    def detach(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._processes.discard(process)

    @property
    def active_count(self) -> int:
        with self._lock:
            return sum(process.poll() is None for process in self._processes)

    def cancel(self) -> None:
        with self._lock:
            self.cancel_requested = True
            processes = list(self._processes)
        for process in processes:
            self._terminate_tree(process)

    @staticmethod
    def _terminate_tree(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def scan_field_ranges(
    abaqus_command: str,
    job_config_path: Path,
    output_path: Path,
    log: LogCallback | None = None,
    controller: MultiProcessController | None = None,
) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_process(
        [
            abaqus_command,
            "cae",
            f"noGUI={abaqus_script('scan_legend_worker.py')}",
            "--",
            "--config",
            str(job_config_path),
            "--output",
            str(output_path),
        ],
        job_config_path.parent,
        log,
        controller,
    )
    with output_path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def run_job(
    abaqus_command: str,
    job_config_path: Path,
    log: LogCallback | None = None,
    controller: MultiProcessController | None = None,
) -> None:
    run_process(
        [
            abaqus_command,
            "cae",
            f"noGUI={abaqus_script('extract_job_worker.py')}",
            "--",
            str(job_config_path),
        ],
        job_config_path.parent,
        log,
        controller,
    )


def render_group_contours(
    abaqus_command: str,
    job_config_path: Path,
    log: LogCallback | None = None,
    controller: MultiProcessController | None = None,
) -> None:
    config = json.loads(job_config_path.read_text(encoding="utf-8"))
    request_id = config.get("render_request_id")
    command = [abaqus_command, "cae", f"noGUI={abaqus_script('render_group_contours.py')}",
               "--", str(job_config_path)]
    process_error = None
    try:
        run_process(command, job_config_path.parent, log, controller)
    except ProcessCancelled:
        raise
    except RuntimeError as exc:
        if not request_id:
            raise
        process_error = exc
    if not request_id:
        return
    # Some CAE versions exit zero after a script error. Require this invocation's receipt.
    try:
        metadata = json.loads((Path(config["output_dir"]) / "metadata.json").read_text(encoding="utf-8"))
        receipt = metadata["group_render_receipt"]
        if receipt["request_id"] != request_id:
            raise ValueError("渲染回执不属于本次请求")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise RuntimeError(f"{config['odb_path']} 未返回本次有效的出图回执：{process_error or exc}") from exc
    if receipt.get("status") != "succeeded":
        raise RuntimeError(receipt.get("error") or "云图渲染失败，请检查渲染日志")
    if process_error:
        raise process_error


__all__ = [
    "MultiProcessController",
    "ProcessCancelled",
    "render_group_contours",
    "run_job",
    "scan_field_ranges",
]

