"""Generated archive only. New A is never executed on real labels in tests."""
import copy,hashlib,json,os,sys
from pathlib import Path
import pytest
from epi_next import archive_bound_ab_v2 as entry
from test_r92_label_read_entry import bundle,write


def fixture(tmp_path,force_zip64=False):
    oldreq,_,_=bundle(tmp_path,False);base=entry.prior.read_bound(oldreq['original_batch_request'])
    archive=Path(base['source_archive']['path'])
    if force_zip64:
        import zipfile
        with zipfile.ZipFile(archive) as z:raws={i.filename:z.read(i) for i in z.infolist()}
        repacked=archive.with_suffix('.new')
        with zipfile.ZipFile(repacked,'w',zipfile.ZIP_DEFLATED) as z:
            for name,data in raws.items():
                with z.open(name,'w',force_zip64=True) as f:f.write(data)
        os.replace(repacked,archive)
        with zipfile.ZipFile(archive) as z:
            members=[{'name':i.filename,'compression_method':i.compress_type,'compressed_bytes':i.compress_size,
                      'uncompressed_bytes':i.file_size,'crc32':i.CRC,'header_offset':i.header_offset} for i in z.infolist()]
        inv=Path(base['inventory_binding']['path']);inv.write_text(''.join(json.dumps(x)+'\n' for x in members))
        base['inventory_binding']['sha256']=entry.prior.old.sha(inv)
        oldreq['label_members']=[x for x in members if x['name'] in ('Index.csv','Slice-level-labels.npy')]
    digest=entry.prior.old.sha(archive)
    r=entry.identity.scan(archive,digest,archive.stat().st_size,chunk=1024)
    receipt=write(tmp_path/'identity.json',r)
    a0=write(tmp_path/'historical-a0.json',{'phases':{'integrity':{'sha256':digest,'bytes':archive.stat().st_size}}})
    req={'schema':entry.SCHEMA,'caps':entry.CAPS,'source_bindings':[],
         'runtime_sha256':entry.prior.old.sha(sys.executable),'identity_receipt':receipt,
         'original_source':{'path':str(archive),'sha256':digest,'bytes':archive.stat().st_size},
         'original_A0_receipt':a0,'original_anchor_request':write(tmp_path/'anchor.json',{'source_archive':{'path':str(archive),'sha256':digest,'bytes':archive.stat().st_size,'receipt_path':a0['path'],'receipt_sha256':a0['sha256']}}),'cached_discovery':write(tmp_path/'discovery.json',{'sources':[]}),
         'inventory':base['inventory_binding'],'label_members':oldreq['label_members'],
         'output_root':str(tmp_path/'new-output')}
    app={'schema':'ARCHIVE_BOUND_AB_RETRY_APPROVAL_V2','request_sha256':'GENERATED_SHA',
         'permit_cached_official_metadata':True,'permit_original_Index':True,
         'permit_original_slice_labels':True,'permit_new_HTTP':False,
         'permit_full_archive_rescan':False,'permit_C':False,'permit_pixels':False,
         'permit_models':False,'retry':False}
    return req,app,archive


def test_normal_generated_ab_no_http_no_rescan(tmp_path,monkeypatch):
    req,app,_=fixture(tmp_path)
    monkeypatch.setattr(entry.identity,'scan',lambda *_:pytest.fail('UNAUTHORIZED_RESCAN'))
    monkeypatch.setattr(entry.prior,'discover',lambda:pytest.fail('UNAUTHORIZED_HTTP'))
    result=entry.run(req,'GENERATED_SHA',app)
    receipt=json.loads(Path(result['receipt_path']).read_text())
    assert receipt['status']=='AB_EVIDENCE_SAVED_MAPPING_UNKNOWN'
    assert receipt['new_HTTP_calls']==0 and receipt['full_archive_scan_bytes_in_this_execution']==0
    assert receipt['label_shape']==[1,8] and receipt['registry']=='NOT_RUN'
    assert len(receipt['payloads'])==2
    with pytest.raises(FileExistsError):entry.run(req,'GENERATED_SHA',app)


def test_any_new_drift_stops_before_cached_metadata_or_payload(tmp_path,monkeypatch):
    req,app,p=fixture(tmp_path);p.write_bytes(b'X'*p.stat().st_size)
    req['cached_discovery']={'path':str(tmp_path/'UNREAD'),'sha256':'0'*64}
    monkeypatch.setattr(entry,'SecureMember',lambda *_:pytest.fail('PAYLOAD_ENTERED'))
    with pytest.raises(entry.identity.IdentityError,match='STAT_OR_NAMESPACE'):entry.run(req,'GENERATED_SHA',app)
    assert not Path(req['output_root']).exists()


