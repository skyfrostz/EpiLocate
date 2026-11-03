"""Isolated fixed-byte ChildGuard fixtures, no device slot or real checkpoint."""

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[3]
from dataclasses import asdict
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time
from unittest.mock import patch
import numpy as np
import pytest
import torch
from epi_next.shared_runner_binding_v3 import load_supervisor_bundle,finish_child,reconcile_counts,verify_model_runtime
from epi_next.runner_ledger_v3 import CounterLedger
from epi_next.spi_recovery_v2 import ComputeMeter,StopBudget,run_spi
from epi_next.e1_fill_runner_v3 import run_fill_case
from epi_next.e1_fill_v2 import gaussian_replacement
from epi_next.first_real_e1_e2 import DifferentiablePreparedModel
from epi_next.localization import occlusion_2d

torch.set_num_threads(1)
COST=dict(synthetic_forward_entered=0,loss_backward=0,autograd_grad=0,real_forward=0)
SOURCE=Path(os.environ.get('EPI_NEXT_SUPERVISOR_TEST_SOURCE',
    str(_PUBLIC_ROOT / 'research/next-hospital-20261014/.local/phase2/wave1-supervisor-2ba7068-v2/dependencies/EPI-NEXT-shared-supervisor-v2')))
MODULES=('wave1_supervisor','execution_lock','coordinator_writer','artifacts','hospital_runtime','hospital_contract','contracts','geometry')


@pytest.fixture(scope='module',autouse=True)
def all_cost():
    before=torch.Tensor.backward;grad=torch.autograd.grad
    def backward(value,*a,**kw):COST['loss_backward']+=1;return before(value,*a,**kw)
    def autograd(*a,**kw):COST['autograd_grad']+=1;return grad(*a,**kw)
    with patch.object(torch.Tensor,'backward',new=backward),patch('torch.autograd.grad',new=autograd):yield
    print('SEAM_TEST_COST='+json.dumps(COST))


def fixture_bundle(tmp_path):
    # Source bytes are frozen before import; this is an isolated test snapshot,
    # not the coordinator's final execution dependency receipt.
    root=tmp_path/'bundle';root.mkdir();entries=[]
    for name in MODULES:
        src=SOURCE/(name+'.py');raw=src.read_bytes();(root/src.name).write_bytes(raw)
        entries.append(dict(name=src.name,repo=str(SOURCE),relative_path=src.name,sha256=hashlib.sha256(raw).hexdigest()))
    manifest=dict(entries=entries,packages={'numpy':importlib.metadata.version('numpy')})
    raw=(json.dumps(manifest,sort_keys=True)+'\n').encode();(root/'dependency_lock.json').write_bytes(raw)
    (root/'receipt.json').write_text(json.dumps(dict(run_id='bundle',artifact_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()})))
    digest=hashlib.sha256(raw).hexdigest();module=load_supervisor_bundle(root,digest)
    print('SEAM_SHARED_SOURCE_SHA='+json.dumps({e['name']:e['sha256'] for e in entries}))
    return module,root,digest


def fixture_guard(tmp_path,monkeypatch,max_forward=20,max_backward=20):
    module,bundle,digest=fixture_bundle(tmp_path)
    directory=tmp_path/'job';directory.mkdir()
    spec=module.SupervisionSpec(job_id='isolated-job',task_key='synthetic-only',owner='LOCALIZATION',device='cpu',
        max_forward=max_forward,max_backward=max_backward,timeout_seconds=120)
    (directory/'spec.json').write_text(json.dumps(asdict(spec)))
    (directory/'counters.json').write_text(json.dumps(dict(job_id=spec.job_id,forward=0,backward=0,sequence=0,cases={})))
    (directory/'ADMITTED').write_text('isolated fixture: no parent or real slot')
    monkeypatch.setenv('EPI_NEXT_SUPERVISOR_DIR',str(directory));monkeypatch.setenv('EPI_NEXT_JOB_STARTED_MONOTONIC',str(time.monotonic()))
    monkeypatch.setenv('EPI_NEXT_DEPENDENCY_ROOT',str(bundle));monkeypatch.setenv('EPI_NEXT_DEPENDENCY_SHA',digest)
    guard=module.ChildGuard.from_environment()
    ledger=CounterLedger(tmp_path/'algorithm.json',experiment_id=spec.job_id,max_forwards=max_forward,max_reverse=max_backward,create=True)
    meter=ComputeMeter(guard=guard,ledger=ledger,stop_file=directory/'STOP',max_forwards=max_forward,max_reverse=max_backward,max_seconds=120)
    return guard,meter


