import json
import threading

import pytest

from modules.control_plane.contracts import ApiProblem
from modules.control_plane.odb_upgrade_operations import OdbUpgradeOperationManager
from tests.control_plane.test_odb_upgrade_operations import request, wait


def test_completed_history_and_idempotency_survive_restart(tmp_path):
    path = tmp_path / 'upgrades.json'
    calls = []
    def runner(*args, **kwargs):
        calls.append(1)
        return {'results': [{'source_path': 'case.odb', 'status': 'upgraded'}]}
    first = OdbUpgradeOperationManager(runner=runner, journal_path=path)
    try:
        created = first.create(request())
        finished = wait(first, created['operationId'])
    finally:
        first.close()
    second = OdbUpgradeOperationManager(runner=runner, journal_path=path)
    try:
        assert second.get(created['operationId']) == finished
        assert second.create(request())['operationId'] == created['operationId']
        assert calls == [1]
    finally:
        second.close()


def test_interrupted_record_is_not_replayed_or_reported_success(tmp_path):
    path = tmp_path / 'upgrades.json'
    entered, release = threading.Event(), threading.Event()
    def runner(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return {'results': []}
    first = OdbUpgradeOperationManager(runner=runner, journal_path=path)
    try:
        created = first.create(request())
        assert entered.wait(5)
        crash_image = path.read_bytes()
    finally:
        release.set()
        first.close()
    # Replay the last durable image from an interrupted process, not clean close.
    path.write_bytes(crash_image)
    calls = []
    second = OdbUpgradeOperationManager(runner=lambda *a, **kw: calls.append(1), journal_path=path)
    try:
        recovered = second.get(created['operationId'])
        assert recovered['status'] == 'failed'
        assert recovered['error']['code'] == 'UPGRADE_INTERRUPTED'
        assert recovered['preview'] == created['preview']
        assert recovered['version'] > created['version']
        assert second.create(request())['operationId'] == created['operationId']
        assert calls == []
    finally:
        second.close()


def test_corrupt_history_fails_closed_without_overwriting(tmp_path):
    path = tmp_path / 'upgrades.json'
    path.write_bytes(b'{broken')
    manager = OdbUpgradeOperationManager(journal_path=path)
    try:
        with pytest.raises(ApiProblem, match='记录'):
            manager.create(request())
        with pytest.raises(ApiProblem):
            manager.list_snapshots()
        assert path.read_bytes() == b'{broken'
    finally:
        manager.close()


def test_journal_single_owner_and_failed_initial_write_do_not_run(tmp_path, monkeypatch):
    path = tmp_path / 'upgrades.json'
    calls = []
    first = OdbUpgradeOperationManager(journal_path=path, runner=lambda *a, **kw: calls.append(1))
    second = OdbUpgradeOperationManager(journal_path=path)
    try:
        with pytest.raises(ApiProblem):
            second.create(request())
        def fail(*args):
            raise OSError('disk full')
        monkeypatch.setattr(first._journal, 'save', fail)
        with pytest.raises(ApiProblem):
            first.create(request())
        assert calls == []
        assert first.list_snapshots() == []
    finally:
        second.close()
        first.close()


def test_disk_failure_during_upgrade_requests_safe_stop_and_keeps_receipts(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def runner(preview, *, controller, log, **kwargs):
        entered.set()
        assert release.wait(5)
        log('ODB_UPGRADE_START|1|1|case.odb')
        assert controller.stop_requested and not controller.cancel_requested
        return {'results': [{'source_path': 'case.odb', 'status': 'upgraded'}]}
    manager = OdbUpgradeOperationManager(journal_path=tmp_path / 'history.json', runner=runner)
    try:
        created = manager.create(request())
        assert entered.wait(5)
        def fail(*args):
            raise OSError('disk full')
        monkeypatch.setattr(manager._journal, 'save', fail)
        release.set()
        final = wait(manager, created['operationId'])
        assert final['status'] == 'cancelled'
        assert final['results'][0]['status'] == 'upgraded'
        assert final['persistenceWarning']
        assert manager.prepare_shutdown()['safeToStop'] is False
        with pytest.raises(ApiProblem):
            manager.create(request('new'))
    finally:
        release.set()
        manager.close()


@pytest.mark.parametrize('corruption', ['duplicate', 'bad-progress', 'private-field', 'invalid-status', 'false-success', 'wrong-source'])
def test_malformed_journal_preserves_bytes_and_blocks_submissions(tmp_path, corruption):
    path = tmp_path / 'history.json'
    manager = OdbUpgradeOperationManager(journal_path=path, runner=lambda *a, **kw: {'results': []})
    try:
        wait(manager, manager.create(request())['operationId'])
    finally:
        manager.close()
    content = json.loads(path.read_text(encoding='utf-8'))
    item = content['operations'][0]
    if corruption == 'duplicate': content['operations'].append(item)
    if corruption == 'bad-progress': item['progress']['completed'] = 100
    if corruption == 'private-field': item['_controller'] = {}
    if corruption == 'invalid-status': item['status'] = 'unknown'
    if corruption == 'false-success': item['status'] = 'succeeded'
    if corruption == 'wrong-source': item['results'] = [{'source_path': 'wrong.odb', 'status': 'upgraded'}]
    raw = json.dumps(content).encode()
    path.write_bytes(raw)
    reopened = OdbUpgradeOperationManager(journal_path=path)
    try:
        with pytest.raises(ApiProblem): reopened.create(request('new'))
        assert path.read_bytes() == raw
    finally:
        reopened.close()


def test_http_history_survives_actual_runtime_recreation(tmp_path):
    from tests.control_plane.test_api import (
        api_request,
        json_response,
        running_control_plane,
        sse_data,
    )
    from tests.control_plane.test_odb_upgrade_api import BASE, terminal
    calls = []
    def runner(*args, **kwargs):
        calls.append(1)
        return {'results': [{'source_path': 'case.odb', 'status': 'upgraded'}]}
    with running_control_plane(tmp_path, odb_upgrade_runner=runner) as runtime:
        initial = json_response(api_request(runtime, BASE, method='POST', payload=request()))
        finished = terminal(runtime, initial['operationId'])
        events = sse_data(api_request(runtime, '/api/v1/events?after=0')[2])
        upgrade_events = [event for event in events if event['kind'].startswith('odb.upgrade.')]
        assert upgrade_events[0]['kind'] == 'odb.upgrade.queued'
        assert upgrade_events[-1]['kind'] == 'odb.upgrade.succeeded'
        assert [event['version'] for event in upgrade_events] == sorted({event['version'] for event in upgrade_events})
    with running_control_plane(tmp_path, odb_upgrade_runner=runner) as runtime:
        listing = json_response(api_request(runtime, BASE))
        assert listing['operations'] == [finished]
        again = json_response(api_request(runtime, BASE, method='POST', payload=request()))
        assert again['operationId'] == initial['operationId']
        assert calls == [1]
        events = sse_data(api_request(runtime, '/api/v1/events?after=0')[2])
        assert any(event['kind'] == 'odb.upgrade.recovered' for event in events)


def test_actual_process_crash_preserves_completed_receipt_without_reexecution(tmp_path):
    import os
    import queue
    import subprocess
    import sys
    from pathlib import Path

    import psutil
    journal = tmp_path / 'crash-history.json'
    child = subprocess.Popen([sys.executable, '-m', 'tests.control_plane.upgrade_crash_child', str(journal)],
        cwd=Path(__file__).resolve().parents[2], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    worker = None
    try:
        worker = psutil.Process(int(child.stdout.readline().strip()))
        assert 'tests.control_plane.upgrade_crash_child' in worker.cmdline()
        assert str(journal) in worker.cmdline()
        # A Windows reader can deny an atomic replace while its file handle is
        # open. Wait for the writer's checkpoint instead of polling that file.
        checkpoint = queue.Queue()
        reader = threading.Thread(target=lambda: checkpoint.put(child.stdout.readline()), daemon=True)
        reader.start()
        assert checkpoint.get(timeout=15).strip() == b'receipt-ready'
        reader.join(timeout=5)
        saved = json.loads(journal.read_text(encoding='utf-8'))['operations'][0]
        assert len(saved['results']) == 1
        # Terminate only the disposable test child, never a user/application process.
        worker.kill()
        worker.wait(timeout=5)
        child.wait(timeout=5)
    finally:
        if worker is not None and worker.is_running():
            worker.kill()
            worker.wait(timeout=5)
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        child.stderr.close()
        child.stdout.close()
    calls = []
    recovered = OdbUpgradeOperationManager(journal_path=journal, runner=lambda *a, **kw: calls.append(1))
    try:
        assert recovered._storage_error is None, recovered._storage_error
        item = recovered.list_snapshots()[0]
        assert item['error']['code'] == 'UPGRADE_INTERRUPTED'
        assert item['results'] == [{'source_path': 'case.odb', 'status': 'upgraded'}]
        assert item['progress']['completed'] == 1
        assert item['progress']['total'] == 2
        assert calls == []
    finally:
        recovered.close()
