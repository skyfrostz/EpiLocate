"""Generated Part10/JPEG only; no clinical archive access."""
import copy
import io
import json
import logging
import sys
import warnings
import numpy as np
import pydicom
import pytest
from epi_next import research_import as ri
from test_a2_six_sop import dicom


def changed(i=1, **fields):
    ds=pydicom.dcmread(io.BytesIO(dicom(i)[0]))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        for key,value in fields.items():setattr(ds,key,value)
        out=io.BytesIO();pydicom.dcmwrite(out,ds,enforce_file_format=True)
    return out.getvalue()


@pytest.mark.parametrize('signed',[False,True])
def test_native_decode_with_opaque_invalid_identity(signed,capsys,caplog):
    raw,values=dicom(1,signed)
    # Equal byte lengths keep the generated explicit encoding intact.
    raw=raw.replace(b'1.2.4.1',b'BAD-UID').replace(b'1.2.5.1',b'BAD-UID')
    settings=(pydicom.config.settings.reading_validation_mode,pydicom.config.settings.writing_validation_mode)
    array,row=ri.parse_decode(raw,True)
    np.testing.assert_array_equal(array,values.astype(np.float32)*2-1000)
    assert row['source_dicom_identity_status']=='NOT_EVALUATED'
    assert row['opaque_fingerprints']['StudyInstanceUID']['raw_value_sha256']
    text=json.dumps(row)+capsys.readouterr().out+capsys.readouterr().err+caplog.text
    assert 'BAD-UID' not in text and 'GENERATED_FORBIDDEN' not in text
    assert settings==(pydicom.config.settings.reading_validation_mode,pydicom.config.settings.writing_validation_mode)


def test_warning_and_exception_redaction(caplog,capsys):
    secret='GENERATED_SECRET_UID'
    def noisy():
        logging.getLogger('pydicom').warning('Invalid UI %s',secret)
        warnings.warn(secret)
        raise ValueError(secret)
    with pytest.raises(ri.Reject,match='SELECTED_FIELD_OR_CODEC_ERROR') as caught:ri.warn_safe(noisy)
    assert secret not in str(caught.value)+caplog.text+capsys.readouterr().err
    assert 'PYDICOM_DIAGNOSTIC_REDACTED' in caplog.text
    # Actual mature pydicom UI conversion may warn/log or raise in strict mode.
    raw,_=ri.warn_safe(lambda:changed(SOPClassUID=secret))
    with pytest.raises(ri.Reject):ri.parse_decode(raw)
    assert secret not in caplog.text+capsys.readouterr().err


@pytest.mark.parametrize('fields',[
 {'RescaleType':'US'},{'RescaleSlope':0},{'ImageOrientationPatient':[1,0,0,1,0,0]},
 {'PixelSpacing':[0,.8]},{'NumberOfFrames':2},{'ImageType':['ORIGINAL','LOCALIZER']},
 {'Rows':1024},{'HighBit':5}])
def test_technical_rejects_without_repair(fields):
    with pytest.raises(ri.Reject):ri.parse_decode(changed(**fields))


def stack():
    frames=[];records=[]
    for i in (3,1,2):
        f,r=ri.parse_decode(dicom(i)[0]);frames.append(f);records.append(r)
    return frames,records


def test_projection_sort_native_affine():
    frames,records=stack();array,ledger=ri.volume(frames,records)
    assert array.shape==(3,2,3) and ledger['sorted_member_indices']==[1,2,0]
    np.testing.assert_allclose(np.asarray(ledger['affine_LPS'])@np.array([0,1,1,1]),[.8,.7,1,1])
    assert ledger['resampling']=='NONE' and ledger['anatomical_complete']=='NOT_ESTABLISHED'


@pytest.mark.parametrize('issue',['duplicate','gap','orientation','drift','series','single'])
def test_stack_quarantine(issue):
    frames,records=stack()
    if issue=='duplicate':records[0]['IPP']=records[1]['IPP']
    if issue=='gap':records[0]['IPP']=[0,0,4]
    if issue=='orientation':records[0]['IOP']=[0,1,0,1,0,0]
    if issue=='drift':records[0]['IPP'][0]=1
    if issue=='series':
        for i,r in enumerate(records):r['opaque_fingerprints']={'SeriesInstanceUID':{'raw_value_sha256':str(i)}}
    if issue=='single':frames=frames[:1];records=records[:1]
    with pytest.raises(ri.Reject):ri.volume(frames,records)


def case(i):
    return {'record_id':str(i),'source_group_id':str(i),'native_volume_sha256':str(i),'publisher_group_evidence_bound':True,
            'source_diagnosis':'CAP','task_label':1,'PIXEL_QA':'PASS','RESCALE_QA':'PASS_DECLARED_HU','PROVENANCE_BOUND':True,'GEOMETRY_QA':'PASS_COMPLETE_SELECTED_STACK','split':'train_weak',
            'source_dicom_identity_status':'NOT_EVALUATED','label_provenance':[], 'tensor_artifact':{},'affine_LPS':[],
            'spacing_ZYX_mm':[], 'geometry_ledger':{}}


