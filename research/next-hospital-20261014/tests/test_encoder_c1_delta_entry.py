"""Generated-only launch/supervise/child seam; no Torch import or real queue."""
import builtins
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from epi_next import encoder_fov64_recovery as recovery
from test_encoder_fov64_pair import Guard, FakeBackend


def test_generated_same_entry_launch_to_complete_with_atomic_rename(tmp_path, monkeypatch):
    pair = recovery.pair
    parent = tmp_path/'generated128.npy'
    np.save(parent, np.linspace(0, 1, 128**3, dtype=np.float32).reshape(1,1,128,128,128))
    ledger = tmp_path/'generated128.json'
    ledger.write_text(json.dumps(dict(input_file_sha256=pair.file_sha(parent),
        model_to_native=np.eye(4).tolist(), model_to_lps=np.eye(4).tolist(),
        proposed_spacing_spl_mm=[1,1,1])))
    project = tmp_path/'generated-project'
    monkeypatch.setattr(recovery, '__file__', str(project/'research'/'next-hospital'/'epi_next'/'entry.py'))
    output = project/'.local'/'ctfm-v3-fov64-pair'/'attempt-1'
    config = dict(output=str(output), supervisor_output_root=str(tmp_path/'supervision'),
        checkpoint_sha256='GENERATED_NO_CHECKPOINT', selection=dict(source_input_path=str(parent),
        source_input_sha256=pair.file_sha(parent), source_ledger_path=str(ledger),
        source_ledger_sha256=pair.file_sha(ledger)))
    binding = dict(source_sha256={'fixture':'generated'},
        authority_references=dict(administrative_decision=dict(path='/generated/decision', digest='a'*64)),
        supervisor_bundle=dict(dependency_root=str(tmp_path/'generated-dependency')))
    command = dict(environment={}, cwd=str(tmp_path))
    guard = Guard()
    monkeypatch.setattr(guard, 'begin_case', lambda case: guard.check(), raising=False)
    monkeypatch.setattr(guard, 'end_case', lambda: guard.check(), raising=False)
    original_ledger = guard.ledger
    from contextlib import contextmanager
    @contextmanager
    def counters():
        with original_ledger() as value: yield dict(value, cases=0)
    monkeypatch.setattr(guard, 'ledger', counters)
    backend = FakeBackend()
    backend.adapter = None
    backend.release = lambda: None
    monkeypatch.setattr(pair, 'TorchBackend', lambda *args: backend)
    monkeypatch.setattr(pair, 'configure_allocator', lambda mps: {'generated':True})
    monkeypatch.setattr(pair, 'cleanup_device', lambda *args: dict(device_recovered=True))
    mps = SimpleNamespace(driver_allocated_memory=lambda: 0, current_allocated_memory=lambda: 0)
    torch = SimpleNamespace(__version__='FAKE_NO_TORCH', mps=mps,
        backends=SimpleNamespace(mps=SimpleNamespace(is_built=lambda:True, is_available=lambda:True)),
        set_num_threads=lambda n: None, set_num_interop_threads=lambda n: None, manual_seed=lambda n: None)
    real_import = builtins.__import__
    def generated_import(name, *args, **kwargs):
        if name == 'torch': return torch
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', generated_import)
    # The normal artifact check experiences an actual rename during its first scan.
    original_scan = pair.PrivateArtifacts._disk_snapshot
    scans = []
    def atomic_scan(artifacts):
        scans.append(1)
        if len(scans) == 1:
            pending = artifacts.directory/'generated.tmp'
            pending.write_bytes(b'generated telemetry')
            pending.replace(artifacts.directory/'generated.json')
            raise FileNotFoundError('generated lifecycle event; rescan complete tree')
        return original_scan(artifacts)
    monkeypatch.setattr(pair.PrivateArtifacts, '_disk_snapshot', atomic_scan)
    trace = []
    def supervised(spec, argv, root, dep, sha, **kwargs):
        trace.append('supervise')
        assert spec == pair.SPEC and sha == recovery.DEPENDENCY_SHA
        assert kwargs == dict(recovery_decision_path='/generated/decision', recovery_decision_sha='a'*64)
        directory = Path(root)/pair.JOB
        directory.mkdir(parents=True)
        (directory/'spec.json').write_text(json.dumps(spec))
        monkeypatch.setenv('EPI_NEXT_SUPERVISOR_DIR', str(directory))
        monkeypatch.setenv('EPI_NEXT_DEPENDENCY_ROOT', dep)
        monkeypatch.setenv('EPI_NEXT_DEPENDENCY_SHA', sha)
        monkeypatch.setattr(recovery.sys, 'argv', argv[2:])
        assert recovery.main() == 0
        trace.append('child_complete')
        return dict(status=guard.completed['status'], job_id=pair.JOB, slot_completed=True)
    shared = SimpleNamespace(SupervisionSpec=lambda **values: values, run_supervised=supervised,
        ChildGuard=SimpleNamespace(from_environment=lambda **kwargs: guard))
    # Only generated admission references are substituted; production gates remain unchanged.
    monkeypatch.setattr(recovery, 'verify_readiness', lambda args:(config,binding,command,shared,{},[]))
    monkeypatch.setattr(recovery, 'validate_dispatch', lambda *args: {'generated':True})
    def subprocess_run(argv, **kwargs):
        trace.append('launch')
        monkeypatch.setattr(recovery.sys, 'argv', argv[2:])
        return SimpleNamespace(returncode=recovery.main())
    monkeypatch.setattr(recovery.subprocess, 'run', subprocess_run)
    monkeypatch.setattr(recovery.sys, 'argv', ['entry','--mode','launch','--config','generated',
        '--config-sha','c','--binding','generated','--binding-sha','b','--command-template','generated',
        '--command-sha','m','--dispatch','generated','--dispatch-sha','d'])
    assert recovery.main() == 0
    assert trace == ['launch','supervise','child_complete']
    result = json.loads((output/'result.json').read_bytes())
    assert backend.devices == ['cpu','mps'] and result['actual_forward'] == 2 and result['actual_backward'] == 0
    assert result['comparison']['elements'] == 32768 and result['comparison']['max_absolute_error'] == 0
    spatial = json.loads((output/'ledger64.json').read_bytes())
    assert spatial['edge_error_voxels'] == spatial['inverse_error_voxels'] == 0
    assert spatial['model_to_native'][0] == [2.,0.,0.,.5]
    assert (output/'generated.json').read_bytes() == b'generated telemetry'
    assert 'torch' not in recovery.sys.modules
