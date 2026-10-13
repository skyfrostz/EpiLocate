"""Versioned single-member HU interpretation and stored/rescale QA.
Frozen RI, source DICOM, decoder and model preprocessing are unchanged.
"""
import argparse,io,json,math,os,time
from pathlib import Path
import numpy as np
from . import research_import as v1, a3_structure_audit as a3
from .a0_acquire import bound_json,exclusive,phase,secure_parent
old=v1.old
ROOT={tag:(key,old.FIELD_VR[key]) for key,tag in v1.TAGS.items() if key not in {'PixelData','SliceThickness'}}
ROOT[0x00189361]=('MultiEnergyCTAcquisition','CS')
MAPS={0x00283000:'ModalityLUTSequence',0x00409096:'RealWorldValueMappingSequence',0x00189360:'CTAdditionalXRaySourceSequence',0x00189362:'MultiEnergyCTAcquisitionSequence'}
CAPS={'compressed_input_bytes':512*1024,'inflated_member_bytes_total':239180,'output_bytes_total':4*1024**2,
      'RSS_stop_bytes':512*1024**2,'wall_seconds':60,'inflated_header_prefix_bytes_per_member':128*1024,
      'element_count_per_member':4096,'depth_max':16,'structural_events_max_per_member':32,'whitelist_value_bytes_per_element':4096}


def interpret(values,states,source_supported=False,accept_source=False):
    image_value=values.get('ImageType');image_values=image_value.split('\\') if isinstance(image_value,str) else ['']
    condition_evidence={'rule_version':'PS3.3_2026d_C.8.2.1_Table_C.8-3+EPI_PROFILE_V3','classic_CT_class_pair':values.get('SOPClassUID')==old.CT and values.get('MediaStorageSOPClassUID')==old.CT,
        'ImageType_V1':image_values[0] if image_values[0] in ('ORIGINAL','DERIVED') else 'INVALID_OR_NOT_RECORDED',
        'ImageType_V3':image_values[2] if len(image_values)>2 and image_values[2] in ('AXIAL','LOCALIZER') else ('NOT_RECORDED' if len(image_values)<3 else 'UNSUPPORTED_OR_INVALID'),
        'MultiEnergy_status':states.get('MultiEnergyCTAcquisition','NOT_READ'),'MultiEnergy_enum':values.get('MultiEnergyCTAcquisition') if values.get('MultiEnergyCTAcquisition') in ('NO','YES') else None,
        'RescaleType_status':states.get('RescaleType','NOT_READ'),'explicit_HU_match':values.get('RescaleType')=='HU',
        'source_claim_bound':source_supported,'source_limitations_explicitly_accepted':accept_source}
    def result(branch,reason):return {'unit_branch':branch,'unit_reason':reason,'conditions':condition_evidence,'source_acceptance_required':branch=='SOURCE_SUPPORTED_RESEARCH_ONLY','source_DICOM_modified':False}
    if values.get('SOPClassUID')!=old.CT or values.get('MediaStorageSOPClassUID')!=old.CT:return result('UNKNOWN','SUPPORTED_CLASSIC_CT_REQUIRED')
    for key in ('RescaleSlope','RescaleIntercept'):
        x=values.get(key)
        if states.get(key)!='PRESENT' or not isinstance(x,(int,float)) or not math.isfinite(x) or key=='RescaleSlope' and x==0:return result('CONFLICT','INVALID_SCALAR_RESCALE')
    with np.errstate(over='ignore',under='ignore'):
        m32=np.float32(values['RescaleSlope']);b32=np.float32(values['RescaleIntercept'])
    if not np.isfinite(m32) or m32==0 or not np.isfinite(b32) or values['RescaleIntercept']!=0 and b32==0:return result('CONFLICT','FLOAT32_RESCALE_PARAMETER_UNREPRESENTABLE')
    for key in MAPS.values():
        if states.get(key) not in ('ABSENT',):return result('CONFLICT','MAPPING_OR_ADDITIONAL_SOURCE_REQUIRES_SEPARATE_PATH')
    image=image_values
    if states.get('ImageType')!='PRESENT' or len(image)<2 or image[0] not in ('ORIGINAL','DERIVED') or image[1] not in ('PRIMARY','SECONDARY'):return result('CONFLICT','INVALID_IMAGE_TYPE')
    if any(v in ('LOCALIZER','SCOUT') for v in image):return result('CONFLICT','LOCALIZER_NOT_RESEARCH_SLICE')
    # Engineering support restriction, NOT a quotation of the standard:
    # only AXIAL is a supported present Value3 in this bounded first decoder.
    if len(image)>2 and image[2]!='AXIAL':return result('CONFLICT','UNSUPPORTED_IMAGE_TYPE_VALUE3_PROFILE')
    energy=states.get('MultiEnergyCTAcquisition');energy_value=values.get('MultiEnergyCTAcquisition')
    if energy=='PRESENT' and energy_value not in ('YES','NO') or energy in ('EMPTY','INVALID'):return result('CONFLICT','INVALID_MULTIENERGY_ENUM')
    if energy=='PRESENT' and energy_value=='YES':return result('CONFLICT','MULTIENERGY_OUTSIDE_ENGINEERING_PROFILE')
    if energy not in ('ABSENT','PRESENT'):return result('UNKNOWN','MULTIENERGY_NOT_CONFIRMED')
    typestate=states.get('RescaleType');unit=values.get('RescaleType')
    conditional=image[0]=='ORIGINAL' and len(image)>2 and image[2]=='AXIAL' and (energy=='ABSENT' or energy_value=='NO')
    if typestate in ('EMPTY','INVALID'):return result('CONFLICT','INVALID_RESCALE_TYPE')
    if typestate=='PRESENT':
        if unit=='HU':return result('EXPLICIT_HU','EXPLICIT_HU')
        return result('CONFLICT' if conditional else 'NON_HU','EXPLICIT_NON_HU_NOT_OVERRIDDEN')
    if typestate!='ABSENT':return result('UNKNOWN','RESCALE_TYPE_NOT_CONFIRMED')
    if conditional:return result('DICOM_CONDITIONAL_HU','PS3_3_2026D_C8_2_1_TABLE_C8_3')
    if source_supported and accept_source:return result('SOURCE_SUPPORTED_RESEARCH_ONLY','BOUND_SOURCE_HU_CLAIM_WITH_UNRESOLVED_IMAGE_TYPE_CONDITION')
    return result('UNKNOWN','CONDITION_UNKNOWN_OR_NOT_MET_SOURCE_ACCEPTANCE_REQUIRED')


