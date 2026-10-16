"""Independent safe diagnostics; frozen v3/HU rules/decoder/tolerances unchanged."""
import argparse,io,json,logging,math,os,struct,time,warnings
from pathlib import Path
import numpy as np
from . import ri_hu_v3 as v3
from .a0_acquire import bound_json,exclusive,phase,secure_parent
old=v3.old
CAPS=dict(v3.CAPS)
SAFE_CODES={'MEMBER_CRC_MISMATCH','DECODED_SHAPE_OR_SIZE','DECODED_DTYPE','JPEG_DATASET_PRECISION_MISMATCH',
 'MULTIPLE_ENCAPSULATED_FRAMES','RESCALE_FLOAT32_PARAMETERS','STORED_BITS_RANGE','NONFINITE_RESCALED_OUTPUT','RESCALE_NUMERICAL_QA',
 'PLUGIN_NOT_AVAILABLE','DECODER_REQUEST_LIMIT','FIXED_DECODER_OBJECT_PROFILE','PIXEL_PROFILE','NATIVE_2D_GEOMETRY','OUTPUT_LIMIT'}


def exception_record(exc,stage):
    # No str/repr(exc), source text, locals, input paths or pixel bytes.
    import pydicom
    repo=Path(__file__).resolve().parent.parent;site=Path(pydicom.__file__).resolve().parent.parent
    def kind(e):return {'module':type(e).__module__,'class':type(e).__name__}
    chain=[];seen=set();current=exc
    while current is not None and id(current) not in seen and len(chain)<8:
        seen.add(id(current));item=kind(current);item['relationship']='primary' if not chain else relation;chain.append(item)
        if current.__cause__ is not None:current=current.__cause__;relation='cause'
        else:current=current.__context__;relation='context'
    frames=[];tb=exc.__traceback__
    while tb is not None and len(frames)<16:
        filename=Path(tb.tb_frame.f_code.co_filename)
        try:
            rel=filename.resolve().relative_to(repo)
            relative=rel.as_posix() if filename.suffix=='.py' and rel.parts[0] in ('epi_next','tests') else 'UNBOUND_CODE'
        except ValueError:
            try:
                rel=filename.resolve().relative_to(site)
                relative=rel.as_posix() if rel.parts[0] in ('pydicom','pylibjpeg','libjpeg') else 'UNBOUND_CODE'
            except ValueError:relative='UNBOUND_CODE'
        frames.append({'relative_code':relative,'function':tb.tb_frame.f_code.co_name,'line':tb.tb_lineno});tb=tb.tb_next
    code=exc.args[0] if type(exc) in (v3.v1.Reject,old.HeaderError,old.GuardError) and len(exc.args)==1 and isinstance(exc.args[0],str) and exc.args[0] in SAFE_CODES else stage+'_ERROR'
    return dict(kind(exc),reason_code=code,failed_stage=stage,code_locations=frames,type_chain=chain,raw_exception_text_retained=False)


class Trace:
    def __init__(self):
        self.stage=None;self.last_completed=None;self.isolation_stage=None;self.primary_error=None;self.reporting_error=None;self.field_errors=[];self.field_observations=[];self.decoder_return_metadata=None
        self.counts={'decode_request':0,'decoder_api_entered':0,'decoder_api_returned':0,'plugin_entered':'UNKNOWN','plugin_returned':'UNKNOWN'}
        self.integrity={'bytes_read':0,'declared_length_consumed':False,'EOF_verified':False,'sha_computed':False,'member_sha256':None,'CRC_verified':False,'output_committed':False}
    def call(self,stage,fn):
        self.stage=stage
        class Redact(logging.Filter):
            def filter(self,r):r.msg='DIAGNOSTIC_REDACTED';r.args=();r.exc_info=None;r.exc_text=None;r.stack_info=None;return True
        filt=Redact();loggers=[logging.getLogger(n) for n in ('pydicom','pylibjpeg','libjpeg')];handlers=set(logging.getLogger().handlers)
        for logger in loggers:logger.addFilter(filt);handlers.update(logger.handlers)
        for handler in handlers:handler.addFilter(filt)
        original_factory=logging.getLogRecordFactory()
        def safe_factory(*args,**kwargs):
            record=original_factory(*args,**kwargs)
            for family in ('pydicom','pylibjpeg','libjpeg'):
                if record.name==family or record.name.startswith(family+'.'):
                    filt.filter(record);record.name=family;record.pathname='CODE_LOCATION_REDACTED';record.filename='CODE_LOCATION_REDACTED';record.funcName='DIAGNOSTIC';break
            return record
        logging.setLogRecordFactory(safe_factory)
        try:
            with warnings.catch_warnings(record=True):
                warnings.simplefilter('always')
                try:result=fn()
                except Exception as exc:
                    if self.primary_error is None:self.primary_error=exception_record(exc,stage)
                    raise
            self.last_completed=stage;return result
        finally:
            logging.setLogRecordFactory(original_factory)
            for logger in loggers:logger.removeFilter(filt)
            for handler in handlers:handler.removeFilter(filt)
    def record(self):return {'last_completed_stage':self.last_completed,'failed_stage':self.isolation_stage if self.primary_error is None else self.primary_error['failed_stage'],
                            'primary_error':self.primary_error,'reporting_error':self.reporting_error,'counts':self.counts,'integrity':self.integrity,'field_errors':self.field_errors,'field_observations':self.field_observations,'decoder_return_metadata':self.decoder_return_metadata}


