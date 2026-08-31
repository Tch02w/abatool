"""Qt-free discovery of local Abaqus ODB files."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path

from .contracts import ApiProblem, OdbDiscoveryRequest, OdbFileDto

DEFAULT_EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".venv",
        "AbaqusODBPostProcessor_Results",
        "_AbaqusODBPostProcessor_Results",
    }
)
_NATURAL_NUMBER_PATTERN = re.compile(r"(\d+)")


def natural_sort_key(value: str) -> tuple[tuple[int, object], ...]:
    """Return a deterministic, case-insensitive key with numeric ordering."""

    parts = _NATURAL_NUMBER_PATTERN.split(str(value))
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in parts
        if part
    )


def _is_generated_or_backup_odb(path: Path) -> bool:
    stem = path.stem.casefold()
    return stem.endswith("-old") or "-old-" in stem or "-upgrading-" in stem


def _modified_at(timestamp: float) -> str:
    return (
        datetime.fromtimestamp(timestamp, UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _to_dto(path: Path, root: Path) -> OdbFileDto:
    stat = path.stat()
    return OdbFileDto(
        path=str(path.resolve()),
        relative_path=str(path.relative_to(root)),
        name=path.name,
        size_bytes=max(0, int(stat.st_size)),
        modified_at=_modified_at(stat.st_mtime),
    )


def _candidate_is_odb(path: Path) -> bool:
    return path.suffix.casefold() == ".odb" and not _is_generated_or_backup_odb(path)


def discover_odb_files(
    request: OdbDiscoveryRequest,
) -> tuple[Path, tuple[OdbFileDto, ...], tuple[str, ...]]:
    """Discover ODB files and return resolved paths plus non-fatal warnings."""

    try:
        root = Path(request.root).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ApiProblem(
            400,
            "ROOT_NOT_FOUND",
            "ODB 根目录不存在或无法解析",
            details={"root": request.root, "reason": str(exc)},
        ) from exc

    if not root.is_dir():
        raise ApiProblem(
            400,
            "ROOT_NOT_DIRECTORY",
            "ODB root 必须指向目录",
            details={"root": str(root)},
        )

    warnings: list[str] = []
    candidates: list[Path] = []

    if request.recursive:

        def record_walk_error(error: OSError) -> None:
            location = str(getattr(error, "filename", "") or root)
            warnings.append(f"无法读取目录 {location}：{error}")

        for directory, directory_names, file_names in os.walk(
            root,
            topdown=True,
            onerror=record_walk_error,
            followlinks=False,
        ):
            directory_names[:] = sorted(
                (
                    name
                    for name in directory_names
                    if name not in DEFAULT_EXCLUDED_DIRECTORIES
                ),
                key=natural_sort_key,
            )
            directory_path = Path(directory)
            for name in sorted(file_names, key=natural_sort_key):
                path = directory_path / name
                if _candidate_is_odb(path):
                    candidates.append(path)
    else:
        try:
            candidates = [
                path
                for path in root.iterdir()
                if path.is_file() and _candidate_is_odb(path)
            ]
        except OSError as exc:
            raise ApiProblem(
                400,
                "ROOT_NOT_READABLE",
                "无法读取 ODB 根目录",
                details={"root": str(root), "reason": str(exc)},
            ) from exc

    items: list[OdbFileDto] = []
    for path in candidates:
        try:
            if path.is_file():
                items.append(_to_dto(path, root))
        except OSError as exc:
            warnings.append(f"无法读取文件 {path}：{exc}")

    items.sort(key=lambda item: natural_sort_key(item.relative_path))
    return root, tuple(items), tuple(warnings)


__all__ = [
    "DEFAULT_EXCLUDED_DIRECTORIES",
    "discover_odb_files",
    "natural_sort_key",
]
