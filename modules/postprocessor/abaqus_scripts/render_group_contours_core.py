"""Render group-specific contour frames without repeating numeric extraction."""

from __future__ import print_function

from abaqus import session
from abaqusConstants import *
import visualization
import displayGroupOdbToolset as dgo
import csv
import json
import math
import os
import sys
import traceback


config_candidates = [value for value in sys.argv if value.lower().endswith(".json")]
if not config_candidates:
    raise RuntimeError("Cannot locate group render job JSON in argv: {0}".format(repr(sys.argv)))
config_path = os.path.abspath(config_candidates[-1])
with open(config_path, "r", encoding="utf-8") as stream:
    config = json.load(stream)

odb_path = os.path.abspath(config["odb_path"])
output_dir = os.path.abspath(config["output_dir"])
source_output_dir = os.path.abspath(config["source_output_dir"])
frame_root = os.path.join(output_dir, "frames")
contour_dir = os.path.join(output_dir, "contours")
os.makedirs(frame_root, exist_ok=True)
os.makedirs(contour_dir, exist_ok=True)
log_path = os.path.join(output_dir, "abaqus_worker.log")


def log(message):
    text = str(message)
    print(text)
    sys.stdout.flush()
    with open(log_path, "a", encoding="utf-8") as stream:
        stream.write(text + "\n")


with open(log_path, "w", encoding="utf-8") as stream:
    stream.write("Abaqus group contour renderer started\n")


def read_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


full_timeline = read_rows(os.path.join(source_output_dir, "data", "timeline_alignment.csv"))
if not full_timeline:
    raise RuntimeError("Numeric cache has no timeline rows: {0}".format(source_output_dir))
selected_timeline_path = os.path.join(
    source_output_dir, "data", "selected_timeline_alignment.csv"
)
if os.path.isfile(selected_timeline_path):
    selected_timeline = read_rows(selected_timeline_path)
else:
    requested_sequences = set(
        int(value) for value in config.get("selected_sequence_indices", [])
    )
    selected_timeline = [
        row
        for row in full_timeline
        if not requested_sequences
        or int(row["SequenceIndex"]) in requested_sequences
    ]
if not selected_timeline:
    raise RuntimeError("Numeric cache has no selected timeline rows: {0}".format(source_output_dir))
timeline = selected_timeline

rebar_rows = read_rows(
    os.path.join(source_output_dir, "rebar", "rebar_element_stress_force_timehistory.csv")
)
longitudinal = {}
for row in rebar_rows:
    key = (row["InstanceName"], int(row["ElementLabel"]))
    longitudinal[key] = True

settings = config["settings"]
image_size_unit = str(settings.get("image_size_unit", "px")).lower()
image_width = int(settings.get("image_width", 1500))
image_height = int(settings.get("image_height", 1000))
if image_size_unit not in ("px", "mm"):
    raise RuntimeError("image_size_unit must be px or mm")
if image_size_unit == "px":
    if not 320 <= image_width <= 4096 or not 320 <= image_height <= 4096:
        raise RuntimeError("Pixel image dimensions must be between 320 and 4096")
    image_size_setting = (image_width, image_height)
else:
    if not 30 <= image_width <= 500 or not 30 <= image_height <= 500:
        raise RuntimeError("Viewport dimensions must be between 30 and 500 mm")
    image_size_setting = SIZE_ON_SCREEN


