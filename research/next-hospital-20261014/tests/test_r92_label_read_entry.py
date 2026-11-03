"""Generated ZIP/CSV/NPY/DICOM fixtures only; no real payloads or networking."""
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import zipfile

import numpy as np
import pytest
from epi_next import r92_label_read_entry as entry
from test_a3_structure_audit import element,part10,pixel,Guarded,sq,item


def write(path,data):
    path.write_text(json.dumps(data));return {'path':str(path),'sha256':entry.old.sha(path)}


def bundle(tmp_path,semantics=True):
    f=io.BytesIO();np.save(f,np.array([[1,0,0,0,0,0,0,1]],dtype='uint8'))
    data={'Index.csv':b'class,subject,row\nGENERATED,A,0\n','Slice-level-labels.npy':f.getvalue()}
    for i in range(8):
        data[f'GENERATED/A/{i}.dcm']=part10(element((32,0x1041),'DS',f'{i*2:02} '.encode()+b' ')+pixel())
    archive=tmp_path/'generated.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in data.items():z.writestr(name,raw)
    with zipfile.ZipFile(archive) as z:
        members=[{'name':i.filename,'compression_method':i.compress_type,'compressed_bytes':i.compress_size,
                  'uncompressed_bytes':i.file_size,'crc32':i.CRC,'header_offset':i.header_offset} for i in z.infolist()]
    inv=tmp_path/'inventory.jsonl';inv.write_text(''.join(json.dumps(x)+'\n' for x in members))
    receipt=tmp_path/'a0.json';receipt.write_text('{}');st=archive.stat()
    source={'path':str(archive),'bytes':st.st_size,'stat_binding':{'device':st.st_dev,'inode':st.st_ino,'mtime_ns':st.st_mtime_ns},'receipt_path':str(receipt),'receipt_sha256':entry.old.sha(receipt)}
    base={'source_archive':source,'inventory_binding':{'path':str(inv),'sha256':entry.old.sha(inv)},
          'stages':{'RI-c':{'groups':[{'source_group_id':'G','members':members[2:]}]}}}
    ledger={'frame_ledgers':[{'member_index':i,'full_member_sha256':hashlib.sha256(data[f'GENERATED/A/{i}.dcm']).hexdigest(),
                             'IPP':[0,0,i*2]} for i in range(8)],
            'affine_LPS':[[0,0,1,0],[0,1,0,0],[2,0,0,0],[0,0,0,1]]}
    group={'source_group_id':'G','source_subject_directory':'GENERATED/A','task_label':1,
           'split':'train_weak','depth':8,'fixed8':list(range(8)),
           'geometry_binding':write(tmp_path/'ledger.json',ledger),'native_order_to_frame_ordinal':list(range(8))}
    req={'schema':'R92_DATA_LABEL_READER_EXECUTABLE_V1','caps':entry.CAPS if semantics else entry.AB_CAPS,'source_bindings':[],
         'runtime_sha256':entry.old.sha(sys.executable),'output_root':str(tmp_path/'output'),
         'audit':write(tmp_path/'audit.json',{'rows':[group]}),'original_batch_request':write(tmp_path/'batch.json',base),
         'label_members':members[:2],'run_discovery':True,'semantics':None}
    if semantics:
        proof=write(tmp_path/'proof.json',{'GENERATED_ONLY':True})
        ev={k:proof for k in ('publisher_order','index_base','version','row_extent','source_subject_binding')}
        ev.update(index={'path':'GENERATED_MEMBER_Index','sha256':hashlib.sha256(data['Index.csv']).hexdigest()},
                  labels={'path':'GENERATED_MEMBER_NPY','sha256':hashlib.sha256(data['Slice-level-labels.npy']).hexdigest()},
                  label_version_resolved=True,order_policy='SLICE_LOCATION_ASCENDING')
        req['semantics']=write(tmp_path/'semantics.json',{'index_columns':{'diagnosis':'class','subject':'subject','annotation_index':'row'},'index_base':0,'evidence':ev,'row_extents':{'0':8}})
    app={'schema':'R92_DATA_LABEL_READ_APPROVAL_V1','request_sha256':'GENERATED_SHA','permit_A':True,'permit_B':True,'permit_C':semantics,'permit_pixels':False,'permit_models':False,'retry':False}
    return req,app,data


