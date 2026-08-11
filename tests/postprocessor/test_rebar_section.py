from modules.postprocessor.rebar_section import (
    crosses_horizontal_cut,
    project_axial_force_to_pile_axis,
    sum_crossing_rebar_force,
)


def _element(bar_id, z1, z2, force, *, current=None):
    reference_first = (0.0, 0.0, z1)
    reference_last = (0.0, 0.0, z2)
    current_first, current_last = current or (reference_first, reference_last)
    return {
        "bar_id": bar_id,
        "reference_first": reference_first,
        "reference_last": reference_last,
        "current_first": current_first,
        "current_last": current_last,
        "axial_force": force,
    }


def test_shared_node_uses_one_half_open_segment_per_bar():
    elements = [_element(1, 0.0, 10.0, 100.0), _element(1, 10.0, 20.0, 120.0)]
    force, selected, duplicates = sum_crossing_rebar_force(
        elements, 10.0, tolerance=1e-6, top_z=20.0
    )
    assert force == 120.0
    assert len(selected) == 1
    assert duplicates == 0


def test_top_endpoint_is_included_once():
    assert crosses_horizontal_cut(10.0, 20.0, 20.0, tolerance=1e-6, is_top_of_rebar=True)
    assert not crosses_horizontal_cut(0.0, 10.0, 10.0, tolerance=1e-6)


def test_current_axis_projection_ignores_connectivity_order():
    assert project_axial_force_to_pile_axis(100.0, (0, 0, 0), (3, 0, 4)) == 80.0
    assert project_axial_force_to_pile_axis(100.0, (3, 0, 4), (0, 0, 0)) == 80.0


def test_each_bar_is_counted_once_even_for_duplicate_candidates():
    elements = [
        _element(1, 0.0, 10.0, 100.0),
        _element(1, 0.0, 10.0, 999.0),
        _element(2, 0.0, 10.0, -50.0),
    ]
    force, selected, duplicates = sum_crossing_rebar_force(
        elements, 5.0, tolerance=1e-6, top_z=10.0
    )
    assert force == 50.0
    assert len(selected) == 2
    assert duplicates == 1