class TechnicalWalker(v3.TechnicalWalker):
    def __init__(self,stream,trace):super().__init__(stream);self.trace=trace
    def take(self,key,vr,n,end,expected):
        if self.states.get(key,'NOT_READ')!='NOT_READ':self.fail('DUPLICATE_TECHNICAL_FIELD')
        if n>4096:self.fail('TECHNICAL_VALUE_LIMIT','resource_stop')
        raw=self.read(n,end)
        descriptor={'keyword':key,'tag':self.ctx['tag'],'VR':vr,'value_length':n}
        if vr!=expected and not (key.startswith('PixelPadding') and vr in ('US','SS')):
            self.states[key]='INVALID';self.trace.field_observations.append(dict(descriptor,state='INVALID',reason_code='FIELD_VR_MISMATCH',exception_type_observed=False));return
        if not raw:
            self.states[key]='EMPTY';self.values[key]=None
            self.trace.field_observations.append(dict(descriptor,state='EMPTY',reason_code='EMPTY_ENCODED_VALUE',exception_type_observed=False));return
        try:value=self.trace.call('TECHNICAL_FIELD_CONVERSION',lambda:old.field_value(raw,vr,key,self.values))
        except (ValueError,old.HeaderError):
            info=dict(self.trace.primary_error,field={'keyword':key,'tag':self.ctx['tag'],'VR':vr,'value_length':n})
            self.trace.field_errors.append(info);self.states[key]='INVALID';return
        self.states[key]='EMPTY' if value is None or value=='' else 'PRESENT';self.values[key]=value