class Classifier(torch.nn.Module):
    def forward(self,x):
        COST['synthetic_forward_entered']+=1
        y=x.square().mean((1,2,3))*.05
        return torch.stack((y*.2,y),1)


def test_e1_same_response_as_frozen_tiles_only_fill_changes(tmp_path,monkeypatch):
    guard,meter=fixture_guard(tmp_path,monkeypatch)
    spec=dict(normalization_mean=[.485,.456,.406],normalization_std=[.229,.224,.225])
    model=DifferentiablePreparedModel(Classifier(),spec).eval()
    image=np.linspace(.1,.9,32*32,dtype=np.float32).reshape(32,32);valid=np.ones_like(image,dtype=bool)
    try:
        result=run_fill_case(model,image,valid,meter)
        def reference_predict(value):
            with torch.inference_mode():return model(torch.from_numpy(value.copy())[None,None])[0].numpy().astype(np.float64)
        reference=occlusion_2d(reference_predict,image,valid,1,fill=gaussian_replacement(image))
        assert result['records']==reference['records'] and result['status']==reference['status']
        assert meter.forwards==meter.forward_entered==9 and result['model_calls']==7 and result['adapter_attempts']==2
        counts=reconcile_counts(guard,meter.receipt(),9)
        assert counts['reservations_equal'] and counts['shared_reserved_forward']==9
        finish_child(guard,tmp_path/'unused.json','NO_RELIABLE_RESPONSE',meter.receipt(),actual_forward=9)
        complete=json.loads((guard.directory/'runner-complete.json').read_text())
        assert complete['status']=='NO_RELIABLE_RESPONSE' and complete['actual_forward']==9 and complete['actual_backward']==0
    finally:
        if not guard.done.is_set():guard.close()


def test_e2_every_reverse_registered_stop_preserves_partial_mask_optimizer(tmp_path,monkeypatch):
    guard,meter=fixture_guard(tmp_path,monkeypatch);events=[];snapshots={}
    image=torch.linspace(.1,.9,144).reshape(1,1,12,12);valid=torch.ones((12,12),dtype=bool)
    def sink(event):
        events.append(event);(guard.directory/'STOP').write_text('requested after first complete step')
    try:
        result=run_spi(Classifier(),image,valid,weight=.1,steps=3,meter=meter,gradient_steps=(1,),sink=sink,
            checkpoints=(),checkpoint_sink=lambda step,state:snapshots.update({step:state}))
        assert result['status']=='PARTIAL_BUDGET' and result['reason']=='STOP_REQUESTED'
        assert meter.forwards==2 and meter.backward==1 and meter.autograd==2 and meter.optimizer_steps==1
        assert meter.reverse_entered==3 and len(result['final_mask'])==7 and result['last_logits']
        assert snapshots['partial']['step']==1 and snapshots['partial']['optimizer']['state']
        assert 'mask_before_projection' in events[0] and 'mask_after_projection' in events[0]
        assert 'combined_gradient' in events[0] and events[0]['optimizer_param_is_forward_leaf']
        assert reconcile_counts(guard,meter.receipt(),2)['reservations_equal']
        finish_child(guard,tmp_path/'unused.json','PARTIAL_BUDGET',meter.receipt(),actual_forward=2,reason=result['reason'])
        complete=json.loads((guard.directory/'runner-complete.json').read_text())
        assert complete['status']=='PARTIAL_BUDGET' and complete['actual_backward']==3
        module=__import__(guard.__class__.__module__,fromlist=['validated_completion'])
        telemetry=json.loads((guard.directory/'telemetry.json').read_text())
        assert module.validated_completion(guard.directory,guard.spec,telemetry,os.getpid(),guard.started,time.monotonic())==complete
        with pytest.raises(RuntimeError,match='JOB_ALREADY_COMPLETED_NO_NEW_WORK'):guard.before_forward()
        assert reconcile_counts(guard,meter.receipt(),2)['shared_reserved_forward']==2
    finally:
        if not guard.done.is_set():guard.close()


