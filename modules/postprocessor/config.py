from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from modules.common.json_io import save_json_mapping

from .file_attributes import clear_windows_hidden

PACKAGE_DIR = Path(__file__).resolve().parent


def load_defaults() -> dict[str, Any]:
    with (PACKAGE_DIR / "defaults.json").open("r", encoding="utf-8") as stream:
        return json.load(stream)


def save_json(path: Path, payload: dict[str, Any]) -> None:
    if path.is_file():
        clear_windows_hidden(path)
    save_json_mapping(path, payload)


def project_root() -> Path:
    return PACKAGE_DIR.parent.parent


def abaqus_script(name: str) -> Path:
    return PACKAGE_DIR / "abaqus_scripts" / name
