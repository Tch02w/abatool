import json
import threading
from pathlib import Path

import pytest

from modules.control_plane.contracts import ApiProblem
from modules.control_plane.region_extraction import (
    RegionExtractionRequest,
    execute_region_extraction,
    finalize_region_extraction,
)
from modules.postprocessor.result_catalog import (
    classify_result,
    collect_result_records,
    result_section,
)
from modules.postprocessor.result_index import build_result_index, load_result_index
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_postprocessing_api import _settings, _wait


def payload(root):
    path = root / "sample.odb"
    path.write_bytes(b"original")
    return {"schemaVersion": 1, "clientRequestId": "region-test", "root": str(root), "path": str(path),
                "region": {"scope": "instance", "instance": "A", "kind": "instance", "name": "A"},
                "method": "truss_reference_area", "acknowledgeReferenceArea": True,
                "referenceAreaOverride": 10., "frames": [{"step": "Load", "index": 0}]}


def successful_worker(arguments, cwd, log, controller):
    request = json.loads(Path(arguments[arguments.index("--request") + 1]).read_text(encoding="utf-8"))
    output = Path(arguments[arguments.index("--output") + 1])
    output.mkdir()
    csv = output / "region_values.csv"
    csv.write_text("value\n120\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"status": "succeeded", "rows": 1,
        "source": request["path"], "csv": str(csv), "request": request,
        "sourceIdentity": request["sourceIdentity"]}), encoding="utf-8")
    return output


@pytest.mark.parametrize("change", [
    {"referenceAreaOverride": float("nan")}, {"referenceAreaOverride": -2},
    {"acknowledgeReferenceArea": False}, {"method": "sum_solid_stress"},
    {"frames": []}, {"frames": [{"step": "Load", "index": True}]},
    {"region": {"scope": "assembly", "instance": "A", "kind": "instance", "name": "A"}},
])
def test_request_validation(tmp_path, change):
    request = payload(tmp_path)
    request.update(change)
    with pytest.raises(ApiProblem):
        RegionExtractionRequest.from_payload(request, "abaqus")


def test_worker_exit_zero_without_receipt_is_failure(tmp_path, monkeypatch):
    from modules.control_plane import region_extraction
    request = RegionExtractionRequest.from_payload(payload(tmp_path), "abaqus")
    monkeypatch.setattr(region_extraction, "run_process", lambda *args: None)
    with pytest.raises(RuntimeError, match="成功回执"):
        execute_region_extraction(request, None, None, None)
    assert request.path.read_bytes() == b"original"


def test_success_receipt_required_and_outputs_registered(tmp_path, monkeypatch):
    from modules.control_plane import region_extraction
    request = RegionExtractionRequest.from_payload(payload(tmp_path), "abaqus")
    monkeypatch.setattr(region_extraction, "run_process", successful_worker)
    result = execute_region_extraction(request, None, None, None)
    assert result["outputCount"] == 1
    assert result["rowCount"] == 1
    assert request.path.read_bytes() == b"original"
    output = Path(result["outputs"][0])
    assert collect_result_records(output) == []
    finalize_region_extraction(request, result)
    assert any(record.path.name == "region_values.csv" for record in collect_result_records(output))
    assert "publication_marker" not in result


def test_source_change_while_queued_prevents_worker_start(tmp_path, monkeypatch):
    from modules.control_plane import region_extraction
    request = RegionExtractionRequest.from_payload(payload(tmp_path), "abaqus")
    request.path.write_bytes(b"changed while queued")
    calls = []
    monkeypatch.setattr(region_extraction, "run_process", lambda *args: calls.append(args))
    with pytest.raises(RuntimeError, match="source|Source|源"):
        execute_region_extraction(request, None, None, None)
    assert calls == []


def test_source_change_during_worker_rejects_success_receipt(tmp_path, monkeypatch):
    from modules.control_plane import region_extraction
    request = RegionExtractionRequest.from_payload(payload(tmp_path), "abaqus")
    outputs = []
    def run(arguments, cwd, log, controller):
        output = successful_worker(arguments, cwd, log, controller)
        outputs.append(output)
        request.path.write_bytes(b"changed during worker")
    monkeypatch.setattr(region_extraction, "run_process", run)
    with pytest.raises(RuntimeError, match="source|Source|源"):
        execute_region_extraction(request, None, None, None)
    assert collect_result_records(outputs[0]) == []


def test_source_change_before_final_commit_keeps_result_hidden(tmp_path, monkeypatch):
    from modules.control_plane import region_extraction
    request = RegionExtractionRequest.from_payload(payload(tmp_path), "abaqus")
    monkeypatch.setattr(region_extraction, "run_process", successful_worker)
    result = execute_region_extraction(request, None, None, None)
    request.path.write_bytes(b"changed after worker validation")
    with pytest.raises(RuntimeError, match="Source ODB changed"):
        finalize_region_extraction(request, result)
    assert collect_result_records(Path(result["outputs"][0])) == []


