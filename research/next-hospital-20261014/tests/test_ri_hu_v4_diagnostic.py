"""Real v4 worker/pipeline paths using generated members and fixed fake API."""
import copy,io,json,logging
from pathlib import Path
import numpy as np
import pytest
from epi_next import ri_hu_v4_diagnostic as v4
from test_a2_six_sop import fixture


SECRET='GENERATED_IDENTITY_UID_AND_PIXEL_BYTES_SECRET'
class FakeDecoder:
    available_plugins=('pylibjpeg',)
    def __init__(self,mode='success'):self.mode=mode;self.calls=0
    def as_array(self,ds,**kwargs):
        self.calls+=1;assert kwargs=={'decoding_plugin':'pylibjpeg'}
        assert 'RescaleSlope' not in ds and 'PatientID' not in ds
        if self.mode=='raise':
            try:raise ValueError(SECRET)
            except ValueError as exc:raise RuntimeError(SECRET) from exc
        shape=(2,3) if self.mode!='shape' else (3,2)
        dtype=np.uint16 if self.mode!='dtype' else np.float32
        array=np.arange(6,dtype=dtype).reshape(shape)
        return array,{'bits_allocated':16,'bits_stored':16 if self.mode!='precision' else 12}


def request(tmp_path):
    r=fixture(tmp_path);r.update(member=r['selection'][0]['member'],output_root=str(tmp_path/'out'),bound_source_HU_claim=False)
    return r


def run(tmp_path,mode='success',factory=None):
    r=request(tmp_path);Path(r['output_root']).mkdir();fake=FakeDecoder(mode)
    result=v4.audit(r,False,(lambda uid:fake) if factory is None else factory)
    return result,fake,r


def test_complete_generated_entry_normal_once(tmp_path):
    result,fake,r=run(tmp_path)
    assert result['status']=='SINGLE_FRAME_NUMERICAL_QA_COMPLETE'
    d=result['diagnostic'];assert d['primary_error'] is None
    assert d['counts']['decode_request']==d['counts']['decoder_api_entered']==d['counts']['decoder_api_returned']==fake.calls==1
    assert d['counts']['plugin_entered']==d['counts']['plugin_returned']=='UNKNOWN'
    assert d['integrity']['EOF_verified'] and d['integrity']['CRC_verified'] and d['integrity']['member_sha256']
    np.testing.assert_array_equal(np.load(result['artifacts'][1]['path']),np.arange(6,dtype=np.float32).reshape(2,3)*2-1000)


@pytest.mark.parametrize('mode,stage,entered,returned',[('raise','DECODER_API_CALL_RETURN',1,0),('shape','STORED_ARRAY_CHECK',1,1),('dtype','STORED_ARRAY_CHECK',1,1),('precision','STORED_ARRAY_CHECK',1,1)])
def test_actual_entry_distinguishes_decoder_and_post_return_failures(tmp_path,mode,stage,entered,returned):
    result,fake,_=run(tmp_path,mode)
    d=result['diagnostic'];assert result['status']=='STOPPED_NO_RETRY'
    assert d['primary_error']['failed_stage']==stage
    assert d['counts']['decoder_api_entered']==entered and d['counts']['decoder_api_returned']==returned
    assert fake.calls==1 and d['integrity']['CRC_verified'] and d['integrity']['member_sha256']
    assert d['primary_error']['code_locations'] and SECRET not in json.dumps(result)
    if mode=='raise':assert [x['class'] for x in d['primary_error']['type_chain']]==['RuntimeError','ValueError']


def test_missing_plugin_actual_entry_does_not_call_decoder(tmp_path):
    fake=FakeDecoder();fake.available_plugins=()
    result,_,_=run(tmp_path,factory=lambda uid:fake)
    d=result['diagnostic'];assert d['failed_stage']=='FIXED_PLUGIN_ADMISSION'
    assert d['counts']['decoder_api_entered']==0 and fake.calls==0


