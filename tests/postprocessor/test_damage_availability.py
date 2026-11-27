"""Exercise the production CAE scanner, numeric policy and frame renderer without a license."""

import ast
import builtins
import csv
import io
import os
import traceback
from pathlib import Path
from types import SimpleNamespace

import pytest

from modules.postprocessor.cache import (
    numeric_config_snapshot,
    prescan_config_snapshot,
    stable_config_hash,
)
from modules.postprocessor.legends import choose_sequences

SCRIPTS = Path(__file__).resolve().parents[2] / "modules/postprocessor/abaqus_scripts"


def functions(file, names, **scope):
    path = SCRIPTS / file
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tree.body = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    exec(compile(tree, str(path), "exec"), scope)  # noqa: S102 - local, named worker functions
    return scope


class Field:
    def __init__(self, *values):
        self.values = [SimpleNamespace(data=v) for v in values]

    def getSubset(self, *, region, position, readOnly):
        assert (region, position, readOnly) == ("concrete", "IP", True)
        return self


def frame(index, fields):
    return SimpleNamespace(
        incrementNumber=index, frameValue=float(index), fieldOutputs=fields
    )


def test_numeric_csv_separates_absence_empty_region_and_measured_zero():
    scope = functions(
        "extract_job.py",
        {"damage_metrics", "concrete_damage_values", "scalar"},
        builtins=builtins,
        INTEGRATION_POINT="IP",
    )
    rows = [
        scope["damage_metrics"](frame(i, fields), "concrete", 0.8)
        for i, fields in enumerate(
            [
                {},
                {"DAMAGET": Field(), "DAMAGEC": Field(0)},
                {"DAMAGET": Field(0), "DAMAGEC": Field()},
                {"DAMAGET": Field(0.1, 0.9), "DAMAGEC": Field(0.4)},
            ]
        )
    ]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    stream.seek(0)
    data = list(csv.DictReader(stream))
    assert [r["MaxDAMAGET"] for r in data] == ["", "", "0.0", "0.9"]
    assert [r["MaxDAMAGEC"] for r in data] == ["", "0.0", "", "0.4"]
    assert [r["ThresholdCandidate"] for r in data] == ["", "", "False", "True"]
    assert [r["DAMAGETStatus"] for r in data] == [
        "field_absent",
        "no_concrete_integration_points",
        "available",
        "available",
    ]


@pytest.mark.parametrize("partial", [True, False])
def test_scanner_selects_fields_on_a_supported_frame_and_reports_coverage(partial):
    frames = [
        frame(i, fields)
        for i, fields in enumerate(
            [
                ({} if partial else {"DAMAGET": Field(0)}),
                {"DAMAGET": Field() if partial else Field(0)},
                {"DAMAGET": Field(0)},
                {"DAMAGET": Field(0.95)},
            ]
        )
    ]
    for f in frames:
        f.fieldOutputs["S"] = Field(15)
    position = {}
    options = SimpleNamespace(setValues=lambda **kw: None)

    def set_frame(step, frame):
        position["frame"] = frame

    def set_primary(view, variable, refinement, location):
        # The original implementation called this before selecting a frame.
        assert frames[position["frame"]].fieldOutputs[variable].values
        position["variable"] = variable

    def refresh():
        values = frames[position["frame"]].fieldOutputs[position["variable"]].values
        options.autoMinValue = options.autoMaxValue = values[0].data

    view = SimpleNamespace(
        setValues=lambda **kw: None,
        forceRefresh=refresh,
        odbDisplay=SimpleNamespace(
            setFrame=set_frame,
            contourOptions=options,
            display=SimpleNamespace(setValues=lambda **kw: None),
        ),
    )
    odb = SimpleNamespace(
        rootAssembly=SimpleNamespace(elementSets={"concrete": "concrete"}),
        steps={"step": SimpleNamespace(frames=frames)},
        close=lambda: None,
    )
    specs = [
        (name, var, "concrete", None, "IP", False)
        for name, var in (
            ("PILE_CON_DAMAGET", "DAMAGET"),
            ("PILE_CON_DAMAGEC", "DAMAGEC"),
            ("PILE_CON_S_MISES", "S"),
        )
    ]
    scope = functions(
        "scan_legend_limits.py",
        {"scan", "unavailable_reason"},
        os=os,
        INTEGRATION_POINT="IP",
        CONTOURS_ON_DEF="contours",
        ON=True,
        session=SimpleNamespace(openOdb=lambda **kw: odb, Viewport=lambda **kw: view),
        active_specs=lambda cfg: specs,
        element_data=lambda *args: ({}, {1: (0, 0, 0)}),
        longitudinal_data=lambda *args: ({}, {}),
        set_group=lambda *args: None,
        primary=set_primary,
        ring_coverage=lambda *args: 1.0,
    )
    scan = scope["scan"](
        {
            "odb_path": "x",
            "pile_concrete_set": "concrete",
            "pile_display_set": "pile",
            "soil_set": "soil",
            "start_step": "step",
            "end_step": "step",
            "settings": {"damage_threshold": 0.8},
        }
    )
    missing = scan["unavailable_fields"]
    assert missing["PILE_CON_DAMAGEC"] == {"field_absent": [0, 1, 2, 3]}
    catalog = scan["frame_catalog"]
    assert all(
        f["ranges"]["PILE_CON_S_MISES"] == {"min": 15, "max": 15} for f in catalog
    )
    assert (
        catalog[2]["FractureCandidate"] is False
        and catalog[2]["DamageAngularCoverage"] == 0
    )
    detect = scan["auto_detection"]
    assert detect["first_observed_candidate_sequence_index"] == 3
    assert detect["evaluated_frames"] == (2 if partial else 4)
    if partial:
        assert missing["PILE_CON_DAMAGET"] == {
            "field_absent": [0],
            "no_concrete_integration_points": [1],
        }
        assert all(
            catalog[i][key] is None
            for i in (0, 1)
            for key in ("MaxDAMAGET", "DamageAngularCoverage", "FractureCandidate")
        )
        assert detect["first_fracture_sequence_index"] is None and choose_sequences(
            scan, "auto"
        ) == [3]
    else:
        assert "PILE_CON_DAMAGET" not in missing
        assert detect["first_fracture_sequence_index"] == 3 and choose_sequences(
            scan, "auto"
        ) == [2, 3]


