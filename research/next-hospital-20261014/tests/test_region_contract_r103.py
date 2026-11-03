"""Generated metadata/tensors only; no real model or medical-reference IO."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
import torch
from epi_next.region_contract_r103 import (SCHEMA,validate_contract,reference_eligibility,hard_region,
    fixed_random_regions,loss_components,planned_counts,validate_counts,validate_reuse_metadata,validate_spec,REUSE_FIELDS)


def contract():
    z=[2.,1.];members=[f'generated{i}' for i in range(8)]
    return dict(schema=SCHEMA,prediction_scope='BAG',K=8,function='FP32_GAP_CAST_FP64_MEAN_STANDARDIZED_AFFINE',
        class_labels=['Normal_SOURCE','COVID-19_OR_CAP_SOURCE'],binding={k:'a'*64 for k in ('backbone_sha256','head_sha256','preprocessing_sha256','input_manifest_sha256')},
        members=members,changed_members=members[:1],unchanged_members=members[1:],
        baseline=dict(stage=0,kind='ORIGINAL_BAG',state_sha256='b'*64,logits=z),
        original_prediction=dict(class_id=0,logits=z.copy(),logits_sha256=hashlib.sha256(json.dumps(z,separators=(',',':')).encode()).hexdigest()),
        target=dict(policy='ORIGINAL_ARGMAX_FIXED',declared_class=0,resolved_class=0),
        medical_reference=dict(input_identity=None,reference=None),source_label=dict(scope='SOURCE_GROUP',class_id=1,provenance_sha256='c'*64),medical_intent='NORMAL_MODEL_RESPONSE')


def test_target_prediction_source_and_residual_are_separate():
    c=contract();r=validate_contract(c)
    assert r['resolved_class']==0 and not r['source_label_is_slice_truth']
    c['target']=dict(policy='DECLARED_FIXED',declared_class=1,resolved_class=1);c['medical_intent']='INFECTION_SOURCE_CATEGORY_RESPONSE'
    r=validate_contract(c);assert r['predicted_class']==0 and r['resolved_class']==1 and not r['infection_optimization_eligible']
    c['target']['policy']='ORIGINAL_ARGMAX_FIXED'
    with pytest.raises(ValueError,match='DECLARED_RESOLVED'):validate_contract(c)
    c=contract();c['baseline']=dict(stage=1,kind='CURRENT_RESIDUAL_BAG',state_sha256='d'*64,logits=[0.,3.])
    assert validate_contract(c)['resolved_class']==0
    c['baseline']['kind']='ORIGINAL_BAG'
    with pytest.raises(ValueError,match='STALE'):validate_contract(c)
    c=contract();c['changed_members']=['different-patient']
    with pytest.raises(ValueError,match='ORIGINAL_MEMBER'):validate_contract(c)


def test_pixel_identity_and_partial_reference_not_slice_truth():
    identity=dict(source_namespace='GENERATED',source_group_id='groupA',native_volume_sha256='a'*64,
        series_uid='seriesA',sop_uid='sopA',native_z=3,native_geometry_sha256='b'*64)
    r=dict(kind='PARTIAL_POLYGON',mapping_status='PAIRED',identity=identity.copy(),geometry_qa='PASS',
        medical_stratum='INFECTION_REFERENCE',manifest_sha256='c'*64,annotation_completeness='UNKNOWN')
    result=reference_eligibility(identity,r);assert result['pixel_eligible'] and not result['complete_Dice_IoU_FP_eligible'] and result['background']=='UNKNOWN'
    bad=copy.deepcopy(r);bad['identity']['sop_uid']='same-size-other-slice'
    assert not reference_eligibility(identity,bad)['pixel_eligible']
    bad=copy.deepcopy(r);bad['identity']['source_namespace']='OTHER_COLLECTION'
    assert not reference_eligibility(identity,bad)['pixel_eligible']
    assert not reference_eligibility(identity,dict(kind='SLICE_01',mapping_status='PAIRED'))['pixel_eligible']
    assert reference_eligibility(identity,None)['status']=='UNKNOWN'


def test_exact_hard_area_biased_ste_gradients_and_raw_scale():
    soft=torch.full((20,20),.5,requires_grad=True);valid=torch.ones_like(soft,dtype=torch.bool);valid[-1]=False
    for percent in (5,10,20):
        weights,meta=hard_region(soft,valid,percent,straight_through=True)
        assert int(weights.sum())==380*percent//100 and not meta['reliable']
        assert ((weights==0)|(weights==1)).all() and not weights[-1].any()
    weights,_=hard_region(soft,valid,5,straight_through=True)
    weights.sum().backward();assert torch.equal(soft.grad,valid.float()) # surrogate, not top-k derivative
    actual,_=hard_region(soft.detach(),valid,5);assert torch.equal(actual.flatten()[:19],torch.ones(19))
    random=fixed_random_regions(valid);assert not (random[5]&~random[10]).any() and not (random[10]&~random[20]).any()
    _,empty=hard_region(torch.ones(2,2),torch.ones(2,2,dtype=torch.bool),5);assert empty['status']=='EMPTY_NO_PADDING'
    x=torch.tensor([[1.,2.]],requires_grad=True,dtype=torch.float64);y=x+torch.tensor([[.1,-.2]],dtype=torch.float64)
    loss=loss_components(x,y);assert float(loss['K2_COMPONENT_LS_R103_V1'].detach())==pytest.approx(64*float(loss['RAW_BAG_LS_R103_V1'].detach()))
    torch.testing.assert_close(loss['delta_component_logits'],8*loss['delta_bag_logits'])


def test_counts_and_reuse_cannot_smuggle_infection_or_extra_calls():
    counts=planned_counts((5,0,2));assert counts['forward']==57 and counts['encoded_samples']==64
    assert planned_counts()['forward']==73 and planned_counts((0,0,0))['forward']==43
    report=dict(reserved=counts.copy(),returned=counts.copy(),actual=counts.copy(),batch_sizes=[8]+[1]*56)
    validate_counts(report,(5,0,2),success=True)
    bad=copy.deepcopy(report);bad['returned']['forward']+=1
    with pytest.raises(ValueError):validate_counts(bad,(5,0,2),success=True)
    with pytest.raises(ValueError,match='NEW_TARGET'):planned_counts(target_class=1)
    original={k:'a'*64 if k.endswith('sha256') else 'generated' for k in REUSE_FIELDS};original.update(target_policy='ORIGINAL_ARGMAX_FIXED',target_class=0)
    validate_reuse_metadata(original,copy.deepcopy(original))
    changed=copy.deepcopy(original);changed['target_class']=1
    with pytest.raises(ValueError,match='SAME_INPUT_TARGET'):validate_reuse_metadata(original,changed)
    failed=copy.deepcopy(report);failed['returned']['forward']-=1;failed['returned']['encoded_samples']-=1;failed['batch_sizes'].pop();failed['actual']=None
    validate_counts(failed,(5,0,2))


def test_frozen_candidate_is_spec_not_real_entry():
    p=Path(__file__).parents[1]/'configs/e2-area-constrained-r103-v1.json'
    spec=json.loads(p.read_text());r=validate_spec(spec)
    assert not r['real_executable'] and spec['infection_branch']['count_plan'] is None
    changed=copy.deepcopy(spec);changed['status']='READY_TO_EXECUTE'
    with pytest.raises(ValueError):validate_spec(changed)
