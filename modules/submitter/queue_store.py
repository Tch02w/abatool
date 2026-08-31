"""Qt-free, atomic persistence for the legacy-compatible job queue file."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any
from uuid import uuid4

from .app_paths import JOBLIST_PATH
from .constants import ACTIVE_STATUSES, STATUS_UNKNOWN
from .models import QueueItem

QUEUE_ITEM_FIELD_NAMES = {field.name for field in fields(QueueItem)}
_save_lock = threading.RLock()
_last_saved_payloads: dict[str, dict[str, Any]] = {}


def atomic_write_json(path: str | Path, payload: object) -> None:
    """Atomically replace one JSON file without sharing a fixed temp name."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def queue_item_to_json(item: QueueItem) -> dict[str, Any]:
    return asdict(item)


def queue_item_from_json(
    payload: object,
    *,
    restore_active_state: bool = True,
) -> QueueItem | None:
    if not isinstance(payload, dict):
        return None
    values = {
        key: value
        for key, value in payload.items()
        if key in QUEUE_ITEM_FIELD_NAMES
    }
    try:
        item = QueueItem(**values)
    except TypeError:
        return None
    if restore_active_state and item.status in ACTIVE_STATUSES:
        item.status = STATUS_UNKNOWN
        item.message = "程序重启后状态待确认"
        item.active_job_key = ""
        item.pids = []
        item.pid_create_times = {}
        item.rss_bytes = 0
    return item


def load_joblist_state(
    path: str | Path = JOBLIST_PATH,
    *,
    restore_active_state: bool = True,
) -> tuple[list[QueueItem], list[QueueItem], str]:
    source = Path(path)
    try:
        with source.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except FileNotFoundError:
        return [], [], ""
    except (OSError, json.JSONDecodeError) as exc:
        return [], [], str(exc)
    if not isinstance(payload, dict):
        return [], [], "joblist.json 格式不是对象"

    def read_items(key: str) -> list[QueueItem]:
        items: list[QueueItem] = []
        for raw_item in payload.get(key, []) or []:
            item = queue_item_from_json(
                raw_item,
                restore_active_state=restore_active_state and key == "queue_items",
            )
            if item is not None:
                items.append(item)
        return items

    return read_items("candidates"), read_items("queue_items"), ""


def save_joblist_state(
    candidates: list[QueueItem],
    queue_items: list[QueueItem],
    path: str | Path = JOBLIST_PATH,
) -> None:
    target = Path(path)
    payload = {
        "candidates": [queue_item_to_json(item) for item in candidates],
        "queue_items": [queue_item_to_json(item) for item in queue_items],
    }
    cache_key = os.path.normcase(str(target.absolute()))
    with _save_lock:
        if payload == _last_saved_payloads.get(cache_key) and target.is_file():
            return
        atomic_write_json(target, payload)
        _last_saved_payloads[cache_key] = payload


__all__ = [
    "QUEUE_ITEM_FIELD_NAMES",
    "atomic_write_json",
    "load_joblist_state",
    "queue_item_from_json",
    "queue_item_to_json",
    "save_joblist_state",
]
