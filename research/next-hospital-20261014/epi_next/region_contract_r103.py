"""R103 metadata gates and generated-testable area-objective kernels.

No model/CT/GT loader, evaluation runner, dispatch, or changes to R92/HSPI.
"""
from __future__ import annotations
import copy
import math
import hashlib
import json

SCHEMA='EPI_NEXT_CONDITIONAL_REGION_R103_V1'
PIXEL_IDENTITY=('source_namespace','source_group_id','native_volume_sha256','series_uid',
                'sop_uid','native_z','native_geometry_sha256')
AREAS=(5,10,20)


def sha(value):
    if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('SHA256_REQUIRED')


def validate_contract(value):
    """Target/source/medical intent and current BAG baseline are distinct."""
    c=copy.deepcopy(value)
    if c.get('schema')!=SCHEMA or c.get('prediction_scope')!='BAG' or c.get('K')!=8:
        raise ValueError('EXPLICIT_K8_BAG_CONTRACT_REQUIRED')
    if c.get('function')!='FP32_GAP_CAST_FP64_MEAN_STANDARDIZED_AFFINE':
        raise ValueError('FROZEN_AFFINE_FUNCTION_REQUIRED')
    if c.get('class_labels')!=['Normal_SOURCE','COVID-19_OR_CAP_SOURCE']:
        raise ValueError('EXACT_SOURCE_CLASS_MAP_REQUIRED')
    for name in ('backbone_sha256','head_sha256','preprocessing_sha256','input_manifest_sha256'):
        sha(c['binding'][name])
    members=c['members'];changed=c['changed_members']
    if (len(members)!=8 or len(set(members))!=8 or any(not isinstance(m,str) or not m for m in members)
            or len(changed)!=1 or changed[0] not in members):
        raise ValueError('ONE_ORIGINAL_MEMBER_CHANGED_OTHER_SEVEN_FIXED')
    if c.get('unchanged_members')!=[m for m in members if m not in changed]:
        raise ValueError('SEVEN_UNCHANGED_MEMBERS_EXACT_ORDER_REQUIRED')
    baseline=c['baseline']
    if type(baseline.get('stage')) is not int or baseline['stage']<0:
        raise ValueError('BASELINE_STAGE_REQUIRED')
    expected='ORIGINAL_BAG' if baseline['stage']==0 else 'CURRENT_RESIDUAL_BAG'
    if baseline.get('kind')!=expected:raise ValueError('NO_STALE_ORIGINAL_BASELINE_AT_RESIDUAL_STAGE')
    sha(baseline['state_sha256'])
    z=baseline['logits']
    if (not isinstance(z,list) or len(z)!=2 or any(type(x) not in (int,float) or not math.isfinite(x) for x in z)):
        raise ValueError('FINITE_BINARY_FP64_LOGITS_REQUIRED')
    predicted=0 if z[0]>=z[1] else 1
    target=c['target'];policy=target.get('policy');declared=target.get('declared_class')
    if policy not in ('ORIGINAL_ARGMAX_FIXED','DECLARED_FIXED') or type(declared) is not int or declared not in (0,1):
        raise ValueError('EXPLICIT_FIXED_TARGET_REQUIRED')
    # ORIGINAL target uses original unperturbed bag, even at a later residual.
    original=c['original_prediction']
    oz=original.get('logits')
    if not isinstance(oz,list) or len(oz)!=2 or any(type(x) not in (int,float) or not math.isfinite(x) for x in oz):
        raise ValueError('ORIGINAL_FINITE_LOGITS_REQUIRED')
    sha(original['logits_sha256'])
    if hashlib.sha256(json.dumps(oz,separators=(',',':'),allow_nan=False).encode()).hexdigest()!=original['logits_sha256']:
        raise ValueError('ORIGINAL_LOGITS_SHA_MISMATCH')
    if original.get('class_id')!=(0 if oz[0]>=oz[1] else 1):raise ValueError('ORIGINAL_PREDICTION_LOGITS_MISMATCH')
    if type(original.get('class_id')) is not int or original['class_id'] not in (0,1):
        raise ValueError('ORIGINAL_PREDICTION_REQUIRED')
    if baseline['stage']==0 and original['class_id']!=predicted:raise ValueError('ORIGINAL_LOGITS_PREDICTION_MISMATCH')
    resolved=original['class_id'] if policy=='ORIGINAL_ARGMAX_FIXED' else declared
    if declared!=resolved or target.get('resolved_class')!=resolved:
        raise ValueError('DECLARED_RESOLVED_TARGET_MISMATCH')
    source=c.get('source_label')
    if source is not None:
        if source.get('scope')!='SOURCE_GROUP' or type(source.get('class_id')) is not int or source['class_id'] not in (0,1):
            raise ValueError('SOURCE_GROUP_WEAK_LABEL_ONLY')
        sha(source['provenance_sha256'])
    goal=c.get('medical_intent')
    if goal not in ('NORMAL_MODEL_RESPONSE','INFECTION_SOURCE_CATEGORY_RESPONSE','DIAGNOSTIC_MODEL_RESPONSE'):
        raise ValueError('EXPLICIT_MEDICAL_INTENT_REQUIRED')
    if (goal=='NORMAL_MODEL_RESPONSE' and resolved!=0) or (goal=='INFECTION_SOURCE_CATEGORY_RESPONSE' and resolved!=1):
        raise ValueError('TARGET_INTENT_MISMATCH')
    margin=z[resolved]-z[1-resolved]
    medical=c.get('medical_reference')
    if not isinstance(medical,dict) or set(medical)!={'input_identity','reference'}:
        raise ValueError('EXPLICIT_MEDICAL_REFERENCE_AVAILABILITY_REQUIRED')
    pairing=reference_eligibility(medical['input_identity'],medical['reference'])
    return dict(contract=c,predicted_class=predicted,original_predicted_class=original['class_id'],
        resolved_class=resolved,source_label_is_slice_truth=False,conditional_scope='one changed member, not a region alone explaining whole CT',
        infection_optimization_eligible=goal=='INFECTION_SOURCE_CATEGORY_RESPONSE' and margin>0,
        pixel_reference=pairing,infection_reference_association_eligible=goal=='INFECTION_SOURCE_CATEGORY_RESPONSE' and pairing['pixel_eligible'],
        display_label='Normal prediction response' if goal=='NORMAL_MODEL_RESPONSE' else 'Fixed source-category model response',
        infection_evidence_status='NOT_AN_INFECTION_EXPLANATION' if goal=='NORMAL_MODEL_RESPONSE' else 'NONPOSITIVE_MODEL_RESPONSE' if resolved==1 and margin<=0 else 'MODEL_RESPONSE_ONLY_NOT_CLINICAL_EVIDENCE',
        reliable_candidates=[],cpf='NOT_INHERITED_NOT_CALIBRATED',probability_semantics='uncalibrated model response, never infection/lesion probability')


