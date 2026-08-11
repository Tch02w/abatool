"""Operating-system application-data locations shared by the unified product."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def resolve_app_data_dir(
    app_name: str,
    *,
    environment_variable: str = "",
    roaming_on_windows: bool = False,
) -> Path:
    """Resolve one application's writable state directory without using source paths."""

    if environment_variable:
        override = os.environ.get(environment_variable, "").strip()
        if override:
            return Path(override).expanduser().resolve()

    if os.name == "nt":
        variable = "APPDATA" if roaming_on_windows else "LOCALAPPDATA"
        base = os.environ.get(variable, "").strip()
        if base:
            return Path(base) / app_name
        fallback = "Roaming" if roaming_on_windows else "Local"
        return Path.home() / "AppData" / fallback / app_name

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name

    base = os.environ.get("XDG_DATA_HOME", "").strip()
    return (Path(base).expanduser() if base else Path.home() / ".local" / "share") / app_name
