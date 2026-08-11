"""UTF-8 JSON persistence primitives shared by both Abaqus workflows."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_json_mapping(path: Path) -> dict[str, Any]:
    """Load a JSON object, returning an empty mapping for unavailable data."""

    try:
        with path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def save_json_mapping(path: Path, payload: dict[str, Any]) -> None:
    """Atomically replace a JSON object while preserving UTF-8 Chinese text."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary_path, path)