def create_large_render_viewport(name, unit, requested_width, requested_height):
    """Use a real large canvas so fixed-size annotations stay proportional."""

    if unit == "mm":
        try:
            viewport = session.Viewport(
                name=name,
                origin=(0, 0),
                width=float(requested_width),
                height=float(requested_height),
                border=OFF,
                titleBar=OFF,
            )
            return viewport, (float(requested_width), float(requested_height))
        except Exception as error:
            raise RuntimeError(
                "The requested {0}x{1} mm viewport does not fit the current "
                "screen; reduce the dimensions: {2}".format(
                    requested_width, requested_height, error
                )
            )

    aspect_ratio = float(requested_width) / float(requested_height)
    attempts = []
    for maximum_width, maximum_height in (
        (396.0, 264.0),
        (360.0, 240.0),
        (330.0, 220.0),
        (300.0, 200.0),
        (270.0, 180.0),
        (240.0, 160.0),
        (180.0, 120.0),
    ):
        if maximum_width / maximum_height >= aspect_ratio:
            height = maximum_height
            width = height * aspect_ratio
        else:
            width = maximum_width
            height = width / aspect_ratio
        if width < 30.0 or height < 30.0:
            continue
        try:
            viewport = session.Viewport(
                name=name,
                origin=(0, 0),
                width=width,
                height=height,
                border=OFF,
                titleBar=OFF,
            )
            return viewport, (width, height)
        except Exception as error:
            attempts.append("{0:g}x{1:g}: {2}".format(width, height, error))
    raise RuntimeError(
        "Unable to create a large render viewport: {0}".format(
            " | ".join(attempts)
        )
    )


viewport, render_viewport_mm = create_large_render_viewport(
    "Group contour renderer",
    image_size_unit,
    image_width,
    image_height,
)
viewport.makeCurrent()
odb = session.openOdb(name=odb_path, readOnly=True)
viewport.setValues(displayedObject=odb)
viewport.odbDisplay.setFrame(
    step=int(timeline[0]["StepIndex"]), frame=int(timeline[0]["FrameIndex"])
)

legend_ranges = config.get("legend_ranges", {})
animation_legend_ranges = config.get("animation_legend_ranges", {})
damage_spectrum_name = "DAMAGE_DYNAMIC_10"
damage_colors = (
    "#F2F2F2", "#D9E8F5", "#B7D4EA", "#7BC8B8", "#2FBF71",
    "#B7DD3B", "#F2D13D", "#E85B2A", "#CC1F2F", "#FF0000",
)
if damage_spectrum_name not in session.spectrums:
    session.Spectrum(name=damage_spectrum_name, colors=damage_colors)

session.graphicsOptions.setValues(
    backgroundStyle=SOLID,
    backgroundColor="#FFFFFF",
    backgroundBottomColor="#FFFFFF",
)
session.printOptions.setValues(
    rendition=COLOR, vpDecorations=OFF, vpBackground=ON, compass=OFF
)
if config.get("require_fixed_legends"):
    # Per-image palette reduction can change the printed legend colors across models.
    session.printOptions.setValues(reduceColors=OFF)
session.pngOptions.setValues(imageSize=image_size_setting)
viewport.viewportAnnotationOptions.setValues(
    triad=OFF, legend=ON, title=OFF, state=OFF, annotations=OFF, compass=OFF
)
viewport.view.setProjection(projection=PARALLEL)
viewport.odbDisplay.commonOptions.setValues(renderStyle=SHADED, visibleEdges=FREE)


def replace_longitudinal_group():
    grouped = {}
    for instance_name, element_label in longitudinal:
        grouped.setdefault(instance_name, []).append(element_label)
    first = True
    for instance_name, labels in sorted(grouped.items()):
        leaf = dgo.LeafFromElementLabels(
            partInstanceName=instance_name,
            elementLabels=tuple(str(value) for value in sorted(labels)),
        )
        if first:
            viewport.odbDisplay.displayGroup.replace(leaf=leaf)
            first = False
        else:
            viewport.odbDisplay.displayGroup.add(leaf=leaf)
    if first:
        raise RuntimeError("Numeric cache contains no longitudinal rebar elements")


def primary_variable(variable, refinement):
    output_position = NODAL if variable == "U" else INTEGRATION_POINT
    if refinement is None:
        viewport.odbDisplay.setPrimaryVariable(
            variableLabel=variable, outputPosition=output_position
        )
    else:
        viewport.odbDisplay.setPrimaryVariable(
            variableLabel=variable,
            outputPosition=output_position,
            refinement=refinement,
        )


