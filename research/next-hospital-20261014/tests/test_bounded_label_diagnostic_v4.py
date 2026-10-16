"""New generated caches only. Run solely in chief's serial CPU window."""
import hashlib,io,json,sys
import numpy as np
import pytest
from epi_next import bounded_label_diagnostic_v4 as d


def binding(path,raw):
    path.write_bytes(raw);return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def request(tmp_path):
    meta=binding(tmp_path/'meta.json',json.dumps({'groups':[dict(source_group_id='GEN',source_subject_directory='COVID-19 Cases/P001',source_diagnosis='COVID-19')]}).encode())
    f=io.BytesIO();np.save(f,np.zeros((3,8),dtype='uint8'))
    q=dict(schema=d.SCHEMA,caps=d.CAPS,spec=dict(task_key='GENERATED-NEW-DIAGNOSTIC-V4',max_forward=0,max_backward=0),source_bindings=[],runtime_sha256=d.provenance.prior.old.sha(sys.executable),package_versions={},metadata=meta,output_root=str(tmp_path/'output'),cache={'Index':binding(tmp_path/'Index.csv',b'Label Index,Diagnosis,Relative Path,Folder/ID\n1,COVID-19,COVID-19 Cases,P001\n'),'original':binding(tmp_path/'generated.bin',f.getvalue())})
    owner=dict(schema='BOUNDED_LABEL_CACHE_DIAGNOSTIC_APPROVAL_V4',status='APPROVED_NEW_SCOPE',request_sha256='GENERATED',permit_exact_cache_read=True,permit_HTTP=False,permit_headers=False,permit_pixels=False,permit_models=False,permit_archive_body=False,retry=False)
    return q,owner


def test_generated_diagnostics_preserve_ambiguous_path_join(tmp_path):
    q,o=request(tmp_path);r=d.run(q,'GENERATED',o)
    out=json.loads((tmp_path/'output/INDEX_DIAGNOSTICS_V4.json').read_text())
    assert out['raw_path_join_rows']==1 and out['valid_bases']==[0,1]
    assert r['status']=='DIAGNOSTICS_COMPLETE_PAIRING_BLOCKED' and r['medical_denominator'] is None and r['headers']==0
    with pytest.raises(FileExistsError):d.run(q,'GENERATED',o)


def test_check_only_never_reads_cache(tmp_path,monkeypatch):
    q,o=request(tmp_path);monkeypatch.setattr(d,'cached_bytes',lambda *_:pytest.fail('PAYLOAD_ENTERED'))
    assert d.run(q,'GENERATED')['status']=='CHECK_ONLY_NO_PAYLOAD_ACCESS'
    o['schema']='R103_DATA_PRODUCER_APPROVAL_V2'
    with pytest.raises(ValueError,match='NEW_EXACT_OWNER'):d.run(q,'GENERATED',o)


def test_cache_identity_cap_and_symlink_reject(tmp_path):
    p=tmp_path/'cache';b=binding(p,b'GEN');budget=d.provenance.prior.old.Budget(d.CAPS)
    with pytest.raises(ValueError,match='SIZE_CAP'):d.cached_bytes(b,2,budget)
    p.write_bytes(b'BAD')
    with pytest.raises(ValueError,match='SHA_DRIFT'):d.cached_bytes(b,3,budget)
    link=tmp_path/'link';link.symlink_to(p)
    with pytest.raises(ValueError):d.cached_bytes(dict(b,path=str(link)),3,budget)


def test_missing_author_domain_never_inferred_from_depth():
    assert d.extent_gate(None,dict(depth=8),'a'*64)=='AUTHOR_EXTENT_AND_MEMBER_DOMAIN_MISSING'
    with pytest.raises(ValueError,match='NOT_QUALIFIED'):d.extent_gate(dict(effective_native_count=8),dict(depth=8,source_group_id='GEN'),'a'*64)


def test_old_task_rejected_and_corrupt_cache_failure_receipt(tmp_path):
    q,o=request(tmp_path);q['spec']['task_key']='DATA-R103-VERSION-INDEX-AUDIT-01'
    with pytest.raises(ValueError,match='OLD_A_TASK'):d.run(q,'GENERATED')
    q['spec']['task_key']='GENERATED-NEW-DIAGNOSTIC-V4';q['cache']['original']['sha256']='0'*64
    with pytest.raises(ValueError,match='SHA_DRIFT'):d.run(q,'GENERATED',o)
    r=json.loads((tmp_path/'output/RECEIPT_V4.json').read_text());assert r['status']=='FAILED_STOP_NO_RETRY' and r['headers']==0
