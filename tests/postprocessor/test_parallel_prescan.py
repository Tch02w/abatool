import json
import threading
from pathlib import Path

import pytest
from PIL import Image

from modules.postprocessor import postprocess_execution as execution
from modules.postprocessor.runner_parallel import MultiProcessController


def test_group_results_preserve_requested_order_after_parallel_completion(tmp_path, monkeypatch):
    paths = [tmp_path / name for name in ("z-last-alphabetically.odb", "a-first-alphabetically.odb")]
    for path in paths:
        path.write_bytes(path.name.encode())
    group = execution.PostprocessGroup("g", "comparison", tuple(paths))
    plan = execution.PostprocessPlan(
        jobs={path: execution.PostprocessJob(path=path, start_step="Load", end_step="Load") for path in paths},
        groups=(group,), options=execution.PostprocessOptions(
            "abaqus", tmp_path, 2, True, False, "element_cut", 0,
            {"animation_duration_seconds": 4, "export_transparent_background_png": False}), batch_id="ordered",
    )
    monkeypatch.setattr(execution, "batch_temp_dir", lambda batch: tmp_path / "scratch" / batch)
    monkeypatch.setattr(execution, "scan_field_ranges", lambda *a: {
        "frame_catalog": [{"SequenceIndex": 0, "ranges": {"PILE_U_MAG": {"min": 0, "max": 1}}}],
    })
    monkeypatch.setattr(execution, "numeric_asset_is_valid", lambda *a, **kw: True)
    second_done = threading.Event()

    def render(command, config_path, *args):
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        frames = Path(payload["output_dir"]) / "frames" / "PILE_U_MAG"
        frames.mkdir(parents=True)
        count = 3 if Path(payload["odb_path"]) == paths[0] else 7
        for index in range(count):
            Image.new("RGB", (8, 8), (index, 0, 0)).save(frames / f"{index}.png")
        if Path(payload["odb_path"]) == paths[0]:
            assert second_done.wait(5)
        else:
            second_done.set()

    monkeypatch.setattr(execution, "render_group_contours", render)
    monkeypatch.setattr(execution, "write_group_member_manifest", lambda *a, **kw: None)
    outputs = execution._execute_group(plan, group, 0, lambda *a: None, None,
                                       MultiProcessController(), threading.Lock())
    assert [Path(output).name for output in outputs] == [path.stem for path in paths]
    for output, count in zip(outputs, (3, 7)):
        with Image.open(Path(output) / "animations" / "PILE_U_MAG.gif") as gif:
            assert gif.n_frames == count
            total = 0
            for index in range(count):
                gif.seek(index)
                total += gif.info["duration"]
            assert total == 4000
    records = list(tmp_path.rglob("comparison_group_legends.json"))
    assert records
    for record in records:
        assert json.loads(record.read_text(encoding="utf-8"))["g"]["members"] == [str(path) for path in paths]


def test_same_named_odbs_have_isolated_parallel_prescan_configs(tmp_path, monkeypatch):
    paths = [tmp_path / folder / "case.odb" for folder in ("model-a", "model-b")]
    for path in paths:
        path.parent.mkdir()
        path.write_bytes(b"odb")
    jobs = {path: execution.PostprocessJob(path=path, start_step="Load", end_step="Load") for path in paths}
    group = execution.PostprocessGroup("g", "comparison", tuple(paths))
    plan = execution.PostprocessPlan(
        jobs=jobs, groups=(group,),
        options=execution.PostprocessOptions(
            abaqus_command="abaqus", root=tmp_path, parallel_workers=2, force_rescan=True,
            full_timehistory_freebody=False, rebar_method="element_cut",
            expected_longitudinal_rebar_count=0, settings={},
        ),
    )
    monkeypatch.setattr(execution, "batch_temp_dir", lambda batch: tmp_path / "scratch" / batch)
    barrier = threading.Barrier(2)
    observations = []

    def inspect_prescan(command, config_path, *args):
        # Both configs have been written before either simulated worker reads one.
        barrier.wait(timeout=5)
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        observations.append((config_path, Path(payload["odb_path"])))
        raise ValueError("stop after observing prescan inputs")

    monkeypatch.setattr(execution, "scan_field_ranges", inspect_prescan)
    with pytest.raises(ValueError, match="stop after observing"):
        execution._execute_group(plan, group, 0, lambda *args: None, None, MultiProcessController(), threading.Lock())
    assert len({config for config, _ in observations}) == 2
    assert {source for _, source in observations} == set(paths)