def reference_eligibility(identity,reference):
    """No pixels opened. Pair eligibility only, never computes a GT metric."""
    if reference is None:return dict(status='UNKNOWN',pixel_eligible=False,reason='NO_REFERENCE_METADATA',background='UNKNOWN')
    if reference.get('kind')=='SLICE_01':
        return dict(status='SLICE_ONLY',pixel_eligible=False,reason='DOCTOR_SLICE_LABEL_IS_NOT_PIXEL_MASK',background='UNKNOWN')
    if reference.get('mapping_status') not in ('PAIRED','PARTIALLY_PAIRED'):
        return dict(status=reference.get('mapping_status','UNKNOWN'),pixel_eligible=False,reason='DATA_PAIRING_NOT_CONFIRMED',background='UNKNOWN')
    ri=reference.get('identity',{})
    if not isinstance(identity,dict):return dict(status='UNKNOWN',pixel_eligible=False,reason='NO_EXACT_INPUT_IDENTITY',background='UNKNOWN')
    if any(identity.get(k) is None or ri.get(k) is None for k in PIXEL_IDENTITY):
        return dict(status='UNKNOWN',pixel_eligible=False,reason='INCOMPLETE_EXACT_CASE_SERIES_SOP_GEOMETRY_IDENTITY',background='UNKNOWN')
    if any(identity[k]!=ri[k] for k in PIXEL_IDENTITY):
        return dict(status='CONFLICT',pixel_eligible=False,reason='NO_CROSS_PATIENT_SERIES_SOP_OR_NATIVE_Z_JOIN',background='UNKNOWN')
    if reference.get('kind') not in ('PARTIAL_POLYGON','DENSE_INFECTION_MASK') or reference.get('geometry_qa')!='PASS' or reference.get('medical_stratum')!='INFECTION_REFERENCE':
        return dict(status='UNKNOWN',pixel_eligible=False,reason='REFERENCE_TYPE_OR_STRATUM_OR_GEOMETRY_NOT_QUALIFIED',background='UNKNOWN')
    sha(reference['manifest_sha256'])
    complete=reference['kind']=='DENSE_INFECTION_MASK' and reference.get('annotation_completeness')=='CONFIRMED_COMPLETE'
    return dict(status='PAIRED' if complete else 'PARTIALLY_PAIRED',pixel_eligible=True,
        background='CONFIRMED_WITHIN_DECLARED_DENSE_DOMAIN' if complete else 'UNKNOWN',
        complete_Dice_IoU_FP_eligible=complete,polygon_count_semantics='reference objects, not independent3D lesions')


