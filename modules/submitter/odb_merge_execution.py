"""Qt-free protected ODB merge execution shared by native frontends."""

from __future__ import annotations

import errno
import json
import logging
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
from .odb_merge_publication import (
    PREPARED_RECEIPT,
    PREVIOUS_TARGET,
    file_identity,
    publish_receipt,
)

ProgressCallback = Callable[[int, str], None]
LogCallback = Callable[[str], None]


class _ExtraInitialHistoryZero(OdbMergeError):
    """The native join added exactly one zero to a resumed real series."""


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
    keep_staging = False
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
        disk_full = False

        def capture(message: str) -> None:
            nonlocal validation_marker, disk_full
            captured.append(message)
            disk_full = disk_full or any(
                text in message.casefold()
                for text in (
                    "no space left on device",
                    "there is not enough space on the disk",
                    "磁盘空间不足",
                )
            )
            if arguments[0] == "python" and message.startswith(
                (
                    "ABASUB_ODB_VALIDATION_FAILED|",
                    "ABASUB_ODB_EXTRA_INITIAL_ZERO|",
                    "ABASUB_ODB_RESTORE_FAILED|",
                )
            ):
                validation_marker = message
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
            if validation_marker is None and not disk_full:
                raise
        if disk_full:
            raise OdbMergeError("目标磁盘或 Abaqus 临时目录空间不足，合并未发布。")
        if validation_marker is not None:
            category, _, detail = validation_marker.partition("|")
            validation_reason = json.loads(detail)
            if not isinstance(validation_reason, str):
                raise OdbMergeError("ODB 合并内容校验返回了无效的错误说明。")
            if category == "ABASUB_ODB_EXTRA_INITIAL_ZERO":
                raise _ExtraInitialHistoryZero(validation_reason)
            if category == "ABASUB_ODB_RESTORE_FAILED":
                raise OdbMergeError(f"无法保留源历史，合并未发布：{validation_reason}")
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
        published.append(destination)
        source.unlink()

    # A pre-existing folder belongs to another attempt or its recovery evidence.
    plan.staging_dir.mkdir()
    try:
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
        restored_history = False
        try:
            validation_output = run(plan.validation_arguments)
        except _ExtraInitialHistoryZero as extra:
            if not request.include_history:
                raise
            check_cancelled()
            check_sources()
            report(84, "检测到额外的起始零点，正在按源记录重建历史…")
            check_cancelled()
            if log:
                log(f"历史通道多出起始零点：{extra}")
            # Release the rejected utility output before copying another large ODB.
            # Both names were reserved in this invocation's private staging folder.
            for private_path in {plan.working_odb, plan.restartjoin_output_odb}:
                if private_path.resolve().parent != plan.staging_dir.resolve():
                    raise OdbMergeError("合并工作副本路径已改变。")
                private_path.unlink()
            if (
                shutil.disk_usage(plan.staging_dir).free
                < plan.staged_original_backup.stat().st_size
            ):
                raise OdbMergeError(
                    "目标磁盘空间不足，无法创建历史重建所需的工作副本。"
                )
            copy_file(plan.staged_original_backup, plan.working_odb)
            run(tuple(arg for arg in plan.restartjoin_arguments if arg != "history"))
            check_cancelled()
            worker = plan.staging_dir / "restore_odb_history.py"
            shutil.copyfile(abaqus_script(worker.name), worker)
            restore_output = run(
                (
                    "python",
                    worker.name,
                    plan.staged_original_backup.name,
                    plan.staged_restart_backup.name,
                    plan.restartjoin_output_odb.name,
                )
            )
            if "ABASUB_ODB_HISTORY_RESTORED" not in restore_output.splitlines():
                raise OdbMergeError("历史数据重建未完成，合并未发布。")
            check_cancelled()
            report(88, "正在重新打开结果，逐项核对场帧、历史位置及数据…")
            check_cancelled()
            validation_output = run((*plan.validation_arguments, "--restored"))
            restored_history = True
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
                or (
                    restored_history
                    and validation.get("historyMethod") != "source-samples"
                )
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
            attemptId=plan.staging_dir.name.rsplit("-", 1)[-1],
            validatedFile=file_identity(plan.restartjoin_output_odb),
            originalBackupFile=file_identity(plan.staged_original_backup),
            restartBackupFile=file_identity(plan.staged_restart_backup),
        )
        prepared = plan.staging_dir / PREPARED_RECEIPT
        previous = plan.staging_dir / PREVIOUS_TARGET
        if (
            plan.request.conflict_policy == MergeConflictPolicy.OVERWRITE
            and plan.request.output_odb.exists()
        ):
            validation["previousFile"] = file_identity(plan.request.output_odb)
            try:
                os.link(plan.request.output_odb, previous)
            except PermissionError, NotImplementedError:
                # File-specific ACLs may allow replacement but forbid linking the old target.
                copy_file(plan.request.output_odb, previous)
            validation["previousBackupFile"] = file_identity(previous)
            if file_identity(plan.request.output_odb) != validation["previousFile"]:
                raise OdbMergeError("发布准备期间已有目标 ODB 发生变化。")
        prepared.write_text(
            json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if published_validation.exists():
            raise OdbMergeError(f"目标目录已有本次编号的回执：{published_validation}")
        check_cancelled()
        check_sources()
        report(92, "正在保存安全副本并发布合并结果…")
        publish(plan.staged_original_backup, plan.original_backup)
        publish(plan.staged_restart_backup, plan.restart_backup)
        if (
            previous.exists()
            and file_identity(plan.request.output_odb) != validation["previousFile"]
        ):
            raise OdbMergeError("已有目标在最终替换前发生变化，合并未发布。")
        publish(
            plan.restartjoin_output_odb,
            plan.request.output_odb,
            overwrite=previous.exists(),
        )
        # Readers must never see a public success receipt before its ODB is in place.
        publish_receipt(
            prepared,
            published_validation,
            plan.request.output_odb,
            validation["validatedFile"],
        )
        published.append(published_validation)
        try:
            report(100, "ODB 合并与只读验证完成。")
        except Exception:  # Observers cannot undo a committed ODB and receipt.
            logging.getLogger(__name__).exception("ODB 已发布，但完成进度通知失败")
        return OdbMergeResult(
            output_odb=plan.request.output_odb,
            original_backup=plan.original_backup,
            restart_backup=plan.restart_backup,
            command=plan.command_preview(),
            validation_report=published_validation,
            empty_frame_steps=empty_frame_steps,
        )
    except BaseException as error:
        # If only the last small receipt failed, restore the old result by its
        # same-volume link. Do not overwrite a target changed by another writer.
        if (
            plan.request.output_odb in published
            and published_validation not in published
        ):
            keep_staging = True
            try:
                if (
                    not validation["validatedFile"]
                    or file_identity(plan.request.output_odb)
                    != validation["validatedFile"]
                ):
                    raise OdbMergeError("目标文件身份已改变")
                if "previousFile" in validation:
                    if (
                        not validation["previousBackupFile"]
                        or file_identity(previous) != validation["previousBackupFile"]
                    ):
                        raise OdbMergeError("旧目标备份身份已改变")
                    os.replace(previous, plan.request.output_odb)
                else:
                    plan.request.output_odb.unlink()
            except (OSError, OdbMergeError) as rollback_error:
                raise OdbMergeError(
                    f"发布回执失败且暂时无法恢复目标。请保留 {plan.staging_dir} 并核对目标：{rollback_error}"
                ) from error
            published.remove(plan.request.output_odb)
            keep_staging = False
        if plan.request.output_odb not in published:
            for path in reversed(published):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        if (
            plan.request.output_odb not in published
            and isinstance(error, OSError)
            and (
                error.errno == errno.ENOSPC
                or getattr(error, "winerror", None) in (39, 112)
            )
        ):
            raise OdbMergeError("目标磁盘空间不足，ODB 合并未发布。") from error
        raise
    finally:
        if not keep_staging:
            shutil.rmtree(plan.staging_dir, ignore_errors=True)


__all__ = [
    "LogCallback",
    "ProgressCallback",
    "execute_odb_merge",
]