applied_legends = {"static": {}, "animation": {}}
scanned_sequences = {name: set(indices) for name, indices in config.get("legend_scan_sequences", {}).items()}


def check_member_scan(spec, item, ranges, kind):
    name = spec["name"]
    rule = ranges.get(name)
    if not config.get("require_fixed_legends") or not rule or rule.get("source") == "comparison_group_manual_override":
        return
    if int(item["SequenceIndex"]) not in scanned_sequences.get(name, ()):
        raise ValueError("组 {0}，模型 {1}，变量 {2}（{3}），序号 {4} 有场输出，但未参与组色标计算。请强制重扫或填写手动上下限。".format(
            config["comparison_group"], os.path.basename(odb_path), name, kind, item["SequenceIndex"]))


def apply_limits(spec, ranges, kind):
    name = spec["name"]
    limits = ranges.get(name)
    context = "组 {0}，模型 {1}，变量 {2}（{3}）".format(
        config["comparison_group"], os.path.basename(odb_path), name,
        "静态云图" if kind == "static" else "动画")
    options = viewport.odbDisplay.contourOptions
    if spec["variable"] in ("DAMAGET", "DAMAGEC"):
        style = dict(contourStyle=DISCRETE, numIntervals=10, spectrum=damage_spectrum_name,
                     outsideLimitsMode=SPECIFY, outsideLimitsBelowColor="#F2F2F2", outsideLimitsAboveColor="#FF0000")
    else:
        style = dict(contourStyle=CONTINUOUS, numIntervals=12, spectrum="Rainbow", outsideLimitsMode=SPECTRUM)
    if limits is None:
        if config.get("require_fixed_legends"):
            raise ValueError(context + "缺少组色标。请强制重扫范围，或在“图例范围”中填写手动上下限。")
        options.setValues(contourType=BANDED, intervalType=UNIFORM, contourEdges=OFF,
                          minAutoCompute=ON, maxAutoCompute=ON, **style)
        applied_legends[kind][name] = {"mode": "auto"}
        return
    try:
        minimum, maximum = float(limits["min"]), float(limits["max"])
        if not (math.isfinite(minimum) and math.isfinite(maximum) and minimum < maximum):
            raise ValueError("range")
    except (TypeError, KeyError, ValueError, OverflowError):
        raise ValueError(context + "的色标上下限无效。请重新预扫描或修正手动范围。")
    options.setValues(contourType=BANDED, intervalType=UNIFORM, contourEdges=OFF,
                      minAutoCompute=OFF, minValue=minimum, maxAutoCompute=OFF, maxValue=maximum, **style)
    actual_min, actual_max = float(options.minValue), float(options.maxValue)
    if not (math.isclose(actual_min, minimum, rel_tol=1e-6) and math.isclose(actual_max, maximum, rel_tol=1e-6)):
        raise ValueError(context + "的视口色标与设定值不一致。")
    applied_legends[kind][name] = {"mode": "fixed", "min": actual_min, "max": actual_max}


def set_static_limits(spec):
    apply_limits(spec, legend_ranges, "static")


def set_animation_limits(spec):
    apply_limits(spec, animation_legend_ranges, "animation")


def legend_mode(kind, fixed_mode):
    entries = applied_legends[kind]
    if not entries:
        return "not_rendered"
    modes = {entry["mode"] for entry in entries.values()}
    if modes == {"fixed"}:
        return fixed_mode
    return "auto" if modes == {"auto"} else "mixed_fixed_and_auto"


