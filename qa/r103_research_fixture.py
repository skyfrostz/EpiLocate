"""Tiny generated receipts, no real patient identifiers, assets or map arrays."""
from qa.r18_research_fixture import reference
from epilocate_next.r103_research_metadata import CLASSES


def spatial_fixture():
    return dict(schema='R92_TRUE_SPATIAL_RECEIPT_V1',status='PASS',expert_labels='UNKNOWN',actual_slice_positions=8,
        rows=[dict(source_group_id='GENERATED-SPATIAL',head_reference=reference('head.json'),
            model_context=dict(backbone_sha256=reference('encoder')['sha256']),
            hook=dict(shape=[8,512,7,7],hook='avgpool.forward_pre_hook'),residual_correction=False,
            assets={k:reference(k+'.npy') for k in ('signed_class','signed_margin','positive_margin_display')},
            saved_logits=[2.,1.],geometry=dict(indices_Z=list(range(8))),geometry_reference=reference('geometry.json'))])


def comparison_fixture():
    responses={}
    for m in ('CAM','E1','E2'):
        for pct in (5,10,20):
            for action in ('keep','remove'):
                responses[f'{m}_{pct}_{action}']=dict(fixed_target=0,logits=[[1.5,1.]],
                    target_logit_margin=.5,all_logits_squared_difference=.25)
    responses['E2_final_soft_keep']=dict(fixed_target=0,logits=[[1.5,1.]],target_logit_margin=.5,all_logits_squared_difference=.25)
    return dict(schema='R92_SAME_BAG_COMPARISON_V1',status='SUCCESS',expert_reference_status='UNKNOWN',
        source_group_id='GENERATED-COMPARISON',candidate_status='NO_CALIBRATED_RELIABILITY_RULE',reliable_candidates=[],
        source_geometry=dict(indices_Z=list(range(8))),limitation='GENERATED uncalibrated conditional member0',
        adapter=dict(K=8,prediction_scope='BAG',class_labels=CLASSES[:],target_policy='ORIGINAL_ARGMAX_FIXED',
            fixed_target=0,original_logits=[[2.,1.]],cpf='NOT_CALIBRATED_NOT_APPLIED'),responses=responses)


def old_fixture():
    return dict(schema='R92_FOURGRID_RESULT_V1',status='SUCCESS',fixed_target=1,limitation='GENERATED old mechanism',
        responses={k:dict(fixed_target=1,logits=[[0.,1.]],target_logit_margin=1.) for k in 'ABCD'})


def label_fixture():
    return dict(schema='ARCHIVE_BOUND_AB_RESULT_V2',status='AB_EVIDENCE_SAVED_MAPPING_UNKNOWN',registry='NOT_RUN',
                index_rows_observed=79,label_shape=[79,200])


def joined_fixture():
    from qa.r18_research_fixture import producer_fixture
    from epilocate_next.r18_research_artifact import from_encoder_contributions
    from epilocate_next.r103_research_metadata import from_r102_receipt,join_saved_contributions
    raw=producer_fixture();raw['cases']=raw['cases'][:1]
    source=reference('scalar-source.json');scalar=from_encoder_contributions(raw,source,evidence='GENERATED')
    c=raw['cases'][0];sp=spatial_fixture();r=sp['rows'][0]
    r.update(source_group_id=c['source_group_id'],saved_logits=c['saved_raw_logits'],
        head_reference=c['head_reference'],geometry=c['geometry'],geometry_reference=c['geometry_reference'])
    metadata=from_r102_receipt(sp,reference('spatial.json'),evidence='GENERATED')
    control=dict(schema='R103_R18_FIXED8_DATA_CONTROL_V1',status='EXISTING_JSON_METADATA_ONLY',medical_pairing='NOT RUN',
        new_feature_arithmetic=0,new_model_calls=0,new_native_weight_array_reads=0,source_artifact=source,
        development_record_ids=[c['record_id']],rows=[dict(source_group_id=c['source_group_id'],record_id=c['record_id'],
            split='val_classification',fixed8_native_indices=c['geometry']['indices_Z'],native_depth=64,
            sample_geometry_reference=c['geometry_reference'])])
    return metadata,scalar,control,reference('control.json')
