from __future__ import annotations

from pathlib import Path

from modules.submitter.local_job_execution import (
    LocalJobProcessController,
    _archive_result,
    _execution_command,
    _prepare_existing_results,
    _prepare_workspace,
)
from modules.submitter.models import QueueItem


def test_ssd_workspace_copies_input_and_restart_dependency_family(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    calculation_root = tmp_path / "ssd"
    source_dir.mkdir()
    calculation_root.mkdir()
    inp = source_dir / "phase2.inp"
    odb = source_dir / "phase1.odb"
    res = source_dir / "phase1.res"
    inp.write_text("*Heading\n*Restart, read\n", encoding="utf-8")
    odb.write_bytes(b"odb")
    res.write_bytes(b"res")
    item = QueueItem(
        inp_path=str(inp),
        source_inp_path=str(inp),
        job_name="phase2_custom",
        oldjob_path=str(odb),
        oldjob_name="phase1",
        run_mode="restart",
        calculation_root_dir=str(calculation_root),
        cores=8,
        memory="80%",
        abaqus_command="abq2026.bat",
    )

    prepared_inp, work_dir, oldjob_arg = _prepare_workspace(item)
    command = _execution_command(item, prepared_inp, oldjob_arg)

    assert prepared_inp == work_dir / inp.name
    assert prepared_inp.read_text(encoding="utf-8").startswith("*Heading")
    assert (work_dir / odb.name).read_bytes() == b"odb"
    assert (work_dir / res.name).read_bytes() == b"res"
    assert oldjob_arg == "phase1"
    assert "job=phase2_custom" in command
    assert 'input="phase2.inp"' in command
    assert "oldjob=phase1" in command
    assert "cpus=8" in command
    assert "memory=80%" in command
    assert "ask_delete=OFF" in command


def test_existing_result_policy_backups_without_touching_other_files(
    tmp_path: Path,
) -> None:
    odb = tmp_path / "case.odb"
    sta = tmp_path / "case.sta"
    msg = tmp_path / "case.msg"
    odb.write_bytes(b"old odb")
    sta.write_bytes(b"old sta")
    msg.write_bytes(b"keep")

    _prepare_existing_results(tmp_path, "case", "backup")

    assert not odb.exists()
    assert not sta.exists()
    assert msg.read_bytes() == b"keep"
    assert len(list(tmp_path.glob("case_bak_*.odb"))) == 1
    assert len(list(tmp_path.glob("case_bak_*.sta"))) == 1


def test_completed_ssd_workspace_moves_to_unique_archive_destination(
    tmp_path: Path,
) -> None:
    work_dir = tmp_path / "ssd" / "case"
    archive_root = tmp_path / "archive"
    work_dir.mkdir(parents=True)
    (work_dir / "case.inp").write_text("*Heading\n", encoding="utf-8")
    (work_dir / "case.odb").write_bytes(b"result")
    item = QueueItem(
        job_name="case",
        calculation_root_dir=str(tmp_path / "ssd"),
        archive_dir=str(archive_root),
        cleanup_after_archive=True,
    )

    destination, status, error = _archive_result(item, work_dir)

    assert status == "已归档"
    assert error == ""
    assert not work_dir.exists()
    assert (Path(destination) / "case.odb").read_bytes() == b"result"


def test_local_job_cancel_is_cooperative_and_does_not_force_kill() -> None:
    controller = LocalJobProcessController()

    controller.cancel()

    assert controller.cancel_requested is True