def set_soil_view():
    view_cut_name = "Y-Plane"
    if view_cut_name in viewport.odbDisplay.viewCuts:
        soil_cut = viewport.odbDisplay.viewCuts[view_cut_name]
    else:
        soil_cut = viewport.odbDisplay.ViewCut(
            name=view_cut_name,
            shape=PLANE,
            origin=(0.0, float(settings["soil_section_coordinate"]), 0.0),
            normal=(0.0, 1.0, 0.0),
            axis2=(0.0, 0.0, 1.0),
            followDeformation=OFF,
        )
    soil_cut.setValues(
        origin=(0.0, float(settings["soil_section_coordinate"]), 0.0),
        normal=(0.0, 1.0, 0.0),
        axis2=(0.0, 0.0, 1.0),
        followDeformation=OFF,
        showModelAboveCut=OFF,
        showModelBelowCut=ON,
        showModelOnCut=ON,
        showFreeBodyCut=OFF,
    )
    viewport.odbDisplay.setValues(viewCut=ON, viewCutNames=(view_cut_name,))
    viewport.odbDisplay.viewCutOptions.setValues(
        displaySlicing=OFF,
        useBelowOptions=OFF,
        useOnOptions=OFF,
        useAboveOptions=OFF,
    )
    viewport.view.setViewpoint(
        viewVector=(0.0, 1.0, 0.0), cameraUpVector=(0.0, 0.0, 1.0)
    )


specs = (
    {"name": "PILE_U_MAG", "set": config["pile_display_set"], "variable": "U", "refinement": (INVARIANT, "Magnitude")},
    {"name": "PILE_CON_S_MISES", "set": config["pile_concrete_set"], "variable": "S", "refinement": (INVARIANT, "Mises")},
    {"name": "PILE_STEEL_S_MISES", "set": config.get("pile_steel_set", ""), "variable": "S", "refinement": (INVARIANT, "Mises")},
    {"name": "PILE_CON_DAMAGET", "set": config["pile_concrete_set"], "variable": "DAMAGET", "refinement": None},
    {"name": "PILE_CON_DAMAGEC", "set": config["pile_concrete_set"], "variable": "DAMAGEC", "refinement": None},
    {"name": "SOIL_PEEQ_XZ", "set": config["soil_set"], "variable": "PEEQ", "refinement": None, "soil": True},
    {"name": "SOIL_PEMAG_XZ", "set": config["soil_set"], "variable": "PEMAG", "refinement": None, "soil": True},
    {"name": "SOIL_S33_XZ", "set": config["soil_set"], "variable": "S", "refinement": (COMPONENT, "S33"), "soil": True},
    {"name": "SOIL_S_MISES_XZ", "set": config["soil_set"], "variable": "S", "refinement": (INVARIANT, "Mises"), "soil": True},
    {"name": "REBAR_LONG_S_MISES_UNDEFORMED", "variable": "S", "refinement": (INVARIANT, "Mises"), "longitudinal": True, "undeformed": True},
    {"name": "REBAR_LONG_S11_UNDEFORMED", "variable": "S", "refinement": (COMPONENT, "S11"), "longitudinal": True, "undeformed": True},
)


specs = tuple(spec for spec in specs if not (
    spec.get("longitudinal") and config.get("reinforcement_mode", "required") == "none"
))


