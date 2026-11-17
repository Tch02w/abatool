from pathlib import Path

import pytest

from modules.control_plane.contracts import ApiProblem
from modules.control_plane.job_drafts import LocalJobDraftPreviewRequest
from modules.control_plane.postprocessing import (
    PostprocessRunRequest,
    PostprocessScanRequest,
)
from modules.submitter.cpu_policy import local_cpu_policy
from modules.submitter.local_job_execution import (
    LocalJobProcessController,
    _execution_command,
    execute_local_job,
)
from modules.submitter.models import QueueItem
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)
from tests.control_plane.test_postprocessing_api import _run_payload, _scan_payload


@pytest.mark.parametrize('release,limit', [('2020', 32), ('2021', 32), ('2022', 16), ('2024', 16), ('2025', 16)])
def test_local_draft_cpu_boundary(monkeypatch, release, limit):
    monkeypatch.setattr('psutil.cpu_count', lambda logical=True: 32 if logical else 16)
    monkeypatch.setattr('modules.submitter.app_settings.load_app_settings', lambda: {
        'abaqus_command': 'abaqus', 'local_abaqus_release': release})
    monkeypatch.setattr('modules.postprocessor.config.load_defaults', dict)
    payload = {'schemaVersion': 1, 'abaqusCommand': 'abaqus', 'cpus': limit}
    assert LocalJobDraftPreviewRequest.from_payload(payload).draft.cpus == limit
    with pytest.raises(ApiProblem, match='cpus'):
        LocalJobDraftPreviewRequest.from_payload(payload | {'cpus': limit + 1})


def test_postprocess_parallel_uses_logical_cpus(tmp_path: Path, monkeypatch):
    monkeypatch.setattr('psutil.cpu_count', lambda logical=True: 8 if logical else 4)
    odb = tmp_path / 'sample.odb'
    odb.write_bytes(b'test-only')
    payload = _scan_payload(tmp_path, odb) | {'parallelWorkers': 8}
    assert PostprocessScanRequest.from_payload(payload).parallel_workers == 8
    with pytest.raises(ApiProblem):
        PostprocessScanRequest.from_payload(payload | {'parallelWorkers': 9})
    run = _run_payload(tmp_path, odb) | {'parallelWorkers': 8}
    assert PostprocessRunRequest.from_payload(run, abaqus_command='abaqus', defaults={}).plan.options.parallel_workers == 8
    with pytest.raises(ApiProblem):
        PostprocessRunRequest.from_payload(run | {'parallelWorkers': 9}, abaqus_command='abaqus', defaults={})


@pytest.mark.parametrize('release,physical,limit', [('2021', 16, 32), ('2022', 16, 16), ('6.14', 16, 32), ('', 16, 16), ('unknown', None, 1)])
def test_policy_fallbacks(monkeypatch, release, physical, limit):
    monkeypatch.setattr('psutil.cpu_count', lambda logical=True: 32 if logical else physical)
    assert local_cpu_policy(release=release)['jobCpuLimit'] == limit


def test_launcher_version_and_resource_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr('psutil.cpu_count', lambda logical=True: 32 if logical else 16)
    monkeypatch.setattr('modules.submitter.app_settings.load_app_settings', lambda: {'local_abaqus_release': '2025'})
    monkeypatch.setattr('modules.postprocessor.config.load_defaults', dict)
    with running_control_plane(tmp_path) as runtime:
        response = api_request(runtime, '/api/v1/local-resources?abaqusCommand=abq2021.bat')
        assert response[0] == 200
        assert json_response(response)['jobCpuLimit'] == 32
        response = api_request(runtime, '/api/v1/local-resources?abaqusCommand=abq2022.bat')
        assert json_response(response)['jobCpuLimit'] == 16
        assert json_response(response)['physicalCpus'] == 16


def test_execution_rechecks_stale_cpu_config_before_touching_files(tmp_path, monkeypatch):
    monkeypatch.setattr('psutil.cpu_count', lambda logical=True: 32 if logical else 16)
    inp, odb = tmp_path / 'job.inp', tmp_path / 'job.odb'
    inp.write_text('*Heading\n')
    odb.write_bytes(b'original result')
    item = QueueItem(inp_path=str(inp), job_name='job', cores=17, abaqus_command='abq2022.bat')
    with pytest.raises(ValueError, match='cpus'):
        execute_local_job(item, 'backup', LocalJobProcessController())
    assert odb.read_bytes() == b'original result'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['job.inp', 'job.odb']
    item.abaqus_command = 'abq2021.bat'
    item.cores = 32
    assert 'cpus=32' in _execution_command(item, inp, '')
