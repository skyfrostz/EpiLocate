"""Known generated JPEG arrays and targeted v5 flow/termination controls."""
import copy,io,json,os,struct,time
from pathlib import Path
import numpy as np
import pydicom
from pydicom.encaps import encapsulate
import pytest
from epi_next import ri_hu_v5_precision as v5
from test_a2_six_sop import jpeg,dicom,fixture
from test_ri_hu_v4_diagnostic import rewrite_generated_member


def generated_frame(values,precision=16):
    # Reuse the existing fixture encoder. Translation changes its first
    # predictor from 32768 to 2**(P-1); later deltas cancel the translation.
    values=np.asarray(values,dtype=np.uint16)
    translated=(values.astype(np.int64)+(32768-(1<<(precision-1)))).astype(np.uint16)
    frame=bytearray(jpeg(translated));frame[frame.index(b'\xff\xc3')+4]=precision
    return bytes(frame)


def values(bits=12):
    return {'Rows':2,'Columns':3,'SamplesPerPixel':1,'PhotometricInterpretation':'MONOCHROME2','BitsAllocated':16,'BitsStored':bits,'HighBit':bits-1,
            'PixelRepresentation':0,'RescaleSlope':2.,'RescaleIntercept':-1000.}


def run_process(tmp_path,array,precision=16,bits=12,probe=None,factory=None,frame=None):
    tmp_path.mkdir(exist_ok=True);t=v5.Trace(v5.Output(tmp_path));v=values(bits)
    t.precision['dicom']=v5.safe_dicom(v,{'NumberOfFrames':'ABSENT'})
    payload=encapsulate([generated_frame(array,precision) if frame is None else frame])
    result=v5.process(v,payload,t,probe,factory)
    return result,t


@pytest.mark.parametrize('precision,bits,array',[
 (16,16,[[258,513,4095],[1,2048,7]]),(16,12,[[258,513,4095],[1,2048,7]]),
 (10,12,[[100,258,513],[1,500,1023]])])
def test_real_native_codec_known_arrays_exact_no_unused_bit_correction(tmp_path,precision,bits,array):
    expected=np.array(array,dtype=np.uint16)
    (native,qa),t=run_process(tmp_path,expected,precision,bits)
    archived=np.load(tmp_path/'decoded-buffer-diagnostic.npy').view('<u2').reshape(2,3)
    np.testing.assert_array_equal(archived,expected)
    np.testing.assert_array_equal(native,expected.astype(np.float32)*2-1000)
    assert t.precision['jpeg']['P']==precision and t.precision['independent']['precision']==precision
    assert t.precision['comparison']['BitsStored']==bits
    assert t.counts['as_buffer_api_entered']==t.counts['as_buffer_api_returned']==1
    assert t.counts['native_parameter_probe_entered']==t.counts['native_parameter_probe_returned']==1
    assert t.value_semantics['outside_declared_count']==0


def test_5000_preserved_and_904_is_only_diagnostic_simulation(tmp_path):
    expected=np.array([[5000,4095,0],[1,258,513]],dtype=np.uint16)
    (native,qa),t=run_process(tmp_path,expected)
    assert native is None and qa is None
    archived=np.load(tmp_path/'decoded-buffer-diagnostic.npy').view('<u2').reshape(2,3)
    assert archived[0,0]==5000 and int(archived[0,0])&4095==904
    assert t.value_semantics['outside_declared_count']==1
    assert t.value_semantics['simulated_unused_bit_changed_count']==1 and t.value_semantics['simulated_unused_bit_max_difference']==4096
    assert t.value_semantics['status']=='DECODED_VALUE_SEMANTICS_UNRESOLVED'
    assert not list(tmp_path.glob('*rescaled*'))


def test_cross_container_p8_records_both_parameters_before_stop(tmp_path):
    with pytest.raises(v5.v3.v1.Reject):
        run_process(tmp_path,[[7,8,9],[10,11,12]],8,12,factory=lambda uid:pytest.fail('codec requested'))
    d=json.loads((tmp_path/'stage-checkpoint-v5.json').read_text())
    assert d['precision']['jpeg']['P']==8 and d['precision']['comparison']['BitsStored']==12
    assert d['primary_error']['reason_code']=='CONTAINER_PROFILE_UNSUPPORTED'
    assert d['counts']['as_buffer_request']==0