def render(spec):
    if spec.get("longitudinal") and config.get("reinforcement_mode", "required") == "none":
        return
    if not spec.get("longitudinal") and not spec.get("set"):
        return
    folder = os.path.join(frame_root, spec["name"])
    os.makedirs(folder, exist_ok=True)
    viewport.odbDisplay.setValues(viewCut=OFF)
    if spec.get("longitudinal"):
        replace_longitudinal_group()
    else:
        viewport.odbDisplay.displayGroup.replace(
            leaf=dgo.LeafFromElementSets(elementSets=(spec["set"],))
        )
    if spec.get("soil"):
        set_soil_view()
    else:
        viewport.odbDisplay.setValues(viewCut=OFF)
        viewport.view.setViewpoint(
            viewVector=tuple(float(value) for value in settings["camera_view_vector"]),
            cameraUpVector=tuple(float(value) for value in settings["camera_up_vector"]),
        )
    state = (CONTOURS_ON_UNDEF,) if spec.get("undeformed") else (CONTOURS_ON_DEF,)
    written = []
    render_timeline = full_timeline
    for animation_index, item in enumerate(render_timeline):
        step_index = int(item["StepIndex"])
        frame_index = int(item["FrameIndex"])
        frame = list(odb.steps.values())[step_index].frames[frame_index]
        if spec["variable"] not in frame.fieldOutputs:
            continue
        viewport.odbDisplay.setFrame(step=step_index, frame=frame_index)
        if not written:
            primary_variable(spec["variable"], spec.get("refinement"))
            viewport.odbDisplay.display.setValues(plotState=state)
            viewport.view.fitView()
        check_member_scan(spec, item, animation_legend_ranges, "动画")
        set_animation_limits(spec)
        base = os.path.join(
            folder,
            "{0:04d}_{1}_F{2:04d}".format(
                animation_index, item["StepName"], frame_index
            ),
        )
        try:
            session.printToFile(fileName=base, format=PNG, canvasObjects=(viewport,))
            if config.get("render_request_id") and not os.path.getsize(base + ".png"):
                raise IOError("Empty frame image")
            written.append(base + ".png")
        except Exception:
            if config.get("render_request_id"):
                raise
            log("RENDER FAILED {0} {1}\n{2}".format(
                spec["name"], animation_index, traceback.format_exc()
            ))
    static_item = selected_timeline[-1]
    step_index = int(static_item["StepIndex"])
    frame_index = int(static_item["FrameIndex"])
    static_frame = list(odb.steps.values())[step_index].frames[frame_index]
    if spec["variable"] in static_frame.fieldOutputs:
        viewport.odbDisplay.setFrame(step=step_index, frame=frame_index)
        check_member_scan(spec, static_item, legend_ranges, "静态云图")
        set_static_limits(spec)
        static_base = os.path.join(contour_dir, spec["name"] + "_LAST")
        try:
            session.printToFile(
                fileName=static_base,
                format=PNG,
                canvasObjects=(viewport,),
            )
            if config.get("render_request_id") and not os.path.getsize(static_base + ".png"):
                raise IOError("Empty static contour image")
        except Exception:
            if config.get("render_request_id"):
                raise
            log("STATIC RENDER FAILED {0}\n{1}".format(
                spec["name"], traceback.format_exc()
            ))
    log("RENDER {0}: {1} frames".format(spec["name"], len(written)))


for spec in specs:
    render(spec)

if config.get("render_request_id") and not (applied_legends["static"] or applied_legends["animation"]):
    raise RuntimeError("当前模型和帧均无可绘制的场输出：" + odb_path)
metadata_path = os.path.join(output_dir, "metadata.json")
if os.path.isfile(metadata_path):
    with open(metadata_path, "r", encoding="utf-8") as stream:
        metadata = json.load(stream)
else:
    metadata = {}
metadata.update(
    {
        "comparison_group": config["comparison_group"],
        "reinforcement_mode": config.get("reinforcement_mode", "required"),
        "legend_ranges": legend_ranges,
        "contour_sequences": [spec["name"] for spec in specs if spec["name"] in applied_legends["animation"]],
        "soil_view_vector": [0.0, 1.0, 0.0],
        "soil_camera_up_vector": [0.0, 0.0, 1.0],
        "numeric_cache_source": source_output_dir,
        "render_viewport_mm": list(render_viewport_mm),
        "image_size_unit": image_size_unit,
        "requested_image_size": [image_width, image_height],
        "animation_legend_mode": legend_mode("animation", "comparison_group_full_timeline_fixed"),
        "animation_legend_ranges": animation_legend_ranges,
        "static_contour_legend_mode": legend_mode("static", "comparison_group_fixed_selected_frames"),
    }
)
odb.close()
metadata["applied_legend_ranges"] = applied_legends
if config.get("render_request_id"):
    metadata["group_render_receipt"] = {"request_id": config["render_request_id"], "status": "succeeded"}
with open(metadata_path, "w", encoding="utf-8") as stream:
    json.dump(metadata, stream, ensure_ascii=False, indent=2)
log("GROUP RENDER COMPLETE")
