"""Local fixed-bundle seams with fake MPS numbers; no slot or model launch."""

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[3]
from dataclasses import asdict
import json
from pathlib import Path
import time

import pytest

from epi_next.encoder_volume_runner import ActualMpsTelemetry, CallJournal, load_supervisor

BUNDLE = Path(str(_PUBLIC_ROOT / 'research/next-hospital-20261014/.local/phase2/wave1-supervisor-aca34f9-v1/bundle_receipt.json'))


@pytest.fixture
def shared():
    if not BUNDLE.is_file(): pytest.skip('fixed local INTEGRATION bundle unavailable')
    bundle = json.loads(BUNDLE.read_bytes())
    assert bundle['dependency_sha256'] == '0000000000000000000000000000000000000000000000000000000000000000'
    assert bundle['import_manifest_sha256'] == '0000000000000000000000000000000000000000000000000000000000000000'
    return load_supervisor({'supervisor_bundle': bundle}), bundle


@pytest.fixture
def make_guard(shared, tmp_path, monkeypatch):
    module, bundle = shared
    spec = module.SupervisionSpec(job_id='synthetic-contract-test', task_key='synthetic-only', owner='ENCODER',
                                  device='mps', max_forward=24, max_backward=0,
                                  timeout_seconds=1200, per_case_seconds=120)
    (tmp_path/'spec.json').write_text(json.dumps(asdict(spec)))
    (tmp_path/'counters.json').write_text(json.dumps(dict(job_id=spec.job_id, forward=0, backward=0, sequence=0, cases={})))
    (tmp_path/'ADMITTED').write_text('SYNTHETIC FIXTURE ONLY; NO SUPERVISOR JOB')
    monkeypatch.setenv('EPI_NEXT_SUPERVISOR_DIR', str(tmp_path))
    monkeypatch.setenv('EPI_NEXT_JOB_STARTED_MONOTONIC', str(time.monotonic()))
    monkeypatch.setenv('EPI_NEXT_DEPENDENCY_ROOT', bundle['dependency_root'])
    monkeypatch.setenv('EPI_NEXT_DEPENDENCY_SHA', bundle['dependency_sha256'])
    guards = []
    def create(callback=lambda: {'driver_bytes': 300, 'tensor_bytes': 100}):
        guard = module.ChildGuard.from_environment(mps_driver=callback)
        guards.append(guard)
        return guard
    yield create
    for guard in guards:
        if not guard.done.is_set(): guard.close()


def test_real_guard_stop_file_and_complete_schema(shared, make_guard, tmp_path):
    module, _ = shared
    guard = make_guard(); journal = CallJournal(guard, tmp_path/'adapter-calls.jsonl')
    guard.begin_case('case_1'); journal.reserve(1, 'mps', 0); journal.network_entry()
    (tmp_path/'STOP').write_text('synthetic trigger')
    with pytest.raises(module.StopWork): journal.reserve(1, 'mps', 1)
    guard.complete(status='PARTIAL_BUDGET', reason='synthetic stop', device_recovered=False,
                   actual_forward=journal.actual, actual_backward=0)
    completion = json.loads((tmp_path/'runner-complete.json').read_bytes())
    telemetry = json.loads((tmp_path/'telemetry.json').read_bytes())
    assert completion['actual_forward'] == 1 and completion['status'] == 'PARTIAL_BUDGET'
    assert telemetry['stop_seen'] and telemetry['mps_driver_bytes'] == 300 and telemetry['mps_tensor_bytes'] == 100
    assert not telemetry['device_recovered']


def test_real_guard_counter_and_case_cannot_reset_on_recreation(shared, make_guard, tmp_path):
    module, _ = shared
    first = make_guard(); first.begin_case('case_1')
    for _ in range(24): first.before_forward()
    first.close()
    second = make_guard()
    with pytest.raises(module.StopWork, match='CALL_BUDGET'): second.before_forward()
    with pytest.raises(module.StopWork, match='CASE_ALREADY_STARTED'): second.begin_case('case_1')
    assert json.loads((tmp_path/'counters.json').read_bytes())['forward'] == 24


def test_real_guard_per_case_and_global_deadlines_fence_forward(shared, make_guard):
    module, _ = shared; guard = make_guard(); guard.begin_case('case_1')
    guard.case_started = time.monotonic()-120
    with pytest.raises(module.StopWork, match='CASE_DEADLINE'): guard.before_forward()
    guard.end_case(); guard.started = time.monotonic()-1200
    with pytest.raises(module.StopWork, match='GLOBAL_DEADLINE'): guard.before_forward()
    with guard.ledger() as ledger: assert ledger['forward'] == 0


def test_real_guard_rejects_actual_above_reserved(shared, make_guard, tmp_path):
    guard = make_guard()
    with pytest.raises(ValueError, match='MUST_NOT_EXCEED'):
        guard.complete(actual_forward=1, actual_backward=0)
    assert not (tmp_path/'runner-complete.json').exists()


def test_real_guard_telemetry_error_stops_new_work(shared, make_guard, tmp_path):
    module, _ = shared
    class FailedMps:
        def driver_allocated_memory(self): raise RuntimeError('injected API failure')
    telemetry = ActualMpsTelemetry(FailedMps())
    try:
        guard = make_guard(telemetry)
    except module.StopWork:
        # Startup may see the callback failure before returning the guard.
        return
    assert guard.stop.wait(.5)
    with pytest.raises(module.StopWork): guard.before_forward()
    guard.done.set(); guard.thread.join(timeout=1)
    # Do not mark recovery; fake API remains failed. Restore fixture signal handlers.
    import signal
    for sig, handler in guard._previous_handlers.items(): signal.signal(sig, handler)
    assert telemetry.report()['missing_measurements'] >= 1
    assert not (tmp_path/'runner-complete.json').exists()