def decoder_pipeline(values,payload,t,factory=None):
    from pydicom.encaps import generate_frames
    from pydicom.dataset import Dataset,FileMetaDataset
    from pydicom.pixels import get_decoder
    # Preserve the old actual sequence: frame extraction -> JPEG precheck ->
    # minimal Dataset -> fixed plugin -> decoder -> stored checks -> rescale.
    def frame_extract():
        frames=iter(generate_frames(payload,number_of_frames=1));frame=next(frames)
        if next(frames,None) is not None:raise old.HeaderError('MULTIPLE_ENCAPSULATED_FRAMES')
        return frame
    def parameter_check():
        with np.errstate(over='ignore',under='ignore'):
            m=np.float32(values['RescaleSlope']);b=np.float32(values['RescaleIntercept'])
        if not np.isfinite(m) or m==0 or not np.isfinite(b) or values['RescaleIntercept']!=0 and b==0:raise v3.v1.Reject('RESCALE_FLOAT32_PARAMETERS')
    t.call('FP32_PARAMETERS_CHECK',parameter_check)
    frame=t.call('ENCAPSULATION_FRAME_EXTRACTION',frame_extract)
    t.call('JPEG_PRECHECK',lambda:v3.v1.codec.validate_jpeg_frame(frame,values))
    def construct():
        ds=Dataset();ds.file_meta=FileMetaDataset();ds.file_meta.TransferSyntaxUID=v3.v1.codec.JPEG
        for key in ('Rows','Columns','SamplesPerPixel','PhotometricInterpretation','BitsAllocated','BitsStored','HighBit','PixelRepresentation','NumberOfFrames'):
            if key in values:setattr(ds,key,values[key])
        ds.PixelData=payload;return ds
    ds=t.call('MINIMAL_DATASET_CONSTRUCTION',construct)
    def admit():
        dec=(get_decoder if factory is None else factory)(v3.v1.codec.JPEG)
        if 'pylibjpeg' not in dec.available_plugins:raise v3.v1.Reject('PLUGIN_NOT_AVAILABLE')
        return dec
    decoder=t.call('FIXED_PLUGIN_ADMISSION',admit)
    def invoke():
        if t.counts['decoder_api_entered']>=1:raise v3.v1.Reject('DECODER_REQUEST_LIMIT')
        t.counts['decoder_api_entered']+=1
        returned=decoder.as_array(ds,decoding_plugin='pylibjpeg')
        t.counts['decoder_api_returned']+=1;return returned
    returned=t.call('DECODER_API_CALL_RETURN',invoke)
    def stored_check():
        array,props=returned
        t.decoder_return_metadata={'shape':list(array.shape),'dtype_kind':array.dtype.kind,'dtype_itemsize':array.dtype.itemsize,
            'bits_allocated':int(props['bits_allocated']) if isinstance(props.get('bits_allocated'),(int,np.integer)) else 'UNKNOWN',
            'bits_stored':int(props['bits_stored']) if isinstance(props.get('bits_stored'),(int,np.integer)) else 'UNKNOWN'}
        if array.shape!=(values['Rows'],values['Columns']) or array.nbytes>v3.v1.codec.B['decoded_pixel_bytes_per_SOP_max']:raise old.HeaderError('DECODED_SHAPE_OR_SIZE')
        if array.dtype.itemsize!=values['BitsAllocated']//8 or array.dtype.kind!=('i' if values['PixelRepresentation'] else 'u'):raise old.HeaderError('DECODED_DTYPE')
        if props['bits_allocated']!=values['BitsAllocated'] or props['bits_stored']!=values['BitsStored']:raise old.HeaderError('JPEG_DATASET_PRECISION_MISMATCH')
        lo,hi=(-(2**(values['BitsStored']-1)),2**(values['BitsStored']-1)-1) if values['PixelRepresentation'] else (0,2**values['BitsStored']-1)
        if int(array.min())<lo or int(array.max())>hi:raise v3.v1.Reject('STORED_BITS_RANGE')
        return array
    stored=t.call('STORED_ARRAY_CHECK',stored_check)
    native=t.call('SINGLE_RESCALE',lambda:stored.astype(np.float32)*np.float32(values['RescaleSlope'])+np.float32(values['RescaleIntercept']))
    error=t.call('FP64_FP32_ORACLE',lambda:v3.check_rescale(stored,native,values['RescaleSlope'],values['RescaleIntercept']))
    def metadata():
        padding=values.get('PixelPaddingValue');limit=values.get('PixelPaddingRangeLimit');limit=padding if limit is None else limit
        padding_count=None if padding is None else int(np.count_nonzero((stored>=min(padding,limit))&(stored<=max(padding,limit))))
        return {'scalar_rescale_applications':1,'max_float32_float64_difference':error,'VOI_window_applied':False,'model_normalization_applied':False,'LUT_or_realworld_applied':False,
            'stored_dtype':str(stored.dtype),'stored_shape':list(stored.shape),'per_instance_coefficients':True,'resampling':'NONE',
            'padding_count':padding_count,'padding_not_removed_from_raw_QA':True,'stored_finite':bool(np.isfinite(stored).all()),'rescaled_finite':bool(np.isfinite(native).all()),
            'stored_min':int(stored.min()),'stored_max':int(stored.max()),'rescaled_min':float(native.min()),'rescaled_max':float(native.max())}
    return stored,native,t.call('QA_METADATA',metadata)


def object_geometry(values):
    if values.get('TransferSyntaxUID')!=v3.v1.codec.JPEG or values.get('Modality')!='CT' or values.get('SamplesPerPixel')!=1 or values.get('PhotometricInterpretation')!='MONOCHROME2' or values.get('NumberOfFrames',1)!=1:raise v3.v1.Reject('FIXED_DECODER_OBJECT_PROFILE')
    if not all(2<=values.get(k,0)<=512 for k in ('Rows','Columns')) or values.get('BitsAllocated') not in (8,16) or not 0<values.get('BitsStored',0)<=values['BitsAllocated'] or values.get('HighBit')!=values['BitsStored']-1 or values.get('PixelRepresentation') not in (0,1):raise v3.v1.Reject('PIXEL_PROFILE')
    iop=np.asarray(values.get('ImageOrientationPatient'),dtype=float);ipp=np.asarray(values.get('ImagePositionPatient'),dtype=float);spacing=np.asarray(values.get('PixelSpacing'),dtype=float)
    if iop.shape!=(6,) or ipp.shape!=(3,) or spacing.shape!=(2,) or not all(np.isfinite(x).all() for x in (iop,ipp,spacing)) or np.any(spacing<=0) or abs(np.linalg.norm(iop[:3])-1)>1e-4 or abs(np.linalg.norm(iop[3:])-1)>1e-4 or abs(iop[:3]@iop[3:])>1e-4:raise v3.v1.Reject('NATIVE_2D_GEOMETRY')
    return {'IPP':ipp.tolist(),'IOP':iop.tolist(),'PixelSpacing':spacing.tolist(),'stack_QA':'NOT_EVALUATED_SINGLE_FRAME'}


