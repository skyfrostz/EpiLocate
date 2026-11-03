"""Generated references only, no actual labels or images."""
import copy
import pytest
from epi_next import medical_slice_registry_v2 as m
from test_slice_evaluation_registry import fixture


def example():
    g,i,a,e=fixture();g[0].update(record_id='GEN',source_diagnosis='COVID-19',is_original_COVID_FN=True,split='val_classification')
    e['order_policy']='SLICE_LOCATION_DESCENDING'
    r={'source_group_id':g[0]['source_group_id'],'source_diagnosis':'COVID-19','geometry_sha256':g[0]['geometry_binding']['sha256'],
       'version_applicability':'VERIFIED_CURRENT','original_Label_Index':0,'label_index_base':0,'annotation_case_index':0,'Index_row':0,
       'label_file_version':'GENERATED_UPDATED','evidence':e,'labels_publisher_domain':[1,0,1,0,1,0,1,0],
       'declared_valid_publisher_indices':list(range(8)),'range_policy':'EXPLICIT_PUBLISHER_EXTENT'}
    return {'groups':g},{'status':'EXECUTED','rows':[r]}


def test_not_run_is_null_evaluable_not_zero():
    meta,_=example();r=m.build_registry(meta);m.validate_registry(r)
    assert r['all60']['state_counts']['UNKNOWN']==1 and r['all60']['confirmed_evaluable_groups'] is None
    assert r['development20']['unknown_fixed8_positions']==8 and r['original_COVID_FN']['pairing_execution']=='NOT_RUN'


def test_full_partial_unknown_conflict_denominators():
    meta,ref=example();r=m.build_registry(meta,ref);assert r['rows'][0]['status']=='PAIRED'
    assert r['rows'][0]['fixed8_labels']==[0,1,0,1,0,1,0,1]
    ref['rows'][0]['labels_publisher_domain'][0]=None
    r=m.build_registry(meta,ref);assert r['rows'][0]['status']=='PARTIALLY_PAIRED'
    assert r['all60']['confirmed_evaluable_fixed8_positions']==7
    ref['rows'][0]['geometry_sha256']='b'*64
    r=m.build_registry(meta,ref);assert r['rows'][0]['status']=='CONFLICT'
    assert r['all60']['confirmed_evaluable_groups']==0 and r['rows'][0]['fixed8_labels']==[None]*8


@pytest.mark.parametrize('defect',['duplicate_ref','unknown_version','missing_order','wrong_length','missing_SL','invalid_label','unproved_base'])
def test_fail_closed(defect):
    meta,ref=example();r=ref['rows'][0]
    if defect=='duplicate_ref':ref['rows'].append(copy.deepcopy(r))
    if defect=='unknown_version':r['version_applicability']='UNKNOWN'
    if defect=='missing_order':r['evidence']['order_policy']='UNKNOWN'
    if defect=='wrong_length':r['labels_publisher_domain'].pop()
    if defect=='missing_SL':del meta['groups'][0]['native_slices'][1]['slice_location']
    if defect=='invalid_label':r['labels_publisher_domain'][0]=True
    if defect=='unproved_base':r['label_index_base']=1
    result=m.build_registry(meta,ref);assert result['rows'][0]['status'] in ('UNKNOWN','CONFLICT')
    assert result['all60']['confirmed_evaluable_fixed8_positions']==0


def test_undeclared_tail_never_negative_or_metric_denominator():
    meta,ref=example();r=ref['rows'][0];r['declared_valid_publisher_indices']=list(range(6));r['labels_publisher_domain'][-2:]=[None,None]
    result=m.build_registry(meta,ref);assert result['rows'][0]['status']=='PARTIALLY_PAIRED'
    assert result['all60']['confirmed_evaluable_native_positions']==6
    assert result['rows'][0]['actual_effective_slice_count']==6


def test_labels_cannot_enter_training_sampling_roi_or_threshold():
    meta,ref=example()
    for p in ('training','slice_selection','ROI','threshold_selection'):
        with pytest.raises(ValueError,match='EVALUATION_ONLY'):m.build_registry(meta,ref,purpose=p)


def test_status_corruption_validator_rejects():
    meta,_=example();r=m.build_registry(meta);r['rows'][0]['native_labels'][0]=0
    with pytest.raises(ValueError,match='UNKNOWN_CANNOT'):m.validate_registry(r)


def test_export_generated20_matches_encoder_validator():
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('generated_enc_validator',Path(__file__).resolve().parents[1]/'epi_next/r103_slice_evaluation.py')
    enc=importlib.util.module_from_spec(spec);spec.loader.exec_module(enc)
    meta,ref=example();g=meta['groups'][0];g['native_tensor_SHA']='b'*64
    for value in ref['rows'][0]['evidence'].values():
        if isinstance(value,dict) and 'path' in value:value['path']='/generated/'+value['path']
    ref['rows'][0]['evidence']['member_mapping']={'path':'/generated/member-map.json','sha256':'c'*64}
    groups=[];refs=[]
    for i in range(20):
        z=copy.deepcopy(g);z.update(record_id='GEN'+str(i),source_group_id='GROUP'+str(i));groups.append(z)
        r=copy.deepcopy(ref['rows'][0]);r.update(source_group_id=z['source_group_id'],annotation_case_index=i,original_Label_Index=i,Index_row=i);refs.append(r)
    meta=dict(groups=groups,development_record_ids=[g['record_id'] for g in groups])
    consumer={'path':'/generated/consumer.json','sha256':'d'*64};ctrlref={'path':'/generated/control.json','sha256':'e'*64}
    control={'consumer':consumer,'rows':[dict(record_id=g['record_id'],native_depth=g['depth'],fixed8_native_indices=g['fixed8'],native_geometry_reference=g['geometry_binding'],native_tensor_sha256=g['native_tensor_SHA']) for g in groups]}
    scores={'fixed8_control':ctrlref,'cases':[dict(record_id=g['record_id'],source_group_id=g['source_group_id'],source_diagnosis=g['source_diagnosis'],split=g['split']) for g in groups]}
    result=m.build_registry(meta,{'status':'EXECUTED','rows':refs})
    view=m.export_development_view(result,meta,consumer,ctrlref,{'path':'/generated/parent.json','sha256':'f'*64},'a'*64)
    _,counts=enc.validate_registry(view,scores,control);assert counts['paired_groups']==20 and counts['confirmed_positions']==160
    view=m.export_development_view(m.build_registry(meta),meta,consumer,ctrlref,{},'a'*64)
    with pytest.raises(ValueError,match='NOT_RUN_REGISTRY'):enc.validate_registry(view,scores,control)


def test_summary_corruption_rejected():
    meta,_=example();r=m.build_registry(meta);r['all60']['confirmed_evaluable_groups']=0
    with pytest.raises(ValueError,match='NULL'):m.validate_registry(r)