def test_group_labels_and_consumer():
    cases=ri.bind_groups([case(1),case(2)]);rows=ri.consumer_records(cases)
    assert rows[0]['source_diagnosis']=='CAP' and rows[0]['clinical_patient_independence_status']=='UNKNOWN'
    assert rows[0]['model_input_projection']==['tensor','task_label']
    assert rows[0]['complete_selected_stack']
    cases[1]['source_group_id']=cases[0]['source_group_id'];cases[1]['split']='val_classification'
    with pytest.raises(ri.Reject,match='CROSS_SPLIT'):ri.consumer_records(cases)


@pytest.mark.parametrize('issue',['volume','content','opaque','publisher','label','group'])
def test_group_conflicts_and_unknown_not_promoted(issue):
    a,b=case(1),case(2)
    if issue=='volume':b['native_volume_sha256']=a['native_volume_sha256']
    if issue=='content':
        for c in (a,b):c['frame_ledgers']=[{'full_member_sha256':'same'}]
    if issue=='opaque':
        for c in (a,b):c['source_group_fingerprints']={'StudyInstanceUID':'same'}
    if issue=='group':b['source_group_id']=a['source_group_id']
    if issue=='publisher':b['publisher_group_evidence_bound']=False
    if issue=='label':b['task_label']=0
    ri.bind_groups([a,b]);assert b['research_status']=='QUARANTINED'
    with pytest.raises(ri.Reject):ri.consumer_records([a,b])


def fake_request(tmp_path):
    caps=dict(ri.codec.B,compressed_input_bytes=1000,inflated_member_bytes_total=1000,output_bytes_total=10000)
    groups=[dict(case(i),caps=dict(caps),members=[]) for i in range(1,4)]
    return {'output_root':str(tmp_path/'out'),'overall_wall_seconds':120,'disk_free_floor_bytes':0,'receipt_bytes_max':100000,
            'stages':{s:{'groups':copy.deepcopy(groups),'caps':dict(caps,compressed_input_bytes=3000,inflated_member_bytes_total=3000,output_bytes_total=30000),
                         'per_group_wall_seconds':20,'stage_wall_seconds':60} for s in ('RI-a','RI-b','RI-c')}}


def test_failure_cost_reservation_stops_all_remaining(tmp_path,monkeypatch):
    req=fake_request(tmp_path);calls=[]
    def fail(*args):
        calls.append(args);(tmp_path/'out'/'retained.part').write_bytes(b'partial')
        raise RuntimeError('GENERATED_SECRET_UID')
    monkeypatch.setattr(ri,'phase',fail)
    approval={**{'permit_'+s:True for s in req['stages']},'permit_opaque_uid_fingerprints':{s:False for s in req['stages']}}
    result=ri.pipeline(req,approval)
    assert len(calls)==1 and result['status']=='PARTIAL_STOPPED_NO_RETRY'
    a=result['stages']['RI-a'];assert a['reserved_attempt_upper_bounds']['compressed_input_bytes']==1000
    assert a['observed_successful_groups']['compressed_input_bytes']==0
    assert a['failed_group_actual_costs'].startswith('UNKNOWN')
    assert result['retained_output_bytes_before_receipt']==7
    assert result['stages']['RI-b']['status']=='NOT_RUN_PRIOR_FAILURE'
    assert 'GENERATED_SECRET_UID' not in json.dumps(result)


def test_post_group_audit_blocks_rib_dependency(tmp_path,monkeypatch):
    req=fake_request(tmp_path);calls=[]
    def okay(fn,args,*rest):
        request,group,out,caps,opaque,single=args;calls.append(single)
        row=dict(group,PIXEL_QA='PASS',budget={'compressed_input_bytes':1,'inflated_bytes':1,'output_bytes':1})
        if single:row.update(research_status='LIMITED_SINGLE_FRAME');row.pop('native_volume_sha256')
        else:row.update(research_status='LIMITED_PENDING_COHORT_GROUP_AUDIT',native_volume_sha256='duplicate')
        return row
    monkeypatch.setattr(ri,'phase',okay)
    approval={**{'permit_'+s:True for s in req['stages']},'permit_opaque_uid_fingerprints':{s:False for s in req['stages']}}
    result=ri.pipeline(req,approval)
    assert len(calls)==6 and result['stages']['RI-c']['status']=='CONDITION_NOT_MET'


def test_cli_default_and_missing_approval_never_dispatch(monkeypatch,capsys):
    b={'request_sha256':'1'*64,'source_bindings':[{'path':ri.__file__},{'path':str(ri.CONTRACT)}],
       'decoder_distributions':{},'decoder_module_bindings':[],'decoder_binary_bindings':[]}
    monkeypatch.setattr(ri,'bound_json',lambda p,h:{} if p=='r' else b)
    monkeypatch.setattr(ri.old,'verify_readiness',lambda b:None);monkeypatch.setattr(ri,'validate_request',lambda r:None)
    monkeypatch.setattr(ri,'pipeline',lambda *a:pytest.fail('unexpected archive dispatch'))
    argv=['generated','--request','r','--request-sha256','1'*64,'--readiness','b','--readiness-sha256','2'*64]
    monkeypatch.setattr(sys,'argv',argv);ri.main();assert 'CHECK_ONLY' in capsys.readouterr().out
    monkeypatch.setattr(sys,'argv',argv+['--execute'])
    with pytest.raises(ri.Reject,match='NEW_ITEMIZED'):ri.main()


