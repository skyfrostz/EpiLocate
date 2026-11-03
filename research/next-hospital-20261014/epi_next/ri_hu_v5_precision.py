"""V5 unsigned same-container precision diagnostics; one fixed as_buffer API."""
import argparse,hashlib,io,json,math,os,signal,struct,subprocess,time
from pathlib import Path
import numpy as np
from . import ri_hu_v4_diagnostic as v4
from .a0_acquire import bound_json,phase,secure_parent
v3=v4.v3;old=v4.old;CAPS=dict(v4.CAPS)
OUTER_RESERVE=256*1024;LEDGER_RESERVE=64*1024
CODES={'JPEG_SOI_REQUIRED','JPEG_STRUCTURE_TRUNCATED','JPEG_SEGMENT_LENGTH','JPEG_SOF_LENGTH','JPEG_PROFILE_NOT_SOF3',
 'JPEG_DUPLICATE_SOF','JPEG_COMPONENT_PROFILE','JPEG_SCAN_PROFILE','JPEG_EOI_REQUIRED','JPEG_ENTROPY_MARKER',
 'PARAMETER_PARSERS_DISAGREE','JPEG_DIMENSION_CONFLICT','JPEG_PRECISION_UNSUPPORTED','SIGNED_PROFILE_UNSUPPORTED',
 'CONTAINER_PROFILE_UNSUPPORTED','BUFFER_LENGTH_CONFLICT','BUFFER_PROPERTIES_CONFLICT','DECODED_STREAM_RANGE_CONFLICT',
 'OUTPUT_TOTAL_LIMIT','MEMBER_HISTORY_HASH_MISMATCH','API_REQUEST_LIMIT','WORKER_RSS_LIMIT'}


