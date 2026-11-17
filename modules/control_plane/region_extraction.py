"""Validated native-client requests for generic region extraction."""

from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
from uuid import uuid4

from .contracts import ApiProblem
from modules.postprocessor.config import abaqus_script, save_json
from modules.postprocessor.process_runner import run_process, ProcessCancelled
from modules.postprocessor.result_assets import safe_result_name, INCOMPLETE_OUTPUT_MARKER
from modules.postprocessor.abaqus_scripts.solid_section_math import section_config
from modules.postprocessor.abaqus_scripts.region_extract_core import source_identity, require_source_identity

REGION_KIND = "odb.postprocess.region"


class RegionExtractionResult(dict):
    """Internal publication handle; marker paths never come from API payloads."""

    def __init__(self, values, marker):
        super().__init__(values)
        self.publication_marker = marker


def finalize_region_extraction(request, result):
    """Publish under the operation-manager lock after the cancellation check."""
    if not isinstance(result, RegionExtractionResult):
        raise RuntimeError("Missing internal region publication handle")
    require_source_identity(request.path, json.loads(request.extraction_json)["sourceIdentity"])
    result.publication_marker.unlink()


@dataclass(frozen=True)
class RegionExtractionRequest:
    client_request_id: str
    root: Path
    path: Path
    abaqus_command: str
    extraction_json: str

    @property
    def signature(self):
        return (REGION_KIND, str(self.root), self.abaqus_command, self.extraction_json)

    def summary(self):
        return dict(json.loads(self.extraction_json), clientRequestId=self.client_request_id,
                    root=str(self.root), paths=[str(self.path)])

    @classmethod
    def from_payload(cls, payload, abaqus_command):
        # Reuse path/auth-independent protocol validation without a module cycle.
        from .postprocessing import _validate_fields, _resolve_root, _resolve_odb_path, _text, _client_request_id
        fields = {"schemaVersion", "clientRequestId", "root", "path", "region", "method", "frames",
                  "acknowledgeReferenceArea", "referenceAreaOverride", "section"}
        _validate_fields(payload, fields, required=fields - {"section"})
        root = _resolve_root(_text(payload, "root"))
        path = _resolve_odb_path(root, _text(payload, "path"), 0)
        region = payload.get("region")
        if not isinstance(region, dict):
            raise ApiProblem(400, "INVALID_REGION", "必须指定实例或单元集")
        _validate_fields(region, {"scope", "instance", "kind", "name"}, check_schema=False)
        if (region["scope"] not in ("assembly", "instance")
                or region["kind"] not in ("instance", "element_set")
                or not isinstance(region["instance"], str)
                or not isinstance(region["name"], str) or not region["name"].strip()
                or (region["scope"] == "assembly" and (region["instance"] or region["kind"] == "instance"))
                or (region["scope"] == "instance" and not region["instance"].strip())
                or (region["kind"] == "instance" and region["name"] != region["instance"])):
            raise ApiProblem(400, "INVALID_REGION", "实例或单元集标识无效")
        method = payload.get("method")
        if method not in ("beam_sections", "truss_reference_area", "solid_section"):
            raise ApiProblem(400, "INVALID_REGION_METHOD", "请选择梁内力、钢筋参考面积轴力或实体截面内力")
        section = None
        if method == "solid_section":
            try:
                section = section_config(payload.get("section"))
            except ValueError as error:
                raise ApiProblem(400, "INVALID_SECTION", str(error)) from error
        elif payload.get("section") is not None:
            raise ApiProblem(400, "UNUSED_SECTION", "当前提取方法不使用切面参数")
        acknowledge = payload.get("acknowledgeReferenceArea")
        if type(acknowledge) is not bool or (method == "truss_reference_area" and not acknowledge):
            raise ApiProblem(400, "REFERENCE_AREA_NOT_ACKNOWLEDGED", "请确认 S11×参考面积的适用限制")
        area = payload.get("referenceAreaOverride")
        if area is not None and (type(area) not in (int, float) or not math.isfinite(area) or area <= 0):
            raise ApiProblem(400, "INVALID_REFERENCE_AREA", "截面积必须为有限正数，单位为模型长度单位的平方")
        frames = payload.get("frames")
        if not isinstance(frames, list) or not 1 <= len(frames) <= 100000:
            raise ApiProblem(400, "INVALID_REGION_FRAMES", "请明确选择至少一帧，最多十万帧")
        seen = set()
        for frame in frames:
            if not isinstance(frame, dict):
                raise ApiProblem(400, "INVALID_REGION_FRAMES", "帧选择无效")
            _validate_fields(frame, {"step", "index"}, check_schema=False)
            if not isinstance(frame["step"], str) or not frame["step"].strip() or type(frame["index"]) is not int or frame["index"] < 0:
                raise ApiProblem(400, "INVALID_REGION_FRAMES", "分析步或帧序号无效")
            key = (frame["step"], frame["index"])
            if key in seen:
                raise ApiProblem(400, "INVALID_REGION_FRAMES", "不能重复选择同一帧")
            seen.add(key)
        extraction = dict(path=str(path), region=region, method=method, frames=frames,
                          acknowledgeReferenceArea=acknowledge, referenceAreaOverride=area,
                          sourceIdentity=source_identity(path))
        if section is not None:
            extraction["section"] = section
        return cls(_client_request_id(payload), root, path, abaqus_command,
                   json.dumps(extraction, ensure_ascii=False, sort_keys=True, allow_nan=False))


