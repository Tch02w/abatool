from __future__ import print_function

from abaqus import session
from abaqusConstants import *
import bisect
import builtins
import csv
import json
import math
import os
import re
import sys
import traceback
import visualization
import displayGroupOdbToolset as dgo


def flatten(groups):
    for group in groups:
        try:
            for item in group:
                yield item
        except TypeError:
            yield group


def write_csv(path, headers, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def scalar(value):
    data = value.data
    try:
        return float(data)
    except (TypeError, ValueError):
        return float(data[0])


def vector_sum(values, width=3):
    output = [0.0] * width
    for value in values:
        data = value.data
        for index in range(min(width, len(data))):
            output[index] += float(data[index])
    return output


def safe_name(value):
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in value)


arguments = sys.argv[1:]
if "--" in arguments:
    arguments = arguments[arguments.index("--") + 1 :]
if not arguments:
    raise RuntimeError("Usage: abaqus cae noGUI=extract_job.py -- job_config.json")

config_path = os.path.abspath(arguments[0])
with open(config_path, "r", encoding="utf-8") as stream:
    config = json.load(stream)

odb_path = os.path.abspath(config["odb_path"])
output_dir = os.path.abspath(config["output_dir"])
data_dir = os.path.join(output_dir, "data")
history_output_dir = os.path.join(output_dir, "History_Output")
rebar_dir = os.path.join(output_dir, "rebar")
freebody_dir = os.path.join(output_dir, "freebody")
frame_root = os.path.join(output_dir, "frames")
contour_dir = os.path.join(output_dir, "contours")
render_outputs = bool(config.get("render_outputs", True))
directories = [
    output_dir,
    data_dir,
    history_output_dir,
    rebar_dir,
    freebody_dir,
]
if render_outputs:
    directories.extend([frame_root, contour_dir])
for directory in directories:
    os.makedirs(directory, exist_ok=True)
log_path = os.path.join(output_dir, "abaqus_worker.log")


def log(message):
    text = str(message)
    print(text)
    with open(log_path, "a", encoding="utf-8") as stream:
        stream.write(text + "\n")


with open(log_path, "w", encoding="utf-8") as stream:
    stream.write("Abaqus ODB worker started\n")

settings = config["settings"]
animation_legend_ranges = config.get("animation_legend_ranges", {})
start_step_name = config["start_step"]
end_step_name = config["end_step"]
load_set_name = config["load_set"]
pile_display_set_name = config["pile_display_set"]
concrete_set_name = config["pile_concrete_set"]
soil_set_name = config["soil_set"]
rebar_set_name = config["rebar_set"]
longitudinal_material_name = str(
    config.get("longitudinal_material", "HRB400")
).strip()
if not longitudinal_material_name:
    raise RuntimeError("longitudinal_material must not be blank")
bar_diameter_mm = float(config["rebar_diameter_mm"])
bar_area_mm2 = math.pi * bar_diameter_mm ** 2 / 4.0
orientation_threshold = float(settings["longitudinal_orientation_threshold"])
cut_count = int(settings["axial_cut_count"])
prefracture_index = int(config.get("prefracture_sequence_index", -1))
full_freebody = bool(config.get("full_timehistory_freebody", False))
rebar_method = str(config.get("rebar_method", "element_cut")).strip().lower()
if rebar_method not in ("element_cut", "legacy_interpolation"):
    raise RuntimeError("rebar_method must be element_cut or legacy_interpolation")
rebar_cut_tolerance_mm = abs(float(settings.get("rebar_cut_tolerance_mm", 1.0e-4)))
configured_expected_rebar_count = int(
    config.get("expected_longitudinal_rebar_count", 0)
)
REBAR_SECTION_RULE = (
    "reference_geometry_[z_min,z_max)_with_physical_top_inclusive; "
    "S11*A_projected_to_global_Z_using_current_direction"
)
REBAR_INTERPOLATION_METHOD = (
    "element_centroid_depth_linear_with_end_element_constant"
)
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
    "ODB PostProcessor",
    image_size_unit,
    image_width,
    image_height,
)
viewport.makeCurrent()
odb = session.openOdb(name=odb_path, readOnly=True)
viewport.setValues(displayedObject=odb)
assembly = odb.rootAssembly
step_names = list(odb.steps.keys())
start_step_index = step_names.index(start_step_name)
end_step_index = step_names.index(end_step_name)

time_offsets = {}
running_time = 0.0
for step_name in step_names:
    time_offsets[step_name] = running_time
    frames = odb.steps[step_name].frames
    if frames:
        running_time += float(frames[-1].frameValue)

timeline = []
sequence_index = 0
for step_index in range(start_step_index, end_step_index + 1):
    step_name = step_names[step_index]
    for frame_index, frame in enumerate(odb.steps[step_name].frames):
        if step_index > start_step_index and frame_index == 0:
            continue
        timeline.append(
            {
                "SequenceIndex": sequence_index,
                "StepIndex": step_index,
                "StepName": step_name,
                "FrameIndex": frame_index,
                "IncrementNumber": int(frame.incrementNumber),
                "StepTime": float(frame.frameValue),
                "TotalTime": time_offsets[step_name] + float(frame.frameValue),
                "frame": frame,
            }
        )
        sequence_index += 1

timeline_headers = [
    "SequenceIndex",
    "StepIndex",
    "StepName",
    "FrameIndex",
    "IncrementNumber",
    "StepTime",
    "TotalTime",
]
write_csv(
    os.path.join(data_dir, "timeline_alignment.csv"),
    timeline_headers,
    [{name: item[name] for name in timeline_headers} for item in timeline],
)

load_region = assembly.nodeSets[load_set_name]
load_rows = []
for item in timeline:
    frame = item["frame"]
    values = dict((name, [0.0, 0.0, 0.0]) for name in ("U", "UR", "RF", "RM"))
    for variable in values:
        if variable in frame.fieldOutputs:
            subset = frame.fieldOutputs[variable].getSubset(region=load_region)
            values[variable] = vector_sum(subset.values)
    row = dict((name, item[name]) for name in timeline_headers)
    row.update(
        {
            "U1_mm": values["U"][0],
            "U2_mm": values["U"][1],
            "U3_mm": values["U"][2],
            "UR1_rad": values["UR"][0],
            "UR2_rad": values["UR"][1],
            "UR3_rad": values["UR"][2],
            "RF1_N": values["RF"][0],
            "RF2_N": values["RF"][1],
            "RF3_N": values["RF"][2],
            "RM1_Nmm": values["RM"][0],
            "RM2_Nmm": values["RM"][1],
            "RM3_Nmm": values["RM"][2],
        }
    )
    load_rows.append(row)