class Capture:
    def __init__(self,stream):self.s=stream;self.parts=[];self.header=True
    def __getattr__(self,key):return getattr(self.s,key)
    def read(self,n):
        if self.header and self.s.emitted+n>128*1024:raise old.GuardError('INFLATED_PREFIX_OR_SIZE_LIMIT')
        data=self.s.read(n);self.parts.append(data);return data


class TechnicalWalker(a3.Walker):
    def __init__(self,s):
        super().__init__(s,'FIXED_RI_FIRST_MEMBER',CAPS)
        self.states={key:'NOT_READ' for key,_ in ROOT.values()};self.states.update({key:'NOT_READ' for key in MAPS.values()})
    def header(self,end,path,domain):
        tag,vr,n=super().header(end,path,domain);integer=(tag[0]<<16)|tag[1]
        if domain=='dataset' and integer in MAPS:
            self.states[MAPS[integer]]='PRESENT';self.fail('MAPPING_PATH_REQUIRES_SEPARATE_REVIEW','mapping_stop')
        return tag,vr,n
    def take(self,key,vr,n,end,expected):
        if self.states.get(key,'NOT_READ')!='NOT_READ':self.fail('DUPLICATE_TECHNICAL_FIELD')
        if n>4096:self.fail('TECHNICAL_VALUE_LIMIT','resource_stop')
        raw=self.read(n,end)
        if vr!=expected and not (key.startswith('PixelPadding') and vr in ('US','SS')):self.states[key]='INVALID';return
        if not raw:self.states[key]='EMPTY';self.values[key]=None;return
        try:value=old.field_value(raw,vr,key,self.values)
        except (ValueError,old.HeaderError):self.states[key]='INVALID';return
        self.states[key]='EMPTY' if value is None or value=='' else 'PRESENT';self.values[key]=value
    def selected(self,key,vr,n,end):
        if key in ('MediaStorageSOPClassUID','TransferSyntaxUID'):return super().selected(key,vr,n,end)
        integer=int(self.ctx['tag'].replace(',',''),16)
        if integer in ROOT:return self.take(key,vr,n,end,ROOT[integer][1])
        return super().skip(n,end)
    def skip(self,n,end):
        integer=int(self.ctx['tag'].replace(',',''),16)
        if self.ctx['domain']=='dataset' and integer in ROOT:
            key,expected=ROOT[integer];return self.take(key,self.ctx['VR'],n,end,expected)
        return super().skip(n,end)
    def scan(self):
        report=super().run()
        if report['root_completed_up_to_pixel_or_member_end']:
            for key,status in self.states.items():
                if status=='NOT_READ':self.states[key]='ABSENT'
        return {'states':self.states,'values':self.values,'stop_code':report['stop_code'],'complete':report['root_completed_up_to_pixel_or_member_end'],
                'consumed_prefix_bytes':report['consumed_prefix_bytes'],'prefix_sha256':report['prefix_sha256']}


