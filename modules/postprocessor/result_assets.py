"""Versioned shared ODB data and lightweight comparison-group references."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from .cache import (
    NUMERIC_PAYLOAD_REQUIRED_CSV_COLUMNS,
    NUMERIC_PIPELINE_VERSION,
    numeric_payload_is_valid,
    numeric_payload_validation_errors,
)
from .config import save_json
from .file_attributes import ensure_windows_hidden

RESULT_LAYOUT_VERSION = 3
SHARED_DATA_ROOT_NAME = "ODB数据"
ASSET_MANIFEST_NAME = "_odb_data_manifest.json"
GROUP_MEMBER_MANIFEST_NAME = "_group_member_manifest.json"
INCOMPLETE_OUTPUT_MARKER = "_postprocess_incomplete.json"
NUMERIC_DIRECTORIES = ("data", "History_Output", "rebar", "freebody", "plots")
NUMERIC_FILES = ("metadata.json", "summary.xlsx")


def is_incomplete_output(path: Path) -> bool:
    """Recognize new incomplete outputs without hiding unmarked legacy results."""
    return any((parent / INCOMPLETE_OUTPUT_MARKER).is_file() for parent in (path, *path.parents))


def safe_result_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", value).strip(" .")
    return cleaned or "未命名"


def numeric_asset_id(content_fingerprint: str, numeric_config_hash: str) -> str:
    return f"{content_fingerprint[:12]}-{numeric_config_hash[:12]}"


def numeric_asset_dir(
    result_root: Path | str,
    odb_path: Path | str,
    content_fingerprint: str,
    numeric_config_hash: str,
) -> Path:
    odb_name = safe_result_name(Path(odb_path).stem)
    return (
        Path(result_root)
        / SHARED_DATA_ROOT_NAME
        / odb_name
        / numeric_asset_id(content_fingerprint, numeric_config_hash)
    )


def copy_numeric_payload(source: Path | str, target: Path | str) -> None:
    source_root = Path(source)
    target_root = Path(target)
    target_root.mkdir(parents=True, exist_ok=True)
    for name in NUMERIC_DIRECTORIES:
        source_path = source_root / name
        target_path = target_root / name
        if target_path.is_symlink() or target_path.is_file():
            target_path.unlink()
        elif target_path.is_dir():
            shutil.rmtree(target_path)
        if source_path.is_dir():
            shutil.copytree(source_path, target_path)
    for name in NUMERIC_FILES:
        source_path = source_root / name
        target_path = target_root / name
        if target_path.is_symlink() or target_path.is_file():
            target_path.unlink()
        elif target_path.is_dir():
            shutil.rmtree(target_path)
        if source_path.is_file():
            shutil.copy2(source_path, target_path)


def write_numeric_asset_manifest(
    asset_dir: Path | str,
    *,
    odb_path: Path | str,
    content_fingerprint: str,
    numeric_config_hash: str,
    abaqus_version: str,
) -> Path:
    root = Path(asset_dir).resolve()
    validation_errors = numeric_payload_validation_errors(root)
    if validation_errors:
        raise ValueError(
            "数值资产不完整，拒绝写入可复用清单：" + "；".join(validation_errors)
        )
    manifest = root / ASSET_MANIFEST_NAME
    save_json(
        manifest,
        {
            "layout_version": RESULT_LAYOUT_VERSION,
            "numeric_pipeline_version": NUMERIC_PIPELINE_VERSION,
            "kind": "odb_shared_numeric_data",
            "asset_id": numeric_asset_id(
                content_fingerprint, numeric_config_hash
            ),
            "odb_path": str(Path(odb_path).resolve()),
            "content_fingerprint": content_fingerprint,
            "numeric_config_hash": numeric_config_hash,
            "abaqus_version": str(abaqus_version),
            "group_independent_contents": [
                *NUMERIC_DIRECTORIES,
                *NUMERIC_FILES,
            ],
            "required_csv_columns": {
                path: list(columns)
                for path, columns in NUMERIC_PAYLOAD_REQUIRED_CSV_COLUMNS.items()
            },
        },
    )
    ensure_windows_hidden(manifest)
    return manifest


def numeric_asset_is_valid(
    asset_dir: Path | str,
    *,
    content_fingerprint: str,
    numeric_config_hash: str,
    abaqus_version: str,
) -> bool:
    root = Path(asset_dir)
    manifest_path = root / ASSET_MANIFEST_NAME
    if not manifest_path.is_file() or not numeric_payload_is_valid(root):
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            return False
        layout_version = int(manifest.get("layout_version", -1))
        numeric_pipeline_version = int(
            manifest.get("numeric_pipeline_version", -1)
        )
    except (OSError, ValueError, TypeError):
        return False
    return (
        layout_version == RESULT_LAYOUT_VERSION
        and numeric_pipeline_version == NUMERIC_PIPELINE_VERSION
        and manifest.get("kind") == "odb_shared_numeric_data"
        and manifest.get("content_fingerprint") == content_fingerprint
        and manifest.get("numeric_config_hash") == numeric_config_hash
        and str(manifest.get("abaqus_version", "")) == str(abaqus_version)
    )


def write_group_member_manifest(
    group_output_dir: Path | str,
    *,
    asset_dir: Path | str,
    comparison_group: str,
    odb_path: Path | str,
    content_fingerprint: str,
    numeric_config_hash: str,
) -> Path:
    output_root = Path(group_output_dir).resolve()
    asset_root = Path(asset_dir).resolve()
    manifest_path = output_root / GROUP_MEMBER_MANIFEST_NAME
    relative_asset = os.path.relpath(asset_root, output_root)
    save_json(
        manifest_path,
        {
            "layout_version": RESULT_LAYOUT_VERSION,
            "numeric_pipeline_version": NUMERIC_PIPELINE_VERSION,
            "kind": "comparison_group_member",
            "comparison_group": comparison_group,
            "odb_path": str(Path(odb_path).resolve()),
            "content_fingerprint": content_fingerprint,
            "numeric_config_hash": numeric_config_hash,
            "shared_data_relative_path": relative_asset,
            "shared_data_absolute_path": str(asset_root),
            "group_dependent_contents": [
                name
                for name in (
                    "frames",
                    "frames_transparent",
                    "animations",
                    "contours",
                    "contours_transparent",
                )
                if (output_root / name).exists()
            ],
        },
    )
    ensure_windows_hidden(manifest_path)
    return manifest_path


def resolve_group_member_asset(group_output_dir: Path | str) -> Path | None:
    output_root = Path(group_output_dir).resolve()
    manifest_path = output_root / GROUP_MEMBER_MANIFEST_NAME
    if not manifest_path.is_file():
        return None
    try:
        payload: dict[str, Any] = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError, TypeError):
        return None
    relative = str(payload.get("shared_data_relative_path", "")).strip()
    if relative:
        candidate = (output_root / relative).resolve()
        if candidate.is_dir():
            return candidate
    absolute = str(payload.get("shared_data_absolute_path", "")).strip()
    if absolute:
        candidate = Path(absolute)
        if candidate.is_dir():
            return candidate.resolve()
    return None
