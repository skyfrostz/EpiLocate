"""Generated loader/dispatch seams only; no patient arrays, weights, locks or queue."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager

import pytest

from qa import next_e2_readout as entry
from epilocate_next.e2_readout_launch import run_existing_readout, ReadoutFailure

ROOT = Path(__file__).resolve().parents[1]
LOC = ROOT.parent/'epi-next-localization/research/next-hospital-20261014'
BINDING = ROOT/'.local/e2-r-readout-r79-20261013/execution-binding-r79-v1.json'


def write(path, value, raw=False):
    data = value if raw else json.dumps(value).encode()
    path.write_bytes(data)
    return dict(path=str(path), sha256=hashlib.sha256(data).hexdigest())


class Guard:
    def __init__(self): self.started=time.monotonic(); self.forward=0; self.backward=0; self.begun=[]
    def check(self): pass
    def begin_case(self, key): self.begun.append(key)
    def end_case(self): self.begun.append('END')
    def before_forward(self): self.forward += 1
    def before_backward(self): self.backward += 1


@pytest.fixture
def generated(tmp_path):
    # Reuse LOC's generated setup, not its clinical loaders or real artifacts.
    sys.path.insert(0,str(LOC))
    spec=importlib.util.spec_from_file_location('_loc_readout_generated_test',LOC/'tests/test_target_readout_v5.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    p,i,c,payload,r,raw,g=module.setup.__wrapped__()
    model=module.Generated();model.predict_numpy=model.numpy
    req=dict(schema_version='EPI_NEXT_APPLICATION_REQUEST_V1',algorithm_mode='E2',method_mode='E2-CT',
        algorithm_version='E2_R_READOUT_V5',config_sha256=c.sha256(),execution_mode='SYNTHETIC',
        input=dict(case_id='generated-case',study_id='generated-study',series_id='generated-series',
            slice_id='generated-slice',input_sha256='4'*64,display_sha256='4'*64,scope='SINGLE_SLICE',
            display_kind='RESEARCH_ARRAY',source_identity_status='SYNTHETIC',native_shape_zyx=[248,512,512],
            model_shape=[224,224],native_slice_index=123,affine_lps=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],
            geometry_ledger_sha256='5'*64,mapping_qa_sha256='5'*64,mapping_verified=True),
        model=dict(model_id='generated',checkpoint_sha256=i['model_sha256'],
            preprocessing_version='generated-preproc',preprocessing_sha256=i['preprocessing_sha256'],protocol_id='generated'),
        task=dict(definition_id='GENERATED_ONLY',unit='SLICE',class_labels=['model_class_0','model_class_1'],target_class=1),
        budget=dict(forward=18,backward=0,updates=0,seconds=120,output_bytes=67108864))
    fields=dict(job_id=entry.JOB,application_request=req,prepared_delivery={},preparation_config={},
        scientific_request={},loc_dependency_lock=write(tmp_path/'lock.json',{}),
        localization_root=str(LOC/'epi_next'),integration_bridge_source=str(ROOT/'research/next-hospital-20261014/epi_next'),
        case_index=3,mapping_qa_sha256='5'*64,reuse_stage1={})
    v=dict(job_id=entry.JOB,existing_e2_binding=fields,readout_request=write(tmp_path/'request.json',r),
        saved_fidelity=write(tmp_path/'saved.json',raw,True),output_root=str(tmp_path/'output'),_binding_sha256='6'*64)
    loads=[]
    def load(_):loads.append('model');return model
    adapter=SimpleNamespace(prepare=lambda *_:SimpleNamespace(prepared=p,geometry=g),
        reuse_provider=lambda _:(payload,r['reuse_payload_canonical_sha256']),
        model=load,config=lambda _:c,model_adapter_sha256=i['model_adapter_sha256'])
    kwargs=dict(modules=(None,SimpleNamespace(BudgetStopped=module.old_fidelity.__globals__['BudgetStopped']),None),
        readout=sys.modules['epi_next.e2_readout_v5'],
        runner_builder=lambda *a,**k:SimpleNamespace(handlers={'E2':adapter}))
    return v,Guard(),kwargs,model,loads,r,payload


def test_same_loader_four_reuse_fourteen_actual_forward(generated):
    v,guard,kwargs,model,loads,_,_=generated
    out=run_existing_readout(v,guard,**kwargs)
    assert out['status']=='SUCCESS',out['error']
    assert out['new_cost']['forward']==guard.forward==model.calls==14
    assert out['historical_logits_reused']==4 and len(out['responses'])==16
    assert guard.backward==out['new_cost']['optimizer_steps']==0
    assert loads==['model'] and len(out['adapter_checks'])==2
    assert (Path(v['output_root'])/'readout.json').stat().st_size<67108864
    assert guard.begun==[entry.JOB,'END']


def test_adapter_mismatch_is_two_billed_calls_and_no_fallback(generated):
    import numpy as np
    v,guard,kwargs,model,_,_,_=generated
    model.predict_numpy=lambda x:model.numpy(x)+np.array([0.,.01])
    out=run_existing_readout(v,guard,**kwargs)
    assert out['status']=='FAILED' and guard.forward==model.calls==out['new_cost']['forward']==2
    assert not out['responses'] and len(out['unrun_objects'])==16


def test_loading_time_uses_parent_clock_without_reset(generated):
    v,guard,kwargs,model,_,_,_=generated
    guard.started -= 121
    out=run_existing_readout(v,guard,**kwargs)
    assert out['status']=='PARTIAL_BUDGET' and out['new_cost']['forward']==guard.forward==model.calls==0
    assert out['stop_events'][0]['kind']=='TIME_BUDGET'


def test_incompatible_historical_logits_stop_before_model_load(generated,tmp_path):
    v,guard,kwargs,model,loads,r,payload=generated
    raw=json.loads(Path(v['saved_fidelity']['path']).read_bytes());raw['responses']['original']['logits']=[[0,99]]
    v['saved_fidelity']=write(tmp_path/'wrong-saved.json',raw)
    r['saved_fidelity']['file_sha256']=v['saved_fidelity']['sha256']
    v['readout_request']=write(tmp_path/'wrong-request.json',r)
    with pytest.raises(ReadoutFailure) as error:run_existing_readout(v,guard,**kwargs)
    assert error.value.actual_forward==error.value.actual_backward==0
    failure=json.loads((Path(v['output_root'])/'entry-failure.json').read_bytes())
    assert failure['new_cost']['forward']==guard.forward==model.calls==0 and not loads


def fake_supervisor():
    calls=[]
    wave=SimpleNamespace(SupervisionSpec=lambda **k:SimpleNamespace(**k),
        run_supervised=lambda *a,**k:calls.append((a,k)) or dict(status='SUCCESS'))
    return lambda _:dict(wave1_supervisor=wave),calls


def binding_ref():return dict(path=str(BINDING),sha256=hashlib.sha256(BINDING.read_bytes()).hexdigest())


def dispatch(tmp_path, ref, value, mutation=None):
    item=dict(id='E2-R',binding=ref,limits=entry.COMPUTE,task_key=entry.TASK,job_id=entry.JOB,output_root=value['output_root'])
    req=write(tmp_path/'approval-request.json',dict(items=[item]))
    owner=dict(status='EXPLICIT_ITEMIZED_APPROVAL',approved_item_ids=['E2-R'],request=req)
    if mutation=='old_approval':owner['approved_item_ids']=['E2-FIDELITY-5F']
    owner_ref=write(tmp_path/'owner.json',owner)
    admission=dict(status='APPROVED_ADMINISTRATIVE_RECOVERY',queue_root=value['queue_root'],scope=dict(
        allowed_next_task_keys=[entry.TASK],basis=dict(e2_r_itemized_owner=dict(digest=owner_ref['sha256']),
        e2_r_itemized_request=dict(digest=req['sha256']))))
    if mutation=='wrong_queue':admission['queue_root']='generated-other-queue'
    if mutation=='no_admission':admission['scope']['allowed_next_task_keys']=[]
    if mutation=='wrong_basis':admission['scope']['basis']['e2_r_itemized_owner']['digest']='0'*64
    admission_ref=write(tmp_path/'admission.json',admission)
    now=datetime.now(timezone.utc)
    d=dict(schema='EPI_NEXT_E2_R_DISPATCH_V1',status='READY_FOR_CHIEF_DISPATCH',binding=ref,
        task_key=entry.TASK,job_id=entry.JOB,compute=copy.deepcopy(entry.COMPUTE),
        supervision_spec=value['supervision_spec'],owner_receipt=owner_ref,new_admission_decision=admission_ref,
        execution_window=dict(status='CHIEF_SLOT_GRANTED',slot_id='generated-same-slot',
            not_before_utc=(now-timedelta(seconds=1)).isoformat(),not_after_utc=(now+timedelta(minutes=5)).isoformat()))
    if mutation=='budget':d['compute']['forward']=19
    if mutation=='old_task':d['task_key']='consumed-old-task'
    if mutation=='no_slot':d['execution_window']['status']='PENDING'
    return write(tmp_path/'dispatch.json',d)


def test_metadata_check_has_no_execution_or_queue():
    loader,calls=fake_supervisor();out=entry.run(binding_ref(),supervisor_loader=loader)
    assert out['model_calls']==out['queue_observations']==0 and not out['arrays_weights_read'] and not calls


def test_parent_calls_shared_supervisor_once_only_after_exact_dispatch(tmp_path):
    ref=binding_ref();value=entry.bound(ref);d=dispatch(tmp_path,ref,value);loader,calls=fake_supervisor()
    @contextmanager
    def adapter(*_):yield SimpleNamespace(errors=[]),None
    out=entry.run(ref,d,execute=True,supervisor_loader=loader,supervision_adapter=adapter)
    assert out['status']=='SUCCESS' and len(calls)==1
    args,kwargs=calls[0];assert args[0].max_forward==18 and args[0].max_backward==0
    assert '--child' in args[1] and kwargs['recovery_decision_sha']==entry.bound(d)['new_admission_decision']['sha256']


@pytest.mark.parametrize('mutation',['old_approval','wrong_queue','no_admission','wrong_basis','budget','old_task','no_slot'])
def test_dispatch_drift_rejected_without_shared_slot(tmp_path,mutation):
    ref=binding_ref();value=entry.bound(ref);d=dispatch(tmp_path,ref,value,mutation);loader,calls=fake_supervisor()
    with pytest.raises(ValueError):entry.run(ref,d,execute=True,supervisor_loader=loader)
    assert not calls


@pytest.mark.parametrize('known',[True,False])
def test_failure_completion_retains_known_counts_and_unknown_stays_null(tmp_path,monkeypatch,known):
    import epilocate_next.e2_readout_launch as launch
    completions=[]
    guard=SimpleNamespace(check=lambda:None,complete=lambda *a,**k:completions.append(k))
    modules=dict(wave1_supervisor=SimpleNamespace(ChildGuard=SimpleNamespace(from_environment=lambda:guard)),
        coordinator_writer=SimpleNamespace(write_new=lambda *_:None))
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(set_num_threads=lambda _:None,set_num_interop_threads=lambda _:None,
        get_num_threads=lambda:1,get_num_interop_threads=lambda:1))
    def failed(*a,**k):
        if known:raise ReadoutFailure(ValueError('generated'),SimpleNamespace(forward_count=2,backward_count=0),True)
        raise ValueError('generated unknown')
    monkeypatch.setattr(launch,'run_existing_readout',failed)
    with pytest.raises(RuntimeError if known else ValueError):
        entry.admitted_child(dict(sha256='1'*64),{},modules,tmp_path,SimpleNamespace(reporting=False))
    assert completions[0]['actual_forward']==(2 if known else None)
    assert completions[0]['actual_backward']==(0 if known else None)


@pytest.mark.parametrize('mutation',['task','closure','source','test_source'])
def test_binding_drift_rejected_without_model_or_queue(tmp_path,mutation):
    value=entry.bound(binding_ref())
    if mutation=='task':value['existing_e2_binding']['application_request']['task']['target_class']=0
    if mutation=='closure':value['source_sha256'].pop(str(ROOT/'worker/inference.py'))
    if mutation=='source':value['source_sha256'][str(ROOT/'worker/inference.py')]='0'*64
    if mutation=='test_source':value['generated_validation']['source_sha256'][str(ROOT/'qa/test_e2_readout_lifecycle.py')]='0'*64
    ref=write(tmp_path/'changed-binding.json',value);loader,calls=fake_supervisor()
    with pytest.raises(ValueError):entry.run(ref,supervisor_loader=loader)
    assert not calls
