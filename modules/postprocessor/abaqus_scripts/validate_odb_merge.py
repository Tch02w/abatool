"""Read-only restartjoin verification; run with the Abaqus Python interpreter."""

# Preserve syntax accepted by older Abaqus Python workers.
# ruff: noqa: UP010, UP030, UP032
from __future__ import print_function

import hashlib
import json
import os
import sys

import numpy as np


def _text(digest, value):
    digest.update(json.dumps(value, sort_keys=True, ensure_ascii=True).encode("ascii"))
    digest.update(b"\n")


def _array(digest, value, dtype="<f8"):
    if value is None:
        _text(digest, None)
        return
    array = np.asarray(value, dtype=dtype)
    _text(digest, list(array.shape))
    digest.update(array.tobytes(order="C"))


def _precision_data(value, name):
    try:
        return getattr(value, name)
    except Exception:  # noqa: BLE001 - Abaqus precision access raises SWIG errors.
        return getattr(value, name + "Double")


def field_signature(field):
    """Hash all saved numeric values, labels, locations and local axes.

    Bulk blocks avoid creating one Python FieldValue per integration point.
    Double precision/unsupported bulk access falls back to FieldValue access.
    """
    blocks = []
    try:
        for block in field.bulkDataBlocks:
            digest = hashlib.sha256()
            _text(
                digest,
                [
                    getattr(block.instance, "name", ""),
                    str(block.position),
                    getattr(block.sectionPoint, "number", 0),
                    list(block.componentLabels),
                ],
            )
            for name in ("elementLabels", "nodeLabels", "integrationPoints"):
                _array(digest, getattr(block, name, None), "<i8")
            for name in ("data", "conjugateData", "localCoordSystem"):
                _array(digest, getattr(block, name, None))
            blocks.append(digest.hexdigest())
        mode = "bulk"
    except Exception:  # noqa: BLE001 - unsupported bulk access must use FieldValue.
        # The documented bulk API rejects double precision. Never substitute zero.
        digest = hashlib.sha256()
        for value in field.values:
            _text(
                digest,
                [
                    getattr(getattr(value, "instance", None), "name", ""),
                    str(value.position),
                    getattr(value, "nodeLabel", None),
                    getattr(value, "elementLabel", None),
                    getattr(value, "integrationPoint", None),
                    getattr(getattr(value, "sectionPoint", None), "number", 0),
                ],
            )
            _array(digest, _precision_data(value, "data"))
            if getattr(field, "isComplex", False):
                _array(digest, _precision_data(value, "conjugateData"))
            _array(digest, _precision_data(value, "localCoordSystem"))
        blocks = [digest.hexdigest()]
        mode = "values"
    return [str(field.type), list(field.componentLabels), mode, sorted(blocks)]


def _frame_signature(frame):
    return [
        float(frame.frameValue),
        frame.incrementNumber,
        {name: field_signature(field) for name, field in frame.fieldOutputs.items()},
    ]


def _history_signature(step):
    digest = hashlib.sha256()
    for name in sorted(step.historyRegions.keys()):
        region = step.historyRegions[name]
        _text(digest, name)
        for key in sorted(region.historyOutputs.keys()):
            output = region.historyOutputs[key]
            _text(digest, [key, str(output.type)])
            _array(digest, output.data)
            _array(digest, getattr(output, "conjugateData", None))
    return digest.hexdigest()


def expected_steps(original, restart):
    if not len(restart.steps) or not any(
        len(step.frames) for step in restart.steps.values()
    ):
        raise ValueError("Restart ODB contains no result frames")
    restarted = list(restart.steps.items())
    first_number = restarted[0][1].number
    numbers = [step.number for _, step in restarted]
    if numbers != sorted(set(numbers)):
        raise ValueError("Restart step numbers are not strictly increasing")
    prefix = [
        (name, step)
        for name, step in original.steps.items()
        if step.number < first_number
    ]
    if len({name for name, _ in prefix + restarted}) != len(prefix + restarted):
        raise ValueError("Restart step names conflict with retained original steps")
    return [(name, step, "original") for name, step in prefix] + [
        (name, step, "restart") for name, step in restarted
    ]


def verify(original, restart, joined, include_history):
    expected = expected_steps(original, restart)
    if list(joined.steps.keys()) != [name for name, _, _ in expected]:
        raise ValueError(
            "Joined step sequence differs from original prefix + restart steps"
        )
    report = []
    for name, source, origin in expected:
        result = joined.steps[name]
        if (result.number, str(result.domain), result.totalTime) != (
            source.number,
            str(source.domain),
            source.totalTime,
        ):
            raise ValueError("Step metadata differs: " + name)
        if len(result.frames) != len(source.frames):
            raise ValueError("Frame count differs: " + name)
        for index in range(len(source.frames)):
            if _frame_signature(source.frames[index]) != _frame_signature(
                result.frames[index]
            ):
                raise ValueError(
                    "Frame time, field coverage or values differ: {0}, frame {1}".format(
                        name, index
                    )
                )
        # Without `history`, restartjoin removes history from the whole result,
        # including retained original steps (Abaqus 2025 real-run verified).
        if include_history:
            if _history_signature(source) != _history_signature(result):
                raise ValueError("History output differs: " + name)
        elif any(
            len(region.historyOutputs) for region in result.historyRegions.values()
        ):
            raise ValueError("History output unexpectedly retained: " + name)
        report.append(
            {
                "name": name,
                "source": origin,
                "frames": len(source.frames),
                "history_checked": True,
                "history_policy": "preserved" if include_history else "omitted",
            }
        )
        print("Verified step {0}: {1} frames".format(name, len(source.frames)))
        sys.stdout.flush()
    return report


def main():
    from odbAccess import openOdb

    original_path, restart_path, joined_path, history, report_path = sys.argv[1:]
    opened = []
    try:
        for path in (original_path, restart_path, joined_path):
            opened.append(openOdb(path=path, readOnly=True))
        steps = verify(opened[0], opened[1], opened[2], history == "1")
    finally:
        close_error = None
        for odb in reversed(opened):
            try:
                odb.close()
            except Exception as error:  # noqa: BLE001 - still close every other ODB.
                close_error = close_error or error
        if close_error is not None:
            raise close_error
    payload = {
        "schemaVersion": 1,
        "status": "verified",
        "joinedPath": os.path.abspath(joined_path),
        "originalPath": os.path.abspath(original_path),
        "restartPath": os.path.abspath(restart_path),
        "includeHistory": history == "1",
        "steps": steps,
        "checks": ["step-order", "frame-time", "field-values-and-locations", "history"],
    }
    with open(report_path, "w") as stream:
        json.dump(payload, stream, indent=2)
    print("ABASUB_ODB_VALIDATION_OK")


if __name__ == "__main__":
    main()
