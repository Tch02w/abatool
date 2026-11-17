"""CAE view-cut integration for a selected solid region, using legacy geometry.

Requires a private noGUI CAE session. The ODB must be opened read-only by caller.
All forces are global; moments are explicitly about the exported reference point.
"""
import csv
import math
import os
import re

from solid_section_math import section_config, plane_origin, force_moment_components, dot
from region_extract_core import resolve_region, flatten_elements, value_data


def region_leaf(dgo, region, descriptor):
    if descriptor["kind"] == "instance":
        return dgo.LeafFromPartInstance(partInstanceName=(descriptor["instance"],))
    if descriptor["scope"] == "instance":
        return dgo.LeafFromElementLabels(partInstanceName=descriptor["instance"],
            elementLabels=tuple(str(element.label) for element in flatten_elements(region.elements)))
    return dgo.LeafFromElementSets(elementSets=(descriptor["name"],))


def extract_solid_rows(odb, request, output):
    from abaqus import session
    from abaqusConstants import (OFF, ON, UNDEFORMED, PLANE, CURRENT_DISPLAY_GROUP, CSYS,
                                GLOBAL, SCIENTIFIC, COMMA_SEPARATED_VALUES, SPECIFY, CENTROID)
    import visualization
    import displayGroupOdbToolset as dgo

    config = section_config(request.get("section"))
    region = resolve_region(odb, request["region"])
    elements = list(flatten_elements(region.elements))
    if not elements or any(re.fullmatch(r"C3D(?:4|6|8|10|15|20|27)[A-Z]*", str(element.type)) is None for element in elements):
        raise ValueError("View-cut integration requires a nonempty region of 3D continuum solid elements")
    steps = list(odb.steps.keys())
    selections = request.get("frames")
    if not isinstance(selections, list) or not selections:
        raise ValueError("Explicit step/frame selections are required")
    seen = set()
    for selection in selections:
        key = (selection.get("step"), selection.get("index"))
        if (key in seen or key[0] not in steps or type(key[1]) is not int
                or not 0 <= key[1] < len(odb.steps[key[0]].frames)):
            raise ValueError("Invalid or duplicate step/frame selection")
        seen.add(key)

    viewport = session.Viewport(name="Region solid extraction", width=150, height=100)
    viewport.makeCurrent()
    viewport.setValues(displayedObject=odb)
    viewport.odbDisplay.display.setValues(plotState=(UNDEFORMED,))
    viewport.odbDisplay.displayGroup.replace(leaf=region_leaf(dgo, region, request["region"]))
    normal = config["normal"]
    axis2 = (1., 0., 0.) if abs(normal[0]) < 0.8 else (0., 1., 0.)
    projection = dot(axis2, normal)
    axis2 = tuple(value - projection * direction for value, direction in zip(axis2, normal))
    length = math.hypot(*axis2)
    axis2 = tuple(value / length for value in axis2)
    session.freeBodyReportOptions.setValues(numDigits=10, forceThreshold=1e-12, momentThreshold=1e-12,
        numberFormat=SCIENTIFIC, reportFormat=COMMA_SEPARATED_VALUES, csysType=GLOBAL)
    viewport.odbDisplay.viewCutOptions.setValues(displaySlicing=OFF, freeBodyCutThru=CURRENT_DISPLAY_GROUP,
        numCutFreeBody=1, componentResolution=CSYS, csysName=GLOBAL,
        summationLoc=SPECIFY if config["momentReference"] == "point" else CENTROID,
        summationPoint=config["momentPoint"] or (0., 0., 0.))
    raw_dir = os.path.join(output, "raw_sections")
    os.makedirs(raw_dir)
    projected_bounds = None
    for sequence, selection in enumerate(selections):
        step = selection["step"]
        index = selection["index"]
        frame = odb.steps[step].frames[index]
        if "S" not in frame.fieldOutputs or bool(getattr(frame.fieldOutputs["S"], "isComplex", False)):
            raise ValueError("Solid section requires real stress output in every selected frame")
        values = frame.fieldOutputs["S"].getSubset(region=region).values
        coverage = set()
        for value in values:
            if str(value.position) == "INTEGRATION_POINT":
                value_data(value)  # Reject invalid stress before CAE integration.
                coverage.add((value.instance.name, value.elementLabel))
        if len(coverage) != len(elements):
            raise ValueError("Stress output does not cover every selected solid element")
        if projected_bounds is None:
            coordinates = {name: {node.label: tuple(float(number) for number in node.coordinates)
                                 for node in odb.rootAssembly.instances[name].nodes}
                           for name in set(name for name, label in coverage)}
            projected_bounds = []
            for instance_name, label in coverage:
                element = odb.rootAssembly.instances[instance_name].getElementFromLabel(label)
                projections = [dot(coordinates[instance_name][node], normal) for node in element.connectivity]
                projected_bounds.append((min(projections), max(projections)))
        viewport.odbDisplay.setFrame(step=steps.index(step), frame=index)
        for cut_index, offset in enumerate(config["offsets"]):
            origin = plane_origin(config, offset)
            distance = dot(origin, normal)
            if not any(low <= distance <= high and low < high for low, high in projected_bounds):
                raise ValueError("Requested plane does not intersect the selected solid elements")
            name = "RegionCut_{0}_{1}".format(sequence, cut_index)
            cut = viewport.odbDisplay.ViewCut(name=name, shape=PLANE, origin=origin,
                normal=normal, axis2=axis2, followDeformation=OFF)
            # CAE initializes position at mid-range, not at the supplied origin.
            # The explicit zero offset is essential; report CutX/Y/Z is the
            # moment reference point and cannot be used to infer the plane.
            if not cut.cutRange[0] < 0 < cut.cutRange[1]:
                raise ValueError("Requested plane lies outside the displayed solid range")
            cut.setValues(position=0., showModelAboveCut=OFF, showModelBelowCut=ON,
                          showModelOnCut=ON, showFreeBodyCut=ON)
            viewport.odbDisplay.setValues(viewCut=ON, viewCutNames=(name,))
            raw = os.path.join(raw_dir, "frame_{0}_cut_{1}.csv".format(sequence, cut_index))
            session.writeFreeBodyReport(fileName=raw, append=OFF, step=steps.index(step), frame=index,
                                        stepFrame=SPECIFY, odb=odb)
            with open(raw, encoding="utf-8-sig") as stream:
                records = list(csv.DictReader(stream))
            if len(records) != 1:
                raise ValueError("Expected exactly one section result; cut may not intersect the selected elements")
            report = records[0]
            if report["StepName"].strip() != step or int(report["FrameId"]) != index:
                raise ValueError("CAE returned a different frame than requested")
            force = tuple(float(report[name]) for name in ("Fx", "Fy", "Fz"))
            moment = tuple(float(report[name]) for name in ("Mx", "My", "Mz"))
            reference = tuple(float(report[name]) for name in ("CutX", "CutY", "CutZ"))
            if not all(math.isfinite(value) for value in force + moment + reference):
                raise ValueError("Non-finite section integration result")
            axial, torsion, bending = force_moment_components(force, moment, normal)
            components = list(zip(("Fx", "Fy", "Fz", "Mx", "My", "Mz", "N_normal", "M_torsion", "M_bending_magnitude"),
                                  force + moment + (axial, torsion, bending)))
            for component, number in components:
                yield dict(step=step, frame=index, frame_value=float(frame.frameValue),
                    instance=request["region"]["instance"], element="", position="SECTION_CUT",
                    integration_point="", section_point="", cut_index=cut_index, method="solid_section", component=component,
                    value=number, area="", area_source="", convention="abaqus_view_cut_reference_geometry_global_components",
                    plane_x=origin[0], plane_y=origin[1], plane_z=origin[2],
                    normal_x=normal[0], normal_y=normal[1], normal_z=normal[2],
                    moment_reference_x=reference[0], moment_reference_y=reference[1], moment_reference_z=reference[2])
            # Keep this private session bounded for long frame/cut sequences.
            viewport.odbDisplay.setValues(viewCut=OFF)
            del viewport.odbDisplay.viewCuts[name]
