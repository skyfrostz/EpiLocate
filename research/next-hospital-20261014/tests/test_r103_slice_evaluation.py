"""Generated metadata/scores only; no real registry, arrays, model or labels."""
import copy
import json
from pathlib import Path
import pytest
from epi_next.r103_slice_evaluation import evaluate,rank_metrics,EvaluationRejected


def ref(name):return dict(path='/generated/'+name,sha256='a'*64)


def fixture():
    policy=json.loads((Path(__file__).parents[1]/'reports/r103_encoder/SLICE_EVALUATION_PROTOCOL_V1.json').read_text())
    controls=[];cases=[];rows=[]
    for i in range(60):
        control=dict(record_id=f'case{i}',source_group_id=f'group{i}',split='val_classification' if i<20 else 'train_weak',
            source_diagnosis='COVID-19' if i<10 else 'Normal',native_depth=8,fixed8_native_indices=list(range(8)),
            native_geometry_reference=ref('nativegeo'+str(i)),sample_geometry_reference=ref('samplegeo'+str(i)),native_tensor_sha256='b'*64)
        controls.append(control)
        if i>=20:continue
        margin=[-4.,-3.,-2.,-1.,0.,1.,2.,3.]
        beta=[.1,-.2];components=[[.5,m+.5] for m in margin]
        raw=[[v-beta[j] for j,v in enumerate(r)] for r in components]
        case=dict(record_id=control['record_id'],source_group_id=control['source_group_id'],split=control['split'],source_diagnosis=control['source_diagnosis'],
            geometry=dict(indices_Z=list(range(8))),geometry_reference=control['sample_geometry_reference'],reconstruction_status='PASS',expert_slice_label_availability='UNKNOWN',
            slice_component_logits=components,raw_class_terms=raw,weighted_class_terms=[[v/8 for v in r] for r in raw],
            slice_component_margin=margin,effective_bias=beta,effective_margin_bias=-.3,saved_raw_logits=[.5,0.],saved_bag_margin=-.5,
            saved_positive_probability=.3775406688,saved_predicted_class=0,source_label=dict(class_id=1 if i<10 else 0,scope='BAG'))
        cases.append(case)
        provenance={k:ref(k) for k in ('index','label_file','version_evidence','order_evidence','extent_evidence','member_mapping')}
        provenance.update(index_row_zero_based=i,label_index_raw=i,label_index_base=0,label_version='generated-original',ordering_confirmed=True,extent_confirmed=True,source_identity_confirmed=True)
        labels=[0,0,0,0,1,1,1,1]
        rows.append(dict(record_id=control['record_id'],source_group_id=control['source_group_id'],split=control['split'],source_diagnosis=control['source_diagnosis'],
            native_depth=8,fixed8_native_indices=list(range(8)),native_geometry_reference=control['native_geometry_reference'],native_tensor_sha256='b'*64,
            mapping_status='PAIRED',reason='generated',fixed8_labels=labels,confirmed_positions=[True]*8,scan_reference_counts=dict(positive=4,negative=4,unknown=0),
            effective_length=8,provenance=provenance))
    control=dict(schema='R103_R18_FIXED8_DATA_CONTROL_V1',consumer=ref('consumer'),rows=controls,development_record_ids=[c['record_id'] for c in cases],original_three_COVID_false_negative_record_ids=['case0','case1','case2'])
    scores=dict(schema='R103_SAVED_JSON_SCORES_V1',fixed8_control=ref('control'),cases=cases)
    registry=dict(schema='R103_SLICE_REFERENCE_REGISTRY_V1',pairing_execution='EXECUTED',purpose='EVALUATION_ONLY',reference_scope='SLICE_INFECTION_NOT_PIXEL_MASK',consumer=control['consumer'],fixed8_control=scores['fixed8_control'],
        label_semantics=dict(confirmed=True,positive='INFECTION_PRESENT',negative='INFECTION_ABSENT'),rows=rows,
        denominators=dict(source_groups=20,paired_groups=20,partially_paired_groups=0,unknown_groups=0,conflict_groups=0,confirmed_positions=160))
    return scores,control,registry,policy