def check_rescale(stored,native,slope,intercept):
    reference=stored.astype(np.float64)*slope+intercept
    if not np.isfinite(reference).all() or not np.isfinite(native).all():raise v1.Reject('NONFINITE_RESCALED_OUTPUT')
    if not np.allclose(native,reference,rtol=1e-6,atol=1e-3):raise v1.Reject('RESCALE_NUMERICAL_QA')
    return float(np.max(np.abs(native-reference)))


def stored_to_rescaled(values,payload):
    # Fixed mature JPEG Lossless stored-domain decoder: minimal Dataset has NO
    # rescale, LUT, real-world, VOI/window or normalization attributes.
    with np.errstate(over='ignore',under='ignore'):
        m32=np.float32(values['RescaleSlope']);b32=np.float32(values['RescaleIntercept'])
    if not np.isfinite(m32) or m32==0 or not np.isfinite(b32) or values['RescaleIntercept']!=0 and b32==0:raise v1.Reject('RESCALE_FLOAT32_PARAMETERS')
    stored=v1.codec.decode_pixels(values,payload)
    lo,hi=(-(2**(values['BitsStored']-1)),2**(values['BitsStored']-1)-1) if values['PixelRepresentation'] else (0,2**values['BitsStored']-1)
    if int(stored.min())<lo or int(stored.max())>hi:raise v1.Reject('STORED_BITS_RANGE')
    native=stored.astype(np.float32)*np.float32(values['RescaleSlope'])+np.float32(values['RescaleIntercept'])
    error=check_rescale(stored,native,values['RescaleSlope'],values['RescaleIntercept'])
    padding=values.get('PixelPaddingValue');limit=values.get('PixelPaddingRangeLimit');limit=padding if limit is None else limit
    padding_count=None if padding is None else int(np.count_nonzero((stored>=min(padding,limit))&(stored<=max(padding,limit))))
    return stored,native,{'scalar_rescale_applications':1,'per_instance_coefficients':True,'stored_dtype':str(stored.dtype),'stored_shape':list(stored.shape),
                        'max_float32_float64_difference':error,'padding_count':padding_count,'padding_not_removed_from_raw_QA':True,'VOI_window_applied':False,'model_normalization_applied':False,
                        'LUT_or_realworld_applied':False,'resampling':'NONE'}