def area_count(valid_pixels,percent):
    if type(valid_pixels) is not int or valid_pixels<0 or percent not in AREAS:
        raise ValueError('FIXED_5_10_20_PERCENT_AND_VALID_COUNT_REQUIRED')
    return valid_pixels*percent//100


def hard_region(soft,valid,percent,*,straight_through=False):
    """Exact model-grid cardinality, stable row-major ties, no quota padding.

    STE has hard forward values and a BIASED soft derivative surrogate; it is
    not a mathematical derivative of top-k. No medical reliability criterion.
    """
    import torch
    if (soft.ndim!=2 or soft.shape!=valid.shape or soft.dtype!=torch.float32 or valid.dtype!=torch.bool
            or soft.device.type!='cpu' or valid.device.type!='cpu' or not torch.isfinite(soft).all()
            or not ((soft>=0)&(soft<=1)).all()):
        raise ValueError('FINITE_FP32_SOFT_AND_BOOL_VALID_GRID_REQUIRED')
    indices=torch.nonzero(valid.flatten(),as_tuple=False).flatten()
    k=area_count(len(indices),percent)
    order=torch.argsort(soft.flatten()[indices],descending=True,stable=True)
    hard=torch.zeros_like(soft).flatten();hard[indices[order[:k]]]=1;hard=hard.reshape_as(soft)
    weights=(soft+(hard-soft).detach())*valid if straight_through else hard
    return weights,dict(percent=percent,k=k,valid_pixels=len(indices),status='NONEMPTY' if k else 'EMPTY_NO_PADDING',reliable=False)


def loss_components(original,perturbed,k=8):
    """Single changed input only. Never deletes or rescales cached features."""
    from .conditional_bag_r92 import bag_losses
    old=bag_losses(original,perturbed,k)
    losses=dict(RAW_BAG_LS_R103_V1=old['RAW_BAG_LS_R92_V1'],K2_COMPONENT_LS_R103_V1=old['K2_COMPONENT_LS_R92_V1'])
    losses['delta_component_logits']=k*(perturbed-original)
    losses['delta_bag_logits']=perturbed-original
    return losses


def fixed_random_regions(valid):
    import numpy as np
    import torch
    if valid.dtype!=torch.bool or valid.ndim!=2 or valid.device.type!='cpu':raise ValueError('VALID_MODEL_GRID_REQUIRED')
    indices=np.flatnonzero(valid.numpy());order=np.random.Generator(np.random.PCG64(17)).permutation(indices)
    result={}
    for p in AREAS:
        region=torch.zeros_like(valid).flatten();region[order[:area_count(len(indices),p)]]=True
        result[p]=region.reshape_as(valid)
    return result


def planned_counts(translation_counts=(5,5,5),*,target_policy='ORIGINAL_ARGMAX_FIXED',target_class=0,controls_reused=True):
    if target_policy!='ORIGINAL_ARGMAX_FIXED' or target_class!=0 or controls_reused is not True:
        raise ValueError('NORMAL_REUSE_COUNT_PLAN_NOT_VALID_FOR_NEW_TARGET_OR_CONTROLS')
    if len(translation_counts)!=3 or any(type(n) is not int or not 0<=n<=5 for n in translation_counts):
        raise ValueError('THREE_FIXED_AREA_TRANSLATION_COUNTS_0_TO5')
    # baseline2 + optimization24 + final soft/hard9 + random6 + old peak2 =43
    f=43+2*sum(translation_counts)
    return dict(forward=f,encoded_samples=f+7,backward=24,mask_updates=24,model_updates=0,bag_aggregations=f+1)


