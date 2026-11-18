from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from modules.control_plane.contracts import ApiProblem
from modules.control_plane.job_queue_commands import JobQueueService
from modules.submitter import external_job_scan_core
from modules.submitter.constants import STATUS_COMPLETED, STATUS_UNKNOWN
from modules.submitter.queue_store import save_joblist_state
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_local_queue_runtime_api import queue_item


@pytest.mark.parametrize("manual", [False, True])
def test_slow_external_scan_does_not_block_queue_reads(tmp_path, manual):
    item = queue_item(tmp_path, "case")
    item.status = STATUS_UNKNOWN
    item.effective_work_dir = str(tmp_path)
    path = tmp_path / "joblist.json"
    save_joblist_state([], [item], path)
    entered, release = threading.Event(), threading.Event()

    def scanner(root, known):
        entered.set()
        assert release.wait(15)
        return [], []

    service = JobQueueService(path, external_job_scanner=scanner, external_monitor_interval=999)
    service.observe_recovered_directories([str(tmp_path)])
    with ThreadPoolExecutor(max_workers=2) as pool:
        scan = pool.submit(service.execute, {"schemaVersion": 1, "action": "scanExternalJobs", "root": str(tmp_path)}) if manual else pool.submit(service.refresh_external_jobs)
        try:
            assert entered.wait(5)
            read = pool.submit(service.snapshot)
            snapshot = read.result(timeout=1)
            assert snapshot["queueItems"][0]["itemId"] == item.item_id and snapshot["externalScanActive"]
        finally:
            release.set()
            scan.result(timeout=10)
            service.close()


@pytest.mark.parametrize("change", ["attempt", "remove", "replace", "selection", "candidate"])
def test_scan_result_cannot_overwrite_newer_queue_state(tmp_path, change):
    item = queue_item(tmp_path, "case")
    item.status, item.effective_work_dir = STATUS_UNKNOWN, str(tmp_path)
    path = tmp_path / "joblist.json"
    save_joblist_state([], [item], path)
    entered, release = threading.Event(), threading.Event()

    def scanner(root, known):
        entered.set()
        assert release.wait(15)
        return [{"job_name": "case", "work_dir": root, "runtime_status": STATUS_COMPLETED,
                 "runtime_message": "old scan", "status_only_update": True}], []

    service = JobQueueService(path, external_job_scanner=scanner, external_monitor_interval=999)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.execute, {"schemaVersion": 1, "action": "scanExternalJobs", "root": str(tmp_path)})
        try:
            assert entered.wait(5)

            def mutate(candidates, items):
                if change == "attempt":
                    items[0].attempt_id, items[0].message = "new-attempt", "new execution"
                elif change == "remove":
                    items.clear()
                elif change == "replace":
                    items[:] = [queue_item(tmp_path, "case")]
                elif change == "selection":
                    items[0].selected = True
                else:
                    candidates.append(queue_item(tmp_path, "candidate"))
            service.runtime_transaction(mutate)
            release.set()
            result = future.result(timeout=10)
            current = service.runtime_items()
            if change == "candidate":
                assert len(current[0]) == 1 and current[1][0].status == STATUS_COMPLETED
                assert result["changed"] == 1
            else:
                assert result["changed"] == 0 and result["stats"]["staleResultsSkipped"] == 1
                if change == "remove":
                    assert not current[1]
                else:
                    assert current[1][0].status != STATUS_COMPLETED
                    if change == "attempt":
                        assert current[1][0].attempt_id == "new-attempt" and current[1][0].message == "new execution"
                    elif change == "replace":
                        assert current[1][0].item_id != item.item_id
                    else:
                        assert current[1][0].selected
        finally:
            release.set()
            service.close()


def test_duplicate_scan_and_close_do_not_wait_or_publish_late_results(tmp_path):
    path = tmp_path / "joblist.json"
    save_joblist_state([], [], path)
    entered, release = threading.Event(), threading.Event()

    def scanner(root, known):
        entered.set()
        assert release.wait(15)
        return [{"job_name": "external", "work_dir": root, "runtime_status": STATUS_COMPLETED}], []

    service = JobQueueService(path, external_job_scanner=scanner, external_monitor_interval=999)
    request = {"schemaVersion": 1, "action": "scanExternalJobs", "root": str(tmp_path)}
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.execute, request)
        try:
            assert entered.wait(5)
            with pytest.raises(ApiProblem) as error:
                service.execute(request)
            assert error.value.code == "EXTERNAL_SCAN_BUSY"
            service.refresh_external_jobs()
            service.close()
            release.set()
            with pytest.raises(ApiProblem) as error:
                future.result(timeout=10)
            assert error.value.code == "CONTROL_PLANE_SHUTTING_DOWN"
            assert not service.runtime_items()[1]
        finally:
            release.set()
            service.close()


