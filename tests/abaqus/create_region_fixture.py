"""Create an artificial ODB for extractor acceptance, never run a solver.

Run with Abaqus Python; the caller must supply a NEW .odb path.
Values are deliberately prescribed, not claimed as a solved engineering model.
"""
import os
import sys
import json
import hashlib

from odbAccess import Odb
from abaqusConstants import (THREE_D, DEFORMABLE_BODY, TIME, VECTOR,
                            TENSOR_3D_FULL, INTEGRATION_POINT, NODAL)


def create(path):
    if os.path.exists(path):
        raise RuntimeError("Refusing to overwrite an existing ODB")
    odb = Odb(name="Known region values", path=path,
              description="Artificial extraction fixture; no solver results")
    try:
        beam = odb.Part(name="BEAM", embeddedSpace=THREE_D, type=DEFORMABLE_BODY)
        beam.addNodes(labels=(1, 2, 3), coordinates=((0., 0., 0.), (0., 0., 2.), (0., 0., 4.)))
        beam.addElements(labels=(1, 2), connectivity=((1, 2), (2, 3)), type="B31")
        beam_instance = odb.rootAssembly.Instance(name="BEAM-1", object=beam)
        beam_instance.ElementSetFromElementLabels(name="PICK", elementLabels=(2,))
        solid = odb.Part(name="SOLID", embeddedSpace=THREE_D, type=DEFORMABLE_BODY)
        solid.addNodes(labels=tuple(range(1, 9)), coordinates=(
            (0., 0., 0.), (2., 0., 0.), (2., 3., 0.), (0., 3., 0.),
            (0., 0., 4.), (2., 0., 4.), (2., 3., 4.), (0., 3., 4.)))
        solid.addElements(labels=(1,), connectivity=(tuple(range(1, 9)),), type="C3D8")
        solid_instance = odb.rootAssembly.Instance(name="SOLID-1", object=solid)
        solid_instance.ElementSetFromElementLabels(name="PICK", elementLabels=(1,))
        material = odb.Material(name="FIXTURE")
        material.Elastic(table=((1000., .3),))
        section = odb.HomogeneousSolidSection(name="FIXTURE", material="FIXTURE", thickness=1.)
        solid_instance.assignSection(region=solid_instance.elementSets["PICK"], section=section)
        odb.rootAssembly.ElementSetFromElementLabels(name="SOLID-SET", elementLabels=(("SOLID-1", (1,)),))
        step = odb.Step(name="Known", description="Prescribed field data", domain=TIME, timePeriod=1.)
        for frame_index, factor in enumerate((1., 2.)):
            frame = step.Frame(incrementNumber=frame_index, frameValue=float(frame_index))
            for name, labels, data in (
                ("SF", ("SF1", "SF2", "SF3"), ((101., 12., -13.), (201., 22., -23.))),
                ("SM", ("SM1", "SM2", "SM3"), ((31., -32., 33.), (41., -42., 43.))),
            ):
                field = frame.FieldOutput(name=name, description=name, type=VECTOR, componentLabels=labels)
                field.addData(position=INTEGRATION_POINT, instance=beam_instance, labels=(1, 2),
                              data=tuple(tuple(factor * x for x in row) for row in data))
            stress = frame.FieldOutput(name="S", description="Uniform stress", type=TENSOR_3D_FULL)
            stress.addData(position=INTEGRATION_POINT, instance=solid_instance, labels=(1,),
                           data=tuple((0., 0., factor * 10., 0., factor * 2., factor * -3.) for _ in range(8)))
            displacement = frame.FieldOutput(name="U", description="Zero displacement", type=VECTOR)
            for instance in (beam_instance, solid_instance):
                displacement.addData(position=NODAL, instance=instance,
                                     labels=tuple(node.label for node in instance.nodes),
                                     data=tuple((0., 0., 0.) for _ in instance.nodes))
            step.setDefaultDeformedField(displacement)
        odb.save()
    finally:
        odb.close()
    with open(path, "rb") as stream:
        digest = hashlib.sha256(stream.read()).hexdigest()
    with open(path + ".created.json", "x", encoding="utf-8") as stream:
        json.dump(dict(status="created", sha256=digest, frames=2), stream)


if __name__ == "__main__":
    create(os.path.abspath(sys.argv[1]))