def test_generated_cohorts_targets_random_and_mil_bias():
    args=fixture();result=evaluate(*args)
    assert result['status']=='DONE' and result['actual_computation']['model_forward']==0
    g=result['groups'][0]
    assert g['scores']['INFECTION_MARGIN_COMPONENT']['AUROC']==1
    assert g['scores']['INFECTION_MARGIN_COMPONENT']['AP']==1
    assert g['scores']['INFECTION_MARGIN_COMPONENT']['top_k_hits']==2
    assert g['scores']['ORIGINAL_ARGMAX_FIXED_MARGIN']['AUROC']==0
    assert g['scores']['ORIGINAL_ARGMAX_FIXED_MARGIN']['interpretation']=='NORMAL_TARGET_NOT_AN_INFECTION_MAP'
    assert g['scores']['DECLARED_FIXED_CLASS1_MARGIN']['all8_scores']==g['scores']['INFECTION_MARGIN_COMPONENT']['all8_scores']
    assert len(g['scores']['FIXED_RANDOM_REFERENCE']['ordered_native_z'])==8
    assert evaluate(*args)['groups'][0]['scores']['FIXED_RANDOM_REFERENCE']==g['scores']['FIXED_RANDOM_REFERENCE']
    assert result['macro_by_cohort']['PRIMARY_COMPLETE8']['INFECTION_MARGIN_COMPONENT']['AUROC']['defined_groups']==20
    assert 'ORIGINAL_ARGMAX_FIXED_MARGIN' not in result['macro_by_cohort']['PRIMARY_COMPLETE8']
    assert result['original_argmax_macro_separate_by_target_class']['0']['PRIMARY_COMPLETE8']['source_groups']==20
    assert all(g['medical_mechanism_assignment']=='UNKNOWN_NOT_FORCED' for g in result['three_COVID_FN_posthoc'])


def test_single_class_and_tied_AP_exact_definitions():
    allpos=rank_metrics([1,1,1],[1,1,1],[0,1,2],2)
    assert allpos['AUROC'] is None and allpos['AP']==1
    allneg=rank_metrics([1,1,1],[0,0,0],[0,1,2],2)
    assert allneg['AUROC'] is None and allneg['AP'] is None and allneg['recall_at_k'] is None
    tied=rank_metrics([1,1],[1,0],[8,3],2)
    assert tied['AUROC']==.5 and tied['AP']==.5 and tied['ordered_native_z']==[3,8]
    one=rank_metrics([1],[1],[2],2)
    assert one['top_k_hits'] is None and one['top_k_status']=='UNDEFINED_FEWER_THAN_K_CONFIRMED'


def test_mixed_original_targets_have_separate_class_macro_only():
    s,c,r,p=fixture();case=s['cases'][11]
    margin=[v+1 for v in case['slice_component_margin']]
    case.update(slice_component_margin=margin,slice_component_logits=[[.5,.5+v] for v in margin],
        saved_raw_logits=[.5,1.],saved_bag_margin=.5,saved_predicted_class=1,saved_positive_probability=.6224593312)
    case['raw_class_terms']=[[v-case['effective_bias'][j] for j,v in enumerate(row)] for row in case['slice_component_logits']]
    case['weighted_class_terms']=[[v/8 for v in row] for row in case['raw_class_terms']]
    out=evaluate(s,c,r,p)
    original=out['original_argmax_macro_separate_by_target_class']
    assert original['0']['PRIMARY_COMPLETE8']['source_groups']==19
    assert original['1']['PRIMARY_COMPLETE8']['source_groups']==1
    assert original['0']['PRIMARY_COMPLETE8']['AUROC']['mean']==0
    assert original['1']['PRIMARY_COMPLETE8']['AUROC']['mean']==1
    assert 'ORIGINAL_ARGMAX_FIXED_MARGIN' not in out['macro_by_cohort']['PRIMARY_COMPLETE8']


def test_partial_unknown_conflict_not_primary_or_negative():
    s,c,r,p=fixture()
    row=r['rows'][0];row.update(mapping_status='PARTIALLY_PAIRED',fixed8_labels=[0,1]+[None]*6,confirmed_positions=[True,True]+[False]*6,
        scan_reference_counts=dict(positive=1,negative=1,unknown=6))
    for row,status in zip(r['rows'][1:3],['UNKNOWN','CONFLICT']):
        row.update(mapping_status=status,fixed8_labels=[None]*8,confirmed_positions=[False]*8,scan_reference_counts=dict(positive=0,negative=0,unknown=8))
    r['denominators']=dict(source_groups=20,paired_groups=17,partially_paired_groups=1,unknown_groups=1,conflict_groups=1,confirmed_positions=138)
    out=evaluate(s,c,r,p)
    assert out['groups'][0]['cohort']=='SECONDARY_PARTIAL_CONFIRMED'
    assert out['groups'][0]['scores']['INFECTION_MARGIN_COMPONENT']['n']==2
    assert out['groups'][1]['scores']=={} and out['groups'][2]['scores']=={}
    assert out['macro_by_cohort']['PRIMARY_COMPLETE8']['INFECTION_MARGIN_COMPONENT']['source_groups']==17
    assert out['groups'][1]['known_reference_sampling_omission'] is None


