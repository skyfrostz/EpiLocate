"""R76 increment only, generated Part10/native codec/stack/flow controls."""
import copy,io,json
from pathlib import Path
import numpy as np
import pydicom,pytest
from pydicom.encaps import encapsulate
from epi_next import research_import_v5 as bulk
from test_research_import import changed
from test_ri_hu_v5_precision import generated_frame


def generated(bits=12,high=11,values=None):
    values=np.array([[258,513,7],[8,9,10]] if values is None else values,dtype=np.uint16)
    ds=pydicom.dcmread(io.BytesIO(changed(BitsStored=bits,HighBit=high,RescaleType='HU',PixelRepresentation=0)))
    ds.Rows,ds.Columns=values.shape;ds.PixelData=encapsulate([generated_frame(values)])
    buf=io.BytesIO();pydicom.dcmwrite(buf,ds,enforce_file_format=True);return buf.getvalue(),values


def budget():return bulk.ri.diag.v1.Budget(dict(bulk.ri.codec.B,output_bytes_total=16*1024**2))


def test_complete_generated_frame_precision_and_once_rescale(tmp_path):
    raw,values=generated();arr,row=bulk.parse_frame(raw,tmp_path/'one',budget(),True,'NOT_EVALUATED')
    assert row['diagnostic']['primary_error'] is None
    np.testing.assert_array_equal(arr,values.astype(np.float32)*2-1000)
    assert row['precision']['comparison']['P']==16 and row['precision']['comparison']['BitsStored']==12
    assert row['qa']['scalar_rescale_applications']==1
    assert row['diagnostic']['counts']['as_buffer_api_returned']==1 and row['diagnostic']['counts']['as_array_api_entered']==0
    assert row['opaque_fingerprints'] and row['diagnostic']['source_identity_status']=='NOT_EVALUATED'


def test_outside_declared_range_retains_raw_and_stops(tmp_path):
    raw,_=generated(values=[[5000,513,7],[8,9,10]])
    arr,row=bulk.parse_frame(raw,tmp_path/'one',budget(),False,'NOT_EVALUATED')
    assert arr is None and row['diagnostic']['primary_error']['reason_code']=='DECODED_VALUE_SEMANTICS_UNRESOLVED'
    assert row['diagnostic']['value_semantics']['raw_max']==5000
    assert np.load(tmp_path/'one'/'decoded-buffer-diagnostic.npy').view('<u2')[0]==5000


def stack():
    frames=[np.full((64,64),i,dtype=np.float32) for i in range(64)]
    records=[{'IPP':[0,0,float(i)],'IOP':[1,0,0,0,1,0],'PixelSpacing':[.7,.7],'opaque_fingerprints':{}} for i in range(64)]
    return frames,records


def test_stack_reverse_sort_affine_no_resampling():
    f,r=stack();arr,g=bulk.ri.volume(f[::-1],r[::-1])
    assert arr[0,0,0]==0 and arr[-1,0,0]==63
    assert g['sorted_member_indices']==list(range(63,-1,-1)) and g['resampling']=='NONE'
    assert g['anatomical_complete']=='NOT_ESTABLISHED'


@pytest.mark.parametrize('problem',['duplicate','spacing','series','drift'])
def test_geometry_quarantines_without_fix(problem):
    f,r=stack()
    if problem=='duplicate':r[1]['IPP']=r[0]['IPP']
    if problem=='spacing':r[1]['IPP']=[0,0,1.2]
    if problem=='series':
        r[0]['opaque_fingerprints']={'SeriesInstanceUID':{'raw_value_sha256':'a'}};r[1]['opaque_fingerprints']={'SeriesInstanceUID':{'raw_value_sha256':'b'}}
    if problem=='drift':r[1]['IPP']=[.1,0,1]
    with pytest.raises(bulk.ri.Reject):bulk.ri.volume(f,r)


def test_output_cumulative_guard_counts_replacements(tmp_path):
    out=bulk.FrameOutput(tmp_path,budget(),used=2*1024**2-1)
    with pytest.raises(bulk.ri.Reject):out.write('generated.json',b'xx')
    assert not list(tmp_path.iterdir())


