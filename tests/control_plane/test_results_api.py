from __future__ import annotations

import os
from pathlib import Path

import pytest
from openpyxl import Workbook

from modules.postprocessor.result_catalog import classify_result, result_section
from modules.postprocessor.result_index import build_result_index, index_path
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)


def _post(runtime, path: str, payload: dict):
    return api_request(
        runtime,
        path,
        method="POST",
        payload={"schemaVersion": 1} | payload,
    )


def _make_result_tree(root: Path) -> tuple[Path, Path, Path]:
    batch = root / "试验组" / "20260830_120000"
    odb = batch / "模型-2"
    data = odb / "data"
    plots = odb / "plots"
    data.mkdir(parents=True)
    plots.mkdir()
    (data / "load_point_raw.csv").write_text(
        "Time,RF3\n0,0\n1,10\n",
        encoding="utf-8",
    )
    (plots / "pile_bending_moment.png").write_bytes(b"png-fixture")
    (odb / "metadata.json").write_text('{"name":"中文"}', encoding="utf-8")
    build_result_index(batch, classify_result, result_section)
    return batch, odb, data


def test_internal_index_details_belong_to_the_selected_batch(tmp_path):
    root = tmp_path / "结果"
    batch, model, _ = _make_result_tree(root)
    database = index_path(batch)
    before = database.read_bytes()
    with running_control_plane(tmp_path / "profile") as runtime:
        def listing(scope, **filters):
            response = _post(runtime, "/api/v1/result-records", {
                "root": str(root), "scope": str(scope), "timeDirectory": str(batch),
                "section": "all", **filters,
            })
            assert response[0] == 200
            return json_response(response)

        normal = listing(batch)
        shown = listing(batch, includeInternal=True, section="info", useCase="内部索引")
        row, = shown["records"]
        assert row["path"] == str(database) and row["internal"] and not row["recommended"]
        assert row["section"] == "info" and row["sizeBytes"] == len(before)
        assert row["useCase"] not in normal["useCases"]
        assert shown["totalCount"] == normal["totalCount"] + 1
        assert shown["indexMetadata"]["record_count"] == str(normal["totalCount"])
        assert shown["indexMetadata"]["identity_hash"] == normal["indexMetadata"]["identity_hash"]
        assert listing(model, includeInternal=True, useCase="内部索引")["records"] == []
        assert listing(batch, directDirectory=str(batch), includeInternal=True, query=database.name)["records"] == []
    assert database.read_bytes() == before


def test_xlsx_preview_selects_a_visible_worksheet_and_keeps_other_formats_compatible(tmp_path):
    from zipfile import ZipFile

    from openpyxl import Workbook

    root = tmp_path / "结果"
    root.mkdir()
    path = root / "多表.xlsx"
    book = Workbook()
    hidden = book.active
    hidden.title = "内部"
    hidden.sheet_state = "hidden"
    first = book.create_sheet("目录")
    first.append(["摘要"])
    detail = book.create_sheet("荷载 RF3")
    for value in range(4):
        detail.append([value, -value])
    book.create_sheet("空表")
    book.save(path)
    book.close()
    csv = root / "一列.csv"
    csv.write_text("A\n1\n", encoding="utf-8")
    no_sheets = root / "无可见表.xlsx"
    with ZipFile(no_sheets, "w") as archive:
        archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                         '<sheets><sheet name="内部" state="veryHidden"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
    with running_control_plane(tmp_path / "profile") as runtime:
        def get(f=path, **options):
            response = _post(runtime, "/api/v1/result-previews", {"root": str(root), "path": str(f), **options})
            return response[0], json_response(response)

        status, overview = get()
        assert status == 200 and overview["selectedWorksheet"] == "目录"
        assert overview["worksheets"] == ["目录", "荷载 RF3", "空表"] and overview["rows"] == [["摘要"]]
        status, selected = get(worksheet="荷载 RF3", maxRows=2)
        assert status == 200 and selected["selectedWorksheet"] == "荷载 RF3"
        assert selected["rows"] == [["0", "0"], ["1", "-1"]] and selected["truncated"]
        status, empty = get(worksheet="空表")
        assert status == 200 and empty["rows"] == empty["headers"] == [] and not empty["truncated"]
        for missing in ("内部", "已移除"):
            status, error = get(worksheet=missing)
            assert status == 422 and error["error"]["code"] == "RESULT_WORKSHEET_UNAVAILABLE"
        for invalid in (None, 4, ""):
            status, error = get(worksheet=invalid)
            assert status == 400 and error["error"]["code"] == "INVALID_RESULT_WORKSHEET"
        assert get(csv, worksheet="目录")[0] == 400
        assert "worksheets" not in get(csv)[1]
        status, error = get(no_sheets)
        assert status == 422 and "没有可预览的可见数据工作表" in error["error"]["message"]


