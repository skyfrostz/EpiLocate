"""P1 ENGINE tests: generated scalar tensors/analytic classifiers, no patients."""
from dataclasses import replace
import copy
import hashlib
import json
import time
from pathlib import Path
import torch
import pytest
from epi_next.hspi_core_v3 import HSPIConfig,adopt_wave1_checkpoint,BudgetStopped
from epi_next.p1_runner_v4 import (continue_case,SegmentBudget,verify_dispatch,CAPS,P1_SHA,CONSOLIDATED_SHA)
from epi_next.p1_storage_v4 import BoundedStore,TraceStream
from epi_next.spi_recovery_v2 import ComputeMeter,run_spi
from epi_next.runner_ledger_v3 import CounterLedger

torch.set_num_threads(1)
COST={'generated_forward':0,'generated_backward':0,'real_forward':0}

class Model(torch.nn.Module):
    def forward(self,x):
        COST['generated_forward']+=1
        y=x.square().mean((1,2,3))*.05
        return torch.stack([y*.2,y],1)


def generated_checkpoint(steps=2,final=8):
    x=torch.linspace(.1,.9,144).reshape(1,1,12,12);v=torch.ones(12,12,dtype=torch.bool);v[:2]=False
    rows=[];cps={};model=Model()
    old=run_spi(model,x,v,weight=1,steps=steps,gradient_steps=(),checkpoints=(steps,),sink=rows.append,
                checkpoint_sink=lambda n,cp:cps.update({n:cp}))
    cfg=HSPIConfig(mode='E2-CT',image_size=(12,12),grids=(7,),reference_grid=7,epsilon=0,
                   stages=1,steps=final,masking_policy='preserve_exterior',adapter_policy='generated W1')
    prov={k:'a'*64 for k in ('checkpoint_sha256','source_sha256','input_sha256','model_sha256','preprocessing_sha256','execution_lock_sha256')}
    cp=adopt_wave1_checkpoint(cps[steps],rows,x,v,cfg,identity='generated-v4',provenance=prov,expected_baseline=old['baseline_logits'])
    return model,x,v,cfg,cp


class Guard:
    def __init__(self,clock=time.monotonic):self.begin=0;self.end=0;self.clock=clock;self.active=False
    def begin_case(self,key):
        assert not self.active;self.active=True;self.begin+=1;self.case_started=self.clock()
    def end_case(self):assert self.active;self.active=False;self.end+=1


def test_three_cases_nine_restores_share_exact_counter_trace_adam_and_time(tmp_path):
    store=BoundedStore(tmp_path/'output');ledger=CounterLedger(store.root/'algorithm-counters.json',experiment_id='generated',max_forwards=36,max_reverse=18,create=True)
    meter=ComputeMeter(max_forwards=36,max_reverse=18,ledger=ledger)
    for index in (1,2,3):
        model,x,v,cfg,cp=generated_checkpoint();guard=Guard()
        result,times,binding=continue_case(model,x,v,cfg,cp,meter,store,index,'generated-v4',milestones=(4,6,8),guard=guard)
        assert guard.begin==guard.end==1
        assert times['restores']==3 and len(times['segments'])==3
        assert all(s['case_cumulative_seconds']>=s['elapsed_seconds'] for s in times['segments'])
        assert result['completed_steps']==8 and result['status']=='NO_FEASIBLE_MASK'
        assert result['checkpoint']['history']==[] and binding['rows']==6
        actual=[json.loads(line) for line in store.path(f'case-{index}-new-epochs.jsonl').read_text().splitlines()]
        reference=[]
        full=run_spi(Model(),x,v,weight=1,steps=8,gradient_steps=(),checkpoints=(),sink=reference.append)
        for got,expected in zip(actual,reference[2:]):
            assert got['epoch']==expected['epoch']+1 and got['ls']==expected['similarity']
            assert got['lm']==expected['sparsity'] and got['logits']==[expected['logits']]
            assert got['mask'][0][0]==expected['mask_before']
        assert torch.equal(result['checkpoint']['mask'][0,0],torch.tensor(full['final_mask']))
        assert meter.forwards==index*12 and meter.backward==meter.optimizer_steps==index*6
        assert len(list(store.root.glob(f'case-{index}-restore-*-audit.json')))==3
    assert meter.forwards==36 #18 audit forwards +18 optimization forwards.
    assert ledger.read()['pending'] is None and ledger.read()['autograd_grad_calls']==0
    reopened=CounterLedger(ledger.path,experiment_id='generated',max_forwards=36,max_reverse=18)
    assert reopened.read()['forward_attempts']==36
    print('P1_GENERATED_ENGINE_METER='+json.dumps(meter.receipt()))


