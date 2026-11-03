"""COVID-CT-MD consumer contracts; in-memory metadata/generated arrays only.

DATA owns label derivation, exact membership and split. No file reader, model,
optimizer, split generator or GT argument is present in this module.
"""
from __future__ import annotations
import hashlib
import json
import re

import numpy as np

TASK = 'COVIDCTMD_SOURCE_CASE_WEAK_BINARY_V1'
SCHEMA = 'CTFM_WEAK_CASE_CONSUMPTION_V1'
COVERAGE = 'SELECTED_COMPLETE_SERIES_FULL_FOV64_V1'
AGGREGATION = 'WHOLE_SERIES_LAST_STAGE_GAP512_V1'
CACHE_VERSION = 'CTFM_WEAK_CASE_SPATIAL_CACHE_V1'
DATA_SCHEMA_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
HASH_FIELDS = ('input_sha', 'model_sha', 'preprocess_sha', 'geometry_sha', 'config_sha',
               'split_manifest_sha', 'data_manifest_sha', 'task_definition_sha')
ROW_FIELDS = {'patient_group_id', 'study_key', 'series_key', 'source_diagnosis', 'task_label',
              'label_provenance_sha', 'weak_label_level', 'split', 'complete_selected_series',
              'series_selection_sha', 'study_imaging_finding',
              'input_sha', 'geometry_sha'}
TOP_FIELDS = {'schema', 'task', 'dataset_id', 'dataset_version', 'data_manifest_sha', 'split_manifest_sha',
              'task_definition_sha', 'patient_equivalence_status', 'pretraining_overlap_status', 'rows'}


