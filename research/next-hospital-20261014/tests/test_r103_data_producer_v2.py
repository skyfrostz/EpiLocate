"""Generated payloads/archives only; no real medical data or network."""
import copy,hashlib,io,json,sys
from pathlib import Path
import numpy as np
import pytest
from epi_next import r103_data_producer_v2 as p
from test_archive_bound_ab_v2 import fixture,write


def test_global_corrections_do_not_extend_registered_scope():
    raw=b'Label Index,Diagnosis,Relative Path,Folder/ID\n0,COVID-19,COVID-19 Cases,P001\n1,COVID-19,COVID-19 Cases,P006\n2,CAP,CAP Cases,P001\n'
    groups=[dict(source_subject_directory='COVID-19 Cases/P001',source_group_id='A',source_diagnosis='COVID-19')]
    audit=p.index_audit(raw,3,groups)
    assert audit['global_author_correction_rows']==[0,1] and len(audit['matched'])==1
    old=np.zeros((3,8),dtype='uint8');new=old.copy();new[1,0]=1
    assert p.correction_scope_verified(old,new,audit)==(1,True)
    new[2,0]=1
    assert p.correction_scope_verified(old,new,audit)==(2,False)
    assert audit['base_basis'].startswith('INFERENCE')


def test_ambiguous_base_and_duplicate_rejected():
    raw=b'Label Index,Diagnosis,Relative Path,Folder/ID\n1,COVID-19,COVID-19 Cases,P001\n'
    assert p.index_audit(raw,3,[])['base'] is None
    with pytest.raises(ValueError,match='DUPLICATE_LABEL_INDEX'):p.index_audit(raw+raw.splitlines()[1]+b'\n',3,[])


def test_version_only_producer_exact60_20_unknown_and_no_header(tmp_path,monkeypatch):
    req,_,_=fixture(tmp_path)
    groups=[dict(source_group_id=str(i),record_id='GEN'+str(i),source_diagnosis='COVID-19',split='train_weak' if i<40 else 'val_classification',source_subject_directory='COVID-19 Cases/P'+str(i+1).zfill(3),depth=8,fixed8=list(range(8)),geometry_binding={'path':'/generated/geometry','sha256':'a'*64},native_tensor_SHA='b'*64,is_original_COVID_FN=i in (40,41,42)) for i in range(60)]
    metadata=dict(groups=groups,development_record_ids=[g['record_id'] for g in groups[40:]])
    req.update(schema=p.SCHEMA,phase_scope='VERSION_INDEX_AUDIT_ONLY',caps=p.VERSION_CAPS,extent_proofs={},updated_policy='DISABLED_GENERATED_TEST',consumer={'path':'/generated/consumer','sha256':'c'*64},ENC_fixed8_control={'path':'/generated/control','sha256':'d'*64},semantic_evidence={},metadata=write(tmp_path/'metadata.json',metadata))
    req['source_closure_sha256']=hashlib.sha256(b'[]').hexdigest()
    index=b'Label Index,Diagnosis,Relative Path,Folder/ID\n'+b''.join(f'{i},COVID-19,COVID-19 Cases,P{i+1:03}\n'.encode() for i in range(60))
    f=io.BytesIO();np.save(f,np.zeros((60,8),dtype='uint8'));labels=f.getvalue()
    req['pinned_files']={}
    for key,name,raw in [('cached_Index','Index.csv',index),('cached_original_labels','Slice-level-labels.npy',labels)]:
        target=tmp_path/name;target.write_bytes(raw);req[key]={'path':str(target),'sha256':hashlib.sha256(raw).hexdigest()};req['pinned_files'][name]={'git_blob':p.blob_sha(raw)}
    anchor=p.ab.prior.read_bound(req['original_anchor_request']);anchor['stages']={'RI-c':{'groups':[]}};req['original_anchor_request']=write(tmp_path/'anchor.json',anchor)
    approval=dict(schema='R103_DATA_PRODUCER_APPROVAL_V2',status='APPROVED_NEW_SCOPE',request_sha256='GENERATED',permit_cached_original_labels=True,permit_conditional_updated_1=True,permit_conditional_development_headers=False,permit_pairing_registry=True,permit_pixels=False,permit_models=False,permit_archive_rescan=False,retry=False)
    monkeypatch.setattr(p,'extract_location',lambda *_:pytest.fail('HEADER_UNREACHABLE'))
    monkeypatch.setattr(p.ab.identity,'scan',lambda *_:pytest.fail('RESCAN_FORBIDDEN'))
    monkeypatch.setattr(p.urllib.request,'build_opener',lambda *_:pytest.fail('NO_HTTP_IN_GENERATED_CASE'))
    assert p.produce(req,'GENERATED')['status'].startswith('CHECK_ONLY')
    result=p.produce(req,'GENERATED',approval)
    receipt=json.loads(Path(result['receipt_path']).read_text());view=json.loads((Path(req['output_root'])/'DEVELOPMENT20_V2.json').read_text())
    assert receipt['status']=='PRODUCER_COMPLETE_WITH_REFERENCE_STATES' and receipt['new_header_members']==0
    assert receipt['pairing_execution']=='NOT_RUN' and len(view['rows'])==20
    assert view['schema']=='R103_SLICE_REFERENCE_REGISTRY_V1' and view['usable_reference_denominator'] is None
    assert set(receipt['consumer_refs']['DEVELOPMENT20_V2.json'])=={'path','sha256'}
    req['package_versions']={'numpy':'INVALID_GENERATED_VERSION'}
    with pytest.raises(ValueError,match='PACKAGE_VERSION_DRIFT'):p.validate(req,'GENERATED')
    req['package_versions']={}
    req['extent_proofs']={'0':{'path':'/forbidden','sha256':'a'*64}}
    with pytest.raises(ValueError,match='VERSION_ONLY_CANNOT'):p.validate(req,'GENERATED')


def test_header_resource_or_structure_failure_is_not_missing_reference(monkeypatch):
    class Stream:
        def close(self):pass
    class Walker:
        def __init__(self,*args):pass
        def run(self):return {'stop_code':'NOT_VALID_STRUCTURE'}
    monkeypatch.setattr(p,'HeaderMember',lambda *_:Stream());monkeypatch.setattr(p.ab.prior,'LocationWalker',Walker)
    with pytest.raises(ValueError,match='HEADER_STRUCTURE'):p.extract_location(None,None,None,None)
