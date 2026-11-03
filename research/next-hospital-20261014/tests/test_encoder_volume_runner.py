"""Small synthetic/fault tests only: no Torch, CT, weights, MPS or supervisor job."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from epi_next import encoder_volume_runner as runner


class Mps:
    def __init__(self):
        self.driver, self.tensor = 300, 100
        self.calls = []

    def driver_allocated_memory(self): return self.driver
    def current_allocated_memory(self): return self.tensor
    def recommended_max_memory(self): return 16 * runner.GIB
    def set_per_process_memory_fraction(self, value): self.calls.append(('fraction', value))
    def synchronize(self): self.calls.append('sync')
    def empty_cache(self): self.calls.append('empty_cache')


class Guard:
    def __init__(self):
        self.reserved, self.stopped, self.active = 0, False, None
        self.visited = []

    def check(self):
        if self.stopped: raise RuntimeError('STOP_REQUESTED')

    def before_forward(self):
        self.check()
        if self.reserved >= 24: raise RuntimeError('CALL_BUDGET')
        self.reserved += 1

    def begin_case(self, key):
        self.check()
        assert self.active is None and key not in self.visited
        self.active = key; self.visited.append(key)

    def end_case(self): self.active = None


def test_actual_telemetry_preserves_gaps_and_errors():
    mps = Mps(); ticks = iter([0., .002, .05, .054, .08, .081])
    telemetry = runner.ActualMpsTelemetry(mps, lambda: next(ticks))
    assert telemetry() == {'driver_bytes': 300, 'tensor_bytes': 100}
    mps.driver = 450
    telemetry()
    mps.tensor = None
    with pytest.raises(ValueError): telemetry()
    report = telemetry.report()
    assert report['max_actual_interval_seconds'] == .05
    assert report['gaps_over_target'] == 2 and report['missing_measurements'] == 1
    assert report['driver_peak_sampled_bytes'] == 450
    assert report['samples'][2]['tensor_bytes'] is None  # never synthesize zero


def test_allocator_uses_positive_supported_fraction_and_rejects_zero():
    mps = Mps(); record = runner.configure_allocator(mps)
    assert record['fraction'] == 5/16
    assert mps.calls == [('fraction', 5/16)]
    with pytest.raises(ValueError): runner.configure_allocator(mps, 0)
    mps.recommended_max_memory = lambda: 0
    with pytest.raises(ValueError): runner.configure_allocator(mps)


def test_stop_after_reservation_does_not_invent_actual_call(tmp_path):
    guard = Guard(); original = guard.before_forward
    def stop_after_reserve(): original(); guard.stopped = True
    guard.before_forward = stop_after_reserve
    journal = runner.CallJournal(guard, tmp_path/'calls.jsonl')
    with pytest.raises(RuntimeError, match='STOP'): journal.reserve(1, 'cpu', 0)
    assert guard.reserved == 1 and journal.adapter_attempts == journal.actual == 0


def test_failed_network_is_counted_once_and_no_automatic_retry(tmp_path):
    guard = Guard(); journal = runner.CallJournal(guard, tmp_path/'calls.jsonl')
    journal.reserve(1, 'mps', 0); journal.network_entry()
    guard.stopped = True
    with pytest.raises(RuntimeError): journal.reserve(1, 'mps', 1)
    assert journal.actual == journal.adapter_attempts == guard.reserved == 1
    events = [json.loads(line) for line in journal.path.read_text().splitlines()]
    assert [e['event'] for e in events] == ['ADAPTER_ATTEMPT', 'NETWORK_ENTERED']


def test_global_24_attempts_include_warmups_and_all_cases(tmp_path):
    guard = Guard(); journal = runner.CallJournal(guard, tmp_path/'calls.jsonl')
    for case in [1, 2, 3]:
        guard.begin_case(f'case_{case}')
        for device in ['cpu', 'mps']:
            for repeat in range(4):
                journal.reserve(case, device, repeat); journal.network_entry()
        guard.end_case()
    with pytest.raises(RuntimeError, match='CALL_BUDGET'): journal.reserve(3, 'mps', 4)
    assert journal.actual == 24 and journal.device_counts == {'cpu': 12, 'mps': 12}


def test_stop_between_adapter_and_network_keeps_distinct_counts(tmp_path):
    guard = Guard(); journal = runner.CallJournal(guard, tmp_path/'calls.jsonl')
    journal.reserve(1, 'cpu', 0); guard.stopped = True
    with pytest.raises(RuntimeError, match='STOP'): journal.network_entry()
    assert journal.adapter_attempts == guard.reserved == 1 and journal.actual == 0


def test_cleanup_requires_actual_final_measurement_and_baseline():
    mps = Mps(); telemetry = runner.ActualMpsTelemetry(mps)
    baseline = telemetry()
    result = runner.cleanup_device(mps, telemetry, baseline)
    assert result['device_recovered'] and mps.calls == ['sync', 'empty_cache', 'sync']
    mps.tensor = 101
    assert not runner.cleanup_device(mps, telemetry, baseline)['device_recovered']
    mps.tensor = 100; mps.driver = runner.PRE_STOP
    assert not runner.cleanup_device(mps, telemetry, baseline)['device_recovered']
    def failure(): raise RuntimeError('driver API unavailable')
    mps.driver_allocated_memory = failure
    result = runner.cleanup_device(mps, telemetry, baseline)
    assert not result['device_recovered'] and result['final_actual_child_memory'] is None


def test_cleanup_sync_failure_is_not_recovery():
    mps = Mps(); telemetry = runner.ActualMpsTelemetry(mps); baseline = telemetry()
    def failure(): raise RuntimeError('inflight kernel')
    mps.synchronize = failure
    result = runner.cleanup_device(mps, telemetry, baseline)
    assert not result['device_recovered'] and result['error'] == 'RuntimeError'


def test_streamed_input_independent_probes_handle_permutation_and_flip():
    native = np.linspace(-1600, 2900, 13*17*19, dtype=np.float32).reshape(13, 17, 19)
    oriented = native.transpose(2, 0, 1)[::-1]
    value = runner.stream_area_input(oriented, (7, 8, 9))
    records = runner.area_probes(oriented, value, lambda: None)
    assert len(records) == 9 and max(x['absolute_error'] for x in records) < 6e-8
    value[0, 0, 0, 0, 0] += .01
    with pytest.raises(ValueError, match='SAMPLE_MISMATCH'):
        runner.area_probes(oriented, value, lambda: None)


def test_streaming_stop_checks_interrupt_before_model_work():
    count = [0]
    def check():
        count[0] += 1
        if count[0] == 5: raise RuntimeError('STOP_REQUESTED')
    with pytest.raises(RuntimeError, match='STOP'):
        runner.stream_area_input(np.zeros((17, 19, 23), dtype=np.float32), (7, 8, 9), check)
    assert count == [5]


def test_private_artifacts_reject_overwrite_and_disk_overrun(tmp_path):
    artifacts = runner.PrivateArtifacts(tmp_path/'new', 8192)
    artifacts.array('small.npy', np.zeros(4, dtype=np.float32))
    with pytest.raises(FileExistsError): artifacts.array('small.npy', np.zeros(4, dtype=np.float32))
    with pytest.raises(RuntimeError, match='OUTPUT_LIMIT'):
        artifacts.array('large.npy', np.zeros(2048, dtype=np.float32))
    with pytest.raises(FileExistsError): runner.PrivateArtifacts(tmp_path/'new', 8192)


def test_real_work_stops_after_failed_first_case_without_next_case(monkeypatch, tmp_path):
    """Exercise real orchestration; substitute tiny arrays and no Torch model."""
    import sys
    guard = Guard(); journal = runner.CallJournal(guard, tmp_path/'calls.jsonl')
    artifacts = runner.PrivateArtifacts(tmp_path/'assets', 1024*1024)
    for i in [1, 2, 3]: artifacts.array(f'case_{i}_input.npy', np.zeros((1, 1, 2, 2, 2), np.float32))
    prepared = [{'case_index': i, 'input_sha256': artifacts.assets[f'case_{i}_input.npy']} for i in [1, 2, 3]]
    monkeypatch.setattr(runner, 'prepare_inputs', lambda *a: prepared)
    monkeypatch.setattr(runner, 'lattice_from_model', lambda m: {})
    adapter = SimpleNamespace(encoder=SimpleNamespace(register_forward_pre_hook=lambda h: None))
    monkeypatch.setitem(sys.modules, 'epi_next.encoder', SimpleNamespace(load_ctfm_local=lambda *a: adapter))
    entered = []
    def fail_device(_torch, _adapter, _x, device, index, _config, _assets, _guard, count, _telemetry):
        count.reserve(index, device, 0); count.network_entry(); entered.append((index, device))
        raise RuntimeError('UNSUPPORTED_OPERATOR')
    monkeypatch.setattr(runner, 'device_runs', fail_device)
    config = {'checkpoint_sha256': 'unused', 'shape': [1, 1, 2, 2, 2]}
    result = {'cases': []}
    with pytest.raises(RuntimeError, match='UNSUPPORTED_OPERATOR'):
        runner.execute_work(SimpleNamespace(from_numpy=lambda x: x), SimpleNamespace(data=None, weights=None),
                            config, artifacts, guard, journal, SimpleNamespace(phase=''), result, {})
    assert entered == [(1, 'cpu')] and guard.visited == ['case_1']
    assert journal.actual == guard.reserved == 1


@pytest.mark.parametrize('fault', ['none', 'changed_source', 'missing_source', 'changed_spec', 'changed_revision', 'changed_supervisor_sha'])
def test_execution_bindings_fail_closed_before_torch_or_data(monkeypatch, tmp_path, fault):
    root = Path(runner.__file__).resolve().parent
    names = ['encoder_volume_runner.py', 'encoder.py', 'encoder_real_input.py', 'encoder_real_smoke.py',
             'encoder_volume_dry_run.py', 'encoder_volume_guard.py', 'encoder_ctfm_mps_smoke.py']
    spec = dict(owner='ENCODER', device='mps', max_forward=24, max_backward=0, timeout_seconds=1200,
                per_case_seconds=120, telemetry_startup_seconds=15, telemetry_max_gap_seconds=.25,
                request_grace_seconds=.25, term_grace_seconds=.75, recovery_seconds=2)
    overlay = dict(scientific_config_sha256=runner.CONFIG_SHA, resource_revision_sha256=runner.REVISION_SHA,
                   allocator_limit_bytes=runner.PRE_STOP, supervisor_package=runner.PACKAGE,
                   supervisor_bundle={'dependency_sha256': 'fixed', 'dependency_root': str(tmp_path),
                                      'package_path': str(tmp_path/runner.PACKAGE)},
                   supervision=dict(spec), source_sha256={name: runner.file_sha(root/name) for name in names})
    config = {'experiment_id': 'test-task'}
    approval = {'ctfm_implementation_binding': {'sha256': runner.CONFIG_SHA}}
    revision = {'status': 'APPROVED_RESOURCE_SEMANTICS_REVISION',
                'original_approval': {'sha256': runner.APPROVAL_SHA}}
    if fault == 'changed_source': overlay['source_sha256']['encoder.py'] = '0'*64
    if fault == 'missing_source': del overlay['source_sha256']['encoder.py']
    if fault == 'changed_spec': spec['max_forward'] = 25
    if fault == 'changed_revision': revision['status'] = 'PENDING'
    (tmp_path/'spec.json').write_text(json.dumps(dict(spec, task_key='test-task', job_id='test-job')))
    monkeypatch.setenv('EPI_NEXT_SUPERVISOR_DIR', str(tmp_path))
    monkeypatch.setenv('EPI_NEXT_DEPENDENCY_ROOT', str(tmp_path))
    monkeypatch.setenv('EPI_NEXT_DEPENDENCY_SHA', 'changed' if fault == 'changed_supervisor_sha' else 'fixed')
    documents = {'overlay': overlay, 'config': config, 'approval': approval, 'revision': revision}
    monkeypatch.setattr(runner, 'read_bound_json', lambda path, sha: documents[path])
    args = SimpleNamespace(overlay='overlay', config='config', approval='approval', revision='revision',
                           overlay_sha='test', supervisor_sha='fixed',
                           output=root.parents[2]/'.local/ctfm-volume-wave1/test-never-created')
    if fault == 'none':
        assert runner.validate_bindings(args)[0] == config
        assert not args.output.exists()
    else:
        with pytest.raises(ValueError): runner.validate_bindings(args)
