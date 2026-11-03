"""Versioned saved-JSON slice correspondence evaluator; no model/array IO.

Pure functions are for generated regression or separately approved evaluation.
Real registry consumption must enter the admitted R103 CLI, never this import.
"""
import hashlib
import math
import random
import statistics


class EvaluationRejected(ValueError):
    pass


def require(ok, reason):
    if not ok: raise EvaluationRejected(reason)


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def reference(value):
    return (isinstance(value,dict) and set(value)=={'path','sha256'}
            and isinstance(value['path'],str) and value['path'].startswith('/')
            and isinstance(value['sha256'],str) and len(value['sha256'])==64
            and all(c in '0123456789abcdef' for c in value['sha256']))


def near(a,b,policy):
    t=policy['score_identity_tolerance']
    return finite(a) and finite(b) and abs(a-b)<=t['atol']+t['rtol']*abs(b)


def validate_scores(scores,control,policy):
    require(scores.get('schema')=='R103_SAVED_JSON_SCORES_V1','SCORE_SCHEMA')
    require(control.get('schema')=='R103_R18_FIXED8_DATA_CONTROL_V1','CONTROL_SCHEMA')
    cases=scores['cases']; ids=control['development_record_ids']
    require(len(cases)==20 and [c['record_id'] for c in cases]==ids and len(set(ids))==20,'EXACT_DEVELOPMENT20')
    by_id={r['record_id']:r for r in control['rows']}
    require(len(control['rows'])==len(by_id)==60 and len({r['source_group_id'] for r in control['rows']})==60,'ORIGINAL_CONTROL60')
    for c in cases:
        original=by_id[c['record_id']]
        depth=original['native_depth']; indices=original['fixed8_native_indices']
        require(type(depth) is int and depth>=8 and len(indices)==8 and len(set(indices))==8
                and all(type(v) is int for v in indices) and indices==[math.floor((j+.5)*depth/8) for j in range(8)],'UNIQUE_ORIGINAL_NATIVE8_REQUIRED')
        require(all(c[k]==original[k] for k in ('source_group_id','split','source_diagnosis')),'SOURCE_GROUP_BINDING')
        require(c['split']=='val_classification' and c['geometry']['indices_Z']==original['fixed8_native_indices'],'ORIGINAL8_CHANGED')
        require(c['geometry_reference']==original['sample_geometry_reference'],'GEOMETRY_BINDING')
        require(c['reconstruction_status']=='PASS' and c['expert_slice_label_availability']=='UNKNOWN','SAVED_RESULT_SCOPE')
        for key in ('slice_component_logits','raw_class_terms','weighted_class_terms'):
            require(len(c[key])==8 and all(len(r)==2 and all(finite(v) for v in r) for r in c[key]),'SCORES_8_BY2_FINITE')
        require(len(c['slice_component_margin'])==8 and all(finite(v) for v in c['slice_component_margin']),'MARGIN_SHAPE')
        require(len(c['effective_bias'])==2 and len(c['saved_raw_logits'])==2,'BIAS_LOGIT_SHAPE')
        for j in range(2):
            require(near(math.fsum(r[j] for r in c['slice_component_logits'])/8,c['saved_raw_logits'][j],policy),'MEAN_MIL_LOGIT_MISMATCH')
            for i in range(8):
                require(near(c['raw_class_terms'][i][j]+c['effective_bias'][j],c['slice_component_logits'][i][j],policy),'EFFECTIVE_BIAS_MISSING')
                require(near(c['raw_class_terms'][i][j]/8,c['weighted_class_terms'][i][j],policy),'K8_WEIGHT_MISMATCH')
        for i in range(8):require(near(c['slice_component_logits'][i][1]-c['slice_component_logits'][i][0],c['slice_component_margin'][i],policy),'MARGIN_DIRECTION')
        require(near(math.fsum(c['slice_component_margin'])/8,c['saved_bag_margin'],policy),'BAG_MARGIN_MISMATCH')
        require(c['saved_predicted_class']==int(c['saved_positive_probability']>.5),'FROZEN_THRESHOLD')
    return by_id


