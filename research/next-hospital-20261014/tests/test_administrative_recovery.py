"""Generated fixtures only; never touches the production queue or approval assets."""
import json
from types import SimpleNamespace
import pytest
from epi_next.artifacts import canonical_json, sha256
from epi_next.execution_lock import validate_administrative_recovery, tracked_device_slot
from epi_next import hospital_runtime, wave1_supervisor, execution_lock


def fixture(tmp_path):
    queue=tmp_path/'queue'; slot=queue/'slots'/'old';slot.mkdir(parents=True)
    def save(path,value):
        path.write_bytes(canonical_json(value))
        return {'path':str(path),'digest':sha256(path.read_bytes())}
    start=save(slot/'started.json',{'job_id':'old','task_key':'spent','device':'mps'})
    receipt=save(tmp_path/'receipt.json',{'job_id':'old','status':'BLOCKED','slot_completed':False})
    raw=tmp_path/'sample.jsonl';raw.write_text('generated\n')
    review=save(tmp_path/'r0.json',{'status':'REVIEW_CONDITIONS_MET_NOT_DEVICE_RECOVERY_PROOF',
        'schema':'EPI_NEXT_R0_ONCE_READONLY','no_gpu_probe':True,'no_process_signals':True,
        'samples':61,'checks':{k:True for k in ['61_samples_no_missing','timing_bounds',
            'free_all_at_least20','swap_delta_strict_less1GiB','no_registered_identity_rows']},'unknown_slot_changed':False,
        'finished_exists_after':False,'model_calls':0,'raw_sha256':{raw.name:sha256(raw.read_bytes())}})
    scope={'old_job_id':'old','old_task_key':'spent','started_sha256':start['digest'],
           'supervisor_reference':receipt,'r0_reference':review,'allowed_next_task_keys':['next']}
    approval=save(tmp_path/'approval.json',{'schema':'EPI-NEXT-OWNER-RECOVERY-APPROVAL-1',
        'status':'EXPLICIT_ADMINISTRATIVE_RECOVERY_APPROVED','principal':'钟佳桦',
        'scope_sha256':sha256(canonical_json(scope))})
    decision={'schema':'EPI-NEXT-ADMINISTRATIVE-RECOVERY-1','status':'APPROVED_ADMINISTRATIVE_RECOVERY',
              'queue_root':str(queue),'historical_status_unchanged':True,'model_authorization_granted':False,
              'scope':scope,'approval_reference':approval}
    binding=save(tmp_path/'decision.json',decision)
    return queue,slot,binding,decision,save


def test_shared_gates_consume_bound_decision_without_repair(tmp_path,monkeypatch):
    queue,slot,binding,decision,save=fixture(tmp_path)
    before={p.name:p.read_bytes() for p in slot.iterdir()}
    monkeypatch.setattr(hospital_runtime,'QUEUE_ROOT',queue)
    monkeypatch.setattr(execution_lock,'verify_dependencies',lambda *args:None)
    monkeypatch.setattr(wave1_supervisor,'_run_supervised',lambda *args,**kw:kw)
    args={'recovery_decision_path':binding['path'],'recovery_decision_sha':binding['digest']}
    spec=SimpleNamespace(task_key='next')
    with pytest.raises(RuntimeError,match='GLOBAL_UNKNOWN'):wave1_supervisor.run_supervised(spec,[],None,None,None)
    assert wave1_supervisor.run_supervised(spec,[],None,None,None,**args)['recovery_decision_sha']==binding['digest']
    with tracked_device_slot('mps',owner='ENCODER',job_id='new',task_key='next',
            budget={'max_model_calls':0,'max_seconds':1,'max_rss_bytes':1000,'max_mps_driver_bytes':1000},
            dependency_root=tmp_path,dependency_sha='fixture',**args) as new:
        assert new.record['administrative_recovery']['decision_sha256']==binding['digest']
    assert before=={p.name:p.read_bytes() for p in slot.iterdir()}
    assert not (slot/'finished.json').exists()
    # A second unknown slot cannot be excused by the first decision.
    with pytest.raises(RuntimeError,match='GLOBAL_UNKNOWN'):wave1_supervisor.run_supervised(spec,[],None,None,None,**args)


@pytest.mark.parametrize('mutation', ['hash','task','approval','raw','start','finished','scope'])
def test_invalid_recovery_fails_closed(tmp_path,mutation):
    queue,slot,binding,decision,save=fixture(tmp_path)
    task='next'
    if mutation=='hash':binding['digest']='0'*64
    if mutation=='task':task='spent'
    if mutation=='approval':
        decision['approval_reference']=save(tmp_path/'approval.json',{'status':'APPROVED_ONCE_READONLY'})
        binding=save(tmp_path/'decision.json',decision)
    if mutation=='raw':(tmp_path/'sample.jsonl').write_text('changed')
    if mutation=='start':(slot/'started.json').write_text('{}')
    if mutation=='finished':(slot/'finished.json').write_text('{}')
    if mutation=='scope':
        decision['scope']['allowed_next_task_keys'].append('unauthorized')
        binding=save(tmp_path/'decision.json',decision)
    with pytest.raises(ValueError):validate_administrative_recovery(queue,task,binding['path'],binding['digest'])


def test_duplicate_task_remains_fenced(tmp_path,monkeypatch):
    queue,slot,binding,decision,save=fixture(tmp_path)
    other=queue/'slots'/'done';other.mkdir()
    save(other/'started.json',{'task_key':'next'})
    save(other/'finished.json',{})
    monkeypatch.setattr(hospital_runtime,'QUEUE_ROOT',queue)
    with pytest.raises(RuntimeError,match='DUPLICATE_TASK'):
        wave1_supervisor.run_supervised(SimpleNamespace(task_key='next'),[],None,None,None,
            recovery_decision_path=binding['path'],recovery_decision_sha=binding['digest'])
