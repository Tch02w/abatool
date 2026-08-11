"""应用运行数据目录的唯一 Interface。"""

from __future__ import annotations

from pathlib import Path

from modules.common.app_paths import resolve_app_data_dir as resolve_app_data_dir_shared

APP_NAME = "AbaqusSubmitter"
APP_DATA_DIR_ENV = "ABAQUS_SUBMITTER_DATA_DIR"


def resolve_app_data_dir() -> Path:
    return resolve_app_data_dir_shared(
        APP_NAME,
        environment_variable=APP_DATA_DIR_ENV,
    )


APP_DATA_DIR = resolve_app_data_dir()
CONFIG_PATH = APP_DATA_DIR / "config.json"
JOBLIST_PATH = APP_DATA_DIR / "joblist.json"
SCHEDULER_STATE_PATH = APP_DATA_DIR / "scheduler_state.db"


__all__ = [
    "APP_DATA_DIR",
    "APP_DATA_DIR_ENV",
    "CONFIG_PATH",
    "JOBLIST_PATH",
    "SCHEDULER_STATE_PATH",
    "resolve_app_data_dir",
]