def audit(r,accept_source,factory=None):
    t=Trace();budget=v3.v1.diag.v1.Budget(CAPS);stream=None;public={'model_calls':0,'training_calls':0,'source_identity_status':'SOURCE_DICOM_ID_NONCONFORMANT'}
    try:
        stream=t.call('MEMBER_OPEN',lambda:old.Member(old.open_bound_archive(r),r['member'],budget,r['member']['uncompressed_bytes'],r['source_archive']))
        capture=v3.Capture(stream);scan=t.call('HEADER_CONDITIONS',lambda:TechnicalWalker(capture,t).scan());values=scan['values']
        branch=t.call('UNIT_INTERPRETATION',lambda:v3.interpret(values,scan['states'],r['bound_source_HU_claim'],accept_source))
        public.update(states=scan['states'],header_complete=scan['complete'],header_stop=scan['stop_code'],header_prefix_bytes=scan['consumed_prefix_bytes'],unit_interpretation=branch)
        if not scan['complete'] or t.field_errors or branch['unit_branch'] not in ('EXPLICIT_HU','DICOM_CONDITIONAL_HU','SOURCE_SUPPORTED_RESEARCH_ONLY'):
            t.isolation_stage='HEADER_CONDITIONS' if not scan['complete'] else 'UNIT_INTERPRETATION'
            return dict(public,status='ISOLATED_NO_PIXEL_DECODE',diagnostic=t.record(),budget=budget.report())
        geometry=t.call('OBJECT_GEOMETRY_CHECK',lambda:object_geometry(values));public['native_geometry']=geometry
        def complete_read():
            capture.header=False
            while stream.emitted<r['member']['uncompressed_bytes']:capture.read(min(32768,r['member']['uncompressed_bytes']-stream.emitted))
            t.integrity.update(bytes_read=stream.emitted,declared_length_consumed=stream.emitted==r['member']['uncompressed_bytes'],sha_computed=True,member_sha256=stream.hash.hexdigest())
        t.call('FULL_MEMBER_READ',complete_read)
        def verify():
            digest=stream.finish();t.integrity.update(EOF_verified=True,CRC_verified=True,member_sha256=digest)
        t.call('MEMBER_EOF_SHA_CRC_VERIFICATION',verify)
        raw=b''.join(capture.parts)
        def projection():
            from pydicom.filereader import read_dataset
            end=144+struct.unpack_from('<I',raw,140)[0]
            return read_dataset(io.BytesIO(raw[end:]),False,True,bytelength=len(raw)-end,specific_tags=[0x7fe00010])
        ds=t.call('PIXELDATA_TECHNICAL_PROJECTION',projection)
        payload=t.call('PIXELDATA_LAZY_VALUE',lambda:ds.PixelData)
        t.counts['decode_request']+=1
        stored,native,qa=decoder_pipeline(values,payload,t,factory)
        artifacts=[]
        def save():
            for name,array in [('native-stored.npy',stored),('native-rescaled.npy',native)]:
                buffer=io.BytesIO();np.save(buffer,array,allow_pickle=False);content=buffer.getvalue();budget.count('output',len(content));p=Path(r['output_root'])/name
                with os.fdopen(exclusive(p),'wb') as f:f.write(content)
                artifacts.append({'path':str(p),'sha256':old.sha(p),'shape':list(array.shape),'dtype':str(array.dtype)})
            t.integrity['output_committed']=True
        t.call('ARRAY_OUTPUT_COMMIT',save)
        public.update(status='SINGLE_FRAME_NUMERICAL_QA_COMPLETE',artifacts=artifacts,qa=qa,rescale_coefficients={'slope':values['RescaleSlope'],'intercept':values['RescaleIntercept']})
    except Exception as exc:
        if t.primary_error is None:t.primary_error=exception_record(exc,t.stage or 'AUDIT')
        public['status']='STOPPED_NO_RETRY'
    finally:
        if stream is not None:
            t.integrity['bytes_read']=stream.emitted
            try:stream.close()
            except Exception as exc:t.reporting_error=exception_record(exc,'STREAM_CLOSE');public['status']='STOPPED_NO_RETRY'
    return dict(public,diagnostic=t.record(),budget=budget.report())