def validate_counts(report,translation_counts=(5,5,5),*,success=False,target_policy='ORIGINAL_ARGMAX_FIXED',target_class=0,controls_reused=True):
    expected=planned_counts(translation_counts,target_policy=target_policy,target_class=target_class,controls_reused=controls_reused)
    for group in ('reserved','returned'):
        row=report[group]
        for k,cap in expected.items():
            if type(row.get(k)) is not int or not 0<=row[k]<=cap:raise ValueError('COUNTER_OR_BUDGET_INVALID:'+k)
    if any(report['returned'][k]>report['reserved'][k] for k in expected):raise ValueError('RETURNED_EXCEEDS_RESERVED')
    if (len(report['batch_sizes'])!=report['returned']['forward'] or sum(report['batch_sizes'])!=report['returned']['encoded_samples']
            or any(type(n) is not int or n<1 for n in report['batch_sizes'])):
        raise ValueError('BATCH_AND_SAMPLE_COUNTS_REQUIRED')
    if success:
        if report['reserved']!=expected or report['returned']!=expected or report.get('actual')!=expected:
            raise ValueError('SUCCESS_REQUIRES_COMPLETE_ACTUAL_COUNTS')
        if report['batch_sizes']!=[8]+[1]*(expected['forward']-1):raise ValueError('ONLY_CHANGED_INPUT_ENCODING_AFTER_K8_BASELINE')
    elif report.get('actual') is not None and report['actual']!=report['returned']:
        raise ValueError('KNOWN_ACTUAL_MUST_EQUAL_RETURNED')
    elif report['reserved']!=report['returned'] and report.get('actual') is not None:
        raise ValueError('FAILED_INFLIGHT_ACTUAL_MUST_REMAIN_UNKNOWN')
    return expected


REUSE_FIELDS=('backbone_sha256','head_sha256','preprocessing_sha256','input_manifest_sha256',
    'prepared_bag_sha256','member_id','baseline_state_sha256','target_policy','target_class',
    'valid_support_sha256','fill_policy','area_protocol_sha256','algorithm_source_sha256','runtime_lock_sha256')


def validate_reuse_metadata(saved,current):
    if any(k not in saved or k not in current or saved[k]!=current[k] for k in REUSE_FIELDS):
        raise ValueError('SAME_INPUT_TARGET_FUNCTION_AND_CONTROL_BINDING_REQUIRED_NO_FALLBACK')
    for k in REUSE_FIELDS:
        if k.endswith('sha256'):sha(saved[k])
    if saved['target_policy']!='ORIGINAL_ARGMAX_FIXED' or saved['target_class']!=0:
        raise ValueError('R102_NORMAL_CONTROL_CANNOT_BECOME_INFECTION_CONTROL')
    return dict(status='COMPATIBLE_BY_LOCKED_PROVENANCE',
        original_region_hash='not stored per R102 readout; require deterministic reconstruction from saved maps/tiles/Mask and original source/runtime, never invent hash',new_forward=0)


def validate_spec(value):
    if (value.get('schema')!='E2_AREA_CONSTRAINED_CANDIDATE_R103_V1' or value.get('status')!='SPEC_NOT_EXECUTABLE_NOT_APPROVED'
            or value.get('method')!='E2-AREA-CONSTRAINED-CANDIDATE'
            or value['primary_branch']['areas']!=list(AREAS) or value['primary_branch']['steps_per_area']!=8
            or value['primary_branch']['medical_intent']!='NORMAL_MODEL_RESPONSE'
            or value['limits']['max_forward']!=73 or value['limits']['max_backward']!=24
            or value['limits']['max_mask_updates']!=24 or value['limits']['model_updates']!=0
            or value['normal_branch']['counts_full']!=planned_counts()):
        raise ValueError('FIXED_R103_SPEC_REQUIRED_NO_REAL_EXECUTION')
    return dict(status='SPEC_VALID',real_executable=False,medical_evaluation_eligible=False,
        counts_scope='M0 same original Normal target and strictly reusable R102 controls only',limits=value['limits'])


def main():
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description='JSON-only validator; no model/GT evaluator or execution option')
    parser.add_argument('--kind',choices=('contract','spec','reference','counts'),required=True)
    parser.add_argument('--input',required=True);parser.add_argument('--sha',required=True)
    a=parser.parse_args();p=Path(a.input)
    if not p.is_absolute() or p.suffix!='.json' or p.is_symlink() or p.stat().st_size>16*1024**2:
        raise ValueError('BOUND_JSON_METADATA_ONLY')
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=a.sha:raise ValueError('INPUT_METADATA_SHA')
    value=json.loads(raw)
    if a.kind=='spec':result=validate_spec(value)
    elif a.kind=='contract':
        result=validate_contract(value);result={k:v for k,v in result.items() if k!='contract'}
    elif a.kind=='reference':result=reference_eligibility(value['identity'],value['reference'])
    else:result=validate_counts(value['report'],value['translation_counts'],success=value['success'],
        target_policy=value['target_policy'],target_class=value['target_class'],controls_reused=value['controls_reused'])
    print(json.dumps(dict(mode='METADATA_VALIDATION_ONLY_NOT_REAL_EVALUATION',result=result),sort_keys=True))


if __name__=='__main__':main()
