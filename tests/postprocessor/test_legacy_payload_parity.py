"""Compare the native payload with the actual pre-WinUI widget implementation."""
import os
import json
import threading
from dataclasses import fields
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from modules.postprocessor.app import MainWindow
from modules.postprocessor.main_window import FRAME_MODE_LABELS
from modules.postprocessor.models import OdbScan
from modules.postprocessor.postprocess_execution import PostprocessJob, PostprocessOptions, _job_payload
from modules.postprocessor import batch_window, postprocess_execution
from modules.postprocessor.runner_parallel import MultiProcessController
from modules.postprocessor.process_runner import ProcessCancelled
from modules.postprocessor.result_assets import INCOMPLETE_OUTPUT_MARKER, GROUP_MEMBER_MANIFEST_NAME
from tests.postprocessor.test_queue_cache import write_valid_numeric_extraction


@pytest.mark.parametrize("pile_type", ["RC", "CFST"])
@pytest.mark.parametrize("frame_mode", ["auto", "all", "manual"])
@pytest.mark.parametrize("method", ["element_cut", "legacy_interpolation"])
@pytest.mark.parametrize("render_outcome", ["complete", "cancel", "error"])
def test_native_worker_payload_matches_legacy(tmp_path, monkeypatch, pile_type, frame_mode, method, render_outcome):
    monkeypatch.setenv("ABAQUS_POSTPROCESSOR_DATA_DIR", str(tmp_path / "state"))
    app = QApplication.instance() or QApplication([])
    odb = tmp_path / "GJA-2-R_U100D.odb"
    odb.write_bytes(b"fixture")
    window = MainWindow()
    try:
        window.state_path = tmp_path / "project_state.json"
        window._load_folder_state(str(tmp_path))
        window._populate([OdbScan(
            path=odb, steps=["Load"], assembly_node_sets=["SET-LOAD"],
            assembly_element_sets=["SET-PILE", "SET-PILE_CON", "SET-KEY", "SET-SOIL_CUT", "SET-REBAR"],
            field_outputs=["S", "U"],
        )])
        row = window.rows_by_path[str(odb.resolve())]
        row["pile_type"].setCurrentText(pile_type)
        row["frame_mode"].setCurrentText(next(label for label, mode in FRAME_MODE_LABELS.items() if mode == frame_mode))
        row["manual_frames"].setText("0,2-4" if frame_mode == "manual" else "")
        window.rebar_method_selector.setCurrentIndex(window.rebar_method_selector.findData(method))
        window.expected_longitudinal_rebar_count_input.setValue(24)
        window.full_timehistory.setChecked(True)
        output = tmp_path / "output"
        legacy = window._job_payload(row, output)
        # Legacy UI has no explicit no-rebar mode; preserve its required-bars default.
        job_values = {field.name: legacy[field.name] for field in fields(PostprocessJob) if field.name not in {"path", "reinforcement_mode"}}
        options = PostprocessOptions(
            abaqus_command="abaqus", root=tmp_path, parallel_workers=2, force_rescan=False,
            full_timehistory_freebody=legacy["full_timehistory_freebody"],
            rebar_method=legacy["rebar_method"],
            expected_longitudinal_rebar_count=legacy["expected_longitudinal_rebar_count"],
            settings=legacy["settings"],
        )
        native = _job_payload(PostprocessJob(path=odb, **job_values), output, options, legacy["comparison_group"])
        assert native == legacy

        traces = {"legacy": [], "native": []}
        render_outputs = {}
        for label, module in (("legacy", batch_window), ("native", postprocess_execution)):
            def record(stage, config_path, label=label):
                payload = json.loads(config_path.read_text(encoding="utf-8"))
                normalized = {key: value for key, value in payload.items() if key not in ("output_dir", "source_output_dir")}
                traces[label].append((stage, normalized))
                return Path(payload["output_dir"])

            def prescan(command, config_path, *args, record=record):
                record("prescan", config_path)
                return {
                    "frame_catalog": [{"SequenceIndex": i, "ranges": {"PILE_U_MAG": {"min": 0, "max": i + 1}}} for i in range(5)],
                    "auto_detection": {"prefracture_sequence_index": 2},
                }

            def extract(command, config_path, *args, record=record):
                write_valid_numeric_extraction(record("extract", config_path))

            def render(command, config_path, *args, record=record, label=label):
                render_outputs[label] = record("render", config_path)
                if label == "native" and render_outcome == "cancel":
                    args[-1].cancel()
                if label == "native" and render_outcome == "error":
                    raise RuntimeError("render failed")

            monkeypatch.setattr(module, "scan_field_ranges", prescan)
            monkeypatch.setattr(module, "run_job", extract)
            monkeypatch.setattr(module, "render_group_contours", render)
            monkeypatch.setattr(module, "numeric_asset_is_valid", lambda *a, **kw: False)
            monkeypatch.setattr(module, "numeric_cache_is_valid", lambda *a, **kw: False)
            monkeypatch.setattr(module, "finalize_numeric_output", lambda folder: (Path(folder) / "summary.xlsx").write_bytes(b"fixture"))
            monkeypatch.setattr(module, "finalize_render_output", lambda *a, **kw: None)
            monkeypatch.setattr(module, "batch_temp_dir", lambda batch: tmp_path / "scratch" / batch)

        name = legacy["comparison_group"]
        old_task = {
            "id": "group", "name": name, "members": [str(odb)],
            "plan": {"overrides": {}, "standalone": False},
            "snapshots": {str(odb): legacy}, "force_rescan": True,
            "folder_root": str(tmp_path), "batch_id": "legacy",
        }
        window._execute_group_task(old_task, 1, MultiProcessController(), lambda message: None)
        group = postprocess_execution.PostprocessGroup("group", name, (odb,))
        from dataclasses import replace
        plan = postprocess_execution.PostprocessPlan(
            jobs={odb: PostprocessJob(path=odb, **job_values)}, groups=(group,),
            options=replace(options, force_rescan=True), batch_id="native",
        )
        if render_outcome == "complete":
            postprocess_execution._execute_group(plan, group, 0, lambda *a: None, None, MultiProcessController(), threading.Lock())
            assert not (render_outputs["native"] / INCOMPLETE_OUTPUT_MARKER).exists()
            assert (render_outputs["native"] / GROUP_MEMBER_MANIFEST_NAME).is_file()
        else:
            error = ProcessCancelled if render_outcome == "cancel" else RuntimeError
            with pytest.raises(error):
                postprocess_execution._execute_group(plan, group, 0, lambda *a: None, None, MultiProcessController(), threading.Lock())
            assert (render_outputs["native"] / INCOMPLETE_OUTPUT_MARKER).is_file()
            assert not (render_outputs["native"] / GROUP_MEMBER_MANIFEST_NAME).exists()
        assert [stage for stage, _ in traces["legacy"]] == ["prescan", "extract", "render"]
        assert traces["native"] == traces["legacy"]
    finally:
        window.close()
        app.processEvents()