def test_stop_after_reservation_does_not_enter_or_reset_counts(tmp_path,monkeypatch):
    guard,meter=fixture_guard(tmp_path,monkeypatch,max_forward=1)
    original=guard.before_forward
    def reserve_then_stop():original();(guard.directory/'STOP').write_text('stop during admission')
    monkeypatch.setattr(guard,'before_forward',reserve_then_stop)
    try:
        with pytest.raises(StopBudget,match='STOP_REQUESTED'):meter.forward(Classifier(),torch.ones((1,1,12,12)))
        assert meter.forwards==1 and meter.forward_entered==meter.forward_completed==0
        reopened=CounterLedger(meter.ledger.path,experiment_id=guard.spec.job_id,max_forwards=1,max_reverse=20)
        assert reopened.read()['forward_attempts']==1 and reopened.read()['pending'] is None
        comparison=reconcile_counts(guard,meter.receipt(),0);assert comparison['shared_reserved_forward']==1
        finish_child(guard,tmp_path/'unused.json','PARTIAL_BUDGET',meter.receipt(),actual_forward=0)
    finally:
        if not guard.done.is_set():guard.close()


def test_ledger_rejects_unknown_inflight_and_budget_survives_reopen(tmp_path):
    path=tmp_path/'global.json';ledger=CounterLedger(path,experiment_id='synthetic',max_forwards=1,max_reverse=0,create=True)
    ledger.begin('forward');ledger.entered('forward')
    assert ledger.read()['forward_entered']==1
    other=CounterLedger(path,experiment_id='synthetic',max_forwards=1,max_reverse=0)
    with pytest.raises(RuntimeError,match='UNKNOWN_INFLIGHT'):other.begin('forward')
    ledger.end('forward',False,True)
    with pytest.raises(RuntimeError,match='FORWARD_LIMIT'):other.begin('forward')


def test_shared_dependency_drift_rejected_before_child_guard(tmp_path):
    _,bundle,digest=fixture_bundle(tmp_path)
    (bundle/'geometry.py').write_text('changed')
    with pytest.raises(ValueError,match='dependency bytes mismatch'):load_supervisor_bundle(bundle,digest)


def test_model_runtime_is_pinned_separately_from_shared_numpy():
    import platform
    lock=dict(python_version=platform.python_version(),model_runtime_packages={n:importlib.metadata.version(n) for n in ('torch','torchvision','numpy')})
    verify_model_runtime(lock)
    lock['model_runtime_packages']['torch']='incorrect'
    with pytest.raises(ValueError,match='model runtime version mismatch'):verify_model_runtime(lock)


def test_e1_setup_failure_writes_completion_before_any_model_read(tmp_path,monkeypatch):
    import epi_next.e1_fill_runner_v3 as worker
    guard,meter=fixture_guard(tmp_path,monkeypatch)
    # Main's containment is real; use a fresh private fixture folder, no inputs.
    root=Path(worker.__file__).resolve().parents[3]/'.local'/'phase2'
    fixture_root=root/('seam-'+hashlib.sha256(str(tmp_path).encode()).hexdigest()[:16])
    fixture_root.mkdir(parents=True,exist_ok=False)
    worker_file=fixture_root/'research'/'next-hospital-20261014'/'epi_next'/'e1_fill_runner_v3.py'
    worker_file.parent.mkdir(parents=True);worker_file.write_text('isolated containment fixture')
    monkeypatch.setattr(worker,'__file__',str(worker_file))
    allowed=fixture_root/'.local'/'phase2';output=allowed/'failed-setup'
    lock=dict(status='LOCKED_FOR_E1_FILL_CPU_EXECUTION',real_model_execution_authorized=True,
        proposal_sha256=worker.PROPOSAL_SHA,max_network_forwards=792,max_reverse_calls=0,soft_timeout_seconds_total=120)
    monkeypatch.setattr(worker,'locked_json',lambda p,s:lock if str(p)=='lock' else dict(prepared_delivery_sha256='unused'))
    monkeypatch.setattr(worker,'bind_child',lambda *a,**kw:(guard,{}))
    monkeypatch.setattr(worker,'consume_inputs',lambda *a:(_ for _ in ()).throw(ValueError('synthetic prepared refusal')))
    monkeypatch.setattr(worker,'baseline_source',lambda *a:pytest.fail('must not load model after input refusal'))
    arguments=['worker','--execution-lock','lock','--lock-sha','synthetic','--proposal','proposal','--prepared-delivery','missing',
        '--baseline-config','config','--baseline-run','baseline','--integration-source','unused','--output',str(output),
        '--resource-revision','revision','--dependency-root','bundle','--dependency-sha','synthetic']
    monkeypatch.setattr('sys.argv',arguments)
    try:
        assert worker.main()==2
        delivery=json.loads((output/'run_delivery.json').read_text())
        assert delivery['status']=='FAILED' and delivery['actual_classifier_forward_entered']==0
        completion=json.loads((guard.directory/'runner-complete.json').read_text())
        assert completion['status']=='FAILED' and completion['actual_forward']==completion['actual_backward']==0
    finally:
        if not guard.done.is_set():guard.close()
