"""Actual DATA pure producer/export -> actual ENC validator/evaluator.

All groups, geometry, evidence paths and labels here are generated. No medical
registry/file/array/model is read. DATA files are read as source only.
"""

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[3]
import hashlib
import importlib
import json
import os
import sys
import types
from pathlib import Path
import pytest
from epi_next.r103_slice_evaluation import evaluate,EvaluationRejected
from test_r103_slice_evaluation import fixture


DATA=Path(str(_PUBLIC_ROOT / 'research/next-hospital-20261014/epi_next'))


def data_producer():
    name='r103_generated_seam_data'
    if name not in sys.modules:
        package=types.ModuleType(name);package.__path__=[str(DATA)];sys.modules[name]=package
    return importlib.import_module(name+'.medical_slice_registry_v2')


def generated_inputs():
    scores,control,_,policy=fixture()
    for i in range(3,10):
        c=scores['cases'][i];margin=[v+1 for v in c['slice_component_margin']]
        c.update(slice_component_margin=margin,slice_component_logits=[[.5,.5+v] for v in margin],
            saved_raw_logits=[.5,1.],saved_bag_margin=.5,saved_predicted_class=1,saved_positive_probability=.6224593312)
        c['raw_class_terms']=[[v-c['effective_bias'][j] for j,v in enumerate(row)] for row in c['slice_component_logits']]
        c['weighted_class_terms']=[[v/8 for v in row] for row in c['raw_class_terms']]
    groups=[];references=[]
    for i,c in enumerate(control['rows']):
        groups.append(dict(source_group_id=c['source_group_id'],record_id=c['record_id'],source_diagnosis=c['source_diagnosis'],split=c['split'],
            depth=8,fixed8=list(range(8)),geometry_binding=c['native_geometry_reference'],native_tensor_SHA=c['native_tensor_sha256'],
            native_slices=[dict(native_index=j,member_key=f'GENERATED-{i}-{j}',ipp_normal_position=float(j),slice_location=float(j)) for j in range(8)],is_original_COVID_FN=i<3))
        if i>=20 or i==1:continue
        evidence={k:dict(path='/generated/'+k,sha256='a'*64) for k in
            ('index','labels','publisher_order','index_base','version','row_extent','source_subject_binding','member_mapping')}
        evidence.update(label_version_resolved=True,order_policy='SLICE_LOCATION_DESCENDING')
        labels=[1,1,1,1,0,0,0,0]
        if i==3:labels[0]=None
        references.append(dict(source_group_id=c['source_group_id'],source_diagnosis=c['source_diagnosis'],
            geometry_sha256='c'*64 if i==2 else c['native_geometry_reference']['sha256'],version_applicability='ORIGINAL_VERSION_EXPLICIT_SCOPE',
            original_Label_Index=i,label_index_base=0,annotation_case_index=i,Index_row=i,label_file_version='GENERATED_ORIGINAL',
            evidence=evidence,labels_publisher_domain=labels,declared_valid_publisher_indices=list(range(8)),range_policy='EXPLICIT_PUBLISHER_EXTENT'))
    metadata=dict(groups=groups,development_record_ids=control['development_record_ids'],bindings=dict(evidence_type='GENERATED_ONLY'))
    return scores,control,policy,metadata,dict(status='EXECUTED',rows=references)


def test_actual_data20_view_to_encoder_mixed_targets(monkeypatch):
    paths=[DATA/'medical_slice_registry_v2.py',DATA/'slice_evaluation_registry.py']
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    producer=data_producer();scores,control,policy,metadata,references=generated_inputs()
    full=producer.build_registry(metadata,references);producer.validate_registry(full)
    view=producer.export_development_view(full,metadata,control['consumer'],scores['fixed8_control'],dict(path='/generated/full-registry.json',sha256='a'*64),'f'*64)
    result=evaluate(scores,control,view,policy)
    assert result['registry_denominators']==dict(source_groups=20,paired_groups=17,partially_paired_groups=1,unknown_groups=1,conflict_groups=1,confirmed_positions=143)
    original=result['original_argmax_macro_separate_by_target_class']
    assert original['0']['PRIMARY_COMPLETE8']['source_groups']==11
    assert original['1']['PRIMARY_COMPLETE8']['source_groups']==6
    assert result['groups'][1]['scores']=={} and result['groups'][2]['scores']=={}
    assert result['groups'][3]['cohort']=='SECONDARY_PARTIAL_CONFIRMED'
    assert 'ORIGINAL_ARGMAX_FIXED_MARGIN' not in result['macro_by_cohort']['PRIMARY_COMPLETE8']
    after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};assert before==after
    if os.environ.get('R103_CROSSLINE_PROOF'):
        path=Path(os.environ['R103_CROSSLINE_PROOF'])
        proof=dict(schema='R103_GENERATED_CROSSLINE_PROOF_V1',status='PASS_GENERATED_ONLY',producer_module='medical_slice_registry_v2',
            producer_function='build_registry -> export_development_view',consumer_function='r103_slice_evaluation.evaluate (includes both strict validators)',
            source_sha256=before,source_groups=20,states=view['denominators'],mixed_original_targets=dict(class0_primary=11,class1_primary=6),
            source_modules_only=True,real_label_reads=0,real_registry_reads=0,array_reads=0,model_calls=0,
            note='Generated143 confirmed positions are not an actual medical denominator; no diagnostic accuracy or localization result claimed')
        with path.open('x') as stream:json.dump(proof,stream,sort_keys=True,indent=2);stream.write('\n')


def test_data_not_run_view_is_rejected_not_reported_as_zero():
    producer=data_producer();scores,control,policy,metadata,_=generated_inputs()
    full=producer.build_registry(metadata)
    view=producer.export_development_view(full,metadata,control['consumer'],scores['fixed8_control'],dict(path='/generated/full.json',sha256='a'*64),'f'*64)
    assert view['usable_reference_denominator'] is None
    with pytest.raises(EvaluationRejected,match='NOT_RUN_REGISTRY'):evaluate(scores,control,view,policy)


def test_actual_data_native_partial_without_sampled_reference_stays_excluded():
    producer=data_producer();scores,control,policy,metadata,references=generated_inputs()
    indices=list(range(1,16,2));control['rows'][0].update(native_depth=16,fixed8_native_indices=indices);scores['cases'][0]['geometry']['indices_Z']=indices
    group=metadata['groups'][0];group.update(depth=16,fixed8=indices,native_slices=[dict(native_index=j,member_key=f'GEN-16-{j}',ipp_normal_position=float(j),slice_location=float(j)) for j in range(16)])
    reference=references['rows'][0];reference.update(labels_publisher_domain=[None if j%2==0 else j%4//2 for j in range(16)],declared_valid_publisher_indices=list(range(1,16,2)))
    full=producer.build_registry(metadata,references)
    view=producer.export_development_view(full,metadata,control['consumer'],scores['fixed8_control'],dict(path='/generated/full.json',sha256='a'*64),'f'*64)
    result=evaluate(scores,control,view,policy)
    assert result['groups'][0]['mapping_status']=='PARTIALLY_PAIRED'
    assert result['groups'][0]['scores']=={} and result['groups'][0]['cohort']=='EXCLUDED_NO_CONFIRMED_FIXED8_REFERENCE'
