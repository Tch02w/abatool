import ast
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from modules.postprocessor import runner_parallel
from modules.postprocessor.legends import aggregate_group_animation_ranges, member_legend_coverage


@pytest.fixture
def renderer():
    # Execute the actual viewport setters without initializing a licensed CAE session.
    source = Path(__file__).resolve().parents[2] / "modules/postprocessor/abaqus_scripts/render_group_contours_core.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and
                 n.name in ("apply_limits", "set_animation_limits", "set_static_limits", "legend_mode", "check_member_scan")]
    options = SimpleNamespace()
    options.setValues = lambda **kwargs: vars(options).update(kwargs)
    names = "DISCRETE CONTINUOUS SPECIFY SPECTRUM BANDED UNIFORM OFF ON".split()
    scope = dict(os=os, math=math, viewport=SimpleNamespace(odbDisplay=SimpleNamespace(contourOptions=options)),
                 odb_path="model.odb", config={"comparison_group": "组A", "require_fixed_legends": True},
                 applied_legends={"static": {}, "animation": {}}, legend_ranges={}, animation_legend_ranges={},
                 scanned_sequences={},
                 damage_spectrum_name="damage", **{name: name for name in names})
    exec(compile(tree, str(source), "exec"), scope)
    return scope


@pytest.mark.parametrize("invalid", [None, {"min": 0, "max": math.nan}, {"min": 4, "max": 3}, {}])
def test_one_member_cannot_borrow_another_members_missing_scan(renderer, invalid):
    local = {"frame_catalog": [{"SequenceIndex": 0, "ranges": {"U": invalid}}]}
    other = {"frame_catalog": [{"SequenceIndex": 0, "ranges": {"U": {"min": 1, "max": 3}}}]}
    plan = aggregate_group_animation_ranges([{"comparison_group": "组A", "range_scan": scan} for scan in (local, other)])["组A"]
    assert plan["U"]["min"] == 1 and plan["U"]["max"] == 3
    spec, frame = {"name": "U"}, {"SequenceIndex": 0}
    renderer["scanned_sequences"] = member_legend_coverage(local)
    with pytest.raises(ValueError, match="组A.*model.odb.*U.*序号 0"):
        renderer["check_member_scan"](spec, frame, plan, "动画")
    renderer["check_member_scan"](spec, frame, {"U": {"source": "comparison_group_manual_override"}}, "动画")
    renderer["scanned_sequences"] = member_legend_coverage(other)
    renderer["check_member_scan"](spec, frame, plan, "动画")


def test_fixed_bounds_match_viewport_and_static_animation_are_independent(renderer):
    spec = {"variable": "DAMAGET", "name": "PILE_CON_DAMAGET"}
    # A manually entered small positive maximum must not be rounded up to the zero-field default.
    renderer["legend_ranges"][spec["name"]] = {"min": 0, "max": 4e-13}
    renderer["animation_legend_ranges"][spec["name"]] = {"min": 0, "max": .42}
    for kind, setter, maximum in [("static", "set_static_limits", 4e-13), ("animation", "set_animation_limits", .42)]:
        renderer[setter](spec)
        opts = renderer["viewport"].odbDisplay.contourOptions
        assert opts.minAutoCompute == opts.maxAutoCompute == "OFF"
        assert opts.numIntervals == 10 and opts.maxValue == maximum
        assert renderer["applied_legends"][kind][spec["name"]] == {"mode": "fixed", "min": 0, "max": maximum}


@pytest.mark.parametrize("setter", ["set_static_limits", "set_animation_limits"])
@pytest.mark.parametrize("limits", [None, {}, {"min": 2, "max": 1}, {"min": 0, "max": math.inf}])
def test_group_refuses_unusable_scale_before_print(renderer, setter, limits):
    for key in ("legend_ranges", "animation_legend_ranges"):
        if limits is not None:
            renderer[key]["S"] = limits
    with pytest.raises(ValueError, match="组A.*model.odb.*S.*色标"):
        renderer[setter]({"variable": "S", "name": "S"})
    assert renderer["applied_legends"] == {"static": {}, "animation": {}}


def test_standalone_fallback_is_recorded_per_field_and_output(renderer):
    renderer["config"]["require_fixed_legends"] = False
    renderer["set_static_limits"]({"variable": "DAMAGET", "name": "damage"})
    opts = renderer["viewport"].odbDisplay.contourOptions
    assert opts.minAutoCompute == opts.maxAutoCompute == "ON"
    assert renderer["applied_legends"]["static"]["damage"] == {"mode": "auto"}
    renderer["legend_ranges"]["U"] = {"min": 0, "max": 1}
    renderer["set_static_limits"]({"variable": "U", "name": "U"})
    assert renderer["legend_mode"]("static", "fixed") == "mixed_fixed_and_auto"
    assert renderer["legend_mode"]("animation", "fixed") == "not_rendered"


@pytest.mark.parametrize(("receipt", "text"), [
    (None, "回执"),
    ({"request_id": "old", "status": "succeeded"}, "回执"),
    ({"request_id": "current", "status": "failed", "error": "组色标缺失"}, "组色标缺失"),
    ({"request_id": "current", "status": "succeeded"}, None),
])
def test_cae_zero_exit_requires_current_receipt(tmp_path, monkeypatch, receipt, text):
    path = tmp_path / "job_config.json"
    path.write_text(json.dumps(dict(output_dir=str(tmp_path), odb_path="a.odb", render_request_id="current")), encoding="utf-8")
    if receipt:
        (tmp_path / "metadata.json").write_text(json.dumps({"group_render_receipt": receipt}), encoding="utf-8")
    monkeypatch.setattr(runner_parallel, "run_process", lambda *args: None)
    if text:
        with pytest.raises(RuntimeError, match=text):
            runner_parallel.render_group_contours("abaqus", path)
    else:
        runner_parallel.render_group_contours("abaqus", path)
