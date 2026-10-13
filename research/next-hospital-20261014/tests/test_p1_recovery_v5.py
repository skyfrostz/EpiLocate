"""Fixed v3 recovery consumption in isolated generated queues only."""

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[3]
import copy
import json
from pathlib import Path
import sys
import pytest
from epi_next import p1_recovery_v5 as recovery,p1_runner_v4 as worker
from epi_next.shared_runner_binding_v3 import load_supervisor_bundle

INDEX=Path(str(_PUBLIC_ROOT / 'hospital-release/20261010-recovery-readiness-v9/CONSUMPTION_INDEX.json'))
BASE=Path(__file__).resolve().parents[3]/'.local/phase2/p1-engineering-v4/readiness-final.json'


def fixture(tmp_path,monkeypatch):
    index=json.loads(INDEX.read_text())
    supervisor=load_supervisor_bundle(index['dependency_root'],recovery.DEPENDENCY_SHA)
    execution=sys.modules[supervisor.__package__+'.execution_lock']
    runtime=sys.modules[supervisor.__package__+'.hospital_runtime']
    canonical=sys.modules[supervisor.__package__+'.artifacts'].canonical_json
    queue=tmp_path/'GENERATED_QUEUE';slot=queue/'slots'/'generated-old';slot.mkdir(parents=True)
    monkeypatch.setattr(runtime,'QUEUE_ROOT',queue)
    def save(path,value):
        path.write_bytes(canonical(value));return {'path':str(path),'digest':worker.file_sha(path)}
    start=save(slot/'started.json',{'job_id':'generated-old','task_key':'generated-spent','device':'cpu'})
    receipt=save(tmp_path/'old-receipt.json',{'job_id':'generated-old','status':'BLOCKED','slot_completed':False})
    raw=tmp_path/'generated-r0-raw.jsonl';raw.write_text('generated fixture; no sampling\n')
    r0=save(tmp_path/'r0.json',{'status':'REVIEW_CONDITIONS_MET_NOT_DEVICE_RECOVERY_PROOF',
        'schema':'EPI_NEXT_R0_ONCE_READONLY','no_gpu_probe':True,'no_process_signals':True,
        'samples':61,'checks':{k:True for k in ('61_samples_no_missing','timing_bounds','free_all_at_least20',
            'swap_delta_strict_less1GiB','no_registered_identity_rows')},'unknown_slot_changed':False,
        'finished_exists_after':False,'model_calls':0,'raw_sha256':{raw.name:worker.file_sha(raw)}})
    scope={'old_job_id':'generated-old','old_task_key':'generated-spent','started_sha256':start['digest'],
        'supervisor_reference':receipt,'r0_reference':r0,'allowed_next_task_keys':['generated-P1']}
    approval=save(tmp_path/'owner.json',{'schema':'EPI-NEXT-OWNER-RECOVERY-APPROVAL-1',
        'status':'EXPLICIT_ADMINISTRATIVE_RECOVERY_APPROVED','principal':'project-owner',
        'scope_sha256':execution.sha256(canonical(scope))})
    decision=save(tmp_path/'decision.json',{'schema':'EPI-NEXT-ADMINISTRATIVE-RECOVERY-1',
        'status':'APPROVED_ADMINISTRATIVE_RECOVERY','queue_root':str(queue),
        'historical_status_unchanged':True,'model_authorization_granted':False,'scope':scope,'approval_reference':approval})
    index_ref=recovery.reference(INDEX);decision_ref={'path':decision['path'],'sha256':decision['digest']}
    _,binding=recovery.recovery_context(index_ref,decision_ref,'generated-P1')
    ready=json.loads(BASE.read_text())
    ready.update(schema='P1_RECOVERY_READINESS_V5',recovery_binding=binding,dependency_root=index['dependency_root'],
        dependency_sha256=recovery.DEPENDENCY_SHA,supervisor_job_id='generated-new',supervisor_task_key='generated-P1',
        supervision_output_root=str(tmp_path/'supervision'),execution_output=str(tmp_path/'runner'),
        parent_source_sha256=worker.file_sha(recovery.__file__),python_executable=str(Path(sys.executable).absolute()),
        cwd=str(Path.cwd().resolve()),local_source_bindings={str(Path(worker.__file__).with_name(n).resolve()):
            worker.file_sha(Path(worker.__file__).with_name(n)) for n in worker.MODULES})
    ready_path=tmp_path/'ready.json';ready_path.write_text(json.dumps(ready));ready_ref=recovery.reference(ready_path)
    lock=recovery.dispatch_template(ready,ready_ref)
    lock.update(status='LOCKED_FOR_P1_CPU_EXECUTION',real_model_execution_authorized=True,unique_queue_verified_by_chief=True)
    return supervisor,queue,slot,ready,ready_ref,lock,decision_ref


def test_fixed_bundle_full_recovery_closure_dispatch_and_drift(tmp_path,monkeypatch):
    _,_,slot,ready,ready_ref,lock,_=fixture(tmp_path,monkeypatch)
    before=slot.joinpath('started.json').read_bytes()
    worker.verify_dispatch(ready,ready_ref['sha256'],lock)
    assert set(ready['recovery_binding']['modules'])==recovery.NAMES
    assert ready['recovery_binding']['owner_approval']['sha256']!=worker.APPROVAL_SHA
    bad=copy.deepcopy(lock);bad['unique_queue_verified_by_chief']=False
    with pytest.raises(ValueError,match='EXACT_RECOVERY'):worker.verify_dispatch(ready,ready_ref['sha256'],bad)
    bad=copy.deepcopy(lock);bad['recovery_binding']['r0']['sha256']='0'*64
    with pytest.raises(ValueError,match='EXACT_RECOVERY'):worker.verify_dispatch(ready,ready_ref['sha256'],bad)
    Path(ready['recovery_binding']['r0_raw'][0]['path']).write_text('changed')
    with pytest.raises(ValueError,match='RAW_SHA'):worker.verify_dispatch(ready,ready_ref['sha256'],lock)
    assert slot.joinpath('started.json').read_bytes()==before and not slot.joinpath('finished.json').exists()