def test_parser_disagreement_no_codec_and_same_frame_hash(tmp_path):
    def disagree(frame):return {'precision':15,'rows':2,'columns':3,'nr_components':1}
    with pytest.raises(v5.v3.v1.Reject):run_process(tmp_path,[[258,513,7],[8,9,10]],probe=disagree,factory=lambda uid:pytest.fail('codec'))
    d=json.loads((tmp_path/'stage-checkpoint-v5.json').read_text())
    assert d['precision']['jpeg']['P']==16 and d['precision']['independent']['precision']==15
    assert d['precision']['frame']['sha256'] and d['counts']['as_buffer_request']==0


@pytest.mark.parametrize('change,code',[('length','JPEG_SEGMENT_LENGTH'),('marker','JPEG_PROFILE_NOT_SOF3'),('truncate','JPEG_EOI_REQUIRED'),('predictor','JPEG_SCAN_PROFILE')])
def test_structure_profile_evidence_before_error(tmp_path,change,code):
    frame=bytearray(generated_frame([[258,513,7],[8,9,10]]))
    if change=='length':pos=frame.index(b'\xff\xc3');frame[pos+2:pos+4]=b'\xff\xff'
    if change=='marker':frame[frame.index(b'\xff\xc3')+1]=0xc0
    if change=='truncate':frame=frame[:-2]
    if change=='predictor':frame[frame.index(b'\xff\xda')+7]=2
    record={}
    with pytest.raises(v5.old.HeaderError) as e:v5.jpeg_record(bytes(frame),record)
    assert e.value.args[0]==code
    if change!='length':assert record['P']==16 and record['SOF_offset']>=2


def test_app_skip_big_endian_offsets_without_app_text():
    frame=generated_frame([[258,513,7],[8,9,10]]);private=b'GENERATED_PRIVATE_APP_TEXT'
    app=b'\xff\xe1'+struct.pack('>H',len(private)+2)+private
    altered=frame[:2]+app+frame[2:];record={};v5.jpeg_record(altered,record)
    assert record['P']==16 and (record['Y'],record['X'])==(2,3)
    assert record['SOF_offset']==frame.index(b'\xff\xc3')+len(app)
    assert private.decode() not in json.dumps(record)


class FakeBuffer:
    available_plugins=('pylibjpeg',)
    def __init__(self,mode='raise'):self.mode=mode;self.calls=0
    def as_buffer(self,ds,**kwargs):
        self.calls+=1
        assert kwargs=={'index':0,'validate':True,'decoding_plugin':'pylibjpeg','allow_excess_frames':False}
        if self.mode=='exit':os._exit(71)
        if self.mode=='sleep':time.sleep(3)
        if self.mode=='raise':raise RuntimeError('GENERATED_SECRET_UID')
        raw=np.array([[258,513,7],[8,9,10]],dtype='<u2').tobytes()
        props={'bits_allocated':8 if self.mode=='properties' else 16,'bits_stored':12,'pixel_representation':0}
        return raw,props


def test_codec_error_parameters_persist_no_retry(tmp_path):
    fake=FakeBuffer()
    with pytest.raises(RuntimeError):run_process(tmp_path,[[258,513,7],[8,9,10]],factory=lambda uid:fake)
    d=json.loads((tmp_path/'stage-checkpoint-v5.json').read_text())
    assert fake.calls==1 and d['precision']['parser_agreement'] and d['counts']['as_buffer_api_returned']==0
    assert 'GENERATED_SECRET_UID' not in json.dumps(d)


def test_raw_saved_before_late_properties_failure(tmp_path):
    fake=FakeBuffer('properties')
    with pytest.raises(v5.v3.v1.Reject):run_process(tmp_path,[[258,513,7],[8,9,10]],factory=lambda uid:fake)
    d=json.loads((tmp_path/'stage-checkpoint-v5.json').read_text())
    assert (tmp_path/'decoded-buffer-diagnostic.npy').exists()
    assert d['counts']['as_buffer_api_returned']==1 and d['artifacts']


def worker_request(tmp_path):
    r=fixture(tmp_path);ds=pydicom.dcmread(io.BytesIO(dicom(1)[0]));ds.BitsStored=12;ds.HighBit=11
    ds.PixelData=encapsulate([generated_frame([[258,513,7],[8,9,10]])])
    memory=io.BytesIO();pydicom.dcmwrite(memory,ds,enforce_file_format=True)
    r.update(member=r['selection'][0]['member'],output_root=str(tmp_path/'out'),bound_source_HU_claim=False)
    rewrite_generated_member(tmp_path,r,memory.getvalue());r['expected_member_sha256']=__import__('hashlib').sha256(memory.getvalue()).hexdigest()
    return r


