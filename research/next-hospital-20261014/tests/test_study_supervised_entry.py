"""Small full-entry synthetic jobs; frozen shared bytes, tmp_path queue only."""

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[3]
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

import pytest

import epi_next.study_labels as labels
from test_study_labels import bind_fixture, annotation


INTEGRATION = Path(str(_PUBLIC_ROOT / '.'))
SHARED_COMMIT = 'aca34f99ce3e642331bf82e71e6fd625f6e02409'


def shared_snapshot(tmp_path):
    source = INTEGRATION / 'research/next-hospital-20261014/epi_next'
    if not (source / 'wave1_supervisor.py').exists():
        pytest.fail('shared supervisor source required for full-entry verification')
    target = tmp_path / 'shared-pinned'
    target.mkdir()
    files = {}
    for name in sorted(labels.SHARED_MODULES):
        raw = subprocess.check_output(['git', 'show', SHARED_COMMIT + ':research/next-hospital-20261014/epi_next/' + name], cwd=INTEGRATION)
        (target / name).write_bytes(raw)
        files[name] = hashlib.sha256(raw).hexdigest()
        (target / name).chmod(0o444)
    manifest = target / 'imports.json'
    manifest.write_text(json.dumps({'files': files}, sort_keys=True))
    manifest.chmod(0o444)
    return target, manifest, labels.digest(manifest), files['wave1_supervisor.py']


def test_full_synthetic_supervised_entry_and_partial(tmp_path, monkeypatch):
    revision, archive = bind_fixture(tmp_path, monkeypatch, [annotation(), annotation('study-b', 'normal')])
    package, manifest, manifest_sha, module_sha = shared_snapshot(tmp_path)
    shared, imports = labels.load_shared(package, manifest, manifest_sha, module_sha)
    assert len(imports) == len(labels.SHARED_MODULES)
    assert all(Path(row['path']).parent == package for row in imports)
    shared.hospital_runtime.QUEUE_ROOT = tmp_path / 'synthetic-device-queue'
    # Use real own-process inventory; deterministic pressure is test-only, not
    # a claim about production macOS pressure admission.
    class FixtureMonitor(shared.SystemMonitor):
        def pressure(self):
            return {'free_fraction': .8, 'swap_used_bytes': 0}

    data_root = Path(labels.__file__).resolve().parent.parent
    # The unpublished supervisor is committed only in this temporary fixture
    # repository; never commit or mutate INTEGRATION's owned checkout.
    subprocess.run(['git', 'init', '-q', str(package)], check=True)
    subprocess.run(['git', 'add', '.'], cwd=package, check=True)
    subprocess.run(['git', '-c', 'user.name=Synthetic Fixture', '-c', 'user.email=fixture@example.invalid',
                    'commit', '-qm', 'synthetic pinned shared bytes'], cwd=package, check=True)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=package, text=True).strip()
    execution_lock = sys.modules[shared.__package__ + '.execution_lock']
    dependency_sha = execution_lock.dependency_snapshot(tmp_path / 'dependencies', 'EPI-NEXT-synthetic-lock',
        [{'name': name, 'repo': str(package),
          'relative_path': name, 'commit': commit, 'sha256': labels.digest(package / name)}
         for name in sorted(labels.SHARED_MODULES)],
        {'numpy': importlib.metadata.version('numpy')})
    dependency_root = tmp_path / 'dependencies' / 'EPI-NEXT-synthetic-lock'
    # Frozen actual DATA source, imported by a unique test package; no old
    # epi_next module can shadow either child DATA or shared dependencies.
    data_package = tmp_path / 'fixture_data'
    data_package.mkdir()
    (data_package / '__init__.py').write_text('')
    for name in ('study_labels.py', 'bounded_study_parser.py'):
        (data_package / name).write_bytes((data_root / 'epi_next' / name).read_bytes())
    hashes = {name: getattr(labels, name) for name in ('REVISION_SHA', 'APPROVAL_SHA', 'REQUEST_SHA', 'PROPOSAL_SHA', 'SOURCE_SHA')}
    script = tmp_path / 'synthetic-entry.py'
    script.write_text('''import json,sys,os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from fixture_data import study_labels as runner
for key,value in json.loads(sys.argv.pop(1)).items():setattr(runner,key,value)
partial=sys.argv.pop(1)=='partial'
if partial:
    original=runner.annotations
    def stop_after_row(*args):
        for row in original(*args):
            yield row
            (Path(os.environ['EPI_NEXT_SUPERVISOR_DIR'])/'STOP').touch()
    runner.annotations=stop_after_row
sys.exit(runner.main())
''')
    monkeypatch.setenv('PYTHONDONTWRITEBYTECODE', '1')
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        monkeypatch.setenv(key, '1')
    for mode, expected in (('complete', 'SUCCESS'), ('partial', 'PARTIAL_BUDGET')):
        job_id = 'synthetic-study-' + mode
        jobs = tmp_path / 'jobs'
        job = jobs / job_id
        output = job / 'data-assets'
        command = [sys.executable, str(script), json.dumps(hashes), mode,
                   '--resource-revision', revision, '--output', str(output), '--stop-file', str(job / 'STOP'),
                   '--supervisor-package', str(package), '--supervisor-module-sha256', module_sha,
                   '--supervisor-import-manifest', str(manifest), '--supervisor-import-manifest-sha256', manifest_sha]
        spec = shared.SupervisionSpec(job_id=job_id, task_key='synthetic-study-labels-' + mode, device='cpu', owner='DATA',
                                     max_forward=0, max_backward=0, timeout_seconds=120)
        receipt = shared.run_supervised(spec, command, jobs, dependency_root, dependency_sha, _monitor=FixtureMonitor())
        assert receipt['status'] == expected, (receipt, (job / 'stderr.log').read_text())
        assert receipt['slot_completed'] and receipt['counters']['forward'] == receipt['counters']['backward'] == 0
        complete = json.loads((job / 'runner-complete.json').read_bytes())
        assert complete['reason']['data_receipt_sha256'] == labels.digest(output / 'receipt.json')
        assert complete['actual_forward'] == complete['actual_backward'] == 0
        final_telemetry = json.loads((job / 'telemetry.json').read_bytes())
        assert final_telemetry['device_recovered'] is True
        actual_imports = json.loads((output / 'shared-imports.json').read_bytes())
        assert {Path(row['path']).name for row in actual_imports} == labels.SHARED_MODULES
        assert all(Path(row['path']).parent == package for row in actual_imports)
        data_receipt = json.loads((output / 'receipt.json').read_bytes())
        if mode == 'partial':
            assert data_receipt['case_status_counts'] == {'UNKNOWN': 3}
            assert data_receipt['selected_count'] == 1
    # Manifest/file mismatch is caught before executing any shared source.
    with pytest.raises(ValueError, match='manifest mismatch'):
        labels.load_shared(package, manifest, '0' * 64, module_sha)