@pytest.mark.parametrize('mutation', ['denominator','index','split','unknown_zero','bias','no_version','unconfirmed_meaning','padding','omitted_group','old_schema','duplicate_native','empty_partial','complete_partial','not_run'])
def test_fail_closed_registry_and_score_drift(mutation):
    s,c,r,p=fixture()
    if mutation=='denominator':r['denominators']['confirmed_positions']=159
    if mutation=='index':r['rows'][0]['fixed8_native_indices']=[7,6,5,4,3,2,1,0]
    if mutation=='split':r['rows'][0]['split']='train_weak'
    if mutation=='unknown_zero':r['rows'][0]['confirmed_positions'][0]=False
    if mutation=='bias':s['cases'][0]['effective_bias'][0]=9
    if mutation=='no_version':del r['rows'][0]['provenance']['version_evidence']
    if mutation=='unconfirmed_meaning':r['label_semantics']['confirmed']=False
    if mutation=='padding':r['rows'][0]['effective_length']=200
    if mutation=='omitted_group':r['rows'].pop()
    if mutation=='old_schema':r['schema']='SLICE_EVALUATION_REGISTRY_V1'
    if mutation=='duplicate_native':
        c['rows'][0]['fixed8_native_indices']=[0]*8;s['cases'][0]['geometry']['indices_Z']=[0]*8;r['rows'][0]['fixed8_native_indices']=[0]*8
    if mutation=='empty_partial':r['rows'][0].update(mapping_status='PARTIALLY_PAIRED',confirmed_positions=[False]*8,fixed8_labels=[None]*8)
    if mutation=='complete_partial':r['rows'][0]['mapping_status']='PARTIALLY_PAIRED'
    if mutation=='not_run':r['pairing_execution']='NOT_RUN'
    with pytest.raises((EvaluationRejected,KeyError)):evaluate(s,c,r,p)


def test_unknown_all_yields_no_agreement_numbers_and_no_forced_FN():
    s,c,r,p=fixture()
    for row in r['rows']:row.update(mapping_status='UNKNOWN',fixed8_labels=[None]*8,confirmed_positions=[False]*8,scan_reference_counts=dict(positive=0,negative=0,unknown=8))
    r['denominators']=dict(source_groups=20,paired_groups=0,partially_paired_groups=0,unknown_groups=20,conflict_groups=0,confirmed_positions=0)
    out=evaluate(s,c,r,p)
    assert out['status']=='NO_CONFIRMED_REFERENCE_DENOMINATOR'
    assert out['macro_by_cohort']['PRIMARY_COMPLETE8']['INFECTION_MARGIN_COMPONENT']['AUROC']['mean'] is None


def test_explicit_partial_source_extent_does_not_require_full_depth():
    s,c,r,p=fixture();row=r['rows'][0]
    row.update(mapping_status='PARTIALLY_PAIRED',fixed8_labels=[0,0,0,1,1,1,None,None],confirmed_positions=[True]*6+[False]*2,
        scan_reference_counts=dict(positive=3,negative=3,unknown=2),effective_length=6)
    r['denominators'].update(paired_groups=19,partially_paired_groups=1,confirmed_positions=158)
    out=evaluate(s,c,r,p)
    assert out['groups'][0]['cohort']=='SECONDARY_PARTIAL_CONFIRMED' and out['groups'][0]['fixed8_unknown']==2


@pytest.mark.parametrize('field,value',[('threshold',.4),('declared_target',dict(policy='DECLARED_FIXED',class_id=0)),('primary_score','ORIGINAL_ARGMAX_FIXED_MARGIN')])
def test_protocol_target_and_threshold_cannot_silently_change(field,value):
    s,c,r,p=fixture();p[field]=value
    with pytest.raises(EvaluationRejected):evaluate(s,c,r,p)


def test_native_partial_can_have_zero_confirmed_fixed8_and_is_excluded():
    s,c,r,p=fixture();indices=list(range(1,16,2))
    c['rows'][0].update(native_depth=16,fixed8_native_indices=indices)
    s['cases'][0]['geometry']['indices_Z']=indices
    r['rows'][0].update(native_depth=16,fixed8_native_indices=indices,mapping_status='PARTIALLY_PAIRED',
        fixed8_labels=[None]*8,confirmed_positions=[False]*8,scan_reference_counts=dict(positive=4,negative=4,unknown=8),effective_length=8)
    r['denominators'].update(paired_groups=19,partially_paired_groups=1,confirmed_positions=152)
    out=evaluate(s,c,r,p)
    assert out['groups'][0]['cohort']=='EXCLUDED_NO_CONFIRMED_FIXED8_REFERENCE' and out['groups'][0]['scores']=={}
    assert out['groups'][0]['mapping_status']=='PARTIALLY_PAIRED'
