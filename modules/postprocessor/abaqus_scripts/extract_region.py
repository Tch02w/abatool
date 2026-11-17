"""Abaqus Python entry point. Publish only a fully validated CSV in a new folder."""

import argparse
import csv
import json
import os
import sys

from odbAccess import openOdb

script_file = globals().get("__file__")
if not script_file:
    script_file = next(value for value in sys.argv if value.lower().endswith("extract_region.py"))
    if script_file.lower().startswith("nogui="):
        script_file = script_file.split("=", 1)[1]
sys.path.insert(0, os.path.dirname(os.path.abspath(script_file)))
from region_extract_core import extract_rows, source_identity, require_source_identity


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    # CAE 2025 consumes "--" and appends its own -cae/-noGUI/-tmpdir flags.
    args = parser.parse_known_args(arguments)[0] if "-cae" in arguments and "-noGUI" in arguments else parser.parse_args(arguments)
    with open(args.request, "r", encoding="utf-8-sig") as stream:
        request = json.load(stream)
    source = os.path.abspath(request["path"])
    output = os.path.abspath(args.output)
    # No overwrite and no user-specified CSV filename to collide with a model.
    os.makedirs(output)
    pending = os.path.join(output, "region_values.pending.csv")
    destination = os.path.join(output, "region_values.csv")
    incomplete = os.path.join(output, "_postprocess_incomplete.json")
    with open(incomplete, "x", encoding="utf-8") as stream:
        json.dump({"kind": "region_extraction", "status": "running"}, stream)
    odb = None
    count = 0
    try:
        initial_identity = (require_source_identity(source, request["sourceIdentity"])
                            if request.get("sourceIdentity") is not None else source_identity(source))
        if request.get("method") == "solid_section":
            from abaqus import session
            from region_solid_core import extract_solid_rows
            odb = session.openOdb(name=source, readOnly=True)
            rows = extract_solid_rows(odb, request, output)
        else:
            odb = openOdb(source, readOnly=True)
            rows = extract_rows(odb, request)
        with open(pending, "w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=[
                "step", "frame", "frame_value", "instance", "element", "position",
                "integration_point", "section_point", "method", "component", "value",
                "area", "area_source", "convention", "cut_index", "plane_x", "plane_y", "plane_z",
                "normal_x", "normal_y", "normal_z", "moment_reference_x", "moment_reference_y", "moment_reference_z"])
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
                count += 1
        if not count:
            raise RuntimeError("Selected region produced no result rows")
        # Closing belongs to validation: a close failure must never leave a
        # published result. Clear the handle before closing to avoid retrying it.
        closing = odb
        odb = None
        closing.close()
        require_source_identity(source, initial_identity)
        # Every requested frame/element and the source must pass before publish.
        os.rename(pending, destination)
        report = {"schemaVersion": 1, "status": "succeeded", "source": source, "request": request,
                  "rows": count, "csv": destination, "units": "model_defined",
                  "sourceIdentity": initial_identity,
                  "aggregation": ("section_stress_integration" if request.get("method") == "solid_section"
                                  else "none_per_element_per_output_location")}
        with open(os.path.join(output, "manifest.json"), "x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        print(json.dumps({"status": "succeeded", "rows": count, "csv": destination}))
        os.remove(incomplete)
    except Exception as error:
        with open(os.path.join(output, "failure.json"), "x", encoding="utf-8") as stream:
            json.dump({"status": "failed", "error": str(error), "partialRows": count}, stream, ensure_ascii=False, indent=2)
        raise
    finally:
        if odb is not None:
            try:
                odb.close()
            except Exception as error:
                # Keep the primary extraction failure and its incomplete marker.
                print("ODB cleanup close failed: " + str(error), file=sys.stderr)


if __name__ == "__main__":
    main()