def audit(r,accept_source):
    budget=v1.diag.v1.Budget(CAPS);stream=old.Member(old.open_bound_archive(r),r['member'],budget,r['member']['uncompressed_bytes'],r['source_archive']);capture=Capture(stream)
    attempts=0;public={};stage='HEADER_SCAN'
    try:
        scan=TechnicalWalker(capture).scan();values=scan['values'];states=scan['states']
        stage='UNIT_INTERPRETATION'
        branch=interpret(values,states,r['bound_source_HU_claim'],accept_source)
        public={'states':states,'header_complete':scan['complete'],'header_stop':scan['stop_code'],'header_prefix_bytes':scan['consumed_prefix_bytes'],
                'unit_interpretation':branch,'source_identity_status':'SOURCE_DICOM_ID_NONCONFORMANT','identity_values_interpreted_or_modified':False,
                'single_frame_trainable':False,'pixel_decoder_calls':0,'model_calls':0,'training_calls':0}
        if not scan['complete'] or branch['unit_branch'] not in ('EXPLICIT_HU','DICOM_CONDITIONAL_HU','SOURCE_SUPPORTED_RESEARCH_ONLY'):
            return dict(public,status='ISOLATED_NO_PIXEL_DECODE',budget=budget.report())
        stage='STORED_PIXEL_PROFILE'
        if values.get('TransferSyntaxUID')!=v1.codec.JPEG or values.get('Modality')!='CT' or values.get('SamplesPerPixel')!=1 or values.get('PhotometricInterpretation')!='MONOCHROME2' or values.get('NumberOfFrames',1)!=1:raise v1.Reject('FIXED_DECODER_OBJECT_PROFILE')
        if not all(2<=values.get(k,0)<=512 for k in ('Rows','Columns')) or values.get('BitsAllocated') not in (8,16) or not 0<values.get('BitsStored',0)<=values['BitsAllocated'] or values.get('HighBit')!=values['BitsStored']-1 or values.get('PixelRepresentation') not in (0,1):raise v1.Reject('PIXEL_PROFILE')
        stage='NATIVE_2D_GEOMETRY'
        iop=np.asarray(values.get('ImageOrientationPatient'),dtype=float);ipp=np.asarray(values.get('ImagePositionPatient'),dtype=float);spacing=np.asarray(values.get('PixelSpacing'),dtype=float)
        if iop.shape!=(6,) or ipp.shape!=(3,) or spacing.shape!=(2,) or not all(np.isfinite(x).all() for x in (iop,ipp,spacing)) or np.any(spacing<=0) or abs(np.linalg.norm(iop[:3])-1)>1e-4 or abs(np.linalg.norm(iop[3:])-1)>1e-4 or abs(iop[:3]@iop[3:])>1e-4:raise v1.Reject('NATIVE_2D_GEOMETRY')
        # Continue SAME stream, same member, once; no second header/member read.
        stage='FULL_MEMBER_FINISH_CRC'
        capture.header=False
        while stream.emitted<r['member']['uncompressed_bytes']:capture.read(min(32768,r['member']['uncompressed_bytes']-stream.emitted))
        full_sha=stream.finish();raw=b''.join(capture.parts)
        # Mature selected-tag reader accesses only PixelData, no clinical fields.
        from pydicom.filereader import read_dataset
        import struct
        end=144+struct.unpack_from('<I',raw,140)[0]
        ds,_=v1.warn_safe(lambda:read_dataset(io.BytesIO(raw[end:]),False,True,bytelength=len(raw)-end,specific_tags=[0x7fe00010]))
        stage='PIXEL_DECODE_AND_RESCALE_QA'
        attempts=1;(stored,rescaled,qa),_=v1.warn_safe(lambda:stored_to_rescaled(values,ds.PixelData));budget.check()
        stage='ARTIFACT_PUBLICATION'
        artifacts=[]
        for name,array in [('native-stored.npy',stored),('native-rescaled.npy',rescaled)]:
            buffer=io.BytesIO();np.save(buffer,array,allow_pickle=False);content=buffer.getvalue();budget.count('output',len(content));path=Path(r['output_root'])/name
            with os.fdopen(exclusive(path),'wb') as f:f.write(content)
            artifacts.append({'path':str(path),'sha256':old.sha(path),'shape':list(array.shape),'dtype':str(array.dtype)})
        return dict(public,status='SINGLE_FRAME_NUMERICAL_QA_COMPLETE',pixel_decoder_calls=1,qa=qa,artifacts=artifacts,
                    source_full_member_sha256=full_sha,source_member_CRC='PASS',native_geometry={'IPP':ipp.tolist(),'IOP':iop.tolist(),'PixelSpacing':spacing.tolist(),'stack_QA':'NOT_EVALUATED_SINGLE_FRAME'},
                    rescale_coefficients={'slope':values['RescaleSlope'],'intercept':values['RescaleIntercept']},budget=budget.report())
    except Exception as exc:
        return dict(public,**{'status':'STOPPED_NO_RETRY','failure_stage':stage,'reason_code':str(exc) if isinstance(exc,v1.Reject) and str(exc) in {'STORED_BITS_RANGE','NONFINITE_RESCALED_OUTPUT','RESCALE_NUMERICAL_QA','FIXED_DECODER_OBJECT_PROFILE','PIXEL_PROFILE','NATIVE_2D_GEOMETRY','RESCALE_FLOAT32_PARAMETERS'} else v1.safe_reason(exc),'pixel_decoder_attempts':attempts,'pixel_decoder_calls':0 if attempts==0 else 'UNKNOWN_FAILED_ATTEMPT','budget':budget.report(),'model_calls':0,'training_calls':0})
    finally:stream.close()


