from copy import deepcopy
from types import SimpleNamespace as N

import pytest

from modules.postprocessor.abaqus_scripts.validate_odb_merge import (
    field_signature,
    main,
    verify,
)


def step(number, value=1.0, name="S"):
    block = N(
        instance=N(name="PART-1"),
        position="INTEGRATION_POINT",
        sectionPoint=N(number=0),
        componentLabels=("S11",),
        data=((value,),),
        elementLabels=(1,),
        integrationPoints=(1,),
    )
    field = N(type="SCALAR", componentLabels=("S11",), bulkDataBlocks=[block])
    frame = N(frameValue=1.0, incrementNumber=10, fieldOutputs={name: field})
    return N(
        number=number,
        totalTime=float(number - 1),
        domain="TIME",
        frames=[frame],
        historyRegions={},
    )


def odb(**steps):
    return N(steps=steps)


def test_valid_join_retains_original_and_restart_frames():
    base, restart = odb(Base=step(1)), odb(Restart=step(2))
    joined = odb(**deepcopy({**base.steps, **restart.steps}))
    report = verify(base, restart, joined, True)
    assert [entry["source"] for entry in report] == ["original", "restart"]


@pytest.mark.parametrize(
    "change",
    [
        "missing_step",
        "frame_count",
        "field_value",
        "field_name",
        "location",
        "time",
        "metadata",
    ],
)
def test_rejects_noop_or_corrupted_join(change):
    base, restart = odb(Base=step(1)), odb(Restart=step(2))
    joined = odb(**deepcopy({**base.steps, **restart.steps}))
    if change == "missing_step":
        del joined.steps["Restart"]
    elif change == "frame_count":
        joined.steps["Restart"].frames.clear()
    elif change == "field_value":
        joined.steps["Restart"].frames[0].fieldOutputs["S"].bulkDataBlocks[0].data = (
            (9.0,),
        )
    elif change == "field_name":
        joined.steps["Restart"].frames[0].fieldOutputs.clear()
    elif change == "location":
        joined.steps["Restart"].frames[0].fieldOutputs["S"].bulkDataBlocks[
            0
        ].elementLabels = (2,)
    elif change == "time":
        joined.steps["Restart"].frames[0].frameValue = 2.0
    else:
        joined.steps["Restart"].number = 9
    with pytest.raises(ValueError):
        verify(base, restart, joined, True)


def test_midstep_restart_replaces_overlap_and_drops_abandoned_later_steps():
    base = odb(Base=step(1), Loading=step(2, value=1.0), Abandoned=step(3))
    restart = odb(Loading=step(2, value=9.0), New=step(3))
    joined = odb(Base=deepcopy(base.steps["Base"]), **deepcopy(restart.steps))
    assert len(verify(base, restart, joined, True)) == 3
    joined.steps["Loading"] = deepcopy(base.steps["Loading"])
    with pytest.raises(ValueError, match="field coverage or values"):
        verify(base, restart, joined, True)


def test_history_option_and_empty_uncomputed_future_step():
    base, restart = odb(Base=step(1)), odb(Restart=step(2), Future=step(3))
    restart.steps["Future"].frames.clear()
    restart.steps["Restart"].historyRegions = {
        "RP": N(historyOutputs={"RF": N(type="SCALAR", data=((0.0, 0.0), (1.0, 2.0)))})
    }
    joined = odb(**deepcopy({**base.steps, **restart.steps}))
    assert verify(base, restart, joined, True)[-1]["frames"] == 0
    joined.steps["Restart"].historyRegions.clear()
    with pytest.raises(ValueError, match="History output"):
        verify(base, restart, joined, True)
    verify(base, restart, joined, False)
    restart.steps["Restart"].frames.clear()
    with pytest.raises(ValueError, match="no result frames"):
        verify(base, restart, joined, False)


def test_history_disabled_removes_original_history_too():
    base, restart = odb(Base=step(1)), odb(Restart=step(2))
    base.steps["Base"].historyRegions = {
        "RP": N(historyOutputs={"RF": N(type="SCALAR", data=((0.0, 1.0),))})
    }
    joined = odb(**deepcopy({**base.steps, **restart.steps}))
    with pytest.raises(ValueError, match="unexpectedly retained"):
        verify(base, restart, joined, False)
    joined.steps["Base"].historyRegions.clear()
    report = verify(base, restart, joined, False)
    assert all(entry["history_policy"] == "omitted" for entry in report)
    with pytest.raises(ValueError, match="History output differs"):
        verify(base, restart, joined, True)


def test_double_precision_fallback_checks_values_and_axes():
    class DoubleValue(N):
        @property
        def data(self):
            raise RuntimeError("Double precision")

        @property
        def localCoordSystem(self):
            raise RuntimeError("Double precision")

    class DoubleField(N):
        @property
        def bulkDataBlocks(self):
            raise RuntimeError("Double precision")

    value = DoubleValue(
        instance=N(name="PART-1"),
        position="NODAL",
        nodeLabel=1,
        dataDouble=(1.234567890123,),
        localCoordSystemDouble=(),
    )
    field = DoubleField(type="SCALAR", componentLabels=(), values=[value])
    saved = field_signature(field)
    assert saved[2] == "values"
    value.dataDouble = (1.234567890124,)
    assert field_signature(field) != saved
    value.dataDouble = (1.234567890123,)
    value.localCoordSystemDouble = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    assert field_signature(field) != saved


def test_close_failure_closes_every_odb_and_emits_no_success(
    tmp_path, monkeypatch, capsys
):
    import sys

    base, restart = odb(Base=step(1)), odb(Restart=step(2))
    joined = odb(**deepcopy({**base.steps, **restart.steps}))
    databases = [base, restart, joined]
    closed = []

    def close(index):
        closed.append(index)
        if index == 2:
            raise RuntimeError("Close failed")

    for index, database in enumerate(databases):
        database.close = lambda index=index: close(index)
    remaining = iter(databases)
    report = tmp_path / "report.json"
    monkeypatch.setitem(
        sys.modules, "odbAccess", N(openOdb=lambda **kwargs: next(remaining))
    )
    monkeypatch.setattr(
        sys, "argv", ["validate", "original", "restart", "joined", "1", str(report)]
    )
    with pytest.raises(RuntimeError, match="Close failed"):
        main()
    assert closed == [2, 1, 0]
    assert not report.exists()
    assert "ABASUB_ODB_VALIDATION_OK" not in capsys.readouterr().out