def test_dataset_construction_failure_before_decoder(tmp_path,monkeypatch):
    from pydicom.dataset import Dataset
    original=Dataset.__setattr__
    def fail(self,key,value):
        if key=='PixelData':raise RuntimeError(SECRET)
        return original(self,key,value)
    r=request(tmp_path);Path(r['output_root']).mkdir()
    monkeypatch.setattr(Dataset,'__setattr__',fail)
    result=v4.audit(r,False,lambda uid:FakeDecoder())
    assert result['diagnostic']['failed_stage']=='MINIMAL_DATASET_CONSTRUCTION'
    assert result['diagnostic']['counts']['decoder_api_entered']==0 and SECRET not in json.dumps(result)


def test_encapsulation_failure_actual_entry(tmp_path,monkeypatch):
    import pydicom.encaps
    monkeypatch.setattr(pydicom.encaps,'generate_frames',lambda *a,**k:iter(()))
    result,_,_=run(tmp_path)
    assert result['diagnostic']['failed_stage']=='ENCAPSULATION_FRAME_EXTRACTION'
    assert result['diagnostic']['counts']['decoder_api_entered']==0


@pytest.mark.parametrize('target,stage',[('rescale','SINGLE_RESCALE'),('oracle','FP64_FP32_ORACLE')])
def test_late_rescale_or_oracle_failure_retains_integrity(tmp_path,monkeypatch,target,stage):
    if target=='oracle':monkeypatch.setattr(v4.v3,'check_rescale',lambda *a:(_ for _ in ()).throw(RuntimeError(SECRET)))
    else:
        class Broken(np.ndarray):
            def astype(self,*a,**k):raise RuntimeError(SECRET)
        class Decode(FakeDecoder):
            def as_array(self,*a,**k):array,props=super().as_array(*a,**k);return array.view(Broken),props
        factory=lambda uid:Decode()
    result,_,_=run(tmp_path,factory=factory if target=='rescale' else None)
    d=result['diagnostic'];assert d['failed_stage']==stage and d['counts']['decoder_api_returned']==1
    assert d['integrity']['CRC_verified'] and SECRET not in json.dumps(result)


def test_primary_not_overwritten_when_ledger_reporting_fails(tmp_path,monkeypatch,capsys):
    r=request(tmp_path)
    monkeypatch.setattr(v4,'phase',lambda fn,args,*rest:fn(*args))
    def bad_report(*a):raise OSError(SECRET)
    monkeypatch.setattr(v4.v3,'publish_ledger',bad_report)
    result=v4.pipeline(r,False,lambda uid:FakeDecoder('raise'))
    assert result['diagnostic']['primary_error']['class']=='RuntimeError'
    assert result['diagnostic']['reporting_error']['class']=='OSError'
    assert SECRET not in capsys.readouterr().out+json.dumps(result)


def test_child_logger_exception_is_redacted_through_actual_decoder_stage(tmp_path,capsys,caplog):
    original=logging.getLogRecordFactory();logger=logging.getLogger('pydicom.fresh_child_diagnostic')
    handler=logging.StreamHandler();logger.addHandler(handler)
    class LoggingDecoder(FakeDecoder):
        def as_array(self,*args,**kwargs):
            try:raise ValueError(SECRET)
            except ValueError:logger.exception(SECRET)
            return super().as_array(*args,**kwargs)
    try:result,_,_=run(tmp_path,factory=lambda uid:LoggingDecoder())
    finally:logger.removeHandler(handler)
    captured=capsys.readouterr()
    assert SECRET not in captured.out+captured.err+caplog.text+json.dumps(result)
    assert logging.getLogRecordFactory() is original


def test_field_conversion_error_actual_entry_preserves_tag_vr_length(tmp_path,monkeypatch):
    r=request(tmp_path);Path(r['output_root']).mkdir();original=v4.old.field_value
    def fail(raw,vr,key,values):
        if key=='RescaleSlope':raise ValueError(SECRET)
        return original(raw,vr,key,values)
    monkeypatch.setattr(v4.old,'field_value',fail)
    result=v4.audit(r,False,lambda uid:FakeDecoder())
    assert result['status']=='ISOLATED_NO_PIXEL_DECODE'
    d=result['diagnostic'];assert d['counts']['decode_request']==0
    assert d['field_errors'][0]['field']['keyword']=='RescaleSlope'
    assert d['field_errors'][0]['field']['VR']=='DS' and d['field_errors'][0]['field']['value_length']>0
    assert SECRET not in json.dumps(result)


