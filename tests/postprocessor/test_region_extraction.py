from types import SimpleNamespace as NS
import os

import pytest

from modules.postprocessor.abaqus_scripts.region_extract_core import extract_rows, source_identity, require_source_identity


def test_source_guard_rejects_same_size_rewrite_even_with_restored_mtime(tmp_path):
    source = tmp_path / "input.odb"
    source.write_bytes(b"original")
    original_stat = source.stat()
    expected = source_identity(source)
    assert set(expected) == {"size", "mtimeNs", "sampledSha256"}
    source.write_bytes(b"modified")
    os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    with pytest.raises(RuntimeError, match="Source ODB changed"):
        require_source_identity(source, expected)


def test_source_guard_does_not_compare_windows_path_and_handle_ctime(tmp_path, monkeypatch):
    from modules.postprocessor.abaqus_scripts import region_extract_core
    source = tmp_path / "input.odb"
    source.write_bytes(b"original")
    expected = source_identity(source)
    real_fstat = os.fstat
    def fstat(fd):
        value = real_fstat(fd)
        return NS(st_size=value.st_size, st_mtime_ns=value.st_mtime_ns,
                  st_ctime_ns=value.st_ctime_ns + 100, st_dev=value.st_dev, st_ino=value.st_ino)
    monkeypatch.setattr(region_extract_core.os, "fstat", fstat)
    assert source_identity(source) == expected


def fixture(kind="T3D2"):
    instance = NS(name="A", elements=[NS(label=1, type=kind)], elementSets={}, sectionAssignments=[])
    value = NS(data=(12.,), instance=instance, elementLabel=1, integrationPoint=1,
               position="INTEGRATION_POINT", sectionPoint=NS(number=0))
    field = NS(componentLabels=("S11",), getSubset=lambda **kw: NS(values=[value], componentLabels=field.componentLabels))
    odb = NS(rootAssembly=NS(instances={"A": instance}), sections={},
             steps={"Load": NS(frames=[NS(frameValue=1., fieldOutputs={"S": field})])})
    request = {"region": {"scope": "instance", "kind": "instance", "instance": "A", "name": "A"},
               "method": "truss_reference_area", "acknowledgeReferenceArea": True,
               "referenceAreaOverride": 10., "frames": [{"step": "Load", "index": 0}]}
    return odb, request, value, field


def test_reference_area_is_explicit_and_traceable():
    odb, request, _, _ = fixture()
    row, = extract_rows(odb, request)
    assert row["value"] == 120.
    assert row["area_source"] == "explicit_uniform_override"
    assert row["component"] == "N_reference_area"
    assert row["instance"] == "A"
    assert row["convention"] == "S11_times_reference_area_not_current_area"


def test_missing_area_is_not_guessed():
    odb, request, _, _ = fixture()
    del request["referenceAreaOverride"]
    with pytest.raises(ValueError, match="No section area"):
        list(extract_rows(odb, request))


def test_truss_subset_has_different_components_than_mixed_global_stress_field():
    odb, request, value, field = fixture()
    field.componentLabels = ("S11", "S22", "S33", "S12", "S13", "S23")
    value.data = (12., 0., 0.)
    field.getSubset = lambda **kw: NS(values=[value], componentLabels=("S11", "S22", "S12"))
    row, = extract_rows(odb, request)
    assert row["value"] == 120.


def test_stored_section_area_is_used():
    odb, request, _, _ = fixture()
    del request["referenceAreaOverride"]
    instance = odb.rootAssembly.instances["A"]
    instance.sectionAssignments = [NS(sectionName="bar", region=NS(elements=instance.elements))]
    odb.sections["bar"] = NS(area=5.)
    row, = extract_rows(odb, request)
    assert row["value"] == 60.
    assert row["area_source"] == "odb_section:bar"


@pytest.mark.parametrize("change", [
    {"acknowledgeReferenceArea": False}, {"referenceAreaOverride": float("nan")},
    {"referenceAreaOverride": True}, {"referenceAreaOverride": -1},
    {"frames": []}, {"frames": [{"step": "Load", "index": True}]},
    {"frames": [{"step": "Load", "index": 0}, {"step": "Load", "index": 0}]},
])
def test_invalid_request_rejected(change):
    odb, request, _, _ = fixture()
    request.update(change)
    with pytest.raises(ValueError):
        list(extract_rows(odb, request))


def test_solid_or_shell_stress_is_not_mislabelled_as_axial_force():
    for kind in ("C3D8R", "S4R"):
        odb, request, _, _ = fixture(kind)
        with pytest.raises(ValueError, match="incompatible"):
            list(extract_rows(odb, request))


def test_missing_frame_output_does_not_become_zero():
    odb, request, _, _ = fixture()
    odb.steps["Load"].frames[0].fieldOutputs = {}
    with pytest.raises(ValueError, match="Missing S"):
        list(extract_rows(odb, request))


def test_partial_region_output_does_not_pass_as_complete():
    odb, request, _, _ = fixture()
    odb.rootAssembly.instances["A"].elements.append(NS(label=2, type="T3D2"))
    with pytest.raises(ValueError, match="every selected element"):
        list(extract_rows(odb, request))


def test_complex_and_nonfinite_output_rejected():
    odb, request, value, field = fixture()
    field.isComplex = True
    with pytest.raises(ValueError, match="Complex"):
        list(extract_rows(odb, request))
    field.isComplex = False
    value.data = (float("inf"),)
    with pytest.raises(ValueError, match="Non-finite"):
        list(extract_rows(odb, request))


def test_beam_components_not_summed_or_transformed():
    odb, request, value, field = fixture("B31")
    request["method"] = "beam_sections"
    field.componentLabels = ("SF1", "SF2", "SM1", "SM2", "SM3")
    value.data = (10., 2., -3., 4., 5.)
    odb.steps["Load"].frames[0].fieldOutputs = {"SF": field}
    rows = list(extract_rows(odb, request))
    assert [(row["component"], row["value"]) for row in rows] == list(zip(field.componentLabels, value.data))
    assert all(row["convention"] == "abaqus_local_section_axes" for row in rows)


def test_beam_torque_only_does_not_satisfy_bending_output():
    odb, request, value, field = fixture("B31")
    request["method"] = "beam_sections"
    field.componentLabels = ("SF1", "SM3")
    value.data = (10., 5.)
    odb.steps["Load"].frames[0].fieldOutputs = {"SF": field}
    with pytest.raises(ValueError, match="bending"):
        list(extract_rows(odb, request))
