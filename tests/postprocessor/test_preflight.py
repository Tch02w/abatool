from dataclasses import replace
from pathlib import Path

import pytest

from modules.postprocessor.postprocess_execution import PostprocessJob
from modules.postprocessor.preflight import job_scan_issues


def fixture():
    job = PostprocessJob(
        path=Path("case.odb"), start_step="Load-1", end_step="Load-2",
        load_set="Load", pile_display_set="Pile", pile_concrete_set="Concrete",
        soil_set="Soil", rebar_set="Rebar",
    )
    scan = {
        "steps": ["Load-1", "Load-2"], "assembly_node_sets": ["Load"],
        "assembly_element_sets": ["Pile", "Concrete", "Soil", "Rebar", "Steel"],
    }
    return job, scan


@pytest.mark.parametrize("pile_type,steel", [("RC", ""), ("RC", "Steel"), ("CFST", "Steel")])
def test_explicit_supported_roles_pass(pile_type, steel):
    job, scan = fixture()
    assert job_scan_issues(replace(job, pile_type=pile_type, pile_steel_set=steel), scan) == []


def test_cf_steel_remains_optional_as_in_legacy_extraction():
    job, scan = fixture()
    assert job_scan_issues(replace(job, pile_type="CFST"), scan) == []


def test_wrong_set_kind_does_not_pass_by_matching_name():
    job, scan = fixture()
    scan["assembly_node_sets"] = []
    scan["assembly_element_sets"].append("Load")
    assert job_scan_issues(job, scan) == ["加载节点集不存在：Load"]


def test_missing_and_empty_roles_are_reported_together():
    job, scan = fixture()
    scan["set_details"] = {"Pile": {"element_count": 0}}
    issues = job_scan_issues(replace(job, soil_set="Gone"), scan)
    assert issues == ["桩体显示集合为空：Pile", "土体集合不存在：Gone"]


def test_step_order_and_empty_frames_are_rejected():
    job, scan = fixture()
    assert job_scan_issues(replace(job, start_step="Load-2", end_step="Load-1"), scan) == ["起始分析步不能晚于结束分析步"]
    scan["step_details"] = [{"name": name, "frame_count": 0} for name in scan["steps"]]
    assert job_scan_issues(job, scan) == ["所选分析步范围没有可用帧"]


def test_scan_error_is_not_hidden_behind_missing_fields():
    job, _ = fixture()
    assert job_scan_issues(job, {"error": "unreadable"}) == ["ODB 无法读取：unreadable"]


def test_explicit_unreinforced_model_does_not_require_truss_or_rebar_set():
    job, scan = fixture()
    scan["instances"] = {"Concrete": {"element_types": {"C3D8R": 10}}}
    scan["assembly_element_sets"].remove("Rebar")
    assert job_scan_issues(replace(job, reinforcement_mode="none", rebar_set=""), scan) == []
    assert job_scan_issues(replace(job, reinforcement_mode="invalid"), scan)


def test_solid_only_model_reports_legacy_capability_limit():
    job, scan = fixture()
    scan["instances"] = {"Concrete": {"element_types": {"C3D8R": 20}}}
    assert "没有 T3D2" in job_scan_issues(job, scan)[0]
    scan["instances"]["Rebar"] = {"element_types": {"T3D2": 30}}
    assert job_scan_issues(job, scan) == []


def test_missing_type_metadata_is_not_treated_as_proof_of_missing_bars():
    job, scan = fixture()
    scan["instances"] = {"Concrete": {"element_types": {"C3D8R": 20}}, "Unknown": {}}
    assert job_scan_issues(job, scan) == []


@pytest.mark.parametrize("invalid_second", [False, True])
def test_all_groups_are_validated_before_any_extraction(tmp_path, monkeypatch, invalid_second):
    from modules.postprocessor import postprocess_execution as execution

    job, scan = fixture()
    paths = [tmp_path / "first.odb", tmp_path / "second.odb"]
    jobs = {path: replace(job, path=path) for path in paths}
    reports = [dict(scan, path=str(path)) for path in paths]
    if invalid_second:
        reports[1]["assembly_node_sets"] = []
    calls = []
    monkeypatch.setattr(execution, "scan_folder", lambda *a, **kw: {"odbs": reports})
    monkeypatch.setattr(execution, "_execute_group", lambda plan, group, *a: calls.append(group.group_id) or [])
    plan = execution.PostprocessPlan(
        jobs=jobs,
        groups=tuple(execution.PostprocessGroup(str(i), str(i), (path,)) for i, path in enumerate(paths)),
        options=execution.PostprocessOptions(
            abaqus_command="abaqus", root=tmp_path, parallel_workers=2, force_rescan=False,
            full_timehistory_freebody=False, rebar_method="element_cut",
            expected_longitudinal_rebar_count=0, settings={},
        ),
    )
    if invalid_second:
        with pytest.raises(ValueError, match="second.odb：加载节点集不存在"):
            execution.execute_postprocess_plan(plan)
        assert calls == []
    else:
        execution.execute_postprocess_plan(plan)
        assert calls == ["0", "1"]
