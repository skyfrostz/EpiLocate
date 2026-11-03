import numpy as np
from epi_next.localization import BudgetConfig, fixed_target_response, occlusion_2d
from epi_next.residual_localization import residual_input_occlusion_3d
from epi_next.verification_vnext import numerical_witness, residual_region_witness


def test_saturation_rank_and_fixed_target_survive_class_switch():
    x=np.array([[4.,1.],[0.,0.]])
    r=occlusion_2d(lambda a:[0.,100.+a.sum()],x,np.ones_like(x,bool),1,patch_sizes=(1,))
    d=numerical_witness(r)
    assert d['status']=='PASS' and d['margin_order_record_indices']==[0,1,2,3]
    assert d['saturated_nonzero_margin_record_indices']==[0,1]
    assert d['probability_order_record_indices']==[0,1,2,3]
    switch=fixed_target_response([2.,3.,0.],[4.,1.,0.],1)
    assert switch['target']==1 and switch['perturbed_argmax']==0 and switch['margin_delta']==4
    shifted=fixed_target_response([102.,103.,100.],[104.,101.,100.],1)
    assert shifted['margin_delta']==switch['margin_delta']


def test_upstream_float32_rounding_cannot_be_recovered_or_forced_positive():
    a=np.array([0,1e8],np.float32);b=np.array([0,1e8-1],np.float32)
    response=fixed_target_response(a,b,1)
    assert response['margin_delta']==0 and response['probability_delta']==0
    x=np.ones((2,2))
    r=occlusion_2d(lambda x:a,x,np.ones_like(x,bool),1,patch_sizes=(1,))
    assert r['status']=='NO_RELIABLE_RESPONSE' and not r['candidates']


def test_failed_forward_not_counted_as_checked_space_and_partial_candidate_retained():
    x=np.ones((4,4,4));valid=np.ones_like(x,bool);calls=[0]
    def model(a):
        calls[0]+=1
        if calls[0]==5:raise RuntimeError('controlled failure after accepted formal check')
        return [0.,a.sum()],a
    r=residual_input_occlusion_3d(model,x,valid,1,(1,1,1),BudgetConfig(scales_mm=(1.,2.),seed=17))
    d=residual_region_witness(r,valid,include_indices=True)
    assert r['status']=='FAILED' and len(r['records'])==1 and d['failed_calls']==1
    assert d['regions']['verified_candidates']['voxels']==1
    assert d['regions']['unchecked']['voxels']==63
    assert d['regions']['actually_removed_before_last_stage']['voxels']==0
    assert d['regions']['diagnostic_probe_support']['voxels']==2
    assert d['coarse_proposals'][0]['center_zyx'] is not None


def test_budget_probe_space_remains_unchecked_for_formal_candidate_verification():
    x=np.ones((4,4,4));valid=np.ones_like(x,bool)
    r=residual_input_occlusion_3d(lambda a:([0.,a.sum()],a),x,valid,1,(1,1,1),BudgetConfig(scales_mm=(1.,),max_extra_evaluations=2))
    d=residual_region_witness(r,valid)
    assert d['stop_status']=='PARTIAL_BUDGET' and d['stop_reason']=='EXTRA_EVALUATION_LIMIT'
    assert d['regions']['unchecked']['voxels']==64 and d['regions']['verified_candidates']['voxels']==0
    assert 'flat_indices' not in d['regions']['unchecked']


def test_nonpositive_formal_checks_and_unchecked_partition_valid_domain():
    x=np.ones((1,1,3));valid=np.ones_like(x,bool)
    r=residual_input_occlusion_3d(lambda a:([0.,1.],a),x,valid,1,(1,1,1),BudgetConfig(scales_mm=(1.,)))
    d=residual_region_witness(r,valid)
    assert r['status']=='NO_RELIABLE_RESPONSE'
    assert d['regions']['checked_nonpositive']['voxels']==3 and d['regions']['unchecked']['voxels']==0


def test_e1_call_cap_and_inflight_timeout_preserve_completed_records():
    x=np.ones((4,4));v=np.ones_like(x,bool)
    limited=occlusion_2d(lambda a:[0.,a.sum()],x,v,1,patch_sizes=(1,),max_model_calls=3)
    assert limited['status']=='PARTIAL_BUDGET' and limited['model_calls']==3 and len(limited['records'])==2
    elapsed=[0.]
    def model(a):elapsed[0]+=1.;return [0.,a.sum()]
    timed=occlusion_2d(model,x,v,1,patch_sizes=(1,),timeout_seconds=2.,clock=lambda:elapsed[0])
    assert timed['status']=='PARTIAL_BUDGET' and timed['reason']=='TIME_LIMIT' and len(timed['records'])==1
    assert timed['elapsed_seconds']==2.


def test_unexpected_model_exception_still_counts_attempt_and_serializes_failure():
    def broken(a):raise OSError('controlled unavailable model dependency')
    r=occlusion_2d(broken,np.ones((2,2)),np.ones((2,2),bool),1)
    assert r['status']=='FAILED' and r['reason']=='MODEL_FAILURE' and r['model_calls']==1
