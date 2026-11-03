"""Holdout qualification of metadata only; never imports/executes a model."""
from .r103_slice_evaluation import require,reference


def validate_holdout_manifest(manifest,control,identity,expected_count,*,identity_reference):
    require(identity['schema']=='R103_FROZEN_R18_IDENTITY_V1' and identity['K']==8 and identity['threshold']==.5,'FROZEN_CLASSIFIER_IDENTITY')
    require(type(expected_count) is int and expected_count>0,'EXACT_LOCKED_N_REQUIRED')
    require(manifest['schema']=='R103_HOLDOUT_SOURCE_MANIFEST_V1' and manifest['status']=='LOCKED_BEFORE_PREDICTIONS','PREPREDICTION_LOCK_REQUIRED')
    require(manifest['cohort_type'] in ('INTERNAL_SAME_SOURCE_HOLDOUT','EXTERNAL_CROSS_SOURCE_VALIDATION'),'DISTINCT_COHORT_SCOPE')
    source=manifest['source_dataset_id']
    require(isinstance(source,str) and source and (source==identity['training_source_dataset'])==(manifest['cohort_type']=='INTERNAL_SAME_SOURCE_HOLDOUT'),'INTERNAL_EXTERNAL_SOURCE_MUST_MATCH_SCOPE')
    require(reference(identity_reference) and manifest['classifier_identity']==identity_reference and manifest['threshold']==.5,'EXACT_CLASSIFIER_BINDING')
    require(reference(manifest['license_evidence']) and reference(manifest['label_definition_evidence']) and reference(manifest['overlap_audit']),'SOURCE_LABEL_LICENSE_OVERLAP_EVIDENCE')
    rows=manifest['rows'];require(len(rows)==expected_count,'DECLARED_LOCKED_N')
    old_ids={r['record_id'] for r in control['rows']};old_groups={r['source_group_id'] for r in control['rows']};old_hashes={r['native_tensor_sha256'] for r in control['rows']}
    require(len({r['record_id'] for r in rows})==len({r['source_group_id'] for r in rows})==len({r['native_tensor_sha256'] for r in rows})==expected_count,'UNIQUE_NEW_SOURCE_GROUPS')
    counts={name:0 for name in ('COVID-19','CAP','Normal')};known_patients=[]
    for r in rows:
        require(r['source_dataset_id']==source,'NO_MIXED_DATASET_COHORT')
        require(r['record_id'] not in old_ids and r['source_group_id'] not in old_groups and r['native_tensor_sha256'] not in old_hashes,'NO_PRIOR60_OR_KNOWN_HASH_REUSE')
        require(r['not_used_for_training_validation_explanation_selection'] is True and r['native_QA']=='QUALIFIED_BOUND_GEOMETRY_HU','NEW_GROUP_ELIGIBILITY')
        require(r['source_diagnosis'] in counts and type(r['task_label']) is int and r['task_label']==int(r['source_diagnosis']!='Normal'),'SOURCE_WEAK_LABEL_RULE')
        require(reference(r['geometry_reference']) and reference(r['native_tensor_reference']) and r['native_tensor_reference']['sha256']==r['native_tensor_sha256'],'NEW_INPUT_REFERENCE_ONLY')
        counts[r['source_diagnosis']]+=1
        if r['confirmed_patient_id'] is not None:known_patients.append(r['confirmed_patient_id'])
    require(len(known_patients)==len(set(known_patients)),'KNOWN_PATIENT_DUPLICATION')
    require(manifest['class_counts']==counts,'EXACT_CLASS_DENOMINATORS')
    require(manifest['clinical_patient_independence']=='UNKNOWN' and manifest['pretraining_overlap'] in ('UNKNOWN','KNOWN_OVERLAP','AUDITED_NO_KNOWN_OVERLAP'),'NO_UPGRADE_OF_UNKNOWN_BASELINE_PATIENT_INDEPENDENCE')
    return dict(status='QUALIFIED_METADATA_ONLY_NOT_RUN',cohort_type=manifest['cohort_type'],source_groups=expected_count,class_counts=counts,
                clinical_patient_independence=manifest['clinical_patient_independence'],pretraining_overlap=manifest['pretraining_overlap'],
                planned_backbone_batches=expected_count,planned_slice_positions=8*expected_count,planned_frozen_numpy_affine=expected_count,
                backward=0,updates=0,actual_model_calls=0)
