"""Resume a validated archive checkpoint without invoking a solver."""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from uuid import uuid4

from .local_archive import (
    MANIFEST_NAME,
    ArchiveCancelled,
    ArchiveIntegrityError,
    _copy_verified,
    _digest,
    _identity,
    _inventory,
    _linked,
    _publish,
    archive_job_files,
    cleanup_verified,
)
from .local_archive_state import ArchiveStateError

LOGGER = logging.getLogger(__name__)


def _relative(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ArchiveStateError("归档相对路径无效")
    path = Path(value)
    if (path.is_absolute() or path.as_posix() != value
            or any(p in {"", ".", ".."} or ":" in p for p in value.split("/"))
            or (os.name == "nt" and os.path.isreserved(value))):
        raise ArchiveStateError("归档相对路径越界")
    return path


def _plan(item, state):
    if (not isinstance(state.get("files"), dict) or not isinstance(state.get("directories"), list)
            or any(not isinstance(state.get(key), str) for key in ("root", "stage", "destination"))):
        raise ArchiveStateError("归档文件计划的格式无效")
    root, stage, final = (Path(state[key]) for key in ("root", "stage", "destination"))
    if any(not p.is_absolute() or p.resolve() != p for p in (root, stage, final)):
        raise ArchiveStateError("归档记录路径包含链接或相对路径")
    if stage.parent != root or final.parent != root or stage == final:
        raise ArchiveStateError("归档目标越过记录的根目录")
    if not re.fullmatch(re.escape("." + item.job_name + ".archive-") + r"[0-9a-f]{32}\.partial", stage.name):
        raise ArchiveStateError("归档临时目录身份无效")
    if final.name != item.job_name and not re.fullmatch(re.escape(item.job_name) + r"_[0-9a-f]{32}", final.name):
        raise ArchiveStateError("归档最终目录身份无效")
    files = {}
    for key, value in state["files"].items():
        if not isinstance(value, list) or len(value) != 4 or any(type(n) is not int or n < 0 for n in value):
            raise ArchiveStateError("归档源文件身份无效")
        files[_relative(key)] = tuple(value)
    directories = [_relative(p) for p in state["directories"]]
    if (not files or len(files) != len(state["files"]) or Path(MANIFEST_NAME) in files
            or len(set(directories)) != len(directories) or set(files) & set(directories)):
        raise ArchiveStateError("归档文件清单无效")
    if state["cleanup"]:
        source = Path(state["source"])
        if (not item.calculation_root_dir or Path(item.calculation_root_dir).resolve() / item.job_name != source
                or (item.source_inp_path and Path(item.source_inp_path).resolve().is_relative_to(source))):
            raise ArchiveStateError("恢复清理仅允许不含原始 INP 的独立计算目录")
    return root, stage, final, files, directories


def _manifest(item, source, records):
    return {"schemaVersion": 1, "state": "complete", "jobName": item.job_name,
            "attemptId": item.attempt_id, "sourceDirectory": str(source), "files": records}


def _check_manifest(item, source, final, state, files, check):
    manifest = state.get("manifest")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        raise ArchiveIntegrityError("归档记录缺少发布清单")
    records = manifest["files"]
    if manifest != _manifest(item, source, records) or set(records) != {p.as_posix() for p in files}:
        raise ArchiveIntegrityError("发布清单的执行身份或文件范围不符")
    path = final / MANIFEST_NAME
    if path.resolve() != path or json.loads(path.read_text(encoding="utf-8")) != manifest:
        raise ArchiveIntegrityError("最终归档清单与持久记录不符")
    for relative, identity in files.items():
        check()
        record, target = records[relative.as_posix()], final / relative
        if (not isinstance(record, dict) or record.get("bytes") != identity[2]
                or not isinstance(record.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])):
            raise ArchiveIntegrityError("归档摘要记录无效")
        if target.resolve() != target or target.stat().st_size != identity[2] or _digest(target, check) != record["sha256"]:
            raise ArchiveIntegrityError(f"归档文件完整性校验失败：{target}")
    return records


