"""Read-only local preparation planning and protected per-file publication."""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from .command import queue_item_to_options, validate_options
from .constants import MAX_CPUS

RESTART_EXTENSIONS = (".odb", ".res", ".stt", ".sim", ".mdl", ".prt", ".sta", ".msg", ".dat", ".log", ".com")
RESULT_EXTENSIONS = (".odb", ".sta")
LOGGER = logging.getLogger(__name__)


class WorkspacePreparationCancelled(InterruptedError):
    pass


@dataclass(frozen=True)
class LocalWorkspacePlan:
    job_name: str
    source_inp: Path
    prepared_inp: Path
    work_dir: Path
    oldjob: Path | None
    oldjob_arg: str
    copies: tuple[tuple[Path, Path], ...]


def _linked(path):
    return path.is_symlink() or path.is_junction()


def check_existing_results(work_dir, job_name, policy):
    if policy not in {"backup", "overwrite", "cancel"}:
        raise ValueError("existing result policy must be backup, overwrite, or cancel")
    lock = work_dir / f"{job_name}.lck"
    if lock.exists() or _linked(lock):
        raise RuntimeError(f"检测到同名 LCK 文件，拒绝重复提交：{lock}")
    results = [work_dir / f"{job_name}{extension}" for extension in RESULT_EXTENSIONS]
    if any(_linked(path) or (path.exists() and not path.is_file()) for path in results):
        raise ValueError("同名结果不是普通文件，拒绝覆盖或移动；请先核对目标目录")
    if policy == "cancel" and any(path.exists() or _linked(path) for path in results):
        raise RuntimeError("检测到同名结果文件，当前策略为取消提交")


def check_plan_available(plan, policy):
    check_existing_results(plan.work_dir, plan.job_name, policy)
    if plan.oldjob is not None:
        for lock in (plan.oldjob.with_suffix(".lck"), plan.work_dir / (plan.oldjob.stem + ".lck")):
            if lock.exists() or _linked(lock):
                raise RuntimeError(f"Restart 前置文件仍有 LCK，拒绝准备：{lock}")
    if _linked(plan.work_dir):
        raise ValueError(f"计算工作目录不能是目录链接：{plan.work_dir}")
    if plan.work_dir.exists() and not plan.work_dir.is_dir():
        raise NotADirectoryError(f"计算工作目录不是目录：{plan.work_dir}")
    for source, target in plan.copies:
        if not source.is_file():
            raise FileNotFoundError(f"准备源文件不存在：{source}")
        if _linked(target) or (target.exists() and not target.is_file()):
            raise ValueError(f"准备目标不是普通文件，拒绝覆盖：{target}")


def plan_workspace(item, policy="backup"):
    source_inp = Path(item.source_inp_path or item.inp_path).resolve()
    if not source_inp.is_file():
        raise FileNotFoundError(f"INP 文件不存在：{source_inp}")
    options = replace(queue_item_to_options(item, default_cpus=MAX_CPUS), inp_file=str(source_inp))
    valid, message = validate_options(options)
    if not valid:
        raise ValueError(message)
    if not item.job_name or (os.name == "nt" and os.path.isreserved(item.job_name)):
        raise ValueError("作业名称不能为空或使用系统保留名称")
    if item.fortran_path and not Path(item.fortran_path).is_file():
        raise FileNotFoundError(f"用户子程序不存在：{item.fortran_path}")
    copies = []
    if item.calculation_root_dir:
        root = Path(item.calculation_root_dir).resolve()
        if root.exists() and not root.is_dir():
            raise NotADirectoryError(f"计算根路径不是目录：{root}")
        work_dir = root / item.job_name
        if _linked(work_dir) or work_dir.resolve().parent != root:
            raise ValueError("计算工作目录必须是指定根目录下的作业目录")
        prepared = work_dir / source_inp.name
        copies.append((source_inp, prepared))
    else:
        prepared = Path(item.inp_path).resolve()
        if not prepared.is_file():
            raise FileNotFoundError(f"计算 INP 文件不存在：{prepared}")
        work_dir = prepared.parent
    oldjob, oldjob_arg = None, ""
    if item.oldjob_path:
        oldjob = Path(item.oldjob_path).resolve()
        if not oldjob.is_file():
            raise FileNotFoundError(f"Restart 前置 ODB 不存在：{oldjob}")
        if os.path.normcase(oldjob.stem) == os.path.normcase(item.job_name):
            raise ValueError("当前作业名称不能与 oldjob 名称相同。")
        if item.calculation_root_dir:
            copies.extend((path, work_dir / path.name) for extension in RESTART_EXTENSIONS
                          if (path := oldjob.with_suffix(extension)).is_file())
            oldjob_arg = oldjob.stem
        else:
            oldjob_arg = oldjob.stem if (work_dir / oldjob.name).resolve() == oldjob else str(oldjob.with_suffix(""))
    plan = LocalWorkspacePlan(item.job_name, source_inp, prepared, work_dir, oldjob, oldjob_arg, tuple(copies))
    check_plan_available(plan, policy)
    return plan


def _identity(path):
    value = path.stat()
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def _copy_file(source, target, *, link, check):
    if target.exists() and source.samefile(target):
        return
    temporary = target.with_name(f".{target.name}.prepare-{uuid4().hex}.tmp")
    before = _identity(source)
    owned = False
    try:
        if link:
            try:
                os.link(source, temporary)
                owned = True
            except FileExistsError:
                raise
            except OSError:
                temporary.open("xb").close()
                owned = True
                shutil.copy2(source, temporary)
        else:
            temporary.open("xb").close()
            owned = True
            shutil.copy2(source, temporary)
        if _identity(source) != before:
            raise RuntimeError(f"准备期间源文件发生变化，未替换目标：{source}")
        check()
        os.replace(temporary, target)
    finally:
        # Only this call's unique temporary file is removed; no recursive cleanup.
        if owned:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                LOGGER.warning("准备临时文件清理失败，已保留：%s", temporary, exc_info=True)


def prepare_workspace(item, *, policy="backup", plan=None, cancelled=lambda: False):
    plan = plan or plan_workspace(item, policy)

    def check():
        if cancelled():
            raise WorkspacePreparationCancelled("已取消准备，未启动 Abaqus")
        check_plan_available(plan, policy)

    check()
    plan.work_dir.mkdir(parents=True, exist_ok=True)
    for index, (source, target) in enumerate(plan.copies):
        check()
        _copy_file(source, target, link=index > 0, check=check)
    check()
    return plan.prepared_inp, plan.work_dir, plan.oldjob_arg
