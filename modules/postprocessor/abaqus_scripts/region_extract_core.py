"""Read-only, region-scoped extraction primitives shared by the Abaqus worker.

No field extrapolation, no merging of labels across instances, and no summation
of forces along a member. Each result retains its original output location.
"""

import math
import hashlib
import os
import re
import stat


def source_identity(path):
    """Detect ordinary rewrites/replacements without fully hashing large ODBs.

    Compare local filesystem identity while reading; persist only size, mtime
    and 64 KiB head/middle/tail samples across Python versions. This is a
    change guard, not a full-file integrity certificate.
    """
    def metadata(value):
        return {"size": value.st_size, "mtimeNs": value.st_mtime_ns,
                "ctimeNs": value.st_ctime_ns, "device": value.st_dev, "inode": value.st_ino}

    before = os.stat(path)
    if not stat.S_ISREG(before.st_mode) or before.st_size <= 0:
        raise RuntimeError("Source ODB must be a nonempty regular file")
    expected = metadata(before)
    # Windows path-stat and descriptor-stat may expose different ctime
    # semantics (creation versus metadata change). Compare like with like.
    handle_expected = {key: value for key, value in expected.items() if key != "ctimeNs"}
    digest = hashlib.sha256()
    sample_size = 64 * 1024
    offsets = (0, max((before.st_size - sample_size) // 2, 0), max(before.st_size - sample_size, 0))
    with open(path, "rb") as stream:
        handle = metadata(os.fstat(stream.fileno()))
        if any(handle[key] != value for key, value in handle_expected.items()):
            raise RuntimeError("Source ODB changed while reading its identity")
        for offset in offsets:
            stream.seek(offset)
            block = stream.read(sample_size)
            digest.update(str(offset).encode("ascii") + b":" + block)
        handle = metadata(os.fstat(stream.fileno()))
        if any(handle[key] != value for key, value in handle_expected.items()):
            raise RuntimeError("Source ODB changed while reading its identity")
    if metadata(os.stat(path)) != expected:
        raise RuntimeError("Source ODB changed while reading its identity")
    # The host and Abaqus use different Python versions. Windows ctime, inode
    # and device representations can differ between them; do not persist those.
    return dict(size=expected["size"], mtimeNs=expected["mtimeNs"], sampledSha256=digest.hexdigest())


def require_source_identity(path, expected):
    try:
        current = source_identity(path)
    except OSError as error:
        raise RuntimeError("Source ODB is no longer accessible: " + str(path)) from error
    if current != expected:
        raise RuntimeError("Source ODB changed after the extraction request: " + str(path))
    return current


def flatten_elements(groups):
    for group in groups:
        if hasattr(group, "label"):
            yield group
        else:
            for element in group:
                yield element


def resolve_region(odb, descriptor):
    scope = descriptor.get("scope")
    kind = descriptor.get("kind")
    name = descriptor.get("name")
    instance = descriptor.get("instance", "")
    if scope == "assembly" and not instance:
        owner = odb.rootAssembly
    elif scope == "instance" and instance in odb.rootAssembly.instances:
        owner = odb.rootAssembly.instances[instance]
    else:
        raise ValueError("Unknown region scope or instance")
    if kind == "instance" and scope == "instance" and name == instance:
        return owner
    if kind == "element_set" and name in owner.elementSets:
        return owner.elementSets[name]
    raise ValueError("Select an existing element set or entire instance")


def validate_element_family(region, method):
    types = set(str(element.type) for element in flatten_elements(region.elements))
    if not types:
        raise ValueError("Selected region contains no elements")
    pattern = r"(?:B(?:21|22|23|31|32|33)(?:H|OS|OSH)?|PIPE(?:21|22|31|32)H?)" if method == "beam_sections" else r"T[23]D[23](?:H|T)?"
    if any(re.fullmatch(pattern, item) is None for item in types):
        raise ValueError("Element family is incompatible with {0}: {1}".format(method, ", ".join(sorted(types))))
    return sorted(types)


def value_data(value):
    try:
        raw = value.data
    except Exception:
        raw = value.dataDouble
    if isinstance(raw, (int, float)):
        raw = (raw,)
    numbers = tuple(float(item) for item in raw)
    if not all(math.isfinite(item) for item in numbers):
        raise ValueError("Non-finite field output")
    return numbers


def section_areas(odb):
    """Only use explicitly stored section area; never infer it from a set name."""
    areas = {}
    for instance_name, instance in odb.rootAssembly.instances.items():
        for assignment in instance.sectionAssignments:
            section = odb.sections[assignment.sectionName]
            area = getattr(section, "area", None)
            if area is None:
                continue
            area = float(area)
            if not math.isfinite(area) or area <= 0:
                raise ValueError("Invalid area in section " + assignment.sectionName)
            for element in flatten_elements(assignment.region.elements):
                key = (instance_name, element.label)
                if key in areas and areas[key][0] != area:
                    raise ValueError("Conflicting section areas for " + str(key))
                areas[key] = (area, "odb_section:" + assignment.sectionName)
    return areas


def extract_rows(odb, request):
    """Yield long-form records for explicit step/frame selections.

    truss_reference_area deliberately reproduces the legacy S11*A0 convention:
    it is an estimate at finite strain, not a claimed current-area axial force.
    beam_sections reports stored SF/SM components in Abaqus local section axes.
    """
    method = request.get("method")
    if method not in ("beam_sections", "truss_reference_area"):
        raise ValueError("Unsupported extraction method")
    if method == "truss_reference_area" and request.get("acknowledgeReferenceArea") is not True:
        raise ValueError("S11 times reference area requires explicit acknowledgement of the finite-strain limitation")
    selections = request.get("frames")
    if not isinstance(selections, list) or not selections:
        raise ValueError("Explicit step/frame selections are required")
    selected_frames = []
    seen = set()
    for selection in selections:
        step_name = selection.get("step")
        index = selection.get("index")
        if step_name not in odb.steps or type(index) is not int or not 0 <= index < len(odb.steps[step_name].frames):
            raise ValueError("Invalid step/frame selection")
        key = (step_name, index)
        if key in seen:
            raise ValueError("Duplicate step/frame selection")
        seen.add(key)
        selected_frames.append((step_name, index, odb.steps[step_name].frames[index]))
    region = resolve_region(odb, request["region"])
    validate_element_family(region, method)
    expected_elements = sum(1 for _ in flatten_elements(region.elements))
    override = request.get("referenceAreaOverride")
    if override is not None:
        if type(override) not in (int, float) or not math.isfinite(override) or override <= 0:
            raise ValueError("Reference area override must be a positive finite number in model length squared")
        override = float(override)
    areas = section_areas(odb) if method == "truss_reference_area" and override is None else {}

    for step_name, index, frame in selected_frames:
        names = ("SF", "SM") if method == "beam_sections" else ("S",)
        available_components = set()
        coverage = {}
        frame_rows = 0
        for name in names:
            if name not in frame.fieldOutputs:
                if name == "SM":
                    continue  # Some ODBs include moment components within SF.
                raise ValueError("Missing {0} in {1}, frame {2}".format(name, step_name, index))
            field = frame.fieldOutputs[name]
            if bool(getattr(field, "isComplex", False)):
                raise ValueError("Complex output requires a separate amplitude/phase extraction method")
            # Abaqus can reduce the tensor layout for the selected element family.
            # Mixed solid/truss frames have six global S labels but three in the
            # truss subset. Map data using the subset, never the parent field.
            subset = field.getSubset(region=region)
            labels = list(subset.componentLabels)
            if method == "truss_reference_area" and "S11" not in labels:
                raise ValueError("Selected frame has no S11 component")
            values = subset.values  # Saved positions only; no extrapolation/write.
            for value in values:
                if str(value.position) != "INTEGRATION_POINT":
                    continue
                if value.instance is None:
                    raise ValueError("Element output has no instance identity")
                data = value_data(value)
                if len(data) != len(labels):
                    raise ValueError("Field data/component count mismatch")
                base = {
                    "step": step_name, "frame": index, "frame_value": float(frame.frameValue),
                    "instance": value.instance.name, "element": value.elementLabel,
                    "position": str(value.position), "integration_point": value.integrationPoint,
                    "section_point": getattr(getattr(value, "sectionPoint", None), "number", 0),
                    "method": method,
                }
                if method == "beam_sections":
                    for label, number in zip(labels, data):
                        if not re.fullmatch(r"S[FM][123]", label):
                            continue
                        available_components.add(label)
                        coverage.setdefault(label, set()).add((value.instance.name, value.elementLabel))
                        row = dict(base, component=label, value=number,
                                   area="", area_source="", convention="abaqus_local_section_axes")
                        frame_rows += 1
                        yield row
                else:
                    key = (value.instance.name, value.elementLabel)
                    if override is not None:
                        area, source = override, "explicit_uniform_override"
                    elif key in areas:
                        area, source = areas[key]
                    else:
                        raise ValueError("No section area for {0}; provide a verified area explicitly".format(key))
                    force = data[labels.index("S11")] * area
                    if not math.isfinite(force):
                        raise ValueError("Non-finite stress-area product")
                    frame_rows += 1
                    coverage.setdefault("N_reference_area", set()).add(key)
                    yield dict(base, component="N_reference_area", value=force, area=area,
                               area_source=source, convention="S11_times_reference_area_not_current_area")
        if frame_rows == 0:
            raise ValueError("No integration-point output in selected region for {0}, frame {1}".format(step_name, index))
        if any(len(keys) != expected_elements for keys in coverage.values()):
            raise ValueError("Output does not cover every selected element; missing data must not be interpreted as zero")
        if method == "beam_sections" and ("SF1" not in available_components or not {"SM1", "SM2"}.intersection(available_components)):
            raise ValueError("Selected beam region/frame lacks axial force or bending moment output")
