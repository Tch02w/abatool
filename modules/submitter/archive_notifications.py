"""Small durable archive receipts, independent of queue-row retention."""
from __future__ import annotations

import json
import math
import re
import time
from types import SimpleNamespace

from .local_archive import archive_published
from .local_archive_state import ArchiveBusyError, ArchiveStateStore, work_directory
from .queue_store import atomic_write_json


class ArchiveNoticeStore:
    def __init__(self, archive_store: ArchiveStateStore):
        self.archive_store = archive_store
        self.root = archive_store.root / "notifications"
        self._seen = {}

    def _path(self, operation_id):
        if not isinstance(operation_id, str) or not re.fullmatch(r"[0-9a-f]{32}", operation_id):
            raise ValueError("归档提醒操作身份无效")
        if self.root.resolve() != self.root:
            raise ValueError("归档提醒目录发生变化")
        return self.root / (operation_id + ".json")

    def begin(self, item, operation_id):
        if not item.complete_notify:
            return None
        path = self._path(operation_id)
        if path.exists():
            raise ValueError("归档提醒操作已存在，未覆盖")
        record = {"schemaVersion": 1, "operationId": operation_id, "itemId": item.item_id,
                  "attemptId": item.attempt_id, "jobName": item.job_name, "createdAt": time.time(),
                  "sourceDirectory": str(work_directory(item)), "result": None}
        atomic_write_json(path, record)
        return record

    def finish(self, record, destination, status, error, cancelled=False):
        if record is None or record["result"] is not None:
            return
        current = self._read(self._path(record["operationId"]))
        if any(current[k] != record[k] for k in record if k != "result"):
            raise ValueError("归档提醒身份已变化，未覆盖原记录")
        if current["result"] is not None:
            record.update(current)
            return
        outcome = {"status": "succeeded" if status == "已归档" else "cancelled" if cancelled else "failed",
                   "message": ("归档处理：" + status + ("；" + error if error else ""))[:2000],
                   "workDirectory": destination if archive_published(status, destination) else record["sourceDirectory"]}
        updated = dict(record, result=outcome)
        atomic_write_json(self._path(record["operationId"]), updated)
        record.update(updated)

    def _read(self, path):
        if path.resolve() != path or path.stat().st_size > 64 * 1024:
            raise ValueError("归档提醒记录路径或大小异常")
        value = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(value, dict) or set(value) != {"schemaVersion", "operationId", "itemId", "attemptId", "jobName", "createdAt", "sourceDirectory", "result"}
                or type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1
                or any(not isinstance(value[k], str) or not value[k] for k in ("operationId", "itemId", "attemptId", "jobName", "sourceDirectory"))
                or self._path(value["operationId"]) != path
                or type(value["createdAt"]) not in (float, int) or not math.isfinite(value["createdAt"]) or value["createdAt"] <= 0):
            raise ValueError("归档提醒记录格式无效")
        result = value["result"]
        if result is not None and (not isinstance(result, dict) or set(result) != {"status", "message", "workDirectory"}
                or result["status"] not in {"succeeded", "failed", "cancelled"}
                or any(not isinstance(result[k], str) for k in ("message", "workDirectory"))):
            raise ValueError("归档提醒结果无效")
        return value

    def recover(self, since, publish):
        """Replay unseen receipts; the existing inbox owns read-state and deduplication."""
        warnings = []
        if self.root.resolve() != self.root:
            return ["归档提醒目录异常，未读取"]
        if not self.root.exists():
            return warnings
        if not self.root.is_dir():
            return ["归档提醒目录不可读，未当作空历史"]
        for path in sorted(self.root.glob("*.json")):
            try:
                stat = path.stat()
                fingerprint = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
                if self._seen.get(path.name) == fingerprint:
                    continue
                value = self._read(path)
                if value["createdAt"] < since:
                    self._seen[path.name] = fingerprint
                    continue
                if value["result"] is None:
                    item = SimpleNamespace(item_id=value["itemId"], attempt_id=value["attemptId"])
                    with self.archive_store.claim(item):
                        # The owner might have completed between our read and acquisition.
                        value = self._read(path)
                        if value["result"] is None:
                            self.finish(value, "", "归档已中断", "上次归档未收尾，请在作业概览核对并恢复；求解不会重跑")
                        stat = path.stat()
                        fingerprint = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
                publish(source="local", execution_id=f"{value['attemptId']}:archive:{value['operationId']}",
                        job_id=value["itemId"], job_name=value["jobName"], status=value["result"]["status"],
                        message=value["result"]["message"], work_directory=value["result"]["workDirectory"])
                self._seen[path.name] = fingerprint
            except ArchiveBusyError:
                continue
            except (OSError, ValueError, TypeError, KeyError):
                warnings.append("归档提醒记录暂无法核对，原记录已保留")
        return warnings