def test_deterministic_selection_and_exact_category_splits():
    from epi_next.research_import_prepare import selected_groups
    inventory=[]
    for category,n in [('COVID-19 Cases',17),('Cap Cases',17),('Normal Cases',32)]:
        for i in range(n,0,-1):
            inventory.append({'name':f'{category}/S{i}/IM0002.dcm'})
            inventory.append({'name':f'{category}/S{i}/IM0001.dcm'})
    inventory.append({'name':'COVID-19 Cases/S1/nested/FORBIDDEN.dcm'})
    a=selected_groups(inventory);b=selected_groups(list(reversed(inventory)))
    assert a==b and len(a)==60
    from collections import Counter
    assert Counter((g['split'],g['source_diagnosis']) for g in a)=={
        ('train_weak','COVID-19'):10,('train_weak','CAP'):10,('train_weak','Normal'):20,
        ('val_classification','COVID-19'):5,('val_classification','CAP'):5,('val_classification','Normal'):10}
    assert a[0]['directory'].endswith('/S1') and a[9]['directory'].endswith('/S10')
    assert all(len(g['members'])==2 for g in a)


def test_generated_complete_zip_member_to_native_ledger(tmp_path):
    from test_a2_six_sop import fixture
    req=fixture(tmp_path);req['source_archive'].update(version='GENERATED_ONLY',sha256=ri.old.sha(req['source_archive']['path']))
    req.update(full_member_bytes_max=1024**2,publisher_group_semantics='PUBLISHER_SUBJECT_DIRECTORY_BOUND',publisher_evidence=[{'generated':True}])
    group=dict(case(9),members=[x['member'] for x in req['selection'][:2]],A3_seed_identity_nonconformant=False)
    out=tmp_path/'out';out.mkdir()
    row=ri.group_worker(req,group,str(out),ri.codec.B,False,False)
    assert row['source_dicom_identity_status']=='NOT_EVALUATED'
    assert row['GEOMETRY_QA']=='PASS_COMPLETE_SELECTED_STACK'
    assert len(row['frame_ledgers'])==2 and all(r['full_member_sha256'] for r in row['frame_ledgers'])
    assert np.load(row['tensor_artifact']['path']).shape==(2,2,3)
    assert ri.old.sha(row['geometry_ledger']['path'])==row['geometry_ledger']['sha256']
    assert 'GENERATED_FORBIDDEN' not in json.dumps(row)


def test_failure_reason_is_allowlisted_only():
    assert ri.safe_reason(RuntimeError('PHASE_FAILED:Reject:MIXED_STACK_GEOMETRY'))=='MIXED_STACK_GEOMETRY'
    assert ri.safe_reason(RuntimeError('PHASE_FAILED:ValueError:GENERATED_SECRET_UID'))=='GROUP_REJECTED_STOP_NO_RETRY'


@pytest.mark.parametrize('failure,expected',[
    ('PHASE_FAILED:Reject:MISSING_NATIVE_GEOMETRY','MISSING_NATIVE_GEOMETRY'),
    ('PHASE_FAILED:Reject:OPAQUE_SOURCE_GROUP_CONFLICT','OPAQUE_SOURCE_GROUP_CONFLICT'),
    ('PHASE_FAILED:Reject:DECLARED_HU_RESCALE_REQUIRED_NO_DEFAULT_NO_LUT_FALLBACK','DECLARED_HU_RESCALE_REQUIRED_NO_DEFAULT_NO_LUT_FALLBACK'),
    ('PHASE_FAILED:GuardError:COMPRESSED_LIMIT','COMPRESSED_LIMIT'),
    ('PHASE_FAILED:ValueError:GENERATED_SECRET_UID','GROUP_REJECTED_STOP_NO_RETRY'),
])
def test_pipeline_persisted_failure_reason_is_specific_and_safe(tmp_path,monkeypatch,failure,expected):
    req=fake_request(tmp_path);calls=[]
    def fail(*args):
        calls.append(args)
        raise RuntimeError(failure)
    monkeypatch.setattr(ri,'phase',fail)
    approval={**{'permit_'+s:True for s in req['stages']},
              'permit_opaque_uid_fingerprints':{s:False for s in req['stages']}}
    result=ri.pipeline(req,approval)
    saved=json.loads((tmp_path/'out'/'receipt.json').read_text())
    for receipt in (result,saved):
        row=receipt['stages']['RI-a']['rows'][0]
        assert row['reason_code']==expected and row['raw_error_text_retained'] is False
        assert receipt['status']=='PARTIAL_STOPPED_NO_RETRY'
        assert receipt['stages']['RI-b']['status']=='NOT_RUN_PRIOR_FAILURE'
        assert 'GENERATED_SECRET_UID' not in json.dumps(receipt)
    assert len(calls)==1