def validate_registry(registry,scores,control):
    require(registry.get('schema')=='R103_SLICE_REFERENCE_REGISTRY_V1','STRICT_VERSIONED_REGISTRY_REQUIRED')
    require(registry.get('pairing_execution')=='EXECUTED','NOT_RUN_REGISTRY_IS_NOT_AN_EVALUATED_ZERO')
    require(registry.get('purpose')=='EVALUATION_ONLY' and registry.get('reference_scope')=='SLICE_INFECTION_NOT_PIXEL_MASK','REFERENCE_USE_SCOPE')
    require(registry.get('consumer')==control['consumer'] and registry.get('fixed8_control')==scores['fixed8_control'],'REGISTRY_INPUT_BINDING')
    rows=registry['rows']; expected={c['record_id']:c for c in scores['cases']}
    require(len(rows)==20 and {r['record_id'] for r in rows}==set(expected),'ALL20_REGISTRY_ROWS_REQUIRED')
    require(len({r['source_group_id'] for r in rows})==20,'UNIQUE_REGISTRY_GROUPS')
    controls={r['record_id']:r for r in control['rows']}
    counts=dict(source_groups=20,paired_groups=0,partially_paired_groups=0,unknown_groups=0,conflict_groups=0,confirmed_positions=0)
    statuses={'PAIRED':'paired_groups','PARTIALLY_PAIRED':'partially_paired_groups','UNKNOWN':'unknown_groups','CONFLICT':'conflict_groups'}
    for r in rows:
        c=expected[r['record_id']];original=controls[r['record_id']]
        require(all(r[k]==c[k] for k in ('source_group_id','split','source_diagnosis')),'REGISTRY_SOURCE_SPLIT_MISMATCH')
        require(r['fixed8_native_indices']==original['fixed8_native_indices'] and r['native_depth']==original['native_depth'],'REGISTRY_FIXED8_DEPTH_MISMATCH')
        require(r['native_geometry_reference']==original['native_geometry_reference'] and r['native_tensor_sha256']==original['native_tensor_sha256'],'NATIVE_IDENTITY_MISMATCH')
        require(r['mapping_status'] in statuses and isinstance(r['reason'],str),'MAPPING_STATUS_REASON')
        labels=r['fixed8_labels'];confirmed=r['confirmed_positions']
        require(len(labels)==len(confirmed)==8 and all(type(v) is bool for v in confirmed),'REFERENCE_POSITION_MASK')
        require(all((type(v) is int and v in (0,1)) if ok else v is None for v,ok in zip(labels,confirmed)),'UNKNOWN_IS_NOT_NEGATIVE')
        n=sum(confirmed); status=r['mapping_status'];counts[statuses[status]]+=1;counts['confirmed_positions']+=n
        scan=r['scan_reference_counts']
        require(set(scan)=={'positive','negative','unknown'} and all(type(v) is int and v>=0 for v in scan.values()) and sum(scan.values())==r['native_depth'],'SCAN_DENOMINATOR')
        if status in ('UNKNOWN','CONFLICT'):
            require(n==0 and scan['unknown']==r['native_depth'] and bool(r['reason']),'UNRESOLVED_REFERENCE_EXCLUDED')
            continue
        require(registry['label_semantics']==dict(confirmed=True,positive='INFECTION_PRESENT',negative='INFECTION_ABSENT'),'MEDICAL_LABEL_MEANING_UNRESOLVED')
        require(type(r['effective_length']) is int and scan['positive']+scan['negative']<=r['effective_length']<=r['native_depth'],'NO_PADDING_OR_TRUNCATION_INFERENCE')
        provenance=r['provenance']
        require(set(provenance)=={'index','label_file','version_evidence','order_evidence','extent_evidence','member_mapping','index_row_zero_based','label_index_raw','label_index_base','label_version','ordering_confirmed','extent_confirmed','source_identity_confirmed'},'STRICT_REFERENCE_PROVENANCE')
        require(all(reference(provenance[k]) for k in ('index','label_file','version_evidence','order_evidence','extent_evidence','member_mapping')),'REFERENCE_SOURCE_SHA_REQUIRED')
        require(all(provenance[k] is True for k in ('ordering_confirmed','extent_confirmed','source_identity_confirmed')),'PAIRING_UNCONFIRMED')
        require(type(provenance['index_row_zero_based']) is int and provenance['index_row_zero_based']>=0 and type(provenance['label_index_raw']) is int
                and type(provenance['label_index_base']) is int and provenance['label_index_base'] in (0,1) and provenance['label_index_raw']>=provenance['label_index_base']
                and isinstance(provenance['label_version'],str) and bool(provenance['label_version']),'INDEX_VERSION_BASE_REQUIRED')
        if status=='PAIRED':require(n==8 and scan['unknown']==0 and r['effective_length']==r['native_depth'],'PAIRED_REQUIRES_COMPLETE_RESOLVED_REFERENCE')
        if status=='PARTIALLY_PAIRED':require(scan['positive']+scan['negative']>=1 and scan['unknown']>0,'PARTIAL_MUST_HAVE_CONFIRMED_INCOMPLETE_NATIVE_REFERENCE')
        require(sum(v==1 for v in labels)<=scan['positive'] and sum(v==0 for v in labels)<=scan['negative'],'SELECTED_REFERENCE_EXCEEDS_SCAN')
    require(registry.get('denominators')==counts,'DECLARED_REGISTRY_DENOMINATOR_MISMATCH')
    return {r['record_id']:r for r in rows},counts


