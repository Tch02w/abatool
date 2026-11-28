"""Qt-free protected ODB merge execution shared by native frontends."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path

from modules.postprocessor.config import abaqus_script
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


def _identity(path: Path) -> tuple[int, int, int, int, int]:
    state = path.stat()
    return (
        state.st_dev,
        state.st_ino,
        state.st_size,
        state.st_mtime_ns,
        state.st_ctime_ns,
    )


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
    source_identities = {
        path: _identity(path)
        for path in (plan.request.original_odb, plan.request.restart_odb)
    }
    validation_file = plan.staging_dir / "merge_validation.json"
    published_validation = plan.request.output_odb.with_suffix(
        "." + plan.staging_dir.name.rsplit("-", 1)[-1] + ".merge-validation.json"
    )

    def report(percent: int, phase: str) -> None:
        if progress is not None:
            progress(max(0, min(100, int(percent))), phase)

    def check_cancelled() -> None:
        if effective_controller.cancel_requested:
            raise ProcessCancelled("ODB merge cancelled by user")

    def check_sources() -> None:
        for path, identity in source_identities.items():
            if _identity(path) != identity:
                raise OdbMergeError(f"合并期间源 ODB 发生变化，结果未发布：{path}")

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
        validation_marker: str | None = None

        def capture(message: str) -> None:
            nonlocal validation_marker
            captured.append(message)
            if arguments == plan.validation_arguments and message.startswith(
                "ABASUB_ODB_VALIDATION_FAILED|"
            ):
                validation_marker = message.partition("|")[2]
            if log is not None:
                log(message)

        try:
            run_process(
                [plan.request.abaqus_command, *arguments],
                plan.staging_dir,
                capture,
                effective_controller,
            )
        except ProcessCancelled:
            raise
        except RuntimeError:
            if validation_marker is None:
                raise
        if validation_marker is not None:
            validation_reason = json.loads(validation_marker)
            if not isinstance(validation_reason, str):
                raise OdbMergeError("ODB 合并内容校验返回了无效的错误说明。")
            if validation_reason.startswith(
                "History contains samples not present in the source: "
            ):
                channel = validation_reason.partition(": ")[2]
                raise OdbMergeError(
                    f"合并后的历史含源文件未记录的样本：{channel}。请分段查看源历史；"
                    "只需场结果时，可取消勾选历史输出后重新执行。"
                )
            raise OdbMergeError(f"ODB 合并内容校验失败：{validation_reason}")
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
        check_sources()
        shutil.copyfile(abaqus_script("validate_odb_merge.py"), plan.validation_script)
        report(60, "正在执行 Abaqus restartjoin…")
        if log is not None:
            log(f"命令：{plan.command_preview()}")
        run(plan.restartjoin_arguments)
        if (
            not plan.restartjoin_output_odb.is_file()
            or plan.restartjoin_output_odb.stat().st_size <= 0
        ):
            raise OdbMergeError("restartjoin 未生成有效的非空 ODB。")

        report(82, "正在逐分析步核对帧、场输出和历史数据…")
        validation_output = run(plan.validation_arguments)
        if "ABASUB_ODB_VALIDATION_OK" not in validation_output:
            raise OdbMergeError("Abaqus 未返回 ODB 只读验证成功标记。")
        try:
            validation = json.loads(validation_file.read_text(encoding="utf-8"))
            expected_paths = {
                "originalPath": plan.staged_original_backup,
                "restartPath": plan.staged_restart_backup,
                "joinedPath": plan.restartjoin_output_odb,
            }
            if (
                validation.get("schemaVersion") != 1
                or validation.get("status") != "verified"
                or validation.get("includeHistory") is not plan.request.include_history
                or not validation.get("steps")
                or any(
                    Path(validation.get(key, "")).resolve() != value.resolve()
                    for key, value in expected_paths.items()
                )
            ):
                raise ValueError("验证回执与本次合并输入不符")
        except (OSError, ValueError, TypeError, AttributeError) as error:
            raise OdbMergeError(f"合并内容校验未生成有效回执：{error}") from error

        empty_frame_steps = tuple(
            step["name"] for step in validation["steps"] if step["frames"] == 0
        )
        if empty_frame_steps and log is not None:
            log(
                "以下分析步没有结果帧，已按源文件保留；合并成功不表示计算完成："
                + "、".join(empty_frame_steps)
            )
        check_cancelled()
        check_sources()
        validation.update(
            originalPath=str(plan.request.original_odb),
            restartPath=str(plan.request.restart_odb),
            joinedPath=str(plan.request.output_odb),
            originalBackup=str(plan.original_backup),
            restartBackup=str(plan.restart_backup),
        )
        validation_file.write_text(
            json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        report(92, "正在保存安全副本并发布合并结果…")
        publish(plan.staged_original_backup, plan.original_backup)
        publish(plan.staged_restart_backup, plan.restart_backup)
        publish(validation_file, published_validation)
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
            validation_report=published_validation,
            empty_frame_steps=empty_frame_steps,
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