def test_first_failed_group_stops_all_and_keeps_reservation(tmp_path,monkeypatch):
    spec={'per_group_wall_seconds':30,'stage_wall_seconds':180,'caps':dict(compressed_input_bytes=20,inflated_member_bytes_total=20,output_bytes_total=20),
          'groups':[{'record_id':'a','source_group_id':'a','caps':dict(compressed_input_bytes=10,inflated_member_bytes_total=10,output_bytes_total=10)},{'record_id':'b','source_group_id':'b','caps':dict(compressed_input_bytes=10,inflated_member_bytes_total=10,output_bytes_total=10)}]}
    r={'active_stages':['RI-a','RI-b','RI-c'],'output_root':str(tmp_path/'out'),'stages':{s:copy.deepcopy(spec) for s in ('RI-a','RI-b','RI-c')},'overall_wall_seconds':90,'disk_free_floor_bytes':0,'receipt_bytes_max':1024**2}
    calls=[]
    def fail(*args,**kw):calls.append(args);raise RuntimeError('generated phase loss')
    monkeypatch.setattr(bulk.ri,'phase',fail)
    result=bulk.pipeline(r)
    assert len(calls)==1 and result['status']=='PARTIAL_STOPPED_NO_RETRY'
    assert result['stages']['RI-a']['reserved_attempt_upper_bounds']['compressed_input_bytes']==10
    assert result['stages']['RI-c']['rows'][0]['research_status']=='NOT_RUN'



def test_cross_split_pixel_duplicate_isolates_both_groups():
    base=dict(PIXEL_QA='PASS',RESCALE_QA='PASS_DECLARED_HU',PROVENANCE_BOUND=True,publisher_group_evidence_bound=True,source_diagnosis='COVID-19',task_label=1,GEOMETRY_QA='PASS_COMPLETE_SELECTED_STACK',source_group_fingerprints={})
    a=dict(base,source_group_id='a',native_volume_sha256='va',split='train_weak',frame_ledgers=[{'full_member_sha256':'aa','HU_array_sha256':'same','opaque_fingerprints':{}}])
    b=dict(base,source_group_id='b',native_volume_sha256='vb',split='val_classification',frame_ledgers=[{'full_member_sha256':'bb','HU_array_sha256':'same','opaque_fingerprints':{}}])
    bulk.bind_groups([a,b])
    assert a['training_eligible'] is b['training_eligible'] is False
    assert a['cross_group_duplicate_audit']==b['cross_group_duplicate_audit']=='CONFLICT'


def test_generated_complete64_zip_to_native_volume(tmp_path):
    import zipfile
    archive=tmp_path/'generated.zip';ds=pydicom.dcmread(io.BytesIO(generated()[0]))
    yy,xx=np.indices((64,64));members=[]
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for i in range(64):
            arr=(yy+xx+i+1).astype(np.uint16);ds.Rows=ds.Columns=64;ds.ImagePositionPatient=[0,0,float(i)]
            ds.SOPInstanceUID=ds.file_meta.MediaStorageSOPInstanceUID=f'1.2.3.{i+1}'
            ds.PixelData=encapsulate([generated_frame(arr)])
            buf=io.BytesIO();pydicom.dcmwrite(buf,ds,enforce_file_format=True);z.writestr(f'generated/IM{i:04d}.dcm',buf.getvalue())
        for info in z.infolist():members.append(dict(name=info.filename,compression_method=info.compress_type,compressed_bytes=info.compress_size,uncompressed_bytes=info.file_size,crc32=info.CRC,header_offset=info.header_offset))
    inventory=tmp_path/'inventory.jsonl';inventory.write_text('\n'.join(json.dumps(m) for m in members));receipt=tmp_path/'generated-receipt.json';receipt.write_text('{}')
    st=archive.stat();req={'source_archive':dict(path=str(archive),version='GENERATED_ONLY',sha256=bulk.old.sha(archive),bytes=st.st_size,stat_binding=dict(device=st.st_dev,inode=st.st_ino,mtime_ns=st.st_mtime_ns),receipt_path=str(receipt),receipt_sha256=bulk.old.sha(receipt)),
        'inventory_binding':dict(path=str(inventory),sha256=bulk.old.sha(inventory)),'full_member_bytes_max':1024**2,'A3_known_nonconformant_members':[]}
    group=dict(record_id='generated-group',source_group_id='generated-group',directory='generated',members=members,A3_seed_identity_nonconformant=False,source_diagnosis='CAP',task_label=1,split='train_weak',label_provenance={'GENERATED_ONLY':True})
    caps=dict(bulk.ri.codec.B,compressed_input_bytes=16*1024**2,inflated_member_bytes_total=16*1024**2,output_bytes_total=64*1024**2)
    out=tmp_path/'output';out.mkdir();row=bulk.group_worker(req,group,out,caps,True,False)
    assert row['GEOMETRY_QA']=='PASS_COMPLETE_SELECTED_STACK',row.get('primary_error')
    assert len(row['frame_ledgers'])==64 and row['tensor_artifact']['shape']==[64,64,64]
    assert sum(r['qa']['scalar_rescale_applications'] for r in row['frame_ledgers'])==64
    native=np.load(row['tensor_artifact']['path']);assert native[63,0,0]==64*2-1000
    assert row['budget']['output_bytes']>native.nbytes and row['geometry_ledger']['sha256']==bulk.old.sha(row['geometry_ledger']['path'])