def rank_metrics(values,labels,native_z,top_k):
    require(len(values)==len(labels)==len(native_z) and all(finite(v) for v in values),'FINITE_METRIC_INPUT')
    n=len(values); positives=sum(labels); negatives=n-positives
    auroc=None if not positives or not negatives else math.fsum((1 if a>b else .5 if a==b else 0)
        for a,y in zip(values,labels) if y for b,z in zip(values,labels) if not z)/(positives*negatives)
    order=sorted(range(n),key=lambda i:(-values[i],native_z[i]))
    ap=None
    if positives:
        ap=0.;seen=tp=0
        for threshold in sorted(set(values),reverse=True):
            at=[i for i in range(n) if values[i]==threshold];added=sum(labels[i] for i in at)
            seen+=len(at);tp+=added;ap+=(added/positives)*(tp/seen)
    k_ready=n>=top_k;top=order[:top_k] if k_ready else []
    hits=sum(labels[i] for i in top) if k_ready else None
    def distribution(label):
        x=[v for v,y in zip(values,labels) if y==label]
        return dict(n=len(x),mean=statistics.fmean(x) if x else None,median=statistics.median(x) if x else None,min=min(x) if x else None,max=max(x) if x else None,values=x)
    return dict(n=n,positive=positives,negative=negatives,AUROC=auroc,
        AUROC_undefined_reason=None if auroc is not None else 'BOTH_REFERENCE_CLASSES_REQUIRED',AP=ap,
        AP_undefined_reason='NO_POSITIVE_REFERENCE' if not positives else None,
        ordered_native_z=[native_z[i] for i in order],ordered_scores=[values[i] for i in order],
        top_k=top_k,top_k_status='DEFINED' if k_ready else 'UNDEFINED_FEWER_THAN_K_CONFIRMED',top_k_hits=hits,
        top_k_any_positive=None if hits is None else hits>0,precision_at_k=None if hits is None else hits/top_k,
        recall_at_k=None if hits is None or not positives else hits/positives,
        positive_distribution=distribution(1),negative_distribution=distribution(0))


def macro(groups,target,cohort):
    selected=[g for g in groups if g['cohort']==cohort and target in g['scores']]
    result={'source_groups':len(selected)}
    for key in ('AUROC','AP','precision_at_k','recall_at_k','top_k_any_positive'):
        defined=[g['scores'][target][key] for g in selected if g['scores'][target][key] is not None]
        result[key]=dict(mean=statistics.fmean(defined) if defined else None,defined_groups=len(defined),undefined_groups=len(selected)-len(defined))
    return result


