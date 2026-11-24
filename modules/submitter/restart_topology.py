"""Resolve queue restart predecessors before accepting a dependency edit."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from .command import validate_job_name
from .constants import STATUS_FAILED
from .models import QueueItem
from .queue_scheduler import oldjob_name_from_item, queue_item_matches_oldjob_path


class RestartTopology:
    def __init__(self, items: list[QueueItem]):
        self.parents: dict[str, str] = {}
        self.issues: dict[str, tuple[str, str]] = {}
        # Older queue files may store only the input filename as their job name.
        self.by_id = {
            item.job_id: item if item.job_name else replace(item, job_name=Path(item.source_inp_path or item.inp_path).stem)
            for item in items
        }
        self._valid_chains: set[str] = set()
        by_name = defaultdict(list)
        for item in self.by_id.values():
            by_name[item.job_name.casefold()].append(item)
        for item in self.by_id.values():
            name = oldjob_name_from_item(item)
            path = Path(item.oldjob_path) if item.oldjob_path else None
            if not (name or item.dependency_job_ids or item.run_mode == "restart"):
                continue
            if name and name.casefold() == item.job_name.casefold():
                self.parents[item.job_id] = item.job_id
                continue
            keys = list(dict.fromkeys(key for key in item.dependency_job_ids if key))
            if len(keys) > 1 or (keys and keys[0] not in self.by_id):
                self.issues[item.job_id] = (
                    ("incompatible_path", "记录包含多个前置作业，请重新指定唯一的前置 ODB")
                    if len(keys) > 1
                    else ("missing_parent", "记录中的前置作业已不存在")
                )
                continue
            explicit = [self.by_id[key] for key in keys]
            matches = explicit or [
                other
                for other in by_name.get(name.casefold(), ())
                if path is None or queue_item_matches_oldjob_path(item, other)
            ]
            if len(matches) == 1:
                self.parents[item.job_id] = matches[0].job_id
            if path and (path.suffix.lower() != ".odb" or path.stem.casefold() != name.casefold()):
                self.issues[item.job_id] = ("incompatible_path", "前置路径必须指向与前置作业同名的 .odb 文件")
            elif len(matches) > 1:
                self.issues[item.job_id] = ("incompatible_path", "存在多个前置作业，请指定唯一的前置 ODB")
            elif explicit and name and explicit[0].job_name.casefold() != name.casefold():
                self.issues[item.job_id] = ("incompatible_path", "队列中的前置作业名称与记录的依赖不一致")
            elif (
                explicit
                and path
                and any(
                    (
                        explicit[0].inp_path,
                        explicit[0].archive_destination,
                        explicit[0].effective_work_dir,
                        explicit[0].external_work_dir,
                    )
                )
                and not queue_item_matches_oldjob_path(item, explicit[0])
            ):
                self.issues[item.job_id] = ("incompatible_path", "前置 ODB 路径与指定的队列作业不一致")
            elif not matches and not (path and path.is_file()):
                self.issues[item.job_id] = ("missing_parent", f"未找到前置作业或 ODB：{name or '尚未指定'}")

    def edit_issue(self, item: QueueItem, *, allow_unassigned=False) -> str:
        current = item.job_id
        visited = set()
        while current and current not in self._valid_chains:
            if current in visited:
                return f"{item.job_name} 的前置链包含循环依赖（{self.by_id[current].job_name}）"
            visited.add(current)
            if current in self.issues:
                if (
                    allow_unassigned
                    and current == item.job_id
                    and not (oldjob_name_from_item(item) or item.dependency_job_ids)
                ):
                    return ""
                return self.issues[current][1]
            current = self.parents.get(current, "")
        self._valid_chains.update(visited)
        return ""


def legacy_restart_edit_failure(item: QueueItem) -> bool:
    """Identify the old pre-run validation write, never a solver failure."""
    name = oldjob_name_from_item(item)
    return (
        item.status == STATUS_FAILED
        and not item.valid
        and bool(name)
        and (name.casefold() == item.job_name.casefold() or not validate_job_name(name)[0])
        and (
            item.message in {"Restart 依赖作业名无效", "当前作业名称不能与 Restart 依赖作业名相同。"}
            or item.message.startswith("Restart 依赖作业名不合法：")
        )
        # Startup projects STATUS_FAILED into FAILED even for never-dispatched edits.
        and item.scheduler_state in {"", "PENDING", "FAILED"}
        and not item.attempt_id
        and not (
            item.active_job_key
            or item.is_external
            or item.pids
            or item.pid_create_times
            or item.archive_status
            or item.archive_destination
            or item.elapsed
            or item.memory_sample_count
            or item.memory_peak_bytes
            or item.rss_bytes
        )
    )
