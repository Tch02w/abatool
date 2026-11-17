"""Local hardware limits. Product policy, not an Abaqus licensing rule."""

from __future__ import annotations

import re
import psutil


def logical_cpu_count() -> int:
    return max(1, psutil.cpu_count(logical=True) or 1)


def local_cpu_policy(command: str = "", *, release: str | None = None) -> dict:
    from modules.submitter.app_settings import load_app_settings
    from modules.postprocessor.config import load_defaults

    logical = logical_cpu_count()
    detected_physical = psutil.cpu_count(logical=False)
    # Never label logical processors as physical cores when detection fails.
    physical = min(logical, max(1, detected_physical or 1))
    if release is None:
        settings, defaults = load_app_settings(), load_defaults()
        configured_command = str(settings.get("abaqus_command") or defaults.get("abaqus_command") or "abaqus")
        configured_release = str(settings.get("local_abaqus_release") or defaults.get("local_abaqus_release") or "")
        # A version-specific launcher takes precedence over the default installation.
        launcher_year = re.search(r"(?:abq|abaqus)[-_ ]?(20\d{2})(?!\d)", command, re.I)
        release = launcher_year.group(1) if launcher_year else (
            configured_release if not command or command.strip('"').casefold() == configured_command.strip('"').casefold()
            or command.casefold() in {"abaqus", "abaqus.bat"} else "")
    match = re.search(r"(?<!\d)(20\d{2})(?!\d)", release)
    year = int(match.group(1)) if match else None
    legacy_release = re.search(r"(?<!\d)6\.\d+(?!\d)", release) is not None
    use_logical = legacy_release or (year is not None and year <= 2021)
    return {
        "logicalCpus": logical, "physicalCpus": physical,
        "physicalCpusDetected": detected_physical is not None,
        "jobCpuLimit": logical if use_logical else physical,
        "jobCpuBasis": "logical" if use_logical else "physical",
        "jobCpuRelease": release,
        "jobCpuPolicyNote": "逻辑线程数（Abaqus ≤2021）" if use_logical else (
            "物理核心数（Abaqus >2021）" if year is not None else "版本未识别，保守按物理核心数"),
    }


def validate_local_cpus(cpus: int, command: str = "") -> None:
    policy = local_cpu_policy(command)
    if isinstance(cpus, bool) or not isinstance(cpus, int) or not 0 <= cpus <= policy["jobCpuLimit"]:
        raise ValueError(f"cpus 必须在 0 到 {policy['jobCpuLimit']} 之间；{policy['jobCpuPolicyNote']}。")
