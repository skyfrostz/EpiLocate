import numpy as np
import pytest
from epi_next.localization import fixed_target_response, occlusion_2d, hierarchical_input_occlusion_3d, BudgetConfig


def test_saturation_preserves_margin():
    r=fixed_target_response([0,100],[0,99],1)
    assert r['probability_delta']==0 and r['margin_delta']==1


def test_target_stays_fixed_when_argmax_changes():
    r=fixed_target_response([2,3],[2,1],1)
    assert (r['baseline_argmax'],r['perturbed_argmax'],r['target'],r['margin_delta'])==(1,0,1,2)


@pytest.mark.parametrize('bad',[[np.nan,0],[np.inf,0],[[0,1]],[1]])
def test_nonfinite_or_shape_rejected(bad):
    with pytest.raises(ValueError): fixed_target_response(bad,[0,1],1)


def test_e1_ties_all_negative_and_empty():
    x=np.ones((4,4));valid=np.ones_like(x,dtype=bool)
    r=occlusion_2d(lambda a:[0,a.sum()],x,valid,1,patch_sizes=(2,2))
    assert len(r['candidates'])==4 and r['model_calls']==5
    assert all(z['margin_delta']==4 for z in r['candidates'])
    negative=occlusion_2d(lambda a:[0,-a.sum()],x,valid,1,patch_sizes=(2,))
    assert negative['status']=='NO_RELIABLE_RESPONSE' and not negative['candidates']
    assert occlusion_2d(None,x,valid & False,1)['status']=='INPUT_UNSUPPORTED'
    assert occlusion_2d(None,x,None,1)['status']=='INPUT_UNSUPPORTED'


def test_e1_nonfinite_prediction_counted():
    r=occlusion_2d(lambda a:[0,np.nan],np.ones((2,2)),np.ones((2,2),bool),1)
    assert r['status']=='FAILED' and r['model_calls']==1


def args():
    x=np.ones((8,8,8)); return x,np.ones_like(x,bool),x.copy()


def test_f1_counts_probes_and_budget_reproducibility():
    x,v,c=args();cfg=BudgetConfig(max_extra_evaluations=4,scales_mm=(1.,2.,3.))
    r=hierarchical_input_occlusion_3d(lambda a:[0,a.sum()],x,v,c,1,(1,1,1),cfg)
    rr=hierarchical_input_occlusion_3d(lambda a:[0,a.sum()],x,v,c,1,(1,1,1),cfg)
    assert r['status']=='PARTIAL_BUDGET' and r['extra_evaluations']==4 and r['model_calls']==5
    assert r['random_probes_completed']==2
    assert r['records']==rr['records']
    assert all(z['target']==1 for z in r['records'])
    assert len({tuple(z['mask_flat_indices']) for z in r['records']})==4


def test_f1_full_input_perturbation_and_physical_units():
    x,v,c=args();seen=[]
    def model(a): seen.append(a.copy());return [0,a.sum()]
    r=hierarchical_input_occlusion_3d(model,x,v,c,1,(2,1,1),BudgetConfig(scales_mm=(2.,)))
    for a,z in zip(seen[1:],r['records']):
        assert np.flatnonzero(a==0).tolist()==z['mask_flat_indices']
        assert all(a.flatten()[i]==1 for i in set(range(x.size))-set(z['mask_flat_indices']))
        assert z['bounds_zyx'][0][1]-z['bounds_zyx'][0][0]==1
    assert np.all(x==1)


def test_f1_soft_timeout_preserves_record():
    x,v,c=args();t=[0.]
    def model(a): t[0]+=1.;return [0,a.sum()]
    r=hierarchical_input_occlusion_3d(model,x,v,c,1,(1,1,1),BudgetConfig(timeout_seconds=2,scales_mm=(1.,)),clock=lambda:t[0])
    assert r['status']=='PARTIAL_BUDGET' and r['extra_evaluations']==1
    assert len(r['records'])==1 and r['elapsed_seconds']==2


