import csv
import json

import pytest
from openpyxl import load_workbook

from modules.postprocessor.postprocess import (
    build_pile_force_moment,
    interpolate_components,
)
from modules.postprocessor.postprocess_core import build_xlsx, plot_pile_axial


def test_moment_interpolation_is_linear_between_rebar_centroids():
    points = [(0.0, 10.0, 100.0, -50.0), (100.0, 30.0, 300.0, 50.0)]
    force, mx, my, rule = interpolate_components(points, 25.0, -10.0, 110.0)
    assert (force, mx, my) == (15.0, 150.0, -25.0)
    assert rule == "linear_between_element_centroids"


def test_moment_is_zero_outside_physical_rebar_extent():
    values = interpolate_components([(0.0, 10.0, 100.0, -50.0)], -20.0, -10.0, 110.0)
    assert values == (0.0, 0.0, 0.0, "outside_rebar_extent_zero")


def _write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.parametrize(
    ("method", "expected_rebar", "expected_total"),
    [
        ("element_cut", -90.0, 10.0),
        ("legacy_interpolation", -10.0, 90.0),
    ],
)
def test_selected_rebar_method_controls_pile_total_without_losing_comparison(
    tmp_path,
    method,
    expected_rebar,
    expected_total,
):
    output_dir = tmp_path / "result"
    axial_path = output_dir / "freebody" / "pile_total_axial_force_time_aligned.csv"
    _write_csv(
        axial_path,
        [
            {
                "SequenceIndex": 0,
                "StepIndex": 0,
                "StepName": "Load",
                "FrameIndex": 1,
                "IncrementNumber": 1,
                "StepTime": 1.0,
                "TotalTime": 1.0,
                "Status": "LAST",
                "Elevation_mm": 5.0,
                "DepthFromGround_mm": 5.0,
                "Fz_N": 100.0,
                "Mx_Nmm": 0.0,
                "My_Nmm": 0.0,
                "RebarMethod": method,
                "RebarAxial_Section_TensionPositive_N": -90.0,
                "RebarAxial_Section_CompressionPositive_N": 90.0,
                "RebarAxial_Interpolated_TensionPositive_N": -10.0,
                "RebarAxial_Interpolated_CompressionPositive_N": 10.0,
                "PileTotalAxial_TensionPositive_N": 0.0,
                "PileTotalAxial_CompressionPositive_N": 0.0,
            }
        ],
    )
    _write_csv(
        output_dir / "rebar" / "rebar_element_stress_force_timehistory.csv",
        [
            {
                "SequenceIndex": 0,
                "CentroidZ_mm": 0.0,
                "CentroidX_mm": 0.0,
                "CentroidY_mm": 0.0,
                "ElementAxialForce_TensionPositive_N": -10.0,
            },
            {
                "SequenceIndex": 0,
                "CentroidZ_mm": 10.0,
                "CentroidX_mm": 0.0,
                "CentroidY_mm": 0.0,
                "ElementAxialForce_TensionPositive_N": -10.0,
            },
        ],
    )
    metadata_path = output_dir / "rebar" / "rebar_metadata.json"
    metadata_path.write_text(
        json.dumps({"rebar_z_extent_mm": [0.0, 10.0]}),
        encoding="utf-8",
    )

    build_pile_force_moment(output_dir)

    with axial_path.open("r", encoding="utf-8-sig", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert float(row["PileTotalAxial_TensionPositive_N"]) == expected_total
    assert (
        float(row["PileTotalAxial_TensionPositive_N"]) - float(row["Fz_N"])
        == expected_rebar
    )
    assert float(row["RebarAxial_Section_TensionPositive_N"]) == -90.0
    assert float(row["RebarAxial_Interpolated_TensionPositive_N"]) == -10.0


@pytest.mark.parametrize(
    ("method", "active_label", "comparison_label"),
    [
        (
            "element_cut",
            "Rebar element-cut (active)",
            "Rebar legacy interpolation (comparison)",
        ),
        (
            "legacy_interpolation",
            "Rebar legacy interpolation (active)",
            "Rebar element-cut (comparison)",
        ),
    ],
)
def test_axial_plot_labels_the_selected_rebar_method(
    tmp_path,
    monkeypatch,
    method,
    active_label,
    comparison_label,
):
    source = tmp_path / "freebody" / "pile_total_axial_force_time_aligned.csv"
    _write_csv(
        source,
        [
            {
                "DepthFromGround_mm": 1000.0,
                "ConcreteAxial_CompressionPositive_N": 100.0,
                "RebarMethod": method,
                "RebarAxial_Section_CompressionPositive_N": 90.0,
                "RebarAxial_Interpolated_CompressionPositive_N": 10.0,
                "PileTotalAxial_CompressionPositive_N": 20.0,
            }
        ],
    )

    labels = []

    class FakeAxes:
        def plot(self, *_args, **kwargs):
            labels.append(kwargs.get("label"))

        def axhline(self, *_args, **_kwargs):
            pass

        def invert_yaxis(self):
            pass

        def grid(self, *_args, **_kwargs):
            pass

        def set_xlabel(self, *_args):
            pass

        def set_ylabel(self, *_args):
            pass

        def set_title(self, *_args):
            pass

        def legend(self):
            pass

    class FakeFigure:
        def clear(self):
            pass

        def savefig(self, target, **_kwargs):
            target.touch()

    monkeypatch.setattr(
        "modules.postprocessor.postprocess_core._file_plot",
        lambda *_args: (FakeFigure(), FakeAxes()),
    )

    assert plot_pile_axial(tmp_path).exists()
    assert active_label in labels
    assert comparison_label in labels


def test_axial_plot_never_connects_status_sequence_groups_and_prefers_last(
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "freebody" / "pile_total_axial_force_time_aligned.csv"

    def row(status, sequence, depth, method, force):
        return {
            "Status": status,
            "SequenceIndex": sequence,
            "DepthFromGround_mm": depth,
            "ConcreteAxial_CompressionPositive_N": force,
            "RebarMethod": method,
            "RebarAxial_Section_CompressionPositive_N": force + 10.0,
            "RebarAxial_Interpolated_CompressionPositive_N": force + 20.0,
            "PileTotalAxial_CompressionPositive_N": force + 30.0,
        }

    _write_csv(
        source,
        [
            row("PRE_FRACTURE", 99, 2000.0, "legacy_interpolation", 990.0),
            row("LAST", 3, 1000.0, "element_cut", 30.0),
            row("PRE_FRACTURE", 99, 0.0, "legacy_interpolation", 900.0),
            row("LAST", 3, 0.0, "element_cut", 3.0),
        ],
    )

    figures = []

    class FakeAxes:
        def __init__(self):
            self.plots = []
            self.title = ""

        def plot(self, x_values, y_values, **kwargs):
            self.plots.append(
                (kwargs.get("label"), list(x_values), list(y_values))
            )

        def axhline(self, *_args, **_kwargs):
            pass

        def invert_yaxis(self):
            pass

        def grid(self, *_args, **_kwargs):
            pass

        def set_xlabel(self, *_args):
            pass

        def set_ylabel(self, *_args):
            pass

        def set_title(self, title):
            self.title = title

        def legend(self):
            pass

    class FakeFigure:
        def clear(self):
            pass

        def __init__(self, axes):
            self.axes = axes
            self.target = None

        def savefig(self, target, **_kwargs):
            self.target = target
            target.touch()

    def fake_subplots(*_args):
        axes = FakeAxes()
        figure = FakeFigure(axes)
        figures.append(figure)
        return figure, axes

    monkeypatch.setattr(
        "modules.postprocessor.postprocess_core._file_plot",
        fake_subplots,
    )

    canonical = plot_pile_axial(tmp_path)

    assert canonical is not None
    assert canonical.name == "pile_total_axial_force_depth.png"
    assert {figure.target.name for figure in figures} == {
        "pile_total_axial_force_depth.png",
        "pile_total_axial_force_depth_PRE_FRACTURE_SEQ0099.png",
    }
    canonical_figure = next(figure for figure in figures if figure.target == canonical)
    comparison_figure = next(figure for figure in figures if figure.target != canonical)
    assert "Status LAST · Sequence 3" in canonical_figure.axes.title
    assert "active rebar: element-cut" in canonical_figure.axes.title
    assert "Status PRE_FRACTURE · Sequence 99" in comparison_figure.axes.title
    assert "active rebar: legacy interpolation" in comparison_figure.axes.title
    assert all(
        y_values == [0.0, 1.0]
        for _label, _x_values, y_values in canonical_figure.axes.plots
    )
    assert all(
        y_values == [0.0, 2.0]
        for _label, _x_values, y_values in comparison_figure.axes.plots
    )


@pytest.mark.parametrize(
    ("method", "expected_active_text"),
    [
        ("element_cut", "element-cut T3D2 section force (active)"),
        (
            "legacy_interpolation",
            "centroid-interpolated T3D2 force (active legacy comparison mode)",
        ),
    ],
)
def test_summary_axial_method_follows_preferred_profile_rebar_method(
    tmp_path,
    method,
    expected_active_text,
):
    other_method = (
        "legacy_interpolation" if method == "element_cut" else "element_cut"
    )
    _write_csv(
        tmp_path / "freebody" / "pile_total_axial_force_time_aligned.csv",
        [
            {
                "Status": "PRE_FRACTURE",
                "SequenceIndex": 99,
                "RebarMethod": other_method,
            },
            {
                "Status": "LAST",
                "SequenceIndex": 3,
                "RebarMethod": method,
            },
        ],
    )

    workbook_path = build_xlsx(tmp_path)
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        values = {
            item: value
            for item, value, *_rest in workbook["Summary"].iter_rows(
                min_row=4,
                values_only=True,
            )
            if item
        }
    finally:
        workbook.close()

    explanation = values["Pile axial"]
    assert f"RebarMethod={method}" in explanation
    assert expected_active_text in explanation
    assert "intersected" not in explanation.casefold()
