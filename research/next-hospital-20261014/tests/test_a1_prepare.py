"""Tiny generated CT/ZIP only; no real archive members or torch."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile

import numpy as np
import pytest
from epi_next import a1_prepare as a1

def generated_request():
    # The fixture is standalone; it never needs private application/data files.
    tags=['0002,0002','0002,0003','0002,0010','0008,0005','0008,0008','0008,0016','0008,0018','0008,0060','0010,0020','0010,0021','0018,0050','0018,0088','0020,000D','0020,000E','0020,0013','0020,0032','0020,0037','0020,0052','0020,0100','0028,0002','0028,0004','0028,0008','0028,0010','0028,0011','0028,0030','0028,0100','0028,0101','0028,0102','0028,0103','0028,0120','0028,0121','0028,1052','0028,1053','0028,1054']
    fields=[{'tag':t,'keyword':k} for t,k in zip(tags,a1.FIELD_VR)]
    a={'members':12,'compressed_input_bytes':160*1024**2,'inflated_header_prefix_bytes_per_member':131072,'inflated_header_prefix_bytes_total':128*1024**2,'element_count_per_member':4096,'whitelist_value_bytes_per_element':4096,'output_bytes_total':16*1024**2,'RSS_stop_bytes':256*1024**2,'wall_seconds':300,'disk_free_floor_bytes':0}
    b={'rows_max':1024,'columns_max':1024,'slices_per_directory_max':512,'compressed_input_bytes':256*1024**2,'inflated_member_bytes_per_member':1024**2,'inflated_member_bytes_total':256*1024**2,'decoded_pixel_bytes_per_slice_max':2*1024**2,'raw_plus_float32_native_output_bytes_per_directory_max':512*1024**2,'output_bytes_total':2*1024**3,'QA_PNG_bytes_total_max':16*1024**2,'QA_PNG_count_max':18,'RSS_stop_bytes':768*1024**2,'wall_seconds':900,'per_directory_wall_seconds':120,'disk_free_floor_bytes':0,'preflight_free_bytes':0}
    candidates=[];records=[]
    for i,diagnosis in enumerate(['COVID-19','COVID-19','CAP','CAP','Normal','Normal'],1):
        candidates.append({'candidate_id':f'MD-A1-{i:02d}','directory':f'GENERATED/{i}'})
        records.append({'record_id':f'MD-A1-{i:02d}','dataset_id':'COVID-CT-MD','version':'GENERATED-ONLY','patient_group_id':None,'patient_group_status':'UNKNOWN','study_key':None,'series_key':None,'source_diagnosis':{'value':diagnosis,'original_value':diagnosis,'provenance':{'source_url':'https://example.invalid/generated','evidence_ref':'GENERATED','verification':'PUBLIC_SOURCE_ONLY'}},'study_imaging_finding':'UNKNOWN','task_label':0 if diagnosis=='Normal' else 1,'label_definition_id':'MD_SOURCE_DIAGNOSIS_WEAK_V1','split':'dev_localization','image_ref':None,'image_sha256':None,'image_missing_reason':'GENERATED','access_status':'NOT_APPROVED','geometry_qa':'NOT_RUN'})
    return {'source_archive':{},'inventory_binding':{},'requests':[{'caps':a,'field_value_whitelist':fields},{'caps':b}],'candidates':candidates,'weak_record_candidates':records,'overall_budget':{'wall_seconds':1320}}


def element(tag,vr,value,explicit=True):
    if vr in ('US','SS'):raw=struct.pack('<'+('H' if vr=='US' else 'h'),value)
    else:
        raw=str(value).encode('ascii')
        if len(raw)%2:raw+=b'\x00' if vr=='UI' else b' '
    head=struct.pack('<HH',*tag)
    if not explicit:return head+struct.pack('<I',len(raw))+raw
    return head+vr.encode()+(b'\0\0'+struct.pack('<I',len(raw)) if vr in a1.LONG_VR else struct.pack('<H',len(raw)))+raw


def dicom(i,k,*,implicit=False,patient=None,orientation='1\\0\\0\\0\\1\\0',z=None):
    uid=f'1.2.840.999.{i}.{k+1}';ts='1.2.840.10008.1.2' if implicit else '1.2.840.10008.1.2.1'
    meta=b''.join(element(t,v,x) for t,v,x in [((2,2),'UI',a1.CT),((2,3),'UI',uid),((2,16),'UI',ts)])
    fields=[((8,8),'CS','ORIGINAL\\PRIMARY'),((8,22),'UI',a1.CT),((8,24),'UI',uid),((8,96),'CS','CT'),((16,16),'PN','GENERATED_NAME_NEVER_RETAIN'),((16,32),'LO',patient or f'GEN-{i}'),((16,33),'LO','GEN-ISSUER'),((32,13),'UI',f'1.2.840.999.{i}.100'),((32,14),'UI',f'1.2.840.999.{i}.200'),((32,19),'IS',100-k),((32,50),'DS',f'0\\0\\{k*2 if z is None else z}'),((32,55),'DS',orientation),((32,82),'UI',f'1.2.840.999.{i}.300'),((40,2),'US',1),((40,4),'CS','MONOCHROME2'),((40,16),'US',2),((40,17),'US',3),((40,48),'DS','0.7\\0.8'),((40,256),'US',16),((40,257),'US',12),((40,258),'US',11),((40,259),'US',1),((40,4178),'DS',-1000),((40,4179),'DS',2),((40,4180),'LO','HU')]
    body=b''.join(element(t,v,x,not implicit) for t,v,x in fields)
    pixels=np.array([-1,0,1,2,3,4],dtype=np.int16)+k*10;raw=(pixels.astype(np.uint16)&4095).astype('<u2').tobytes()
    phead=struct.pack('<HH',0x7fe0,16)+(struct.pack('<I',len(raw)) if implicit else b'OW\0\0'+struct.pack('<I',len(raw)))
    prefix=b'\0'*128+b'DICM'+meta+body+phead
    return prefix+raw,len(prefix),pixels.reshape(2,3)


def fixture(tmp_path,collision=False):
    request=generated_request();payloads={};expected={}
    for i,c in enumerate(request['candidates'],1):
        for k in (1,0):
            name=c['directory']+f'/reverse-{1-k}.dcm';raw,prefix,pixels=dicom(i,k,implicit=i%2==0,patient='SAME' if collision and i<=2 else None);payloads[name]=raw;expected[name]=(prefix,pixels)
    archive=tmp_path/'generated-only.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in payloads.items():z.writestr(name,data)
        z.writestr('Clinical-data.csv',b'GENERATED_FORBIDDEN_BODY')
    with zipfile.ZipFile(archive) as z:
        rows={i.filename:dict(name=i.filename,compression_method=i.compress_type,compressed_bytes=i.compress_size,uncompressed_bytes=i.file_size,crc32=i.CRC,header_offset=i.header_offset) for i in z.infolist()}
    inv=tmp_path/'inventory.jsonl';inv.write_text(''.join(json.dumps(x)+'\n' for x in rows.values()));receipt=tmp_path/'generated-a0.json';receipt.write_text('{}')
    st=archive.stat();request['source_archive'].update(path=str(archive),bytes=st.st_size,receipt_path=str(receipt),receipt_sha256=a1.sha(receipt),stat_binding={'device':st.st_dev,'inode':st.st_ino,'mtime_ns':st.st_mtime_ns});request['inventory_binding'].update(path=str(inv),sha256=a1.sha(inv))
    for c in request['candidates']:
        c['members']=[r for name,r in rows.items() if name.startswith(c['directory']+'/')];c['dicom_member_count']=len(c['members'])
    request['requests'][0]['caps'].update(members=12,disk_free_floor_bytes=0)
    request['requests'][1]['caps'].update(members=12,disk_free_floor_bytes=0,preflight_free_bytes=0)
    return request,payloads,expected


def test_prefix_boundary_whitelist_and_implicit_explicit(tmp_path):
    r,payloads,expected=fixture(tmp_path);caps=r['requests'][0]['caps']
    for candidate in r['candidates']:
        row=candidate['members'][0];b=a1.Budget(caps);stream=a1.Member(r['source_archive']['path'],row,b,caps['inflated_header_prefix_bytes_per_member'])
        try:
            h=a1.parse_header(stream,a1.whitelist(r),caps)
            assert stream.emitted==expected[row['name']][0]
            assert h['header_sha256']==hashlib.sha256(payloads[row['name']][:stream.emitted]).hexdigest()
            assert 'PatientName' not in h['values'] and 'GENERATED_NAME_NEVER_RETAIN' not in json.dumps(h)
            assert h['pixel_length']==12
        finally:stream.close()


def test_same_entry_generated_end_to_end_sorted_pixels_and_meter(tmp_path):
    r,_,expected=fixture(tmp_path);out=tmp_path/'run';receipt=a1.pipeline(r,out,True)
    assert receipt['status']=='A1_COMPLETE_ELIGIBLE_SUBSET',receipt
    assert receipt['stages']['A1b']['decoded_directories']==6
    assert receipt['stages']['A1b']['QA_PNG_count']==12
    manifest=json.loads((out/'canonical-manifest.json').read_text())
    for c in manifest['cases']:
        p=out/c['candidate_id'];case=json.loads((p/'case.json').read_text());stored=np.load(p/'stored.npy');scaled=np.load(p/'rescaled.npy')
        assert case['geometry']['actual_spacing_mm']=={'slice_median':2.0,'slice_min':2.0,'slice_max':2.0,'row':.7,'column':.8}
        np.testing.assert_array_equal(stored[0],np.array([-1,0,1,2,3,4]).reshape(2,3))
        np.testing.assert_array_equal(scaled,stored.astype(np.float32)*2-1000)
        assert sum(x.stat().st_size for x in p.iterdir())==c['budget']['output_bytes']
    assert all(row['patient_group_status']=='UNKNOWN' for row in manifest['weak_records'])
    assert 'torch' not in sys.modules


def test_identity_collision_blocks_entire_pixel_stage(tmp_path):
    r,_,_=fixture(tmp_path,collision=True);out=tmp_path/'run';receipt=a1.pipeline(r,out,True)
    assert receipt['status']=='A1B_BLOCKED_IDENTITY_CONFLICT'
    assert not list(out.glob('*/stored.npy*'))
    discovery=json.loads((out/'a1a-discovery.json').read_text());assert discovery['member_accounted_count']==12 and discovery['identity_conflicts']


def test_header_only_stage_does_not_publish_pixels(tmp_path):
    r,_,_=fixture(tmp_path);out=tmp_path/'run';receipt=a1.pipeline(r,out,False)
    assert receipt['status']=='A1A_DISCOVERY_COMPLETE_A1B_NOT_APPROVED'
    assert not list(out.glob('*/stored.npy*'))


def test_geometry_rejections_and_inverse(tmp_path):
    r,_,_=fixture(tmp_path);caps=r['requests'][0]['caps'];headers=[]
    for row in r['candidates'][0]['members']:
        s=a1.Member(r['source_archive']['path'],row,a1.Budget(caps),caps['inflated_header_prefix_bytes_per_member'])
        try:headers.append(a1.parse_header(s,a1.whitelist(r),caps))
        finally:s.close()
    geom=a1.geometry(headers,r['requests'][1]['caps']);a=np.array(geom['native_k_row_col_to_LPS']);inv=np.array(geom['LPS_to_native_k_row_col']);np.testing.assert_allclose(a@inv,np.eye(4),atol=1e-12)
    for key,value in [('ImagePositionPatient',[0,0,0]),('ImageOrientationPatient',[1,0,0,1,0,0]),('PixelSpacing',[0,.8]),('SeriesInstanceUID','1.2.3.99'),('TemporalPositionIdentifier',2)]:
        bad=copy.deepcopy(headers);bad[0]['values'][key]=value
        with pytest.raises(a1.HeaderError):a1.geometry(bad,r['requests'][1]['caps'])


def test_unsupported_syntax_never_reaches_pixel_value(tmp_path):
    r,_,_=fixture(tmp_path);row=r['candidates'][0]['members'][0];caps=r['requests'][0]['caps'];s=a1.Member(r['source_archive']['path'],row,a1.Budget(caps),caps['inflated_header_prefix_bytes_per_member'])
    # Exercise the actual parser on generated unsupported TS, not a real file.
    raw,prefix,_=dicom(7,0);old=b'1.2.840.10008.1.2.1';raw=raw.replace(old,b'1.2.840.10008.1.2.5')
    class Memory:
        emitted=0
        hash=hashlib.sha256()
        def read(self,n):
            value=raw[self.emitted:self.emitted+n];self.emitted+=n;self.hash.update(value);return value
        def skip(self,n):self.read(n)
    s.close();m=Memory()
    with pytest.raises(a1.HeaderError,match='UNSUPPORTED_TRANSFER'):a1.parse_header(m,a1.whitelist(r),caps)
    assert m.emitted<prefix


def test_zip_crc_and_prefix_budget_fail_closed(tmp_path):
    r,_,_=fixture(tmp_path);row=r['candidates'][0]['members'][0];caps=r['requests'][0]['caps']
    s=a1.Member(r['source_archive']['path'],row,a1.Budget(caps),100)
    with pytest.raises(a1.GuardError):s.read(132)
    assert s.emitted==0;s.close()
    # Stored synthetic member with a post-header corruption; local CRC remains.
    raw,prefix,_=dicom(1,0);p=tmp_path/'crc.zip'
    with zipfile.ZipFile(p,'w',zipfile.ZIP_STORED) as z:z.writestr('generated.dcm',raw)
    with zipfile.ZipFile(p) as z:
        i=z.infolist()[0];row=dict(name=i.filename,compression_method=0,compressed_bytes=i.compress_size,uncompressed_bytes=i.file_size,crc32=i.CRC,header_offset=i.header_offset)
    data=bytearray(p.read_bytes());data[30+len('generated.dcm')+len(raw)-1]^=1;p.write_bytes(data)
    b=a1.Budget(r['requests'][1]['caps']);s=a1.Member(p,row,b,1024**2)
    try:
        with pytest.raises(a1.GuardError,match='CRC'):s.finish()
    finally:s.close()


def test_output_limit_preserves_parts_and_does_not_publish(tmp_path):
    r,_,_=fixture(tmp_path);r['requests'][1]['caps']['output_bytes_total']=128*1024+100;receipt=a1.pipeline(r,tmp_path/'run',True)
    assert receipt['status']=='FAILED' and 'OUTPUT' in receipt['failure']
    assert not (tmp_path/'run/canonical-manifest.json').exists()


def test_source_stat_drift_is_rejected_without_member_read(tmp_path):
    r,_,_=fixture(tmp_path);r['source_archive']['stat_binding']['mtime_ns']-=1
    with pytest.raises(a1.GuardError,match='DRIFT'):a1.open_bound_archive(r)


def test_sequence_is_rejected_before_embedded_pixel_inflation(tmp_path):
    r,_,_=fixture(tmp_path);raw,prefix,_=dicom(1,0)
    start=132
    # File-meta ends just before the first dataset tag. Insert an explicit SQ
    # before the ordinary dataset, containing generated pixel-looking bytes.
    for _ in range(3):
        vr=raw[start+4:start+6].decode();n=struct.unpack('<H',raw[start+6:start+8])[0];start+=8+n
    embedded=b'GENERATED_ICON_PIXEL_VALUE';sequence=struct.pack('<HH',0x0088,0x0200)+b'SQ\0\0'+struct.pack('<I',len(embedded));new=raw[:start]+sequence+embedded+raw[start:]
    class Memory:
        emitted=0
        hash=hashlib.sha256()
        def read(self,n):
            value=new[self.emitted:self.emitted+n];self.emitted+=n;self.hash.update(value);return value
        def skip(self,n):self.read(n)
    s=Memory()
    with pytest.raises(a1.HeaderError,match='SEQUENCE'):a1.parse_header(s,a1.whitelist(r),r['requests'][0]['caps'])
    assert s.emitted==start+len(sequence)


def test_opened_archive_identity_and_symlink_refused(tmp_path):
    r,_,_=fixture(tmp_path);row=r['candidates'][0]['members'][0];caps=r['requests'][0]['caps']
    old=copy.deepcopy(r['source_archive']);old['stat_binding']['inode']+=1
    with pytest.raises(a1.GuardError,match='OPEN_STAT_DRIFT'):
        a1.Member(old['path'],row,a1.Budget(caps),131072,old)
    alias=tmp_path/'alias.zip';alias.symlink_to(r['source_archive']['path'])
    with pytest.raises(OSError):a1.Member(alias,row,a1.Budget(caps),131072,r['source_archive'])


def test_cli_check_only_and_missing_approval_never_open_archive(monkeypatch,capsys):
    request={'source_archive':{'path':'GENERATED_MUST_NOT_OPEN'}}
    binding={'request_sha256':a1.APPLICATION_SHA}
    monkeypatch.setattr(a1,'bound_json',lambda path,digest: request if path=='generated-request' else binding)
    monkeypatch.setattr(a1,'verify_readiness',lambda value: None)
    def forbidden(*args,**kwargs):raise AssertionError('archive pipeline accessed')
    monkeypatch.setattr(a1,'pipeline',forbidden)
    args=['generated-cli','--request','generated-request','--request-sha256',a1.APPLICATION_SHA,'--readiness','generated-binding','--readiness-sha256','0'*64]
    monkeypatch.setattr(sys,'argv',args);a1.main()
    assert json.loads(capsys.readouterr().out)['status']=='CHECK_ONLY_NO_ARCHIVE_MEMBER_ACCESS'
    monkeypatch.setattr(sys,'argv',args+['--execute'])
    with pytest.raises(a1.GuardError,match='EXACT_OWNER_APPROVAL_REQUIRED'):a1.main()


def test_loaded_source_binding_drift_refused(tmp_path):
    from epi_next import a0_acquire,weak_records
    modules=[a1,a0_acquire,weak_records]
    binding={'source_bindings':[{'path':m.__file__,'sha256':'0'*64} for m in modules]}
    with pytest.raises(a1.GuardError,match='SOURCE_BINDING_DRIFT'):a1.verify_readiness(binding)
