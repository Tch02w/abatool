from modules.postprocessor.result_catalog import collect_result_records, classify_result, result_section
from modules.postprocessor.result_index import build_result_index, load_result_index


def test_incomplete_group_is_not_published_by_catalog_or_index(tmp_path):
    batch = tmp_path / "batch"
    pending = batch / "pending"
    done = batch / "legacy-complete"
    (pending / "contours").mkdir(parents=True)
    done.mkdir()
    (pending / "contours" / "partial.png").write_bytes(b"partial")
    marker = pending / "_postprocess_incomplete.json"
    marker.write_text('{}', encoding="utf-8")
    (done / "summary.xlsx").write_bytes(b"legacy")
    assert {r.path.name for r in collect_result_records(batch)} == {"summary.xlsx"}
    assert collect_result_records(pending / "contours") == []
    build_result_index(batch, classify_result, result_section)
    assert {r["name"] for r in load_result_index(batch).records} == {"summary.xlsx"}
    marker.unlink()
    assert "partial.png" in {r.path.name for r in collect_result_records(batch)}
    build_result_index(batch, classify_result, result_section)
    assert "partial.png" in {r["name"] for r in load_result_index(batch).records}
