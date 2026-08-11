import pandas as pd
import pytest

from modules.postprocessor.axial_smoothing import (
    depth_plot_values,
    engineering_plot_values,
    paired_depth_columns,
    smooth,
)


def test_median_smoothing_rejects_single_spike() -> None:
    values = pd.Series([0.0, 0.0, 100.0, 0.0, 0.0])
    assert smooth(values, "median", 3).tolist() == [0.0] * 5


def test_mean_smoothing_uses_centred_window() -> None:
    values = pd.Series([0.0, 0.0, 90.0, 0.0, 0.0])
    assert smooth(values, "mean", 3).tolist() == [0.0, 30.0, 30.0, 30.0, 0.0]


def test_smoothing_requires_odd_window() -> None:
    with pytest.raises(ValueError, match="odd"):
        smooth(pd.Series([1.0, 2.0]), "median", 2)


def test_smoothing_preserves_each_column_independently() -> None:
    first = pd.Series([0.0, 100.0, 0.0])
    second = pd.Series([100.0, 0.0, 100.0])
    assert smooth(first, "median", 3).tolist() == [50.0, 0.0, 50.0]
    assert smooth(second, "median", 3).tolist() == [50.0, 100.0, 50.0]


def test_paired_depth_columns_match_numbered_column_suffixes() -> None:
    columns = ["基础埋深", "桩体轴力", "基础埋深.1", "桩体轴力.1", "桩体轴力.2"]
    pairs = paired_depth_columns(columns, ["桩体轴力", "桩体轴力.1", "桩体轴力.2"], "基础埋深")
    assert pairs == {"桩体轴力": "基础埋深", "桩体轴力.1": "基础埋深.1", "桩体轴力.2": "基础埋深"}


def test_engineering_table_units_are_not_scaled_again() -> None:
    force, force_label = engineering_plot_values(pd.Series([2500.0]), "桩体弯矩.12")
    depth, depth_label = depth_plot_values(pd.Series([17.5]), "基础埋深.12")
    assert force.tolist() == [2500.0]
    assert force_label == "Bending moment (kN·m)"
    assert depth.tolist() == [17.5]
    assert depth_label == "Depth (m)"


def test_raw_odb_units_are_converted_from_n_and_mm() -> None:
    force, force_label = engineering_plot_values(
        pd.Series([2500.0]), "PileTotalAxial_CompressionPositive_N"
    )
    depth, depth_label = depth_plot_values(pd.Series([17500.0]), "DepthFromGround_mm")
    assert force.tolist() == [2.5]
    assert force_label == "Axial force (kN)"
    assert depth.tolist() == [17.5]
    assert depth_label == "Depth (m)"
