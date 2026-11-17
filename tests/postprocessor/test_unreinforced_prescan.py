"""Execute the production scanner policy without importing an Abaqus runtime."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def policy():
    path = Path(__file__).resolve().parents[2] / "modules/postprocessor/abaqus_scripts/scan_legend_limits.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in {"longitudinal_data", "active_specs"}]
    namespace = {"SPECS": [("concrete", "S", "concrete"), ("soil", "S", "soil"),
                           ("pile", "U", "pile"), ("bars", "S", "rebar")]}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def test_explicit_unreinforced_never_reads_a_rebar_region(policy):
    assert policy["longitudinal_data"]({"reinforcement_mode": "none"}, object()) == ({}, {})
    assert [s[2] for s in policy["active_specs"]({"reinforcement_mode": "none"})] == ["concrete", "soil", "pile"]


def test_legacy_default_still_requires_reinforcement(policy):
    calls = []
    policy["element_data"] = lambda *args: calls.append(args) or ({"BAR": [1]}, {("BAR", 1): (0, 0, 1)})
    assembly = SimpleNamespace(elementSets={"REBAR": "region"})
    config = {"rebar_set": "REBAR", "settings": {"longitudinal_orientation_threshold": 0.9}}
    assert policy["longitudinal_data"](config, assembly)[0] == {"BAR": [1]}
    assert calls[0] == (assembly, "region", "HRB400", 0.9)
    assert len(policy["active_specs"](config)) == 4
    policy["element_data"] = lambda *args: ({}, {})
    with pytest.raises(RuntimeError, match="No filtered"):
        policy["longitudinal_data"](config, assembly)


def test_invalid_mode_does_not_silently_drop_bars(policy):
    with pytest.raises(RuntimeError, match="Unsupported"):
        policy["longitudinal_data"]({"reinforcement_mode": "absent?"}, object())


def test_worker_loader_still_applies_component_and_empty_set_patches(monkeypatch):
    import sys
    path = Path(__file__).resolve().parents[2] / "modules/postprocessor/abaqus_scripts/scan_legend_worker.py"
    monkeypatch.setattr(sys, "argv", [str(path)])
    captured = []
    # Execute the actual loader, intercepting only its final Abaqus execution.
    namespace = {"exec": lambda code, *args: captured.append(code)}
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)
    assert len(captured) == 1
    assert 'in active_specs(config):' in namespace['source']
    assert 'if not region_name:' in namespace['source']


def test_reinforcement_mode_changes_both_cache_identities():
    from modules.postprocessor.cache import numeric_config_snapshot, prescan_config_snapshot
    for snapshot in (numeric_config_snapshot, prescan_config_snapshot):
        assert snapshot({"reinforcement_mode": "none"}) != snapshot({"reinforcement_mode": "required"})
