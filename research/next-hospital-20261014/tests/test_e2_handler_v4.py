"""Targeted actual-core/generated tests; no clinical weights/data loaders."""
from dataclasses import replace
import importlib.util
from pathlib import Path
import numpy as np
import pytest
import torch
from epi_next.hspi_core_v3 import Budget,source_sha
from epi_next.e2_handler_v4 import run_prepared_e2,digest,selected_fidelity,import_stage1
from epi_next.e2_request_v4 import validate_request

spec=importlib.util.spec_from_file_location('generated_e2_v4',Path(__file__).parents[1]/'scripts/run_e2_handler_synthetic_v4.py')
generated=importlib.util.module_from_spec(spec);spec.loader.exec_module(generated)
torch.set_num_threads(1)


@pytest.fixture(scope='module')
def known():
    p,i,c,g=generated.fixture();generated.independent_witness(c)
    model=generated.Peaks();trace=[]
    result=run_prepared_e2(p,model,g,c,identity=i,trace_sink=trace.append)
    payload=generated.reuse_payload(p,i,c,result['stages'][0])
    return p,i,c,g,result,payload,trace


def test_autonomous_chain_and_distinct_layers(known):
    p,i,c,g,r,payload,trace=known
    assert r['execution_status']=='SUCCESS' and r['full_plan_completed']
    assert [s['cell'] for s in r['stages']]==[0,48,0,99,0,168]
    assert r['new_cost']['forward']==1086 and r['new_cost']['backward']==1080
    assert len(trace)==1080 and 'mask' not in trace[0] and 'top1cell' in trace[0]
    assert len(r['optimized_input_masks'])==6
    for s in r['stages']:assert s['baseline_logits']==[[1.,0.]]
    for layer in r['optimized_input_masks']:
        assert np.array_equal(layer['model_values'],layer['native_values'])
    assert np.array_equal(r['model_space']['reliable'],r['native_space']['reliable'])
    assert np.array_equal(r['psmi_whole_patch_support']['model_values'],r['model_space']['reliable'])
    assert [v['votes'] for v in r['psmi']['votes']]==[2,2]
    assert len(r['candidates'])==2 and all(v['native_pixels']==144 for v in r['candidates'])
    assert all(np.array_equal(v['model_mask'],v['native_mask']) for v in r['candidates'])
    assert r['score_semantics'].endswith('NOT lesion probability')


def test_terminal_reuse_not_optimizer_resume_and_single_meter(known):
    p,i,c,g,fresh,payload,trace=known
    model=generated.Peaks();meter=Budget();meter.forward=11;meter.backward=9;meter.optimizer_steps=9
    stages=[]
    result=run_prepared_e2(p,model,g,c,identity={**i,'reused_stage1_sha256':digest(payload)},
        reused_stage1=payload,budget=meter,stage_sink=stages.append)
    assert result['new_cost']['forward']==model.calls==905
    assert result['new_cost']['backward']==result['new_cost']['optimizer_steps']==900
    assert result['cumulative_meter_cost']['forward']==916
    assert len(stages)==6 and stages[0]['origin']=='REUSED_VERIFIED_P1_STAGE1'
    assert np.array_equal(result['model_space']['reliable'],fresh['model_space']['reliable'])


@pytest.mark.parametrize('change',['sha','input','loss','mask'])
def test_incompatible_reuse_pre_call_refusal(known,change):
    p,i,c,g,r,payload,trace=known
    import copy
    payload=copy.deepcopy(payload);i={**i,'reused_stage1_sha256':digest(payload)}
    if change=='sha':i['reused_stage1_sha256']='0'*64
    elif change=='input':payload['input_binding']['input_sha256']='0'*64
    elif change=='loss':c=replace(c,lam=.1)
    else:payload['best']['mask'][0][0][0][0]=0.
    if change!='sha':i['reused_stage1_sha256']=digest(payload)
    model=generated.Peaks()
    with pytest.raises(ValueError):run_prepared_e2(p,model,g,c,identity=i,reused_stage1=payload)
    assert model.calls==0


def test_empty_base_all_other_scales_diagnosed(known):
    p,i,c,g,r,payload,trace=known
    payload={**payload,'best':None,'feasible_count':0}
    result=run_prepared_e2(p,generated.Peaks(),g,c,identity={**i,'reused_stage1_sha256':digest(payload)},reused_stage1=payload)
    assert result['execution_status']=='NO_RELIABLE_RESPONSE'
    assert result['new_cost']['forward']==724 and result['new_cost']['optimizer_steps']==720
    assert len(result['skipped_branches'])==1 and not result['unrun_branches']
    assert result['termination_policy_completed'] and not result['full_plan_completed']
    assert result['votes_finalized'] and result['psmi']['status']=='NO_MULTISCALE_SUPPORT'


