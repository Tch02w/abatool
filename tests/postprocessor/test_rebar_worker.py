from __future__ import annotations

import ast
import builtins
import math
from pathlib import Path
from types import SimpleNamespace

WORKER = (
    Path(__file__).parents[2]
    / "modules"
    / "postprocessor"
    / "abaqus_scripts"
    / "extract_job.py"
)
COMPATIBILITY_WORKER = WORKER.with_name("extract_job_compatibility.py")


def _worker_functions(*names: str, namespace: dict | None = None) -> dict:
    source = WORKER.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(WORKER))
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert [node.name for node in selected] == [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in set(names)
    ]
    assert {node.name for node in selected} == set(names)
    output = dict(namespace or {})
    exec(  # noqa: S102 - execute only selected AST functions from our worker.
        compile(
            ast.Module(body=selected, type_ignores=[]),
            filename=str(WORKER),
            mode="exec",
        ),
        output,
        output,
    )
    return output


def test_worker_resolves_each_current_node_with_explicit_fallback_priority() -> None:
    merge = _worker_functions("merge_rebar_node_coordinates")[
        "merge_rebar_node_coordinates"
    ]
    reference = {
        ("I", 1): (0.0, 0.0, 0.0),
        ("I", 2): (0.0, 0.0, 10.0),
        ("I", 3): (0.0, 0.0, 20.0),
    }
    coordinates = {("I", 1): (3.0, 4.0, 5.0)}
    displacements = {
        # COORD must win over U when both exist.
        ("I", 1): (100.0, 100.0, 100.0),
        ("I", 2): (1.0, 2.0, 3.0),
    }

    resolved, source, counts = merge(reference, coordinates, displacements)

    assert resolved == {
        ("I", 1): (3.0, 4.0, 5.0),
        ("I", 2): (1.0, 2.0, 13.0),
        ("I", 3): (0.0, 0.0, 20.0),
    }
    assert source == "mixed:COORD+reference_plus_U+reference_geometry"
    assert counts == {
        "COORD": 1,
        "reference_plus_U": 1,
        "reference_geometry": 1,
    }


def test_worker_maps_real_odb_truss_area_and_material_per_element() -> None:
    section_d20 = SimpleNamespace(area=314.159, material="HRB400")
    section_d25 = SimpleNamespace(area=490.874, material="HRB400")
    assignment_d20 = SimpleNamespace(
        sectionName="LONG_D20",
        region=SimpleNamespace(
            elements=[SimpleNamespace(label=11), SimpleNamespace(label=12)]
        ),
    )
    assignment_d25 = SimpleNamespace(
        sectionName="LONG_D25",
        region=SimpleNamespace(elements=[SimpleNamespace(label=21)]),
    )
    assembly = SimpleNamespace(
        instances={
            "REBAR-1": SimpleNamespace(
                sectionAssignments=[assignment_d20, assignment_d25]
            )
        }
    )
    odb = SimpleNamespace(
        sections={"LONG_D20": section_d20, "LONG_D25": section_d25}
    )
    messages: list[str] = []
    functions = _worker_functions(
        "flatten",
        "collect_element_section_data",
        namespace={"assembly": assembly, "odb": odb, "log": messages.append},
    )

    mapped = functions["collect_element_section_data"]()

    assert mapped == {
        ("REBAR-1", 11): {
            "section_name": "LONG_D20",
            "material": "HRB400",
            "area": 314.159,
        },
        ("REBAR-1", 12): {
            "section_name": "LONG_D20",
            "material": "HRB400",
            "area": 314.159,
        },
        ("REBAR-1", 21): {
            "section_name": "LONG_D25",
            "material": "HRB400",
            "area": 490.874,
        },
    }
    assert messages == []


