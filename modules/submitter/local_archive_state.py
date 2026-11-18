"""Durable archive checkpoints keyed by the original, already-completed solve attempt."""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path

from .queue_store import atomic_write_json


class ArchiveStateError(ValueError):
    pass


class ArchiveBusyError(RuntimeError):
    pass


def work_directory(item):
    return (Path(item.calculation_root_dir) / item.job_name if item.calculation_root_dir
            else Path(item.effective_work_dir or Path(item.inp_path).parent)).resolve()


class ArchiveStateStore:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def path(self, item):
        if not item.item_id or not item.attempt_id:
            raise ArchiveStateError("归档恢复缺少执行身份")
        key = hashlib.sha256((item.item_id + "\0" + item.attempt_id).encode()).hexdigest()
        return self.root / (key + ".json")

    def _check_root(self):
        if self.root.resolve() != self.root:
            raise ArchiveStateError("归档记录目录发生变化")

    @contextmanager
    def claim(self, item):
        self._check_root()
        self.root.mkdir(parents=True, exist_ok=True)
        lock = self.path(item).with_suffix(".lock")
        if lock.resolve() != lock:
            raise ArchiveStateError("归档锁路径包含链接")
        with lock.open("a+b") as owner:
            if owner.tell() == 0:
                owner.write(b"\0")
                owner.flush()
            owner.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ArchiveBusyError("这次归档仍由另一执行线程或后台持有") from exc
            try:
                yield
            finally:
                owner.seek(0)
                if os.name == "nt":
                    msvcrt.locking(owner.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(owner.fileno(), fcntl.LOCK_UN)

    def begin(self, item, source, command, message):
        return {"schemaVersion": 1, "itemId": item.item_id, "attemptId": item.attempt_id,
                "jobName": item.job_name, "solveConfirmed": True, "source": str(Path(source).resolve()),
                "sourceInp": str(Path(item.source_inp_path).resolve()) if item.source_inp_path else "",
                "cleanup": bool(item.cleanup_after_archive), "command": command, "solveMessage": message,
                "phase": "confirmed", "result": None}

    def save(self, item, state):
        self._check_root()
        atomic_write_json(self.path(item), state)

    def read(self, item):
        self._check_root()
        path = self.path(item)
        if not path.exists():
            return None
        if path.resolve() != path or path.stat().st_size > 32 * 1024 * 1024:
            raise ArchiveStateError("归档记录路径或大小异常")
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ArchiveStateError("归档记录无法读取，未执行恢复") from exc
        expected = self.begin(item, work_directory(item), "", "")
        for name in ("schemaVersion", "itemId", "attemptId", "jobName", "solveConfirmed", "source", "sourceInp", "cleanup"):
            if not isinstance(state, dict) or type(state.get(name)) is not type(expected[name]) or state[name] != expected[name]:
                raise ArchiveStateError(f"归档记录与当前执行不符：{name}")
        if state.get("phase") not in {"confirmed", "prepared", "ready", "published", "done"}:
            raise ArchiveStateError("归档阶段无效")
        if not isinstance(state.get("solveMessage"), str) or not isinstance(state.get("command"), str):
            raise ArchiveStateError("归档记录缺少求解完成信息")
        return state