def test_child_handler_propagate_false_and_last_resort_never_leak(tmp_path,capsys):
    logger=logging.getLogger('pydicom.private_child_propagate_false');before=logger.propagate;logger.propagate=False
    handler=logging.StreamHandler();logger.addHandler(handler)
    class Decoder(FakeDecoder):
        def as_array(self,*a,**k):
            try:raise RuntimeError(SECRET)
            except RuntimeError:logger.exception(SECRET)
            logger.removeHandler(handler)
            logger.error(SECRET)  # no handler: lastResort path
            return super().as_array(*a,**k)
    try:result,_,_=run(tmp_path,factory=lambda uid:Decoder())
    finally:logger.propagate=before;logger.removeHandler(handler)
    assert result['status']=='SINGLE_FRAME_NUMERICAL_QA_COMPLETE'
    output=capsys.readouterr();assert SECRET not in output.out+output.err


def test_unknown_unhashable_exception_args_do_not_break_primary(tmp_path):
    class Decoder(FakeDecoder):
        def as_array(self,*a,**k):raise v4.old.HeaderError([SECRET])
    result,_,_=run(tmp_path,factory=lambda uid:Decoder())
    assert result['diagnostic']['primary_error']['class']=='HeaderError'
    assert result['diagnostic']['primary_error']['reason_code']=='DECODER_API_CALL_RETURN_ERROR'
    assert SECRET not in json.dumps(result)


def rewrite_generated_member(tmp_path,r,raw):
    import zipfile
    archive=tmp_path/'generated-changed-only.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:z.writestr(r['member']['name'],raw)
    with zipfile.ZipFile(archive) as z:
        m=z.infolist()[0];r['member']={'name':m.filename,'compression_method':m.compress_type,'compressed_bytes':m.compress_size,'uncompressed_bytes':m.file_size,'crc32':m.CRC,'header_offset':m.header_offset}
    st=archive.stat();r['source_archive'].update(path=str(archive),bytes=st.st_size,stat_binding={'device':st.st_dev,'inode':st.st_ino,'mtime_ns':st.st_mtime_ns})
    inv=Path(r['inventory_binding']['path']);inv.write_text(json.dumps([r['member']]))
    r['inventory_binding']['sha256']=v4.old.sha(inv)


def test_empty_optional_field_has_descriptor_without_synthetic_exception(tmp_path):
    import pydicom
    from test_a2_six_sop import dicom
    r=request(tmp_path);Path(r['output_root']).mkdir()
    ds=pydicom.dcmread(io.BytesIO(dicom(1)[0]));ds.add_new(0x00280120,'US',None)
    memory=io.BytesIO();pydicom.dcmwrite(memory,ds,enforce_file_format=True)
    rewrite_generated_member(tmp_path,r,memory.getvalue())
    result=v4.audit(r,False,lambda uid:FakeDecoder())
    assert result['status']=='SINGLE_FRAME_NUMERICAL_QA_COMPLETE'
    d=result['diagnostic'];assert d['primary_error'] is None
    field=next(x for x in d['field_observations'] if x['keyword']=='PixelPaddingValue')
    assert field['state']=='EMPTY' and field['value_length']==0


def test_retained_original_numerical_semantics(tmp_path):
    result,_,_=run(tmp_path)
    qa=result['qa'];assert qa['stored_dtype']=='uint16' and qa['stored_shape']==[2,3]
    assert qa['per_instance_coefficients'] is True and qa['resampling']=='NONE'
    assert qa['padding_not_removed_from_raw_QA'] and qa['stored_finite'] and qa['rescaled_finite']
    assert (qa['stored_min'],qa['stored_max'],qa['rescaled_min'],qa['rescaled_max'])==(0,5,-1000,-990)


