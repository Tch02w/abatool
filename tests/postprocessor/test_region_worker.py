import json
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace as NS

import pytest

from tests.postprocessor.test_region_extraction import fixture
from modules.postprocessor.result_catalog import collect_result_records, record_matches_section


def run_worker(tmp_path, monkeypatch, missing_output=False, cae_arguments=False, solid=False,
               source_change=False, close_error=False):
    odb, request, _, _ = fixture()
    source = tmp_path / "input.odb"
    source.write_bytes(b"original")
    request["path"] = str(source)
    if solid:
        request["method"] = "solid_section"
        monkeypatch.setitem(sys.modules, "region_solid_core", NS(extract_solid_rows=lambda *args: iter([
            dict(method="solid_section", component="Fx", value=1.)])))
    if missing_output:
        odb.steps["Load"].frames.append(NS(frameValue=2., fieldOutputs={}))
        request["frames"].append(dict(step="Load", index=1))
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps(request), encoding="utf-8")
    output = tmp_path / "results"
    accesses = []
    closed = []
    def close_odb():
        closed.append(True)
        if source_change:
            source.write_bytes(b"changed during extraction")
        if close_error:
            raise RuntimeError("ODB close failed")
    odb.close = close_odb
    def open_odb(path, **kwargs):
        accesses.append((path, kwargs))
        return odb
    monkeypatch.setitem(sys.modules, "odbAccess", NS(openOdb=open_odb))
    if solid:
        monkeypatch.setitem(sys.modules, "abaqus", NS(session=NS(openOdb=lambda name, **kw: open_odb(name, **kw))))
    script = Path(__file__).parents[2] / "modules/postprocessor/abaqus_scripts/extract_region.py"
    arguments = [str(script), "--request", str(request_file), "--output", str(output)]
    if cae_arguments:
        arguments += ["-cae", "-noGUI", str(script), "-tmpdir", str(tmp_path), "-lmlog", "ON"]
    monkeypatch.setattr(sys, "argv", arguments)
    # run_path's worker import remains local to this test.
    monkeypatch.setattr(sys, "path", list(sys.path))
    try:
        runpy.run_path(str(script), run_name="__main__")
    finally:
        assert accesses == [(str(source), {"readOnly": True})]
        if not source_change:
            assert source.read_bytes() == b"original"
        assert closed == [True]
    return output


def test_worker_publishes_only_validated_results(tmp_path, monkeypatch):
    output = run_worker(tmp_path, monkeypatch)
    assert (output / "region_values.csv").is_file()
    assert not (output / "region_values.pending.csv").exists()
    assert json.loads((output / "manifest.json").read_text(encoding="utf-8"))["rows"] == 1
    records = collect_result_records(output)
    result = next(record for record in records if record.path.name == "region_values.csv")
    assert record_matches_section(result, "common")


def test_worker_partial_frame_failure_not_published(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="Missing S"):
        run_worker(tmp_path, monkeypatch, missing_output=True)
    output = tmp_path / "results"
    assert not (output / "region_values.csv").exists()
    assert not (output / "manifest.json").exists()
    assert (output / "region_values.pending.csv").is_file()
    assert json.loads((output / "failure.json").read_text(encoding="utf-8"))["status"] == "failed"
    assert collect_result_records(output) == []


def test_worker_accepts_cae_injected_arguments(tmp_path, monkeypatch):
    output = run_worker(tmp_path, monkeypatch, cae_arguments=True)
    assert (output / "manifest.json").is_file()


@pytest.mark.parametrize("solid", [False, True])
def test_manifest_distinguishes_section_integration_from_point_values(tmp_path, monkeypatch, solid):
    output = run_worker(tmp_path, monkeypatch, solid=solid)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["aggregation"] == ("section_stress_integration" if solid else "none_per_element_per_output_location")


@pytest.mark.parametrize("solid", [False, True])
@pytest.mark.parametrize("failure", ["source_change", "close_error"])
def test_worker_close_and_source_validation_finish_before_publication(tmp_path, monkeypatch, solid, failure):
    with pytest.raises(RuntimeError):
        run_worker(tmp_path, monkeypatch, solid=solid, **{failure: True})
    output = tmp_path / "results"
    assert not (output / "manifest.json").exists()
    assert not (output / "region_values.csv").exists()
    assert (output / "_postprocess_incomplete.json").is_file()
    assert (output / "failure.json").is_file()
    assert collect_result_records(output) == []