@pytest.mark.parametrize("worker_failure", ["incomplete", "failure", "request", "identity", "rows"])
def test_inconsistent_worker_receipt_is_not_published(tmp_path, monkeypatch, worker_failure):
    from modules.control_plane import region_extraction
    request = RegionExtractionRequest.from_payload(payload(tmp_path), "abaqus")
    outputs = []
    def run(*args):
        output = successful_worker(*args)
        outputs.append(output)
        manifest = output / "manifest.json"
        report = json.loads(manifest.read_text(encoding="utf-8"))
        if worker_failure == "incomplete":
            (output / "_postprocess_incomplete.json").write_text("{}", encoding="utf-8")
        elif worker_failure == "failure":
            (output / "failure.json").write_text("{}", encoding="utf-8")
        elif worker_failure == "request":
            report["request"]["method"] = "beam_sections"
        elif worker_failure == "identity":
            report["sourceIdentity"]["size"] += 1
        else:
            report["rows"] = True
        manifest.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(region_extraction, "run_process", run)
    with pytest.raises(RuntimeError, match="回执"):
        execute_region_extraction(request, None, None, None)
    assert collect_result_records(outputs[0]) == []


@pytest.mark.parametrize("cancel", [False, True])
def test_manager_commits_successful_worker_only_if_not_cancelled(tmp_path, monkeypatch, cancel):
    from modules.control_plane import postprocessing, region_extraction
    ready = threading.Event()
    release = threading.Event()
    results = []
    monkeypatch.setattr(region_extraction, "run_process", successful_worker)
    def execute(*args):
        result = execute_region_extraction(*args)
        results.append(result)
        ready.set()
        assert release.wait(5)
        return result
    monkeypatch.setattr(postprocessing, "execute_region_extraction", execute)
    request = payload(tmp_path)
    with running_control_plane(tmp_path / "state", postprocess_settings_provider=_settings) as runtime:
        response = api_request(runtime, "/api/v1/odb-region-extractions", method="POST", payload=request)
        operation_id = json_response(response)["operationId"]
        try:
            assert ready.wait(5)
            output = Path(results[0]["outputs"][0])
            assert collect_result_records(output) == []
            if cancel:
                response = api_request(runtime, "/api/v1/odb-postprocess-operations/" + operation_id + "/cancel",
                                       method="POST", payload={"schemaVersion": 1})
                assert response[0] == 202
        finally:
            release.set()
        final = _wait(runtime, operation_id)
        assert final["status"] == ("cancelled" if cancel else "succeeded")
        if cancel:
            assert collect_result_records(output) == []
            result_root = Path(results[0]["resultRoots"][0])
            build_result_index(result_root, classify_result, result_section)
            assert load_result_index(result_root).records == []
        else:
            assert any(record.path.name == "region_values.csv" for record in collect_result_records(output))
            assert set(final["result"]) == {"batchId", "resultRoots", "outputCount", "outputs", "rowCount"}


def test_http_route_idempotency_and_existing_operation_tracking(tmp_path, monkeypatch):
    from modules.control_plane import postprocessing
    calls = []
    def run(request, progress, log, controller):
        calls.append(request)
        assert json.loads(request.extraction_json)["region"]["instance"] == "A"
        return {"outputCount": 1, "outputs": [str(tmp_path / "verified")], "resultRoots": [str(tmp_path)]}
    monkeypatch.setattr(postprocessing, "execute_region_extraction", run)
    monkeypatch.setattr(postprocessing, "finalize_region_extraction", lambda *args: None)
    request = payload(tmp_path)
    with running_control_plane(tmp_path, postprocess_settings_provider=_settings) as runtime:
        first = api_request(runtime, "/api/v1/odb-region-extractions", method="POST", payload=request)
        assert first[0] == 202
        second = api_request(runtime, "/api/v1/odb-region-extractions", method="POST", payload=request)
        operation_id = json_response(first)["operationId"]
        assert json_response(second)["operationId"] == operation_id
        final = _wait(runtime, operation_id)
        assert final["status"] == "succeeded"
        assert final["kind"] == "odb.postprocess.region"
        assert final["request"]["paths"] == [request["path"]]
        assert len(calls) == 1
        changed = dict(request, referenceAreaOverride=12.)
        conflict = api_request(runtime, "/api/v1/odb-region-extractions", method="POST", payload=changed)
        assert conflict[0] == 409


def test_outside_root_is_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    request = payload(root)
    outside = tmp_path / "outside.odb"
    outside.write_bytes(b"untouched")
    request["path"] = str(outside)
    with pytest.raises(ApiProblem):
        RegionExtractionRequest.from_payload(request, "abaqus")


def test_solid_section_request_normalizes_normal_and_requires_cut_definition(tmp_path):
    request = payload(tmp_path)
    request["method"] = "solid_section"
    request["referenceAreaOverride"] = None
    with pytest.raises(ApiProblem, match="Section requires"):
        RegionExtractionRequest.from_payload(request, "abaqus")
    request["section"] = {"origin": [0, 0, 0], "normal": [0, 0, 2], "offsets": [10000], "momentReference": "centroid", "momentPoint": None}
    parsed = RegionExtractionRequest.from_payload(request, "abaqus")
    assert json.loads(parsed.extraction_json)["section"]["normal"] == [0., 0., 1.]
    request["method"] = "beam_sections"
    with pytest.raises(ApiProblem, match="切面"):
        RegionExtractionRequest.from_payload(request, "abaqus")