def test_check_only_and_new_owner_required(tmp_path,monkeypatch):
    req,app,_=fixture(tmp_path)
    monkeypatch.setattr(entry,'bound_identity',lambda *_:pytest.fail('ARCHIVE_OPEN'))
    assert entry.run(req,'GENERATED_SHA')['status'].startswith('CHECK_ONLY')
    app['permit_new_HTTP']=True
    with pytest.raises(ValueError,match='NEW_EXACT_OWNER'):entry.run(req,'GENERATED_SHA',app)


def test_link_after_identity_rejected(tmp_path):
    req,app,p=fixture(tmp_path);p.rename(p.with_suffix('.saved'))
    p.symlink_to(p.with_suffix('.saved'))
    with pytest.raises(entry.identity.IdentityError):entry.run(req,'GENERATED_SHA',app)


def test_member_crc_fault_and_unlisted_member(tmp_path):
    req,app,p=fixture(tmp_path);r=entry.prior.read_bound(req['identity_receipt']);b=entry.prior.old.Budget(entry.CAPS)
    fd,chain=entry.identity.reuse(p,r)
    bad=copy.deepcopy(req['label_members'][0]);bad['crc32']+=1
    with pytest.raises(ValueError,match='LOCAL_CENTRAL_SIZE_CRC'):entry.SecureMember(fd,bad,b,r)
    bad=copy.deepcopy(req['label_members'][0]);bad['name']='Clinical-data.csv'
    with pytest.raises(ValueError,match='EXACT_SMALL'):entry.SecureMember(fd,bad,b,r)
    os.close(fd)


def test_namespace_race_during_payload_keeps_failure_not_success(tmp_path,monkeypatch):
    req,app,p=fixture(tmp_path);original=entry.SecureMember.read;once=[]
    def race(self,n):
        data=original(self,n)
        if not once and self.emitted>0:
            once.append(True);os.utime(p,None)
        return data
    monkeypatch.setattr(entry.SecureMember,'read',race)
    with pytest.raises(entry.identity.IdentityError):entry.run(req,'GENERATED_SHA',app)
    receipt=json.loads((Path(req['output_root'])/'receipt.json').read_text())
    assert receipt['status']=='FAILED_STOP_NO_RETRY'
    assert not (Path(req['output_root'])/'Index.csv').exists()


def test_forged_self_consistent_receipt_cannot_override_original_source(tmp_path):
    req,app,_=fixture(tmp_path);r=entry.prior.read_bound(req['identity_receipt'])
    r['expected_sha256']=r['sha256']='0'*64
    req['identity_receipt']=write(tmp_path/'forged.json',r)
    req['original_source']['sha256']='0'*64
    with pytest.raises(ValueError,match='ANCHOR_BINDING'):entry.run(req,'GENERATED_SHA',app)
    assert not Path(req['output_root']).exists()


def test_forged_receipt_bytes_against_independent_A0(tmp_path):
    req,app,_=fixture(tmp_path);r=entry.prior.read_bound(req['identity_receipt'])
    r['expected_bytes']=r['bytes_read']=r['expected_bytes']-1
    req['identity_receipt']=write(tmp_path/'forged.json',r)
    with pytest.raises(ValueError,match='HISTORICAL_CONTENT'):entry.run(req,'GENERATED_SHA',app)


def test_one_secure_archive_open_then_dup_only(tmp_path,monkeypatch):
    req,app,_=fixture(tmp_path);calls=[];opened=entry.identity.secure_open;duplicated=entry.os.dup
    def open_once(p):
        calls.append('open');assert calls.count('open')==1
        return opened(p)
    def duplicate(fd):calls.append('dup');return duplicated(fd)
    monkeypatch.setattr(entry.identity,'secure_open',open_once);monkeypatch.setattr(entry.os,'dup',duplicate)
    monkeypatch.setattr(entry.prior.old.Member,'__init__',lambda *_a,**_k:pytest.fail('OLD_PATH_REOPEN'))
    entry.run(req,'GENERATED_SHA',app)
    assert calls==['open','dup','dup']


def test_generated_small_zip64_members_preserve_mature_header_semantics(tmp_path):
    req,app,_=fixture(tmp_path,force_zip64=True)
    result=entry.run(req,'GENERATED_SHA',app)
    receipt=json.loads(Path(result['receipt_path']).read_text())
    assert receipt['status']=='AB_EVIDENCE_SAVED_MAPPING_UNKNOWN'
    assert len(receipt['payloads'])==2 and all(x['CRC_EOF_verified'] for x in receipt['payloads'])