class Output:
    def __init__(self,root,used=0):self.root=Path(root);self.used=used
    def write(self,name,content,final=False):
        retained=sum(p.stat().st_size for p in self.root.iterdir() if p.is_file())
        reserve=OUTER_RESERVE+(0 if final else LEDGER_RESERVE)
        if max(retained+len(content),self.used+len(content))+reserve>CAPS['output_bytes_total']:raise v3.v1.Reject('OUTPUT_TOTAL_LIMIT')
        self.used+=len(content);path=self.root/name;part=path.with_name(path.name+'.part')
        with part.open('xb') as f:f.write(content);f.flush();os.fsync(f.fileno())
        part.chmod(0o600);os.replace(part,path);return {'path':str(path),'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)}
    def npy(self,name,array):
        buf=io.BytesIO();np.save(buf,array,allow_pickle=False);return self.write(name,buf.getvalue())


class Trace(v4.Trace):
    def __init__(self,out):
        super().__init__();self.out=out;self.precision={'dicom':{},'jpeg':{},'independent':{},'frame':{}}
        self.artifacts=[];self.value_semantics=None;self.inflight=None;self.unit_interpretation=None
        self.counts.pop('decoder_api_entered');self.counts.pop('decoder_api_returned')
        self.counts.update(as_array_api_entered=0,as_array_api_returned=0,python_parameter_parses=0,native_parameter_probe_request=0,native_parameter_probe_entered=0,native_parameter_probe_returned=0,
                           as_buffer_request=0,as_buffer_api_entered=0,as_buffer_api_returned=0)
        self.worker={'pid':os.getpid(),'ppid':os.getppid(),'pgid':os.getpgrp(),'process_start':subprocess.check_output(['ps','-p',str(os.getpid()),'-o','lstart='],text=True).strip()}
    def record(self):
        return dict(super().record(),precision=self.precision,artifacts=self.artifacts,value_semantics=self.value_semantics,
                    inflight=self.inflight,unit_interpretation=self.unit_interpretation,source_identity_status='SOURCE_DICOM_ID_NONCONFORMANT',worker_identity=self.worker,cumulative_output_before_snapshot=self.out.used)
    def snapshot(self):self.out.write('stage-checkpoint-v5.json',old.encoded(self.record()))
    def call(self,stage,fn):
        self.stage=stage;self.snapshot()
        try:return super().call(stage,fn)
        except Exception as exc:
            if isinstance(exc,(v3.v1.Reject,old.HeaderError,old.GuardError)) and len(exc.args)==1 and isinstance(exc.args[0],str) and exc.args[0] in CODES:
                self.primary_error['reason_code']=exc.args[0]
            raise
        finally:
            try:self.snapshot()
            except Exception as exc:self.reporting_error=v4.exception_record(exc,'CHECKPOINT_PUBLICATION')
    def api(self,stage,prefix,fn):
        if self.counts[prefix+'_request']>=1:raise v3.v1.Reject('API_REQUEST_LIMIT')
        self.counts[prefix+'_request']+=1
        entered=prefix+('_api_entered' if prefix=='as_buffer' else '_entered');returned=prefix+('_api_returned' if prefix=='as_buffer' else '_returned')
        self.counts[entered]='UNKNOWN';self.counts[returned]='UNKNOWN'
        self.inflight={'api':prefix,'stage':stage,'reserved_once':True}
        def invoke():
            try:value=fn()
            except Exception:self.counts[entered]=1;self.counts[returned]=0;self.inflight=None;raise
            self.counts[entered]=1;self.counts[returned]=1;self.inflight=None;return value
        return self.call(stage,invoke)


def jpeg_record(frame,record):
    # Narrow adaptation of the frozen SOF3/SOS validator, not a JPEG decoder.
    if frame[:2]!=b'\xff\xd8':raise old.HeaderError('JPEG_SOI_REQUIRED')
    offset=2;sof=None
    while offset<len(frame):
        marker_offset=offset
        if frame[offset]!=255:raise old.HeaderError('JPEG_STRUCTURE_TRUNCATED')
        while offset<len(frame) and frame[offset]==255:offset+=1
        if offset+2>=len(frame):raise old.HeaderError('JPEG_STRUCTURE_TRUNCATED')
        marker=frame[offset];offset+=1;length=struct.unpack_from('>H',frame,offset)[0]
        if marker in range(0xc0,0xd0) and marker not in (0xc4,0xc8,0xcc):
            record.update(SOF_marker=marker,SOF_offset=marker_offset,SOF_segment_length=length)
            if length>=8 and offset+8<=len(frame):
                p,y,x,n=struct.unpack_from('>BHHB',frame,offset+2);record.update(P=p,Y=y,X=x,Nf=n)
        if length<2 or offset+length>len(frame):raise old.HeaderError('JPEG_SEGMENT_LENGTH')
        payload=frame[offset+2:offset+length];offset+=length
        if marker in range(0xc0,0xd0) and marker not in (0xc4,0xc8,0xcc):
            record.update(SOF_marker=marker,SOF_offset=marker_offset,SOF_segment_length=length)
            if len(payload)>=6:
                p,y,x,n=struct.unpack_from('>BHHB',payload);record.update(P=p,Y=y,X=x,Nf=n)
            if marker!=0xc3:raise old.HeaderError('JPEG_PROFILE_NOT_SOF3')
            if sof is not None:raise old.HeaderError('JPEG_DUPLICATE_SOF')
            if len(payload)!=6+3*n:raise old.HeaderError('JPEG_SOF_LENGTH')
            if n!=1 or payload[7:]!=b'\x11\0':raise old.HeaderError('JPEG_COMPONENT_PROFILE')
            sof=payload[6]
        if marker==0xda:
            record.update(SOS_offset=marker_offset,SOS_segment_length=length)
            if len(payload)>=6:record.update(predictor=payload[3],point_transform=payload[5]&15,approximation_high=payload[5]>>4)
            if sof is None or len(payload)!=6 or payload[:2]!=bytes([1,sof]) or payload[2]&15 or payload[3:]!=b'\1\0\0':raise old.HeaderError('JPEG_SCAN_PROFILE')
            while offset<len(frame):
                if frame[offset]!=255:offset+=1;continue
                mark_start=offset;offset+=1
                while offset<len(frame) and frame[offset]==255:offset+=1
                if offset>=len(frame):break
                mark=frame[offset];offset+=1
                if mark==0 or 0xd0<=mark<=0xd7:continue
                if mark==0xd9 and frame[offset:] in (b'',b'\0'):
                    record.update(EOI_offset=mark_start,EOI_present=True,trailing_padding_bytes=len(frame)-offset);return
                raise old.HeaderError('JPEG_ENTROPY_MARKER')
            raise old.HeaderError('JPEG_EOI_REQUIRED')
    raise old.HeaderError('JPEG_EOI_REQUIRED')


def safe_dicom(values,states):
    keys=('BitsAllocated','BitsStored','HighBit','PixelRepresentation','Rows','Columns','SamplesPerPixel','NumberOfFrames')
    result={k:values.get(k) if isinstance(values.get(k),int) else None for k in keys}
    result.update(PhotometricInterpretation=values.get('PhotometricInterpretation') if values.get('PhotometricInterpretation') in ('MONOCHROME2','MONOCHROME1','RGB') else 'UNKNOWN_OR_UNSUPPORTED',
                  NumberOfFrames_status=states.get('NumberOfFrames','NOT_READ'),TransferSyntaxUID=v3.v1.codec.JPEG)
    return result


def process(values,payload,t,parameter_reader=None,decoder_factory=None):
    from pydicom.encaps import generate_fragmented_frames
    import libjpeg
    from pydicom.dataset import Dataset,FileMetaDataset
    from pydicom.pixels import get_decoder
    t.counts['decode_request']+=1
    def parameters():
        with np.errstate(over='ignore',under='ignore'):m=np.float32(values['RescaleSlope']);b=np.float32(values['RescaleIntercept'])
        if not np.isfinite(m) or m==0 or not np.isfinite(b) or values['RescaleIntercept']!=0 and b==0:raise v3.v1.Reject('RESCALE_FLOAT32_PARAMETERS')
    t.call('FP32_PARAMETERS_CHECK',parameters)
    def extract():
        frames=iter(generate_fragmented_frames(payload,number_of_frames=1));fragments=next(frames)
        if next(frames,None) is not None:raise old.HeaderError('MULTIPLE_ENCAPSULATED_FRAMES')
        frame=b''.join(fragments);t.precision['frame'].update(length=len(frame),sha256=hashlib.sha256(frame).hexdigest(),fragment_count=len(fragments),extracted_frame_count=1);return frame
    frame=t.call('ENCAPSULATION_FRAME_EXTRACTION',extract)
    t.counts['python_parameter_parses']+=1
    t.call('JPEG_PARAMETER_RECORD',lambda:jpeg_record(frame,t.precision['jpeg']))
    t.precision['jpeg'].update(frame_sha256=t.precision['frame']['sha256'],parser_id='EPI_SOF3_RECORD_V5_ADAPTED_FROM_FROZEN_VALIDATOR')
    def independent():
        p=(libjpeg.get_parameters if parameter_reader is None else parameter_reader)(frame)
        t.precision['independent']={k:int(p[k]) for k in ('precision','rows','columns','nr_components')}
        t.precision['independent'].update(frame_sha256=t.precision['frame']['sha256'],parser_id='libjpeg.get_parameters_2.4.0');return p
    t.api('NATIVE_PARAMETER_PROBE','native_parameter_probe',independent)
    def compare():
        j=t.precision['jpeg'];p=t.precision['independent'];d=t.precision['dicom']
        t.precision['parser_agreement']=(j['P'],j['Y'],j['X'],j['Nf'])==(p['precision'],p['rows'],p['columns'],p['nr_components'])
        t.precision['precision_equal']=j['P']==d['BitsStored']
        t.precision['metadata_consistency']='PRECISION_EQUAL' if t.precision['precision_equal'] else 'CODESTREAM_METADATA_DISCREPANCY'
        t.precision['comparison']={'P':j['P'],'BitsStored':d['BitsStored'],'BitsAllocated':d['BitsAllocated'],'HighBit':d['HighBit'],
                                   'JPEG_dimensions':[j['Y'],j['X'],j['Nf']],'DICOM_dimensions':[d['Rows'],d['Columns'],d['SamplesPerPixel']]}
        if not t.precision['parser_agreement']:raise v3.v1.Reject('PARAMETER_PARSERS_DISAGREE')
        if (j['Y'],j['X'],j['Nf'])!=(d['Rows'],d['Columns'],1):raise v3.v1.Reject('JPEG_DIMENSION_CONFLICT')
        if not 9<=j['P']<=16:raise v3.v1.Reject('CONTAINER_PROFILE_UNSUPPORTED')
        if d['PixelRepresentation']!=0:raise v3.v1.Reject('SIGNED_PROFILE_UNSUPPORTED')
        if d['BitsAllocated']!=16:raise v3.v1.Reject('CONTAINER_PROFILE_UNSUPPORTED')
    t.call('PARAMETER_COMPARISON_PROFILE',compare)
    def construct():
        ds=Dataset();ds.file_meta=FileMetaDataset();ds.file_meta.TransferSyntaxUID=v3.v1.codec.JPEG
        for k in ('Rows','Columns','SamplesPerPixel','PhotometricInterpretation','BitsAllocated','BitsStored','HighBit','PixelRepresentation','NumberOfFrames'):
            if k in values:setattr(ds,k,values[k])
        ds.PixelData=payload;return ds
    ds=t.call('UNCHANGED_MINIMAL_DATASET',construct)
    def admit():
        dec=(get_decoder if decoder_factory is None else decoder_factory)(v3.v1.codec.JPEG)
        if 'pylibjpeg' not in dec.available_plugins:raise v3.v1.Reject('PLUGIN_NOT_AVAILABLE')
        return dec.as_buffer
    buffer_call=t.call('FIXED_BUFFER_API_ADMISSION',admit)
    buffer,props=t.api('AS_BUFFER_CALL','as_buffer',lambda:buffer_call(ds,index=0,validate=True,decoding_plugin='pylibjpeg',allow_excess_frames=False))
    # Capacity only first: persist original bytes before properties/range QA.
    def preserve():
        if len(buffer)>2*512*512:raise v3.v1.Reject('BUFFER_LENGTH_CONFLICT')
        array=np.frombuffer(buffer,dtype=np.uint8).copy()
        a=t.out.npy('decoded-buffer-diagnostic.npy',array);t.artifacts.append(dict(a,purpose='UNALTERED_BACKEND_BYTES_DIAGNOSTIC_NOT_ACCEPTED'))
        t.precision['buffer']={'length':len(buffer),'sha256':hashlib.sha256(buffer).hexdigest(),'raw_archive_dtype':'uint8','byteorder_basis':'libjpeg wrapper source plus generated asymmetric-byte control; explicit <u2',
                              'returned_properties':{k:int(props[k]) for k in ('bits_allocated','bits_stored','pixel_representation','rows','columns') if isinstance(props.get(k),int)},
                              'properties_are_not_independent_JPEG_parameters':True}
        return array
    raw_bytes=t.call('RAW_BUFFER_DIAGNOSTIC_COMMIT',preserve)
    def view():
        p=t.precision['jpeg']['P'];count=values['Rows']*values['Columns']
        if len(buffer)!=count*2:raise v3.v1.Reject('BUFFER_LENGTH_CONFLICT')
        if props.get('bits_allocated')!=16 or props.get('pixel_representation')!=0:raise v3.v1.Reject('BUFFER_PROPERTIES_CONFLICT')
        return raw_bytes.view('<u2').reshape(values['Rows'],values['Columns'])
    raw=t.call('UNSIGNED_SAME_CONTAINER_VIEW',view)
    def semantics():
        p=t.precision['jpeg']['P'];b=values['BitsStored'];wide=raw.astype(np.uint64)
        stream_max=(1<<p)-1;declared_max=(1<<b)-1;diagnostic_corrected=wide & declared_max
        outside_stream=int(np.count_nonzero(wide>stream_max));outside_declared=int(np.count_nonzero(wide>declared_max))
        changed=int(np.count_nonzero(wide!=diagnostic_corrected));difference=int(np.max(wide-diagnostic_corrected))
        t.value_semantics={'raw_shape':list(raw.shape),'raw_view_dtype':'<u2','raw_min':int(wide.min()),'raw_max':int(wide.max()),'stream_unsigned_range':[0,stream_max],
         'declared_unsigned_range':[0,declared_max],'outside_stream_count':outside_stream,'outside_declared_count':outside_declared,
         'simulated_unused_bit_changed_count':changed,'simulated_unused_bit_max_difference':difference,'simulation_not_accepted_output':True,
         'status':'COMPATIBLE_WITH_DECLARED_RANGE' if outside_stream==outside_declared==changed==0 else 'DECODED_VALUE_SEMANTICS_UNRESOLVED'}
        if outside_stream:raise v3.v1.Reject('DECODED_STREAM_RANGE_CONFLICT')
        return outside_declared==0 and changed==0
    compatible=t.call('STORED_VALUE_SEMANTICS',semantics)
    if not compatible:return None,None
    native=t.call('SINGLE_RESCALE',lambda:raw.astype(np.float32)*np.float32(values['RescaleSlope'])+np.float32(values['RescaleIntercept']))
    error=t.call('FP64_FP32_ORACLE',lambda:v3.check_rescale(raw,native,values['RescaleSlope'],values['RescaleIntercept']))
    padding=values.get('PixelPaddingValue');limit=values.get('PixelPaddingRangeLimit');limit=padding if limit is None else limit
    qa={'scalar_rescale_applications':1,'max_float32_float64_difference':error,'VOI_window_applied':False,'model_normalization_applied':False,'resampling':'NONE',
        'padding_count':None if padding is None else int(np.count_nonzero((raw>=min(padding,limit))&(raw<=max(padding,limit)))),'padding_not_removed_from_raw_QA':True}
    return native,qa


def audit(r,accept_source=False,parameter_reader=None,decoder_factory=None):
    out=Output(r['output_root']);t=Trace(out);budget=v3.v1.diag.v1.Budget(CAPS);stream=None;public={'model_calls':0,'training_calls':0,'source_identity_status':'SOURCE_DICOM_ID_NONCONFORMANT'}
    try:
        t.snapshot();stream=t.call('MEMBER_OPEN',lambda:old.Member(old.open_bound_archive(r),r['member'],budget,r['member']['uncompressed_bytes'],r['source_archive']))
        capture=v3.Capture(stream);scan=t.call('HEADER_CONDITIONS',lambda:v4.TechnicalWalker(capture,t).scan());values=scan['values']
        t.precision['dicom']=safe_dicom(values,scan['states']);t.snapshot()
        branch=t.call('UNIT_INTERPRETATION',lambda:v3.interpret(values,scan['states'],r['bound_source_HU_claim'],False));t.unit_interpretation=branch;public.update(states=scan['states'],unit_interpretation=branch,header_complete=scan['complete'])
        if not scan['complete'] or t.field_errors or branch['unit_branch'] not in ('EXPLICIT_HU','DICOM_CONDITIONAL_HU'):
            t.isolation_stage='UNIT_INTERPRETATION';public['status']='ISOLATED_NO_CODEC';return dict(public,diagnostic=t.record(),budget=budget.report())
        public['native_geometry']=t.call('OBJECT_GEOMETRY',lambda:v4.object_geometry(values))
        def read_complete():
            capture.header=False
            while stream.emitted<r['member']['uncompressed_bytes']:capture.read(min(32768,r['member']['uncompressed_bytes']-stream.emitted))
            t.integrity.update(bytes_read=stream.emitted,declared_length_consumed=stream.emitted==r['member']['uncompressed_bytes'],sha_computed=True,member_sha256=stream.hash.hexdigest())
        t.call('FULL_MEMBER_READ',read_complete)
        def verify():
            sha=stream.finish();t.integrity.update(EOF_verified=True,CRC_verified=True,member_sha256=sha)
            if r.get('expected_member_sha256') and sha!=r['expected_member_sha256']:raise v3.v1.Reject('MEMBER_HISTORY_HASH_MISMATCH')
        t.call('EOF_CRC_HISTORY_SHA',verify);raw=b''.join(capture.parts)
        def projection():
            from pydicom.filereader import read_dataset
            end=144+struct.unpack_from('<I',raw,140)[0]
            return read_dataset(io.BytesIO(raw[end:]),False,True,bytelength=len(raw)-end,specific_tags=[0x7fe00010])
        ds=t.call('PIXELDATA_PROJECTION',projection);payload=t.call('PIXELDATA_LAZY_VALUE',lambda:ds.PixelData)
        native,qa=process(values,payload,t,parameter_reader,decoder_factory);budget.check()
        if native is None:public['status']='DECODED_VALUE_SEMANTICS_UNRESOLVED'
        else:
            def save():t.artifacts.append(dict(out.npy('native-rescaled-accepted-single-frame.npy',native),purpose='SINGLE_FRAME_NUMERICAL_RESULT_NOT_TRAINING_ADMISSION'));t.integrity['output_committed']=True
            t.call('RESCALED_COMMIT',save);public.update(status='SINGLE_FRAME_NUMERICAL_QA_COMPLETE',qa=qa,rescale_coefficients={'slope':values['RescaleSlope'],'intercept':values['RescaleIntercept']})
    except Exception as exc:
        if t.primary_error is None:t.primary_error=v4.exception_record(exc,t.stage or 'AUDIT')
        public['status']='STOPPED_NO_RETRY'
    finally:
        if stream is not None:t.integrity['bytes_read']=stream.emitted;stream.close()
        try:t.snapshot()
        except Exception as exc:t.reporting_error=v4.exception_record(exc,'FINAL_CHECKPOINT')
    return dict(public,diagnostic=t.record(),budget=budget.report())


def pipeline(r,parameter_reader=None,decoder_factory=None):
    start=time.monotonic();out=Path(r['output_root']);secure_parent(out);out.mkdir(mode=0o700,exist_ok=False);samples=[];phase_error=None;recovered_checkpoint=False
    def monitor(path):
        cp=out/'stage-checkpoint-v5.json'
        if cp.exists():
            d=bound_json(cp,old.sha(cp));identity=d['worker_identity'];pid=identity['pid']
            if identity['ppid']!=os.getpid() or identity['pgid']!=pid:raise RuntimeError('WORKER_IDENTITY_CONFLICT')
            process=subprocess.run(['ps','-p',str(pid),'-o','ppid=,rss=,lstart='],text=True,capture_output=True,timeout=2)
            text=process.stdout.strip() if process.returncode==0 else ''
            if text:
                parent_text,rss_text,birth=text.split(maxsplit=2);parent,rss=int(parent_text),int(rss_text)
                assert parent==os.getpid() and os.getpgid(pid)==pid and birth.strip()==identity['process_start']
                samples.append({'pid':pid,'elapsed_seconds':time.monotonic()-start,'RSS_bytes':rss*1024})
                if rss*1024>CAPS['RSS_stop_bytes']:raise RuntimeError('WORKER_RSS_LIMIT')
        st=os.statvfs(path);return st.f_bavail*st.f_frsize
    previous=signal.getsignal(signal.SIGTERM)
    def interrupt(signum,frame):raise InterruptedError('OWN_CLI_SIGTERM')
    signal.signal(signal.SIGTERM,interrupt)
    try:result=phase(audit,(r,False,parameter_reader,decoder_factory),60,start+90,out,4*1024**3,free_fn=monitor)
    except Exception as exc:
        phase_error=v4.exception_record(exc,'SUPERVISED_PHASE')
        if samples and samples[-1]['RSS_bytes']>CAPS['RSS_stop_bytes']:phase_error['reason_code']='WORKER_RSS_LIMIT'
        if isinstance(exc,InterruptedError):phase_error['reason_code']='OWN_CLI_SIGTERM'
        recovered_checkpoint=True
        cp=out/'stage-checkpoint-v5.json'
        saved=bound_json(cp,old.sha(cp)) if cp.exists() else {'counts':{'as_buffer_request':'UNKNOWN','as_buffer_api_entered':'UNKNOWN','as_buffer_api_returned':'UNKNOWN'}}
        result={'status':'STOPPED_NO_RETRY','diagnostic':saved,'budget':'UNKNOWN_NO_PHASE_RESULT'}
        if saved.get('primary_error') is None:saved['primary_error']=phase_error
    finally:signal.signal(signal.SIGTERM,previous)
    identity=result.get('diagnostic',{}).get('worker_identity')
    reap_verified='UNKNOWN'
    if identity:
        observed=subprocess.run(['ps','-p',str(identity['pid']),'-o','lstart='],text=True,capture_output=True).stdout.strip()
        reap_verified=not observed or observed!=identity['process_start']
    used=result.get('diagnostic',{}).get('cumulative_output_before_snapshot',0)
    cp=out/'stage-checkpoint-v5.json'
    if recovered_checkpoint and cp.exists():used+=cp.stat().st_size
    retained=sum(p.stat().st_size for p in out.iterdir() if p.is_file())
    result.update(output_accounting={'cumulative_internal_before_ledger':used,'retained_internal_before_ledger':retained,'outer_reserved_bytes':OUTER_RESERVE,'total_limit_bytes':CAPS['output_bytes_total'],'checkpoint_recovered_after_phase_stop':recovered_checkpoint},worker_reap_verified=reap_verified,schema='RI_HU_PRECISION_LEDGER_V5',attempts=1,elapsed_seconds=time.monotonic()-start,phase_error=phase_error,RSS_samples=samples,
      old_RI_restarted=False,source_fallback=False,training_eligibility='NOT_ESTABLISHED',outer_output_reserve_bytes=OUTER_RESERVE,
      native_parameter_calls_inside_codec='UNKNOWN_OBSERVED; static wrapper expects one additional internal probe, not a second project probe')
    try:Output(out,used).write('precision-ledger-v5.json',old.encoded(result),final=True)
    except Exception as exc:
        result.setdefault('diagnostic',{})['reporting_error']=v4.exception_record(exc,'LEDGER_PUBLICATION');result['status']='REPORTING_FAILURE_PRIMARY_PRESERVED'
        print(json.dumps({'status':result['status'],'primary_error':result['diagnostic'].get('primary_error'),'reporting_error':result['diagnostic']['reporting_error']}))
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--request-sha256',required=True);p.add_argument('--execute',action='store_true');p.add_argument('--approval');p.add_argument('--approval-sha256');a=p.parse_args();r=bound_json(a.request,a.request_sha256)
    if r['schema']!='RI_HU_PRECISION_REQUEST_V5' or r['caps']!=CAPS:raise v3.v1.Reject('EXACT_V5_REQUEST')
    for x in r['evidence_bindings']:v3.v1.assert_file(x)
    old.verify_readiness(r['bindings'])
    if str(Path(__file__).resolve()) not in {x['path'] for x in r['bindings']['source_bindings']} or r['expected_member_sha256']!='0000000000000000000000000000000000000000000000000000000000000000':raise v3.v1.Reject('FIXED_V5_BINDING_REQUIRED')
    import importlib,importlib.metadata
    for name,version in r['bindings']['decoder_distributions'].items():
        if importlib.metadata.version(name)!=version:raise v3.v1.Reject('DECODER_VERSION_DRIFT')
    for x in r['bindings']['decoder_module_bindings']:
        m=importlib.import_module(x['module'])
        if Path(m.__file__).resolve()!=Path(x['path']).resolve():raise v3.v1.Reject('DECODER_MODULE_DRIFT')
        v3.v1.assert_file(x)
    for x in r['bindings']['decoder_binary_bindings']:v3.v1.assert_file(x)
    for x in r['bindings'].get('closure_file_bindings',[]):v3.v1.assert_file(x)
    from pydicom.pixels.decoders.pylibjpeg import _DECODERS
    loaded=[(name,fn.__module__,fn.__name__) for name,fn in _DECODERS[v3.v1.codec.JPEG].items()]
    if loaded!=[('libjpeg','libjpeg.utils','decode_pixel_data')]:raise v3.v1.Reject('FIXED_ENTRYPOINT_DRIFT')
    parent=bound_json(r['parent_request']['path'],r['parent_request']['sha256'])
    if r['member']!=parent['member'] or r['source_archive']!=parent['source_archive'] or r['inventory_binding']!=parent['inventory_binding']:raise v3.v1.Reject('EXACT_MEMBER_REQUIRED')
    if not a.execute:print(json.dumps({'status':'CHECK_ONLY_NO_ARCHIVE_BODY_ACCESS'}));return
    if not a.approval or not a.approval_sha256:raise v3.v1.Reject('NEW_V5_APPROVAL_REQUIRED')
    grant=bound_json(a.approval,a.approval_sha256)
    expected={'schema':'RI_HU_PRECISION_APPROVAL_V5','request_sha256':a.request_sha256,'permit_parameter_probe':True,'permit_precision_discrepancy_diagnostic':True,'permit_raw_diagnostic_save':True,'permit_conditional_rescale':True,'permit_model':False,'permit_training':False,'permit_retry':False,'accept_source_supported_research_only':False}
    if any(type(grant.get(k)) is not type(v) or grant.get(k)!=v for k,v in expected.items()):raise v3.v1.Reject('EXACT_NEW_V5_APPROVAL_REQUIRED')
    if any(os.environ.get(k)!='1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')):raise v3.v1.Reject('CPU1_REQUIRED')
    result=pipeline(r);print(json.dumps({'status':result['status']}))
    if result['status']!='SINGLE_FRAME_NUMERICAL_QA_COMPLETE':raise SystemExit(1)

if __name__=='__main__':
    try:main()
    except Exception as exc:print(json.dumps({'status':'CONTROL_REJECTED','primary_error':v4.exception_record(exc,'CONTROL_BINDING')}));raise SystemExit(1) from None
