from modules.postprocessor.postprocess_execution import suggested_job_from_scan


def suggestions(elements, nodes=None, defaults=None):
    return suggested_job_from_scan(
        {
            "path": "sample.odb",
            "steps": ["Load"],
            "assembly_node_sets": nodes or [],
            "assembly_element_sets": elements,
        },
        defaults or {},
    )["suggested"]


def test_missing_roles_are_not_assigned_arbitrary_first_set():
    result = suggestions(["ALL-ELEMENTS"], ["ALL-NODES"])
    for role in ("loadSet", "pileDisplaySet", "pileConcreteSet", "pileSteelSet", "soilSet", "rebarSet"):
        assert result[role] == "", role


def test_root_key_and_retained_soil_fallbacks_are_restored():
    result = suggestions(["UNRELATED", "SET-KEY", "SET-SOIL-FULL"])
    assert result["pileSteelSet"] == "SET-KEY"
    assert result["soilSet"] == "SET-SOIL-FULL"


def test_configured_roles_take_precedence_over_fallbacks():
    result = suggestions(
        ["SET-KEY", "SET-SOIL-FULL", "SteelTube", "RetainedSoil"],
        defaults={"default_cf_steel_set": "SteelTube", "default_soil_set": "RetainedSoil"},
    )
    assert result["pileSteelSet"] == "SteelTube"
    assert result["soilSet"] == "RetainedSoil"


def test_ambiguous_normalized_names_require_explicit_selection():
    result = suggestions(["SET-PILE", "SET_PILE"])
    assert result["pileDisplaySet"] == ""


def test_unique_normalized_names_remain_supported():
    result = suggestions(["set_pile", "set_pile_con", "set_rebar"], ["set_load"])
    assert result["pileDisplaySet"] == "set_pile"
    assert result["pileConcreteSet"] == "set_pile_con"
    assert result["rebarSet"] == "set_rebar"
    assert result["loadSet"] == "set_load"
