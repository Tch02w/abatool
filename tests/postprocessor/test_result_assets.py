from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from modules.postprocessor.cache import (
    NUMERIC_PAYLOAD_REQUIRED_CSV_COLUMNS,
    NUMERIC_PIPELINE_VERSION,
)
from modules.postprocessor.file_attributes import clear_windows_hidden
from modules.postprocessor.result_assets import (
    ASSET_MANIFEST_NAME,
    RESULT_LAYOUT_VERSION,
    numeric_asset_dir,
    numeric_asset_is_valid,
    resolve_group_member_asset,
    write_group_member_manifest,
    write_numeric_asset_manifest,
)


def write_valid_numeric_payload(root: Path) -> None:
    rows = {
        "data/timeline_alignment.csv": {
            "SequenceIndex": 0,
            "StepIndex": 0,
            "StepName": "Load",
            "FrameIndex": 0,
            "TotalTime": 0.0,
        },
        "rebar/rebar_element_stress_force_timehistory.csv": {
            "SequenceIndex": 0,
            "InstanceName": "REBAR-1",
            "ElementLabel": 1,
            "ElementAxialForce_TensionPositive_N": 10.0,
            "ElementAxialForce_CompressionPositive_N": -10.0,
        },
    }
    diagnostic_row = {
        "SequenceIndex": 0,
        "Elevation_mm": 0.0,
        "RebarMethod": "element_cut",
        "RebarSectionRule": "section_t3d2_intersection",
        "RebarInterpolationRule": "linear_between_element_centroids",
        "RebarActiveRule": "section_t3d2_intersection",
        "RebarAxial_Section_TensionPositive_N": 10.0,
        "RebarAxial_Section_CompressionPositive_N": -10.0,
        "RebarAxial_Interpolated_TensionPositive_N": 9.5,
        "RebarAxial_Interpolated_CompressionPositive_N": -9.5,
        "CrossingT3D2ElementCount": 24,
        "CrossingT3D2WithS11Count": 24,
        "MissingS11CrossingCount": 0,
        "RebarSectionForceValid": True,
        "ExpectedLongitudinalRebarCount": 24,
        "ExpectedLongitudinalRebarCountSource": "odb_detected",
        "CrossingCountMatchesExpected": True,
        "CrossingCountValidationApplicable": True,
        "DuplicateCrossingCandidateCount": 0,
        "RebarDirectionCoordinateSource": "COORD",
        "RebarDirectionCOORDNodeCount": 48,
        "RebarDirectionReferencePlusUNodeCount": 0,
        "RebarDirectionReferenceNodeCount": 0,
    }
    rows["freebody/pile_total_axial_force_time_aligned.csv"] = diagnostic_row
    rows["freebody/rebar_section_diagnostics.csv"] = diagnostic_row
    for relative, required_columns in NUMERIC_PAYLOAD_REQUIRED_CSV_COLUMNS.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(required_columns))
            writer.writeheader()
            writer.writerow(rows[relative])
    (root / "rebar" / "rebar_metadata.json").write_text(
        json.dumps(
            {
                "method": "element_cut",
                "legacy_method": "linear_between_element_centroids",
                "element_cut_rule": "section_t3d2_intersection",
                "cut_tolerance_mm": 0.0001,
                "longitudinal_element_count": 24,
            }
        ),
        encoding="utf-8",
    )
    (root / "metadata.json").write_text("{}", encoding="utf-8")
    (root / "summary.xlsx").write_bytes(b"xlsx")


