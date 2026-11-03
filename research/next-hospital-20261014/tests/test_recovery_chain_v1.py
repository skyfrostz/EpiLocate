"""Two bound historical slots; generated files and isolated queue only."""
import importlib
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import uuid

import pytest

BASE = Path(__file__).resolve().parents[1]
OLD = BASE / '.local/phase2/wave1-supervisor-c9f5369-recovery-v3/epinext_wave1_supervisor_recovery_v3'
NEW = BASE / 'runtime/recovery_chain_v1'
MODULES = ('wave1_supervisor', 'execution_lock', 'coordinator_writer', 'artifacts',
           'hospital_runtime', 'hospital_contract', 'contracts', 'geometry')


@pytest.fixture
def modules(tmp_path, monkeypatch):
    name = 'generated_chain_' + uuid.uuid4().hex
    root = tmp_path / name
    root.mkdir(); (root / '__init__.py').write_text('')
    for module in MODULES:
        source = NEW if module in {'wave1_supervisor', 'execution_lock'} else OLD
        shutil.copyfile(source / (module + '.py'), root / (module + '.py'))
    monkeypatch.syspath_prepend(str(tmp_path))
    loaded = {module: importlib.import_module(name + '.' + module) for module in MODULES}
    yield SimpleNamespace(**loaded)
    for module in list(sys.modules):
        if module == name or module.startswith(name + '.'):
            del sys.modules[module]


def lineage(tmp_path, modules):
    tmp_path = tmp_path.resolve()
    queue = tmp_path / 'queue'
    canonical = modules.artifacts.canonical_json
    sha = modules.artifacts.sha256
    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical(value))
        return {'path': str(path), 'digest': sha(path.read_bytes())}
    def signed(name, scope):
        approval = save(tmp_path / (name + '-owner.json'), {
            'schema': 'EPI-NEXT-OWNER-RECOVERY-APPROVAL-1',
            'status': 'EXPLICIT_ADMINISTRATIVE_RECOVERY_APPROVED',
            'principal': 'project-owner', 'scope_sha256': sha(canonical(scope))})
        decision = dict(schema='EPI-NEXT-ADMINISTRATIVE-RECOVERY-1',
            status='APPROVED_ADMINISTRATIVE_RECOVERY', queue_root=str(queue),
            historical_status_unchanged=True, model_authorization_granted=False,
            scope=scope, approval_reference=approval)
        return save(tmp_path / (name + '-decision.json'), decision), decision
    def incident(job, task, review_schema, parent=None):
        slot = queue / 'slots' / job
        start = {'job_id': job, 'task_key': task, 'device': 'mps'}
        if parent:
            start['administrative_recovery'] = {k: parent[k] for k in
                ('old_job_id', 'decision_path', 'decision_sha256', 'scope_sha256')}
        start_ref = save(slot / 'started.json', start)
        receipt = save(tmp_path / (job + '-receipt.json'), {
            'job_id': job, 'status': 'BLOCKED', 'slot_completed': False})
        raw = tmp_path / job / 'samples.jsonl'
        raw.parent.mkdir(); raw.write_text('generated sample only\n')
        review = save(raw.parent / 'result.json', {
            'schema': review_schema, 'status': 'REVIEW_CONDITIONS_MET_NOT_DEVICE_RECOVERY_PROOF',
            'samples': 61, 'checks': {k: True for k in ['61_samples_no_missing', 'timing_bounds',
                'free_all_at_least20', 'swap_delta_strict_less1GiB', 'no_registered_identity_rows']},
            'unknown_slot_changed': False, 'finished_exists_after': False,
            'model_calls': 0, 'no_gpu_probe': True, 'no_process_signals': True,
            'raw_sha256': {raw.name: sha(raw.read_bytes())}})
        return dict(old_job_id=job, old_task_key=task, started_sha256=start_ref['digest'],
            supervisor_reference=receipt, r0_reference=review, allowed_next_task_keys=[])
    old_scope = incident('old128', 'spent128', 'EPI_NEXT_R0_ONCE_READONLY')
    old_scope['allowed_next_task_keys'] = ['spent-c1']
    old_ref, old_decision = signed('old', old_scope)
    parent = modules.execution_lock.validate_administrative_recovery(queue, 'spent-c1',
        old_ref['path'], old_ref['digest'])
    scope = incident('old-c1', 'spent-c1', 'EPI_NEXT_R1_ONCE_READONLY', parent)
    scope.update(allowed_next_task_keys=['new-p1', 'new-mvp'],
        review_role='R1_NEW_C1_READONLY_REVIEW', predecessor_recovery_reference=old_ref,
        predecessor_validation_task_key='spent-c1')
    binding, decision = signed('new', scope)
    return SimpleNamespace(queue=queue, scope=scope, old_scope=old_scope,
        old_ref=old_ref, binding=binding, decision=decision, signed=signed, save=save)


def validate(m, f, task='new-p1', **kwargs):
    return m.execution_lock.validate_administrative_recovery(f.queue, task,
        f.binding['path'], f.binding['digest'], **kwargs)


def test_two_slots_and_both_tasks_pass_readonly(modules, tmp_path):
    f = lineage(tmp_path, modules)
    before = {str(p): p.read_bytes() for p in f.queue.rglob('*') if p.is_file()}
    for task in ['new-p1', 'new-mvp']:
        receipt = validate(modules, f, task)
        assert receipt['old_job_ids'] == ['old128', 'old-c1']
        assert len(receipt['validated_recovery_chain']) == 2
    assert before == {str(p): p.read_bytes() for p in f.queue.rglob('*') if p.is_file()}
    assert not list(f.queue.rglob('finished.json'))


