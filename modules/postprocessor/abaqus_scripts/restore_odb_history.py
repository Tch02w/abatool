"""Write supported real time histories into a field-only private restartjoin result."""

import hashlib
import sys
from contextlib import closing

import numpy as np


def _node_set_identity(region_set):
    """Check set kind, instance namespaces, node order, labels and coordinates."""
    instances = tuple(region_set.instanceNames or ())
    groups = region_set.nodes
    if (
        not instances
        or len(instances) != len(groups)
        or not any(len(nodes) for nodes in groups)
    ):
        raise ValueError("Unsupported history set: " + region_set.name)
    digest = hashlib.sha256()
    for nodes in groups:
        digest.update(np.asarray([len(nodes)], dtype="<i8").tobytes())
        for node in nodes:
            digest.update(np.asarray([node.label], dtype="<i8").tobytes())
            digest.update(np.asarray(node.coordinates, dtype="<f8").tobytes())
    return region_set.name, bool(region_set.isInternal), instances, digest.digest()


def _assembly_node_set(assembly, name):
    # Set names alone do not identify the kind of entity to which a history refers.
    if (
        name not in assembly.nodeSets
        or name in assembly.elementSets
        or name in assembly.surfaces
    ):
        raise ValueError("Missing or ambiguous assembly node set: " + name)
    return assembly.nodeSets[name]


def _location(region, assembly):
    if region.loadCase is not None or region.position != region.point.position:
        raise ValueError("Unsupported history point or load case: " + region.name)
    position = str(region.position)
    if position == "WHOLE_MODEL" and region.point.assembly is not None:
        if region.point.assembly.name != assembly.name:
            raise ValueError("Unexpected history assembly: " + region.name)
        return position, region.point.assembly.name
    if position == "WHOLE_REGION" and region.point.region is not None:
        point_set = region.point.region
        canonical = _assembly_node_set(assembly, point_set.name)
        identity = _node_set_identity(canonical)
        if _node_set_identity(point_set) != identity:
            raise ValueError(
                "Source history point differs from node set: " + point_set.name
            )
        return position, identity
    raise ValueError("Unsupported history location: " + region.name)


def _channel_metadata(channel):
    invariants = tuple(getattr(channel, "validInvariants", ()) or ())
    if str(channel.type) != "SCALAR" or invariants or len(channel.conjugateData or ()):
        raise ValueError("Unsupported complex or non-scalar history: " + channel.name)
    return channel.name, channel.description, str(channel.type)


def check_locations(source, result, source_assembly, result_assembly):
    for key, region in source.historyRegions.items():
        target = result.historyRegions[key]
        if (region.name, region.description, _location(region, source_assembly)) != (
            target.name,
            target.description,
            _location(target, result_assembly),
        ):
            raise ValueError("Saved history point or description differs: " + key)
        for name, channel in region.historyOutputs.items():
            if _channel_metadata(channel) != _channel_metadata(
                target.historyOutputs[name]
            ):
                raise ValueError("Saved history channel metadata differs: " + name)


def _splice(parent, child):
    for values in (parent, child):
        if not values:
            continue
        times = np.asarray(values)[:, 0]
        if not np.isfinite(times).all() or np.any(np.diff(times) < 0):
            raise ValueError("Continuation history times are out of order")
    if not parent:
        return child
    if not child:
        raise ValueError("Missing continuation history samples")
    keep = int(np.searchsorted(np.asarray(parent)[:, 0], child[0][0], side="left"))
    return parent[:keep] + child


def _write_region(step, assembly, source, source_assembly, parent, parent_assembly):
    from odbAccess import HistoryPoint

    position, key = _location(source, source_assembly)
    if parent is not None:
        if (
            _location(parent, parent_assembly) != (position, key)
            or parent.description != source.description
        ):
            raise ValueError("Continuation history point differs: " + source.name)
        if set(parent.historyOutputs.keys()) - set(source.historyOutputs.keys()):
            raise ValueError("Missing continuation history channels: " + source.name)
    if position == "WHOLE_MODEL":
        if assembly.name != key:
            raise ValueError("Target history assembly differs: " + source.name)
        point = HistoryPoint(assembly=assembly)
    else:
        name = key[0]
        target_set = _assembly_node_set(assembly, name)
        if _node_set_identity(target_set) != key:
            raise ValueError("Target node set differs: " + name)
        point = HistoryPoint(region=target_set)
    target = step.HistoryRegion(
        name=source.name, description=source.description, point=point
    )
    for name, channel in source.historyOutputs.items():
        metadata = _channel_metadata(channel)
        prior_data = None
        if parent is not None and name in parent.historyOutputs:
            prior = parent.historyOutputs[name]
            if _channel_metadata(prior) != metadata:
                raise ValueError("Continuation history channel differs: " + name)
            prior_data = prior.data
        data = _splice(prior_data, channel.data)
        output = target.HistoryOutput(
            name=name, description=channel.description, type=channel.type
        )
        if data:
            output.addData(data=data)


def restore(original, restart, joined):
    # The controller stages its read-only verifier under this name beside this worker.
    from validate_joined_odb import _continued_step, expected_steps

    for name, source, origin in expected_steps(original, restart):
        step = joined.steps[name]
        if str(source.domain) != "TIME" or len(step.historyRegions):
            raise ValueError("Expected an empty time-domain history: " + name)
        prior = _continued_step(original, restart, name)
        old_regions = {} if prior is None else dict(prior.historyRegions.items())
        if set(old_regions.keys()) - set(source.historyRegions.keys()):
            raise ValueError("Missing continuation history regions: " + name)
        for key, region in source.historyRegions.items():
            source_db = original if origin == "original" else restart
            _write_region(
                step,
                joined.rootAssembly,
                region,
                source_db.rootAssembly,
                old_regions.get(key),
                original.rootAssembly,
            )


def main():
    from odbAccess import openOdb

    original_path, restart_path, joined_path = sys.argv[1:]

    def database(path, read_only=True):
        return closing(openOdb(path=path, readOnly=read_only, readInternalSets=True))

    with (
        database(original_path) as old,
        database(restart_path) as new,
        database(joined_path, False) as result,
    ):
        restore(old, new, result)
        result.save()
    print("ABASUB_ODB_HISTORY_RESTORED")


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        import json

        print("ABASUB_ODB_RESTORE_FAILED|" + json.dumps(str(error), ensure_ascii=True))
        sys.stdout.flush()
        raise
