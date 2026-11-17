import json

import pytest

from modules.postprocessor.postprocess import build_pile_force_moment
from modules.postprocessor.postprocess_core import read_csv, write_csv


@pytest.mark.parametrize("composition", ["concrete", "concrete_and_casing"])
def test_unreinforced_preserves_freebody_total_without_adding_stale_rebar(tmp_path, composition):
    (tmp_path / "freebody").mkdir()
    (tmp_path / "rebar").mkdir()
    (tmp_path / "rebar/rebar_metadata.json").write_text(json.dumps({
        "reinforcement_mode": "none", "freebody_composition": composition,
    }))
    path = tmp_path / "freebody/pile_total_axial_force_time_aligned.csv"
    write_csv(path, [{
        "SequenceIndex": 0, "Elevation_mm": 5, "DepthFromGround_mm": 3,
        "Fz_N": -125, "Mx_Nmm": 30, "My_Nmm": 40,
        "RebarMethod": "element_cut", "RebarAxial_Section_TensionPositive_N": 999,
    }])
    target, maxima = build_pile_force_moment(tmp_path)
    row = read_csv(target)[0]
    assert float(row["PileTotalAxial_TensionPositive_N"]) == -125
    assert float(row["PileTotalAxial_CompressionPositive_N"]) == 125
    assert float(row["PileTotalBendingMoment_Resultant_Nmm"]) == 50
    assert float(row["RebarAxial_Section_TensionPositive_N"]) == 0
    assert row["BendingMomentInterpolationRule"] == "not_applicable_unreinforced"
    assert row["FreeBodyComposition"] == composition
    assert maxima.exists()


def test_missing_rebar_is_not_implicitly_unreinforced(tmp_path):
    (tmp_path / "freebody").mkdir()
    (tmp_path / "rebar").mkdir()
    (tmp_path / "rebar/rebar_metadata.json").write_text('{}')
    (tmp_path / "freebody/pile_total_axial_force_time_aligned.csv").write_text('SequenceIndex\n0\n')
    assert build_pile_force_moment(tmp_path) == (None, None)


def test_unreinforced_workbook_summary_uses_explicit_method(tmp_path):
    from modules.postprocessor.postprocess_core import (
        _selected_axial_rebar_method, _pile_axial_method_summary,
    )
    (tmp_path / "rebar").mkdir()
    (tmp_path / "rebar/rebar_metadata.json").write_text(json.dumps({
        "method": "not_applicable_unreinforced",
    }))
    method = _selected_axial_rebar_method(tmp_path)
    assert method == "not_applicable_unreinforced"
    assert "no T3D2 reinforcement contribution is added" in _pile_axial_method_summary(method)
    (tmp_path / "freebody").mkdir()
    write_csv(tmp_path / "freebody/pile_total_axial_force_time_aligned.csv", [{
        "SequenceIndex": 0, "Status": "LAST", "RebarMethod": method,
    }])
    assert _selected_axial_rebar_method(tmp_path) == method