def test_template_and_omitted_recovery_refuse_before_load_or_slot(tmp_path,monkeypatch):
    _,_,_,ready,ready_ref,lock,_=fixture(tmp_path,monkeypatch)
    template=recovery.dispatch_template(ready,ready_ref)
    monkeypatch.setattr(worker,'consume_inputs',lambda *a:pytest.fail('no arrays'))
    monkeypatch.setattr(worker,'bind_child',lambda *a,**k:pytest.fail('no slot'))
    with pytest.raises(ValueError,match='DISPATCH'):worker.verify_dispatch(ready,ready_ref['sha256'],template)
    bad=copy.deepcopy(lock);bad.pop('recovery_binding')
    with pytest.raises(ValueError,match='RECOVERY'):worker.verify_dispatch(ready,ready_ref['sha256'],bad)


def test_parent_passes_both_recovery_args_and_preserves_unknown_slot(tmp_path,monkeypatch):
    supervisor,queue,slot,ready,ready_ref,lock,decision_ref=fixture(tmp_path,monkeypatch)
    lock_path=tmp_path/'dispatch.json';lock_path.write_text(json.dumps(lock));lock_ref=recovery.reference(lock_path)
    seen={}
    def fake_run(spec,command,output,root,digest,**kwargs):
        seen.update(kwargs);seen['spec']=spec;seen['command']=command
        # Execute the REAL outer serial/unknown gate; stub only actual child.
        return original(spec,command,output,root,digest,**kwargs)
    original=supervisor.run_supervised
    monkeypatch.setattr(supervisor,'run_supervised',fake_run)
    monkeypatch.setattr(supervisor,'_run_supervised',lambda *a,**kw:{'status':'NOT RUN','kwargs':kw})
    for k,v in {'PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1',
        'PYTHONPATH':str(Path(worker.__file__).resolve().parents[1])}.items():monkeypatch.setenv(k,v)
    before={p.name:p.read_bytes() for p in slot.iterdir()}
    result=recovery.run_parent(ready_ref,lock_ref)
    assert result['status']=='NOT RUN'
    assert seen['recovery_decision_path']==decision_ref['path'] and seen['recovery_decision_sha']==decision_ref['sha256']
    assert seen['spec'].max_forward==27027 and seen['spec'].max_backward==27000
    assert 'epi_next.p1_runner_v4' in seen['command'] and '--lock-sha' in seen['command']
    assert before=={p.name:p.read_bytes() for p in slot.iterdir()}
    other=queue/'slots'/'second-unknown';other.mkdir();(other/'started.json').write_text('{}')
    with pytest.raises(RuntimeError,match='GLOBAL_UNKNOWN'):recovery.run_parent(ready_ref,lock_ref)


def test_real_fixed_v3_parent_child_generated_one_forward_backward(tmp_path,monkeypatch):
    supervisor,queue,slot,ready,ready_ref,lock,_=fixture(tmp_path,monkeypatch)
    lock_path=tmp_path/'dispatch.json';lock_path.write_text(json.dumps(lock));lock_ref=recovery.reference(lock_path)
    for k,v in {'PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1',
        'PYTHONPATH':str(Path(worker.__file__).resolve().parents[1])}.items():monkeypatch.setenv(k,v)
    # No patient loader and no P1 engine; one generated scalar autograd operation.
    script=tmp_path/'generated_child.py';script.write_text('''import os,torch
from epi_next.shared_runner_binding_v3 import load_supervisor_bundle
s=load_supervisor_bundle(os.environ['EPI_NEXT_DEPENDENCY_ROOT'],os.environ['EPI_NEXT_DEPENDENCY_SHA'])
g=s.ChildGuard.from_environment()
g.begin_case('GENERATED_SCALAR_ONLY')
x=torch.tensor(2.,requires_grad=True)
g.before_forward();y=x.square()
g.before_backward();y.backward()
assert x.grad.item()==4.
g.end_case()
g.complete(status='SUCCESS',device_recovered=True,actual_forward=1,actual_backward=1)
''')
    monkeypatch.setattr(recovery,'worker_command',lambda *a:[sys.executable,str(script)])
    before={p.name:p.read_bytes() for p in slot.iterdir()}
    result=recovery.run_parent(ready_ref,lock_ref)
    assert result['status']=='SUCCESS' and result['slot_completed'] is True
    assert before=={p.name:p.read_bytes() for p in slot.iterdir()} and not (slot/'finished.json').exists()
    counters=json.loads((Path(ready['supervision_output_root'])/'generated-new'/'counters.json').read_text())
    assert counters['forward']==counters['backward']==1
    new_start=json.loads((queue/'slots/generated-new/started.json').read_text())
    assert new_start['administrative_recovery']['decision_sha256']==ready['recovery_binding']['decision']['sha256']
    assert (queue/'slots/generated-new/finished.json').exists()