def test_shared_serial_and_device_gates_only_excuse_bound_slots(modules, tmp_path, monkeypatch):
    f = lineage(tmp_path, modules)
    monkeypatch.setattr(modules.hospital_runtime, 'QUEUE_ROOT', f.queue)
    monkeypatch.setattr(modules.execution_lock, 'verify_dependencies', lambda *args: None)
    monkeypatch.setattr(modules.wave1_supervisor, '_run_supervised', lambda *args, **kw: kw)
    args = dict(recovery_decision_path=f.binding['path'], recovery_decision_sha=f.binding['digest'])
    assert modules.wave1_supervisor.run_supervised(SimpleNamespace(task_key='new-p1'), [],
        None, None, None, **args)['recovery_decision_sha'] == f.binding['digest']
    with modules.execution_lock.tracked_device_slot('cpu', owner='INTEGRATION', job_id='next',
            task_key='new-mvp', budget={'max_model_calls': 0, 'max_seconds': 1, 'max_rss_bytes': 1000},
            dependency_root=tmp_path, dependency_sha='fixture', **args) as new:
        assert new.record['administrative_recovery']['old_job_ids'] == ['old128', 'old-c1']
    with pytest.raises(RuntimeError, match='GLOBAL_UNKNOWN'):
        modules.wave1_supervisor.run_supervised(SimpleNamespace(task_key='new-p1'), [],
            None, None, None, **args)
    with pytest.raises(RuntimeError, match='PRIOR_SLOT_UNKNOWN'):
        with modules.execution_lock.tracked_device_slot('cpu', owner='INTEGRATION', job_id='other',
                task_key='new-p1', budget={'max_model_calls': 0, 'max_seconds': 1, 'max_rss_bytes': 1000},
                dependency_root=tmp_path, dependency_sha='fixture', **args):
            pytest.fail('unlisted third slot admitted')


@pytest.mark.parametrize('mutation', ['old-start', 'new-start', 'old-raw', 'new-raw',
    'old-owner', 'new-owner', 'missing-parent', 'parent-task', 'slot-parent', 'r1-role',
    'parent-next-task', 'finished', 'cycle', 'depth'])
def test_chain_drift_missing_or_rebound_evidence_rejected(modules, tmp_path, mutation):
    f = lineage(tmp_path, modules)
    if mutation.endswith('start'):
        job = 'old128' if mutation == 'old-start' else 'old-c1'
        (f.queue / 'slots' / job / 'started.json').write_text('{}')
    elif mutation.endswith('raw'):
        job = 'old128' if mutation == 'old-raw' else 'old-c1'
        (tmp_path / job / 'samples.jsonl').write_text('drift')
    elif mutation.endswith('owner'):
        (tmp_path / ('old-owner.json' if mutation == 'old-owner' else 'new-owner.json')).write_text('{}')
    elif mutation == 'missing-parent':
        f.scope.pop('predecessor_recovery_reference')
    elif mutation == 'parent-task':
        f.scope['predecessor_validation_task_key'] = 'new-p1'
    elif mutation == 'slot-parent':
        p = f.queue / 'slots/old-c1/started.json';d = json.loads(p.read_text())
        d['administrative_recovery']['decision_sha256'] = '0' * 64
        f.scope['started_sha256'] = f.save(p, d)['digest']
    elif mutation == 'r1-role':
        f.scope['review_role'] = 'wrong'
    elif mutation == 'parent-next-task':
        f.old_scope['allowed_next_task_keys'] = ['new-p1']
        ref, _ = f.signed('old', f.old_scope)
        f.scope['predecessor_recovery_reference'] = ref
    elif mutation == 'finished':
        f.save(f.queue / 'slots/old128/finished.json', {})
    if mutation in {'missing-parent', 'parent-task', 'slot-parent', 'r1-role', 'parent-next-task'}:
        f.binding, f.decision = f.signed('new', f.scope)
    kwargs = {}
    if mutation == 'cycle':kwargs['_chain'] = ((f.binding['path'], f.binding['digest']),)
    if mutation == 'depth':kwargs['_chain'] = (('one', 'one'), ('two', 'two'))
    with pytest.raises(ValueError):validate(modules, f, **kwargs)


@pytest.mark.parametrize('task', ['spent128', 'spent-c1', 'unlisted'])
def test_spent_or_unlisted_task_rejected(modules, tmp_path, task):
    with pytest.raises(ValueError, match='NEXT_TASK_NOT_APPROVED'):
        validate(modules, lineage(tmp_path, modules), task)


def test_same_task_cannot_restart_even_with_valid_chain(modules, tmp_path, monkeypatch):
    f = lineage(tmp_path, modules)
    f.save(f.queue / 'slots/already-used/started.json', {'task_key': 'new-p1'})
    f.save(f.queue / 'slots/already-used/finished.json', {})
    monkeypatch.setattr(modules.hospital_runtime, 'QUEUE_ROOT', f.queue)
    with pytest.raises(RuntimeError, match='DUPLICATE_TASK'):
        modules.wave1_supervisor.run_supervised(SimpleNamespace(task_key='new-p1'), [], None,
            None, None, recovery_decision_path=f.binding['path'], recovery_decision_sha=f.binding['digest'])
