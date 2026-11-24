import pytest

from modules.postprocessor.legends import (
    aggregate_animation_ranges,
    aggregate_group_animation_ranges,
    aggregate_group_ranges,
    choose_sequences,
    parse_sequence_expression,
)


def test_animation_ranges_use_every_frame_of_one_odb() -> None:
    ranges = aggregate_animation_ranges(
        {
            "frame_catalog": [
                {
                    "SequenceIndex": 0,
                    "ranges": {"PILE_U_MAG": {"min": 0.0, "max": 2.0}},
                },
                {
                    "SequenceIndex": 1,
                    "ranges": {"PILE_U_MAG": {"min": -1.0, "max": 5.0}},
                },
            ]
        }
    )
    assert ranges["PILE_U_MAG"]["min"] == -1.0
    assert ranges["PILE_U_MAG"]["max"] == 5.0
    assert ranges["PILE_U_MAG"]["source"] == "odb_full_animation_timeline"


def catalog(indices, ranges=None, prefracture=None):
    return {
        "frame_catalog": [
            {"SequenceIndex": value, "ranges": (ranges or {}).get(value, {})}
            for value in indices
        ],
        "auto_detection": {"prefracture_sequence_index": prefracture},
    }


def test_manual_sequence_expression_supports_ranges():
    assert parse_sequence_expression("0, 2, 4-6", range(8)) == [0, 2, 4, 5, 6]


def test_manual_sequence_expression_rejects_missing_frame():
    with pytest.raises(ValueError):
        parse_sequence_expression("0,9", range(4))


def test_manual_range_reports_first_gap_in_sparse_catalog():
    with pytest.raises(ValueError, match=r"时程序号不存在：3$"):
        parse_sequence_expression("10000-1", [1, 2, 10000])
    assert parse_sequence_expression("5-3,4，3", range(6)) == [3, 4, 5]


def test_auto_selects_prefracture_and_last():
    assert choose_sequences(catalog([0, 1, 2, 3], prefracture=2), "auto") == [2, 3]


def test_auto_rejects_detection_not_present_in_catalog():
    with pytest.raises(ValueError, match="断裂前帧.*不存在"):
        choose_sequences(catalog([0, 1, 3], prefracture=2), "auto")


def test_explicit_prefracture_overrides_stale_detection():
    assert choose_sequences(catalog([0, 1, 3], prefracture=99), "auto", prefracture_override=1) == [1, 3]


@pytest.mark.parametrize("mode", ["auto", "all", "manual"])
def test_explicit_prefracture_must_exist(mode):
    with pytest.raises(ValueError, match="断裂前帧.*不存在"):
        choose_sequences(catalog([0, 1, 3]), mode, "0", prefracture_override=2)


def test_group_range_uses_only_selected_frames_and_isolated_groups():
    jobs = [
        {"comparison_group": "A", "selected_sequence_indices": [0],
         "range_scan": catalog([0, 1], {0: {"PILE_U_MAG": {"min": 1, "max": 3}},
                                        1: {"PILE_U_MAG": {"min": -99, "max": 99}}})},
        {"comparison_group": "A", "selected_sequence_indices": [2],
         "range_scan": catalog([2], {2: {"PILE_U_MAG": {"min": -2, "max": 8}}})},
        {"comparison_group": "B", "selected_sequence_indices": [0],
         "range_scan": catalog([0], {0: {"PILE_U_MAG": {"min": 10, "max": 20}}})},
    ]
    plans = aggregate_group_ranges(jobs)
    assert plans["A"]["PILE_U_MAG"]["min"] == -2
    assert plans["A"]["PILE_U_MAG"]["max"] == 8
    assert plans["B"]["PILE_U_MAG"]["min"] == 10


def test_group_animation_range_uses_all_frames_of_all_members():
    jobs = [
        {"comparison_group": "A", "selected_sequence_indices": [1],
         "range_scan": catalog([0, 1], {
             0: {"PILE_U_MAG": {"min": -5, "max": 2}},
             1: {"PILE_U_MAG": {"min": 0, "max": 8}},
         })},
        {"comparison_group": "A", "selected_sequence_indices": [0],
         "range_scan": catalog([0], {
             0: {"PILE_U_MAG": {"min": -2, "max": 12}},
         })},
        {"comparison_group": "B", "selected_sequence_indices": [0],
         "range_scan": catalog([0], {
             0: {"PILE_U_MAG": {"min": 100, "max": 200}},
         })},
    ]
    plans = aggregate_group_animation_ranges(jobs)
    assert plans["A"]["PILE_U_MAG"]["min"] == -5
    assert plans["A"]["PILE_U_MAG"]["max"] == 12
    assert plans["A"]["PILE_U_MAG"]["source"] == (
        "comparison_group_full_animation_timeline"
    )
    assert plans["B"]["PILE_U_MAG"]["min"] == 100


def test_damage_palette_uses_group_maximum_and_zero_minimum():
    jobs = [
        {"comparison_group": "A", "selected_sequence_indices": [0],
         "range_scan": catalog([0], {0: {
             "PILE_CON_DAMAGET": {"min": 0.12, "max": 0.70},
             "PILE_CON_DAMAGEC": {"min": 0.001, "max": 0.018},
         }})},
        {"comparison_group": "A", "selected_sequence_indices": [1],
         "range_scan": catalog([1], {1: {
             "PILE_CON_DAMAGET": {"min": 0.08, "max": 0.81},
             "PILE_CON_DAMAGEC": {"min": 0.002, "max": 0.024},
         }})},
        {"comparison_group": "B", "selected_sequence_indices": [0],
         "range_scan": catalog([0], {0: {
             "PILE_CON_DAMAGET": {"min": 0.02, "max": 0.20},
         }})},
    ]
    plans = aggregate_group_ranges(jobs)
    assert plans["A"]["PILE_CON_DAMAGET"]["min"] == 0.0
    assert plans["A"]["PILE_CON_DAMAGET"]["max"] == 0.81
    assert plans["A"]["PILE_CON_DAMAGEC"]["max"] == 0.024
    assert plans["B"]["PILE_CON_DAMAGET"]["max"] == 0.20
    assert plans["A"]["PILE_CON_DAMAGET"]["source"] == "comparison_group_damage_max_selected_frames"
