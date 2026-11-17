from __future__ import annotations

from pathlib import Path

from modules.postprocessor.result_catalog import classify_result, result_section
from modules.postprocessor.result_index import build_result_index
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
