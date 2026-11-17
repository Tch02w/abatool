"""Persistent ODB scan and extraction cache helpers.

Cache identity is based on sampled file content rather than the file name.
This lets a renamed or copied ODB reuse completed work without hashing the
entire (potentially very large) file.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

from .config import save_json

CACHE_SCHEMA_VERSION = 2
NUMERIC_PIPELINE_VERSION = 2
SAMPLE_SIZE = 64 * 1024
CACHE_KINDS = ("compatibility", "initial", "prescan", "numeric")

# A successful current numeric extraction must expose both the element-cut
# result and the legacy interpolation result.  These contracts deliberately
# live beside the cache schema so a cache hit cannot bless a legacy directory
# merely because its top-level folders still exist.
NUMERIC_PAYLOAD_REQUIRED_CSV_COLUMNS: dict[str, tuple[str, ...]] = {
    "data/timeline_alignment.csv": (
        "SequenceIndex",
        "StepIndex",
        "StepName",
        "FrameIndex",
        "TotalTime",
    ),
    "rebar/rebar_element_stress_force_timehistory.csv": (
        "SequenceIndex",
        "InstanceName",
        "ElementLabel",
        "ElementAxialForce_TensionPositive_N",
        "ElementAxialForce_CompressionPositive_N",
    ),
    "freebody/pile_total_axial_force_time_aligned.csv": (
        "SequenceIndex",
        "Elevation_mm",
        "RebarMethod",
        "RebarSectionRule",
        "RebarInterpolationRule",
        "RebarActiveRule",
        "RebarAxial_Section_TensionPositive_N",
        "RebarAxial_Section_CompressionPositive_N",
        "RebarAxial_Interpolated_TensionPositive_N",
        "RebarAxial_Interpolated_CompressionPositive_N",
        "CrossingT3D2ElementCount",
        "CrossingT3D2WithS11Count",
        "MissingS11CrossingCount",
        "RebarSectionForceValid",
        "ExpectedLongitudinalRebarCount",
        "ExpectedLongitudinalRebarCountSource",
        "CrossingCountMatchesExpected",
        "CrossingCountValidationApplicable",
        "DuplicateCrossingCandidateCount",
        "RebarDirectionCoordinateSource",
        "RebarDirectionCOORDNodeCount",
        "RebarDirectionReferencePlusUNodeCount",
        "RebarDirectionReferenceNodeCount",
    ),
    "freebody/rebar_section_diagnostics.csv": (
        "SequenceIndex",
        "Elevation_mm",
        "RebarMethod",
        "RebarSectionRule",
        "RebarInterpolationRule",
        "RebarActiveRule",
        "RebarAxial_Section_TensionPositive_N",
        "RebarAxial_Section_CompressionPositive_N",
        "RebarAxial_Interpolated_TensionPositive_N",
        "RebarAxial_Interpolated_CompressionPositive_N",
        "CrossingT3D2ElementCount",
        "CrossingT3D2WithS11Count",
        "MissingS11CrossingCount",
        "RebarSectionForceValid",
        "ExpectedLongitudinalRebarCount",
        "ExpectedLongitudinalRebarCountSource",
        "CrossingCountMatchesExpected",
        "CrossingCountValidationApplicable",
        "DuplicateCrossingCandidateCount",
        "RebarDirectionCoordinateSource",
        "RebarDirectionCOORDNodeCount",
        "RebarDirectionReferencePlusUNodeCount",
        "RebarDirectionReferenceNodeCount",
    ),
}
NUMERIC_PAYLOAD_REQUIRED_REBAR_METADATA_FIELDS = (
    "method",
    "legacy_method",
    "element_cut_rule",
    "cut_tolerance_mm",
    "longitudinal_element_count",
)


def quick_odb_fingerprint(path: Path, sample_size: int = SAMPLE_SIZE) -> str:
    """Hash file size plus fixed head/middle/tail samples with SHA-256."""

    source = path.resolve()
    before = source.stat()
    size = before.st_size
    digest = hashlib.sha256()
    digest.update(str(size).encode("ascii"))
    offsets = (0, max((size - sample_size) // 2, 0), max(size - sample_size, 0))
    with source.open("rb") as stream:
        for offset in offsets:
            stream.seek(offset)
            block = stream.read(sample_size)
            digest.update(offset.to_bytes(8, "big", signed=False))
            digest.update(len(block).to_bytes(8, "big", signed=False))
            digest.update(block)
    after = source.stat()
    if (
        after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
    ):
        raise RuntimeError(f"ODB 文件在生成缓存指纹时发生变化：{source}")
    return digest.hexdigest()


def stable_config_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def odb_file_metadata(path: Path) -> dict[str, Any]:
    source = path.resolve()
    stat = source.stat()
    return {
        "odb_path": str(source),
        "file_size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def _load_json_mapping(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _csv_contract_error(
    path: Path,
    required_columns: tuple[str, ...],
    *, allow_empty: bool = False,
) -> str | None:
    if not path.is_file() or path.stat().st_size <= 0:
        return f"缺少或为空：{path}"
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fieldnames = tuple(reader.fieldnames or ())
            missing = [name for name in required_columns if name not in fieldnames]
            if missing:
                return f"{path} 缺少列：{', '.join(missing)}"
            first_row = next(reader, None)
    except (OSError, UnicodeError, csv.Error) as error:
        return f"{path} 无法读取：{error}"
    if first_row is None and not allow_empty:
        return f"没有数值记录：{path}"
    return None


def _diagnostic_values_error(path: Path, *, unreinforced: bool = False) -> str | None:
    force_columns = (
        "RebarAxial_Section_TensionPositive_N",
        "RebarAxial_Section_CompressionPositive_N",
        "RebarAxial_Interpolated_TensionPositive_N",
        "RebarAxial_Interpolated_CompressionPositive_N",
    )
    crossing_columns = (
        "CrossingT3D2ElementCount",
        "CrossingT3D2WithS11Count",
        "MissingS11CrossingCount",
    )
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            for row_number, row in enumerate(csv.DictReader(stream), 2):
                method = str(row.get("RebarMethod", "")).strip().casefold()
                methods = {"element_cut", "legacy_interpolation"}
                if unreinforced:
                    methods.add("not_applicable_unreinforced")
                    try:
                        if any(float(row.get(name, "")) != 0 for name in force_columns + crossing_columns):
                            return f"{path}:{row_number} 无纵筋模型含非零纵筋结果"
                    except (ValueError, TypeError):
                        return f"{path}:{row_number} 无纵筋结果不完整"
                if method not in methods:
                    return f"{path}:{row_number} 的 RebarMethod 无效"
                missing_forces = [
                    name
                    for name in force_columns
                    if str(row.get(name, "")).strip() == ""
                ]
                if missing_forces:
                    return (
                        f"{path}:{row_number} 缺少钢筋力："
                        f"{', '.join(missing_forces)}"
                    )
                section_valid = str(
                    row.get("RebarSectionForceValid", "")
                ).strip().casefold()
                if section_valid not in {"1", "true", "yes"}:
                    return f"{path}:{row_number} 的钢筋截面力无效"
                try:
                    crossing_values = {
                        name: int(float(str(row.get(name, "")).strip()))
                        for name in crossing_columns
                    }
                    duplicate_crossings = int(
                        float(
                            str(
                                row.get("DuplicateCrossingCandidateCount", "")
                            ).strip()
                        )
                    )
                except (TypeError, ValueError):
                    return f"{path}:{row_number} 缺少 S11 交叉诊断"
                crossing_count = crossing_values["CrossingT3D2ElementCount"]
                with_s11_count = crossing_values["CrossingT3D2WithS11Count"]
                missing_s11 = crossing_values["MissingS11CrossingCount"]
                if (
                    min(crossing_values.values()) < 0
                    or with_s11_count > crossing_count
                    or crossing_count - with_s11_count != missing_s11
                ):
                    return f"{path}:{row_number} 的 S11 交叉计数不一致"
                if missing_s11 != 0:
                    return f"{path}:{row_number} 有 {missing_s11} 个交叉单元缺少 S11"
                if duplicate_crossings != 0:
                    return (
                        f"{path}:{row_number} 有 {duplicate_crossings} 个"
                        "无法唯一归属的纵筋交叉候选"
                    )
    except (OSError, UnicodeError, csv.Error) as error:
        return f"{path} 无法读取：{error}"
    return None


def numeric_payload_validation_errors(root: Path | str) -> list[str]:
    """Return reasons why a numeric payload cannot be reused safely."""

    payload_root = Path(root)
    errors: list[str] = []
    rebar_metadata = _load_json_mapping(payload_root / "rebar" / "rebar_metadata.json")
    unreinforced = bool(rebar_metadata and rebar_metadata.get("reinforcement_mode") == "none"
                        and rebar_metadata.get("longitudinal_element_count") == 0)
    for relative, columns in NUMERIC_PAYLOAD_REQUIRED_CSV_COLUMNS.items():
        path = payload_root / Path(relative)
        try:
            error = _csv_contract_error(path, columns, allow_empty=unreinforced and relative.startswith("rebar/"))
        except OSError as exc:
            error = f"{path} 无法读取：{exc}"
        if error:
            errors.append(error)
        elif relative.startswith("freebody/"):
            diagnostic_error = _diagnostic_values_error(path, unreinforced=unreinforced)
            if diagnostic_error:
                errors.append(diagnostic_error)

    metadata_path = payload_root / "metadata.json"
    if _load_json_mapping(metadata_path) is None:
        errors.append(f"缺少或无法读取：{metadata_path}")

    rebar_metadata_path = payload_root / "rebar" / "rebar_metadata.json"
    rebar_metadata = _load_json_mapping(rebar_metadata_path)
    if rebar_metadata is None:
        errors.append(f"缺少或无法读取：{rebar_metadata_path}")
    else:
        missing = [
            field
            for field in NUMERIC_PAYLOAD_REQUIRED_REBAR_METADATA_FIELDS
            if field not in rebar_metadata
        ]
        if missing:
            errors.append(
                f"{rebar_metadata_path} 缺少字段：{', '.join(missing)}"
            )

    summary_path = payload_root / "summary.xlsx"
    try:
        summary_ready = summary_path.is_file() and summary_path.stat().st_size > 0
    except OSError:
        summary_ready = False
    if not summary_ready:
        errors.append(f"缺少或为空：{summary_path}")
    return errors


def numeric_payload_is_valid(root: Path | str) -> bool:
    """Require current non-empty CSV and metadata contracts."""

    return not numeric_payload_validation_errors(root)


def cache_entry_dir(
    cache_root: Path,
    kind: str,
    content_fingerprint: str,
    config_hash: str = "",
) -> Path:
    path = cache_root / kind / content_fingerprint
    if config_hash:
        path /= config_hash
    return path


def invalidate_content_fingerprint(
    cache_root: Path,
    content_fingerprint: str,
) -> list[Path]:
    """Remove every known cache layer associated with one ODB fingerprint."""

    removed: list[Path] = []
    root = cache_root.resolve()
    for kind in CACHE_KINDS:
        target = root / kind / content_fingerprint
        if not target.is_dir():
            continue
        shutil.rmtree(target)
        removed.append(target)
    return removed


def cache_metadata(
    *,
    kind: str,
    odb_path: Path,
    content_fingerprint: str,
    abaqus_version: str,
    config_hash: str,
    config_snapshot: Any,
) -> dict[str, Any]:
    metadata = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "kind": kind,
        "content_fingerprint": content_fingerprint,
        "abaqus_version": str(abaqus_version),
        "config_hash": config_hash,
        "config_snapshot": config_snapshot,
        **odb_file_metadata(odb_path),
    }
    if kind == "numeric":
        metadata["numeric_pipeline_version"] = NUMERIC_PIPELINE_VERSION
    return metadata


def metadata_matches(
    metadata: dict[str, Any],
    *,
    kind: str,
    content_fingerprint: str,
    abaqus_version: str,
    config_hash: str,
) -> bool:
    """Validate identity fields; mtime/path are intentionally informational."""

    if not isinstance(metadata, dict):
        return False
    try:
        schema_version = int(metadata.get("schema_version", -1))
        numeric_pipeline_version = int(
            metadata.get("numeric_pipeline_version", -1)
        )
    except (TypeError, ValueError):
        return False
    return (
        schema_version == CACHE_SCHEMA_VERSION
        and metadata.get("kind") == kind
        and metadata.get("content_fingerprint") == content_fingerprint
        and str(metadata.get("abaqus_version", "")) == str(abaqus_version)
        and metadata.get("config_hash", "") == config_hash
        and (
            kind != "numeric"
            or numeric_pipeline_version == NUMERIC_PIPELINE_VERSION
        )
    )


def load_json_cache(
    cache_root: Path,
    kind: str,
    content_fingerprint: str,
    abaqus_version: str,
    config_hash: str = "",
) -> dict[str, Any] | None:
    entry = cache_entry_dir(cache_root, kind, content_fingerprint, config_hash)
    metadata_path = entry / "cache_metadata.json"
    payload_path = entry / "payload.json"
    if not metadata_path.is_file() or not payload_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not metadata_matches(
            metadata,
            kind=kind,
            content_fingerprint=content_fingerprint,
            abaqus_version=abaqus_version,
            config_hash=config_hash,
        ):
            return None
        return json.loads(payload_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None


def save_json_cache(
    cache_root: Path,
    kind: str,
    odb_path: Path,
    content_fingerprint: str,
    abaqus_version: str,
    payload: dict[str, Any],
    *,
    config_hash: str = "",
    config_snapshot: Any = None,
) -> Path:
    entry = cache_entry_dir(cache_root, kind, content_fingerprint, config_hash)
    entry.mkdir(parents=True, exist_ok=True)
    save_json(entry / "payload.json", payload)
    save_json(
        entry / "cache_metadata.json",
        cache_metadata(
            kind=kind,
            odb_path=odb_path,
            content_fingerprint=content_fingerprint,
            abaqus_version=abaqus_version,
            config_hash=config_hash,
            config_snapshot=config_snapshot,
        ),
    )
    return entry


def numeric_config_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the frozen fields that can affect extracted numeric results."""

    keys = (
        "start_step",
        "end_step",
        "frame_mode",
        "manual_sequence_expression",
        "selected_sequence_indices",
        "load_direction",
        "load_set",
        "pile_type",
        "pile_display_set",
        "pile_concrete_set",
        "pile_steel_set",
        "soil_set",
        "rebar_set",
        "reinforcement_mode",
        "longitudinal_material",
        "rebar_diameter_mm",
        "prefracture_sequence_index",
        "full_timehistory_freebody",
        "rebar_method",
        "expected_longitudinal_rebar_count",
    )
    settings = payload.get("settings", {})
    numeric_setting_keys = (
        "axial_cut_count",
        "pile_head_above_ground_mm",
        "longitudinal_orientation_threshold",
        "rebar_cut_tolerance_mm",
        "damage_threshold",
    )
    return {
        "numeric_pipeline_version": NUMERIC_PIPELINE_VERSION,
        **{key: payload.get(key) for key in keys},
        "settings": {
            key: settings.get(key) for key in numeric_setting_keys
        },
    }


