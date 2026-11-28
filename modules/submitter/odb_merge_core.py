"""Qt-free planning primitives for protected Abaqus ODB restart merges."""

from __future__ import annotations

import os
import shlex
import subprocess
import uuid
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path


class MergeConflictPolicy(str, Enum):
    """How an existing joined result is handled."""

    AUTO_NUMBER = "auto_number"
    OVERWRITE = "overwrite"


@dataclass(frozen=True)
class OdbMergeRequest:
    """User-selected inputs for one restartjoin operation."""

    original_odb: Path
    restart_odb: Path
    output_odb: Path
    abaqus_command: str = "abaqus"
    include_history: bool = True
    compress_result: bool = False
    copy_original: bool = False
    conflict_policy: MergeConflictPolicy = MergeConflictPolicy.AUTO_NUMBER
    attempt_id: str = ""


@dataclass(frozen=True)
class OdbMergePlan:
    """Resolved file paths and commands for one protected merge."""

    request: OdbMergeRequest
    staging_dir: Path
    original_backup: Path
    restart_backup: Path
    staged_original_backup: Path
    staged_restart_backup: Path
    working_odb: Path
    restartjoin_output_odb: Path
    validation_script: Path
    restartjoin_arguments: tuple[str, ...]
    validation_arguments: tuple[str, ...]

    def command_preview(self) -> str:
        return format_command(
            (self.request.abaqus_command, *self.restartjoin_arguments)
        )


@dataclass(frozen=True)
class OdbMergeResult:
    """Files published after restartjoin and read-only validation succeed."""

    output_odb: Path
    original_backup: Path
    restart_backup: Path
    command: str
    validation_report: Path | None = None
    empty_frame_steps: tuple[str, ...] = ()


class OdbMergeError(RuntimeError):
    """Raised when a protected ODB merge cannot be completed."""


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _same_path(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        return os.path.normcase(os.fspath(_absolute(left))) == os.path.normcase(
            os.fspath(_absolute(right))
        )


def _source_stem(path: Path) -> str:
    stem = path.stem
    return stem[: -len("_original")] if stem.lower().endswith("_original") else stem


def normalize_joined_output(path: Path) -> Path:
    """Ensure the selected result follows the ``*_joined.odb`` convention."""

    output = Path(path)
    stem = output.stem if output.suffix else output.name
    if not stem.lower().endswith("_joined"):
        stem = f"{stem}_joined"
    return output.with_name(f"{stem}.odb")


def _numbered_path(path: Path, occupied: set[Path]) -> Path:
    candidate = path
    index = 2
    normalized_occupied = {
        Path(os.path.normcase(os.fspath(_absolute(item)))) for item in occupied
    }
    while (
        candidate.exists()
        or Path(os.path.normcase(os.fspath(_absolute(candidate))))
        in normalized_occupied
    ):
        candidate = path.with_name(f"{path.stem}_{index:03d}{path.suffix}")
        index += 1
    return candidate


def _validate_request(request: OdbMergeRequest) -> OdbMergeRequest:
    original = _absolute(request.original_odb)
    restart = _absolute(request.restart_odb)
    output = _absolute(normalize_joined_output(request.output_odb))
    for label, path in (("原始 ODB", original), ("重启动 ODB", restart)):
        if path.suffix.lower() != ".odb":
            raise OdbMergeError(f"{label} 必须是 .odb 文件：{path}")
        if not path.is_file():
            raise OdbMergeError(f"{label} 不存在：{path}")
        if path.stat().st_size <= 0:
            raise OdbMergeError(f"{label} 是空文件：{path}")
    if _same_path(original, restart):
        raise OdbMergeError("原始 ODB 与重启动 ODB 不能是同一个文件。")
    if _same_path(output, original) or _same_path(output, restart):
        raise OdbMergeError("输出 ODB 不能覆盖任一源 ODB。")
    if not output.parent.is_dir():
        raise OdbMergeError(f"输出目录不存在：{output.parent}")
    command = request.abaqus_command.strip().strip('"')
    if not command:
        raise OdbMergeError("Abaqus 命令不能为空。")
    if any(character in command for character in "\r\n"):
        raise OdbMergeError("Abaqus 命令不能包含换行符。")
    return replace(
        request,
        original_odb=original,
        restart_odb=restart,
        output_odb=output,
        abaqus_command=command,
    )


def build_merge_plan(request: OdbMergeRequest) -> OdbMergePlan:
    """Validate inputs and resolve non-destructive output paths."""

    request = _validate_request(request)
    output = request.output_odb
    if request.conflict_policy == MergeConflictPolicy.AUTO_NUMBER:
        output = _numbered_path(output, set())
        request = replace(request, output_odb=output)

    occupied = {request.original_odb, request.restart_odb, request.output_odb}
    original_backup = _numbered_path(
        request.output_odb.parent
        / f"{_source_stem(request.original_odb)}_original.odb",
        occupied,
    )
    occupied.add(original_backup)
    restart_backup = _numbered_path(
        request.output_odb.parent / f"{_source_stem(request.restart_odb)}_original.odb",
        occupied,
    )
    attempt_id = request.attempt_id or uuid.uuid4().hex
    if len(attempt_id) != 32 or any(c not in "0123456789abcdef" for c in attempt_id):
        raise OdbMergeError("合并尝试编号无效。")
    staging_dir = request.output_odb.parent / f".abasub-odb-merge-{attempt_id}"
    staged_original = staging_dir / original_backup.name
    staged_restart = staging_dir / restart_backup.name
    working = staging_dir / "abasub_join_working.odb"
    restartjoin_output = (
        staging_dir / f"Restart_{working.name}" if request.copy_original else working
    )
    validation_script = staging_dir / "validate_joined_odb.py"
    restartjoin_arguments = [
        "restartjoin",
        f"originalodb={working.name}",
        f"restartodb={staged_restart.name}",
    ]
    if request.include_history:
        restartjoin_arguments.append("history")
    if request.compress_result:
        restartjoin_arguments.append("compressresult")
    if request.copy_original:
        restartjoin_arguments.append("copyoriginal")
    validation_arguments = (
        "python",
        validation_script.name,
        staged_original.name,
        staged_restart.name,
        restartjoin_output.name,
        "1" if request.include_history else "0",
        "merge_validation.json",
    )
    return OdbMergePlan(
        request=request,
        staging_dir=staging_dir,
        original_backup=original_backup,
        restart_backup=restart_backup,
        staged_original_backup=staged_original,
        staged_restart_backup=staged_restart,
        working_odb=working,
        restartjoin_output_odb=restartjoin_output,
        validation_script=validation_script,
        restartjoin_arguments=tuple(restartjoin_arguments),
        validation_arguments=validation_arguments,
    )


def format_command(arguments: tuple[str, ...]) -> str:
    """Format an argument vector for display without executing through a shell."""

    if os.name == "nt":
        return subprocess.list2cmdline(list(arguments))
    return shlex.join(arguments)


__all__ = [
    "MergeConflictPolicy",
    "OdbMergeError",
    "OdbMergePlan",
    "OdbMergeRequest",
    "OdbMergeResult",
    "build_merge_plan",
    "format_command",
    "normalize_joined_output",
]