def pipeline(r,accept_source,factory=None):
    start=time.monotonic();out=Path(r['output_root']);secure_parent(out);out.mkdir(mode=0o700,exist_ok=False)
    try:result=phase(audit,(r,accept_source,factory),60,start+90,out,4*1024**3)
    except Exception as exc:
        result={'status':'STOPPED_NO_RETRY','diagnostic':{'primary_error':exception_record(exc,'SUPERVISED_PHASE'),'reporting_error':None,'counts':{'decode_request':'UNKNOWN','decoder_api_entered':'UNKNOWN','decoder_api_returned':'UNKNOWN','plugin_entered':'UNKNOWN','plugin_returned':'UNKNOWN'}},'budget':'UNKNOWN_RETAIN_RESERVED'}
    result.update(attempts=1,elapsed_seconds=time.monotonic()-start,old_RI_restarted=False,scientific_patient_or_stack_qualification='NOT_ESTABLISHED')
    try:v3.publish_ledger(out,result)
    except Exception as exc:
        result['diagnostic']['reporting_error']=exception_record(exc,'LEDGER_PUBLICATION');result['status']='REPORTING_FAILURE_PRIMARY_PRESERVED'
        # Safe stdout fallback: no input paths, arrays or full result. Does not
        # overwrite the primary exception when the filesystem cannot write.
        print(json.dumps({'status':result['status'],'diagnostic':result['diagnostic']},ensure_ascii=False))
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--request-sha256',required=True);p.add_argument('--execute',action='store_true');p.add_argument('--approval');p.add_argument('--approval-sha256');args=p.parse_args()
    r=bound_json(args.request,args.request_sha256)
    if r['schema']!='RI_HU_SINGLE_DIAGNOSTIC_DECODE_REQUEST_V4' or r['caps']!=CAPS:raise v3.v1.Reject('EXACT_V4_REQUEST')
    for item in r['evidence_bindings']:v3.v1.assert_file(item)
    old.verify_readiness(r['bindings'])
    import importlib,importlib.metadata
    for name,version in r['bindings']['decoder_distributions'].items():
        if importlib.metadata.version(name)!=version:raise v3.v1.Reject('DECODER_VERSION_DRIFT')
    for item in r['bindings']['decoder_module_bindings']:
        module=importlib.import_module(item['module'])
        if Path(module.__file__).resolve()!=Path(item['path']).resolve():raise v3.v1.Reject('DECODER_MODULE_DRIFT')
        v3.v1.assert_file(item)
    for item in r['bindings']['decoder_binary_bindings']:v3.v1.assert_file(item)
    if str(Path(__file__).resolve()) not in {i['path'] for i in r['bindings']['source_bindings']}:raise v3.v1.Reject('V4_SOURCE_REQUIRED')
    parent=bound_json(r['parent_request']['path'],r['parent_request']['sha256'])
    if r['member']!=parent['member'] or r['source_archive']!=parent['source_archive'] or r['inventory_binding']!=parent['inventory_binding']:raise v3.v1.Reject('EXACT_OLD_MEMBER_REQUIRED')
    if not args.execute:print(json.dumps({'status':'CHECK_ONLY_NO_ARCHIVE_BODY_ACCESS'}));return
    if not args.approval or not args.approval_sha256:raise v3.v1.Reject('NEW_V4_APPROVAL_REQUIRED')
    a=bound_json(args.approval,args.approval_sha256)
    expected={'schema':'RI_HU_SINGLE_DIAGNOSTIC_DECODE_APPROVAL_V4','request_sha256':args.request_sha256,'permit_header_and_conditional_decode':True,'permit_model':False,'permit_training':False,'permit_retry':False}
    if any(type(a.get(k)) is not type(v) or a.get(k)!=v for k,v in expected.items()) or type(a.get('accept_source_supported_research_only')) is not bool:raise v3.v1.Reject('EXACT_NEW_V4_APPROVAL_REQUIRED')
    if a['accept_source_supported_research_only'] and a.get('source_limitations_accepted')!=r['source_limitations_id']:raise v3.v1.Reject('SOURCE_LIMITATIONS_ACCEPTANCE_REQUIRED')
    if any(os.environ.get(k)!='1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')):raise v3.v1.Reject('CPU1_REQUIRED')
    result=pipeline(r,a['accept_source_supported_research_only']);print(json.dumps({'status':result['status']}))
    if result['status']!='SINGLE_FRAME_NUMERICAL_QA_COMPLETE':raise SystemExit(1)

if __name__=='__main__':
    try:main()
    except Exception as exc:print(json.dumps({'status':'CONTROL_REJECTED','primary_error':exception_record(exc,'CONTROL_BINDING')}));raise SystemExit(1) from None
