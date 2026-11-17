import csv
import importlib
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from modules.postprocessor.abaqus_scripts.solid_section_math import section_config, plane_origin, force_moment_components


def section(**changes):
    result = dict(origin=[0, 0, 0], normal=[0, 0, 2], offsets=[.5], momentReference="centroid", momentPoint=None)
    result.update(changes)
    return result


def test_plane_offsets_use_normalized_direction():
    config = section_config(section())
    assert config["normal"] == (0., 0., 1.)
    assert plane_origin(config, .5) == (0., 0., .5)
    assert force_moment_components((2, 3, 4), (5, 6, 7), config["normal"]) == (4., 7., math.hypot(5, 6))


@pytest.mark.parametrize("changes", [dict(normal=[0, 0, 0]), dict(normal=[True, 0, 1]),
    dict(offsets=[]), dict(offsets=[1, 1]), dict(offsets=[float("nan")]),
    dict(origin=[0, 0]), dict(momentReference="unknown"),
    dict(momentReference="point", momentPoint=None), dict(momentPoint=[0, 0, 0])])
def test_invalid_sections_rejected(changes):
    with pytest.raises(ValueError):
        section_config(section(**changes))


@pytest.fixture
def cae(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "modules/postprocessor/abaqus_scripts"))
    core = importlib.import_module("region_solid_core")
    settings = {}
    cuts = []
    def update(**kwargs):
        settings.update(kwargs)
    display = NS(display=NS(setValues=update), displayGroup=NS(replace=update),
                 viewCutOptions=NS(setValues=update), viewCuts={}, setFrame=update, setValues=update)
    def new_cut(**kwargs):
        record = dict(kwargs)
        cuts.append(record)
        cut = NS(cutRange=(-.5, .5), setValues=lambda **values: record.update(values))
        display.viewCuts[kwargs["name"]] = cut
        return cut
    display.ViewCut = new_cut
    viewport = NS(odbDisplay=display, makeCurrent=lambda: None, setValues=update)
    def report(**kwargs):
        with open(kwargs["fileName"], "w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["StepName", "FrameId", "Fx", "Fy", "Fz", "Mx", "My", "Mz", "CutX", "CutY", "CutZ"])
            writer.writerow(["Load", 0, 2, 3, 4, 5, 6, 7, .5, .5, .5])
    session = NS(Viewport=lambda **kw: viewport, freeBodyReportOptions=NS(setValues=update), writeFreeBodyReport=report)
    monkeypatch.setitem(sys.modules, "abaqus", NS(session=session))
    constants = "OFF ON UNDEFORMED PLANE CURRENT_DISPLAY_GROUP CSYS GLOBAL SCIENTIFIC COMMA_SEPARATED_VALUES SPECIFY CENTROID".split()
    monkeypatch.setitem(sys.modules, "abaqusConstants", NS(**{name: name for name in constants}))
    monkeypatch.setitem(sys.modules, "visualization", NS())
    dgo = NS(LeafFromPartInstance=lambda **kw: kw, LeafFromElementSets=lambda **kw: kw, LeafFromElementLabels=lambda **kw: kw)
    monkeypatch.setitem(sys.modules, "displayGroupOdbToolset", dgo)
    points = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
    element = NS(label=1, type="C3D8R", connectivity=tuple(range(1, 9)))
    instance = NS(name="A", elements=[element], nodes=[NS(label=i+1, coordinates=point) for i, point in enumerate(points)],
                  getElementFromLabel=lambda label: element)
    value = NS(instance=instance, elementLabel=1, position="INTEGRATION_POINT", data=(1, 2, 3, 0, 0, 0))
    field = NS(getSubset=lambda **kw: NS(values=[value]), isComplex=False)
    odb = NS(rootAssembly=NS(instances={"A": instance}), steps={"Load": NS(frames=[NS(frameValue=1., fieldOutputs={"S": field})])})
    request = dict(region=dict(scope="instance", instance="A", kind="instance", name="A"),
                   frames=[dict(step="Load", index=0)], section=section())
    return core, odb, request, tmp_path, settings, cuts


def test_solid_worker_keeps_plane_and_moment_reference_distinct(cae):
    core, odb, request, output, settings, cuts = cae
    rows = list(core.extract_solid_rows(odb, request, str(output)))
    assert len(rows) == 9
    assert cuts[0]["position"] == 0.
    assert cuts[0]["origin"] == (0., 0., .5)
    assert rows[0]["plane_x"] == 0
    assert rows[0]["moment_reference_x"] == .5
    assert rows[0]["cut_index"] == 0 and rows[0]["section_point"] == ""
    assert settings["leaf"] == {"partInstanceName": ("A",)}
    assert settings["freeBodyCutThru"] == "CURRENT_DISPLAY_GROUP"
    assert next(row["value"] for row in rows if row["component"] == "N_normal") == 4.


def test_plane_missing_selected_elements_rejected(cae):
    core, odb, request, output, _, cuts = cae
    request["section"]["offsets"] = [2.]
    with pytest.raises(ValueError, match="does not intersect"):
        list(core.extract_solid_rows(odb, request, str(output)))
    assert cuts == []


def test_wrong_solid_family_rejected(cae):
    core, odb, request, output, _, _ = cae
    odb.rootAssembly.instances["A"].elements[0].type = "S4R"
    with pytest.raises(ValueError, match="solid elements"):
        list(core.extract_solid_rows(odb, request, str(output)))