def test_actual_supervised_entry_success_and_durable_integrity(tmp_path):
    r=worker_request(tmp_path);result=v5.pipeline(r)
    assert result['status']=='SINGLE_FRAME_NUMERICAL_QA_COMPLETE',result
    d=result['diagnostic'];assert d['integrity']['CRC_verified'] and d['integrity']['member_sha256']==r['expected_member_sha256']
    assert d['precision']['metadata_consistency']=='CODESTREAM_METADATA_DISCREPANCY'
    assert (Path(r['output_root'])/'precision-ledger-v5.json').exists()


def test_actual_phase_exit_retains_parameters_request_and_unknown_return(tmp_path):
    r=worker_request(tmp_path);result=v5.pipeline(r,decoder_factory=lambda uid:FakeBuffer('exit'))
    assert result['status']=='STOPPED_NO_RETRY'
    d=result['diagnostic'];assert d['integrity']['CRC_verified'] and d['precision']['jpeg']['P']==16
    assert d['counts']['as_buffer_request']==1 and d['counts']['as_buffer_api_returned']=='UNKNOWN'
    assert d['inflight']['api']=='as_buffer'
    assert d['unit_interpretation']['unit_branch']=='EXPLICIT_HU'


def test_output_total_accounts_temporary_and_cumulative_replacements(tmp_path):
    out=v5.Output(tmp_path);out.used=v5.CAPS['output_bytes_total']-v5.OUTER_RESERVE-v5.LEDGER_RESERVE-4
    with pytest.raises(v5.v3.v1.Reject):out.write('control.json',b'12345')
    assert not list(tmp_path.iterdir())


def test_dims_conflict_and_signed_profile_stop_before_codec(tmp_path):
    frame=bytearray(generated_frame([[258,513,7],[8,9,10]]));pos=frame.index(b'\xff\xc3');frame[pos+5:pos+7]=struct.pack('>H',3)
    with pytest.raises(v5.v3.v1.Reject):run_process(tmp_path,[[258,513,7],[8,9,10]],frame=bytes(frame),factory=lambda uid:pytest.fail('codec'))
    d=json.loads((tmp_path/'stage-checkpoint-v5.json').read_text())
    assert d['precision']['comparison']['JPEG_dimensions'][0]==3 and d['primary_error']['reason_code']=='JPEG_DIMENSION_CONFLICT'
    other=tmp_path/'signed';other.mkdir();t=v5.Trace(v5.Output(other));v=values();v['PixelRepresentation']=1;t.precision['dicom']=v5.safe_dicom(v,{})
    with pytest.raises(v5.v3.v1.Reject):v5.process(v,encapsulate([generated_frame([[258,513,7],[8,9,10]])]),t,decoder_factory=lambda uid:pytest.fail('codec'))
    assert t.primary_error['reason_code']=='SIGNED_PROFILE_UNSUPPORTED'


def test_native_parameter_failure_is_not_entropy_decode(tmp_path):
    def fail(frame):raise RuntimeError('GENERATED_PRIVATE_PARAMETER_ERROR')
    with pytest.raises(RuntimeError):run_process(tmp_path,[[258,513,7],[8,9,10]],probe=fail,factory=lambda uid:pytest.fail('codec'))
    d=json.loads((tmp_path/'stage-checkpoint-v5.json').read_text())
    assert d['counts']['native_parameter_probe_entered']==1 and d['counts']['native_parameter_probe_returned']==0
    assert d['counts']['as_buffer_request']==0 and d['precision']['jpeg']['P']==16
    assert 'GENERATED_PRIVATE_PARAMETER_ERROR' not in json.dumps(d)


def test_supervised_native_block_rss_monitor_and_reap(tmp_path,monkeypatch):
    r=worker_request(tmp_path);original=v5.v3.v1.diag.v1.Budget
    monkeypatch.setattr(v5.v3.v1.diag.v1,'Budget',lambda caps:original(dict(caps,RSS_stop_bytes=512*1024**2)))
    monkeypatch.setitem(v5.CAPS,'RSS_stop_bytes',1024)  # test-only parent threshold
    result=v5.pipeline(r,decoder_factory=lambda uid:FakeBuffer('sleep'))
    assert result['phase_error']['reason_code']=='WORKER_RSS_LIMIT'
    assert result['RSS_samples'] and result['diagnostic']['counts']['as_buffer_request']==1
    pid=result['diagnostic']['worker_identity']['pid']
    with pytest.raises(ProcessLookupError):os.kill(pid,0)