def evaluate(scores,control,registry,policy):
    require(policy['schema']=='R103_SLICE_EVALUATION_PROTOCOL_V1' and policy['K']==8 and policy['top_k']==2
            and policy['random_reference']['seed']==10317 and policy['random_reference']['rankings_per_group']==1
            and policy['declared_target']==dict(policy='DECLARED_FIXED',class_id=1) and policy['threshold']==.5
            and policy['primary_score']=='INFECTION_MARGIN_COMPONENT' and policy['secondary_score']=='INFECTION_CLASS1_COMPONENT_LOGIT','PRELOCKED_PROTOCOL')
    validate_scores(scores,control,policy);refs,counts=validate_registry(registry,scores,control)
    groups=[]
    for c in scores['cases']:
        r=refs[c['record_id']];eligible=[i for i,ok in enumerate(r['confirmed_positions']) if ok]
        cohort='PRIMARY_COMPLETE8' if r['mapping_status']=='PAIRED' else 'SECONDARY_PARTIAL_CONFIRMED' if eligible else 'EXCLUDED_NO_CONFIRMED_FIXED8_REFERENCE' if r['mapping_status']=='PARTIALLY_PAIRED' else 'EXCLUDED_UNRESOLVED'
        z=c['geometry']['indices_Z']; positive=sum(v==1 for v in r['fixed8_labels']);unknown=8-len(eligible)
        group=dict(record_id=c['record_id'],source_group_id=c['source_group_id'],source_diagnosis=c['source_diagnosis'],split=c['split'],cohort=cohort,
            mapping_status=r['mapping_status'],mapping_reason=r['reason'],reference_provenance=r.get('provenance'),
            original_BAG_prediction=c['saved_predicted_class'],original_BAG_source_label=c['source_label'],original_BAG_logits=c['saved_raw_logits'],
            original_BAG_margin=c['saved_bag_margin'],original_argmax_target=c['saved_predicted_class'],declared_fixed_target=1,
            effective_bias=c['effective_bias'],effective_margin_bias=c['effective_margin_bias'],
            fixed8_native_indices=z,confirmed_native_indices=[z[i] for i in eligible],fixed8_reference_labels=r['fixed8_labels'],
            fixed8_known_positive=positive,fixed8_unknown=unknown,scan_reference_counts=r['scan_reference_counts'],
            original_COVID_FN=c['record_id'] in control['original_three_COVID_false_negative_record_ids'],scores={},
            medical_mechanism_assignment='UNKNOWN_NOT_FORCED',spatial_localization='NOT_EVALUATED_SLICE_LABELS_ARE_NOT_MASKS')
        group['known_reference_sampling_omission']=None if cohort!='PRIMARY_COMPLETE8' or r['scan_reference_counts']['positive']==0 else positive==0
        group['fixed8_positive_slice_sampling_fraction']=positive/r['scan_reference_counts']['positive'] if cohort=='PRIMARY_COMPLETE8' and r['scan_reference_counts']['positive'] else None
        if eligible:
            margin=c['slice_component_margin']; class1=[row[1] for row in c['slice_component_logits']]
            target_scores=dict(INFECTION_MARGIN_COMPONENT=margin,INFECTION_CLASS1_COMPONENT_LOGIT=class1,
                ORIGINAL_ARGMAX_FIXED_MARGIN=margin if c['saved_predicted_class']==1 else [-v for v in margin],
                DECLARED_FIXED_CLASS1_MARGIN=margin)
            labels=[r['fixed8_labels'][i] for i in eligible];positions=[z[i] for i in eligible]
            for target,values in target_scores.items():
                result=rank_metrics([values[i] for i in eligible],labels,positions,2)
                result['all8_scores']=values
                result['interpretation']='NORMAL_TARGET_NOT_AN_INFECTION_MAP' if target=='ORIGINAL_ARGMAX_FIXED_MARGIN' and c['saved_predicted_class']==0 else 'INFECTION_CLASS1_RESPONSE_VS_SLICE_REFERENCE'
                result['top_k_domain']='ALL_ORIGINAL8' if cohort=='PRIMARY_COMPLETE8' else 'CONFIRMED_SUBSET_ONLY_NOT_ALL8'
                group['scores'][target]=result
            seed=int.from_bytes(hashlib.sha256(('R103_RANDOM_V1:10317:'+c['source_group_id']).encode()).digest()[:8],'big')
            permutation=list(range(len(eligible)));random.Random(seed).shuffle(permutation)
            random_values=[0]*len(eligible)
            for rank,index in enumerate(permutation):random_values[index]=len(eligible)-rank
            group['scores']['FIXED_RANDOM_REFERENCE']=rank_metrics(random_values,labels,positions,2)
            group['random_reference_seed']=seed
            group['component_sign_summary']=dict(positive_component_count=sum(v>0 for v in margin),negative_component_count=sum(v<0 for v in margin),
                positive_mean_term=math.fsum(max(v,0) for v in margin)/8,negative_mean_term=math.fsum(min(v,0) for v in margin)/8,
                meaning='bias-inclusive affine components averaged; positive is not a slice disease prediction; cancellation alone is not medical causality')
        groups.append(group)
    targets=['INFECTION_MARGIN_COMPONENT','INFECTION_CLASS1_COMPONENT_LOGIT','DECLARED_FIXED_CLASS1_MARGIN','FIXED_RANDOM_REFERENCE']
    aggregate={cohort:{target:macro(groups,target,cohort) for target in targets} for cohort in ('PRIMARY_COMPLETE8','SECONDARY_PARTIAL_CONFIRMED')}
    original_by_target={str(target):{cohort:macro([g for g in groups if g['original_argmax_target']==target],'ORIGINAL_ARGMAX_FIXED_MARGIN',cohort)
        for cohort in ('PRIMARY_COMPLETE8','SECONDARY_PARTIAL_CONFIRMED')} for target in (0,1)}
    strata={diagnosis:dict(source_groups=sum(g['source_diagnosis']==diagnosis for g in groups),
        primary_paired_groups=sum(g['source_diagnosis']==diagnosis and g['cohort']=='PRIMARY_COMPLETE8' for g in groups),
        confirmed_positions=sum(len(g['confirmed_native_indices']) for g in groups if g['source_diagnosis']==diagnosis)) for diagnosis in ('COVID-19','CAP','Normal')}
    relation=lambda g: ('SOURCE_POSITIVE_' if g['original_BAG_source_label']['class_id']==1 else 'SOURCE_NEGATIVE_')+('PRED_POSITIVE' if g['original_BAG_prediction']==1 else 'PRED_NEGATIVE')
    bag_strata={key:dict(source_groups=sum(relation(g)==key for g in groups),
        primary_paired_groups=sum(relation(g)==key and g['cohort']=='PRIMARY_COMPLETE8' for g in groups),
        confirmed_positions=sum(len(g['confirmed_native_indices']) for g in groups if relation(g)==key),
        confirmed_known_reference_sampling_omission_groups=sum(g['known_reference_sampling_omission'] is True for g in groups if relation(g)==key))
        for key in ('SOURCE_POSITIVE_PRED_POSITIVE','SOURCE_POSITIVE_PRED_NEGATIVE','SOURCE_NEGATIVE_PRED_POSITIVE','SOURCE_NEGATIVE_PRED_NEGATIVE')}
    return dict(schema='R103_SLICE_CORRESPONDENCE_RESULT_V1',status='DONE' if counts['confirmed_positions'] else 'NO_CONFIRMED_REFERENCE_DENOMINATOR',
        registry_denominators=counts,groups=groups,macro_by_cohort=aggregate,source_diagnosis_denominators=strata,
        original_argmax_macro_separate_by_target_class=original_by_target,BAG_weak_source_label_prediction_strata=bag_strata,
        three_COVID_FN_posthoc=[g for g in groups if g['original_COVID_FN']],primary_score=policy['primary_score'],protocol=policy,
        medical_interpretation='descriptive within-source-group slice correspondence only; no160-independent-patient or pixel-localization claim',
        actual_computation=dict(model_forward=0,backward=0,updates=0,feature_arithmetic=0,JSON_score_identity_checks=20,
            score_metric_group_evaluations=sum(bool(g['scores']) for g in groups),ranking_metric_targets_per_evaluable_group=5),
        clinical_patient_independence='UNKNOWN',pretraining_overlap='UNKNOWN')