def test_atomic_replacement_charges_old_plus_temporary_bytes_and_reopen(tmp_path):
    store=BoundedStore(tmp_path,cap=150000,reserve=65536)
    store.write('blob',b'x'*50000)
    with pytest.raises(BudgetStopped):store.write('blob',b'y'*50000,replace=True)
    assert store.path('blob').read_bytes()==b'x'*50000 and not store.path('blob.pending').exists()
    other=BoundedStore(tmp_path,cap=150000,reserve=65536)
    assert other.size()==50000
    other.write('blob',b'y'*10000,replace=True)
    assert other.size()==10000
    supervision=tmp_path/'external';supervision.mkdir();(supervision/'history').write_bytes(b'x'*10000)
    # Distinct roots used by production, never double-count overlapping roots.
    root=tmp_path/'own';both=BoundedStore(root,cap=150000,reserve=65536,extra_roots=(supervision,))
    assert both.size()==10000


def test_safe_checkpoint_hash_tamper_and_trace_pending_replay(tmp_path):
    _,_,_,_,cp=generated_checkpoint()
    store=BoundedStore(tmp_path);digest=store.checkpoint('state.pt',{'core':cp},replace=True)
    restored=store.load_checkpoint('state.pt',digest)
    assert torch.equal(restored['core']['mask'],cp['mask'])
    store.path('state.pt').write_bytes(b'bad')
    with pytest.raises(ValueError,match='DRIFT'):store.load_checkpoint('state.pt',digest)
    trace=TraceStream(store,'trace.jsonl');row={'epoch':1001,'ls':.2}
    trace.append(row);trace.append(dict(row));assert trace.rows==1
    other=TraceStream(store,'trace.jsonl');assert other.binding()==trace.binding()
    with pytest.raises(ValueError,match='DIVERGED'):other.append({'epoch':1001,'ls':.3})
    with pytest.raises(ValueError,match='SEQUENCE'):other.append({'epoch':1003,'ls':.2})
    with store.path('trace.jsonl').open('ab') as f:f.write(b'{')
    with pytest.raises(ValueError,match='PARTIAL_TRACE'):TraceStream(store,'trace.jsonl')


def test_case_deadline_and_global_time_never_reset_by_new_segment(tmp_path):
    clock=[0.];meter=ComputeMeter(max_seconds=3600,clock=lambda:clock[0]);store=BoundedStore(tmp_path)
    a=SegmentBudget(meter,store,0.,0.,20,clock=lambda:clock[0]);clock[0]=1000
    assert a.permits(1,1)
    b=SegmentBudget(meter,store,0.,1000.,20,clock=lambda:clock[0]);clock[0]=1200
    assert not b.permits(1,1) and b.reason=='CASE_CUMULATIVE_DEADLINE'
    clock[0]=3600
    c=SegmentBudget(meter,store,3500.,3500.,20,clock=lambda:clock[0])
    assert not c.permits(1,1) and c.reason=='TIME_LIMIT'
    assert meter.started==0


