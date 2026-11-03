"""Synthetic file/control closure only; no DATA/medical registry is opened."""
import copy
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from epi_next import r103_eval_entry as entry
from epi_next.r103_slice_evaluation import EvaluationRejected
from epi_next.r103_frozen_classifier import validate_holdout_manifest
from test_r103_slice_evaluation import fixture,ref


def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,sort_keys=True))
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def producer_fixture(tmp_path,monkeypatch):
    data=tmp_path/'DATA';monkeypatch.setattr(entry,'DATA_ROOT',data)
    source=data/'research/next-hospital-20261014/epi_next/producer.py';source.parent.mkdir(parents=True);source.write_text('GENERATED_PRODUCER=1\n')
    source_ref=dict(path=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    monkeypatch.setattr(entry.subprocess,'check_output',lambda *args,**kwargs:source.read_bytes())
    base=data/'.local/r103-generated'
    request_ref=save(base/'request.json',dict(schema='GENERATED_DATA_REQUEST',source_commit='a'*40,source_bindings=[dict(source_ref,bytes=source.stat().st_size)],consumer=ref('consumer'),ENC_fixed8_control=ref('control'),
        output_root=str(base),supervisor_output=str(base/'supervision'),spec=dict(job_id='generated-data-r103',task_key='GENERATED-DATA-R103',max_forward=0,max_backward=0)))
    registry_ref=save(base/'DEVELOPMENT20_V2.json',{'must_not_be_read_by_resolver':True})
    science=save(base/'PRODUCER_RECEIPT_V2.json',dict(schema='GENERATED_DATA_SUCCESS_V1',status='SAVED',request_sha256=request_ref['sha256'],registry=registry_ref,confirmed_positions=8))
    owner=save(base/'owner.json',dict(schema='GENERATED_DATA_OWNER_V1',status='APPROVED',request_sha256=request_ref['sha256']))
    supervisor_binding=dict(dependency_sha256='1'*64,modules={'generated':ref('generated-supervisor')})
    supervisor=save(base/'supervision/generated-data-r103/supervisor-receipt.json',dict(schema='EPI-NEXT-WAVE1-SUPERVISION-1',status='SUCCESS',slot_completed=True,job_id='generated-data-r103',task_key='GENERATED-DATA-R103',
        dependency_sha256=supervisor_binding['dependency_sha256'],actual_loaded_supervisor_modules=supervisor_binding['modules'],runner_actual_counts=dict(forward=0,backward=0),counters=dict(forward=0,backward=0)))
    finished=save(base/'finished.json',dict(status='SUCCESS',job_id='generated-data-r103',receipt_path=supervisor['path'],receipt_sha256=supervisor['sha256'],children=[dict(exit_code=0)]))
    lock=dict(status='EXACT_PRODUCER_LOCKED',request=request_ref,source_commit='a'*40,sources=[source_ref],registry_path=registry_ref['path'],
        science_receipt_path=science['path'],science_receipt_schema='GENERATED_DATA_SUCCESS_V1',science_success_statuses=['SAVED'],
        receipt_request_sha_field=['request_sha256'],receipt_registry_ref_field=['registry'],receipt_confirmed_positions_field=['confirmed_positions'],owner_schema='GENERATED_DATA_OWNER_V1',owner_success_status='APPROVED',owner_request_sha_field=['request_sha256'],
        producer_job_id='generated-data-r103',producer_task_key='GENERATED-DATA-R103',supervisor_receipt_path=supervisor['path'],slot_finished_path=finished['path'])
    q=dict(registry_contract=save(tmp_path/'contract.json',dict(producer_lock=lock,medical_evaluation_ready=True)),supervisor=supervisor_binding,consumer=ref('consumer'),fixed8_control=ref('control'))
    binding=dict(schema='R103_DATA_REGISTRY_BINDING_V1',scientific_request_sha256='f'*64,registry=registry_ref,producer_science_receipt=science,producer_owner_approval=owner,
                 producer_supervisor_receipt=supervisor,producer_slot_finished=finished)
    return q,binding,lock,source


def test_concrete_producer_closure_without_registry_content_read(tmp_path,monkeypatch):
    q,b,lock,source=producer_fixture(tmp_path,monkeypatch)
    original=entry.bound;seen=[]
    def track(r,*args):
        seen.append(r['path']);assert r['path']!=b['registry']['path']
        return original(r,*args)
    monkeypatch.setattr(entry,'bound',track)
    assert entry.resolve_registry(b,q,'f'*64)==dict(registry=b['registry'],confirmed_positions=8)
    assert lock['request']['path'] in seen and b['producer_owner_approval']['path'] in seen


@pytest.mark.parametrize('change',['extra_commit','wrong_output_path','old_A_permission','old_A_science','producer_source_drift','failed_supervisor','child_exit1','unlocked_producer','wrong_supervisor_dependency','unexpected_producer_model'])
def test_no_arbitrary_producer_or_old_permission(tmp_path,monkeypatch,change):
    q,b,lock,source=producer_fixture(tmp_path,monkeypatch)
    if change=='extra_commit':b['producer_commit']='b'*40
    if change=='wrong_output_path':b['registry']=save(Path(b['registry']['path']).with_name('other.json'),{'other':True})
    if change=='producer_source_drift':source.write_text('DRIFT=2\n')
    if change=='unlocked_producer':
        lock['status']='BLOCKED_PENDING_EXACT_DATA_PRODUCER';q['registry_contract']=save(Path(q['registry_contract']['path']),dict(producer_lock=lock,medical_evaluation_ready=True))
    if change in ('old_A_permission','old_A_science','failed_supervisor','child_exit1','wrong_supervisor_dependency','unexpected_producer_model'):
        key={'old_A_permission':'producer_owner_approval','old_A_science':'producer_science_receipt','failed_supervisor':'producer_supervisor_receipt','child_exit1':'producer_slot_finished','wrong_supervisor_dependency':'producer_supervisor_receipt','unexpected_producer_model':'producer_supervisor_receipt'}[change]
        d=json.loads(Path(b[key]['path']).read_text())
        if change in ('old_A_permission','old_A_science'):d['request_sha256']='0'*64
        if change=='failed_supervisor':d['status']='FAILED'
        if change=='child_exit1':d['children'][0]['exit_code']=1
        if change=='wrong_supervisor_dependency':d['dependency_sha256']='0'*64
        if change=='unexpected_producer_model':d['runner_actual_counts']['forward']=1
        b[key]=save(Path(b[key]['path']),d)
    with pytest.raises(EvaluationRejected):entry.resolve_registry(b,q,'f'*64)


def test_default_cli_and_missing_authority_never_read_registry(tmp_path,monkeypatch,capsys):
    q={};monkeypatch.setattr(entry,'check_request',lambda obj:obj);monkeypatch.setattr(entry,'bound',lambda ref:q)
    monkeypatch.setattr(entry,'resolve_registry',lambda *args:pytest.fail('unauthorized registry access'))
    argv=['--request',str(tmp_path/'q.json'),'--request-sha','a'*64]
    assert entry.main(argv)==0 and 'NOT RUN' in capsys.readouterr().out
    with pytest.raises(EvaluationRejected):entry.main(argv+['--execute'])


@pytest.mark.parametrize('count',[None,0])
def test_no_reference_stops_before_registry_consumption(tmp_path,monkeypatch,count):
    q,b,lock,source=producer_fixture(tmp_path,monkeypatch)
    science=json.loads(Path(b['producer_science_receipt']['path']).read_text());science['confirmed_positions']=count
    b['producer_science_receipt']=save(Path(b['producer_science_receipt']['path']),science)
    original=entry.bound
    def track(r,*args):
        assert r['path']!=b['registry']['path'];return original(r,*args)
    monkeypatch.setattr(entry,'bound',track)
    with pytest.raises(entry.NoConfirmedReference):entry.resolve_registry(b,q,'f'*64)


def test_fixed_version_index_scope_cannot_be_extended_by_positive_receipt(tmp_path,monkeypatch):
    q,b,lock,source=producer_fixture(tmp_path,monkeypatch)
    q['registry_contract']=save(Path(q['registry_contract']['path']),dict(producer_lock=lock,medical_evaluation_ready=False))
    with pytest.raises(entry.NoConfirmedReference,match='NO_CONFIRMED_REFERENCE_PATH'):
        entry.resolve_registry(b,q,'f'*64)


def test_declared_source_bytes_checked_beside_complete_sha_projection(tmp_path,monkeypatch):
    q,b,lock,source=producer_fixture(tmp_path,monkeypatch)
    request=json.loads(Path(lock['request']['path']).read_text());request['source_bindings'][0]['bytes']=0
    lock['request']=save(Path(lock['request']['path']),request)
    q['registry_contract']=save(Path(q['registry_contract']['path']),dict(producer_lock=lock,medical_evaluation_ready=True))
    with pytest.raises(EvaluationRejected,match='SOURCE_BYTE_DECLARATION'):entry.resolve_registry(b,q,'f'*64)


def test_main_fixed_scope_block_never_opens_permission_registry_or_queue(tmp_path,monkeypatch,capsys):
    q,b,lock,source=producer_fixture(tmp_path,monkeypatch)
    q['registry_contract']=save(Path(q['registry_contract']['path']),dict(producer_lock=lock,medical_evaluation_ready=False))
    request=save(tmp_path/'encoder-request.json',q)
    monkeypatch.setattr(entry,'check_request',lambda value:value)
    original=entry.bound;allowed={request['path'],q['registry_contract']['path']}
    def bound_control_only(r,*args):
        assert r['path'] in allowed;return original(r,*args)
    monkeypatch.setattr(entry,'bound',bound_control_only)
    argv=['--request',request['path'],'--request-sha',request['sha256'],'--execute']
    for name in ('approval','dispatch','admission','registry-binding'):
        argv+=['--'+name,'/generated/NEVER_OPEN','--'+name+'-sha','0'*64]
    assert entry.main(argv)==0
    result=json.loads(capsys.readouterr().out)
    assert result['status']=='BLOCKED_FROZEN_PRODUCER_NO_REFERENCE_SCOPE' and result['queue_entered'] is False


@pytest.mark.parametrize('bad_registry',[False,True])
def test_admitted_generated_body_zero_model_and_failure_stop(tmp_path,monkeypatch,bad_registry):
    scores,control,registry,policy=fixture()
    if bad_registry:registry['denominators']['confirmed_positions']=159
    control_ref=save(tmp_path/'input-control.json',control)
    scores['fixed8_control']=control_ref;registry['fixed8_control']=control_ref
    scores['source_artifact']=save(tmp_path/'original.json',dict(cases=scores['cases']))
    score_ref=save(tmp_path/'input-scores.json',scores);registry_ref=save(tmp_path/'medical-reference-GENERATED.json',registry)
    policy_ref=save(tmp_path/'policy.json',policy)
    q=dict(scores=score_ref,fixed8_control=control_ref,consumer=control['consumer'],original_contributions=scores['source_artifact'],protocol=policy_ref,
           delivery_root=str(tmp_path/'delivery'),output=str(tmp_path/'delivery/results'),spec=dict(device='cpu',max_forward=0,max_backward=0))
    class Guard:
        spec=SimpleNamespace(**q['spec']);completion=None
        def begin_case(self,key):pass
        def end_case(self):pass
        def check(self):pass
        def complete(self,status,**counts):self.completion=dict(status=status,**counts)
    guard=Guard();shared=SimpleNamespace(ChildGuard=SimpleNamespace(from_environment=lambda:guard),SupervisionSpec=lambda **fields:SimpleNamespace(**fields))
    monkeypatch.setattr(entry,'resolve_registry',lambda *args:dict(registry=registry_ref,confirmed_positions=160 if not bad_registry else 159))
    binding_ref=save(tmp_path/'binding-GENERATED.json',{})
    if bad_registry:
        with pytest.raises(EvaluationRejected):entry.run_child(q,binding_ref,'a'*64,shared)
        assert guard.completion['status']=='FAILED' and (Path(q['output'])/'failure.json').is_file()
    else:
        result=entry.run_child(q,binding_ref,'a'*64,shared)
        assert result['status']=='DONE' and (Path(q['output'])/'evaluation.json').is_file()
        assert guard.completion['status']=='SUCCESS'
    assert guard.completion['actual_forward']==guard.completion['actual_backward']==0


def holdout_fixture():
    scores,control,registry,policy=fixture()
    identity=dict(schema='R103_FROZEN_R18_IDENTITY_V1',K=8,threshold=.5,training_source_dataset='COVID-CT-MD')
    rows=[]
    for i,diagnosis in enumerate(('Normal','COVID-19','CAP')):
        h=hashlib.sha256(('generated'+str(i)).encode()).hexdigest()
        rows.append(dict(record_id='new'+str(i),source_group_id='newgroup'+str(i),native_tensor_sha256=h,
          not_used_for_training_validation_explanation_selection=True,native_QA='QUALIFIED_BOUND_GEOMETRY_HU',source_diagnosis=diagnosis,task_label=int(diagnosis!='Normal'),
          geometry_reference=ref('geo'),native_tensor_reference=dict(path='/generated/new'+str(i),sha256=h),confirmed_patient_id=None,source_dataset_id='COVID-CT-MD'))
    manifest=dict(schema='R103_HOLDOUT_SOURCE_MANIFEST_V1',status='LOCKED_BEFORE_PREDICTIONS',cohort_type='INTERNAL_SAME_SOURCE_HOLDOUT',classifier_identity=ref('frozen-identity'),threshold=.5,
      license_evidence=ref('license'),label_definition_evidence=ref('labels'),overlap_audit=ref('overlap'),rows=rows,class_counts={'Normal':1,'COVID-19':1,'CAP':1},clinical_patient_independence='UNKNOWN',pretraining_overlap='UNKNOWN',source_dataset_id='COVID-CT-MD')
    return manifest,control,identity


def test_frozen_internal_external_holdout_stays_metadata_only():
    m,c,i=holdout_fixture();a=validate_holdout_manifest(m,c,i,3,identity_reference=ref('frozen-identity'))
    assert a['planned_backbone_batches']==3 and a['planned_slice_positions']==24 and a['actual_model_calls']==0
    assert a['clinical_patient_independence']=='UNKNOWN'
    m['cohort_type']='EXTERNAL_CROSS_SOURCE_VALIDATION'
    m['source_dataset_id']='GENERATED_EXTERNAL'
    for row in m['rows']:row['source_dataset_id']='GENERATED_EXTERNAL'
    assert validate_holdout_manifest(m,c,i,3,identity_reference=ref('frozen-identity'))['cohort_type']=='EXTERNAL_CROSS_SOURCE_VALIDATION'


@pytest.mark.parametrize('change',['unlocked','prior_group','prior_hash','used_for_explanation','duplicate_patient','wrong_counts','unknown_N','wrong_threshold','external_same_source','mixed_source','unproven_independence'])
def test_holdout_rejects_reuse_or_unlocked_selection(change):
    m,c,i=holdout_fixture();n=3
    if change=='unlocked':m['status']='DRAFT'
    if change=='prior_group':m['rows'][0]['source_group_id']=c['rows'][0]['source_group_id']
    if change=='prior_hash':m['rows'][0]['native_tensor_sha256']=c['rows'][0]['native_tensor_sha256']
    if change=='used_for_explanation':m['rows'][0]['not_used_for_training_validation_explanation_selection']=False
    if change=='duplicate_patient':m['rows'][0]['confirmed_patient_id']=m['rows'][1]['confirmed_patient_id']='known_same_patient'
    if change=='wrong_counts':m['class_counts']['CAP']=9
    if change=='unknown_N':n=None
    if change=='wrong_threshold':m['threshold']=.4
    if change=='external_same_source':m['cohort_type']='EXTERNAL_CROSS_SOURCE_VALIDATION'
    if change=='mixed_source':m['rows'][0]['source_dataset_id']='OTHER_SOURCE'
    if change=='unproven_independence':m['clinical_patient_independence']='CONFIRMED_BY_BOUND_AUDIT'
    with pytest.raises(EvaluationRejected):validate_holdout_manifest(m,c,i,n,identity_reference=ref('frozen-identity'))
