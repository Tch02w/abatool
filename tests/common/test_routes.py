from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from modules.routes import odb_candidate_for_job


def test_job_route_prefers_run_metadata() -> None:
    candidate = odb_candidate_for_job(
        {"work_dir": r"G:\jobs\case-a", "job_name": "foundation"},
        fallback_work_dir=r"G:\fallback",
        fallback_job_name="fallback",
    )

    assert candidate == Path(r"G:\jobs\case-a\foundation.odb")


def test_job_route_fills_missing_run_fields_from_fallbacks() -> None:
    assert odb_candidate_for_job(
        {"work_dir": r"G:\jobs\case-b"},
        fallback_job_name="restart-2",
    ) == Path(r"G:\jobs\case-b\restart-2.odb")
    assert odb_candidate_for_job(
        {"job_name": "foundation"},
        fallback_work_dir=r"G:\jobs\case-c",
    ) == Path(r"G:\jobs\case-c\foundation.odb")


def test_job_route_prefers_the_completed_archive_destination() -> None:
    assert odb_candidate_for_job(
        {
            "work_dir": r"G:\ssd\foundation",
            "archive_destination": r"G:\archive\foundation",
            "job_name": "foundation",
        }
    ) == Path(r"G:\archive\foundation\foundation.odb")
    assert odb_candidate_for_job(
        {
            "work_dir": r"G:\ssd\restart",
            "job_name": "restart",
            "queue_item": SimpleNamespace(
                archive_destination=r"G:\archive\restart"
            ),
        }
    ) == Path(r"G:\archive\restart\restart.odb")


def test_job_route_can_return_a_work_directory_without_a_job_name() -> None:
    assert odb_candidate_for_job(
        None,
        fallback_work_dir=r"G:\jobs",
    ) == Path(r"G:\jobs")


def test_job_route_rejects_missing_or_whitespace_only_work_directory() -> None:
    assert odb_candidate_for_job(None) is None
    assert odb_candidate_for_job({"work_dir": "   ", "job_name": "demo"}) is None
