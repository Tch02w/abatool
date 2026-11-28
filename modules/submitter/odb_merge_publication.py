"""Identify a locally published ODB after a control-plane process interruption."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .odb_merge_core import (
    MergeConflictPolicy,
    OdbMergeRequest,
    _source_stem,
    normalize_joined_output,
)

PREPARED_RECEIPT = "publication-ready.json"
PREVIOUS_TARGET = "previous-target.odb"


def file_identity(path: Path) -> dict[str, str] | None:
    info = path.stat()
    if not info.st_dev or not info.st_ino:
        return None
    return {
        "volume": str(info.st_dev),
        "fileId": str(info.st_ino),
        "size": str(info.st_size),
        "mtimeNs": str(info.st_mtime_ns),
    }


def publish_receipt(
    prepared: Path, receipt: Path, output: Path, identity: dict[str, str] | None
) -> None:
    if identity and file_identity(output) != identity:
        raise ValueError("发布回执时目标 ODB 已改变")
    os.link(prepared, receipt)
    if identity:
        confirmed = False
        try:
            confirmed = file_identity(output) == identity
            if not confirmed:
                raise ValueError("发布回执时目标 ODB 已改变")
        finally:
            if not confirmed and receipt.samefile(prepared):
                receipt.unlink()


def recover_publication(request: OdbMergeRequest, attempt: str) -> str:
    """Return a conservative operator message. Never rerun or replace the ODB."""
    if not re.fullmatch("[0-9a-f]{32}", attempt):
        return ""
    target = normalize_joined_output(request.output_odb).absolute()
    stage = target.parent / (".abasub-odb-merge-" + attempt)
    prepared = stage / PREPARED_RECEIPT
    direct = target.with_suffix(f".{attempt}.merge-validation.json")
    try:
        if prepared.is_file():
            path = prepared
        elif direct.is_file():
            path = direct
        elif request.conflict_policy == MergeConflictPolicy.AUTO_NUMBER:
            # Execution may have numbered the output again after acceptance.
            files = list(target.parent.glob(f"*.{attempt}.merge-validation.json"))
            if len(files) != 1:
                return ""
            path = files[0]
        else:
            return ""
        if path.is_symlink() or stage.is_symlink():
            return ""
        validation = json.loads(path.read_text(encoding="utf-8"))
        output = Path(validation["joinedPath"])
        if output != target and (
            request.conflict_policy != MergeConflictPolicy.AUTO_NUMBER
            or output.parent != target.parent
            or not re.fullmatch(re.escape(target.stem) + r"_\d+\.odb", output.name)
        ):
            return ""
        receipt = output.with_suffix(f".{attempt}.merge-validation.json")
        if (
            validation.get("attemptId") != attempt
            or validation.get("status") != "verified"
            or Path(validation["originalPath"]) != request.original_odb
            or Path(validation["restartPath"]) != request.restart_odb
            or validation.get("includeHistory") is not request.include_history
            or path not in (prepared, receipt)
        ):
            return ""
        identity = validation.get("validatedFile")
        if not identity:
            return "无法取得可靠的本机文件身份，发布状态待核对。"
        if not output.exists():
            return "目标位置没有 ODB，无法确认本次输出。"
        if output.is_symlink() or not output.is_file():
            return "目标位置已变更，无法确认发布。"
        if file_identity(output) != identity:
            previous = stage / PREVIOUS_TARGET
            if (
                validation.get("previousFile")
                and previous.is_file()
                and not previous.is_symlink()
                and file_identity(output) == validation["previousFile"]
            ):
                return "当前目标仍是替换前的 ODB，未确认本次结果已发布。"
            return "当前目标与已验证候选的本机文件身份不符，无法确认已发布。请保留现有文件。"
        backups = []
        for prefix, source in (
            ("original", request.original_odb),
            ("restart", request.restart_odb),
        ):
            backup = Path(validation[prefix + "Backup"])
            stamp = validation.get(prefix + "BackupFile")
            name = re.escape(_source_stem(source)) + r"_original(?:_\d+)?\.odb"
            if (
                backup.parent != output.parent
                or not re.fullmatch(name, backup.name, re.IGNORECASE)
                or backup
                in (output, request.original_odb, request.restart_odb, *backups)
                or backup.is_symlink()
                or not stamp
                or file_identity(backup) != stamp
            ):
                return "目标身份一致，但无法确认本次源备份完整，已保留现场。"
            backups.append(backup)
        if path == prepared:
            if receipt.exists():
                if (
                    receipt.is_symlink()
                    or json.loads(receipt.read_text(encoding="utf-8")) != validation
                ):
                    return (
                        "目标与已验证候选身份一致，但已有同名回执内容不符，已保留现场。"
                    )
            else:
                # Same-volume, exclusive creation. Never overwrite another receipt.
                publish_receipt(prepared, receipt, output, identity)
        return f"已确认目标是本次验证过的本机 ODB，校验回执已保存：{receipt}。"
    except OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError:
        return "无法核对本次发布文件和回执，请保留目标与工作目录。"