def resume_archive(item, state, *, cancelled=lambda: False, progress=None, checkpoint=None):
    if state["phase"] == "confirmed":
        return archive_job_files(item, Path(state["source"]), cancelled=cancelled, progress=progress, checkpoint=checkpoint)
    final = None
    published = verified = False
    try:
        root, stage, final, files, directories = _plan(item, state)
        source = Path(state["source"])
        if root.is_relative_to(source):
            raise ArchiveStateError("归档根目录位于计算目录内")
        published = final.exists() and state["phase"] in {"ready", "published", "done"}
        if state["phase"] in {"published", "done"} and not published:
            raise ArchiveIntegrityError("已发布的归档目录丢失，未重建或清理源文件")

        def check():
            if cancelled():
                raise ArchiveCancelled("已取消归档恢复")
            if source.resolve() != source or root.resolve() != root or _linked(source):
                raise ArchiveStateError("恢复期间目录路径发生变化")
            if not published and not source.is_dir():
                raise ArchiveStateError("源计算目录不存在")
            if any(source.glob("*.lck")) or any(source.glob("*.LCK")):
                raise ArchiveStateError("仍存在 LCK，未恢复归档")

        check()
        if Path(item.archive_dir).resolve() != root:
            if published or state["phase"] in {"ready", "published", "done"}:
                raise ArchiveStateError("发布阶段不能更换归档根目录，请先恢复原配置")
            if _inventory(source, item, bool(state["cleanup"])) != (files, directories):
                raise ArchiveStateError("源文件与原归档记录不符，未更换归档位置")
            return archive_job_files(item, source, cancelled=cancelled, progress=progress, checkpoint=checkpoint)

        if published:
            if progress:
                progress("正在核对已发布归档", 0, 1)
            records = _check_manifest(item, source, final, state, files, check)
            verified = True
        else:
            if _inventory(source, item, bool(state["cleanup"])) != (files, directories):
                raise ArchiveStateError("源文件与中断前不同，未重新复制或清理")
            root.mkdir(parents=True, exist_ok=True)
            stage.mkdir(exist_ok=True)
            for relative in directories:
                target = stage / relative
                if target.resolve() != target:
                    raise ArchiveStateError("临时目录包含链接")
                target.mkdir(exist_ok=True)
            expected = set(files) | set(directories) | {Path(MANIFEST_NAME)}
            if any(p.relative_to(stage) not in expected or p.resolve() != p for p in stage.rglob("*")):
                raise ArchiveStateError("临时目录含未知文件，未覆盖现场")
            records = {}
            for index, (relative, identity) in enumerate(files.items()):
                check()
                src, target = source / relative, stage / relative
                if _identity(src) != identity or target.resolve() != target:
                    raise ArchiveStateError("归档源或目标发生变化")
                if progress:
                    progress(f"正在核对并恢复归档：{relative}", index, len(files))
                digest = _digest(src, check)
                if not target.is_file() or _digest(target, check) != digest:
                    if target.exists():
                        # Preserve interrupted payloads outside the published directory.
                        evidence = root / ("." + item.job_name + ".recovery-" + uuid4().hex)
                        evidence.mkdir()
                        saved = evidence / relative
                        saved.parent.mkdir(parents=True, exist_ok=True)
                        if not target.resolve().is_relative_to(stage) or not saved.resolve().is_relative_to(evidence):
                            raise ArchiveStateError("中断文件保留路径越界")
                        if checkpoint:
                            checkpoint(state["phase"], {"evidence": [*state.get("evidence", []), str(evidence)]})
                        target.rename(saved)
                    digest = _copy_verified(src, target, identity, check, lambda _: None)
                if _identity(src) != identity:
                    raise ArchiveStateError("源文件在恢复过程中变化")
                records[relative.as_posix()] = {"bytes": identity[2], "sha256": digest}
            check()
            if _inventory(source, item, bool(state["cleanup"])) != (files, directories):
                raise ArchiveStateError("恢复期间源目录内容变化，未发布或清理")
            manifest = _manifest(item, source, records)
            path = stage / MANIFEST_NAME
            if path.exists():
                if json.loads(path.read_text(encoding="utf-8")) != manifest:
                    raise ArchiveIntegrityError("临时归档清单不符，未覆盖")
            else:
                with path.open("x", encoding="utf-8") as output:
                    json.dump(manifest, output, ensure_ascii=False, indent=2)
                    output.flush()
                    os.fsync(output.fileno())
            if checkpoint:
                checkpoint("ready", {"manifest": manifest})
            check()
            _publish(stage, final)
            published = verified = True
        if checkpoint:
            checkpoint("published", {})
        if state["cleanup"] and source.exists():
            if progress:
                progress("归档已核对，继续清理计算目录", 1, 1)
            # Missing captured files/directories are allowed after a prior partial cleanup.
            current_files, current_dirs = _inventory(source, item, True, allow_empty=True)
            if any(files.get(p) != value for p, value in current_files.items()) or not set(current_dirs) <= set(directories):
                raise ArchiveStateError("计算目录出现新文件或变化，未继续清理")
            cleanup_verified(source, final, files, directories, records, check, allow_missing=True)
        if checkpoint:
            checkpoint("done", {})
        return str(final), "已归档", ""
    except Exception as exc:
        LOGGER.exception("归档恢复中断，未重新启动求解")
        if published:
            return str(final), ("已归档，清理未完成" if verified and not isinstance(exc, ArchiveIntegrityError)
                                else "归档待恢复" if isinstance(exc, ArchiveCancelled) else "归档需核对"), str(exc)
        return "", "归档已取消" if isinstance(exc, ArchiveCancelled) else "归档失败", str(exc)
