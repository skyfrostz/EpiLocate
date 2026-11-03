"""Versioned evaluation registry from normalized, source-bound metadata only.
No CSV/NPY/DICOM loading and no training/sampling/model interface.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from . import slice_evaluation_registry as strict

SCHEMA='MEDICAL_SLICE_EVALUATION_REGISTRY_V2'
STATES=('PAIRED','PARTIALLY_PAIRED','UNKNOWN','CONFLICT')


def unknown(group,reason='PAIRING_NOT_RUN'):
    return {'source_group_id':group['source_group_id'],'record_id':group['record_id'],
            'source_diagnosis':group['source_diagnosis'],'split':group['split'],
            'depth':group['depth'],'geometry_binding':group['geometry_binding'],
            'Index_row':None,'original_Label_Index':None,'label_index_base':None,'annotation_case_index':None,'label_file_version':None,
            'actual_effective_slice_count':None,'status':'UNKNOWN','reasons':[reason],
            'native_labels':[None]*group['depth'],'publisher_to_native_indices':None,
            'fixed8_native_indices':group['fixed8'],'fixed8_labels':[None]*8,
            'medical_evaluability':'UNKNOWN','reference_scope':'SLICE_INFECTION_ONLY_NOT_MASK',
            'reference_provenance':None,'is_development':group['split']=='val_classification',
            'is_original_COVID_FN':group.get('is_original_COVID_FN',False)}


def map_reference(group,reference):
    row=unknown(group)
    if reference.get('geometry_sha256')!=group['geometry_binding']['sha256']:
        row.update(status='CONFLICT',reasons=['GEOMETRY_SOURCE_BINDING_MISMATCH']);return row
    if reference.get('source_diagnosis')!=group['source_diagnosis']:
        row.update(status='CONFLICT',reasons=['SOURCE_DIAGNOSIS_MISMATCH']);return row
    if reference.get('version_applicability') not in ('VERIFIED_CURRENT','ORIGINAL_VERSION_EXPLICIT_SCOPE'):
        row['reasons']=['LABEL_VERSION_UNRESOLVED'];return row
    try:
        index=reference['original_Label_Index'];base=reference['label_index_base']
        case=reference['annotation_case_index'];ir=reference['Index_row']
        strict.require(type(base) is int and base in (0,1) and type(index) is int
                       and type(case) is int and index-base==case and case>=0
                       and type(ir) is int and ir>=0,'INDEX_BASE_OR_ROW_UNPROVEN')
        evidence=reference['evidence'];labels=reference['labels_publisher_domain']
        strict.require(len(labels)==group['depth'],'LABEL_LENGTH_MISMATCH_NO_GUESS')
        valid=reference['declared_valid_publisher_indices']
        strict.require(len(valid)==len(set(valid)) and all(type(x) is int and 0<=x<group['depth'] for x in valid),
                       'VALID_SOURCE_DOMAIN_UNPROVEN')
        strict.require(all(value is None for i,value in enumerate(labels) if i not in set(valid)),
                       'UNDECLARED_DOMAIN_LABEL')
        strict.require(reference['range_policy'] in ('EXPLICIT_PUBLISHER_EXTENT','COMPLETE_SOURCE_MEMBER_ORDINAL_DOMAIN'),
                       'EXTENT_UNPROVEN')
        paired=strict.build_registry([group],[{'source_group_id':group['source_group_id'],
            'annotation_case_index':case}],[{'annotation_case_index':case,
            'coverage':'FULL_SELECTED_STACK_EXPLICIT','labels':labels}],evidence)['rows'][0]
        known=group['depth']-paired['scan_unknown']
        state='PAIRED' if known==group['depth'] else ('PARTIALLY_PAIRED' if known else 'UNKNOWN')
        row.update(status=state,reasons=[] if known else ['ALL_REFERENCE_LABELS_UNKNOWN'],
                   Index_row=ir,original_Label_Index=index,label_index_base=base,annotation_case_index=case,label_file_version=reference['label_file_version'],
                   actual_effective_slice_count=len(valid),native_labels=paired['slice_labels_native_order'],
                   publisher_to_native_indices=paired['publisher_to_native_indices'],
                   fixed8_labels=paired['fixed8_labels'],medical_evaluability='SLICE_LEVEL' if known else 'UNKNOWN',
                   reference_provenance=evidence,range_policy=reference['range_policy'],
                   array_tail_policy='OUTSIDE_SOURCE_MEMBER_DOMAIN_UNKNOWN_NOT_NORMAL')
        return row
    except (KeyError,TypeError,strict.MappingRejected) as exc:
        reason=str(exc) if isinstance(exc,strict.MappingRejected) else 'REFERENCE_SCHEMA_MISSING_OR_INVALID'
        # Missing evidence is UNKNOWN; explicit contradictory data is CONFLICT.
        conflict=any(x in reason for x in ('DUPLICATE','MISMATCH','UNDECLARED','INVALID_LABEL'))
        row.update(status='CONFLICT' if conflict else 'UNKNOWN',reasons=[reason]);return row


def build_registry(metadata,references=None,*,purpose='evaluation'):
    strict.require(purpose=='evaluation','EVALUATION_ONLY')
    groups=metadata['groups'];strict.unique(groups,'source_group_id');strict.unique(groups,'record_id')
    for g in groups:
        strict.require(type(g['depth']) is int and g['depth']>=8,'INVALID_DEPTH')
        strict.require(g['fixed8']==[int((j+.5)*g['depth']/8) for j in range(8)],'FIXED8_CHANGED')
        strict.require(g['split'] in ('train_weak','val_classification') and strict.bound(g['geometry_binding']),
                       'FIXED_GROUP_BINDING_REQUIRED')
    refs=references or {'status':'NOT_RUN','rows':[]};byid={};conflicts=set()
    allowed={g['source_group_id'] for g in groups};indices={}
    for r in refs['rows']:
        gid=r['source_group_id'];strict.require(gid in allowed,'REFERENCE_OUTSIDE_FIXED_SCOPE')
        if gid in byid:conflicts.add(gid)
        byid[gid]=r
        key=r.get('annotation_case_index')
        if key is not None:
            if key in indices:conflicts.update((gid,indices[key]))
            indices[key]=gid
    rows=[]
    for g in groups:
        row=map_reference(g,byid[g['source_group_id']]) if g['source_group_id'] in byid else unknown(g,
            'NO_CONFIRMED_REFERENCE' if refs['status']=='EXECUTED' else 'PAIRING_NOT_RUN')
        if g['source_group_id'] in conflicts:row.update(status='CONFLICT',reasons=['DUPLICATE_REFERENCE_IDENTITY'])
        if row['status'] in ('UNKNOWN','CONFLICT'):row['fixed8_labels']=[None]*8;row['native_labels']=[None]*g['depth'];row['medical_evaluability']='UNKNOWN'
        rows.append(row)
    def counts(selected):
        ready=[r for r in selected if r['status'] in ('PAIRED','PARTIALLY_PAIRED')]
        not_run=refs['status']!='EXECUTED'
        return {'source_groups':len(selected),'state_counts':{s:sum(r['status']==s for r in selected) for s in STATES},
                'pairing_execution':'NOT_RUN' if not_run else 'EXECUTED',
                'confirmed_evaluable_groups':None if not_run else len(ready),
                'confirmed_evaluable_native_positions':None if not_run else sum(v is not None for r in ready for v in r['native_labels']),
                'confirmed_evaluable_fixed8_positions':None if not_run else sum(v is not None for r in ready for v in r['fixed8_labels']),
                'unknown_fixed8_positions':sum(v is None for r in selected for v in r['fixed8_labels'])}
    strict.require(refs['status'] in ('NOT_RUN','EXECUTED'),'REFERENCE_EXECUTION_STATUS_REQUIRED')
    strict.require(refs['status']=='EXECUTED' or not refs['rows'],'NOT_RUN_CANNOT_CONTAIN_PAIRING_RESULTS')
    return {'schema':SCHEMA,'purpose':'evaluation','forbidden_uses':['training','slice_selection','ROI','threshold_selection'],
            'metadata_binding':metadata.get('bindings'),'rows':rows,'all60':counts(rows),
            'development20':counts([r for r in rows if r['is_development']]),
            'original_COVID_FN':counts([r for r in rows if r['is_original_COVID_FN']]),
            'clinical_patient_independence':'UNKNOWN','pretraining_overlap':'UNKNOWN',
            'pixel_or_voxel_reference':'NOT_PROVIDED_BY_SLICE_LABELS'}


def validate_registry(registry):
    if registry.get('schema')!=SCHEMA or registry.get('purpose')!='evaluation':raise ValueError('REGISTRY_VERSION_OR_PURPOSE')
    strict.unique(registry['rows'],'source_group_id');strict.unique(registry['rows'],'record_id')
    for r in registry['rows']:
        if r['status'] not in STATES:raise ValueError('REGISTRY_STATE')
        if len(r['fixed8_labels'])!=8 or len(r['native_labels'])!=r['depth']:raise ValueError('REGISTRY_LENGTH')
        if any(v is not None and (type(v) is not int or v not in (0,1)) for v in r['native_labels']):raise ValueError('REGISTRY_LABEL')
        if r['status'] in ('UNKNOWN','CONFLICT') and any(v is not None for v in r['native_labels']+r['fixed8_labels']):raise ValueError('UNKNOWN_CANNOT_BE_NORMAL')
        if r['fixed8_native_indices']!=[int((j+.5)*r['depth']/8) for j in range(8)]:raise ValueError('REGISTRY_FIXED8')
        if r['fixed8_labels']!=[r['native_labels'][i] for i in r['fixed8_native_indices']]:raise ValueError('REGISTRY_SAMPLE_LABEL_MISMATCH')
        known=sum(v is not None for v in r['native_labels'])
        if r['status']=='PAIRED' and known!=r['depth']:raise ValueError('PAIRED_REQUIRES_COMPLETE_REFERENCE')
        if r['status']=='PARTIALLY_PAIRED' and not 0<known<r['depth']:raise ValueError('PARTIAL_REQUIRES_KNOWN_AND_UNKNOWN')
        if r['status'] in ('PAIRED','PARTIALLY_PAIRED'):
            evidence=r['reference_provenance']
            if not evidence or not all(strict.bound(evidence.get(k)) for k in ('index','labels','publisher_order','index_base','version','row_extent','source_subject_binding')):
                raise ValueError('MISSING_REFERENCE_PROVENANCE')
        if not strict.bound(r['geometry_binding']):raise ValueError('REGISTRY_GEOMETRY_BINDING')
    for key,selected in (('all60',registry['rows']),('development20',[r for r in registry['rows'] if r['split']=='val_classification']),('original_COVID_FN',[r for r in registry['rows'] if r['is_original_COVID_FN']])):
        summary=registry[key];ready=[r for r in selected if r['status'] in ('PAIRED','PARTIALLY_PAIRED')]
        if summary['source_groups']!=len(selected) or summary['state_counts']!={s:sum(r['status']==s for r in selected) for s in STATES}:raise ValueError('REGISTRY_SUMMARY_DRIFT')
        if summary['unknown_fixed8_positions']!=sum(v is None for r in selected for v in r['fixed8_labels']):raise ValueError('REGISTRY_UNKNOWN_DENOMINATOR')
        expected=[len(ready),sum(v is not None for r in ready for v in r['native_labels']),sum(v is not None for r in ready for v in r['fixed8_labels'])]
        actual=[summary[k] for k in ('confirmed_evaluable_groups','confirmed_evaluable_native_positions','confirmed_evaluable_fixed8_positions')]
        if summary['pairing_execution']=='NOT_RUN':
            if ready or actual!=[None]*3:raise ValueError('NOT_RUN_DENOMINATOR_MUST_BE_NULL')
        elif summary['pairing_execution']!='EXECUTED' or actual!=expected:raise ValueError('REGISTRY_EVALUATION_DENOMINATOR')
    return True



def export_development_view(result,metadata,consumer,fixed8_control,parent_binding,producer_sha):
    """Exact ENC R103_SLICE_REFERENCE_REGISTRY_V1 view of the same producer."""
    validate_registry(result)
    meta={g['record_id']:g for g in metadata['groups']};rows_by_id={r['record_id']:r for r in result['rows']}
    ids=metadata['development_record_ids'];rows=[]
    for rid in ids:
        row=rows_by_id[rid];group=meta[rid];labels=row['fixed8_labels'];state=row['status']
        provenance=None
        if state in ('PAIRED','PARTIALLY_PAIRED'):
            ev=row['reference_provenance']
            def compact(r):return {'path':r['path'],'sha256':r['sha256']}
            provenance={'index':compact(ev['index']),'label_file':compact(ev['labels']),
                'version_evidence':compact(ev['version']),'order_evidence':compact(ev['publisher_order']),
                'extent_evidence':compact(ev['row_extent']),'member_mapping':compact(ev['member_mapping']),
                'index_row_zero_based':row['Index_row'],'label_index_raw':row['original_Label_Index'],
                'label_index_base':row['label_index_base'],'label_version':row['label_file_version'],
                'ordering_confirmed':True,'extent_confirmed':True,'source_identity_confirmed':True}
        scan={'positive':sum(v==1 for v in row['native_labels']),
              'negative':sum(v==0 for v in row['native_labels']),
              'unknown':sum(v is None for v in row['native_labels'])}
        rows.append({'record_id':rid,'source_group_id':row['source_group_id'],'source_diagnosis':row['source_diagnosis'],
            'split':row['split'],'fixed8_native_indices':row['fixed8_native_indices'],'native_depth':row['depth'],
            'native_geometry_reference':group['geometry_binding'],'native_tensor_sha256':group['native_tensor_SHA'],
            'mapping_status':state,'reason':';'.join(row['reasons']), 'fixed8_labels':labels,
            'confirmed_positions':[v is not None for v in labels],'scan_reference_counts':scan,
            'effective_length':row['actual_effective_slice_count'],'provenance':provenance})
    return {'schema':'R103_SLICE_REFERENCE_REGISTRY_V1','purpose':'EVALUATION_ONLY',
        'reference_scope':'SLICE_INFECTION_NOT_PIXEL_MASK','pairing_execution':result['development20']['pairing_execution'],
        'consumer':consumer,'fixed8_control':fixed8_control,'rows':rows,
        'denominators':{'source_groups':len(rows),'paired_groups':sum(r['mapping_status']=='PAIRED' for r in rows),
            'partially_paired_groups':sum(r['mapping_status']=='PARTIALLY_PAIRED' for r in rows),
            'unknown_groups':sum(r['mapping_status']=='UNKNOWN' for r in rows),
            'conflict_groups':sum(r['mapping_status']=='CONFLICT' for r in rows),
            'confirmed_positions':sum(sum(r['confirmed_positions']) for r in rows)},
        'label_semantics':{'confirmed':True,'positive':'INFECTION_PRESENT','negative':'INFECTION_ABSENT'},
        'parent_registry':parent_binding,'producer_request_sha256':producer_sha,
        'usable_reference_denominator':result['development20']['confirmed_evaluable_fixed8_positions'],
        'source_identity_assertion_scope':'EXACT_GROUP_MEMBER_BINDING_NOT_DICOM_COMPLIANCE_OR_CLINICAL_IDENTITY',
        'clinical_patient_independence':'UNKNOWN','pretraining_overlap':'UNKNOWN'}


def bound_json(path,sha):
    p=Path(path)
    if p.suffix!='.json' or p.is_symlink() or p.stat().st_size>32*1024**2:raise ValueError('CONTROL_JSON_ONLY')
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('CONTROL_JSON_SHA_DRIFT')
    return json.loads(raw)


def main():
    p=argparse.ArgumentParser();p.add_argument('--metadata',required=True);p.add_argument('--sha256',required=True)
    p.add_argument('--references');p.add_argument('--references-sha256');p.add_argument('--output',required=True);a=p.parse_args()
    if bool(a.references)!=bool(a.references_sha256):raise ValueError('REFERENCE_SHA_REQUIRED')
    metadata=bound_json(a.metadata,a.sha256);references=bound_json(a.references,a.references_sha256) if a.references else None
    result=build_registry(metadata,references);validate_registry(result)
    raw=(json.dumps(result,indent=2,allow_nan=False)+'\n').encode()
    with Path(a.output).open('xb') as f:f.write(raw)
    print(json.dumps({'status':'REGISTRY_CONTROL_BUILT','schema':SCHEMA,'sha256':hashlib.sha256(raw).hexdigest(),
                      'all60':result['all60'],'development20':result['development20'],'original_COVID_FN':result['original_COVID_FN']}))


if __name__=='__main__':main()