def test_result_scopes_records_filters_and_previews_are_qt_free(tmp_path: Path) -> None:
    root = tmp_path / "AbaqusODBPostProcessor_Results"
    batch, odb, _data = _make_result_tree(root)

    with running_control_plane(tmp_path) as runtime:
        scopes_response = _post(runtime, "/api/v1/result-scopes", {"root": str(root)})
        assert scopes_response[0] == 200
        scopes = json_response(scopes_response)
        assert [node["kind"] for node in scopes["nodes"]] == [
            "root",
            "group",
            "batch",
            "odb",
        ]
        assert scopes["nodes"][2]["path"] == str(batch.resolve())
        assert scopes["nodes"][2]["indexState"] == "available"
        assert scopes["nodes"][3]["timeDirectory"] == str(batch.resolve())

        records_response = _post(
            runtime,
            "/api/v1/result-records",
            {
                "root": str(root),
                "scope": str(odb),
                "timeDirectory": str(batch),
                "section": "common",
                "query": "load_point",
                "useCase": "",
                "offset": 0,
                "limit": 50,
            },
        )
        assert records_response[0] == 200
        records = json_response(records_response)
        assert records["source"] == "index"
        assert records["filteredCount"] == 1
        assert records["records"][0]["name"] == "load_point_raw.csv"
        assert records["records"][0]["recommended"] is True
        assert records["sectionCounts"]["data"] == 1
        assert "荷载与位移" in records["useCases"]

        preview_response = _post(
            runtime,
            "/api/v1/result-previews",
            {
                "root": str(root),
                "path": str(odb / "data" / "load_point_raw.csv"),
                "maxRows": 1,
            },
        )
        assert preview_response[0] == 200
        preview = json_response(preview_response)
        assert preview["kind"] == "table"
        assert preview["headers"] == ["Time", "RF3"]
        assert preview["rows"] == [["0", "0"]]
        assert preview["truncated"] is True
        exact = json_response(_post(runtime, "/api/v1/result-previews", {
            "root": str(root), "path": str(odb / "data" / "load_point_raw.csv"), "maxRows": 2,
        }))
        assert exact["rows"] == [["0", "0"], ["1", "10"]] and exact["truncated"] is False
        broken = odb / "damaged.xlsx"
        broken.write_bytes(b"invalid workbook")
        failed = _post(runtime, "/api/v1/result-previews", {"root": str(root), "path": str(broken)})
        assert failed[0] == 422 and json_response(failed)["error"]["code"] == "RESULT_PREVIEW_FAILED"

        text_preview = json_response(
            _post(
                runtime,
                "/api/v1/result-previews",
                {"root": str(root), "path": str(odb / "metadata.json")},
            )
        )
        assert text_preview["kind"] == "text"
        assert "中文" in text_preview["text"]


def test_result_api_rejects_missing_indexes_and_paths_outside_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "results"
    batch = root / "group" / "batch"
    odb = batch / "odb"
    odb.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")

    with running_control_plane(tmp_path) as runtime:
        missing_index = _post(
            runtime,
            "/api/v1/result-records",
            {
                "root": str(root),
                "scope": str(odb),
                "timeDirectory": str(batch),
            },
        )
        assert missing_index[0] == 409
        assert json_response(missing_index)["error"]["code"] == "RESULT_INDEX_MISSING"

        outside_preview = _post(
            runtime,
            "/api/v1/result-previews",
            {"root": str(root), "path": str(outside)},
        )
        assert outside_preview[0] == 400
        assert json_response(outside_preview)["error"]["code"] == (
            "PATH_OUTSIDE_RESULT_ROOT"
        )