def test_small_scale_response_is_not_intersection_discarded():
    x,v,c=args()
    def model(a):
        count=int((a==0).sum())
        return [0,10. if count != 1 else 9.]
    r=hierarchical_input_occlusion_3d(model,x,v,c,1,(1,1,1),BudgetConfig(scales_mm=(1.,2.,4.)))
    assert r['candidates'] and all(z['scale_mm']==1 for z in r['candidates'])


def test_f1_no_response_and_unknown_support():
    x,v,c=args()
    r=hierarchical_input_occlusion_3d(lambda a:[0,1],x,v,c,1,(1,1,1),BudgetConfig(scales_mm=(1.,)))
    assert r['status']=='NO_RELIABLE_RESPONSE' and r['candidates']==[]
    assert hierarchical_input_occlusion_3d(None,x,None,c,1,(1,1,1))['status']=='INPUT_UNSUPPORTED'


@pytest.mark.parametrize('cfg',[BudgetConfig(stages=4),BudgetConfig(max_extra_evaluations=33),BudgetConfig(timeout_seconds=121),BudgetConfig(random_probes=1)])
def test_invalid_budget(cfg):
    with pytest.raises(ValueError):cfg.validate()


def test_f1_nonfinite_forward_count_and_partial_records():
    x,v,c=args();calls=[0]
    def model(a):
        calls[0]+=1
        return [0,np.nan] if calls[0]==3 else [0,float(a.sum())]
    r=hierarchical_input_occlusion_3d(model,x,v,c,1,(1,1,1),BudgetConfig(scales_mm=(1.,)))
    assert r['status']=='FAILED' and r['model_calls']==3 and r['extra_evaluations']==2
    assert len(r['records'])==1 and r['random_probes_completed']==1


def test_f1_tiny_domain_cannot_satisfy_two_probes():
    x=np.ones((1,1,1));v=np.ones_like(x,bool)
    r=hierarchical_input_occlusion_3d(lambda a:[0,float(a.sum())],x,v,x,1,(1,1,1))
    assert r['status']=='INPUT_UNSUPPORTED' and r['reason']=='INSUFFICIENT_PROBE_SUPPORT' and r['random_probes_completed']==1
    assert r['model_calls']==2 and r['extra_evaluations']==1


def test_f1_unsearched_probes_are_disjoint_voxels():
    x,v,c=args()
    r=hierarchical_input_occlusion_3d(lambda a:[0,float(a.sum())],x,v,c,1,(1,1,1),BudgetConfig(scales_mm=(3.,)))
    probes=[set(z['mask_flat_indices']) for z in r['records'] if z['kind']=='SEEDED_UNSEARCHED_PROBE']
    assert len(probes)==2 and probes[0].isdisjoint(probes[1])


@pytest.mark.parametrize('target',[True,False,np.bool_(True),1.0,-1,2])
def test_fixed_target_rejects_bool_float_or_out_of_range(target):
    with pytest.raises(ValueError):fixed_target_response([0,1],[0,.5],target)


def test_public_status_reasons_and_variant_identity():
    x,v,c=args()
    missing=hierarchical_input_occlusion_3d(None,x,None,c,1,(1,1,1))
    assert missing['status']=='INPUT_UNSUPPORTED' and missing['reason']=='UNKNOWN_VALID_SUPPORT'
    bad=occlusion_2d(lambda a:[0,np.nan],np.ones((2,2)),np.ones((2,2),bool),1)
    assert bad['status']=='FAILED' and bad['reason']=='NUMERICAL_FAILURE'
    result=hierarchical_input_occlusion_3d(lambda a:[0,float(a.sum())],x,v,c,1,(1,1,1),BudgetConfig(scales_mm=(1.,)))
    assert result['algorithm']=='EPI-NEXT-F1-static-coarse-original-input-search-exclusion-v1'
    assert result['planned_residual_input_f1']=='NOT_IMPLEMENTED'
