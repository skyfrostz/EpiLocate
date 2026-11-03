"""Generated IDs/features only, no CT-FM load, classifier fit or optimizer."""

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[3]
import copy
import itertools
import json
from pathlib import Path

import numpy as np
import pytest

from epi_next import ctfm_weak_case_contract as contract
from epi_next.encoder_offline_review_v3 import linear_head_oracle


@pytest.fixture
def manifest():
    rows=[]
    for i,(split,source) in enumerate(itertools.product(('train_weak','val_classification'),('COVID','CAP','Normal')),1):
        rows.append(dict(patient_group_id='SYN-P%d'%i,study_key='SYN-ST%d'%i,series_key='SYN-SE%d'%i,
            source_diagnosis=source,task_label=0 if source=='Normal' else 1,label_provenance_sha='%064x'%(i+10),
            weak_label_level='DATA_VALIDATED_SOURCE_CASE_CLASS',split=split,complete_selected_series=True,
            series_selection_sha='%064x'%(i+20),study_imaging_finding=None,input_sha='%064x'%i,
            geometry_sha='%064x'%(i+30)))
    return dict(schema=contract.SCHEMA,task=contract.TASK,dataset_id='COVID-CT-MD',
        dataset_version='SYNTHETIC-NOT-RELEASED',data_manifest_sha='a'*64,split_manifest_sha='b'*64,
        task_definition_sha='c'*64,patient_equivalence_status='DATA_LOCKED_PATIENT_GROUPS',
        pretraining_overlap_status='unknown',rows=rows)


@pytest.fixture
def spatial(manifest):
    return {row['patient_group_id']:dict(features=np.full((1,512,4,4,4),i,np.float32),
        coverage_version=contract.COVERAGE,input_sha=row['input_sha'],geometry_sha=row['geometry_sha'])
        for i,row in enumerate(manifest['rows'])}


def test_consumer_accepts_data_weak_source_labels_and_no_labels_reach_encoder(manifest,monkeypatch):
    monkeypatch.setattr(Path,'open',lambda *args,**kwargs:pytest.fail('contract must not read any files/GT'))
    result=contract.validate_manifest(manifest);requests=contract.encoder_requests(manifest)
    assert result['patients']==6 and result['counts']['train_weak']==dict(COVID=1,CAP=1,Normal=1)
    assert len(requests)==6 and all('task_label' not in r and 'source_diagnosis' not in r for r in requests)
    assert all(r['shape']==[1,1,64,64,64] for r in requests)


@pytest.mark.parametrize('field',['mask_path','gt_path','source_folder','acquisition_date','localization_reference'])
def test_gt_and_shortcut_fields_rejected_even_if_null(manifest,field):
    manifest['rows'][0][field]=None
    with pytest.raises(ValueError,match='UNEXPECTED_FIELDS'):contract.validate_manifest(manifest)


def test_cap_negative_or_visible_lesion_claim_rejected(manifest):
    manifest['rows'][1]['task_label']=0
    with pytest.raises(ValueError,match='NO_CAP_NEGATIVE'):contract.validate_manifest(manifest)
    manifest['rows'][1]['task_label']=1;manifest['rows'][1]['study_imaging_finding']='VISIBLE_LESION'
    with pytest.raises(ValueError,match='NO_IMAGING_GT'):contract.validate_manifest(manifest)


@pytest.mark.parametrize('role',['dev_localization','test_localization','sealed','unknown'])
def test_nonclassification_roles_never_enter_fit_or_cache(manifest,role):
    manifest['rows'][3]['split']=role
    with pytest.raises(ValueError,match='SPLIT_FORBIDDEN'):contract.validate_manifest(manifest)


def test_cross_split_patient_or_series_duplicate_and_unresolved_groups_rejected(manifest):
    duplicate=copy.deepcopy(manifest);duplicate['rows'][3]['patient_group_id']=duplicate['rows'][0]['patient_group_id']
    with pytest.raises(ValueError,match='DISTINCT_PATIENT'):contract.validate_manifest(duplicate)
    duplicate=copy.deepcopy(manifest);duplicate['rows'][3]['series_key']=duplicate['rows'][0]['series_key']
    with pytest.raises(ValueError,match='DISTINCT_PATIENT'):contract.validate_manifest(duplicate)
    manifest['patient_equivalence_status']='UNKNOWN'
    with pytest.raises(ValueError,match='PATIENT_GROUPS'):contract.validate_manifest(manifest)


