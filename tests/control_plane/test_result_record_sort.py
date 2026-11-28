from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from modules.control_plane import results
from modules.control_plane.contracts import ApiProblem
from modules.postprocessor.naming import natural_sort_key
from modules.postprocessor.result_assets import SHARED_DATA_ROOT_NAME
from modules.postprocessor.result_catalog import classify_result, result_section
from modules.postprocessor.result_index import build_result_index


def _edge(page, direction):
    record = page["records"][0 if direction == "before" else -1]
    return {"name": record["name"], "isDirectory": record["isDirectory"],
            "direction": direction, "sortAnchor": record["sortAnchor"]}


def test_index_tail_offsets_follow_the_filtered_scope_and_keep_counts(tmp_path):
    batch = tmp_path / "group" / "batch"
    model = batch / "模型"
    other = batch / "其他"
    for directory, count in ((model, 11), (other, 3)):
        directory.mkdir(parents=True)
        for i in range(count):
            (directory / f"frame{i}.csv").write_text("data\n", encoding="utf-8")
    build_result_index(batch, classify_result, result_section)
    query = {"schemaVersion": 1, "root": str(tmp_path), "timeDirectory": str(batch),
             "scope": str(model), "sortBy": "name", "limit": 3, "section": "all"}
    for offset in (0, 5, 8, 9, 11, 14, 10**40):
        page = results.list_result_records(query | {"offset": offset})
        assert [r["name"] for r in page["records"]] == [f"frame{i}.csv" for i in range(11)][offset:offset + 3]
        assert page["totalCount"] == page["filteredCount"] == 11
        assert page["hasMore"] == (offset + 3 < 11)
        filtered = results.list_result_records(query | {"offset": offset, "query": "frame1"})
        assert [r["name"] for r in filtered["records"]] == ["frame1.csv", "frame10.csv"][offset:offset + 3]
        assert filtered["totalCount"] == 11 and filtered["filteredCount"] == 2


def _names(page):
    return [record["name"] for record in page["records"]]


@pytest.fixture(scope="module")
def catalog(tmp_path_factory):
    root = tmp_path_factory.mktemp("sort-catalog")
    batch = root / "group" / "batch"
    model = batch / "model"
    shared = root / SHARED_DATA_ROOT_NAME / "model" / "v1"
    files = [("x10.csv", 200, 100), ("x2.csv", 10, 300), ("x02.csv", 10, 200),
             ("run.log", 80, 0), ("summary.xlsx", 20, 0), ("load_point_raw.csv", 0, 400)]
    for directory in (model, shared):
        directory.mkdir(parents=True)
        for name, size, nanos in files:
            path = directory / name
            path.write_bytes(b"x" * size)
            timestamp = 1_700_000_000_000_000_000 + nanos
            os.utime(path, ns=(timestamp, timestamp))
    build_result_index(batch, classify_result, result_section)
    base = {"schemaVersion": 1, "root": str(root), "scope": str(model), "timeDirectory": str(batch), "limit": 2}
    return files, {"index": base, "direct": base | {"directDirectory": str(model)},
                   "shared": {"schemaVersion": 1, "root": str(root), "scope": str(shared), "limit": 2}}


@pytest.mark.parametrize("sort_by", ["recommended", "useCase", "description", "name", "path", "size", "modified"])
@pytest.mark.parametrize("descending", [False, True])
def test_sort_before_pagination_in_all_three_sources(catalog, sort_by, descending):
    files, queries = catalog
    stable = sorted(files, key=lambda item: (natural_sort_key(item[0]), item[0]))

    def key(item):
        name, size, nanos = item
        record = classify_result(Path(name))
        return {"recommended": record.recommended, "useCase": record.use_case.casefold(),
                "description": record.description.casefold(), "name": natural_sort_key(name),
                "path": natural_sort_key(name), "size": size, "modified": nanos}[sort_by]

    expected = [name for name, *_ in sorted(stable, key=key, reverse=descending)]
    for source, query in queries.items():
        params = query | {"sortBy": sort_by, "sortDescending": descending}
        page = results.list_result_records(params)
        for offset in range(0, len(expected), 2):
            assert (page["sortBy"], page["sortDescending"], page["offset"]) == (sort_by, descending, offset)
            assert _names(page) == expected[offset:offset + 2]
            assert page["filteredCount"] == len(expected)
            if offset and source == "direct":
                prev = results.list_result_records(params | {"directAnchor": _edge(page, "before")})
                assert _names(prev) == expected[offset - 2:offset]
            if page["hasMore"]:
                turn = {"directAnchor": _edge(page, "after")} if source == "direct" else {"offset": offset + 2}
                page = results.list_result_records(params | turn)


