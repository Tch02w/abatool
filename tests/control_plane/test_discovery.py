from __future__ import annotations

from pathlib import Path

import pytest

from modules.control_plane.contracts import ApiProblem, OdbDiscoveryRequest
from modules.control_plane.discovery import discover_odb_files, natural_sort_key


def test_natural_sort_orders_numeric_path_segments() -> None:
    values = ["case-10/model.odb", "case-2/model.odb", "case-1/model.odb"]

    assert sorted(values, key=natural_sort_key) == [
        "case-1/model.odb",
        "case-2/model.odb",
        "case-10/model.odb",
    ]


def test_recursive_discovery_preserves_chinese_paths_and_excludes_generated_trees(
    tmp_path: Path,
) -> None:
    root = tmp_path / "中文 ODB 工程"
    root.mkdir()
    expected = [
        root / "case-2.ODB",
        root / "case-10.odb",
        root / "子目录 3" / "模型-1.odb",
    ]
    excluded = [
        root / ".git" / "hidden.odb",
        root / ".venv" / "hidden.odb",
        root / "AbaqusODBPostProcessor_Results" / "generated.odb",
        root / "_AbaqusODBPostProcessor_Results" / "generated.odb",
        root / "子目录 3" / "模型-old.odb",
        root / "子目录 3" / "模型-old-2.odb",
        root / "子目录 3" / "模型-upgrading-2025.odb",
    ]
    for index, path in enumerate(expected + excluded, 1):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"odb" * index)

    resolved_root, items, warnings = discover_odb_files(
        OdbDiscoveryRequest(root=str(root), recursive=True)
    )

    assert resolved_root == root.resolve()
    assert warnings == ()
    assert [item.name for item in items] == [
        "case-2.ODB",
        "case-10.odb",
        "模型-1.odb",
    ]
    assert [Path(item.path) for item in items] == [path.resolve() for path in expected]
    assert all(item.size_bytes > 0 for item in items)
    assert all(item.modified_at.endswith("Z") for item in items)
    assert all("中文 ODB 工程" in item.path for item in items)


def test_discovery_matches_the_pyside_selection_order(tmp_path: Path) -> None:
    from modules.postprocessor.app import discover_odb_paths as discover_pyside_odbs

    root = tmp_path / "parity"
    for relative in (
        "case-10.odb",
        "case-2.odb",
        "nested-2/model-11.odb",
        "nested-2/model-3.odb",
        "nested-10/model-1.odb",
        "AbaqusODBPostProcessor_Results/ignored.odb",
        "nested-2/model-old.odb",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"odb")

    _, items, warnings = discover_odb_files(
        OdbDiscoveryRequest(root=str(root), recursive=True)
    )

    assert warnings == ()
    assert [Path(item.path) for item in items] == discover_pyside_odbs(root)


def test_non_recursive_discovery_only_returns_root_files(tmp_path: Path) -> None:
    root_file = tmp_path / "root.odb"
    nested_file = tmp_path / "nested" / "nested.odb"
    root_file.write_bytes(b"root")
    nested_file.parent.mkdir()
    nested_file.write_bytes(b"nested")

    _, items, _ = discover_odb_files(
        OdbDiscoveryRequest(root=str(tmp_path), recursive=False)
    )

    assert [Path(item.path) for item in items] == [root_file.resolve()]


def test_discovery_rejects_a_missing_root(tmp_path: Path) -> None:
    with pytest.raises(ApiProblem) as captured:
        discover_odb_files(
            OdbDiscoveryRequest(root=str(tmp_path / "missing"), recursive=True)
        )

    assert captured.value.status == 400
    assert captured.value.code == "ROOT_NOT_FOUND"
