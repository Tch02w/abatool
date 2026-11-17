import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from modules.postprocessor.postprocess_execution import suggested_job_from_scan


@pytest.fixture
def scanner(monkeypatch):
    monkeypatch.setitem(sys.modules, "odbAccess", NS(openOdb=None))
    path = Path(__file__).parents[2] / "modules/postprocessor/abaqus_scripts/scan_odb_core.py"
    spec = importlib.util.spec_from_file_location("test_scan_core", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_odb():
    node = NS(label=1, coordinates=(2., 3.))
    element = NS(label=1, type="T3D2")
    nodes = NS(nodes=[node])
    elements = NS(elements=[element], name="SAME")
    instance = NS(nodes=[node], elements=[element], nodeSets={"SAME": nodes},
                  elementSets={"SAME": elements}, sectionAssignments=[NS(region=elements, sectionName="bar")])
    field = NS(componentLabels=("S11",), type="TENSOR_3D_FULL", locations=[NS(position="INTEGRATION_POINT")])
    return NS(
        rootAssembly=NS(nodeSets={"SAME": NS(nodes=([node],))}, elementSets={"SAME": NS(elements=([element],))},
                        instances={"A": instance, "B": instance}),
        steps={"Load": NS(frames=[NS(frameValue=0., fieldOutputs={}), NS(frameValue=1., fieldOutputs={"S": field})], historyRegions={})},
        sections={"bar": NS(material="steel", area=10.)}, close=lambda: None)


def test_scoped_regions_preserve_same_names_and_repeated_labels(scanner):
    catalog = scanner.structure_catalog(fake_odb())
    assert len(catalog["regions"]) == 8
    assert len({item["id"] for item in catalog["regions"]}) == 8
    assert sum(item["elementCount"] for item in catalog["regions"]) == 5
    assert catalog["sectionAssignments"] == [
        {"instance": "A", "region": "SAME", "section": "bar"},
        {"instance": "B", "region": "SAME", "section": "bar"}]
    assert catalog["sections"][0]["area"] == 10.


def test_availability_is_per_frame_without_reading_values(scanner):
    catalog = scanner.structure_catalog(fake_odb())
    frames = catalog["steps"][0]["frames"]
    assert frames[0]["fields"] == []
    assert frames[1]["fields"][0]["components"] == ["S11"]
    assert frames[1]["fields"][0]["positions"] == ["INTEGRATION_POINT"]
    assert catalog["fieldAvailability"] == "frame_only_not_region_validated"


def test_scan_read_only_and_catalog_reaches_api(scanner, tmp_path):
    path = tmp_path / "test.odb"
    path.write_bytes(b"fake")
    odb = fake_odb()
    closed = []
    odb.close = lambda: closed.append(True)
    opened = []
    def open_odb(path, **options):
        opened.append(options)
        return odb
    scanner.openOdb = open_odb
    scan = scanner.inspect_odb(str(path))
    assert scan["error"] == ""
    assert opened == [{"readOnly": True}]
    assert closed == [True]
    assert scan["set_details"]["SAME"]["bbox"]["z"] == [0., 0.]
    api = suggested_job_from_scan(scan, {})
    assert api["structureCatalog"] == scan["structure_catalog"]


def test_scan_closes_on_metadata_error(scanner, tmp_path):
    odb = fake_odb()
    closed = []
    odb.sections = None
    odb.close = lambda: closed.append(True)
    scanner.openOdb = lambda *args, **kwargs: odb
    scan = scanner.inspect_odb(str(tmp_path / "test.odb"))
    assert scan["error"]
    assert closed == [True]


def test_empty_and_streamed_2d_bounds(scanner):
    assert scanner.bounding_box([]) is None
    assert scanner.bounding_box((NS(coordinates=point) for point in [(2, 3), (-1, 8)])) == {
        "x": [-1., 2.], "y": [3., 8.], "z": [0., 0.]}