def test_real_supervised_pipeline_failure_roundtrip_and_ledger(tmp_path):
    r=request(tmp_path)
    result=v4.pipeline(r,False,lambda uid:FakeDecoder('raise'))
    saved=json.loads((Path(r['output_root'])/'single-frame-ledger-v3.json').read_text())
    for record in (result,saved):
        d=record['diagnostic'];assert d['primary_error']['class']=='RuntimeError'
        assert d['counts']['decoder_api_entered']==1 and d['counts']['decoder_api_returned']==0
        assert d['integrity']['CRC_verified'] is True and d['integrity']['member_sha256']
        assert SECRET not in json.dumps(record)
    assert sum(p.stat().st_size for p in Path(r['output_root']).iterdir())<=v4.CAPS['output_bytes_total']


def test_range_failure_actual_entry_after_fixed_fake_return(tmp_path):
    import pydicom
    from pydicom.encaps import generate_frames,encapsulate
    from test_a2_six_sop import dicom
    r=request(tmp_path);Path(r['output_root']).mkdir()
    ds=pydicom.dcmread(io.BytesIO(dicom(1)[0]));ds.BitsStored=12;ds.HighBit=11
    frame=bytearray(next(generate_frames(ds.PixelData,number_of_frames=1)));frame[frame.index(b'\xff\xc3')+4]=12
    ds.PixelData=encapsulate([bytes(frame)])  # fake API uses no entropy decoding
    memory=io.BytesIO();pydicom.dcmwrite(memory,ds,enforce_file_format=True);rewrite_generated_member(tmp_path,r,memory.getvalue())
    class Decoder(FakeDecoder):
        def as_array(self,*a,**k):self.calls+=1;return np.full((2,3),5000,dtype=np.uint16),{'bits_allocated':16,'bits_stored':12}
    result=v4.audit(r,False,lambda uid:Decoder())
    assert result['diagnostic']['primary_error']['reason_code']=='STORED_BITS_RANGE'
    assert result['diagnostic']['counts']['decoder_api_returned']==1


def test_vr_mismatch_real_entry_isolated_with_safe_field_descriptor(tmp_path):
    import pydicom
    from test_a2_six_sop import dicom
    r=request(tmp_path);Path(r['output_root']).mkdir()
    ds=pydicom.dcmread(io.BytesIO(dicom(1)[0]));ds.add_new(0x00281053,'LO','2.0')
    memory=io.BytesIO();pydicom.dcmwrite(memory,ds,enforce_file_format=True);rewrite_generated_member(tmp_path,r,memory.getvalue())
    result=v4.audit(r,False,lambda uid:FakeDecoder())
    assert result['status']=='ISOLATED_NO_PIXEL_DECODE'
    field=next(x for x in result['diagnostic']['field_observations'] if x['keyword']=='RescaleSlope')
    assert field['reason_code']=='FIELD_VR_MISMATCH' and field['VR']=='LO'
    assert result['diagnostic']['failed_stage']=='UNIT_INTERPRETATION'


def test_existing_real_api_generated_only_success(tmp_path):
    r=request(tmp_path);Path(r['output_root']).mkdir()
    result=v4.audit(r,False)
    assert result['status']=='SINGLE_FRAME_NUMERICAL_QA_COMPLETE',result
    assert result['diagnostic']['counts']['decoder_api_returned']==1
    assert result['diagnostic']['counts']['plugin_returned']=='UNKNOWN'


def test_logger_name_and_formatted_source_path_are_redacted(tmp_path,capsys):
    logger=logging.getLogger('pydicom.'+SECRET);old=logger.propagate;logger.propagate=False
    handler=logging.StreamHandler();handler.setFormatter(logging.Formatter('%(name)s|%(pathname)s|%(funcName)s|%(message)s'));logger.addHandler(handler)
    class Decoder(FakeDecoder):
        def as_array(self,*a,**k):logger.error(SECRET);return super().as_array(*a,**k)
    try:result,_,_=run(tmp_path,factory=lambda uid:Decoder())
    finally:logger.removeHandler(handler);logger.propagate=old
    assert result['status']=='SINGLE_FRAME_NUMERICAL_QA_COMPLETE'
    capture=capsys.readouterr();assert SECRET not in capture.out+capture.err
    assert 'CODE_LOCATION_REDACTED' in capture.err
