from __future__ import print_function

import argparse
import json
import os
import sys

from odbAccess import openOdb


def flatten(groups):
    for group in groups:
        try:
            for item in group:
                yield item
        except TypeError:
            yield group


def count_groups(groups):
    return sum(1 for _ in flatten(groups))


def bounding_box(nodes):
    limits = None
    for node in flatten(nodes):
        coordinates = list(node.coordinates)
        coordinates += [0.0] * (3 - len(coordinates))
        if limits is None:
            limits = [[float(value), float(value)] for value in coordinates[:3]]
        else:
            for index, value in enumerate(coordinates[:3]):
                limits[index][0] = min(limits[index][0], float(value))
                limits[index][1] = max(limits[index][1], float(value))
    if limits is None:
        return None
    return dict(zip(("x", "y", "z"), limits))


def structure_catalog(odb):
    """Metadata only: scoped region identities, without materializing field values.

    An ODB exposes assembly instances, not the CAE part repository. Never combine
    node/element sets with equal names or labels from different instances.
    Field availability is per frame and does not guarantee data in a given set.
    """
    regions = []

    def append_region(scope, instance_name, kind, name, region):
        element_types = {}
        element_count = 0
        if kind != "node_set":
            for element in flatten(region.elements):
                element_count += 1
                key = str(element.type)
                element_types[key] = element_types.get(key, 0) + 1
        regions.append({
            "id": json.dumps([scope, instance_name, kind, name], ensure_ascii=False),
            "scope": scope,
            "instance": instance_name,
            "kind": kind,
            "name": name,
            "nodeCount": count_groups(region.nodes) if kind != "element_set" else 0,
            "elementCount": element_count,
            "elementTypes": element_types,
        })

    assembly = odb.rootAssembly
    for scope, instance_name, owner in [("assembly", "", assembly)] + [
        ("instance", name, assembly.instances[name]) for name in sorted(assembly.instances.keys())
    ]:
        if scope == "instance":
            append_region(scope, instance_name, "instance", instance_name, owner)
        for kind, repository in (("node_set", owner.nodeSets), ("element_set", owner.elementSets)):
            for name in sorted(repository.keys()):
                append_region(scope, instance_name, kind, name, repository[name])

    steps = []
    for name in odb.steps.keys():
        frames = []
        for index, frame in enumerate(odb.steps[name].frames):
            fields = []
            for field_name in sorted(frame.fieldOutputs.keys()):
                field = frame.fieldOutputs[field_name]
                fields.append({
                    "name": field_name,
                    "components": list(field.componentLabels),
                    "type": str(field.type),
                    "positions": sorted(set(str(location.position) for location in field.locations)),
                })
            frames.append({"index": index, "value": float(frame.frameValue), "fields": fields})
        steps.append({"name": name, "frames": frames})

    sections = []
    for name in sorted(odb.sections.keys()):
        section = odb.sections[name]
        item = {"name": name, "type": type(section).__name__, "material": str(getattr(section, "material", ""))}
        area = getattr(section, "area", None)
        if area is not None:
            item["area"] = float(area)
        sections.append(item)
    assignments = []
    for name in sorted(assembly.instances.keys()):
        for assignment in assembly.instances[name].sectionAssignments:
            assignments.append({"instance": name, "region": assignment.region.name,
                                "section": assignment.sectionName})
    return {"schemaVersion": 1, "regions": regions, "steps": steps,
            "sections": sections, "sectionAssignments": assignments,
            "units": "model_defined", "fieldAvailability": "frame_only_not_region_validated"}


def inspect_odb(path):
    result = {"path": path, "error": ""}
    odb = None
    try:
        odb = openOdb(path, readOnly=True)
        assembly = odb.rootAssembly
        step_names = list(odb.steps.keys())
        field_outputs = set()
        step_details = []
        history_output_details = []
        for step_name in step_names:
            step = odb.steps[step_name]
            for frame in step.frames:
                field_outputs.update(frame.fieldOutputs.keys())
            history_regions = []
            for region_name, region in step.historyRegions.items():
                output_names = sorted(region.historyOutputs.keys())
                if not output_names:
                    continue
                output_previews = {}
                for output_name in output_names:
                    data = region.historyOutputs[output_name].data
                    if data is None:
                        data = ()
                    output_previews[output_name] = {
                        "point_count": len(data),
                        "first": list(data[0]) if data else None,
                        "last": list(data[-1]) if data else None,
                    }
                history_regions.append(
                    {
                        "name": region_name,
                        "description": str(getattr(region, "description", "")),
                        "position": str(getattr(region, "position", "")),
                        "outputs": output_names,
                        "output_previews": output_previews,
                    }
                )
            history_output_details.append(
                {
                    "step": step_name,
                    "regions": history_regions,
                }
            )
            step_details.append(
                {
                    "name": step_name,
                    "frame_count": len(step.frames),
                    "end_time": float(step.frames[-1].frameValue) if step.frames else 0.0,
                }
            )

        node_names = sorted(assembly.nodeSets.keys())
        element_names = sorted(assembly.elementSets.keys())
        details = {}
        for name in sorted(set(node_names + element_names)):
            node_set = assembly.nodeSets[name] if name in node_names else None
            element_set = assembly.elementSets[name] if name in element_names else None
            details[name] = {
                "node_count": count_groups(node_set.nodes) if node_set is not None else 0,
                "element_count": count_groups(element_set.elements) if element_set is not None else 0,
                "bbox": bounding_box(node_set.nodes) if node_set is not None else None,
            }

        instance_details = {}
        for name, instance in assembly.instances.items():
            element_types = {}
            for element in instance.elements:
                element_types[element.type] = element_types.get(element.type, 0) + 1
            instance_details[name] = {
                "nodes": len(instance.nodes),
                "elements": len(instance.elements),
                "element_types": element_types,
            }

        result.update(
            {
                "steps": step_names,
                "step_details": step_details,
                "history_output_details": history_output_details,
                "field_outputs": sorted(field_outputs),
                "assembly_node_sets": node_names,
                "assembly_element_sets": element_names,
                "set_details": details,
                "instances": instance_details,
                "structure_catalog": structure_catalog(odb),
                "size_bytes": os.path.getsize(path),
            }
        )
    except Exception as exc:
        result["error"] = repr(exc)
    finally:
        if odb is not None:
            odb.close()
    return result


def parse_args():
    arguments = sys.argv[1:]
    if "--" in arguments:
        arguments = arguments[arguments.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args(arguments)


def main():
    args = parse_args()
    folder = os.path.abspath(args.folder)
    paths = [
        os.path.join(folder, name)
        for name in sorted(os.listdir(folder))
        if name.lower().endswith(".odb")
    ]
    report = {
        "folder": folder,
        "odb_count": len(paths),
        "odbs": [inspect_odb(path) for path in paths],
    }
    output = os.path.abspath(args.output)
    directory = os.path.dirname(output)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(output, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"output": output, "odb_count": len(paths)}))


if __name__ == "__main__":
    main()
