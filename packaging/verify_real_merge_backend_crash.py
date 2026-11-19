"""Check frozen-backend recovery while its real Abaqus validator survives.

Only existing GPTWork ODB copies are accepted. The exact owned validator is
briefly suspended so it remains alive throughout recovery, then resumed. Only
the backend created here is killed. No solver runs or user processes are stopped.
Interrupted staging is intentionally retained for inspection; nothing goes to C:.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import psutil
from verify_real_merge_interruption import (
    WORK_ROOT,
    call,
    digest,
    identity,
    same_alive,
    save,
)


def verify(bundle: Path, original: Path, restart: Path, existing: Path, later: Path | None = None) -> Path:
    bundle, original, restart, existing = [p.resolve(strict=True) for p in (bundle, original, restart, existing)]
    later = later.resolve(strict=True) if later is not None else None
    sources = [original, restart, existing] + ([later] if later is not None else [])
    if any(not p.is_relative_to(WORK_ROOT.resolve()) or p.drive.casefold() == 'c:'
           for p in [bundle, *sources]):
        raise ValueError('Only existing non-C GPTWork packages and ODB copies are accepted')
    executable = bundle / 'control-plane/AbaqusTools.ControlPlane.exe'
    if not executable.is_file():
        raise ValueError('Frozen control plane missing')
    required = original.stat().st_size * 2 + restart.stat().st_size + 2 * 1024**3
    if psutil.disk_usage(str(WORK_ROOT)).free < required:
        raise RuntimeError('Not enough space for protected staging')
    prefix = 'real-batch-backend-crash-' if later is not None else 'real-merge-backend-crash-'
    work = WORK_ROOT / (prefix + uuid4().hex[:12])
    work.mkdir()
    output, temp = work / 'output', work / 'temp'
    output.mkdir()
    temp.mkdir()
    print('WORK=' + str(work), flush=True)
    descriptor_path = work / 'control-plane.json'
    destination = output / 'existing-result.odb'
    before = {str(p): digest(p) for p in sources}
    shutil.copyfile(existing, destination)
    old_hash = digest(destination)
    environment = dict(os.environ)
    for key in ('PYTHONHOME', 'PYTHONPATH', 'ABAQUS_TOOLS_PYTHON', 'ABAQUS_TOOLS_ROOT', 'ABAQUS_TOOLS_LAUNCH_TOKEN'):
        environment.pop(key, None)
    environment.update(ABAQUS_SUBMITTER_DATA_DIR=str(work / 'submitter'),
        ABAQUS_POSTPROCESSOR_DATA_DIR=str(work / 'postprocessor'),
        ABAQUS_TOOLS_ABAQUS_COMMAND=r'D:\SIMULIA\Commands\abaqus.bat',
        ABAQUS_TOOLS_ABAQUS_RELEASE='2025', TEMP=str(temp), TMP=str(temp),
        MPLCONFIGDIR=str(work / 'mpl'), PATH=str(Path(os.environ['SystemRoot']) / 'System32'))
    processes, observed = [], []
    suspended = None
    report = {'status': 'running', 'bundle': str(bundle), 'sourcesBefore': before,
              'solverStarted': False, 'nativeUiAcceptance': False, 'mode': 'batch' if later is not None else 'single',
              'processes': processes, 'observedChildren': observed}
    receipt = work / 'verification.json'
    save(receipt, report)

    def start(index):
        with (work / f'backend-{index}.log').open('wb') as stream:
            process = subprocess.Popen([str(executable), '--descriptor', str(descriptor_path)],
                cwd=bundle, env=environment, stdout=stream, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW)
        record = identity(psutil.Process(process.pid))
        processes.append(record)
        save(receipt, report)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Backend exited before readiness')
            if descriptor_path.exists():
                descriptor = json.loads(descriptor_path.read_text(encoding='utf-8'))
                if descriptor['pid'] == process.pid and descriptor['host'] == '127.0.0.1':
                    call(descriptor, '/healthz')
                    return process, descriptor, record
            time.sleep(.1)
        raise TimeoutError('Keep original backend; readiness not observed')

    def close(process, descriptor, record):
        request_id = str(uuid4())
        route = '/api/v1/shutdown-requests'
        state = call(descriptor, route, {'schemaVersion': 1, 'clientRequestId': request_id})
        if not state['safeToStop'] or state.get('operations') or state.get('pendingRequests'):
            call(descriptor, route + '/' + request_id + '/abort', {'schemaVersion': 1})
            raise RuntimeError('Owned backend busy; preserve instead of forcing shutdown')
        call(descriptor, route + '/' + request_id + '/commit', {'schemaVersion': 1, 'mode': 'idle'})
        record['exitCode'] = process.wait(timeout=30)
        record['descriptorRemoved'] = not descriptor_path.exists()
        assert record['exitCode'] == 0 and record['descriptorRemoved']
        save(receipt, report)

    try:
        first, descriptor, first_record = start(0)
        if later is None:
            request = {'schemaVersion': 1, 'clientRequestId': str(uuid4()),
                'originalOdb': str(original), 'restartOdb': str(restart), 'outputOdb': str(destination),
                'includeHistory': True, 'compressResult': False, 'copyOriginal': False, 'conflictPolicy': 'overwrite'}
            operation = call(descriptor, '/api/v1/odb-merge-operations', request)
        else:
            graph = {'schemaVersion': 1, 'action': 'save', 'expectedRevision': 0,
                'outputDirectory': str(output), 'nodes': [
                    {'nodeId': name, 'name': name, 'parentNodeId': parent, 'odbPath': str(path), 'inpPath': ''}
                    for name, parent, path in zip(('base', 'restart', 'later'), ('', 'base', 'restart'),
                                                  (original, restart, later), strict=True)]}
            call(descriptor, '/api/v1/odb-result-graph-commands', graph)
            request = {'schemaVersion': 1, 'clientRequestId': str(uuid4()),
                'source': {'kind': 'graph', 'revision': 1, 'targetNodeIds': ['later']},
                'options': {'includeHistory': True, 'compressResult': False, 'copyOriginal': False}}
            batch = call(descriptor, '/api/v1/odb-result-batches', request)
            batch_route = '/api/v1/odb-result-batches/' + batch['operationId']
            report.update(batchOperationId=batch['operationId'], graph=graph)
            deadline = time.monotonic() + 30
            while not batch['stages'][0]['childOperationId']:
                assert batch['status'] in ('queued', 'running'), batch
                if time.monotonic() >= deadline:
                    raise TimeoutError('Keep original batch; child admission not observed')
                time.sleep(.03)
                batch = call(descriptor, batch_route)
            assert batch['totalSteps'] == 2 and batch['completedSteps'] == 0
            operation = call(descriptor, '/api/v1/odb-merge-operations/' + batch['stages'][0]['childOperationId'])
        route = '/api/v1/odb-merge-operations/' + operation['operationId']
        report.update(request=request, operationId=operation['operationId'])
        save(receipt, report)
        deadline, worker, selected, last_percent = time.monotonic() + 300, None, None, None
        seen = set()
        while time.monotonic() < deadline:
            operation = call(descriptor, route)
            percent = operation['progress']['percent']
            if percent != last_percent:
                print('PROGRESS=' + str(percent), flush=True)
                last_percent = percent
            if operation['status'] in ('succeeded', 'failed', 'cancelled'):
                raise RuntimeError('Operation ended before real validator was identified')
            for child in psutil.Process(first.pid).children(recursive=True):
                try:
                    record = identity(child)
                    key = (record['pid'], record['created'])
                    if key not in seen:
                        seen.add(key)
                        observed.append(record)
                    scripts = [arg for arg in record['arguments'] if Path(arg).name.casefold() == 'validate_joined_odb.py']
                    if percent == 82 and len(scripts) == 1:
                        script = (Path(record['cwd']) / scripts[0]).resolve()
                        binary = Path(record['executable']).resolve()
                        if (binary.is_relative_to(Path(r'D:\SIMULIA')) and 'python' in binary.name.casefold()
                            and script.is_relative_to(output) and script.parent.name.startswith('.abasub-odb-merge-')
                            and Path(record['cwd']).resolve() == script.parent):
                            # This child came from the owned backend's descendants.
                            # Freeze immediately; traversing its parents first can
                            # outlast validation of a tiny real ODB.
                            child.suspend()
                            suspended = record
                            worker, selected = child, record
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            if worker is not None:
                break
            time.sleep(.03)
        if worker is None:
            raise TimeoutError('Real validator not observed; original task preserved')
        assert same_alive(selected) and any(p.pid == first.pid for p in worker.parents())
        report.update(selectedWorker=selected, validatorTemporarilySuspended=True,
                      snapshotBeforeCrash=call(descriptor, route))
        save(receipt, report)
        assert report['snapshotBeforeCrash']['status'] == 'running'
        first.kill()  # Exact Popen child; intentionally leave its verified worker alive.
        first_record['exitCode'] = first.wait(timeout=15)
        assert same_alive(selected), 'Scenario requires the actual worker to survive'
        report['backendCrashedWithRealWorkerAlive'] = True
        save(receipt, report)
        print('BACKEND_CRASHED_WORKER_ALIVE=' + str(worker.pid), flush=True)

        # Leave the stale descriptor in place: production startup must replace it.
        second, descriptor, second_record = start(1)
        restored = call(descriptor, route)
        assert restored['status'] == 'failed' and restored['error']['code'] == 'ODB_MERGE_INTERRUPTED'
        assert restored['result'] is None and restored['error']['retryable'] is False
        if later is None:
            repeated = call(descriptor, '/api/v1/odb-merge-operations', request)
            assert repeated['operationId'] == operation['operationId'] and repeated['status'] == 'failed'
        else:
            restored_batch = call(descriptor, batch_route)
            assert restored_batch['status'] == 'suspended' and restored_batch['completedSteps'] == 0
            repeated = call(descriptor, '/api/v1/odb-result-batches', request)
            assert repeated['operationId'] == batch['operationId'] and repeated['status'] == 'suspended'
            call(descriptor, batch_route + '/resume', {})
            deadline = time.monotonic() + 30
            while True:
                checked_batch = call(descriptor, batch_route)
                if checked_batch['status'] not in ('queued', 'running', 'cancelling'):
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError('Original batch recovery remains active; preserve it')
                time.sleep(.03)
            assert checked_batch['status'] == 'failed' and checked_batch['error']['code'] == 'ODB_BATCH_FAILED'
            assert checked_batch['completedSteps'] == 0 and not checked_batch['results']
            assert checked_batch['stages'][1]['childOperationId'] is None
            report.update(restoredBatch=restored_batch, batchAfterResume=checked_batch,
                          laterStageNotSubmitted=True, batchResumeDidNotReplay=True)
        assert len(call(descriptor, '/api/v1/odb-merge-operations')['operations']) == 1
        assert same_alive(selected), 'Actual worker must survive recovery verification'
        stages = list(output.glob('.abasub-odb-merge-*'))
        assert len(stages) == 1 and stages[0].resolve() == Path(selected['cwd']).resolve()
        assert digest(destination) == old_hash
        report.update(restoredSnapshot=restored, workerAliveDuringRecovery=True,
            sameRequestNotReplayed=True, interruptedStagingPreserved=True,
            interruptedStaging=str(stages[0]), oldOutputUnchangedDuringRecovery=True)
        save(receipt, report)
        worker.resume()
        suspended = None
        print('RECOVERY_VERIFIED_WORKER_RESUMED', flush=True)
        deadline = time.monotonic() + 300
        last_notice = 0
        while same_alive(selected) and time.monotonic() < deadline:
            if time.monotonic() - last_notice >= 15:
                print('WAITING_ORIGINAL_VALIDATOR=' + str(worker.pid), flush=True)
                last_notice = time.monotonic()
            time.sleep(.2)
        if same_alive(selected):
            raise TimeoutError('Original validator remains live; preserve exact PID, do not relaunch')
        report['validatorEnded'] = True
        report['validatorExitCode'] = worker.wait(timeout=1)
        _, live = psutil.wait_procs([psutil.Process(p['pid']) for p in observed if same_alive(p)], timeout=15)
        if live:
            raise RuntimeError('Owned descendants remain; preserve identities for follow-up')
        assert digest(destination) == old_hash
        assert not list(output.glob('*.merge-validation.json'))
        assert list(output.glob('*.odb')) == [destination], 'Unexpected result was published'
        assert len(list(output.glob('.abasub-odb-merge-*'))) == 1
        assert call(descriptor, route)['error']['code'] == 'ODB_MERGE_INTERRUPTED'
        close(second, descriptor, second_record)
        third, descriptor, third_record = start(2)
        final = (call(descriptor, '/api/v1/odb-merge-operations', request)
                 if later is None else call(descriptor, route))
        assert final['operationId'] == operation['operationId'] and final['error']['code'] == 'ODB_MERGE_INTERRUPTED'
        assert final['result'] is None and len(call(descriptor, '/api/v1/odb-merge-operations')['operations']) == 1
        if later is not None:
            final_batch = call(descriptor, '/api/v1/odb-result-batches', request)
            assert final_batch['operationId'] == batch['operationId'] and final_batch['status'] == 'failed'
            assert final_batch['stages'][1]['childOperationId'] is None and not final_batch['results']
            assert len(call(descriptor, '/api/v1/odb-result-batches')['operations']) == 1
            report['batchFailurePersisted'] = True
        close(third, descriptor, third_record)
        after = {str(p): digest(p) for p in sources}
        assert before == after and digest(destination) == old_hash
        report.update(status='verified', coldStarts=3, sourcesAfter=after, oldOutputUnchanged=True,
            resultPublished=False, interruptedHistoryPersisted=True, ownedProcessesEnded=True)
    except BaseException as error:
        report.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        if suspended is not None and same_alive(suspended):
            psutil.Process(suspended['pid']).resume()
            report['validatorResumedOnFailure'] = True
        report['remainingOwnedPids'] = [p['pid'] for p in processes + observed if same_alive(p)]
        save(receipt, report)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('bundle', 'original', 'restart', 'existing-result'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--later', type=Path, help='Third sequential ODB; exercises two-stage batch recovery instead')
    args = parser.parse_args()
    print(verify(args.bundle, args.original, args.restart, args.existing_result, args.later), flush=True)
