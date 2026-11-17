"""Qt-free ODB post-processing planning and execution.

The legacy PySide6 window grew a capable processing pipeline, but the useful
parts were embedded in widget methods.  This module preserves that pipeline as
an application service so WinUI and tests can use it without importing Qt.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .cache import (
    NUMERIC_PIPELINE_VERSION,
    abaqus_cache_version,
    cache_entry_dir,
    load_json_cache,
    numeric_cache_is_valid,
    numeric_config_snapshot,
    prescan_config_snapshot,
    quick_odb_fingerprint,
    save_json_cache,
    stable_config_hash,
    write_numeric_cache_metadata,
)
from .config import save_json
from .file_attributes import ensure_windows_hidden
from .legends import (
    aggregate_group_animation_ranges,
    aggregate_group_ranges,
    choose_sequences,
)
from .models import OdbScan, normalized_name
from .naming import natural_sort_key, parse_odb_name
from .paths import batch_temp_dir, result_root_for_odb, scan_cache_dir
from .postprocess import finalize_numeric_output, finalize_render_output
from .preflight import job_scan_issues
from .process_runner import ProcessCancelled
from .result_assets import (
    INCOMPLETE_OUTPUT_MARKER,
    RESULT_LAYOUT_VERSION,
    copy_numeric_payload,
    numeric_asset_dir,
    numeric_asset_is_valid,
    write_group_member_manifest,
    write_numeric_asset_manifest,
)
from .runner import scan_folder
from .runner_parallel import (
    MultiProcessController,
    render_group_contours,
    run_job,
    scan_field_ranges,
)

LogCallback = Callable[[str], None]
ProgressCallback = Callable[[int, str], None]


def safe_folder_name(value: str) -> str:
    """Return a Windows-safe result-directory segment."""

    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", str(value)).strip(" .")
    return cleaned or "未命名组"


@dataclass(frozen=True)
class PostprocessJob:
    path: Path
    start_step: str
    end_step: str
    frame_mode: str = "auto"
    manual_sequence_expression: str = ""
    load_direction: str = ""
    load_set: str = ""
    pile_type: str = "RC"
    pile_display_set: str = ""
    pile_concrete_set: str = ""
    pile_steel_set: str = ""
    soil_set: str = ""
    rebar_set: str = ""
    longitudinal_material: str = "HRB400"
    rebar_diameter_mm: float = 32.0
    prefracture_sequence_index: int = -1
    reinforcement_mode: str = "required"


@dataclass(frozen=True)
class PostprocessGroup:
    group_id: str
    name: str
    members: tuple[Path, ...]
    standalone: bool = False
    legend_overrides: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class PostprocessOptions:
    abaqus_command: str
    root: Path
    parallel_workers: int
    force_rescan: bool
    full_timehistory_freebody: bool
    rebar_method: str
    expected_longitudinal_rebar_count: int
    settings: Mapping[str, Any]


@dataclass(frozen=True)
class PostprocessPlan:
    jobs: Mapping[Path, PostprocessJob]
    groups: tuple[PostprocessGroup, ...]
    options: PostprocessOptions
    batch_id: str = field(
        default_factory=lambda: datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    )


def choose_role_set(candidates: list[str], preferred: str, fallback: str = "") -> str:
    """Suggest only an unambiguous configured role; never guess by set order."""
    for requested in (preferred, fallback):
        if not requested:
            continue
        matches = [name for name in candidates if normalized_name(name) == normalized_name(requested)]
        if len(matches) == 1:
            return matches[0]
        if matches:
            return ""
    return ""


def suggested_job_from_scan(scan_payload: Mapping[str, Any], defaults: Mapping[str, Any]) -> dict[str, Any]:
    """Build safe, editable defaults from one Abaqus structure scan."""

    scan = OdbScan.from_dict(dict(scan_payload))
    useful_steps = [
        step
        for step in scan.steps
        if not any(token in step.upper() for token in ("GEO", "GRA"))
    ]
    name_info = parse_odb_name(scan.path.name)
    direction = str(name_info.load_direction or "")
    diameter = name_info.rebar_diameter_mm
    return {
        "path": str(scan.path.resolve()),
        "name": scan.path.name,
        "error": scan.error,
        "steps": list(scan.steps),
        "assemblyNodeSets": list(scan.assembly_node_sets),
        "assemblyElementSets": list(scan.assembly_element_sets),
        "fieldOutputs": list(scan.field_outputs),
        "historyOutputDetails": list(scan.history_output_details),
        "setDetails": dict(scan.set_details),
        "structureCatalog": dict(scan.structure_catalog),
        "contentFingerprint": scan.content_fingerprint,
        "suggested": {
            "startStep": useful_steps[0] if useful_steps else (scan.steps[0] if scan.steps else ""),
            "endStep": scan.steps[-1] if scan.steps else "",
            "frameMode": "auto",
            "manualSequenceExpression": "",
            "loadDirection": direction,
            "loadDirectionSource": "filename" if direction else "manual_required",
            "loadSet": choose_role_set(
                scan.assembly_node_sets,
                str(defaults.get("default_load_set", "SET-LOAD")),
            ),
            "pileType": "RC",
            "pileDisplaySet": choose_role_set(
                scan.assembly_element_sets,
                str(defaults.get("default_pile_set", "SET-PILE")),
            ),
            "pileConcreteSet": choose_role_set(
                scan.assembly_element_sets,
                str(defaults.get("default_concrete_set", "SET-PILE_CON")),
            ),
            "pileSteelSet": choose_role_set(
                scan.assembly_element_sets,
                str(defaults.get("default_cf_steel_set", "SETPILESTEEL")),
                str(defaults.get("default_steel_component_set", "SET-KEY")),
            ),
            "soilSet": choose_role_set(
                scan.assembly_element_sets,
                str(defaults.get("default_soil_set", "SET-SOIL_CUT")),
                str(defaults.get("default_soil_fallback_set", "SET-SOIL-FULL")),
            ),
            "rebarSet": choose_role_set(
                scan.assembly_element_sets,
                str(defaults.get("default_rebar_set", "SET-REBAR")),
            ),
            "longitudinalMaterial": str(
                defaults.get("default_longitudinal_material", "HRB400")
            ),
            "rebarDiameterMm": float(diameter if diameter is not None else 32.0),
            "prefractureSequenceIndex": -1,
        },
        "nameMetadata": {
            "sampleId": name_info.sample_id,
            "family": name_info.family,
            "scheme": name_info.scheme,
            "reinforced": name_info.reinforced,
            "condition": name_info.condition,
            "parameterTags": list(name_info.parameter_tags),
            "isOld": name_info.is_old,
            "upDisplacementMm": name_info.up_displacement_mm,
            "lateralDisplacementMm": name_info.lateral_displacement_mm,
            "rebarDiameterMm": name_info.rebar_diameter_mm,
        },
    }


def analyze_postprocess_inputs(
    *,
    abaqus_command: str,
    abaqus_version: str,
    root: Path,
    paths: Sequence[Path],
    defaults: Mapping[str, Any],
    parallel_workers: int,
    force_rescan: bool,
    progress: ProgressCallback | None = None,
    log: LogCallback | None = None,
    controller: MultiProcessController | None = None,
) -> dict[str, Any]:
    """Read steps, sets, outputs and filename-derived defaults for selected ODBs."""

    selected = tuple(Path(path).resolve() for path in paths)
    total = len(selected)

    def forward(message: str) -> None:
        if log:
            log(message)
        if progress and message.startswith("SCAN_DONE|"):
            parts = message.split("|", 3)
            if len(parts) == 4:
                try:
                    completed = int(parts[1])
                except ValueError:
                    return
                progress(
                    round(100 * completed / max(total, 1)),
                    f"正在读取 ODB 结构 · {parts[3]}",
                )

    payload = scan_folder(
        abaqus_command,
        root,
        scan_cache_dir(root),
        forward,
        controller,
        selected_paths=selected,
        parallel_workers=parallel_workers,
        force_rescan=force_rescan,
        abaqus_version=abaqus_version,
    )
    if payload.get("cancelled"):
        raise ProcessCancelled("ODB structure scan cancelled")
    results = [suggested_job_from_scan(item, defaults) for item in payload.get("odbs", [])]
    if progress:
        progress(100, f"ODB 结构读取完成 · {len(results)} 个")
    return {
        "root": str(root.resolve()),
        "count": len(results),
        "cacheHits": int(payload.get("cache_hits", 0)),
        "parallelWorkers": int(payload.get("parallel_workers", parallel_workers)),
        "items": results,
    }


def _job_payload(
    job: PostprocessJob,
    output_dir: Path,
    options: PostprocessOptions,
    group_name: str,
) -> dict[str, Any]:
    info = parse_odb_name(job.path.name)
    return {
        "odb_path": str(job.path),
        "output_dir": str(output_dir),
        "comparison_group": group_name,
        "start_step": job.start_step,
        "end_step": job.end_step,
        "frame_mode": job.frame_mode,
        "manual_sequence_expression": job.manual_sequence_expression,
        "load_direction": job.load_direction,
        "load_set": job.load_set,
        "pile_type": job.pile_type,
        "pile_display_set": job.pile_display_set,
        "pile_concrete_set": job.pile_concrete_set,
        "pile_steel_set": job.pile_steel_set,
        "soil_set": job.soil_set,
        "rebar_set": job.rebar_set,
        **({"reinforcement_mode": job.reinforcement_mode} if job.reinforcement_mode != "required" else {}),
        "longitudinal_material": job.longitudinal_material,
        "rebar_diameter_mm": job.rebar_diameter_mm,
        "prefracture_sequence_index": job.prefracture_sequence_index,
        "full_timehistory_freebody": options.full_timehistory_freebody,
        "rebar_method": options.rebar_method,
        "expected_longitudinal_rebar_count": options.expected_longitudinal_rebar_count,
        "settings": dict(options.settings),
        "load_direction_source": "filename" if info.load_direction == job.load_direction else "manual",
        "name_metadata": {
            "sample_id": info.sample_id,
            "family": info.family,
            "scheme": info.scheme,
            "reinforced": info.reinforced,
            "condition": info.condition,
            "parameter_tags": list(info.parameter_tags),
            "is_old": info.is_old,
            "up_displacement_mm": info.up_displacement_mm,
            "lateral_displacement_mm": info.lateral_displacement_mm,
        },
    }


def _apply_legend_overrides(
    plan: dict[str, dict[str, Any]],
    overrides: Mapping[str, Mapping[str, Any]],
    group_name: str,
) -> None:
    for field_name, rule in overrides.items():
        if str(rule.get("mode", "")) != "manual":
            continue
        current = plan.setdefault(str(field_name), {})
        current.update(
            {
                "min": float(rule["min"]),
                "max": float(rule["max"]),
                "source": "comparison_group_manual_override",
                "comparison_group": group_name,
            }
        )


def execute_postprocess_plan(
    plan: PostprocessPlan,
    progress: ProgressCallback | None = None,
    log: LogCallback | None = None,
    controller: MultiProcessController | None = None,
) -> dict[str, Any]:
    """Execute every comparison group with cache-safe extraction and rendering."""

    controller = controller or MultiProcessController()
    groups = tuple(group for group in plan.groups if group.members)
    if not groups:
        raise ValueError("后处理计划中没有包含 ODB 的对比组")
    if controller.cancel_requested:
        raise ProcessCancelled("Process cancelled by user")
    if progress:
        progress(0, "正在校验所有 ODB 的分析步与提取集合")
    scans = scan_folder(
        plan.options.abaqus_command, plan.options.root, scan_cache_dir(plan.options.root),
        log, controller, selected_paths=tuple(plan.jobs),
        parallel_workers=plan.options.parallel_workers,
        force_rescan=plan.options.force_rescan,
        abaqus_version=abaqus_cache_version(dict(plan.options.settings)),
    )
    if scans.get("cancelled") or controller.cancel_requested:
        raise ProcessCancelled("ODB preflight cancelled")
    by_path = {Path(item["path"]).resolve(): item for item in scans.get("odbs", [])}
    issues = []
    for path, job in plan.jobs.items():
        scan = by_path.get(path.resolve())
        errors = ["未返回 ODB 结构，请重新读取"] if scan is None else job_scan_issues(job, scan)
        issues.extend(f"{path.name}：{error}" for error in errors)
    if issues:
        raise ValueError("后处理预检查未通过：\n" + "\n".join(issues))
    finalizer_lock = threading.Lock()
    outputs: list[str] = []
    group_results: list[dict[str, Any]] = []
    total_groups = len(groups)

    def emit(percent: int, phase: str) -> None:
        if progress:
            progress(max(0, min(100, int(percent))), phase)

    def group_progress(group_index: int, local_percent: int, phase: str) -> None:
        overall = round(100 * (group_index + local_percent / 100.0) / total_groups)
        emit(overall, phase)

    for group_index, group in enumerate(groups):
        if controller.cancel_requested:
            raise ProcessCancelled("Process cancelled by user")
        group_outputs = _execute_group(
            plan,
            group,
            group_index,
            lambda percent, phase, index=group_index: group_progress(index, percent, phase),
            log,
            controller,
            finalizer_lock,
        )
        outputs.extend(group_outputs)
        group_results.append(
            {
                "groupId": group.group_id,
                "name": group.name,
                "outputCount": len(group_outputs),
                "outputs": list(group_outputs),
            }
        )
    result_roots = sorted(
        {str(result_root_for_odb(Path(path))) for group in groups for path in group.members},
        key=natural_sort_key,
    )
    emit(100, f"ODB 后处理完成 · {len(outputs)} 个结果")
    return {
        "batchId": plan.batch_id,
        "resultRoots": result_roots,
        "outputCount": len(outputs),
        "outputs": outputs,
        "groups": group_results,
    }


def _execute_group(
    plan: PostprocessPlan,
    group: PostprocessGroup,
    group_index: int,
    progress: ProgressCallback,
    log: LogCallback | None,
    controller: MultiProcessController,
    finalizer_lock: threading.Lock,
) -> list[str]:
    members = tuple(Path(path).resolve() for path in group.members)
    # Same-named ODBs in different source directories share this scratch root.
    # A batch-local ordinal isolates both config and report writes per input.
    prescan_names = {path: f"{index:04d}_{safe_folder_name(path.stem)}" for index, path in enumerate(members)}
    workers = min(plan.options.parallel_workers, max(1, len(members)))
    cache_root = scan_cache_dir(plan.options.root)
    group_batch_id = f"{plan.batch_id}_{group_index + 1:02d}"
    scratch_root = batch_temp_dir(group_batch_id)
    abaqus_version = abaqus_cache_version(dict(plan.options.settings))

    def check_cancelled() -> None:
        if controller.cancel_requested:
            raise ProcessCancelled("Process cancelled by user")

    def tagged(path: Path, message: str) -> None:
        if log:
            log(f"[{path.name}] {message}")

    def prepare_one(path: Path) -> tuple[Path, dict[str, Any]]:
        check_cancelled()
        job = plan.jobs[path]
        payload = _job_payload(job, Path("."), plan.options, group.name)
        fingerprint = quick_odb_fingerprint(path)
        snapshot = prescan_config_snapshot(payload)
        config_hash = stable_config_hash(snapshot)
        range_scan = None
        if not plan.options.force_rescan:
            range_scan = load_json_cache(
                cache_root,
                "prescan",
                fingerprint,
                abaqus_version,
                config_hash,
            )
        if range_scan is not None:
            tagged(path, f"命中预扫描缓存：{fingerprint[:12]}/{config_hash[:12]}")
        else:
            scan_dir = scratch_root / "prescan" / prescan_names[path]
            payload["output_dir"] = str(scan_dir)
            payload["comparison_group"] = "范围预扫描"
            config_path = scan_dir / "job_config.json"
            save_json(config_path, payload)
            tagged(path, "重建场值、帧目录与损伤预扫描缓存")
            range_scan = scan_field_ranges(
                plan.options.abaqus_command,
                config_path,
                scan_dir / "frame_catalog_and_ranges.json",
                (lambda line: log(f"[{path.name}] {line}")) if log else None,
                controller,
            )
            save_json_cache(
                cache_root,
                "prescan",
                path,
                fingerprint,
                abaqus_version,
                range_scan,
                config_hash=config_hash,
                config_snapshot=snapshot,
            )
        override = int(payload["prefracture_sequence_index"])
        indices = choose_sequences(
            range_scan,
            payload["frame_mode"],
            payload["manual_sequence_expression"],
            prefracture_override=override,
        )
        detected = range_scan.get("auto_detection", {}).get(
            "prefracture_sequence_index"
        )
        if override < 0:
            payload["prefracture_sequence_index"] = (
                -1 if detected is None else int(detected)
            )
        payload["selected_sequence_indices"] = indices
        tagged(path, f"帧选择={indices}；自动断裂前帧={detected}")
        return path, {
            "payload": payload,
            "range_scan": range_scan,
            "selected_sequence_indices": indices,
            "content_fingerprint": fingerprint,
        }

    progress(2, f"对比组 {group.name} · 正在准备预扫描")
    prepared: dict[Path, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="odb-prescan") as pool:
        futures = {pool.submit(prepare_one, path): path for path in members}
        for done, future in enumerate(as_completed(futures), 1):
            try:
                path, prepared_item = future.result()
            except Exception:
                controller.cancel()
                raise
            prepared[path] = prepared_item
            progress(
                round(45 * done / len(members)),
                f"对比组 {group.name} · 预扫描 {done}/{len(members)} · {path.name}",
            )
    check_cancelled()

    jobs = [
        {
            "comparison_group": group.name,
            "selected_sequence_indices": prepared[path]["selected_sequence_indices"],
            "range_scan": prepared[path]["range_scan"],
        }
        for path in members
    ]
    group_ranges = aggregate_group_ranges(jobs).get(group.name, {})
    animation_ranges = aggregate_group_animation_ranges(jobs).get(group.name, {})
    _apply_legend_overrides(group_ranges, group.legend_overrides, group.name)
    _apply_legend_overrides(animation_ranges, group.legend_overrides, group.name)
    result_roots = {result_root_for_odb(path) for path in members}
    for result_root in result_roots:
        legends_path = (
            result_root
            / "_批次记录"
            / group_batch_id
            / "comparison_group_legends.json"
        )
        save_json(
            legends_path,
            {
                group.group_id: {
                    "name": group.name,
                    "members": [str(path) for path in members],
                    "ranges": group_ranges,
                    "animation_ranges": animation_ranges,
                }
            },
        )
        ensure_windows_hidden(legends_path)

    def extract_one(path: Path) -> str:
        check_cancelled()
        result_root = result_root_for_odb(path)
        output_dir = (
            result_root / "未分组" / group_batch_id / safe_folder_name(path.stem)
            if group.standalone
            else result_root
            / safe_folder_name(group.name)
            / group_batch_id
            / safe_folder_name(path.stem)
        )
        payload = copy.deepcopy(prepared[path]["payload"])
        payload["output_dir"] = str(output_dir)
        payload["comparison_group"] = group.name
        payload["legend_ranges"] = group_ranges
        payload["animation_legend_ranges"] = animation_ranges
        numeric_snapshot = numeric_config_snapshot(payload)
        numeric_hash = stable_config_hash(numeric_snapshot)
        fingerprint = prepared[path]["content_fingerprint"]
        numeric_entry = cache_entry_dir(
            cache_root,
            "numeric",
            fingerprint,
            numeric_hash,
        )
        shared_data_dir = numeric_asset_dir(
            result_root,
            path,
            fingerprint,
            numeric_hash,
        )
        config_path = output_dir / "job_config.json"
        shared_data_ready = numeric_asset_is_valid(
            shared_data_dir,
            content_fingerprint=fingerprint,
            numeric_config_hash=numeric_hash,
            abaqus_version=abaqus_version,
        )
        if not shared_data_ready:
            cache_ready = numeric_cache_is_valid(
                numeric_entry,
                content_fingerprint=fingerprint,
                abaqus_version=abaqus_version,
                config_hash=numeric_hash,
            )
            if shared_data_dir.is_symlink() or shared_data_dir.is_file():
                shared_data_dir.unlink()
            elif shared_data_dir.is_dir():
                shutil.rmtree(shared_data_dir)
            if cache_ready:
                copy_numeric_payload(numeric_entry, shared_data_dir)
                tagged(path, f"从持久缓存恢复 ODB 公共数据；配置={numeric_hash[:12]}")
            else:
                extract_payload = copy.deepcopy(payload)
                extract_payload["output_dir"] = str(shared_data_dir)
                extract_payload["comparison_group"] = "ODB公共数据"
                extract_payload["legend_ranges"] = {}
                extract_payload["animation_legend_ranges"] = {}
                extract_payload["render_outputs"] = False
                asset_config_path = shared_data_dir / "job_config.json"
                save_json(asset_config_path, extract_payload)
                tagged(path, f"提取一次 ODB 公共数值数据；配置={numeric_hash[:12]}")
                run_job(
                    plan.options.abaqus_command,
                    asset_config_path,
                    (lambda line: log(f"[{path.name}] {line}")) if log else None,
                    controller,
                )

            metadata_path = shared_data_dir / "metadata.json"
            if metadata_path.is_file():
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                metadata.update(
                    {
                        "odb_path": str(path),
                        "numeric_cache_reused": cache_ready,
                        "content_fingerprint": fingerprint,
                        "numeric_config_hash": numeric_hash,
                        "result_layout_version": RESULT_LAYOUT_VERSION,
                        "numeric_pipeline_version": NUMERIC_PIPELINE_VERSION,
                        "comparison_group_independent": True,
                    }
                )
                save_json(metadata_path, metadata)
            with finalizer_lock:
                finalize_numeric_output(shared_data_dir)
            write_numeric_asset_manifest(
                shared_data_dir,
                odb_path=path,
                content_fingerprint=fingerprint,
                numeric_config_hash=numeric_hash,
                abaqus_version=abaqus_version,
            )
            if not cache_ready:
                copy_numeric_payload(shared_data_dir, numeric_entry)
                write_numeric_cache_metadata(
                    numeric_entry,
                    odb_path=path,
                    content_fingerprint=fingerprint,
                    abaqus_version=abaqus_version,
                    config_hash=numeric_hash,
                    config_snapshot=numeric_snapshot,
                )
                tagged(path, "已写入持久数值缓存")
            if log:
                log(f"INDEX_SHARED_DATA|{shared_data_dir}")
        else:
            tagged(path, f"复用 ODB 公共数据；配置={numeric_hash[:12]}")

        payload["source_output_dir"] = str(shared_data_dir)
        payload["render_outputs"] = True
        check_cancelled()
        pending_marker = output_dir / INCOMPLETE_OUTPUT_MARKER
        save_json(pending_marker, {"status": "incomplete", "odb_path": str(path), "batch_id": group_batch_id})
        save_json(config_path, payload)
        tagged(path, f"按对比组重渲染云图与动画；组={group.name}")
        render_group_contours(
            plan.options.abaqus_command,
            config_path,
            (lambda line: log(f"[{path.name}] {line}")) if log else None,
            controller,
        )
        settings = payload["settings"]
        check_cancelled()
        with finalizer_lock:
            finalize_render_output(
                output_dir,
                int(settings.get("animation_fps", 5)),
                export_white_background_png=bool(
                    settings.get("export_white_background_png", True)
                ),
                export_transparent_background_png=bool(
                    settings.get("export_transparent_background_png", True)
                ),
            )
        check_cancelled()
        write_group_member_manifest(
            output_dir,
            asset_dir=shared_data_dir,
            comparison_group=group.name,
            odb_path=path,
            content_fingerprint=fingerprint,
            numeric_config_hash=numeric_hash,
        )
        check_cancelled()
        pending_marker.unlink()
        if log:
            log(f"INDEX_INCREMENTAL|{output_dir}")
        tagged(path, f"完成组输出：{output_dir}")
        return str(output_dir)

    outputs_by_path: dict[Path, str] = {}
    progress(48, f"对比组 {group.name} · 开始提取与渲染")
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="odb-extract") as pool:
        futures = {pool.submit(extract_one, path): path for path in members}
        for done, future in enumerate(as_completed(futures), 1):
            try:
                outputs_by_path[futures[future]] = future.result()
            except Exception:
                controller.cancel()
                raise
            path = futures[future]
            progress(
                48 + round(52 * done / len(members)),
                f"对比组 {group.name} · 提取 {done}/{len(members)} · {path.name}",
            )
    check_cancelled()
    # Worker completion order and filename sorting must not replace the user's order.
    return [outputs_by_path[path] for path in members]


__all__ = [
    "PostprocessGroup",
    "PostprocessJob",
    "PostprocessOptions",
    "PostprocessPlan",
    "analyze_postprocess_inputs",
    "execute_postprocess_plan",
    "safe_folder_name",
    "suggested_job_from_scan",
]
