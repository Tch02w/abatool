"""Qt-free protected ODB merge execution shared by native frontends."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path

from modules.postprocessor.process_runner import (
    ProcessCancelled,
    ProcessController,
    run_process,
)

from .odb_merge_core import (
    MergeConflictPolicy,
    OdbMergeError,
    OdbMergeRequest,
    OdbMergeResult,
    build_merge_plan,
)

ProgressCallback = Callable[[int, str], None]
LogCallback = Callable[[str], None]

_VALIDATION_SCRIPT = """\
from __future__ import print_function
import sys
from odbAccess import openOdb

odb = openOdb(path=sys.argv[1], readOnly=True)
try:
    if len(odb.steps) == 0:
        raise RuntimeError("ODB contains no steps")
    if not any(len(step.frames) > 0 for step in odb.steps.values()):
        raise RuntimeError("ODB contains no frames")
    print("ABASUB_ODB_VALIDATION_OK")
finally:
    odb.close()
"""


def execute_odb_merge(
    request: OdbMergeRequest,
    progress: ProgressCallback | None = None,
    log: LogCallback | None = None,
    controller: ProcessController | None = None,
) -> OdbMergeResult:
    """Execute one merge without modifying either source ODB."""

    effective_controller = controller or ProcessController()
    plan = build_merge_plan(request)
    published: list[Path] = []

    def report(percent: int, phase: str) -> None:
        if progress is not None:
            progress(max(0, min(100, int(percent))), phase)

    def check_cancelled() -> None:
        if effective_controller.cancel_requested:
            raise ProcessCancelled("ODB merge cancelled by user")

    def copy_file(source: Path, destination: Path) -> None:
        check_cancelled()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as source_file, destination.open("xb") as target_file:
            while block := source_file.read(8 * 1024 * 1024):
                target_file.write(block)
                check_cancelled()
        shutil.copystat(source, destination)

    def run(arguments: tuple[str, ...]) -> str:
        captured: list[str] = []

        def capture(message: str) -> None:
            captured.append(message)
            if log is not None:
                log(message)

        run_process(
            [plan.request.abaqus_command, *arguments],
            plan.staging_dir,
            capture,
            effective_controller,
        )
        return "\n".join(captured)

    def publish(source: Path, destination: Path, *, overwrite: bool = False) -> None:
        if overwrite:
            os.replace(source, destination)
            published.append(destination)
            return
        try:
            os.link(source, destination)
        except FileExistsError as exc:
            raise OdbMergeError(f"发布结果时目标文件已存在：{destination}") from exc
        except OSError as exc:
            raise OdbMergeError(f"无法发布文件到 {destination}：{exc}") from exc
        source.unlink()
        published.append(destination)

    try:
        plan.staging_dir.mkdir()
        report(5, "正在复制原始 ODB 的安全副本…")
        copy_file(plan.request.original_odb, plan.staged_original_backup)
        report(25, "正在复制重启动 ODB 的安全副本…")
        copy_file(plan.request.restart_odb, plan.staged_restart_backup)
        report(45, "正在创建隔离合并工作副本…")
        copy_file(plan.staged_original_backup, plan.working_odb)

        check_cancelled()
        plan.validation_script.write_text(_VALIDATION_SCRIPT, encoding="utf-8")
        report(60, "正在执行 Abaqus restartjoin…")
        if log is not None:
            log(f"命令：{plan.command_preview()}")
        run(plan.restartjoin_arguments)
        if (
            not plan.restartjoin_output_odb.is_file()
            or plan.restartjoin_output_odb.stat().st_size <= 0
        ):
            raise OdbMergeError("restartjoin 未生成有效的非空 ODB。")

        report(82, "正在使用 Abaqus 只读打开并验证结果…")
        validation_output = run(plan.validation_arguments)
        if "ABASUB_ODB_VALIDATION_OK" not in validation_output:
            raise OdbMergeError("Abaqus 未返回 ODB 只读验证成功标记。")

        check_cancelled()
        report(92, "正在原子发布安全副本和合并结果…")
        publish(plan.staged_original_backup, plan.original_backup)
        publish(plan.staged_restart_backup, plan.restart_backup)
        publish(
            plan.restartjoin_output_odb,
            plan.request.output_odb,
            overwrite=plan.request.conflict_policy == MergeConflictPolicy.OVERWRITE,
        )
        report(100, "ODB 合并与只读验证完成。")
        return OdbMergeResult(
            output_odb=plan.request.output_odb,
            original_backup=plan.original_backup,
            restart_backup=plan.restart_backup,
            command=plan.command_preview(),
        )
    except BaseException:
        # Backups are new files selected by the planner. If publication fails
        # before the result is committed, remove only files created in this run.
        if plan.request.output_odb not in published:
            for path in reversed(published):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        raise
    finally:
        shutil.rmtree(plan.staging_dir, ignore_errors=True)


__all__ = [
    "LogCallback",
    "ProgressCallback",
    "execute_odb_merge",
]
