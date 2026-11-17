"""Confirmed upgrade execution using the legacy safe batch controller.

The operation layer must retain this controller until the runner returns. Cancelling
it requests a safe stop; it must never be replaced with ProcessController/taskkill.
"""
from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from modules.postprocessor.paths import scan_cache_dir
from modules.postprocessor.process_runner import ProcessCancelled
from modules.postprocessor.runner import (
    UpgradeBatchController, check_odb_compatibility, upgrade_odb_files,
)
from .compatibility import load_compatibility_settings
from .contracts import ApiProblem
from .odb_upgrade_drafts import preview_odb_upgrade

# Legacy workers use fixed report filenames. Serialize full check/upgrade sequences.
_upgrade_lock = threading.Lock()


def execute_confirmed_upgrade(
    preview: Mapping[str, Any], *, confirmed: bool,
    controller: UpgradeBatchController,
    log: Callable[[str], None] | None = None,
    on_result: Callable[[dict], None] | None = None,
) -> dict[str, Any]:
    if confirmed is not True:
        raise ApiProblem(400, "UPGRADE_CONFIRMATION_REQUIRED", "必须确认升级与原文件备份计划")
    if not isinstance(controller, UpgradeBatchController):
        raise TypeError("Upgrade requires a safe-stop UpgradeBatchController")
    try:
        request = {"schemaVersion": preview["schemaVersion"], "root": preview["root"],
                   "paths": [entry["sourcePath"] for entry in preview["entries"]]}
    except (KeyError, TypeError) as exc:
        raise ApiProblem(400, "INVALID_UPGRADE_PREVIEW", "升级预览内容不完整") from exc

    def verify():
        if controller.stop_requested:
            raise ProcessCancelled("ODB 升级已取消，未开始下一文件")
        fresh = preview_odb_upgrade(request)
        if fresh != preview:
            raise ApiProblem(409, "UPGRADE_PREVIEW_CHANGED", "文件、备份路径或版本已变化，请重新预览确认")
        return fresh

    with _upgrade_lock:
        current = verify()
        settings = load_compatibility_settings()
        if settings.release != current["targetRelease"]:
            raise ApiProblem(409, "UPGRADE_PREVIEW_CHANGED", "Abaqus 版本已变化，请重新预览确认")
        paths = tuple(Path(entry["sourcePath"]) for entry in current["entries"])
        cache = scan_cache_dir(Path(current["root"])) / "native-upgrade"
        report = check_odb_compatibility(settings.command, paths, cache, log, controller,
                                         force_rescan=True, abaqus_version=settings.cache_version)
        results = report.get("results", [])
        statuses = {str(Path(item["path"]).resolve()): item.get("status") for item in results}
        if len(results) != len(paths) or any(statuses.get(str(path)) != "upgrade_required" for path in paths):
            raise ApiProblem(409, "ODB_NOT_UPGRADEABLE", "仅允许升级本次重新检查确认为旧版本的 ODB",
                             details={"results": results})
        # Recheck after the external read: it may take minutes, during which files can change.
        verify()
        return upgrade_odb_files(settings.command,
            [(Path(entry["sourcePath"]), Path(entry["backupPath"])) for entry in current["entries"]],
            cache, log, controller, release=settings.release,
            abaqus_version=settings.cache_version, parallel_workers=1, on_result=on_result)
