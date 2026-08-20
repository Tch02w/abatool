"""Geometry-only helpers for reinforced-concrete section force extraction.

The Abaqus worker keeps a small Python-2-compatible counterpart of these
functions because it is executed by Abaqus/CAE outside the application
package.  Keeping the geometry rules here makes them independently testable.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import sqrt


def crosses_horizontal_cut(
    z1: float,
    z2: float,
    cut_z: float,
    *,
    tolerance: float,
    is_top_of_rebar: bool = False,
) -> bool:
    """Return whether a segment owns a horizontal cut.

    Segments use ``[z_min, z_max)`` ownership.  The one segment ending at the
    physical top of the reinforcement also owns that endpoint, so a cut through
    a shared node cannot count both adjacent T3D2 elements.
    """

    z_min, z_max = sorted((float(z1), float(z2)))
    cut = float(cut_z)
    tol = abs(float(tolerance))
    if z_max - z_min <= tol:
        return False
    if cut < z_min - tol or cut > z_max + tol:
        return False
    if cut < z_max - tol:
        return True
    return bool(is_top_of_rebar and abs(cut - z_max) <= tol)


def project_axial_force_to_pile_axis(
    axial_force: float,
    first: tuple[float, float, float],
    last: tuple[float, float, float],
) -> float:
    """Project a truss axial resultant onto the global pile (Z) axis.

    T3D2 connectivity can be ordered either upward or downward.  Its stress
    sign already represents tension/compression, so connectivity must not flip
    the resultant sign.  The absolute Z direction cosine gives the consistent
    contribution across a horizontal cut.
    """

    dz = float(last[2]) - float(first[2])
    length = sqrt(sum((float(last[i]) - float(first[i])) ** 2 for i in range(3)))
    return 0.0 if length == 0.0 else float(axial_force) * abs(dz) / length


def sum_crossing_rebar_force(
    elements: Iterable[Mapping[str, object]],
    cut_z: float,
    *,
    tolerance: float,
    top_z: float,
) -> tuple[float, list[Mapping[str, object]], int]:
    """Return projected force, uniquely selected elements, and duplicates.

    Each mapping contains ``bar_id``, ``reference_first``, ``reference_last``,
    ``current_first``, ``current_last`` and ``axial_force``.  Intersection is
    evaluated in the reference geometry to match Abaqus' undeformed Free Body
    Cut; projection uses the current geometry resolved from COORD or
    reference coordinates plus U, with reference geometry only as a final
    explicitly diagnosed fallback.
    """

    selected: dict[object, Mapping[str, object]] = {}
    duplicates = 0
    for element in elements:
        first = element["reference_first"]
        last = element["reference_last"]
        z_max = max(float(first[2]), float(last[2]))
        if not crosses_horizontal_cut(
            float(first[2]), float(last[2]), cut_z,
            tolerance=tolerance,
            is_top_of_rebar=abs(z_max - float(top_z)) <= abs(float(tolerance)),
        ):
            continue
        bar_id = element["bar_id"]
        if bar_id in selected:
            duplicates += 1
            continue
        selected[bar_id] = element
    chosen = list(selected.values())
    force = sum(
        project_axial_force_to_pile_axis(
            float(item["axial_force"]), item["current_first"], item["current_last"]
        )
        for item in chosen
    )
    return force, chosen, duplicates
