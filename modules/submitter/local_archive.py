"""Qt-free archive publication: verify a full copy before optional source cleanup."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import stat
import time
from pathlib import Path
from uuid import uuid4

ARCHIVE_EXTENSIONS = (".inp", ".odb", ".sta", ".msg", ".dat", ".log", ".com", ".prt",
                      ".sim", ".res", ".mdl", ".stt", ".fil", ".pac")
PUBLISHED_STATUSES = frozenset({"已归档", "已归档，清理未完成"})
MANIFEST_NAME = ".abaqustools-archive.json"
CHUNK_BYTES = 4 * 1024 * 1024
LOGGER = logging.getLogger(__name__)


class ArchiveCancelled(InterruptedError):
    pass


class ArchiveIntegrityError(RuntimeError):
    pass


def archive_published(status, destination):
    return bool(destination) and status in PUBLISHED_STATUSES


def _linked(path):
    return path.is_symlink() or path.is_junction()


def _identity(path):
    value = path.stat()
    if not stat.S_ISREG(value.st_mode):
        raise ValueError(f"归档对象不是普通文件：{path}")
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def _inventory(source, item, full):
    files, directories = {}, []

    def visit(directory):
        for path in sorted(directory.iterdir()):
            if _linked(path):
                raise ValueError(f"归档目录中存在链接，未移动原文件：{path}")
            if path.suffix.casefold() == ".lck":
                raise RuntimeError(f"检测到 LCK，暂不归档或清理：{path}")
            if path.is_dir():
                directories.append(path.relative_to(source))
                visit(path)
            else:
                files[path.relative_to(source)] = _identity(path)

    if full:
        visit(source)
    else:
        names = {item.job_name + ext for ext in ARCHIVE_EXTENSIONS}
        input_name = Path(item.source_inp_path or item.inp_path).name
        if input_name and Path(input_name).suffix.casefold() == ".inp":
            names.add(input_name)
        for name in sorted(names):
            path = source / name
            if _linked(path):
                raise ValueError(f"归档文件不能是链接：{path}")
            if path.exists():
                files[Path(name)] = _identity(path)
    if Path(MANIFEST_NAME) in files:
        raise ValueError("工作目录含归档清单，需先核对目录来源")
    if not files:
        raise ValueError("未找到可归档文件，未发布空归档")
    return files, directories


def _digest(path, check):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            check()
            digest.update(chunk)
    check()
    return digest.hexdigest()


def _copy_verified(source, target, expected, check, tick):
    if source.resolve() != source or target.resolve() != target:
        raise ValueError("归档文件路径包含链接")
    if _identity(source) != expected:
        raise RuntimeError(f"归档期间源文件发生变化：{source}")
    digest = hashlib.sha256()
    with source.open("rb") as reader, target.open("xb") as writer:
        while chunk := reader.read(CHUNK_BYTES):
            check()
            writer.write(chunk)
            digest.update(chunk)
            tick(len(chunk))
        writer.flush()
        os.fsync(writer.fileno())
    if _identity(source) != expected or _digest(target, check) != digest.hexdigest():
        raise RuntimeError(f"归档校验失败，原文件保留：{source}")
    os.utime(target, ns=(source.stat().st_atime_ns, expected[3]))
    return digest.hexdigest()


def _publish(stage, destination):
    # Windows rename refuses an existing target. Stage and destination share a volume.
    if stage.resolve() != stage or destination.exists() or _linked(destination):
        raise FileExistsError(f"归档目标已存在，未覆盖：{destination}")
    stage.rename(destination)


def archive_job_files(item, work_dir, *, cancelled=lambda: False, progress=None):
    if not item.archive_dir:
        return "", "", ""
    stage = None
    destination = None
    published = False
    try:
        source = Path(work_dir).absolute()
        if _linked(source) or not source.is_dir():
            raise ValueError("计算工作目录不存在或为目录链接")
        source = source.resolve(strict=True)
        root = Path(item.archive_dir).resolve()
        if not item.job_name or any(c in item.job_name for c in '/\\:') or item.job_name in {".", ".."}:
            raise ValueError("归档作业名称无效")
        if os.name == "nt" and os.path.isreserved(item.job_name):
            raise ValueError("归档作业名称不能使用系统保留名称")
        if root.is_relative_to(source):
            raise ValueError("归档目录不能位于计算工作目录内")
        full = bool(item.cleanup_after_archive)
        if full:
            expected = Path(item.calculation_root_dir).resolve() / item.job_name if item.calculation_root_dir else None
            if expected != source:
                raise ValueError("清理仅允许指定计算根目录下的独立作业目录")
            if item.source_inp_path and Path(item.source_inp_path).resolve().is_relative_to(source):
                raise ValueError("原始 INP 位于计算目录内，拒绝清理原始输入")

        def check():
            if cancelled():
                raise ArchiveCancelled("已取消归档或清理")
            if _linked(source) or source.resolve() != source or not source.is_dir():
                raise RuntimeError("归档期间计算目录发生变化")
            if any(source.glob("*.lck")) or any(source.glob("*.LCK")):
                raise RuntimeError("检测到 LCK，已停止归档或清理")
            if root.resolve() != root:
                raise RuntimeError("归档期间目标根目录发生变化")

        check()
        files, directories = _inventory(source, item, full)
        root.mkdir(parents=True, exist_ok=True)
        destination = root / item.job_name
        if destination.exists() or _linked(destination):
            destination = root / f"{item.job_name}_{uuid4().hex}"
        # Both publication paths are checked before creating or moving anything.
        if destination.resolve().parent != root or destination.resolve().is_relative_to(source):
            raise ValueError("归档目标不在指定根目录下")
        stage = root / f".{item.job_name}.archive-{uuid4().hex}.partial"
        stage.mkdir()
        for relative in directories:
            (stage / relative).mkdir()
        total = sum(value[2] for value in files.values())
        copied, last_report = 0, 0.0

        def tick(count):
            nonlocal copied, last_report
            copied += count
            now = time.monotonic()
            if progress and now - last_report >= 0.2:
                progress("正在复制并校验归档", copied, total)
                last_report = now

        records = {}
        for relative, identity in files.items():
            check()
            digest = _copy_verified(source / relative, stage / relative, identity, check, tick)
            records[relative.as_posix()] = {"bytes": identity[2], "sha256": digest}
        check()
        if _inventory(source, item, full) != (files, directories):
            raise RuntimeError("归档期间工作目录内容发生变化，原文件保留")
        manifest = {"schemaVersion": 1, "state": "complete", "jobName": item.job_name,
                    "attemptId": item.attempt_id, "sourceDirectory": str(source), "files": records}
        with (stage / MANIFEST_NAME).open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        check()
        _publish(stage, destination)
        published = True
        if full:
            if progress:
                progress("归档已校验，正在清理计算目录", total, total)
            check()
            if _inventory(source, item, True) != (files, directories):
                raise RuntimeError("归档已发布，但源目录已变化，未开始清理")
            for relative, identity in files.items():
                check()
                path = source / relative
                # Never recurse-delete a directory or remove an unverified/new file.
                archived = destination / relative
                if path.resolve() != path or _linked(path):
                    raise RuntimeError(f"清理目标发生变化：{path}")
                digest = records[relative.as_posix()]["sha256"]
                try:
                    if archived.resolve() != archived or _digest(archived, check) != digest:
                        raise ArchiveIntegrityError(f"已发布归档发生变化，停止清理：{archived}")
                except OSError as exc:
                    if isinstance(exc, ArchiveCancelled):
                        raise
                    raise ArchiveIntegrityError(f"已发布归档不可读，停止清理：{archived}") from exc
                if _identity(path) != identity or _digest(path, check) != digest:
                    raise RuntimeError(f"清理校验失败，保留原文件：{path}")
                check()
                path.unlink()
            for relative in sorted(directories, key=lambda p: len(p.parts), reverse=True):
                check()
                directory = source / relative
                if _linked(directory) or not directory.resolve().is_relative_to(source):
                    raise RuntimeError(f"清理目录发生变化：{directory}")
                directory.rmdir()
            check()
            source.rmdir()
        return str(destination), "已归档", ""
    except Exception as exc:
        LOGGER.exception("归档未正常结束；保留已确认的求解结果和归档现场")
        if published:
            status = "归档需核对" if isinstance(exc, ArchiveIntegrityError) else "已归档，清理未完成"
            return str(destination), status, str(exc)
        detail = str(exc)
        if stage is not None:
            detail += f"；未发布目录保留供检查：{stage}"
        return "", "归档已取消" if isinstance(exc, ArchiveCancelled) else "归档失败", detail