def execute_region_extraction(request, progress, log, controller):
    extraction = json.loads(request.extraction_json)
    if controller is not None and controller.cancel_requested:
        raise ProcessCancelled("Process cancelled by user")
    require_source_identity(request.path, extraction["sourceIdentity"])
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_region_" + uuid4().hex[:8]
    result_root = request.root / "AbaqusODBPostProcessor_Results"
    batch = result_root / "通用对象提取" / batch_id
    batch.mkdir(parents=True, exist_ok=False)
    marker = batch / INCOMPLETE_OUTPUT_MARKER
    save_json(marker, {"kind": "region_extraction", "status": "awaiting_host_validation"})
    request_path = batch / "request.json"
    save_json(request_path, json.loads(request.extraction_json))
    output = batch / safe_result_name(request.path.stem + "__" + extraction["region"]["name"])[:100]
    if progress:
        progress(5, "正在只读提取所选对象")
    solid = extraction["method"] == "solid_section"
    command = ([request.abaqus_command, "cae", "noGUI=" + str(abaqus_script("extract_region.py")), "--"]
               if solid else [request.abaqus_command, "python", str(abaqus_script("extract_region.py"))])
    run_process(command + ["--request", str(request_path), "--output", str(output)], batch, log, controller)
    if controller is not None and controller.cancel_requested:
        raise ProcessCancelled("Process cancelled by user")
    require_source_identity(request.path, extraction["sourceIdentity"])
    # Abaqus .bat can report exit 0 after a Python exception: require a valid receipt.
    manifest = output / "manifest.json"
    if not manifest.is_file():
        failure = output / "failure.json"
        detail = json.loads(failure.read_text(encoding="utf-8")).get("error", "") if failure.is_file() else ""
        raise RuntimeError("所选对象提取未完成：" + (detail or "缺少成功回执"))
    report = json.loads(manifest.read_text(encoding="utf-8"))
    if (not isinstance(report, dict) or report.get("status") != "succeeded"
            or type(report.get("rows")) is not int or report["rows"] <= 0
            or report.get("request") != extraction
            or report.get("sourceIdentity") != extraction["sourceIdentity"]
            or (output / INCOMPLETE_OUTPUT_MARKER).exists() or (output / "failure.json").exists()
            or Path(report.get("source", "")).resolve() != request.path
            or Path(report.get("csv", "")).resolve() != output / "region_values.csv"
            or not (output / "region_values.csv").is_file()):
        raise RuntimeError("所选对象提取回执与任务不一致")
    if progress:
        progress(95, "已校验 {0} 条结果，正在确认发布".format(report["rows"]))
    return RegionExtractionResult(
        {"batchId": batch_id, "resultRoots": [str(result_root)], "outputCount": 1,
         "outputs": [str(output)], "rowCount": report["rows"]}, marker)
