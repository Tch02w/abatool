from copy import deepcopy
from types import SimpleNamespace as N

import pytest

from modules.postprocessor.abaqus_scripts.restore_odb_history import (
    _assembly_node_set,
    _channel_metadata,
    _location,
    _splice,
)
from modules.postprocessor.abaqus_scripts.validate_odb_merge import (
    ExtraInitialHistoryZero,
    _verify_history_series,
    field_signature,
    main,
    verify,
)


def test_only_extra_initial_real_zero_on_empty_parent_can_be_rebuilt():
    resumed = ((0.3, 1.1), (0.4, -23.0))
    with pytest.raises(ExtraInitialHistoryZero):
        _verify_history_series(None, resumed, ((0.0, 0.0),) + resumed, "U / RF / data")
    for child, candidate, label in [
        (resumed, ((0.0, 0.0), (0.3, 9.1), resumed[-1]), "U / RF / data"),
        (resumed, ((0.0, 7.0),) + resumed, "U / RF / data"),
        (resumed, ((0.0, 0.0),) + resumed, "U / RF / conjugateData"),
        (((0.0, 1.0),), ((0.0, 0.0), (0.0, 1.0)), "U / RF / data"),
    ]:
        with pytest.raises(ValueError) as error:
            _verify_history_series(None, child, candidate, label)
        assert not isinstance(error.value, ExtraInitialHistoryZero)


def test_rebuilt_history_uses_source_boundary_and_rejects_unsupported_location_or_data():
    assert _splice(((0.1, 3.0), (0.3, 6.0)), ((0.3, 5.0),)) == ((0.1, 3.0), (0.3, 5.0))
    with pytest.raises(ValueError, match="Missing continuation"):
        _splice(((0.2, 1.0),), None)
    with pytest.raises(ValueError, match="out of order"):
        _splice(((0.2, 1.0),), ((0.3, 2.0), (0.1, 2.0)))
    with pytest.raises(ValueError, match="complex"):
        _channel_metadata(N(name="RF", type="SCALAR", conjugateData=((0.5, 12.0),)))
    with pytest.raises(ValueError, match="load case"):
        _location(N(name="left", loadCase=N(name="case")), None)
    with pytest.raises(ValueError, match="Unsupported history location"):
        _location(
            N(name="left", position="NODAL", point=N(position="NODAL"), loadCase=None),
            None,
        )


@pytest.mark.parametrize(
    "node, element, surface",
    [(False, True, False), (True, True, False), (True, False, True)],
)
def test_history_region_needs_an_unambiguous_assembly_node_set(node, element, surface):
    tables = [
        {"same": object()} if present else {} for present in (node, element, surface)
    ]
    with pytest.raises(ValueError, match="ambiguous"):
        _assembly_node_set(
            N(nodeSets=tables[0], elementSets=tables[1], surfaces=tables[2]), "same"
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


def partial_time_step(increments, samples):
    output = step(6)
    output.frames = []
    for inc, t, value in increments:
        frame = step(6, value).frames[0]
        frame.incrementNumber, frame.frameValue = inc, t
        output.frames.append(frame)
    output.historyRegions = {
        "RP": N(historyOutputs={"RF": N(type="SCALAR", data=samples)})
    }
    return output


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "parent_frame_at_seam",
        "repeated_frame",
        "lost_prefix",
        "later_parent",
        "parent_history_at_seam",
        "shifted_history_time",
        "lost_history",
        "repeated_history",
        "fabricated_zero",
        "wrong_channel",
        "unexpected_conjugate_data",
        "inconsistent_start_time",
    ],
)
def test_partial_time_step_splices_each_observable_at_its_own_restart(fault):
    base = partial_time_step(
        [(0, 0.0, 1), (3, 0.3, 2), (4, 0.4, 3)], [(0.0, 1.0), (0.2, 2.0), (0.4, 4.0)]
    )
    child = partial_time_step(
        [(3, 0.3, 5), (6, 0.6, 6)], [(0.2, 3.0), (0.35, 5.0), (0.6, 6.0)]
    )
    result = partial_time_step(
        [(0, 0.0, 1), (3, 0.3, 5), (6, 0.6, 6)],
        [(0.0, 1.0), (0.2, 3.0), (0.35, 5.0), (0.6, 6.0)],
    )
    history = result.historyRegions["RP"].historyOutputs["RF"].data
    if fault == "parent_frame_at_seam":
        result.frames[1] = base.frames[1]
    elif fault == "repeated_frame":
        result.frames.insert(1, base.frames[1])
    elif fault == "lost_prefix":
        result.frames.pop(0)
    elif fault == "later_parent":
        result.frames[2] = base.frames[2]
    elif fault == "parent_history_at_seam":
        history[1] = (0.2, 2.0)
    elif fault == "shifted_history_time":
        history[2] = (0.34, 5.0)
    elif fault == "lost_history":
        history.pop(0)
    elif fault == "repeated_history":
        history.insert(1, (0.2, 2.0))
    elif fault == "fabricated_zero":
        base.historyRegions["RP"].historyOutputs["RF"].data = None
        history[0] = (0.0, 0.0)
    elif fault == "wrong_channel":
        result.historyRegions["RP"].historyOutputs["OTHER"] = N(type="SCALAR", data=[])
    elif fault == "unexpected_conjugate_data":
        result.historyRegions["RP"].historyOutputs["RF"].conjugateData = [(0.0, 0.0)]
    elif fault == "inconsistent_start_time":
        base.totalTime = 99.0
    args = (odb(U40D=base), odb(U40D=child), odb(U40D=result), True)
    if fault:
        with pytest.raises(ValueError):
            verify(*args)
    else:
        (info,) = verify(*args)
        assert (info["source"], info["frames"], info["retainedOriginalFrames"]) == (
            "original-prefix-and-restart",
            3,
            1,
        )


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