def test_forward_budget_partial_is_not_automatic_next_restore(tmp_path):
    model,x,v,cfg,cp=generated_checkpoint();store=BoundedStore(tmp_path)
    meter=ComputeMeter(max_forwards=3,max_reverse=6)
    r,t,_=continue_case(model,x,v,cfg,cp,meter,store,1,'generated-v4',milestones=(4,6,8))
    assert r['status']=='PARTIAL_BUDGET' and t['restores']==1
    assert meter.forwards==3 and meter.backward==1
    assert len(t['segments'])==1 and store.path('case-1-latest.pt').exists()


def test_inflight_ledger_refused_and_retained(tmp_path):
    model,x,v,cfg,cp=generated_checkpoint();store=BoundedStore(tmp_path)
    ledger=CounterLedger(store.root/'counts.json',experiment_id='fixture',max_forwards=20,max_reverse=6,create=True)
    ledger.begin('forward');ledger.entered('forward')
    meter=ComputeMeter(max_forwards=20,max_reverse=6,ledger=ledger)
    with pytest.raises(ValueError,match='UNKNOWN_INFLIGHT'):continue_case(model,x,v,cfg,cp,meter,store,1,'generated-v4',milestones=(4,6,8))
    assert ledger.read()['pending'] is not None and ledger.read()['forward_entered']==1


def test_unknown_slot_refuses_before_load_and_changed_science_refuses(tmp_path,monkeypatch):
    import epi_next.p1_runner_v4 as worker
    approval=tmp_path/'approval.json';approval.write_text('{}')
    digest=hashlib.sha256(approval.read_bytes()).hexdigest();monkeypatch.setattr(worker,'APPROVAL_SHA',digest)
    bindings={str(Path(worker.__file__).with_name(n).resolve()):worker.file_sha(Path(worker.__file__).with_name(n)) for n in worker.MODULES}
    ready={'caps':CAPS,'original_config_sha256':P1_SHA,'conditional_approval':{'path':str(approval),'sha256':digest},'local_source_bindings':bindings,'model_runtime_packages':{},'python_version':'test',
           'proposal':{'path':str(Path(__file__).parents[1]/'configs/hspi-v3-p1.json')}}
    with pytest.raises(ValueError,match='UNKNOWN'):verify_dispatch(ready,'b'*64,{'slot_status':'UNKNOWN'})
    with pytest.raises(ValueError,match='DISPATCH'):verify_dispatch(ready,'b'*64,{'slot_status':'RECOVERED_OWNER_CONFIRMED'})
    recovery=tmp_path/'owner.json';recovery.write_text(json.dumps({'owner_explicitly_confirmed':True,'administrative_recovery_only':True}))
    lock={'slot_status':'RECOVERED_OWNER_CONFIRMED','status':'LOCKED_FOR_P1_CPU_EXECUTION','real_model_execution_authorized':True,
       'readiness_sha256':'b'*64,'proposal_sha256':P1_SHA,'conditional_approval_sha256':digest,
       'original_consolidated_proposal_sha256':CONSOLIDATED_SHA,'max_network_forwards':27027,'max_reverse_calls':27000,
       'soft_timeout_seconds_total':3600,'per_case_seconds':1200,'local_source_bindings':bindings,'model_runtime_packages':{},'python_version':'test',
       'owner_recovery_confirmation':{'path':str(recovery),'sha256':hashlib.sha256(recovery.read_bytes()).hexdigest()}}
    verify_dispatch(ready,'b'*64,lock)
    lock['max_network_forwards']=27028
    with pytest.raises(ValueError,match='DISPATCH'):verify_dispatch(ready,'b'*64,lock)