def test_newly_discovered_job_does_not_duplicate_concurrent_user_entry(tmp_path):
    path = tmp_path / "joblist.json"
    save_joblist_state([], [], path)
    entered, release = threading.Event(), threading.Event()

    def scanner(root, known):
        entered.set()
        assert release.wait(15)
        return [{"job_name": "case", "work_dir": root, "pids": [123]}], []

    service = JobQueueService(path, external_job_scanner=scanner, external_monitor_interval=999)
    added = queue_item(tmp_path, "case")
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.execute, {"schemaVersion": 1, "action": "scanExternalJobs", "root": str(tmp_path)})
        try:
            assert entered.wait(5)
            service.runtime_transaction(lambda _, items: items.append(added))
            release.set()
            result = future.result(timeout=10)
            assert result["changed"] == 0 and result["stats"]["staleResultsSkipped"] == 1
            current = service.runtime_items()[1]
            assert len(current) == 1 and current[0].item_id == added.item_id and not current[0].is_external
        finally:
            release.set()
            service.close()


def test_failed_scan_preserves_queue_and_allows_retry(tmp_path):
    path = tmp_path / "joblist.json"
    save_joblist_state([], [queue_item(tmp_path, "case")], path)
    before = path.read_bytes()
    attempts = []

    def scanner(root, known):
        attempts.append(True)
        if len(attempts) == 1:
            raise OSError("process inspection failed")
        return [], []

    service = JobQueueService(path, external_job_scanner=scanner, external_monitor_interval=999)
    request = {"schemaVersion": 1, "action": "scanExternalJobs", "root": str(tmp_path)}
    try:
        with pytest.raises(OSError, match="process inspection failed"):
            service.execute(request)
        assert path.read_bytes() == before and not service.snapshot()["externalScanActive"]
        assert service.execute(request)["changed"] == 0 and len(attempts) == 2
    finally:
        service.close()


def test_log_diagnostics_do_not_hold_queue_lock(tmp_path, monkeypatch):
    item = queue_item(tmp_path, "case")
    item.status, item.effective_work_dir = STATUS_UNKNOWN, str(tmp_path)
    path = tmp_path / "joblist.json"
    save_joblist_state([], [item], path)
    entered, release = threading.Event(), threading.Event()

    def inspect(*_):
        entered.set()
        assert release.wait(15)
        return "", ""

    monkeypatch.setattr(external_job_scan_core, "inspect_job_files", inspect)
    service = JobQueueService(path, external_job_scanner=lambda *_: ([], []), external_monitor_interval=999)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(service.execute, {"schemaVersion": 1, "action": "scanExternalJobs", "root": str(tmp_path)})
        try:
            assert entered.wait(5)
            assert pool.submit(service.snapshot).result(timeout=1)["queueCount"] == 1
        finally:
            release.set()
            future.result(timeout=10)
            service.close()


def test_default_multi_directory_scan_enumerates_processes_once(tmp_path, monkeypatch):
    roots = [tmp_path / "one", tmp_path / "two"]
    for root in roots:
        root.mkdir()
    enumerations, scans = [], []
    rows = [{"pid": 123, "fixture": True}]

    def fetch(**_):
        enumerations.append(True)
        return rows

    def scan(root, **kwargs):
        scans.append(root)
        assert kwargs["process_rows"] is rows
        return [], []

    monkeypatch.setattr(external_job_scan_core, "fetch_psutil_process_rows_for_external_scan", fetch)
    monkeypatch.setattr(external_job_scan_core, "scan_running_abaqus_jobs_by_psutil", scan)
    external_job_scan_core.scan_external_jobs(str(roots[0]), additional_roots=[str(roots[1]), str(roots[1])])
    assert len(enumerations) == 1 and scans == [str(root) for root in roots]


def test_http_runtime_and_queue_stay_readable_during_scan(tmp_path):
    item = queue_item(tmp_path, "case")
    path = tmp_path / "joblist.json"
    save_joblist_state([], [item], path)
    entered, release = threading.Event(), threading.Event()

    def scan(*_):
        entered.set()
        assert release.wait(15)
        return [], []

    with running_control_plane(tmp_path, joblist_path=path, external_job_scanner=scan,
                               external_monitor_interval=999) as runtime, ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(api_request, runtime, "/api/v1/job-queue-commands", method="POST",
                              payload={"schemaVersion": 1, "action": "scanExternalJobs", "root": str(tmp_path)})
        samples = []
        try:
            assert entered.wait(5)
            for endpoint in ("/api/v1/job-queues", "/api/v1/local-queue-runtime"):
                started = time.perf_counter()
                response = api_request(runtime, endpoint)
                elapsed = time.perf_counter() - started
                assert response[0] == 200 and not release.is_set()
                body = json_response(response)
                snapshot = body.get("queue", body)
                assert snapshot["externalScanActive"] and snapshot["queueCount"] == 1
                samples.append({"endpoint": endpoint, "elapsedMs": round(elapsed * 1000, 3)})
            duplicate = api_request(runtime, "/api/v1/job-queue-commands", method="POST",
                                    payload={"schemaVersion": 1, "action": "scanExternalJobs", "root": str(tmp_path)})
            assert duplicate[0] == 409
        finally:
            release.set()
            assert pending.result(timeout=10)[0] == 200
        assert not json_response(api_request(runtime, "/api/v1/job-queues"))["externalScanActive"]
        (tmp_path / "verification.json").write_text(json.dumps({"status": "verified", "samplesWhileBlockedScan": samples}), encoding="utf-8")