def test_group_member_resolves_shared_numeric_asset(tmp_path: Path) -> None:
    asset = numeric_asset_dir(tmp_path, tmp_path / "A.odb", "a" * 64, "b" * 64)
    write_valid_numeric_payload(asset)
    write_numeric_asset_manifest(
        asset,
        odb_path=tmp_path / "A.odb",
        content_fingerprint="a" * 64,
        numeric_config_hash="b" * 64,
        abaqus_version="2025",
    )
    manifest = json.loads(
        (asset / ASSET_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert manifest["layout_version"] == RESULT_LAYOUT_VERSION
    assert manifest["numeric_pipeline_version"] == NUMERIC_PIPELINE_VERSION
    assert manifest["required_csv_columns"][
        "freebody/rebar_section_diagnostics.csv"
    ] == list(
        NUMERIC_PAYLOAD_REQUIRED_CSV_COLUMNS[
            "freebody/rebar_section_diagnostics.csv"
        ]
    )
    assert numeric_asset_is_valid(
        asset,
        content_fingerprint="a" * 64,
        numeric_config_hash="b" * 64,
        abaqus_version="2025",
    )

    group_output = tmp_path / "组A" / "batch" / "A"
    group_output.mkdir(parents=True)
    write_group_member_manifest(
        group_output,
        asset_dir=asset,
        comparison_group="组A",
        odb_path=tmp_path / "A.odb",
        content_fingerprint="a" * 64,
        numeric_config_hash="b" * 64,
    )
    assert resolve_group_member_asset(group_output) == asset.resolve()


def test_empty_legacy_numeric_directories_are_not_reusable(tmp_path: Path) -> None:
    asset = tmp_path / "legacy"
    (asset / "data").mkdir(parents=True)
    (asset / "data" / "timeline_alignment.csv").write_text(
        "SequenceIndex\n0\n", encoding="utf-8"
    )
    (asset / "rebar").mkdir()
    (asset / "freebody").mkdir()
    (asset / "metadata.json").write_text("{}", encoding="utf-8")
    (asset / "summary.xlsx").write_bytes(b"xlsx")

    with pytest.raises(ValueError, match="数值资产不完整"):
        write_numeric_asset_manifest(
            asset,
            odb_path=tmp_path / "A.odb",
            content_fingerprint="a" * 64,
            numeric_config_hash="b" * 64,
            abaqus_version="2025",
        )


def test_legacy_manifest_and_missing_diagnostic_column_are_invalid(
    tmp_path: Path,
) -> None:
    asset = tmp_path / "asset"
    write_valid_numeric_payload(asset)
    write_numeric_asset_manifest(
        asset,
        odb_path=tmp_path / "A.odb",
        content_fingerprint="a" * 64,
        numeric_config_hash="b" * 64,
        abaqus_version="2025",
    )
    manifest_path = asset / ASSET_MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("numeric_pipeline_version")
    manifest["layout_version"] = RESULT_LAYOUT_VERSION - 1
    clear_windows_hidden(manifest_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert not numeric_asset_is_valid(
        asset,
        content_fingerprint="a" * 64,
        numeric_config_hash="b" * 64,
        abaqus_version="2025",
    )

    write_valid_numeric_payload(asset)
    write_numeric_asset_manifest(
        asset,
        odb_path=tmp_path / "A.odb",
        content_fingerprint="a" * 64,
        numeric_config_hash="b" * 64,
        abaqus_version="2025",
    )
    diagnostic_path = asset / "freebody" / "rebar_section_diagnostics.csv"
    required = list(
        NUMERIC_PAYLOAD_REQUIRED_CSV_COLUMNS[
            "freebody/rebar_section_diagnostics.csv"
        ]
    )
    required.remove("MissingS11CrossingCount")
    with diagnostic_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=required)
        writer.writeheader()
        writer.writerow({name: "0" for name in required})
    assert not numeric_asset_is_valid(
        asset,
        content_fingerprint="a" * 64,
        numeric_config_hash="b" * 64,
        abaqus_version="2025",
    )


def test_numeric_asset_rejects_ambiguous_duplicate_rebar_crossing(
    tmp_path: Path,
) -> None:
    asset = tmp_path / "asset"
    write_valid_numeric_payload(asset)
    write_numeric_asset_manifest(
        asset,
        odb_path=tmp_path / "A.odb",
        content_fingerprint="a" * 64,
        numeric_config_hash="b" * 64,
        abaqus_version="2025",
    )
    diagnostic_path = asset / "freebody" / "rebar_section_diagnostics.csv"
    with diagnostic_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = list(reader.fieldnames or ())
        rows = list(reader)
    rows[0]["DuplicateCrossingCandidateCount"] = "1"
    with diagnostic_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    assert not numeric_asset_is_valid(
        asset,
        content_fingerprint="a" * 64,
        numeric_config_hash="b" * 64,
        abaqus_version="2025",
    )