def test_actual_entry_generated_abc_and_no_clobber(tmp_path,monkeypatch):
    req,app,_=bundle(tmp_path);monkeypatch.setattr(entry,'discover',lambda:[])
    result=entry.run(req,'GENERATED_SHA',app)
    saved=json.loads(Path(result['receipt_path']).read_text())
    assert saved['status']=='EVALUATION_REGISTRY_COMPLETE_WITH_UNKNOWN'
    assert saved['header_members_read']==8 and saved['pixel_value_reads']==0
    assert saved['registry'][0]['rows'][0]['fixed8_known_positive']==2
    with pytest.raises(FileExistsError):entry.run(req,'GENERATED_SHA',app)


def test_check_only_and_approval_gate_do_not_open_archive(tmp_path,monkeypatch):
    req,app,_=bundle(tmp_path)
    monkeypatch.setattr(entry.old,'open_bound_archive',lambda *_:pytest.fail('ARCHIVE_OPEN'))
    monkeypatch.setattr(entry,'discover',lambda:pytest.fail('NETWORK'))
    assert entry.run(req,'GENERATED_SHA')['status'].startswith('CHECK_ONLY')
    app['permit_pixels']=True
    with pytest.raises(ValueError,match='APPROVAL'):entry.run(req,'GENERATED_SHA',app)
    assert not Path(req['output_root']).exists()


def test_unknown_semantics_is_normal_stop_no_header(tmp_path,monkeypatch):
    req,app,_=bundle(tmp_path,False);monkeypatch.setattr(entry,'discover',lambda:[])
    monkeypatch.setattr(entry,'location',lambda *_:pytest.fail('HEADER_READ'))
    result=entry.run(req,'GENERATED_SHA',app)
    saved=json.loads(Path(result['receipt_path']).read_text())
    assert saved['status']=='UNKNOWN_SEMANTICS_NO_PAIRING'


@pytest.mark.parametrize('defect',['object','oversize_header','bad_value','trailing'])
def test_npy_faults_before_unsafe_load(defect):
    f=io.BytesIO()
    if defect=='object':np.save(f,np.array([['x']],dtype=object))
    elif defect=='oversize_header':
        np.lib.format.write_array_header_1_0(f,{'descr':'|u1','fortran_order':False,'shape':(1000000000,1000000000)})
    else:np.save(f,np.array([[2 if defect=='bad_value' else 1]],dtype='uint8'))
    with pytest.raises(ValueError):entry.parse_labels(f.getvalue()+(b'x' if defect=='trailing' else b''))


def test_crc_and_stat_and_member_budget_faults(tmp_path):
    req,_,_=bundle(tmp_path);base=entry.read_bound(req['original_batch_request']);m=req['label_members'][0]
    b=entry.old.Budget(entry.CAPS);bad=copy.deepcopy(m);bad['crc32']+=1
    with pytest.raises(ValueError):entry.payload(base['source_archive']['path'],bad,b,base['source_archive'])
    badsource=copy.deepcopy(base['source_archive']);badsource['stat_binding']['inode']+=1
    with pytest.raises(ValueError,match='STAT_DRIFT'):entry.payload(base['source_archive']['path'],m,b,badsource)
    with pytest.raises(ValueError,match='COMPRESSED_LIMIT'):
        entry.LimitedMember(base['source_archive']['path'],m,b,8192,compressed_cap=1)


@pytest.mark.parametrize('nested',[False,True])
def test_pixel_boundary_guard_and_nested_does_not_pair(nested):
    loc=element((32,0x1041),'DS',b'2 ')
    raw=part10(sq(item(loc+pixel(),True),True) if nested else loc+pixel())
    stream=Guarded(raw,raw.index(b'GENERATED_PIXEL_VALUE_FORBIDDEN'))
    walker=entry.LocationWalker(stream,{},entry.structural.CAPS);r=walker.run()
    assert stream.emitted==stream.forbidden
    assert (walker.location is None) == nested
    assert r['stop_code']==('NESTED_PIXEL_VALUE_BOUNDARY' if nested else 'ROOT_PIXEL_VALUE_BOUNDARY')