def test_direct_boundary_order_survives_removed_anchor_and_rejects_invalid_cursors(tmp_path, monkeypatch):
    batch = tmp_path / "group" / "batch"
    batch.mkdir(parents=True)
    subdir = batch / "dir"
    subdir.mkdir()
    for name in ("x2.csv", "x10.csv", "x3.csv"):
        (batch / name).touch()
    query = {"schemaVersion": 1, "root": str(tmp_path), "scope": str(batch), "timeDirectory": str(batch),
             "directDirectory": str(batch), "limit": 2, "sortBy": "size", "sortDescending": True}
    first = results.list_result_records(query)
    assert _names(first) == ["dir", "x2.csv"]
    edge = _edge(first, "after")
    (batch / edge["name"]).unlink()
    next_page = results.list_result_records(query | {"directAnchor": edge})
    assert _names(next_page) == ["x3.csv", "x10.csv"] and next_page["offset"] == 1
    prev = results.list_result_records(query | {"directAnchor": _edge(next_page, "before")})
    assert _names(prev) == ["dir"] and prev["offset"] == 0

    monkeypatch.setattr(results, "_direct_records", lambda *_: pytest.fail("invalid cursor scanned directory"))
    for change in ({"sortBy": "name"}, {"sortDescending": False}, {"directDirectory": str(subdir)},
                   {"directAnchor": edge | {"name": "x3.csv"}}, {"directAnchor": edge | {"sortAnchor": "💡"}},
                   {"directAnchor": edge | {"sortAnchor": edge["sortAnchor"][:-2]}},
                   {"directAnchor": {k: v for k, v in edge.items() if k != "sortAnchor"}}):
        with pytest.raises(ApiProblem) as raised:
            results.list_result_records(query | {"directAnchor": edge} | change)
        assert raised.value.code == "INVALID_DIRECT_ANCHOR"


def test_legacy_sort_and_invalid_argument_types(catalog):
    _, queries = catalog
    for query in queries.values():
        original = results.list_result_records(query)
        assert (original["sortBy"], original["sortDescending"]) == ("default", False)
        for value in ("default", None):
            assert results.list_result_records(query | {"sortBy": value, "sortDescending": True}) == original
        for patch in ({"sortBy": []}, {"sortBy": "Size"}, {"sortDescending": 1}, {"sortDescending": None}):
            with pytest.raises(ApiProblem) as raised:
                results.list_result_records(query | patch)
            assert raised.value.code == "INVALID_RESULT_SORT"


def test_relative_paths_and_missing_values_in_both_directions(tmp_path, monkeypatch):
    scope = tmp_path / "shared"
    scope.mkdir()
    mocked = [replace(classify_result(path), description=description, size=size, mtime_ns=mtime)
              for path, description, size, mtime in [
                  (scope / "part10" / "x.csv", "", -1, 0), (scope / "part2" / "x.csv", "measure", 0, 1)]]
    monkeypatch.setattr(results, "collect_result_records", lambda _: mocked)
    for descending in (False, True):
        params = {"schemaVersion": 1, "root": str(tmp_path), "scope": str(scope), "sortDescending": descending}
        for field in ("size", "modified", "description"):
            records = results.list_result_records(params | {"sortBy": field})["records"]
            assert [row["relativePath"] for row in records] == [str(Path(f"part{i}/x.csv")) for i in (2, 10)]
        records = results.list_result_records(params | {"sortBy": "path"})["records"]
        assert [row["relativePath"] for row in records] == [
            str(Path(f"part{i}/x.csv")) for i in ((10, 2) if descending else (2, 10))]


def test_legacy_deep_offset_keeps_heap_bounded_and_counts_records_once(tmp_path, monkeypatch):
    directory = tmp_path / "group" / "batch"
    directory.mkdir(parents=True)
    sizes = []
    scans = []
    original = results.heapq.nsmallest

    def scan(_directory):
        scans.append(True)
        for i in reversed(range(1280)):
            yield replace(classify_result(directory / f"curve{i}.csv"), size=i)

    def capture(count, iterable, **kwargs):
        sizes.append(count)
        return original(count, iterable, **kwargs)

    monkeypatch.setattr(results, "_direct_records", scan)
    monkeypatch.setattr(results.heapq, "nsmallest", capture)
    params = {"schemaVersion": 1, "root": str(tmp_path), "scope": str(directory), "timeDirectory": str(directory),
              "directDirectory": str(directory), "sortBy": "size", "offset": 990, "limit": 40}
    page = results.list_result_records(params)
    assert _names(page) == [f"curve{i}.csv" for i in range(990, 1030)]
    assert (page["totalCount"], page["filteredCount"], page["offset"]) == (1280, 1280, 990)
    assert max(sizes) <= results.MAX_RESULT_PAGE_SIZE
    scans.clear()
    sizes.clear()
    following = results.list_result_records(params | {"directAnchor": _edge(page, "after")})
    assert _names(following) == [f"curve{i}.csv" for i in range(1030, 1070)]
    assert len(scans) == 1 and sizes == [40]