def test_direct_result_browse_lists_one_level_and_never_builds_an_index(tmp_path):
    from modules.postprocessor.file_attributes import ensure_windows_hidden
    from modules.postprocessor.result_assets import INCOMPLETE_OUTPUT_MARKER
    from modules.postprocessor.result_index import index_path

    root = tmp_path / "结果"
    batch = root / "分组" / "提取批次"
    model = batch / "模型"
    data = model / "data"
    data.mkdir(parents=True)
    sibling = batch / "另一个模型"
    sibling.mkdir()
    pending = model / "未发布"
    pending.mkdir()
    (pending / INCOMPLETE_OUTPUT_MARKER).touch()
    for name in ("_internal.log", ".隐藏", "临时.part", "~$workbook.xlsx", "summary.xlsx"):
        (model / name).touch()
    if os.name == "nt":
        hidden = model / "attribute-only.txt"
        hidden.touch()
        ensure_windows_hidden(hidden)
    for number in (10, 2, 1):
        (data / f"load{number}.csv").write_text(f"time,force\n0,{number}\n", encoding="utf-8")
    queries = {"root": str(root), "scope": str(model), "timeDirectory": str(batch)}
    with running_control_plane(tmp_path) as runtime:
        def records(directory, **extra):
            return _post(runtime, "/api/v1/result-records", {**queries, "directDirectory": str(directory), **extra})

        assert _post(runtime, "/api/v1/result-records", queries)[0] == 409
        response = json_response(records(model, includeInternal=True))
        assert response["source"] == "direct" and response["directDirectory"] == str(model)
        assert [(entry["name"], entry["isDirectory"]) for entry in response["records"]] == [
            ("data", True), ("summary.xlsx", False),
        ]
        page = json_response(records(data, offset=1, limit=1))
        assert page["filteredCount"] == 3 and page["hasMore"]
        file = page["records"][0]
        assert (file["name"], Path(file["relativePath"])) == ("load2.csv", Path("data/load2.csv"))
        preview = json_response(_post(runtime, "/api/v1/result-previews", {"root": str(root), "path": file["path"]}))
        assert preview["rows"] == [["0", "2"]]
        for directory, extra in [
            (pending, {}), (sibling, {}), (model / ".." / model.name, {}),
            (root, {"scope": str(root)}), (data, {"scope": str(data)}),
            (data, {"timeDirectory": str(root)}),
        ]:
            assert records(directory, **extra)[0] in (400, 409)
        (data / INCOMPLETE_OUTPUT_MARKER).touch()
        assert records(data)[0] == 409
        assert [r["name"] for r in json_response(records(model))["records"]] == ["summary.xlsx"]
        assert not index_path(batch).exists()
        build_result_index(batch, classify_result, result_section)
        assert json_response(_post(runtime, "/api/v1/result-records", queries))["source"] == "index"


def test_direct_result_browse_skips_and_rejects_directory_links(tmp_path):
    from modules.control_plane.contracts import ApiProblem
    from modules.control_plane.results import list_result_records

    root = tmp_path / "results"
    batch = root / "group" / "batch"
    model = batch / "model"
    real = model / "real"
    real.mkdir(parents=True)
    link = model / "alias"
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(real), str(link))
    else:
        link.symlink_to(real, target_is_directory=True)
    params = {"schemaVersion": 1, "root": str(root), "scope": str(model), "timeDirectory": str(batch)}
    assert [r["name"] for r in list_result_records(params | {"directDirectory": str(model)})["records"]] == ["real"]
    with pytest.raises(ApiProblem, match="目录不可浏览"):
        list_result_records(params | {"directDirectory": str(link)})


def test_direct_browse_pages_a_large_directory_with_a_damaged_index(tmp_path):
    from modules.control_plane.contracts import ApiProblem
    from modules.control_plane.results import list_result_records
    from modules.postprocessor.result_index import index_path

    root = tmp_path / "results"
    batch = root / "group" / "batch"
    model = batch / "model"
    model.mkdir(parents=True)
    for number in range(501):
        (model / f"curve{number}.csv").touch()
    index_path(batch).write_bytes(b"damaged index")
    params = {"schemaVersion": 1, "root": str(root), "scope": str(batch), "timeDirectory": str(batch)}
    with pytest.raises(ApiProblem) as raised:
        list_result_records(params)
    assert raised.value.code == "RESULT_INDEX_INVALID"
    direct = params | {"directDirectory": str(model), "limit": 500}
    first = list_result_records(direct)
    last = list_result_records(direct | {"offset": 500})
    assert first["hasMore"] and len(first["records"]) == 500 and first["records"][-1]["name"] == "curve499.csv"
    assert not last["hasMore"] and last["filteredCount"] == 501 and last["records"][0]["name"] == "curve500.csv"
    assert index_path(batch).read_bytes() == b"damaged index"