def test_source_splits_map_explicitly_and_patient_weights_ignore_feature_cell_counts(manifest,spatial):
    payload=contract.patient_payload(manifest,spatial)
    assert payload['features'].shape==(6,512) and np.array_equal(payload['features'][:,0],np.arange(6))
    assert payload['splits']==['train']*3+['observed_validation']*3
    assert payload['source_splits']==['train_weak']*3+['val_classification']*3
    assert payload['split_manifest_sha']==manifest['split_manifest_sha']
    assert np.allclose(payload['patient_loss_weights'],[1/3]*3+[0]*3) and not payload['training_performed']


def test_training_statistics_ignore_extreme_validation_values(manifest,spatial):
    for row in manifest['rows'][3:]:spatial[row['patient_group_id']]['features'].fill(1e9)
    stats=contract.train_standardization_control(contract.patient_payload(manifest,spatial))
    assert np.allclose(stats['mean'],1) and np.allclose(stats['scale'],np.std([0.,1.,2.],ddof=0))
    assert stats['fit_patient_ids']==['SYN-P1','SYN-P2','SYN-P3'] and not stats['classifier_fitted']


def test_partial_center_features_or_hash_drift_cannot_be_case_vector(manifest,spatial):
    record=spatial['SYN-P1'];record['coverage_version']='CENTER_ONLY'
    with pytest.raises(ValueError,match='FULL_FOV64'):contract.patient_payload(manifest,spatial)
    record['coverage_version']=contract.COVERAGE;record['input_sha']='e'*64
    with pytest.raises(ValueError,match='BINDING_MISMATCH'):contract.patient_payload(manifest,spatial)


def test_generated_full_fov_geometry_edges_inverse_and_spacing():
    native=(80,112,160);g=contract.full_fov_geometry(native,np.eye(4),[2.,1.,.5])
    matrix=np.array(g['model_to_native']);inverse=np.array(g['native_to_model'])
    edges=np.array([[*p,1] for p in itertools.product([-.5,63.5],repeat=3)]).T
    expected=np.array([[*p,1] for p in itertools.product(*[[-.5,n-.5] for n in native])]).T
    assert np.max(np.abs(matrix@edges-expected))<1e-12
    assert np.max(np.abs(inverse@matrix@edges-edges))<1e-12
    assert np.allclose(g['effective_spacing_spl_mm'],[2.5,1.75,1.25]) and g['crop']=='NONE'


def test_new_identity_reuses_existing_cache_with_coverage_split_and_version_binding(manifest,spatial,tmp_path):
    import torch
    from epi_next.encoder import FeatureCache, feature_cache_key
    metadata=contract.cache_identity(manifest,manifest['rows'][0],model_sha='d'*64,preprocess_sha='e'*64,
                                    config_sha='f'*64,code_sha='1'*40)
    key=feature_cache_key(metadata);cache=FeatureCache(tmp_path/'generated-cache')
    values=torch.from_numpy(spatial['SYN-P1']['features'])
    assert cache.write(metadata,values)==key and torch.equal(cache.read(metadata),values)
    assert metadata['source_split']=='train_weak' and metadata['split']=='train'
    for field,value in [('aggregation_version','other'),('coverage_version','CENTER_ONLY'),
                        ('dataset_version','other'),('split_manifest_sha','2'*64)]:
        changed=dict(metadata,**{field:value});assert feature_cache_key(changed)!=key
        with pytest.raises(FileNotFoundError):cache.read(changed)
    with np.load(tmp_path/'generated-cache'/(key+'.npz'),allow_pickle=False) as loaded:
        payload=json.loads(loaded['metadata'].tobytes());array=loaded['features'].copy()
    array[0,0,0,0,0]+=1
    np.savez(tmp_path/'generated-cache'/(key+'.npz'),features=array,
             metadata=np.frombuffer(json.dumps(payload).encode(),dtype=np.uint8))
    with pytest.raises(ValueError,match='mismatch'):cache.read(metadata)


def test_generated_fixed_coefficients_cam_preserves_logits_not_fitted_head():
    features=np.arange(512*64,dtype=np.float32).reshape(1,512,4,4,4)/1000
    result=linear_head_oracle(features,np.ones(512),np.full(512,2),np.stack([np.ones(512),-np.ones(512)]),np.array([.1,.2]))
    assert np.allclose(result['logits'],result['reconstructed_logits'])
    assert result['class_prediction'].shape==(1,) and not result['clinical_label_or_fitted_head']