write_csv(os.path.join(data_dir, "load_point_raw.csv"), list(load_rows[0].keys()), load_rows)


def history_value_at(data, target_time):
    """Linearly align one History Output series to a field-output frame time."""

    if not data:
        return None
    times = [float(point[0]) for point in data]
    position = bisect.bisect_left(times, float(target_time))
    if position <= 0:
        return float(data[0][1])
    if position >= len(data):
        return float(data[-1][1])
    right_time, right_value = data[position]
    left_time, left_value = data[position - 1]
    right_time = float(right_time)
    left_time = float(left_time)
    if abs(right_time - float(target_time)) <= 1.0e-10:
        return float(right_value)
    if abs(right_time - left_time) <= 1.0e-14:
        return float(right_value)
    ratio = (float(target_time) - left_time) / (right_time - left_time)
    return float(left_value) + ratio * (float(right_value) - float(left_value))


def contact_history_column(output_name):
    """Return a stable column for root-key or pile-soil contact histories."""

    upper = str(output_name).upper()
    variable = upper.strip().split()[0] if upper.strip() else ""
    key_match = re.search(r"KEY(?:[_\- ]+\d+)+", upper)
    if key_match and variable in ("CFN1", "CFN2", "CFN3", "CFNM"):
        key_name = re.sub(r"[_\- ]+", "_", key_match.group(0))
        return "{0}_{1}_N".format(key_name, variable)
    if (
        not key_match
        and "PILE" in upper
        and variable in (
            "CFN1", "CFN2", "CFN3", "CFNM",
            "CFS1", "CFS2", "CFS3", "CFSM",
        )
    ):
        return "PILE_{0}_N".format(variable)
    if "KEY" in upper:
        return str(output_name).strip()
    return ""


history_sources_by_step = {}
history_source_metadata = []
all_history_columns = set()
for step_index in range(start_step_index, end_step_index + 1):
    step_name = step_names[step_index]
    step = odb.steps[step_name]
    step_sources = {}
    for region_name, region in step.historyRegions.items():
        for output_name, history_output in region.historyOutputs.items():
            column = contact_history_column(output_name)
            if not column:
                continue
            series = [
                (float(point[0]), float(point[1]))
                for point in history_output.data
            ]
            if not series:
                continue
            step_sources.setdefault(column, []).append(series)
            all_history_columns.add(column)
            history_source_metadata.append(
                {
                    "step": step_name,
                    "column": column,
                    "region": str(region_name),
                    "region_description": str(
                        getattr(region, "description", "")
                    ),
                    "history_output": str(output_name),
                    "point_count": len(series),
                }
            )
    history_sources_by_step[step_name] = step_sources

contact_history_rows = []
history_columns = sorted(all_history_columns)
if history_columns:
    for item in timeline:
        row = dict((name, item[name]) for name in timeline_headers)
        step_sources = history_sources_by_step.get(item["StepName"], {})
        for column in history_columns:
            values = []
            for series in step_sources.get(column, []):
                value = history_value_at(series, item["StepTime"])
                if value is not None:
                    values.append(value)
            row[column] = sum(values) if values else ""
        contact_history_rows.append(row)
    write_csv(
        os.path.join(history_output_dir, "contact_history_raw.csv"),
        timeline_headers + history_columns,
        contact_history_rows,
    )
with open(
    os.path.join(history_output_dir, "contact_history_sources.json"),
    "w",
    encoding="utf-8",
) as stream:
    json.dump(
        {
            "load_direction": str(config.get("load_direction", "")),
            "columns": history_columns,
            "sources": history_source_metadata,
        },
        stream,
        ensure_ascii=False,
        indent=2,
    )


def region_elements(region):
    groups = region.elements
    instance_names = list(getattr(region, "instanceNames", ()))
    if instance_names and len(instance_names) == len(groups):
        for group_index, group in enumerate(groups):
            for element in group:
                yield instance_names[group_index], element
    else:
        for element in flatten(groups):
            instance_name = getattr(element, "instanceName", "")
            if not instance_name:
                for candidate_name, instance in assembly.instances.items():
                    try:
                        instance.getElementFromLabel(element.label)
                        instance_name = candidate_name
                        break
                    except Exception:
                        pass
            yield instance_name, element


rebar_region = assembly.elementSets[rebar_set_name]
node_maps = {}
element_geometry = {}
parent = {}
element_section_data = {}


def collect_element_section_data():
    """Map instance/label to ODB truss section material and area when exposed."""

    output = {}
    for instance_name, instance in assembly.instances.items():
        for assignment in getattr(instance, "sectionAssignments", ()):
            section_name = str(getattr(assignment, "sectionName", ""))
            section = None
            if section_name:
                try:
                    section = odb.sections[section_name]
                except Exception as error:
                    log(
                        "ODB section read failed for {0}/{1}: {2}".format(
                            instance_name, section_name, error
                        )
                    )
            material = str(getattr(section, "material", "")) if section else ""
            area = getattr(section, "area", None) if section else None
            try:
                area = float(area)
            except (TypeError, ValueError):
                area = None
            try:
                assigned_elements = flatten(assignment.region.elements)
                for assigned_element in assigned_elements:
                    output[(instance_name, assigned_element.label)] = {
                        "section_name": section_name,
                        "material": material,
                        "area": area if area is not None and area > 0.0 else None,
                    }
            except Exception as error:
                log(
                    "Section assignment read failed for {0}/{1}: {2}".format(
                        instance_name, section_name, error
                    )
                )
    return output


element_section_data = collect_element_section_data()


def find(node):
    parent.setdefault(node, node)
    while parent[node] != node:
        parent[node] = parent[parent[node]]
        node = parent[node]
    return node


def union(first, second):
    root_first = find(first)
    root_second = find(second)
    if root_first != root_second:
        parent[root_second] = root_first


