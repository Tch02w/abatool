"""Persistent application settings stored in the Application Data Directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from modules.common.json_io import json_file_lock, load_json_mapping, save_json_mapping

from .app_paths import CONFIG_PATH


def load_app_settings(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return load_json_mapping(path)


def load_settings_section(
    section: str,
    *,
    path: Path = CONFIG_PATH,
) -> dict[str, Any]:
    payload = load_app_settings(path)
    values = payload.get(section, {})
    return dict(values) if isinstance(values, dict) else {}


def save_settings_section(
    section: str,
    values: dict[str, Any],
    *,
    path: Path = CONFIG_PATH,
) -> None:
    update_app_settings({section: dict(values)}, path=path)


class SettingsChangedError(OSError):
    """The section changed after the caller displayed it."""


def update_app_settings(
    values: dict[str, Any], *, path: Path = CONFIG_PATH, expected: dict[str, Any] | None = None,
) -> None:
    """Merge touched settings into the latest valid file under a process-shared lock."""
    with json_file_lock(path):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            payload = {}
        except ValueError as exc:
            raise OSError("原有设置文件无法读取，请先修复该文件。") from exc
        if not isinstance(payload, dict):
            raise OSError("原有设置文件格式无效，请先修复该文件。")
        if expected and any(payload.get(key) != value for key, value in expected.items()):
            raise SettingsChangedError("设置已被其他窗口更改，请重开应用后再编辑。")
        payload.update(values)
        save_json_mapping(path, payload)


def save_app_settings(
    values: dict[str, Any],
    *,
    path: Path = CONFIG_PATH,
) -> None:
    """Atomically replace the settings payload with UTF-8 JSON."""

    with json_file_lock(path):
        save_json_mapping(path, values)


__all__ = [
    "load_app_settings",
    "load_settings_section",
    "save_app_settings",
    "save_settings_section",
    "update_app_settings",
]