def sha_value(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def require_hash(value, length=64):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{%d}'%length,value):
        raise ValueError('BOUND_HASH_REQUIRED')


def validate_manifest(manifest):
    if (set(manifest)!=TOP_FIELDS or manifest['schema']!=SCHEMA or manifest['task']!=TASK
            or manifest['dataset_id']!='COVID-CT-MD'
            or not isinstance(manifest['dataset_version'],str) or not manifest['dataset_version']
            or manifest['patient_equivalence_status']!='DATA_LOCKED_PATIENT_GROUPS'
            or manifest['pretraining_overlap_status'] not in ('unknown','verified_disjoint','overlap_found')):
        raise ValueError('DATA_CONSUMPTION_SCHEMA_OR_PATIENT_GROUPS_REQUIRED')
    for field in ('data_manifest_sha','split_manifest_sha','task_definition_sha'):
        require_hash(manifest[field])
    rows=manifest['rows']
    if not isinstance(rows,list) or not rows: raise ValueError('EXACT_ROWS_REQUIRED')
    patients, studies, series, inputs = set(),set(),set(),set()
    counts={s:{'COVID':0,'CAP':0,'Normal':0} for s in ('train_weak','val_classification')}
    for row in rows:
        if set(row)!=ROW_FIELDS: raise ValueError('UNEXPECTED_FIELDS_GT_OR_SHORTCUT_PATH_FORBIDDEN')
        for key,seen in (('patient_group_id',patients),('study_key',studies),('series_key',series),('input_sha',inputs)):
            if not isinstance(row[key],str) or not row[key] or row[key] in seen:
                raise ValueError('ONE_SELECTED_STUDY_SERIES_PER_DISTINCT_PATIENT_NO_DUPLICATE_INPUT')
            seen.add(row[key])
        if row['split'] not in counts: raise ValueError('TEST_SEALED_LOCALIZATION_OR_UNKNOWN_SPLIT_FORBIDDEN')
        if (row['source_diagnosis'] not in ('COVID','CAP','Normal')
                or type(row['task_label']) is not int or row['task_label'] not in (0,1)
                or row['task_label'] != {'COVID':1,'CAP':1,'Normal':0}[row['source_diagnosis']]
                or row['weak_label_level']!='DATA_VALIDATED_SOURCE_CASE_CLASS'):
            raise ValueError('DATA_WEAK_CLASS_RULE_MISMATCH_NO_CAP_NEGATIVE')
        if row['complete_selected_series'] is not True or row['study_imaging_finding'] is not None:
            raise ValueError('COMPLETE_SELECTED_SERIES_AND_NO_IMAGING_GT_TRAINING_FIELDS_REQUIRED')
        for key in ('input_sha','geometry_sha','series_selection_sha','label_provenance_sha'):
            require_hash(row[key])
        counts[row['split']][row['source_diagnosis']]+=1
    if not all(counts[s]['Normal'] and counts[s]['COVID']+counts[s]['CAP'] for s in counts):
        raise ValueError('BOTH_WEAK_CLASSES_REQUIRED_IN_TRAIN_AND_VAL')
    return dict(status='SCHEMA_PASS_NOT_ACCESS_OR_COMPUTE_AUTHORIZATION',patients=len(rows),counts=counts)


def encoder_requests(manifest):
    """Routing identities/hashes only; no label, category or GT reaches the encoder."""
    validate_manifest(manifest)
    return [dict(patient_group_id=r['patient_group_id'],study_key=r['study_key'],series_key=r['series_key'],
                 input_sha=r['input_sha'],geometry_sha=r['geometry_sha'],
                 series_selection_sha=r['series_selection_sha'],coverage_version=COVERAGE,
                 shape=[1,1,64,64,64],dtype='float32') for r in manifest['rows']]


def full_fov_geometry(native_shape, model_to_native_parent, spacing_spl_mm):
    """Generated-array geometry control, edge preserving all selected Series voxels."""
    shape=np.asarray(native_shape);spacing=np.asarray(spacing_spl_mm,dtype=np.float64)
    parent=np.asarray(model_to_native_parent,dtype=np.float64)
    if (shape.shape!=(3,) or shape.dtype.kind not in 'iu' or np.any(shape<=0)
            or spacing.shape!=(3,) or not np.isfinite(spacing).all() or np.any(spacing<=0)
            or parent.shape!=(4,4) or not np.isfinite(parent).all()
            or not np.allclose(parent[3],[0,0,0,1]) or abs(np.linalg.det(parent[:3,:3]))<1e-12):
        raise ValueError('FINITE_INVERTIBLE_COMPLETE_SERIES_GEOMETRY_REQUIRED')
    ratio=shape/64.;child=np.eye(4);child[:3,:3]=np.diag(ratio);child[:3,3]=.5*ratio-.5
    transform=parent@child
    return dict(coverage_version=COVERAGE,model_shape=[64,64,64],source_shape=shape.tolist(),
                model_to_native=transform.tolist(),native_to_model=np.linalg.inv(transform).tolist(),
                effective_spacing_spl_mm=(spacing*ratio).tolist(),crop='NONE',new_padding='NONE',
                resample='voxel_edge_preserving_volume_cell_average_after_frozen_HU_scaling',
                anatomical_completeness='DATA_MUST_CONFIRM_NO_INCOMPLETE_SERIES',
                small_lesion_retention='UNVALIDATED',nominal_feature_stride=16)


def cache_identity(manifest,row,*,model_sha,preprocess_sha,config_sha,code_sha):
    validate_manifest(manifest)
    if row not in manifest['rows']: raise ValueError('EXACT_MANIFEST_ROW_REQUIRED')
    value=dict(input_sha=row['input_sha'],model_sha=model_sha,preprocess_sha=preprocess_sha,
               geometry_sha=row['geometry_sha'],config_sha=config_sha,code_sha=code_sha,
               split_manifest_sha=manifest['split_manifest_sha'],split={'train_weak':'train',
               'val_classification':'observed_validation'}[row['split']],
               source_split=row['split'],
               data_manifest_sha=manifest['data_manifest_sha'],task_definition_sha=manifest['task_definition_sha'],
               dataset_id=manifest['dataset_id'],dataset_version=manifest['dataset_version'],patient_group_id=row['patient_group_id'],
               study_key=row['study_key'],series_key=row['series_key'],coverage_version=COVERAGE,
               aggregation_version=AGGREGATION,cache_version=CACHE_VERSION,
               input_shape=[1,1,64,64,64],feature_shape=[1,512,4,4,4],dtype='float32',
               series_selection_sha=row['series_selection_sha'])
    for key in HASH_FIELDS: require_hash(value[key])
    require_hash(value['code_sha'],40)
    return value


def validate_features(features,*,coverage_version):
    value=np.asarray(features)
    if (coverage_version!=COVERAGE or value.shape!=(1,512,4,4,4)
            or value.dtype!=np.float32 or not np.isfinite(value).all()):
        raise ValueError('FINITE_FP32_FULL_FOV64_LAST_STAGE_FEATURE_REQUIRED')
    return value


def patient_payload(manifest,spatial_by_patient):
    """Synthetic packing control only; real entry must use cached_patient_payload."""
    validate_manifest(manifest);rows=manifest['rows']
    if set(spatial_by_patient)!={r['patient_group_id'] for r in rows}: raise ValueError('EXACT_PATIENT_FEATURE_SET_REQUIRED')
    vectors=[]
    for row in rows:
        item=spatial_by_patient[row['patient_group_id']]
        if set(item)!={'features','coverage_version','input_sha','geometry_sha'}:
            raise ValueError('SPATIAL_FEATURE_CONSUMPTION_SCHEMA_REQUIRED')
        if item['input_sha']!=row['input_sha'] or item['geometry_sha']!=row['geometry_sha']:
            raise ValueError('FEATURE_INPUT_LEDGER_BINDING_MISMATCH')
        feature=validate_features(item['features'],coverage_version=item['coverage_version'])
        vectors.append(feature.mean(axis=(2,3,4),dtype=np.float64)[0].astype(np.float32))
    return dict(features=np.stack(vectors),labels=np.array([r['task_label'] for r in rows],dtype=np.int64),
                patient_ids=[r['patient_group_id'] for r in rows],splits=[{'train_weak':'train',
                'val_classification':'observed_validation'}[r['split']] for r in rows],
                patient_loss_weights=np.array([1/sum(r['split']=='train_weak' for r in rows)
                    if row['split']=='train_weak' else 0 for row in rows]),aggregation_version=AGGREGATION,
                source_splits=[r['split'] for r in rows],data_manifest_sha=manifest['data_manifest_sha'],
                split_manifest_sha=manifest['split_manifest_sha'],task_definition_sha=manifest['task_definition_sha'],
                target_semantics='SOURCE_CASE_CLASS_ONLY_VISIBLE_LESION_UNKNOWN',training_performed=False)


def cached_patient_payload(manifest,cache,*,model_sha,preprocess_sha,config_sha,code_sha):
    """Future cache-only entry: verify each exact identity before patient packing.

    No backbone or head runs here. Changing model/preprocess/config or any cache
    version cannot read a prior key; cache.read also validates stored identity
    and content hashes. DATA records and prepared-input hashes remain mandatory.
    """
    from .encoder import FeatureCache
    if not isinstance(cache,FeatureCache): raise ValueError('VERIFIED_FEATURE_CACHE_READER_REQUIRED')
    validate_manifest(manifest);products={};identities=[]
    for row in manifest['rows']:
        metadata=cache_identity(manifest,row,model_sha=model_sha,preprocess_sha=preprocess_sha,
                                config_sha=config_sha,code_sha=code_sha)
        features=cache.read(metadata).numpy()  # existing immutable NPZ identity/content validation
        validate_features(features,coverage_version=metadata['coverage_version'])
        products[row['patient_group_id']]=dict(features=features,coverage_version=metadata['coverage_version'],
                                              input_sha=metadata['input_sha'],geometry_sha=metadata['geometry_sha'])
        identities.append(sha_value(metadata))
    payload=patient_payload(manifest,products)
    payload.update(cache_identity_validation='EXISTING_FEATURE_CACHE_READ_FOR_EACH_EXACT_IDENTITY',
                   feature_cache_identity_sha256=identities,model_sha=model_sha,preprocess_sha=preprocess_sha,
                   config_sha=config_sha,code_sha=code_sha,cache_version=CACHE_VERSION)
    return payload


def project_data_records(records,preparations,*,shared_schema_raw,shared_schema_sha,
                         data_manifest_sha,split_manifest_sha,task_definition_sha,
                         pretraining_overlap_status):
    """Projection of DATA's fixed shared schema, never a split/label generator.

    Only already DATA-validated classification records plus independently bound
    complete-Series prepared-input metadata are accepted. No image_ref is opened.
    Null/unapproved assets fail NOT_READY; evaluation registry is never consumed.
    """
    if hashlib.sha256(shared_schema_raw).hexdigest()!=shared_schema_sha or shared_schema_sha!=DATA_SCHEMA_SHA:
        raise ValueError('FIXED_DATA_RECORD_SCHEMA_REQUIRED')
    shared_schema=json.loads(shared_schema_raw)
    if (shared_schema['schema_id']!='EPI_DATA_RECORD_V1'
            or shared_schema['owner']!='DATA' or shared_schema['version']!=1):
        raise ValueError('FIXED_DATA_RECORD_SCHEMA_REQUIRED')
    required=set(shared_schema['required_fields']);allowed=required|set(shared_schema['extra_fields'])
    rows=[];version=None
    for record in records:
        if not required.issubset(record) or set(record)-allowed:
            raise ValueError('DATA_RECORD_SCHEMA_OR_GT_BOUNDARY_MISMATCH')
        if (record['dataset_id']!='COVID-CT-MD' or record['split'] not in ('train_weak','val_classification')
                or record['label_definition_id']!='MD_SOURCE_DIAGNOSIS_WEAK_V1'):
            raise ValueError('ONLY_DATA_VALIDATED_MD_CLASSIFICATION_RECORDS')
        if (record['patient_group_status']!='VERIFIED' or not record['patient_group_id']
                or not record['study_key'] or not record['series_key']
                or record['access_status']!='APPROVED_EXACT_SCOPE' or record['geometry_qa']!='PASS'
                or not isinstance(record['image_ref'],str) or not record['image_ref']
                or not record['image_sha256'] or record['image_missing_reason'] is not None):
            raise ValueError('NOT_READY_GROUP_ASSET_ACCESS_OR_GEOMETRY')
        require_hash(record['image_sha256'])
        if version is not None and version!=record['version']: raise ValueError('MIXED_DATASET_VERSIONS')
        version=record['version'];diagnosis=record['source_diagnosis']
        if diagnosis['provenance']['verification']!='VERIFIED': raise ValueError('NOT_READY_SOURCE_LABEL_PROVENANCE')
        source={'COVID-19':'COVID','CAP':'CAP','Normal':'Normal'}.get(diagnosis['value'])
        if source is None: raise ValueError('SOURCE_CLASS_NOT_IN_FIXED_TASK')
        prepared=preparations[record['series_key']]
        if (set(prepared)!={'source_image_sha256','coverage_version','complete_selected_series',
                           'series_selection_sha','input_sha','geometry_sha'}
                or prepared['source_image_sha256']!=record['image_sha256']
                or prepared['coverage_version']!=COVERAGE or prepared['complete_selected_series'] is not True):
            raise ValueError('NOT_READY_BOUND_COMPLETE_SERIES_PREPARATION')
        # DATA supplied label is preserved and validated; it is never derived from GT/finding.
        rows.append(dict(patient_group_id=record['patient_group_id'],study_key=record['study_key'],
            series_key=record['series_key'],source_diagnosis=source,task_label=record['task_label'],
            label_provenance_sha=sha_value(diagnosis),weak_label_level='DATA_VALIDATED_SOURCE_CASE_CLASS',
            split=record['split'],complete_selected_series=True,series_selection_sha=prepared['series_selection_sha'],
            study_imaging_finding=None,input_sha=prepared['input_sha'],geometry_sha=prepared['geometry_sha']))
    manifest=dict(schema=SCHEMA,task=TASK,dataset_id='COVID-CT-MD',dataset_version=version,
        data_manifest_sha=data_manifest_sha,split_manifest_sha=split_manifest_sha,task_definition_sha=task_definition_sha,
        patient_equivalence_status='DATA_LOCKED_PATIENT_GROUPS',pretraining_overlap_status=pretraining_overlap_status,rows=rows)
    validate_manifest(manifest)
    return manifest


def train_standardization_control(payload):
    """Statistics only: train-only population std, no fitted classifier or selection."""
    values=payload['features'].astype(np.float64);mask=np.array([s=='train' for s in payload['splits']])
    if mask.sum()<2:raise ValueError('TRAIN_STATISTICS_REQUIRE_MULTIPLE_PATIENTS')
    return dict(mean=values[mask].mean(0),scale=np.maximum(values[mask].std(0,ddof=0),1e-6),
                fit_patient_ids=[p for p,m in zip(payload['patient_ids'],mask) if m],
                classifier_fitted=False)