def prescan_config_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Return inputs used by the field-range/damage prescan."""

    keys = (
        "start_step",
        "end_step",
        "pile_display_set",
        "pile_concrete_set",
        "pile_steel_set",
        "soil_set",
        "rebar_set",
        "reinforcement_mode",
        "longitudinal_material",
    )
    settings = payload.get("settings", {})
    prescan_setting_keys = (
        "longitudinal_orientation_threshold",
        "soil_section_coordinate",
        "damage_threshold",
        "damage_angular_coverage",
    )
    return {
        **{key: payload.get(key) for key in keys},
        "settings": {
            key: settings.get(key) for key in prescan_setting_keys
        },
    }


def numeric_cache_is_valid(
    entry: Path,
    *,
    content_fingerprint: str,
    abaqus_version: str,
    config_hash: str,
) -> bool:
    metadata_path = entry / "cache_metadata.json"
    if not metadata_path.is_file() or not numeric_payload_is_valid(entry):
        return False
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return metadata_matches(
        metadata,
        kind="numeric",
        content_fingerprint=content_fingerprint,
        abaqus_version=abaqus_version,
        config_hash=config_hash,
    )


def write_numeric_cache_metadata(
    entry: Path,
    *,
    odb_path: Path,
    content_fingerprint: str,
    abaqus_version: str,
    config_hash: str,
    config_snapshot: dict[str, Any],
) -> None:
    entry.mkdir(parents=True, exist_ok=True)
    save_json(
        entry / "cache_metadata.json",
        cache_metadata(
            kind="numeric",
            odb_path=odb_path,
            content_fingerprint=content_fingerprint,
            abaqus_version=abaqus_version,
            config_hash=config_hash,
            config_snapshot=config_snapshot,
        ),
    )


def abaqus_cache_version(defaults: dict[str, Any]) -> str:
    """Keep release and executable identity separate from the content key."""

    return "{0}|{1}".format(
        defaults.get("local_abaqus_release", ""),
        os.path.normcase(str(defaults.get("abaqus_command", ""))),
    )
