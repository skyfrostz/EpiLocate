"""Generated loader boundaries only. Never opens CT, arrays or model weights."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from backend_v2.tests.test_phase1 import ctx
from backend_v2.tests.test_next_application import request_for, DATA, H
from epilocate_next.e2_launch import ExistingE2Binding,build_existing_e2_runner


def reference(path,value):
    raw=json.dumps(value).encode();path.write_bytes(raw)
    return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())


def test_existing_loaders_are_lazy_bound_and_delegate_without_medical_execution(ctx,tmp_path):
    f,_,ids=ctx;req=request_for(f,ids);req['execution_mode']='LIVE'
    req['budget'].update(forward=0,backward=0,updates=0)
    seen=[]
    guard=SimpleNamespace(check=lambda:seen.append('guard'))
    prepared=SimpleNamespace(image=SimpleNamespace(shape=(32,32)),scope='APPROVED_PREPROCESSED',preprocess_id=req['model']['preprocessing_version'],task_definition_id=req['task']['definition_id'],validate=lambda:None)
    geometry=dict(native_shape_rc=[32,32],native_slice_index_zero_based=0)
    record=dict(case_index=1,source_ct_sha256=H,geometry=dict(sha256=req['input']['geometry_ledger_sha256']))
    delivery=dict(checkpoint_path='NEVER_OPENED_TEST_CHECKPOINT',checkpoint_sha256=req['model']['checkpoint_sha256'],preprocess_sha256=req['model']['preprocessing_sha256'])
    def consume(*args):seen.append('existing_prepared_loader');return delivery,{}, {},[(record,prepared,geometry)]
    def load(*args):seen.append('existing_weight_loader_double');return object()
    def core(*args,**kwargs):
        assert kwargs['allow_real'] and kwargs['budget'].context.guard is guard
        seen.append('injected_core_no_compute');raise RuntimeError('generated intentional stop before computation')
    first=SimpleNamespace(consume_inputs=consume,baseline_source=lambda _:SimpleNamespace(load_verified_resnet18=load),DifferentiablePreparedModel=lambda *_:object())
    config=SimpleNamespace(sha256=lambda:req['config_sha256'])
    core_module=SimpleNamespace(run_prepared_e2=core,BudgetStopped=RuntimeError)
    requests=SimpleNamespace(config_from_request=lambda _:config)
    loc=reference(tmp_path/'lock.json',dict(core_sha256='1'*64,module_sha256={'epi_next/first_real_e1_e2.py':'2'*64}))
    science=reference(tmp_path/'science.json',dict(profile='E2_Q_THREE_FIXED_SLICES_V4',source_binding=dict(core_sha256='1'*64),limits=dict(per_branch_seconds=1)))
    binding=ExistingE2Binding('job_generated_bound',req,dict(path='NEVER_OPENED_PREPARED',sha256='3'*64),dict(path='NEVER_OPENED_CONFIG',sha256='4'*64),science,loc,tmp_path,tmp_path,1,req['input']['mapping_qa_sha256'])
    runner=build_existing_e2_runner(binding,guard,tmp_path/'preserved',modules=(first,core_module,requests))
    assert seen==['guard']
    claim=dict(job_id='wrong_job',attempt_id='attempt_generated',case_id=req['input']['case_id'],model_version={'checkpoint_sha256':req['model']['checkpoint_sha256']},job_parameters=dict(kind='ALGORITHM',application=req))
    generated=tmp_path/'input.bin';generated.write_bytes(DATA)
    with pytest.raises(ValueError,match='LIVE_JOB_REQUEST'):runner.run(claim,generated,None)
    assert seen==['guard']
    claim['job_id']=binding.job_id
    out=runner.run(claim,generated,None)
    assert out.result['application']['execution_status']=='FAILED'
    assert out.result['application']['actual_forward']==0
    assert seen.count('existing_prepared_loader')==seen.count('existing_weight_loader_double')==seen.count('injected_core_no_compute')==1
    assert 'guard' in seen


def test_unbound_metadata_refuses_before_real_loader(ctx,tmp_path):
    from epilocate_next.e2_launch import locked_json
    ref=reference(tmp_path/'generated.json',{'generated':True});ref['sha256']='0'*64
    with pytest.raises(ValueError,match='BOUND_METADATA_SHA'):locked_json(ref)


def test_separate_five_forward_entry_uses_exact_single_guard_and_existing_loaders(ctx,tmp_path):
    from epilocate_next.e2_launch import run_existing_selected_fidelity
    f,_,ids=ctx;req=request_for(f,ids);req['execution_mode']='LIVE';req['budget'].update(forward=5,backward=0,updates=0,seconds=120)
    events=[]
    guard=SimpleNamespace(check=lambda:events.append('check'),begin_case=lambda key:events.append('begin'),end_case=lambda:events.append('end'),before_forward=lambda:events.append('forward'),before_backward=lambda:pytest.fail('backward is forbidden'))
    prepared=SimpleNamespace(image=SimpleNamespace(shape=(32,32)),scope='APPROVED_PREPROCESSED',preprocess_id=req['model']['preprocessing_version'],task_definition_id=req['task']['definition_id'],validate=lambda:None)
    geometry=dict(native_shape_rc=[32,32],native_slice_index_zero_based=0)
    record=dict(case_index=3,source_ct_sha256=H,geometry=dict(sha256=req['input']['geometry_ledger_sha256']))
    delivery=dict(checkpoint_path='NEVER_OPENED',checkpoint_sha256=req['model']['checkpoint_sha256'],preprocess_sha256=req['model']['preprocessing_sha256'])
    first=SimpleNamespace(consume_inputs=lambda *_:(delivery,{}, {},[(record,prepared,geometry)]),baseline_source=lambda _:SimpleNamespace(load_verified_resnet18=lambda *_:object()),DifferentiablePreparedModel=lambda *_:object())
    def fidelity(*args,**kwargs):
        meter=kwargs['budget'];assert kwargs['allow_real'] and meter.context.guard is guard
        for _ in range(5):meter.forward_call(lambda:None)
        return dict(status='SUCCESS',verification_scope='INJECTED_LOADER_GUARD_ONLY_NOT_REAL_FIDELITY',cost=meter.counts(),responses={})
    core=SimpleNamespace(selected_fidelity=fidelity,run_prepared_e2=lambda *_:pytest.fail('must not optimize'),BudgetStopped=RuntimeError,digest=lambda _:'7'*64)
    config=SimpleNamespace(sha256=lambda:req['config_sha256']);requests=SimpleNamespace(config_from_request=lambda _:config)
    loc=reference(tmp_path/'lock.json',dict(core_sha256='1'*64,module_sha256={'epi_next/first_real_e1_e2.py':'2'*64}))
    science=reference(tmp_path/'science.json',dict(profile='P1_SELECTED_MASK_FIDELITY_V4',source_binding=dict(core_sha256='1'*64),limits=dict(seconds=120),scope=dict(reuse_payload_canonical_sha256='7'*64)))
    reuse=reference(tmp_path/'reuse.json',{'GENERATED_NOT_P1':True})
    binding=ExistingE2Binding('fidelity_generated',req,dict(path='NEVER_OPENED',sha256='3'*64),dict(path='NEVER_OPENED',sha256='4'*64),science,loc,tmp_path,tmp_path,3,req['input']['mapping_qa_sha256'],reuse)
    out=run_existing_selected_fidelity(binding,guard,tmp_path/'new-output',modules=(first,core,requests))
    assert out['cost']['forward']==5 and out['cost']['backward']==out['cost']['optimizer_steps']==0
    assert events.count('forward')==5 and events.count('begin')==events.count('end')==1
    assert (tmp_path/'new-output/selected-fidelity.json').exists()
    with pytest.raises(FileExistsError):run_existing_selected_fidelity(binding,guard,tmp_path/'new-output',modules=(first,core,requests))