def test_existing_childguard_three_cases_share_all_audits_and_updates(tmp_path,monkeypatch):
    from test_wave1_runner_seams_v3 import fixture_guard
    from epi_next.shared_runner_binding_v3 import reconcile_counts,finish_child
    guard,meter=fixture_guard(tmp_path,monkeypatch,max_forward=40,max_backward=20)
    store=BoundedStore(tmp_path/'output',extra_roots=(guard.directory,))
    measured=0
    try:
        for index in (1,2,3):
            model,x,v,cfg,cp=generated_checkpoint()
            before=COST['generated_forward']
            r,t,_=continue_case(model,x,v,cfg,cp,meter,store,index,'generated-v4',milestones=(4,6,8),guard=guard)
            measured+=COST['generated_forward']-before
            assert r['completed_steps']==8 and t['restores']==3
        with guard.ledger() as shared:assert len(shared['cases'])==3
        assert meter.forwards==measured==36 and meter.backward==18 and meter.optimizer_steps==18
        assert reconcile_counts(guard,meter.receipt(),measured)['reservations_equal']
        finish_child(guard,store.path('unused'),'NO_RELIABLE_RESPONSE',meter.receipt(),actual_forward=measured)
        completion=json.loads((guard.directory/'runner-complete.json').read_text())
        assert completion['actual_forward']==36 and completion['actual_backward']==18
        store.ensure(0,terminal=True)
        assert store.size()<store.cap
    finally:
        if not guard.done.is_set():guard.close()