def publish_ledger(out,result):
    retained=sum(p.stat().st_size for p in Path(out).rglob('*') if p.is_file())
    result['entry_output_bytes_before_ledger']=retained
    # One hard total including arrays, failed remnants and the final ledger.
    remaining=CAPS['output_bytes_total']-retained
    if remaining<=0:raise v1.Reject('ENTRY_TOTAL_OUTPUT_LIMIT')
    old.json_output(Path(out)/'single-frame-ledger-v3.json',result,v1.diag.v1.Budget(dict(CAPS,output_bytes_total=min(64*1024,remaining))))


def pipeline(r,accept_source):
    start=time.monotonic();out=Path(r['output_root']);secure_parent(out);out.mkdir(mode=0o700,exist_ok=False)
    try:result=phase(audit,(r,accept_source),60,start+90,out,4*1024**3)
    except Exception:result={'status':'STOPPED_NO_RETRY','budget':'UNKNOWN_RETAIN_RESERVED','reason_code':'SUPERVISED_PHASE_STOP'}
    result.update(attempts=1,elapsed_seconds=time.monotonic()-start,old_RI_restarted=False,scientific_patient_or_stack_qualification='NOT_ESTABLISHED')
    publish_ledger(out,result)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--request-sha256',required=True);p.add_argument('--execute',action='store_true');p.add_argument('--approval');p.add_argument('--approval-sha256');args=p.parse_args()
    r=bound_json(args.request,args.request_sha256)
    if r['schema']!='RI_HU_SINGLE_CONDITIONAL_DECODE_REQUEST_V3' or r['caps']!=CAPS:raise v1.Reject('EXACT_V3_REQUEST')
    for ref in r['evidence_bindings']:v1.assert_file(ref)
    old.verify_readiness(r['bindings'])
    import importlib,importlib.metadata
    for name,version in r['bindings']['decoder_distributions'].items():
        if importlib.metadata.version(name)!=version:raise v1.Reject('DECODER_VERSION_DRIFT')
    for item in r['bindings']['decoder_module_bindings']:
        loaded=importlib.import_module(item['module'])
        if str(Path(loaded.__file__).resolve())!=str(Path(item['path']).resolve()):raise v1.Reject('LOADED_DECODER_PATH_DRIFT')
        v1.assert_file(item)
    for item in r['bindings']['decoder_binary_bindings']:v1.assert_file(item)
    if str(Path(__file__).resolve()) not in {i['path'] for i in r['bindings']['source_bindings']}:raise v1.Reject('V3_SOURCE_REQUIRED')
    parent=bound_json(r['parent_request']['path'],r['parent_request']['sha256'])
    if r['member']!=parent['stages']['RI-a']['groups'][0]['members'][0] or r['source_archive']!=parent['source_archive'] or r['inventory_binding']!=parent['inventory_binding']:raise v1.Reject('FIXED_FIRST_MEMBER_REQUIRED')
    if not args.execute:print(json.dumps({'status':'CHECK_ONLY_NO_ARCHIVE_BODY_ACCESS'}));return
    if not args.approval or not args.approval_sha256:raise v1.Reject('NEW_V3_APPROVAL_REQUIRED')
    a=bound_json(args.approval,args.approval_sha256)
    expected={'schema':'RI_HU_SINGLE_CONDITIONAL_DECODE_APPROVAL_V3','request_sha256':args.request_sha256,'permit_header_and_conditional_decode':True,'permit_model':False,'permit_training':False,'permit_retry':False}
    if any(type(a.get(k)) is not type(v) or a.get(k)!=v for k,v in expected.items()) or type(a.get('accept_source_supported_research_only')) is not bool:raise v1.Reject('EXACT_V3_ITEMIZED_APPROVAL_REQUIRED')
    if a['accept_source_supported_research_only'] and a.get('source_limitations_accepted')!=r['source_limitations_id']:raise v1.Reject('SOURCE_LIMITATIONS_ACCEPTANCE_REQUIRED')
    if any(os.environ.get(k)!='1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')):raise v1.Reject('CPU1_REQUIRED')
    result=pipeline(r,a['accept_source_supported_research_only']);print(json.dumps({'status':result['status']}))
    if result['status']!='SINGLE_FRAME_NUMERICAL_QA_COMPLETE':raise SystemExit(1)

if __name__=='__main__':
    try:main()
    except Exception:print(json.dumps({'status':'REJECTED','reason_code':'V3_CONTROL_REJECTED','raw_exception_retained':False}));raise SystemExit(1) from None