def test_generated_exact60_publisher_reuses_six_pilots(tmp_path,monkeypatch):
    # Fresh generated metadata, independent of excluded historical receipts.
    import hashlib
    source=[]
    for split,counts in [('train_weak',{'COVID-19':10,'CAP':10,'Normal':20}),('val_classification',{'COVID-19':5,'CAP':5,'Normal':10})]:
        for diagnosis,count in counts.items():
            for _ in range(count):
                i=len(source);sha=hashlib.sha256(f'GENERATED_ONLY_{i}'.encode()).hexdigest()
                source.append(dict(record_id=f'SYN_{i}',source_group_id=f'SYN_SOURCE_{i}',split=split,
                    source_diagnosis=diagnosis,task_label=int(diagnosis!='Normal'),label_provenance={'kind':'GENERATED_FIXTURE_ONLY'},
                    tensor_artifact=dict(path=str(tmp_path/f'not-read-{i}.npy'),sha256=sha,shape=[64]*3),
                    geometry_ledger=dict(path=str(tmp_path/f'not-read-{i}.json'),sha256=sha),
                    affine_LPS=np.eye(4).tolist(),spacing_ZYX_mm=[1,1,1],source_dicom_identity_status='NOT_EVALUATED',
                    PIXEL_QA='PASS',RESCALE_QA='PASS_DECLARED_HU',PROVENANCE_BOUND=True,GEOMETRY_QA='PASS_COMPLETE_SELECTED_STACK'))
    by_group={r['source_group_id']:r for r in source}
    groups=[dict(record_id=r['record_id'],source_group_id=r['source_group_id'],split=r['split'],caps=dict(compressed_input_bytes=1,inflated_member_bytes_total=1,output_bytes_total=1)) for r in source]
    def spec(g):return dict(groups=g,per_group_wall_seconds=30,stage_wall_seconds=1800,caps=dict(compressed_input_bytes=60,inflated_member_bytes_total=60,output_bytes_total=60,wall_seconds=1800,RSS_stop_bytes=2*1024**3))
    req=dict(active_stages=['RI-a','RI-b','RI-c'],output_root=str(tmp_path/'output'),overall_wall_seconds=1800,disk_free_floor_bytes=0,receipt_bytes_max=64*1024**2,consumer_bytes_max=1024**2,stages={'RI-a':spec(groups[:6]),'RI-b':spec(groups[:6]),'RI-c':spec(groups)})
    calls=[]
    def fake_phase(fn,args,*_,**kw):
        group=args[1];single=args[-1];calls.append(group['source_group_id']);row=copy.deepcopy(by_group[group['source_group_id']]);row.update(frame_ledgers=[],native_volume_sha256=row['tensor_artifact']['sha256'],source_group_fingerprints={},publisher_group_evidence_bound=True,training_eligible=False,budget={})
        if single:row['research_status']='LIMITED_SINGLE_FRAME'
        return row
    monkeypatch.setattr(bulk.ri,'phase',fake_phase)
    result=bulk.pipeline(req);published=json.loads(Path(result['consumer_binding']['path']).read_text())
    assert len(published)==60 and len(calls)==66 and len({r['source_group_id'] for r in published})==60
    assert sum(r['split']=='train_weak' for r in published)==40
    assert all('slice_label' not in r and r['label_definition_id']=='MD_SOURCE_DIAGNOSIS_WEAK_V1' for r in published)
    assert all(r['rescale_policy']=='V5_VERIFIED_EXPLICIT_OR_DICOM_CONDITIONAL_HU_NO_SOURCE_FALLBACK' for r in published)


def test_partial_uid_presence_quarantines_series():
    f,r=stack()
    r[0]['opaque_fingerprints']={'SeriesInstanceUID':{'status':'PRESENT_OPAQUE','raw_value_sha256':'same'}}
    r[1]['opaque_fingerprints']={'SeriesInstanceUID':{'status':'ABSENT','raw_value_sha256':None}}
    records=[{'opaque_fingerprints':x['opaque_fingerprints']} for x in r]
    with pytest.raises(bulk.ri.Reject,match='INCONSISTENT_OPAQUE_SERIES_IDENTITY_STATUS'):
        bulk.validate_series_identity(records)
    bulk.validate_series_identity([{'opaque_fingerprints':{}} for _ in range(2)])