def test_execute_unknown_stops_before_arrays_weights_or_guard(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import epi_next.p1_runner_v4 as worker
    ready=tmp_path/'ready.json';ready.write_text('{}')
    lock=tmp_path/'lock.json';lock.write_text(json.dumps({'slot_status':'UNKNOWN'}))
    args=SimpleNamespace(readiness=ready,readiness_sha=hashlib.sha256(ready.read_bytes()).hexdigest(),
                         execution_lock=lock,lock_sha=hashlib.sha256(lock.read_bytes()).hexdigest())
    monkeypatch.setattr(worker,'consume_inputs',lambda *a:pytest.fail('must not read generated or medical arrays'))
    monkeypatch.setattr(worker,'baseline_source',lambda *a:pytest.fail('must not load classifier'))
    monkeypatch.setattr(worker,'bind_child',lambda *a,**kw:pytest.fail('must not request slot'))
    with pytest.raises(ValueError,match='UNKNOWN'):worker.execute(args)


def test_full_mock_cli_loader_containment_native_results_and_completion(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from test_wave1_runner_seams_v3 import fixture_guard
    from epi_next.first_real_e1_e2 import DifferentiablePreparedModel
    import epi_next.p1_runner_v4 as worker
    guard,_=fixture_guard(tmp_path,monkeypatch,max_forward=40,max_backward=20)
    guard.spec=replace(guard.spec,timeout_seconds=3600,per_case_seconds=1200)
    source=Path(worker.__file__).read_bytes()
    fake=tmp_path/'project/research/next-hospital-20261014/epi_next/p1_runner_v4.py'
    fake.parent.mkdir(parents=True);fake.write_bytes(source);monkeypatch.setattr(worker,'__file__',str(fake))
    output=tmp_path/'project/.local/phase2/p1-approved-v4/run-1'
    spec={'normalization_mean':[.485,.456,.406],'normalization_std':[.229,.224,.225]}
    x=torch.linspace(.1,.9,144).reshape(1,1,12,12);v=torch.ones(12,12,dtype=torch.bool);v[:2]=False
    cfg=HSPIConfig(mode='E2-CT',image_size=(12,12),grids=(7,),reference_grid=7,epsilon=0,stages=1,steps=8,
                   masking_policy='preserve_exterior',adapter_policy='GENERATED_MOCK_CLI_ONLY')
    rows=[];cps={};prior=run_spi(DifferentiablePreparedModel(Model(),spec),x,v,weight=1,steps=2,
        gradient_steps=(),checkpoints=(2,),sink=rows.append,checkpoint_sink=lambda n,cp:cps.update({n:cp}))
    provenance={k:'a'*64 for k in ('checkpoint_sha256','source_sha256','input_sha256','model_sha256','preprocessing_sha256','execution_lock_sha256')}
    records=[{'case_index':i,'arrays':{'image':{'sha256':'a'*64}},'native_manifest_sha256':'a'*64,
              'source_sop_uid':f'GENERATED-SOP-{i}','native_slice_index_zero_based':0} for i in (1,2,3)]
    geometry={'native_shape_rc':[12,12],'native_slice_index_zero_based':0,'model_shape_yx':[12,12],
              'native_to_model_zyx':torch.eye(4).tolist(),'model_to_native_zyx':torch.eye(4).tolist()}
    prepared=SimpleNamespace(image=x[0,0].numpy(),valid_mask=v.numpy())
    inputs=[(r,prepared,geometry) for r in records];load_calls=[]
    ready={'execution_output':str(output),'dependency_root':'generated','dependency_sha256':'a'*64,
      'resource_revision':'generated','proposal':{'path':str(Path(__file__).parents[1]/'configs/hspi-v3-p1.json')},
      'prepared_delivery':{'path':'generated-delivery'},'baseline_config':{'path':'generated-config'},
      'integration_source':'generated-adapter','records':[{'case_index':r['case_index'],'prepared_record':r} for r in records]}
    ready_path=tmp_path/'mock-ready.json';ready_path.write_text(json.dumps(ready))
    lock_path=tmp_path/'mock-lock.json';lock_path.write_text('{}')
    args=SimpleNamespace(readiness=ready_path,readiness_sha=hashlib.sha256(ready_path.read_bytes()).hexdigest(),
                         execution_lock=lock_path,lock_sha=hashlib.sha256(lock_path.read_bytes()).hexdigest(),output=output)
    # Auth gate has its own strict negative/positive tests. Mock only downstream
    # loader invocation and reduced generated plan; never a medical dispatch.
    monkeypatch.setattr(worker,'verify_dispatch',lambda *a:None)
    monkeypatch.setattr(worker,'bind_child',lambda *a,**kw:(guard,{'fixture':'isolated'}))
    monkeypatch.setattr(worker,'config_from_proposal',lambda p:cfg)
    def consume(*a):
        load_calls.append('generated-inputs');return {'checkpoint_path':str(tmp_path/'GENERATED.pt')},None,spec,inputs
    monkeypatch.setattr(worker,'consume_inputs',consume)
    def load(path,digest):
        assert path.name=='GENERATED.pt' and digest==worker.CHECKPOINT_SHA
        load_calls.append('generated-classifier-loader-invoked');return Model()
    monkeypatch.setattr(worker,'baseline_source',lambda p:SimpleNamespace(load_verified_resnet18=load))
    def legacy(record,image,valid,config,identity,readiness):
        return adopt_wave1_checkpoint(cps[2],rows,image,valid,config,identity=identity,provenance=provenance,expected_baseline=prior['baseline_logits'])
    monkeypatch.setattr(worker,'load_legacy',legacy)
    original=worker.continue_case
    monkeypatch.setattr(worker,'continue_case',lambda *a,**kw:original(*a,milestones=(4,6,8),**kw))
    try:
        assert worker.execute(args)==0
        assert load_calls==['generated-inputs','generated-classifier-loader-invoked']
        delivered=json.loads((output/'run_delivery.json').read_text())
        assert delivered['status']=='NO_RELIABLE_RESPONSE' and len(delivered['records'])==3
        assert delivered['cost']['forward_attempts']==delivered['actual_classifier_forward_entered']==36
        assert delivered['cost']['loss_backward_calls']==18 and delivered['cost']['optimizer_steps']==18
        assert delivered['counter_comparison']['reservations_equal']
        assert len(list(output.glob('*-CPF-native.npz')))==3
        final=json.loads((output/'output-final-size.json').read_text())
        assert final['bytes_measured_after_child_shutdown']<final['cap']
        assert guard.done.is_set()
    finally:
        if not guard.done.is_set():guard.close()