def test_reporting_failure_preserves_real_worker_primary(tmp_path,monkeypatch,capsys):
    r=worker_request(tmp_path);original=v5.Output.write
    def fail(self,name,content,final=False):
        if final:raise OSError('GENERATED_REPORTING_SECRET')
        return original(self,name,content,final)
    monkeypatch.setattr(v5.Output,'write',fail)
    result=v5.pipeline(r,decoder_factory=lambda uid:FakeBuffer('raise'))
    assert result['status']=='REPORTING_FAILURE_PRIMARY_PRESERVED'
    assert result['diagnostic']['primary_error']['class']=='RuntimeError'
    assert result['diagnostic']['reporting_error']['class']=='OSError'
    assert 'GENERATED_REPORTING_SECRET' not in capsys.readouterr().out


def test_late_oracle_failure_has_raw_and_parameters(tmp_path,monkeypatch):
    def fail(*args):raise RuntimeError('GENERATED_ORACLE_SECRET')
    monkeypatch.setattr(v5.v3,'check_rescale',fail)
    with pytest.raises(RuntimeError):run_process(tmp_path,[[258,513,7],[8,9,10]])
    d=json.loads((tmp_path/'stage-checkpoint-v5.json').read_text())
    assert d['primary_error']['failed_stage']=='FP64_FP32_ORACLE' and d['counts']['as_buffer_api_returned']==1
    assert d['artifacts'] and d['precision']['parser_agreement']


def test_multifragment_frame_binding_uses_whole_frame(tmp_path):
    expected=np.array([[258,513,7],[8,9,10]],dtype=np.uint16)
    frame=generated_frame(expected);t=v5.Trace(v5.Output(tmp_path));v=values();t.precision['dicom']=v5.safe_dicom(v,{})
    native,qa=v5.process(v,encapsulate([frame],fragments_per_frame=3),t)
    assert t.precision['frame']['fragment_count']==3
    np.testing.assert_array_equal(np.load(tmp_path/'decoded-buffer-diagnostic.npy').view('<u2').reshape(2,3),expected)


def test_nonzero_point_transform_and_component_count_recorded_before_stop():
    frame=bytearray(generated_frame([[258,513,7],[8,9,10]]));pos=frame.index(b'\xff\xda');frame[pos+9]=1;record={}
    with pytest.raises(v5.old.HeaderError):v5.jpeg_record(bytes(frame),record)
    assert record['point_transform']==1
    original=generated_frame([[258,513,7],[8,9,10]]);pos=original.index(b'\xff\xc3')
    payload=bytearray(original[pos+4:pos+13]);payload[5]=2;payload+=b'\2\x11\0'
    malformed=original[:pos+2]+struct.pack('>H',len(payload)+2)+payload+original[pos+13:];record={}
    with pytest.raises(v5.old.HeaderError) as e:v5.jpeg_record(malformed,record)
    assert record['Nf']==2 and e.value.args[0]=='JPEG_COMPONENT_PROFILE'


def test_fp32_underflow_not_rescued_by_oracle_tolerance(tmp_path):
    t=v5.Trace(v5.Output(tmp_path));v=values();v['RescaleSlope']=1e-50;t.precision['dicom']=v5.safe_dicom(v,{})
    with pytest.raises(v5.v3.v1.Reject):v5.process(v,encapsulate([generated_frame([[258,513,7],[8,9,10]])]),t)
    assert t.counts['as_buffer_request']==0 and t.primary_error['failed_stage']=='FP32_PARAMETERS_CHECK'


def test_cli_default_no_grant_never_opens_member(monkeypatch,capsys):
    import sys
    sha='0000000000000000000000000000000000000000000000000000000000000000'
    r={'schema':'RI_HU_PRECISION_REQUEST_V5','caps':v5.CAPS,'expected_member_sha256':sha,'evidence_bindings':[],
       'bindings':{'source_bindings':[{'path':str(Path(v5.__file__).resolve())}],'decoder_distributions':{},'decoder_module_bindings':[],'decoder_binary_bindings':[]},
       'parent_request':{'path':'parent','sha256':'2'*64},'member':{},'source_archive':{},'inventory_binding':{}}
    parent={'member':{},'source_archive':{},'inventory_binding':{}}
    monkeypatch.setattr(v5,'bound_json',lambda p,h:r if p=='r' else parent)
    monkeypatch.setattr(v5.old,'verify_readiness',lambda b:None)
    monkeypatch.setattr(v5,'pipeline',lambda *a:pytest.fail('real access'))
    argv=['generated','--request','r','--request-sha256','1'*64]
    monkeypatch.setattr(sys,'argv',argv);v5.main();assert 'CHECK_ONLY' in capsys.readouterr().out
    monkeypatch.setattr(sys,'argv',argv+['--execute'])
    with pytest.raises(v5.v3.v1.Reject):v5.main()