def test_shared_record_projection_to_verified_cache_payload_and_mixed_identity_rejection(tmp_path):
    import hashlib
    import torch
    from epi_next.encoder import FeatureCache
    path=Path(str(_PUBLIC_ROOT / '.local/phase2/data-alignment-v1-20261010/evidence/record_schema_v1.json'))
    raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==contract.DATA_SCHEMA_SHA
    records=[];prepared={}
    for i,(split,source) in enumerate(itertools.product(('train_weak','val_classification'),('COVID-19','CAP','Normal')),1):
        series='SYN-SERIES-%d'%i;image_sha='%064x'%i
        records.append(dict(dataset_id='COVID-CT-MD',version='SYNTHETIC-NOT-RELEASED',patient_group_id='SYN-P%d'%i,
            patient_group_status='VERIFIED',study_key='SYN-STUDY-%d'%i,series_key=series,
            source_diagnosis=dict(value=source,original_value=source,provenance=dict(source_url=None,
                evidence_ref='SYNTHETIC_ONLY',verification='VERIFIED')),
            study_imaging_finding='UNKNOWN',task_label=0 if source=='Normal' else 1,
            label_definition_id='MD_SOURCE_DIAGNOSIS_WEAK_V1',split=split,image_ref='SYNTHETIC_NOT_A_PATH',
            image_sha256=image_sha,image_missing_reason=None,access_status='APPROVED_EXACT_SCOPE',geometry_qa='PASS'))
        prepared[series]=dict(source_image_sha256=image_sha,coverage_version=contract.COVERAGE,
            complete_selected_series=True,series_selection_sha='%064x'%(i+10),input_sha='%064x'%(i+20),geometry_sha='%064x'%(i+30))
    options=dict(shared_schema_raw=raw,shared_schema_sha=contract.DATA_SCHEMA_SHA,data_manifest_sha='a'*64,
        split_manifest_sha='b'*64,task_definition_sha='c'*64,pretraining_overlap_status='unknown')
    manifest=contract.project_data_records(records,prepared,**options)
    assert manifest['rows'][0]['source_diagnosis']=='COVID' and manifest['rows'][0]['study_imaging_finding'] is None
    for state in ('unknown','verified_disjoint','overlap_found'):
        assert contract.project_data_records(records,prepared,**dict(options,pretraining_overlap_status=state))['pretraining_overlap_status']==state
    cache=FeatureCache(tmp_path/'generated-cache');identity=dict(model_sha='d'*64,preprocess_sha='e'*64,config_sha='f'*64,code_sha='1'*40)
    for i,row in enumerate(manifest['rows']):
        metadata=contract.cache_identity(manifest,row,**identity)
        cache.write(metadata,torch.full((1,512,4,4,4),float(i)))
    payload=contract.cached_patient_payload(manifest,cache,**identity)
    assert payload['features'].shape==(6,512) and payload['model_sha']==identity['model_sha']
    assert payload['source_splits']==['train_weak']*3+['val_classification']*3 and payload['splits']==['train']*3+['observed_validation']*3
    assert payload['cache_identity_validation']=='EXISTING_FEATURE_CACHE_READ_FOR_EACH_EXACT_IDENTITY'
    with pytest.raises(FileNotFoundError):contract.cached_patient_payload(manifest,cache,**dict(identity,model_sha='2'*64))
    with pytest.raises(ValueError,match='READER_REQUIRED'):contract.cached_patient_payload(manifest,object(),**identity)
    missing=copy.deepcopy(records);missing[0].update(image_ref=None,image_sha256=None,image_missing_reason='NOT_ACQUIRED')
    with pytest.raises(ValueError,match='NOT_READY'):contract.project_data_records(missing,prepared,**options)
    extra=copy.deepcopy(records);extra[0]['mask']=None
    with pytest.raises(ValueError,match='GT_BOUNDARY'):contract.project_data_records(extra,prepared,**options)
    excluded=copy.deepcopy(records);excluded[0]['split']='dev_localization'
    with pytest.raises(ValueError,match='ONLY_DATA_VALIDATED'):contract.project_data_records(excluded,prepared,**options)