def test_new_snapshots_cannot_reuse_old_zero_filled_assets_or_unqualified_prescans():
    for build, key in (
        (prescan_config_snapshot, "prescan_pipeline_version"),
        (numeric_config_snapshot, "numeric_pipeline_version"),
    ):
        now = build({})
        old = dict(now)
        if key == "prescan_pipeline_version":
            old.pop(key)
        else:
            old[key] = 2
        assert stable_config_hash(old) != stable_config_hash(now)


@pytest.mark.parametrize("group_renderer", [False, True])
@pytest.mark.parametrize("use_prescan", [False, True])
def test_optional_damage_frames_and_last_static_follow_real_frame_availability(
    tmp_path, group_renderer, use_prescan
):
    # The first frame is present in another region, the second is a real zero,
    # and the selected last frame omits the field entirely.
    frames = [
        frame(0, {"DAMAGET": Field()}),
        frame(1, {"DAMAGET": Field(0)}),
        frame(2, {}),
    ]
    timeline = [
        {
            "SequenceIndex": i,
            "StepIndex": 0,
            "FrameIndex": i,
            "StepName": "step",
            "frame": f,
        }
        for i, f in enumerate(frames)
    ]
    spec = {"name": "PILE_CON_DAMAGET", "variable": "DAMAGET", "set": "concrete"}
    reasons = {
        "PILE_CON_DAMAGET": {"no_concrete_integration_points": [0], "field_absent": [2]}
    }
    config = {"unavailable_fields": reasons} if use_prescan else {}
    owner = SimpleNamespace(elementSets={"concrete": "concrete"})
    no_op = lambda *a, **k: None
    prints = []
    view = SimpleNamespace(
        odbDisplay=SimpleNamespace(
            setValues=no_op,
            setFrame=no_op,
            displayGroup=SimpleNamespace(replace=no_op),
            display=SimpleNamespace(setValues=no_op),
        ),
        view=SimpleNamespace(setViewpoint=no_op, fitView=no_op),
    )
    common = {
        "os": os,
        "builtins": builtins,
        "traceback": traceback,
        "INTEGRATION_POINT": "IP",
        "PNG": "png",
        "CONTOURS_ON_UNDEF": "UNDEF",
        "CONTOURS_ON_DEF": "DEF",
        "OFF": False,
        "ON": True,
        "odb": SimpleNamespace(
            rootAssembly=owner, steps={"step": SimpleNamespace(frames=frames)}
        ),
        "viewport": view,
        "dgo": SimpleNamespace(LeafFromElementSets=no_op),
        "concrete_region": "concrete",
        "session": SimpleNamespace(
            printToFile=lambda *, fileName, **kw: prints.append(Path(fileName).name)
        ),
        "primary_variable": no_op,
        "log": no_op,
        "set_animation_limits": no_op,
        "set_static_limits": no_op,
        "timeline": timeline,
        "full_timeline": timeline,
        "selected_timeline": timeline,
        "frame_root": str(tmp_path),
        "contour_dir": str(tmp_path),
        "config": config,
        "unavailable_fields": reasons if use_prescan else {},
        "settings": {"camera_view_vector": (0, 1, 0), "camera_up_vector": (0, 0, 1)},
    }
    if group_renderer:
        scope = functions(
            "render_group_contours_core.py",
            {"field_available", "render"},
            **common,
            check_member_scan=no_op,
            unavailable_sequences={"PILE_CON_DAMAGET": {0, 2}} if use_prescan else {},
            animation_legend_ranges={},
            legend_ranges={},
        )
    else:
        scope = functions(
            "extract_job.py",
            {"render", "concrete_damage_values"},
            **common,
            safe_name=str,
        )
    scope["render"](spec)
    assert prints == ["0001_step_F0001"]
    assert scope["unavailable_fields"] == reasons

    def printer_failure(**kwargs):
        raise OSError("CAE image write failed")

    scope["session"].printToFile = printer_failure
    with pytest.raises(IOError, match="image write failed"):
        scope["render"](spec)


def test_new_group_request_cannot_skip_unexpected_field_loss_even_with_manual_limit():
    scope = functions(
        "render_group_contours_core.py",
        {"field_available"},
        unavailable_sequences={},
        unavailable_fields={},
        config={
            "unavailable_fields": {},
            "legend_ranges": {"PILE_CON_DAMAGET": {"min": 0, "max": 1}},
        },
    )
    with pytest.raises(RuntimeError, match="availability changed"):
        scope["field_available"](
            {"name": "PILE_CON_DAMAGET", "variable": "DAMAGET"},
            {"SequenceIndex": 0},
            frame(0, {}),
        )
