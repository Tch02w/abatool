"""Opt-in real Abaqus acceptance. Use project Python; requires Abaqus/CAE.

Creates an isolated run directory. Retains all inputs, reports and worker logs,
and writes verification.json ONLY after every exact-value assertion passes.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--abaqus", required=True)
    parser.add_argument("--output-parent", required=True, type=Path)
    parser.add_argument("--source", type=Path, help="Reuse an existing fixture read-only")
    parser.add_argument("--cases", nargs="+", choices=("beam_all", "beam_local_set", "solid_local_set", "solid_assembly",
                                                      "solid_reverse", "solid_x", "solid_inclined", "solid_centroid"))
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    args.output_parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="known-region-", dir=args.output_parent.resolve()))
    print(str(work), flush=True)

    def run(name, command):
        with (work / (name + ".log")).open("w", encoding="utf-8") as log:
            result = subprocess.run(command, cwd=work, stdout=log, stderr=subprocess.STDOUT, check=False)
        if result.returncode:
            raise RuntimeError("Failed: " + name + "; inspect " + str(work))

    source = args.source.resolve() if args.source else work / "known.odb"
    if not args.source:
        run("create", [args.abaqus, "python", str(Path(__file__).with_name("create_region_fixture.py")), str(source)])
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if not args.source:
        marker = Path(str(source) + ".created.json")
        if not marker.is_file():
            raise RuntimeError("Fixture creation did not finish; inspect " + str(work / "create.log"))
        created = json.loads(marker.read_text(encoding="utf-8"))
        assert created == dict(status="created", sha256=source_hash, frames=2)
    worker = repo / "modules/postprocessor/abaqus_scripts/extract_region.py"
    cases = []
    for name, region in (
        ("beam_all", dict(scope="instance", kind="instance", instance="BEAM-1", name="BEAM-1")),
        ("beam_local_set", dict(scope="instance", kind="element_set", instance="BEAM-1", name="PICK")),
        ("solid_local_set", dict(scope="instance", kind="element_set", instance="SOLID-1", name="PICK")),
        ("solid_assembly", dict(scope="assembly", kind="element_set", instance="", name="SOLID-SET")),
        ("solid_reverse", dict(scope="instance", kind="instance", instance="SOLID-1", name="SOLID-1")),
        ("solid_x", dict(scope="instance", kind="instance", instance="SOLID-1", name="SOLID-1")),
        ("solid_inclined", dict(scope="instance", kind="instance", instance="SOLID-1", name="SOLID-1")),
        ("solid_centroid", dict(scope="instance", kind="instance", instance="SOLID-1", name="SOLID-1")),
    ):
        if args.cases and name not in args.cases:
            continue
        solid = name.startswith("solid")
        request = dict(path=str(source), method="solid_section" if solid else "beam_sections", region=region,
                       frames=[dict(step="Known", index=i) for i in (0, 1)])
        if solid:
            request["section"] = dict(origin=[0., 0., 0.], normal=[0., 0., 1.], offsets=[1., 2.],
                                      momentReference="point", momentPoint=[0., 0., 0.])
            if name == "solid_reverse":
                request["section"].update(origin=[0., 0., 4.], normal=[0., 0., -1.])
            elif name == "solid_x":
                request["section"].update(normal=[1., 0., 0.], offsets=[.5, 1.])
            elif name == "solid_inclined":
                request["section"].update(origin=[0., 0., 3.], normal=[1., 0., 1.], offsets=[0.])
            elif name == "solid_centroid":
                request["section"].update(momentReference="centroid", momentPoint=None)
        request_path = work / (name + ".json")
        request_path.write_text(json.dumps(request), encoding="utf-8")
        output = work / name
        command = ([args.abaqus, "cae", "noGUI=" + str(worker), "--"] if solid
                   else [args.abaqus, "python", str(worker)])
        run(name, command + ["--request", str(request_path), "--output", str(output)])
        receipt = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        assert receipt["status"] == "succeeded"
        assert receipt["aggregation"] == ("section_stress_integration" if solid else "none_per_element_per_output_location")
        with (output / "region_values.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        maximum_error = 0.
        assert len(rows) == (18 * len(request["section"]["offsets"]) if solid else 12 if "local" in name else 24)
        keys = set()
        for row in rows:
            frame = int(row["frame"])
            factor = frame + 1
            if solid:
                cut = int(row["cut_index"])
                # Independent analytic values: F=A*S*n, M=(centroid-reference) x F.
                z = 3. - cut if name == "solid_reverse" else cut + 1.
                force = (12., -18., 60.)
                moment = (90. + 18. * z, 12. * z - 60., -36.)
                plane = (0., 0., z)
                unit_normal = (0., 0., 1.)
                reference = (0., 0., 0.)
                if name == "solid_reverse":
                    force = tuple(-x for x in force)
                    moment = tuple(-x for x in moment)
                    unit_normal = (0., 0., -1.)
                elif name == "solid_x":
                    x = (.5, 1.)[cut]
                    force, moment = (0., 0., 24.), (36., -24. * x, 0.)
                    plane, unit_normal = (x, 0., 0.), (1., 0., 0.)
                elif name == "solid_inclined":
                    force, moment = (12., -18., 72.), (144., -48., -36.)
                    plane, unit_normal = (0., 0., 3.), (1. / math.sqrt(2.), 0., 1. / math.sqrt(2.))
                elif name == "solid_centroid":
                    moment, reference = (0., 0., 0.), (1., 1.5, z)
                torsion = sum(x * n for x, n in zip(moment, unit_normal))
                expected = dict(zip(("Fx", "Fy", "Fz", "Mx", "My", "Mz"), force + moment))
                expected.update(N_normal=sum(x * n for x, n in zip(force, unit_normal)), M_torsion=torsion,
                                M_bending_magnitude=math.sqrt(sum((x - torsion*n)**2 for x, n in zip(moment, unit_normal))))
                key = (frame, cut, row["component"])
                for axis, position, direction, ref in zip("xyz", plane, unit_normal, reference):
                    assert math.isclose(float(row["plane_" + axis]), position, abs_tol=1e-6)
                    assert math.isclose(float(row["normal_" + axis]), direction, abs_tol=1e-6)
                    assert math.isclose(float(row["moment_reference_" + axis]), ref, abs_tol=1e-5)
                assert row["section_point"] == ""
            else:
                element = int(row["element"])
                assert element in ((2,) if "local" in name else (1, 2))
                expected = (dict(SF1=101., SF2=12., SF3=-13., SM1=31., SM2=-32., SM3=33.) if element == 1
                            else dict(SF1=201., SF2=22., SF3=-23., SM1=41., SM2=-42., SM3=43.))
                key = (frame, element, row["component"])
            assert key not in keys
            keys.add(key)
            target = factor * expected[row["component"]]
            actual = float(row["value"])
            error = abs(actual - target)
            maximum_error = max(maximum_error, error)
            assert math.isclose(actual, target, abs_tol=1e-3, rel_tol=1e-5), (name, key, actual, target)
        cases.append(dict(name=name, rows=len(rows), maximumAbsoluteError=maximum_error))
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    report = dict(status="passed", cases=cases, sourceSha256Unchanged=source_hash,
                  scope="Synthetic prescribed ODB values, real production workers; no solver or native UI interaction")
    (work / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