def test_worker_reports_crossing_element_with_missing_s11_instead_of_zero_fill() -> None:
    first_key = ("REBAR-1", 11)
    second_key = ("REBAR-1", 21)
    element_geometry = {
        first_key: {
            "bar_id": 1,
            "reference_first": (0.0, 0.0, 0.0),
            "reference_last": (0.0, 0.0, 10.0),
            "nodes": (("REBAR-1", 1), ("REBAR-1", 2)),
        },
        second_key: {
            "bar_id": 2,
            "reference_first": (5.0, 0.0, 0.0),
            "reference_last": (5.0, 0.0, 10.0),
            "nodes": (("REBAR-1", 3), ("REBAR-1", 4)),
        },
    }
    current_nodes = {
        ("REBAR-1", 1): (0.0, 0.0, 0.0),
        ("REBAR-1", 2): (0.0, 0.0, 10.0),
        ("REBAR-1", 3): (5.0, 0.0, 0.0),
        ("REBAR-1", 4): (5.0, 0.0, 10.0),
    }
    source_counts = {
        "COORD": 4,
        "reference_plus_U": 0,
        "reference_geometry": 0,
    }
    section_frames = {
        0: {
            # The second physical crossing has no stress value.
            "tension_force": {first_key: 100.0},
            "current_nodes": current_nodes,
            "coordinate_source": "COORD",
            "coordinate_source_counts": source_counts,
        }
    }
    functions = _worker_functions(
        "owns_cut",
        "project_to_pile_axis",
        "rebar_section_force",
        namespace={
            "builtins": builtins,
            "math": math,
            "element_geometry": element_geometry,
            "rebar_section_by_sequence": section_frames,
            "rebar_cut_tolerance_mm": 1.0e-6,
            "rebar_z_max": 10.0,
        },
    )

    result = functions["rebar_section_force"](0, 5.0)

    assert result == (
        100.0,
        2,
        0,
        "COORD",
        source_counts,
        1,
        ["REBAR-1:21"],
    )


def test_worker_output_contract_blocks_pseudo_complete_missing_stress_result() -> None:
    source = WORKER.read_text(encoding="utf-8")
    compatibility = COMPATIBILITY_WORKER.read_text(encoding="utf-8")

    assert "dict((key, 0.0) for key in element_geometry)" not in source
    assert 'if key not in frame_data["tension_force"]:' in source
    assert '"MissingS11CrossingCount"' in source
    assert '"RebarSectionForceValid"' in source
    assert 'os.remove(pile_total_force_path)' in source
    assert source.index("write_csv(\n    section_diagnostics_path") < source.index(
        "if rebar_force_failures:"
    )
    assert source.index("if rebar_force_failures:") < source.index(
        "write_csv(\n    pile_total_force_path"
    )
    assert "missing_s11_count == 0 and duplicate_count == 0" in source
    assert "ambiguous duplicate T3D2 crossing" in source

    for field in (
        "RebarSectionRule",
        "RebarInterpolationRule",
        "RebarActiveRule",
        "RebarDirectionCOORDNodeCount",
        "RebarDirectionReferencePlusUNodeCount",
        "RebarDirectionReferenceNodeCount",
    ):
        assert f'"{field}"' in source

    assert "configured_uniform_diameter_fallback" in source
    assert "assignment.region.elements" in source
    assert "odb.sections[section_name]" in source
    assert '"legacy_method": REBAR_INTERPOLATION_METHOD' in source
    assert '"element_cut_rule": REBAR_SECTION_RULE' in source
    assert "collect_element_section_data()" in compatibility
    assert 'source.replace(\n    \'rebar_set_name = config["rebar_set"]' not in compatibility


def test_zero_configured_expected_count_uses_detected_bars_and_depth_scope() -> None:
    source = WORKER.read_text(encoding="utf-8")

    assert "else detected_rebar_count" in source
    assert 'else "odb_detected_bar_count"' in source
    assert "if inside_rebar_extent\n                else \"\"" in source
    assert '"CrossingCountValidationApplicable": inside_rebar_extent' in source
