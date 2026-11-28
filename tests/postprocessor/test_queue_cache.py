from __future__ import annotations

import csv
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from modules.postprocessor import batch_window as batch_module
from modules.postprocessor.app import MainWindow
from modules.postprocessor.cache import NUMERIC_PAYLOAD_REQUIRED_CSV_COLUMNS
from modules.postprocessor.config import save_json
from modules.postprocessor.models import OdbScan
from modules.postprocessor.result_assets import ASSET_MANIFEST_NAME, resolve_group_member_asset
from modules.postprocessor.runner_parallel import MultiProcessController


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def scan(path: Path) -> OdbScan:
    return OdbScan(
        path=path,
        steps=["Load"],
        assembly_node_sets=["SET-LOAD"],
        assembly_element_sets=[
            "SET-PILE",
            "SET-PILE_CON",
            "SET-KEY",
            "SET-SOIL_CUT",
            "SET-REBAR",
        ],
        field_outputs=["U", "S", "PEMAG"],
    )


def write_valid_numeric_extraction(output: Path) -> None:
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
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(required_columns))
            writer.writeheader()
            writer.writerow(rows[relative])
    (output / "rebar" / "rebar_metadata.json").write_text(
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
    (output / "History_Output").mkdir(exist_ok=True)
    (output / "metadata.json").write_text("{}", encoding="utf-8")


def test_sequential_groups_reuse_prescan_and_numeric_cache(
    tmp_path: Path, monkeypatch
) -> None:
    application()
    folder = tmp_path / "odb"
    folder.mkdir()
    odb = folder / "GJA-2-R_U100D.odb"
    odb.write_bytes(b"representative-odb-content")

    window = MainWindow()
    window.state_path = tmp_path / "project_state.json"
    window._load_folder_state(str(folder))
    window._populate([scan(odb)])
    path = str(odb.resolve())
    snapshot = window._job_payload(window.rows_by_path[path], Path("."))
    calls = {"prescan": 0, "extract": 0, "render": 0}

    def fake_prescan(*_args, **_kwargs):
        calls["prescan"] += 1
        return {
            "frame_catalog": [
                {
                    "SequenceIndex": 0,
                    "ranges": {
                        "PILE_U_MAG": {"min": 0.0, "max": 1.0}
                    },
                },
                {
                    "SequenceIndex": 1,
                    "ranges": {
                        "PILE_U_MAG": {"min": -2.0, "max": 3.0}
                    },
                },
            ],
            "auto_detection": {"prefracture_sequence_index": 0},
        }

    def fake_extract(_command, config_path, _log, _controller):
        calls["extract"] += 1
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        output = Path(config["output_dir"])
        write_valid_numeric_extraction(output)

    def fake_render(_command, config_path, _log, _controller):
        calls["render"] += 1
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        assert Path(config["source_output_dir"]).is_dir()
        assert config["animation_legend_ranges"]["PILE_U_MAG"] == {
            "min": -2.0,
            "max": 3.0,
            "observed_min": -2.0,
            "observed_max": 3.0,
            "source": "comparison_group_full_animation_timeline",
            "comparison_group": config["comparison_group"],
        }

    monkeypatch.setattr(batch_module, "scan_field_ranges", fake_prescan)
    monkeypatch.setattr(batch_module, "run_job", fake_extract)
    monkeypatch.setattr(batch_module, "render_group_contours", fake_render)

    def fake_finalize_numeric(output_dir):
        (Path(output_dir) / "summary.xlsx").write_bytes(b"xlsx")

    monkeypatch.setattr(
        batch_module, "finalize_numeric_output", fake_finalize_numeric
    )
    monkeypatch.setattr(
        batch_module,
        "finalize_render_output",
        lambda *_args, **_kwargs: None,
    )

    logs: list[str] = []

    def task(group_id: str, name: str, batch_id: str) -> dict:
        return {
            "id": group_id,
            "name": name,
            "plan": {
                "id": group_id,
                "name": name,
                "members": [path],
                "overrides": {},
                "standalone": False,
            },
            "members": [path],
            "snapshots": {path: snapshot},
            "force_rescan": False,
            "batch_id": batch_id,
            "folder_root": str(folder.resolve()),
        }

    first_outputs = window._execute_group_task(
        task("a", "组A", "20260723_120000_000001"),
        1,
        MultiProcessController(),
        logs.append,
    )
    second_outputs = window._execute_group_task(
        task("b", "组B", "20260723_120001_000001"),
        1,
        MultiProcessController(),
        logs.append,
    )

    first_output = Path(first_outputs[0])
    second_output = Path(second_outputs[0])
    assert not (first_output / "data").exists()
    assert not (second_output / "data").exists()
    first_asset = resolve_group_member_asset(first_output)
    second_asset = resolve_group_member_asset(second_output)
    assert first_asset is not None
    assert first_asset == second_asset
    assert (first_asset / "data" / "timeline_alignment.csv").is_file()
    assert (first_asset / "summary.xlsx").is_file()

    # An incomplete shared asset can be rebuilt from a valid persistent cache.
    # A sentinel proves that the deterministic shared directory is cleaned
    # before the cache payload is restored.
    (first_asset / "freebody" / "rebar_section_diagnostics.csv").write_text(
        "SequenceIndex\n0\n", encoding="utf-8"
    )
    (first_asset / "stale-from-interrupted-run.txt").write_text(
        "stale", encoding="utf-8"
    )
    numeric_entries = list((folder / "cache" / "numeric").glob("*/*"))
    assert len(numeric_entries) == 1
    third_outputs = window._execute_group_task(
        task("c", "组C", "20260723_120002_000001"),
        1,
        MultiProcessController(),
        logs.append,
    )
    third_asset = resolve_group_member_asset(Path(third_outputs[0]))
    assert third_asset == first_asset
    assert not (first_asset / "stale-from-interrupted-run.txt").exists()
    assert calls == {"prescan": 1, "extract": 1, "render": 3}

    # If both copies are stale, neither may suppress a fresh Abaqus extraction.
    (first_asset / "freebody" / "rebar_section_diagnostics.csv").write_text(
        "SequenceIndex\n0\n", encoding="utf-8"
    )
    (first_asset / "stale-from-interrupted-run.txt").write_text(
        "stale", encoding="utf-8"
    )
    (
        numeric_entries[0]
        / "freebody"
        / "rebar_section_diagnostics.csv"
    ).write_text("SequenceIndex\n0\n", encoding="utf-8")
    fourth_outputs = window._execute_group_task(
        task("d", "组D", "20260723_120003_000001"),
        1,
        MultiProcessController(),
        logs.append,
    )

    assert calls == {"prescan": 1, "extract": 2, "render": 4}
    fourth_asset = resolve_group_member_asset(Path(fourth_outputs[0]))
    assert fourth_asset == first_asset
    assert not (first_asset / "stale-from-interrupted-run.txt").exists()
    assert any("命中预扫描缓存" in message for message in logs)
    assert any("从持久缓存恢复 ODB 公共数据" in message for message in logs)
    assert any("复用 ODB 公共数据" in message for message in logs)

    # A project with only its old publication can regenerate the workbook offline.
    old_asset = first_asset.with_name(first_asset.name.rsplit("-w", 1)[0])
    first_asset.rename(old_asset)
    manifest_path = old_asset / ASSET_MANIFEST_NAME
    manifest = json.loads(manifest_path.read_bytes())
    del manifest["workbook_version"]
    manifest["asset_id"] = old_asset.name
    save_json(manifest_path, manifest)
    (old_asset / "summary.xlsx").write_bytes(b"legacy workbook fixture")
    numeric_entries[0].rename(tmp_path / "unused-cache")
    outputs = window._execute_group_task(
        task("e", "组E", "20260723_120004_000001"), 1, MultiProcessController(), logs.append
    )
    assert resolve_group_member_asset(Path(outputs[0])) == first_asset
    assert (old_asset / "summary.xlsx").read_bytes() == b"legacy workbook fixture"
    assert (first_asset / "summary.xlsx").read_bytes() == b"xlsx"
    assert calls == {"prescan": 1, "extract": 2, "render": 5}
    window.close()