for instance_name, element in region_elements(rebar_region):
    if not instance_name or not element.type.upper().startswith("T3D2"):
        continue
    key = (instance_name, element.label)
    section_data = element_section_data.get(key, {})
    section_category_name = str(
        getattr(getattr(element, "sectionCategory", None), "name", "")
    )
    section_material_name = str(section_data.get("material", ""))
    material_identity = section_material_name or section_category_name
    if longitudinal_material_name.upper() not in material_identity.upper():
        continue
    if instance_name not in node_maps:
        node_maps[instance_name] = dict(
            (node.label, tuple(float(value) for value in node.coordinates))
            for node in assembly.instances[instance_name].nodes
        )
    nodes = node_maps[instance_name]
    coordinates = [nodes[label] for label in element.connectivity]
    first = coordinates[0]
    last = coordinates[-1]
    dx = last[0] - first[0]
    dy = last[1] - first[1]
    dz = last[2] - first[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    ratio = abs(dz) / length if length else 0.0
    if ratio < orientation_threshold:
        continue
    first_node = (instance_name, element.connectivity[0])
    last_node = (instance_name, element.connectivity[-1])
    union(first_node, last_node)
    centroid = tuple(
        builtins.sum(point[axis] for point in coordinates) / float(len(coordinates))
        for axis in range(3)
    )
    section_area = section_data.get("area")
    if section_area is None:
        section_area = bar_area_mm2
        area_source = "configured_uniform_diameter_fallback"
    else:
        area_source = "odb_section:{0}".format(
            section_data.get("section_name", "")
        )
    element_geometry[key] = {
        "instance": instance_name,
        "label": element.label,
        "centroid": centroid,
        "length": length,
        "ratio": ratio,
        "nodes": (first_node, last_node),
        "reference_first": first,
        "reference_last": last,
        "section_name": section_data.get("section_name", ""),
        "section_material": section_material_name,
        "area_mm2": float(section_area),
        "area_source": area_source,
        "equivalent_diameter_mm": math.sqrt(4.0 * float(section_area) / math.pi),
    }

if not element_geometry:
    raise RuntimeError(
        "No longitudinal T3D2 elements with material {0} were found in {1}".format(
            longitudinal_material_name, rebar_set_name
        )
    )

fallback_area_elements = [
    geometry
    for geometry in element_geometry.values()
    if geometry["area_source"] == "configured_uniform_diameter_fallback"
]
if fallback_area_elements:
    log(
        "REBAR AREA WARNING: {0}/{1} longitudinal T3D2 elements have no "
        "readable ODB truss-section area; using configured uniform diameter "
        "{2:g} mm (area {3:g} model-area units).".format(
            len(fallback_area_elements),
            len(element_geometry),
            bar_diameter_mm,
            bar_area_mm2,
        )
    )

components = {}
for geometry in element_geometry.values():
    root = find(geometry["nodes"][0])
    components.setdefault(root, []).append(geometry)
component_list = []
for root, geometries in components.items():
    x = builtins.sum(item["centroid"][0] for item in geometries) / len(geometries)
    y = builtins.sum(item["centroid"][1] for item in geometries) / len(geometries)
    component_list.append((math.atan2(y, x), root))
component_list.sort()
root_to_bar = dict((root, index + 1) for index, (_angle, root) in enumerate(component_list))
for geometry in element_geometry.values():
    geometry["bar_id"] = root_to_bar[find(geometry["nodes"][0])]

all_rebar_z = [item["centroid"][2] for item in element_geometry.values()]
rebar_node_z = []
for item in element_geometry.values():
    instance_nodes = node_maps[item["instance"]]
    for _instance_name, node_label in item["nodes"]:
        rebar_node_z.append(instance_nodes[node_label][2])
rebar_z_min = min(rebar_node_z)
rebar_z_max = max(rebar_node_z)
detected_rebar_count = len(component_list)
effective_expected_rebar_count = (
    configured_expected_rebar_count
    if configured_expected_rebar_count > 0
    else detected_rebar_count
)
expected_rebar_count_source = (
    "configured"
    if configured_expected_rebar_count > 0
    else "odb_detected_bar_count"
)
reference_rebar_nodes = {}
for geometry in element_geometry.values():
    for instance_name, node_label in geometry["nodes"]:
        reference_rebar_nodes[(instance_name, node_label)] = node_maps[
            instance_name
        ][node_label]


def merge_rebar_node_coordinates(reference, coordinate_values, displacement_values):
    """Resolve each node as COORD, reference + U, or reference, in that order."""

    resolved = {}
    counts = {
        "COORD": 0,
        "reference_plus_U": 0,
        "reference_geometry": 0,
    }
    for key, point in reference.items():
        if key in coordinate_values:
            resolved[key] = coordinate_values[key]
            counts["COORD"] += 1
        elif key in displacement_values:
            displacement = displacement_values[key]
            resolved[key] = tuple(
                float(point[axis]) + float(displacement[axis])
                for axis in range(3)
            )
            counts["reference_plus_U"] += 1
        else:
            resolved[key] = point
            counts["reference_geometry"] += 1
    active_sources = [
        name
        for name in ("COORD", "reference_plus_U", "reference_geometry")
        if counts[name] > 0
    ]
    source = (
        active_sources[0]
        if len(active_sources) == 1
        else "mixed:" + "+".join(active_sources)
    )
    return resolved, source, counts


def nodal_vector_values(frame, variable_name):
    """Read one nodal vector field for the configured rebar region."""

    if variable_name not in frame.fieldOutputs:
        return {}
    try:
        subset = frame.fieldOutputs[variable_name].getSubset(
            region=rebar_region, position=NODAL
        )
        values = {}
        for value in subset.values:
            values[(value.instance.name, value.nodeLabel)] = tuple(
                float(component) for component in value.data
            )
        return values
    except Exception as error:
        log("{0} nodal read failed: {1}".format(variable_name, error))
        return {}


def current_rebar_node_coordinates(frame):
    """Read current nodes with an explicit, per-node fallback chain."""

    coordinate_values = nodal_vector_values(frame, "COORD")
    needs_fallback = any(
        key not in coordinate_values for key in reference_rebar_nodes
    )
    displacement_values = (
        nodal_vector_values(frame, "U") if needs_fallback else {}
    )
    return merge_rebar_node_coordinates(
        reference_rebar_nodes, coordinate_values, displacement_values
    )


def owns_cut(first, last, elevation):
    """Half-open ownership avoids counting both elements at a shared node."""

    z_min = min(first[2], last[2])
    z_max = max(first[2], last[2])
    if z_max - z_min <= rebar_cut_tolerance_mm:
        return False
    if elevation < z_min - rebar_cut_tolerance_mm:
        return False
    if elevation > z_max + rebar_cut_tolerance_mm:
        return False
    if elevation < z_max - rebar_cut_tolerance_mm:
        return True
    return abs(z_max - rebar_z_max) <= rebar_cut_tolerance_mm and abs(elevation - z_max) <= rebar_cut_tolerance_mm


def project_to_pile_axis(force, first, last):
    """Project onto global Z without letting T3D2 connectivity reverse signs."""

    dx = last[0] - first[0]
    dy = last[1] - first[1]
    dz = last[2] - first[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    return 0.0 if length <= 0.0 else force * abs(dz) / length


def rebar_section_force(sequence, elevation):
    """Sum the unique longitudinal T3D2 elements intersected by one FBC."""

    frame_data = rebar_section_by_sequence[sequence]
    selected_candidates = {}
    duplicate_count = 0
    for key, geometry in element_geometry.items():
        if not owns_cut(geometry["reference_first"], geometry["reference_last"], elevation):
            continue
        bar_id = geometry["bar_id"]
        if bar_id in selected_candidates:
            duplicate_count += 1
            continue
        selected_candidates[bar_id] = key

    selected_forces = {}
    missing_stress = []
    for bar_id, key in selected_candidates.items():
        geometry = element_geometry[key]
        if key not in frame_data["tension_force"]:
            missing_stress.append("{0}:{1}".format(key[0], key[1]))
            continue
        tension_force = frame_data["tension_force"][key]
        first_node, last_node = geometry["nodes"]
        current = frame_data["current_nodes"]
        first = current[first_node]
        last = current[last_node]
        selected_forces[bar_id] = project_to_pile_axis(
            tension_force, first, last
        )
    tension_force = builtins.sum(selected_forces.values())
    return (
        tension_force,
        len(selected_candidates),
        duplicate_count,
        frame_data["coordinate_source"],
        frame_data["coordinate_source_counts"],
        len(missing_stress),
        sorted(missing_stress),
    )


rebar_detailed_path = os.path.join(rebar_dir, "rebar_element_stress_force_timehistory.csv")
rebar_headers = timeline_headers + [
    "BarID",
    "InstanceName",
    "ElementLabel",
    "CentroidX_mm",
    "CentroidY_mm",
    "CentroidZ_mm",
    "ElementLength_mm",
    "AbsDzOverLength",
    "S11_MPa",
    "S_Mises_MPa",
    "BarDiameter_mm",
    "BarArea_mm2",
    "BarAreaSource",
    "SectionName",
    "SectionMaterial",
    "ElementAxialForce_TensionPositive_N",
    "ElementAxialForce_CompressionPositive_N",
]
rebar_level_headers = timeline_headers + [
    "CentroidZ_mm",
    "ElementCount",
    "S11_Min_MPa",
    "S11_Mean_MPa",
    "S11_Max_MPa",
    "SteelForce_TensionPositive_N",
    "SteelForce_CompressionPositive_N",
]
rebar_level_rows = []
rebar_force_by_sequence = {}
rebar_section_by_sequence = {}
with open(rebar_detailed_path, "w", newline="", encoding="utf-8-sig") as stream:
    writer = csv.DictWriter(stream, fieldnames=rebar_headers)
    writer.writeheader()
    for item in timeline:
        frame = item["frame"]
        element_stresses = {}
        current_nodes, coordinate_source, coordinate_source_counts = (
            current_rebar_node_coordinates(frame)
        )
        if "S" in frame.fieldOutputs:
            subset = frame.fieldOutputs["S"].getSubset(region=rebar_region, position=INTEGRATION_POINT)
            for value in subset.values:
                key = (value.instance.name, value.elementLabel)
                if key in element_geometry:
                    element_stresses.setdefault(key, []).append(scalar(value))
        by_z = {}
        tension_force_by_element = {}
        for key, stresses in element_stresses.items():
            stress = builtins.sum(stresses) / float(len(stresses))
            geometry = element_geometry[key]
            x, y, z = geometry["centroid"]
            row = dict((name, item[name]) for name in timeline_headers)
            row.update(
                {
                    "BarID": geometry["bar_id"],
                    "InstanceName": key[0],
                    "ElementLabel": key[1],
                    "CentroidX_mm": x,
                    "CentroidY_mm": y,
                    "CentroidZ_mm": z,
                    "ElementLength_mm": geometry["length"],
                    "AbsDzOverLength": geometry["ratio"],
                    "S11_MPa": stress,
                    "S_Mises_MPa": abs(stress),
                    "BarDiameter_mm": geometry["equivalent_diameter_mm"],
                    "BarArea_mm2": geometry["area_mm2"],
                    "BarAreaSource": geometry["area_source"],
                    "SectionName": geometry["section_name"],
                    "SectionMaterial": geometry["section_material"],
                    "ElementAxialForce_TensionPositive_N": stress * geometry["area_mm2"],
                    "ElementAxialForce_CompressionPositive_N": -stress * geometry["area_mm2"],
                }
            )
            writer.writerow(row)
            tension_force_by_element[key] = stress * geometry["area_mm2"]
            by_z.setdefault(round(z, 8), []).append(
                (stress, geometry["area_mm2"])
            )
        sequence_points = []
        for z in sorted(by_z):
            stress_areas = by_z[z]
            stresses = [value[0] for value in stress_areas]
            sum_stress = builtins.sum(stresses)
            force_tension = builtins.sum(
                stress * area for stress, area in stress_areas
            )
            force_compression = -force_tension
            level_row = dict((name, item[name]) for name in timeline_headers)
            level_row.update(
                {
                    "CentroidZ_mm": z,
                    "ElementCount": len(stresses),
                    "S11_Min_MPa": min(stresses),
                    "S11_Mean_MPa": sum_stress / len(stresses),
                    "S11_Max_MPa": max(stresses),
                    "SteelForce_TensionPositive_N": force_tension,
                    "SteelForce_CompressionPositive_N": force_compression,
                }
            )
            rebar_level_rows.append(level_row)
            sequence_points.append((z, force_compression))
        rebar_force_by_sequence[item["SequenceIndex"]] = sequence_points
        rebar_section_by_sequence[item["SequenceIndex"]] = {
            "tension_force": tension_force_by_element,
            "current_nodes": current_nodes,
            "coordinate_source": coordinate_source,
            "coordinate_source_counts": coordinate_source_counts,
        }

write_csv(
    os.path.join(rebar_dir, "rebar_force_by_element_level_timehistory.csv"),
    rebar_level_headers,
    rebar_level_rows,
)
area_values = sorted(
    set(round(float(item["area_mm2"]), 12) for item in element_geometry.values())
)
area_source_counts = {}
for item in element_geometry.values():
    area_source_counts[item["area_source"]] = (
        area_source_counts.get(item["area_source"], 0) + 1
    )
with open(os.path.join(rebar_dir, "rebar_metadata.json"), "w", encoding="utf-8") as stream:
    json.dump(
        {
            "method": rebar_method,
            # Compatibility aliases retained for existing cache/result readers.
            "legacy_method": REBAR_INTERPOLATION_METHOD,
            "element_cut_rule": REBAR_SECTION_RULE,
            "RebarSectionRule": REBAR_SECTION_RULE,
            "RebarInterpolationRule": REBAR_INTERPOLATION_METHOD,
            "RebarActiveRule": (
                REBAR_SECTION_RULE
                if rebar_method == "element_cut"
                else REBAR_INTERPOLATION_METHOD
            ),
            "longitudinal_material": longitudinal_material_name,
            "cut_tolerance_mm": rebar_cut_tolerance_mm,
            "projection": (
                "S11*A projected to global pile Z; nodal direction source "
                "priority is COORD, reference+U, then reference geometry"
            ),
            "odb_detected_bar_count": detected_rebar_count,
            "configured_expected_longitudinal_rebar_count": configured_expected_rebar_count,
            "effective_expected_longitudinal_rebar_count": effective_expected_rebar_count,
            "expected_longitudinal_rebar_count_source": expected_rebar_count_source,
            "longitudinal_element_count": len(element_geometry),
            "bar_diameter_mm": bar_diameter_mm,
            "bar_area_mm2": bar_area_mm2,
            "configured_fallback_bar_diameter_mm": bar_diameter_mm,
            "configured_fallback_bar_area_mm2": bar_area_mm2,
            "configured_area_assumption": (
                "uniform circular diameter; fallback only when an element's "
                "ODB truss-section area is unavailable"
            ),
            "bar_area_source_priority": (
                "odb instance.sectionAssignments -> odb.sections[sectionName].area; "
                "configured uniform diameter only when unavailable"
            ),
            "bar_area_source_counts": area_source_counts,
            "bar_area_values_model_units_squared": area_values,
            "bar_area_fallback_warning": bool(fallback_area_elements),
            "rebar_z_extent_mm": [rebar_z_min, rebar_z_max],
        },
        stream,
        ensure_ascii=False,
        indent=2,
    )

concrete_region = assembly.elementSets[concrete_set_name]
concrete_coordinates = []
for instance_name, element in region_elements(concrete_region):
    if not instance_name:
        continue
    instance = assembly.instances[instance_name]
    if instance_name not in node_maps:
        node_maps[instance_name] = dict(
            (node.label, tuple(float(value) for value in node.coordinates))
            for node in instance.nodes
        )
    for label in element.connectivity:
        concrete_coordinates.append(node_maps[instance_name][label])
pile_z_min = min(point[2] for point in concrete_coordinates)
pile_z_max = max(point[2] for point in concrete_coordinates)
ground_z = pile_z_max - float(settings["pile_head_above_ground_mm"])

targets = []
if full_freebody:
    targets = [("SEQ{0:04d}".format(item["SequenceIndex"]), item) for item in timeline]
else:
    targets.append(("LAST", timeline[-1]))
    if 0 <= prefracture_index < len(timeline) and prefracture_index != timeline[-1]["SequenceIndex"]:
        targets.append(("PRE_FRACTURE", timeline[prefracture_index]))

viewport.odbDisplay.setFrame(step=timeline[0]["StepIndex"], frame=timeline[0]["FrameIndex"])
viewport.odbDisplay.display.setValues(plotState=(UNDEFORMED,))
viewport.odbDisplay.displayGroup.replace(
    leaf=dgo.LeafFromElementSets(elementSets=(concrete_set_name,))
)
cut_name = "PILE_CON_XY_{0}".format(cut_count)
cut = viewport.odbDisplay.ViewCut(
    name=cut_name,
    shape=PLANE,
    origin=(0.0, 0.0, 0.5 * (pile_z_min + pile_z_max)),
    normal=(0.0, 0.0, 1.0),
    axis2=(1.0, 0.0, 0.0),
    followDeformation=OFF,
)
cut.setValues(showModelAboveCut=OFF, showModelBelowCut=ON, showModelOnCut=ON, showFreeBodyCut=ON)
viewport.odbDisplay.setValues(viewCut=ON, viewCutNames=(cut_name,))
epsilon = max(1.0, (pile_z_max - pile_z_min) / 1600.0)
viewport.odbDisplay.viewCutOptions.setValues(
    displaySlicing=ON,
    freeBodyCutThru=CURRENT_DISPLAY_GROUP,
    freeBodyStepThru=ACTIVE_CUT_RANGE,
    numCutFreeBody=cut_count,
    cutFreeBodyMin=cut.cutRange[0] + epsilon,
    cutFreeBodyMax=cut.cutRange[1] - epsilon,
    componentResolution=CSYS,
    csysName=GLOBAL,
)
session.freeBodyReportOptions.setValues(
    numDigits=10,
    forceThreshold=1.0e-12,
    momentThreshold=1.0e-12,
    numberFormat=SCIENTIFIC,
    reportFormat=COMMA_SEPARATED_VALUES,
    csysType=GLOBAL,
)


def interpolate_rebar(sequence, elevation):
    if elevation < rebar_z_min or elevation > rebar_z_max:
        return 0.0, "outside_rebar_extent_zero"
    points = rebar_force_by_sequence[sequence]
    if not points:
        return None, "missing_s11_points"
    elevations = [point[0] for point in points]
    if elevation <= elevations[0]:
        return points[0][1], "end_element_constant"
    if elevation >= elevations[-1]:
        return points[-1][1], "end_element_constant"
    right = bisect.bisect_right(elevations, elevation)
    z0, value0 = points[right - 1]
    z1, value1 = points[right]
    ratio = (elevation - z0) / (z1 - z0)
    return value0 + ratio * (value1 - value0), "linear_between_element_centroids"


concrete_rows = []
combined_rows = []
section_diagnostic_rows = []
rebar_force_failures = []
for label, item in targets:
    viewport.odbDisplay.setFrame(step=item["StepIndex"], frame=item["FrameIndex"])
    raw_path = os.path.join(freebody_dir, "freebody_{0}_raw.csv".format(label))
    session.writeFreeBodyReport(
        fileName=raw_path,
        append=OFF,
        step=item["StepIndex"],
        frame=item["FrameIndex"],
        stepFrame=SPECIFY,
        odb=odb,
    )
    frame_count = 0
    with open(raw_path, "r", encoding="utf-8-sig") as stream:
        for cut_index, raw in enumerate(csv.DictReader(stream), 1):
            elevation = float(raw["CutZ"])
            concrete_force = float(raw["Fz"])
            base = dict((name, item[name]) for name in timeline_headers)
            base.update(
                {
                    "Status": label,
                    "CutIndex": cut_index,
                    "Elevation_mm": elevation,
                    "DepthFromGround_mm": ground_z - elevation,
                    "ConcreteAxial_TensionPositive_N": concrete_force,
                    "ConcreteAxial_CompressionPositive_N": -concrete_force,
                    "Fx_N": float(raw["Fx"]),
                    "Fy_N": float(raw["Fy"]),
                    "Fz_N": concrete_force,
                    "Mx_Nmm": float(raw["Mx"]),
                    "My_Nmm": float(raw["My"]),
                    "Mz_Nmm": float(raw["Mz"]),
                }
            )
            concrete_rows.append(base)
            legacy_compression, legacy_rule = interpolate_rebar(
                item["SequenceIndex"], elevation
            )
            legacy_tension = (
                -legacy_compression if legacy_compression is not None else None
            )
            (
                section_available_tension,
                crossing_count,
                duplicate_count,
                coordinate_source,
                coordinate_source_counts,
                missing_s11_count,
                missing_s11_keys,
            ) = rebar_section_force(item["SequenceIndex"], elevation)
            inside_rebar_extent = (
                rebar_z_min - rebar_cut_tolerance_mm
                <= elevation
                <= rebar_z_max + rebar_cut_tolerance_mm
            )
            expected_for_cut = (
                effective_expected_rebar_count if inside_rebar_extent else ""
            )
            crossing_matches_expected = (
                crossing_count == effective_expected_rebar_count
                if inside_rebar_extent
                else ""
            )
            if inside_rebar_extent and not crossing_matches_expected:
                log(
                    "REBAR CUT WARNING {0} z={1:.6f}: {2} crossing elements, expected {3}".format(
                        label,
                        elevation,
                        crossing_count,
                        effective_expected_rebar_count,
                    )
                )
            if duplicate_count:
                log(
                    "REBAR CUT WARNING {0} z={1:.6f}: {2} duplicate crossing candidates".format(
                        label, elevation, duplicate_count
                    )
                )

            section_force_valid = (
                missing_s11_count == 0 and duplicate_count == 0
            )
            interpolation_force_valid = legacy_compression is not None
            force_result_valid = section_force_valid and interpolation_force_valid
            if missing_s11_count:
                failure = (
                    "{0} z={1:.6f}: missing S/S11 for {2}/{3} crossing T3D2 "
                    "elements ({4})"
                ).format(
                    label,
                    elevation,
                    missing_s11_count,
                    crossing_count,
                    ", ".join(missing_s11_keys),
                )
                rebar_force_failures.append(failure)
                log("REBAR S11 ERROR: " + failure)
            if duplicate_count:
                failure = (
                    "{0} z={1:.6f}: {2} ambiguous duplicate T3D2 crossing "
                    "candidates share an already selected longitudinal bar"
                ).format(label, elevation, duplicate_count)
                rebar_force_failures.append(failure)
                log("REBAR CUT ERROR: " + failure)
            elif inside_rebar_extent and not interpolation_force_valid:
                failure = "{0} z={1:.6f}: no S11 points available for interpolation".format(
                    label, elevation
                )
                rebar_force_failures.append(failure)
                log("REBAR S11 ERROR: " + failure)

            if force_result_valid:
                section_tension = section_available_tension
                active_tension = (
                    legacy_tension
                    if rebar_method == "legacy_interpolation"
                    else section_tension
                )
                pile_total_tension = concrete_force + active_tension
                balance_denominator = max(
                    abs(concrete_force), abs(active_tension), 1.0
                )
                balance_relative = abs(pile_total_tension) / balance_denominator
            else:
                section_tension = ""
                legacy_tension = ""
                legacy_compression = ""
                active_tension = ""
                pile_total_tension = ""
                balance_relative = ""

            active_rule = (
                legacy_rule
                if rebar_method == "legacy_interpolation"
                else REBAR_SECTION_RULE
            )
            combined = dict(base)
            combined.update(
                {
                    "RebarMethod": rebar_method,
                    "RebarAxial_Section_TensionPositive_N": section_tension,
                    "RebarAxial_Section_CompressionPositive_N": (
                        -section_tension if force_result_valid else ""
                    ),
                    "RebarAxial_Interpolated_TensionPositive_N": legacy_tension,
                    "RebarAxial_Interpolated_CompressionPositive_N": legacy_compression,
                    "PileTotalAxial_TensionPositive_N": pile_total_tension,
                    "PileTotalAxial_CompressionPositive_N": (
                        -pile_total_tension if force_result_valid else ""
                    ),
                    "RebarSectionRule": REBAR_SECTION_RULE,
                    "RebarInterpolationRule": legacy_rule,
                    "RebarActiveRule": active_rule,
                    "CrossingT3D2ElementCount": crossing_count,
                    "CrossingT3D2WithS11Count": crossing_count - missing_s11_count,
                    "MissingS11CrossingCount": missing_s11_count,
                    "MissingS11ElementKeys": ";".join(missing_s11_keys),
                    "RebarSectionForceValid": section_force_valid,
                    "RebarInterpolationForceValid": interpolation_force_valid,
                    "RebarForceResultValid": force_result_valid,
                    "RebarAxial_Section_AvailablePart_TensionPositive_N": section_available_tension,
                    "ExpectedLongitudinalRebarCount": expected_for_cut,
                    "ExpectedLongitudinalRebarCountSource": (
                        expected_rebar_count_source if inside_rebar_extent else ""
                    ),
                    "CrossingCountValidationApplicable": inside_rebar_extent,
                    "CrossingCountMatchesExpected": crossing_matches_expected,
                    "DuplicateCrossingCandidateCount": duplicate_count,
                    "RebarDirectionCoordinateSource": coordinate_source,
                    "RebarDirectionCOORDNodeCount": coordinate_source_counts.get(
                        "COORD", 0
                    ),
                    "RebarDirectionReferencePlusUNodeCount": coordinate_source_counts.get(
                        "reference_plus_U", 0
                    ),
                    "RebarDirectionReferenceNodeCount": coordinate_source_counts.get(
                        "reference_geometry", 0
                    ),
                    "AxialBalanceResidual_TensionPositive_N": pile_total_tension,
                    "AxialBalanceRelative": balance_relative,
                }
            )
            combined_rows.append(combined)
            section_diagnostic_rows.append(dict(combined))
            frame_count += 1
    if frame_count != cut_count:
        raise RuntimeError("{0} returned {1} cuts, expected {2}".format(label, frame_count, cut_count))
    log("FREEBODY {0}: {1} cuts".format(label, frame_count))

concrete_force_path = os.path.join(
    freebody_dir, "concrete_axial_force_time_aligned.csv"
)
pile_total_force_path = os.path.join(
    freebody_dir, "pile_total_axial_force_time_aligned.csv"
)
section_diagnostics_path = os.path.join(
    freebody_dir, "rebar_section_diagnostics.csv"
)
write_csv(
    concrete_force_path,
    list(concrete_rows[0].keys()),
    concrete_rows,
)
write_csv(
    section_diagnostics_path,
    list(section_diagnostic_rows[0].keys()),
    section_diagnostic_rows,
)
if rebar_force_failures:
    if os.path.isfile(pile_total_force_path):
        os.remove(pile_total_force_path)
    preview = "\n".join(rebar_force_failures[:12])
    if len(rebar_force_failures) > 12:
        preview += "\n... {0} additional failures".format(
            len(rebar_force_failures) - 12
        )
    raise RuntimeError(
        "Incomplete or ambiguous reinforcement output: no complete pile-total result "
        "was written. See rebar_section_diagnostics.csv.\n" + preview
    )
write_csv(
    pile_total_force_path,
    list(combined_rows[0].keys()),
    combined_rows,
)

damage_rows = []
for item in timeline:
    frame = item["frame"]
    row = dict((name, item[name]) for name in timeline_headers)
    for variable in ("DAMAGET", "DAMAGEC"):
        maximum = 0.0
        if variable in frame.fieldOutputs:
            values = frame.fieldOutputs[variable].getSubset(region=concrete_region).values
            if values:
                maximum = max(scalar(value) for value in values)
        row["Max" + variable] = maximum
    row["ThresholdCandidate"] = row["MaxDAMAGET"] >= float(settings["damage_threshold"])
    damage_rows.append(row)
write_csv(os.path.join(data_dir, "damage_scan.csv"), list(damage_rows[0].keys()), damage_rows)

session.pngOptions.setValues(imageSize=image_size_setting)
viewport.viewportAnnotationOptions.setValues(
    triad=ON, legend=ON, title=OFF, state=ON, annotations=OFF, compass=OFF
)


def primary_variable(variable, refinement):
    if refinement is None:
        viewport.odbDisplay.setPrimaryVariable(variableLabel=variable, outputPosition=INTEGRATION_POINT)
    else:
        viewport.odbDisplay.setPrimaryVariable(
            variableLabel=variable,
            outputPosition=INTEGRATION_POINT,
            refinement=refinement,
        )


def set_animation_limits(spec):
    """Use one observed min/max range for this ODB's complete animation."""

    limits = animation_legend_ranges.get(spec["name"], {})
    if spec["variable"] in ("DAMAGET", "DAMAGEC") and limits:
        viewport.odbDisplay.contourOptions.setValues(
            minAutoCompute=OFF,
            minValue=float(limits["min"]),
            maxAutoCompute=OFF,
            maxValue=float(limits["max"]),
        )
    elif limits:
        viewport.odbDisplay.contourOptions.setValues(
            minAutoCompute=OFF,
            minValue=float(limits["min"]),
            maxAutoCompute=OFF,
            maxValue=float(limits["max"]),
        )
    else:
        viewport.odbDisplay.contourOptions.setValues(
            minAutoCompute=ON,
            maxAutoCompute=ON,
        )


def set_static_limits(spec):
    """Configure the separately rendered static comparison contour."""

    viewport.odbDisplay.contourOptions.setValues(minAutoCompute=ON, maxAutoCompute=ON)


def render(spec):
    folder = os.path.join(frame_root, spec["name"])
    os.makedirs(folder, exist_ok=True)
    if spec.get("longitudinal"):
        grouped = {}
        for key in element_geometry:
            grouped.setdefault(key[0], []).append(str(key[1]))
        labels = tuple((name, tuple(values)) for name, values in sorted(grouped.items()))
        viewport.odbDisplay.displayGroup.replace(leaf=dgo.LeafFromElementLabels(elementLabels=labels))
    else:
        viewport.odbDisplay.displayGroup.replace(
            leaf=dgo.LeafFromElementSets(elementSets=(spec["set"],))
        )
    if spec.get("soil_section"):
        view_cut_name = "SOIL_XZ_" + spec["name"]
        soil_cut = viewport.odbDisplay.ViewCut(
            name=view_cut_name,
            shape=PLANE,
            origin=(0.0, float(settings["soil_section_coordinate"]), 0.5 * (pile_z_min + pile_z_max)),
            normal=(0.0, 1.0, 0.0),
            axis2=(0.0, 0.0, 1.0),
            followDeformation=OFF,
        )
        soil_cut.setValues(showModelAboveCut=OFF, showModelBelowCut=OFF, showModelOnCut=ON, showFreeBodyCut=OFF)
        viewport.odbDisplay.setValues(viewCut=ON, viewCutNames=(view_cut_name,))
        viewport.view.setViewpoint(viewVector=(0.0, -1.0, 0.0), cameraUpVector=(0.0, 0.0, 1.0))
    else:
        viewport.odbDisplay.setValues(viewCut=OFF)
        viewport.view.setViewpoint(
            viewVector=tuple(float(value) for value in settings["camera_view_vector"]),
            cameraUpVector=tuple(float(value) for value in settings["camera_up_vector"]),
        )
    primary_variable(spec["variable"], spec.get("refinement"))
    state = (CONTOURS_ON_UNDEF,) if spec.get("undeformed") else (CONTOURS_ON_DEF,)
    viewport.odbDisplay.display.setValues(plotState=state)
    set_static_limits(spec)
    viewport.view.fitView()
    written = []
    last_rendered_item = None
    for animation_index, item in enumerate(timeline):
        if spec["variable"] not in item["frame"].fieldOutputs:
            continue
        viewport.odbDisplay.setFrame(step=item["StepIndex"], frame=item["FrameIndex"])
        set_animation_limits(spec)
        base = os.path.join(
            folder,
            "{0:04d}_{1}_F{2:04d}".format(animation_index, safe_name(item["StepName"]), item["FrameIndex"]),
        )
        try:
            session.printToFile(fileName=base, format=PNG, canvasObjects=(viewport,))
            written.append(base + ".png")
            last_rendered_item = item
        except Exception:
            log("RENDER FAILED {0} {1}\n{2}".format(spec["name"], animation_index, traceback.format_exc()))
    if last_rendered_item is not None:
        viewport.odbDisplay.setFrame(
            step=last_rendered_item["StepIndex"],
            frame=last_rendered_item["FrameIndex"],
        )
        set_static_limits(spec)
        static_base = os.path.join(contour_dir, spec["name"] + "_LAST")
        try:
            session.printToFile(
                fileName=static_base,
                format=PNG,
                canvasObjects=(viewport,),
            )
        except Exception:
            log("STATIC RENDER FAILED {0}\n{1}".format(spec["name"], traceback.format_exc()))
    log("RENDER {0}: {1} frames".format(spec["name"], len(written)))


specs = [
    {"name": "PILE_U_MAG", "set": pile_display_set_name, "variable": "U", "refinement": (INVARIANT, "Magnitude")},
    {"name": "PILE_S_MISES", "set": pile_display_set_name, "variable": "S", "refinement": (INVARIANT, "Mises")},
    {"name": "PILE_CON_DAMAGET", "set": concrete_set_name, "variable": "DAMAGET", "refinement": None},
    {"name": "PILE_CON_DAMAGEC", "set": concrete_set_name, "variable": "DAMAGEC", "refinement": None},
    {"name": "SOIL_PEEQ_XZ", "set": soil_set_name, "variable": "PEEQ", "refinement": None, "soil_section": True},
    {"name": "SOIL_PEMAG_XZ", "set": soil_set_name, "variable": "PEMAG", "refinement": None, "soil_section": True},
    {"name": "SOIL_S33_XZ", "set": soil_set_name, "variable": "S", "refinement": (COMPONENT, "S33"), "soil_section": True},
    {"name": "SOIL_S_MISES_XZ", "set": soil_set_name, "variable": "S", "refinement": (INVARIANT, "Mises"), "soil_section": True},
    {"name": "REBAR_LONG_S_MISES_UNDEFORMED", "variable": "S", "refinement": (INVARIANT, "Mises"), "longitudinal": True, "undeformed": True},
    {"name": "REBAR_LONG_S11_UNDEFORMED", "variable": "S", "refinement": (COMPONENT, "S11"), "longitudinal": True, "undeformed": True},
]
for spec in specs if render_outputs else []:
    render(spec)

metadata = {
    "odb_path": odb_path,
    "start_step": start_step_name,
    "end_step": end_step_name,
    "timeline_points": len(timeline),
    "alignment_key": ["SequenceIndex", "StepName", "FrameIndex", "TotalTime"],
    "load_set": load_set_name,
    "load_direction": str(config.get("load_direction", "")),
    "pile_type": config["pile_type"],
    "pile_display_set": pile_display_set_name,
    "pile_concrete_set": concrete_set_name,
    "pile_steel_set": config.get("pile_steel_set", ""),
    "soil_set": soil_set_name,
    "rebar_set": rebar_set_name,
    "longitudinal_material": longitudinal_material_name,
    "comparison_group": config.get("comparison_group", ""),
    "legend_ranges": config.get("legend_ranges", {}),
    "rebar_method": rebar_method,
    "RebarSectionRule": REBAR_SECTION_RULE,
    "RebarInterpolationRule": REBAR_INTERPOLATION_METHOD,
    "RebarActiveRule": (
        REBAR_SECTION_RULE
        if rebar_method == "element_cut"
        else REBAR_INTERPOLATION_METHOD
    ),
    "odb_detected_bar_count": detected_rebar_count,
    "configured_expected_longitudinal_rebar_count": configured_expected_rebar_count,
    "effective_expected_longitudinal_rebar_count": effective_expected_rebar_count,
    "expected_longitudinal_rebar_count_source": expected_rebar_count_source,
    "rebar_element_count": len(element_geometry),
    # Keep the historic names for readers that still consume them, while making
    # clear that they are only the fallback when ODB section area is unavailable.
    "rebar_diameter_mm": bar_diameter_mm,
    "bar_area_mm2": bar_area_mm2,
    "configured_fallback_bar_diameter_mm": bar_diameter_mm,
    "configured_fallback_bar_area_mm2": bar_area_mm2,
    "configured_area_assumption": (
        "uniform circular diameter; fallback only when an element's ODB "
        "truss-section area is unavailable"
    ),
    "bar_area_source_priority": (
        "odb instance.sectionAssignments -> odb.sections[sectionName].area; "
        "configured uniform diameter only when unavailable"
    ),
    "bar_area_source_counts": area_source_counts,
    "bar_area_values_model_units_squared": area_values,
    "bar_area_fallback_warning": bool(fallback_area_elements),
    "ground_elevation_model_z_mm": ground_z,
    "freebody_targets": [label for label, _item in targets],
    "freebody_append": False,
    "contour_sequences": [spec["name"] for spec in specs],
    "render_viewport_mm": list(render_viewport_mm),
    "image_size_unit": image_size_unit,
    "requested_image_size": [image_width, image_height],
    "contact_history_columns": history_columns,
    "contact_history_source_count": len(history_source_metadata),
    "render_outputs": render_outputs,
    "animation_legend_mode": "comparison_group_full_timeline_fixed",
    "animation_legend_ranges": animation_legend_ranges,
    "static_contour_legend_mode": "comparison_group_fixed_selected_frames",
}
with open(os.path.join(output_dir, "metadata.json"), "w", encoding="utf-8") as stream:
    json.dump(metadata, stream, ensure_ascii=False, indent=2)
log(json.dumps(metadata, ensure_ascii=False))
odb.close()