def test_autonomous_distributed_empty_and_native_transform(known):
    p,i,c,g,r,payload,trace=known
    class Distributed(torch.nn.Module):
        def forward(self,x):
            score=x.mean((1,2,3));return torch.stack([score,score*0],1)
    image=np.ones_like(p.image)
    import hashlib
    negative=run_prepared_e2(replace(p,image=image,input_sha256=hashlib.sha256(image.tobytes()).hexdigest()),
        Distributed(),g,c,identity=i)
    assert negative['execution_status']=='NO_RELIABLE_RESPONSE'
    assert all(s['status']=='NO_FEASIBLE_MASK' for s in negative['stages'])
    assert negative['new_cost']['forward']==543 and negative['new_cost']['backward']==540
    assert len(negative['skipped_branches'])==3 and not negative['native_space']['reliable'].any()
    forward=np.diag([1.,2.,2.,1.]);forward[0,3]=123
    g={**g,'native_shape_rc':[167,167],'native_slice_index_zero_based':123,
       'model_to_native_zyx':forward.tolist(),'native_to_model_zyx':np.linalg.inv(forward).tolist()}
    model=generated.Peaks()
    native=run_prepared_e2(p,model,g,replace(c,grids=(7,),stages=1,epsilon=0),
        identity={**i,'reused_stage1_sha256':digest(payload)},reused_stage1=payload)
    assert model.calls==0 and native['native_space']['native_slice_index']==123
    expected=np.zeros((167,167),bool);expected[:23,:23]=True
    assert np.array_equal(native['native_space']['reliable'],expected)


def test_partial_and_inflight_deadline(known):
    p,i,c,g,r,payload,trace=known
    out=run_prepared_e2(p,generated.Peaks(),g,c,identity=i,budget=Budget(max_forward=37))
    assert out['execution_status']=='PARTIAL_BUDGET' and out['new_cost']['forward']==37
    assert out['psmi']['status']=='PARTIAL_VOTES' and not out['votes_finalized']
    assert len(out['unrun_branches'])==5
    clock=[0.]
    class Slow(generated.Peaks):
        def forward(self,x):clock[0]+=5;return super().forward(x)
    out=run_prepared_e2(p,Slow(),g,c,identity=i,budget=Budget(clock=lambda:clock[0]),branch_seconds=8)
    assert out['execution_status']=='PARTIAL_BUDGET'
    assert out['new_cost']['forward']==2 and out['new_cost']['backward']==0
    assert out['new_cost']['stop_reason']=='BRANCH_TIMEOUT'
    assert out['stages'][0]['observed_iterations']==1


def test_preflight_dimensions_scope_geometry(known):
    p,i,c,g,r,payload,trace=known
    model=generated.Peaks()
    with pytest.raises(ValueError):run_prepared_e2(p,model,g,c,identity={**i,'classifier_kind':'3D_CTFM'})
    with pytest.raises(ValueError):run_prepared_e2(replace(p,scope='APPROVED_PREPROCESSED',split='train',approval_receipt_sha256='a'*64),model,g,c,identity=i)
    bad={**g,'native_to_model_zyx':np.zeros((4,4)).tolist()}
    with pytest.raises(ValueError):run_prepared_e2(p,model,bad,c,identity=i)
    assert model.calls==0


def test_failure_and_freeze_mode_flags(known):
    p,i,c,g,r,payload,trace=known
    model=generated.Peaks();model.train();initial=model.weight.detach().clone()
    out=run_prepared_e2(p,model,g,replace(c,steps=3),identity=i)
    assert model.training and model.weight.requires_grad and model.weight.grad is None
    assert torch.equal(initial,model.weight.detach())
    class Bad(torch.nn.Module):
        def forward(self,x):return x.mean((2,3)).repeat(1,3)
    out=run_prepared_e2(p,Bad(),g,c,identity=i)
    assert out['execution_status']=='FAILED' and out['new_cost']['forward']==1
    assert out['new_cost']['backward']==0


def test_fidelity_fixed_objects_and_target(known):
    p,i,c,g,r,payload,trace=known
    i={**i,'reused_stage1_sha256':digest(payload)};model=generated.Peaks()
    out=selected_fidelity(p,model,c,payload,identity=i)
    assert out['status']=='SUCCESS' and out['cost']['forward']==model.calls==5
    assert out['cost']['backward']==0 and out['cost']['optimizer_steps']==0
    assert list(out['responses'])==['original','full_mask_keep','peak_patch_keep','full_mask_remove','peak_patch_remove']
    assert {v['fixed_target'] for v in out['responses'].values()}=={0}
    assert out['responses']['peak_patch_remove']['logits']==[[1.,0.]]
    partial=selected_fidelity(p,generated.Peaks(),c,payload,identity=i,budget=Budget(max_forward=2))
    assert partial['status']=='PARTIAL_BUDGET' and len(partial['responses'])==2
    assert source_sha()=='10d71a6390094b578d6b41d593b03a850841451adc61cb97ae68c4f198bebede'


def test_bound_offline_requests():
    root=Path(__file__).parents[1]/'configs'
    q=validate_request(root/'e2-q-v4.json')
    assert q['cost']['forward']==130013 and q['cost']['backward']==130000
    f=validate_request(root/'e2-selected-fidelity-v4.json')
    assert f['cost']['forward']==5 and f['medical_forward']==0