def test_direct_page_anchors_stay_ordered_as_files_change(tmp_path):
    from modules.control_plane.results import list_result_records

    batch = tmp_path / "group" / "batch"
    model = batch / "model"
    model.mkdir(parents=True)
    (model / "²").mkdir()
    for name in ("x2.csv", "x1.csv", "x01.csv", "x10.csv", "x3.csv", "notes.txt"):
        (model / name).touch()
    params = {"schemaVersion": 1, "root": str(tmp_path), "scope": str(model),
              "timeDirectory": str(batch), "directDirectory": str(model), "limit": 2}

    def turn(page, direction, **kwargs):
        edge = page["records"][0 if direction == "before" else -1]
        anchor = {"name": edge["name"], "isDirectory": edge["isDirectory"], "direction": direction}
        return list_result_records(params | {"directAnchor": anchor} | kwargs)

    def names(page):
        return [r["name"] for r in page["records"]]

    first = list_result_records(params)
    assert names(first) == ["²", "notes.txt"]
    second = turn(first, "after")
    assert names(second) == ["x01.csv", "x1.csv"] and second["offset"] == 2
    assert turn(second, "before") == first
    # Insert ahead of the visible page and rename its last row out of the way.
    (model / "added.csv").touch()
    (model / "x1.csv").rename(model / "x20.csv")
    third = turn(second, "after")
    assert names(third) == ["x2.csv", "x3.csv"] and third["offset"] == 4
    assert third["filteredCount"] == 8 and third["hasMore"]
    last = turn(third, "after")
    assert names(last) == ["x10.csv", "x20.csv"] and not last["hasMore"]
    assert turn(last, "before") == third
    assert names(turn(third, "before")) == ["notes.txt", "x01.csv"]
    # Changed contents can make the preceding page shorter than the page size.
    filtered = turn(second, "before", section="data", query="x0")
    assert not filtered["records"] and filtered["offset"] == 0 and filtered["hasMore"]
    assert filtered["totalCount"] == 8 and filtered["filteredCount"] == 1
    (model / "x2.csv").unlink()
    assert names(turn(second, "after")) == ["x3.csv", "x10.csv"]
    assert names(list_result_records(params)) == ["²", "added.csv"]


def test_direct_paging_rejects_invalid_arguments_before_scanning(tmp_path, monkeypatch):
    from modules.control_plane import results
    from modules.control_plane.contracts import ApiProblem

    batch = tmp_path / "group" / "batch"
    batch.mkdir(parents=True)
    params = {"schemaVersion": 1, "root": str(tmp_path), "timeDirectory": str(batch), "scope": str(batch)}
    anchor = {"name": "row1.csv", "isDirectory": False, "direction": "after"}
    direct = params | {"directDirectory": str(batch)}
    monkeypatch.setattr(results, "_direct_records", lambda *_: pytest.fail("invalid request scanned directory"))
    for update, expected in [
        ({"directAnchor": None}, "INVALID_DIRECT_ANCHOR"),
        ({"directAnchor": anchor | {"name": "../x.csv"}}, "INVALID_DIRECT_ANCHOR"),
        ({"directAnchor": anchor | {"isDirectory": 1}}, "INVALID_DIRECT_ANCHOR"),
        ({"directAnchor": anchor | {"direction": []}}, "INVALID_DIRECT_ANCHOR"),
        ({"limit": 501}, "INVALID_LIMIT"), ({"offset": -1}, "INVALID_OFFSET"),
        ({"section": "_"}, "INVALID_RESULT_SECTION"), ({"query": []}, "INVALID_RESULT_FILTER"),
    ]:
        with pytest.raises(ApiProblem) as error:
            results.list_result_records(direct | update)
        assert error.value.code == expected
    with pytest.raises(ApiProblem) as error:
        results.list_result_records(params | {"directAnchor": anchor})
    assert error.value.code == "INVALID_DIRECT_ANCHOR"


def test_xlsx_preview_returns_real_workbook_values_and_rejects_bad_shared_references(tmp_path):
    from tests.postprocessor.test_result_xlsx_preview import workbook

    root = tmp_path / "results"
    root.mkdir()
    path = root / "工程预览.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.append(["时间", "荷载", "备注"])
    sheet.append([0, 12.5, "中文说明"])
    sheet.append([1, -2.75, None])
    book.save(path)
    book.close()
    original = path.read_bytes()
    shared = workbook(root / "shared.xlsx", '<row r="1"><c r="A1" t="s"><v>0</v></c>'
                      '<c r="B1" t="s"><v>5</v></c></row>', string_count=100)

    with running_control_plane(tmp_path) as runtime:
        def preview(target, limit):
            return _post(runtime, "/api/v1/result-previews", {
                "root": str(root), "path": str(target), "maxRows": limit,
            })

        response = preview(path, 2)
        assert response[0] == 200
        data = json_response(response)
        assert data["headers"] == ["A", "B", "C"]
        assert data["rows"] == [["时间", "荷载", "备注"], ["0", "12.5", "中文说明"]]
        assert data["truncated"] is True
        exact = json_response(preview(path, 3))
        assert exact["rows"][-1] == ["1", "-2.75", ""]
        assert exact["truncated"] is False
        response = preview(shared, 1)
        assert response[0] == 200
        assert json_response(response)["rows"] == [["载荷 N", "value-5-" + "x" * 128]]
        for reference in ("-1", "999", "not-an-index"):
            invalid = workbook(root / "invalid.xlsx",
                f'<row r="1"><c r="A1" t="s"><v>{reference}</v></c></row>', string_count=2)
            failed = preview(invalid, 1)
            assert failed[0] == 422
            assert json_response(failed)["error"]["code"] == "RESULT_PREVIEW_FAILED"
    assert path.read_bytes() == original
