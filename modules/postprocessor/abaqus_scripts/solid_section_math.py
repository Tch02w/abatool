"""Version-neutral validation and vector math for explicitly located sections."""
import math


def vector(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(name + " must contain three numbers")
    if any(type(item) not in (int, float) or not math.isfinite(item) for item in value):
        raise ValueError(name + " must contain finite numbers")
    return tuple(float(item) for item in value)


def dot(left, right):
    return sum(a * b for a, b in zip(left, right))


def section_config(payload):
    if not isinstance(payload, dict) or set(payload) != {"origin", "normal", "offsets", "momentReference", "momentPoint"}:
        raise ValueError("Section requires origin, normal, offsets, momentReference and momentPoint")
    origin = vector(payload["origin"], "origin")
    normal = vector(payload["normal"], "normal")
    length = math.hypot(*normal)
    if not math.isfinite(length) or length < 1e-12:
        raise ValueError("Cut normal must be nonzero and finite")
    normal = tuple(item / length for item in normal)
    offsets = payload["offsets"]
    if not isinstance(offsets, list) or not 1 <= len(offsets) <= 1000:
        raise ValueError("Choose 1 to 1000 section offsets")
    if any(type(item) not in (int, float) or not math.isfinite(item) for item in offsets):
        raise ValueError("Section offsets must be finite")
    if len(set(offsets)) != len(offsets):
        raise ValueError("Section offsets must be unique")
    reference = payload["momentReference"]
    if reference not in ("centroid", "point"):
        raise ValueError("Moment reference must be centroid or point")
    point = vector(payload["momentPoint"], "momentPoint") if reference == "point" else None
    if reference == "centroid" and payload["momentPoint"] is not None:
        raise ValueError("Centroid mode must not silently ignore a moment point")
    return {"origin": origin, "normal": normal, "offsets": [float(item) for item in offsets],
            "momentReference": reference, "momentPoint": point}


def plane_origin(config, offset):
    point = tuple(a + offset * b for a, b in zip(config["origin"], config["normal"]))
    if not all(math.isfinite(item) for item in point):
        raise ValueError("Section location overflow")
    return point


def force_moment_components(force, moment, normal):
    axial = dot(force, normal)
    torsion = dot(moment, normal)
    bending = math.hypot(*(value - torsion * axis for value, axis in zip(moment, normal)))
    if not all(math.isfinite(value) for value in (axial, torsion, bending)):
        raise ValueError("Force/moment resolution overflow")
    return axial, torsion, bending