def test_index_ambiguity_and_missing_column_rejected():
    semantics={'index_columns':{'diagnosis':'class','subject':'subject','annotation_index':'row'},'index_base':0}
    for raw in (b'class,subject,row\nC,A,0\nC,A,1\n', b'other\nunknown\n'):
        with pytest.raises(ValueError):entry.parse_index(raw,semantics,[])


def test_unlisted_member_failure_receipt_preserved(tmp_path,monkeypatch):
    req,app,_=bundle(tmp_path);monkeypatch.setattr(entry,'discover',lambda:[])
    req['label_members'][0]['name']='Clinical-data.csv'
    with pytest.raises(ValueError,match='EXACT_LABEL'):entry.run(req,'GENERATED_SHA',app)
    saved=json.loads((Path(req['output_root'])/'receipt.json').read_text())
    assert saved['status']=='FAILED_STOP_NO_RETRY' and saved['pixel_decodes']==0


def test_source_drift_rejected_before_claim(tmp_path):
    req,app,_=bundle(tmp_path);req['source_bindings']=[{'path':str(tmp_path/'a0.json'),'sha256':'0'*64}]
    with pytest.raises(ValueError,match='SOURCE_DRIFT'):entry.run(req,'GENERATED_SHA',app)
    assert not Path(req['output_root']).exists()


def test_duplicate_location_is_not_a_valid_root_boundary():
    raw=part10(element((32,0x1041),'DS',b'2 ')+element((32,0x1041),'DS',b'4 ')+pixel())
    s=Guarded(raw,raw.index(b'GENERATED_PIXEL_VALUE_FORBIDDEN'));w=entry.LocationWalker(s,{},entry.structural.CAPS)
    assert w.run()['stop_code']=='DUPLICATE_OR_REVERSED_TAG_ORDER'
    assert s.emitted < s.forbidden


def test_discovery_byte_limit_is_fatal_not_retry(monkeypatch):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def read(self,n):return b'x'*n
    class Opener:
        def open(self,*args,**kwargs):return Response()
    monkeypatch.setattr(entry.urllib.request,'build_opener',lambda *_:Opener())
    with pytest.raises(ValueError,match='DISCOVERY_BYTE_LIMIT'):entry.discover()


def test_budget_before_inflation(tmp_path):
    req,_,_=bundle(tmp_path);base=entry.read_bound(req['original_batch_request'])
    caps=dict(entry.CAPS);caps['inflated_header_prefix_bytes_total']=1
    with pytest.raises(ValueError,match='INFLATED_LIMIT'):
        entry.payload(base['source_archive']['path'],req['label_members'][0],entry.old.Budget(caps),base['source_archive'])


def test_existing_serial_dispatch_is_required_and_bound():
    req={'spec':{'task_key':'GENERATED_TASK'}}
    d={'status':'EXCLUSIVE_SLOT_ASSIGNED','launch_release':'RELEASED_BY_CHIEF',
       'request_sha256':'SHA','approval_sha256':'APP','task_key':'GENERATED_TASK','owner':'DATA','retry':False}
    entry.validate_dispatch(req,'SHA','APP',d)
    for key in ('request_sha256','approval_sha256','launch_release','task_key','owner'):
        bad=dict(d);bad[key]='WRONG'
        with pytest.raises(ValueError,match='DISPATCH'):entry.validate_dispatch(req,'SHA','APP',bad)


def test_small_payload_cache_reusable_without_reopening_zip(tmp_path,monkeypatch):
    req,app,data=bundle(tmp_path,False);monkeypatch.setattr(entry,'discover',lambda:[])
    result=entry.run(req,'GENERATED_SHA',app)
    record=json.loads(Path(result['receipt_path']).read_text())
    for r in record['B']:
        assert Path(r['private_cache_path']).read_bytes()==data[r['name']]
        assert entry.old.sha(r['private_cache_path'])==r['sha256']
    assert entry.parse_labels((Path(req['output_root'])/'Slice-level-labels.npy').read_bytes()).shape==(1,8)
