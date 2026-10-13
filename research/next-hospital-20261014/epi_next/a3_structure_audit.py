"""Finite Explicit-LE structural walk, selected root statuses, zero pixel read.
This is not a general DICOM parser or complete IOD validator.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time
from . import a2_diagnostic_v2 as diagnostics
from .a0_acquire import bound_json, exclusive, phase, secure_parent

old=diagnostics.old
PARENT_SHA='0000000000000000000000000000000000000000000000000000000000000000'
META={(2,2):'MediaStorageSOPClassUID',(2,3):'MediaStorageSOPInstanceUID',(2,16):'TransferSyntaxUID'}
ROOT={(8,22):'SOPClassUID',(8,24):'SOPInstanceUID',(8,96):'Modality',
      (32,13):'StudyInstanceUID',(32,14):'SeriesInstanceUID',
      (40,2):'SamplesPerPixel',(40,4):'PhotometricInterpretation',(40,8):'NumberOfFrames',
      (40,16):'Rows',(40,17):'Columns',(40,256):'BitsAllocated',(40,257):'BitsStored',
      (40,258):'HighBit',(40,259):'PixelRepresentation'}
CAPS={'compressed_input_bytes':2*1024**2,'inflated_header_prefix_bytes_per_member':128*1024,
      'inflated_header_prefix_bytes_total':768*1024,'output_bytes_total':512*1024,
      'RSS_stop_bytes':256*1024**2,'wall_seconds':60,'element_count_per_member':4096,
      'depth_max':16,'structural_events_max_per_member':32,'whitelist_value_bytes_per_element':4096}
OVERALL={'wall_seconds':90,'cleanup_reserve_seconds':30,'CPU_threads':1,'max_attempts':1,'disk_free_floor_bytes':4*1024**3}

class Stop(Exception):
    def __init__(self,code,ctx,category='structure'):
        self.code,self.ctx,self.category=code,ctx,category
        super().__init__(code)

class Walker:
    def __init__(self,stream,member,caps=CAPS):
        self.s,self.member,self.caps=stream,member,caps
        self.fields={key:{'status':'NOT_REACHED'} for key in list(META.values())+list(ROOT.values())}
        self.values={};self.events=[];self.events_truncated=False;self.count=0;self.depth=0
        self.ctx={'domain':'meta','sequence_path':[],'tag':None,'VR':None,'declared_VL':None,'element_offset':0}
        self.root_completed=False;self.meta_completed=False
        self.structural_stop=None;self.last_tags={}
    def fail(self,code,category='structure'):
        table=META if self.ctx['domain']=='meta' else (ROOT if self.ctx['domain']=='dataset' else {})
        key=next((k for tag,k in table.items() if self.ctx['tag']=='%04X,%04X'%tag),None)
        if key and self.fields[key]['status']=='NOT_REACHED':
            self.fields[key]=dict(self.ctx,keyword=key,status='INVALID',reason_code=code,consumed_prefix_bytes=self.s.emitted)
        raise Stop(code,dict(self.ctx,consumed_prefix_bytes=self.s.emitted),category)
    def read(self,n,end=None):
        if end is not None and self.s.emitted+n>end:self.fail('CONTEXT_BOUNDARY_EXCEEDED','boundary')
        try:return self.s.read(n)
        except (old.GuardError,old.HeaderError) as exc:
            code=str(exc)
            if isinstance(exc,old.GuardError) and code in diagnostics.RESOURCE_CODES:self.fail(code,'resource_stop')
            if code in diagnostics.TRUNCATION_CODES:self.fail(code,'truncation')
            if code in diagnostics.BOUNDARY_CODES:self.fail(code,'boundary_or_prefix_limit')
            self.fail('HEADER_READ_TRUNCATED' if isinstance(exc,old.HeaderError) else 'UNCLASSIFIED_GUARD_STOP', 'truncation' if isinstance(exc,old.HeaderError) else 'resource_stop')
    def skip(self,n,end):
        # Discard scalars without decoding clinical or nested identity values.
        while n:
            take=min(n,32768);self.read(take,end);n-=take
    def event(self,code):
        if len(self.events)<self.caps['structural_events_max_per_member']:
            self.events.append(dict(self.ctx,event_code=code,consumed_prefix_bytes=self.s.emitted))
        else:self.events_truncated=True
    def header(self,end,path,domain):
        self.ctx={'domain':domain,'sequence_path':list(path),'tag':None,'VR':None,'declared_VL':None,'element_offset':self.s.emitted}
        self.count+=1
        if self.count>self.caps['element_count_per_member']:self.fail('ELEMENT_COUNT_LIMIT','resource_stop')
        tag=struct.unpack('<HH',self.read(4,end));self.ctx['tag']='%04X,%04X'%tag
        if tag[0]==0xfffe:
            n=struct.unpack('<I',self.read(4,end))[0];self.ctx['declared_VL']=n
            return tag,None,n
        try:vr=self.read(2,end).decode('ascii')
        except UnicodeError:self.fail('VR_ENCODING_INVALID')
        self.ctx['VR']=vr
        if vr not in old.VRS:self.fail('VR_UNSUPPORTED')
        if vr in old.LONG_VR:
            if self.read(2,end)!=b'\0\0':self.fail('VR_RESERVED_INVALID')
            n=struct.unpack('<I',self.read(4,end))[0]
        else:n=struct.unpack('<H',self.read(2,end))[0]
        self.ctx['declared_VL']=n
        return tag,vr,n
    def length_end(self,n,parent):
        if n==0xffffffff:return None
        if n%2:self.fail('ODD_VALUE_LENGTH')
        end=self.s.emitted+n
        if parent is not None and end>parent:self.fail('DECLARED_LENGTH_EXCEEDS_PARENT','boundary')
        return end
    def selected(self,key,vr,n,end):
        record=dict(self.ctx,keyword=key,consumed_prefix_bytes=self.s.emitted)
        if self.fields[key]['status']!='NOT_REACHED':
            self.fields[key]=dict(record,status='INVALID',reason_code='DUPLICATE_ROOT_OR_META_FIELD');return self.skip(n,end)
        if n>self.caps['whitelist_value_bytes_per_element']:
            self.fields[key]=dict(record,status='INVALID',reason_code='SELECTED_VALUE_LIMIT');self.fail('SELECTED_VALUE_LIMIT','resource_stop')
        if vr!=old.FIELD_VR[key]:
            self.fields[key]=dict(record,status='INVALID',reason_code='VR_MISMATCH');return self.skip(n,end)
        try:raw=self.read(n,end)
        except Stop as exc:
            self.fields[key]=dict(record,status='INVALID',reason_code=exc.code,consumed_prefix_bytes=self.s.emitted)
            raise
        record['consumed_prefix_bytes']=self.s.emitted
        if not raw:
            self.fields[key]=dict(record,status='EMPTY');self.values[key]=None;return
        try:
            if vr=='UI':
                value=diagnostics.uid_value(raw,True,'3',None,record,'PS3.5-9.1')
            elif vr=='US':
                if len(raw)!=2:raise ValueError()
                value=struct.unpack('<H',raw)[0]
            else:
                # Only Modality, PhotometricInterpretation, NumberOfFrames.
                value=raw.decode('ascii').rstrip(' ')
                if not value:
                    self.fields[key]=dict(record,status='EMPTY');self.values[key]=None;return
                if vr=='IS':
                    if len(value)>12:raise ValueError()
                    value=int(value)
                elif len(value)>16 or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _' for c in value):raise ValueError()
        except (ValueError,UnicodeError) as exc:
            code=exc.diagnostic['reason_code'] if isinstance(exc,diagnostics.DiagnosticError) else 'SELECTED_SYNTAX_INVALID'
            self.fields[key]=dict(record,status='INVALID',reason_code=code);return
        self.fields[key]=dict(record,status='PRESENT_VALID');self.values[key]=value
    def sequence(self,n,parent,path):
        seq_end=self.length_end(n,parent)
        bound=parent if seq_end is None else seq_end
        self.event('SQ_ENTER')
        index=0
        while True:
            if seq_end is not None and self.s.emitted==seq_end:return
            tag,vr,length=self.header(bound,path,'dataset/sequence')
            if tag==(0xfffe,0xe0dd):
                if seq_end is not None or length!=0:self.fail('UNEXPECTED_OR_NONZERO_SEQUENCE_DELIMITER')
                self.event('SQ_DELIMITER');return
            if tag!=(0xfffe,0xe000):self.fail('SEQUENCE_EXPECTED_ITEM')
            index+=1;self.event('ITEM_ENTER')
            item_end=self.length_end(length,bound)
            # path length counts SQ nesting; item indices do not add depth.
            self.dataset(item_end if item_end is not None else bound,path+(f'item:{index}',),False,item_end is None)
    def dataset(self,end,path,root,undefined_item=False):
        while True:
            if end is not None and self.s.emitted==end:
                if undefined_item:self.fail('MISSING_ITEM_DELIMITER','boundary')
                if root:self.root_completed=True
                return
            tag,vr,n=self.header(end,path,'dataset' if root else 'dataset/item')
            if tag==(0xfffe,0xe00d):
                if not undefined_item or n!=0:self.fail('UNEXPECTED_OR_NONZERO_ITEM_DELIMITER')
                self.event('ITEM_DELIMITER');return
            if tag[0]==0xfffe:self.fail('UNEXPECTED_SPECIAL_ITEM_TAG')
            if not root and tag[0] in (0,2,6):self.fail('FORBIDDEN_GROUP_INSIDE_ITEM','PS3.5-7.5.1')
            if root and tag[0]==2:self.fail('FILE_META_IN_ROOT_DATASET')
            previous=self.last_tags.get(tuple(path))
            if previous is not None and tag<=previous:
                if root and tag in ROOT:
                    self.fields[ROOT[tag]]=dict(self.ctx,status='INVALID',reason_code='DUPLICATE_OR_REVERSED_TAG_ORDER')
                self.fail('DUPLICATE_OR_REVERSED_TAG_ORDER')
            self.last_tags[tuple(path)]=tag
            if tag in old.PIXELS:
                self.event('PIXEL_VALUE_NOT_READ')
                if root:self.root_completed=True
                self.fail('ROOT_PIXEL_VALUE_BOUNDARY' if root else 'NESTED_PIXEL_VALUE_BOUNDARY','pixel_stop')
            if vr=='SQ':
                self.depth+=1
                if self.depth>self.caps['depth_max']:self.fail('DEPTH_LIMIT','resource_stop')
                self.sequence(n,end,path+('%04X,%04X'%tag,))
                self.depth-=1;continue
            if vr=='UN' or n==0xffffffff:self.fail('UNSUPPORTED_UN_OR_UNDEFINED_SCALAR')
            self.length_end(n,end)
            if root and tag in ROOT:self.selected(ROOT[tag],vr,n,end)
            else:self.skip(n,end)
    def run(self):
        code='ROOT_DATASET_END';category='complete';stopped=None
        try:
            if self.read(132)[128:]!=b'DICM':self.fail('DICM_REQUIRED_NO_FORCE')
            tag,vr,n=self.header(None,(),'meta')
            if tag!=(2,0) or vr!='UL' or n!=4:self.fail('FILE_META_GROUP_LENGTH_REQUIRED')
            length=struct.unpack('<I',self.read(4))[0];end=self.s.emitted+length
            if end>self.caps['inflated_header_prefix_bytes_per_member']:self.fail('FILE_META_BOUNDARY_LIMIT','boundary_or_prefix_limit')
            while self.s.emitted<end:
                tag,vr,n=self.header(end,(),'meta')
                if tag[0]!=2 or tag==(2,0):self.fail('INVALID_FILE_META_CONTEXT')
                if vr in ('SQ','UN') or n==0xffffffff:self.fail('FILE_META_CONTAINER_UNSUPPORTED')
                self.length_end(n,end)
                if tag in META:self.selected(META[tag],vr,n,end)
                else:self.skip(n,end)
            self.meta_completed=True
            for key in META.values():
                if self.fields[key]['status']=='NOT_REACHED':self.fields[key]={'status':'ABSENT'}
            if self.values.get('TransferSyntaxUID') not in (diagnostics.v1.JPEG,'1.2.840.10008.1.2.1'):
                self.fail('UNKNOWN_OR_UNSUPPORTED_DATASET_ENCODING','encoding')
            self.dataset(self.s.row['uncompressed_bytes'],(),True)
        except Stop as exc:code,category,stopped=exc.code,exc.category,exc.ctx
        if self.root_completed:
            for key in ROOT.values():
                if self.fields[key]['status']=='NOT_REACHED':self.fields[key]={'status':'ABSENT'}
        classes=[self.values.get(k) for k in ('MediaStorageSOPClassUID','SOPClassUID')]
        class_match=None if not all(classes) else classes[0]==classes[1]
        object_type='CLASSIC_CT' if classes==[old.CT,old.CT] else ('OTHER_SAME_CLASS' if class_match is True else ('CLASS_MISMATCH' if class_match is False else 'UNKNOWN'))
        public_classes={old.CT:'CLASSIC_CT','1.2.840.10008.5.1.4.1.1.4':'MR_IMAGE','1.2.840.10008.5.1.4.1.1.2.1':'ENHANCED_CT','1.2.840.10008.5.1.4.1.1.7':'SECONDARY_CAPTURE'}
        class_symbols=[public_classes.get(c,'OTHER_SOP_CLASS') if c else 'UNKNOWN' for c in classes]
        identities=[self.values.get(k) for k in ('MediaStorageSOPInstanceUID','SOPInstanceUID')]
        identity_match=None if not all(identities) else identities[0]==identities[1]
        technical={k:self.values[k] for k in ROOT.values() if k in self.values and isinstance(self.values[k],int)}
        modality=self.values.get('Modality')
        technical['Modality']=modality if modality in {'CT','MR','US','NM','PT','DX','CR','XA','RF','SC','OT'} else 'UNKNOWN_OR_OTHER_CODE'
        photo=self.values.get('PhotometricInterpretation')
        technical['PhotometricInterpretation']=photo if photo in {'MONOCHROME1','MONOCHROME2','RGB','YBR_FULL','YBR_FULL_422','PALETTE COLOR'} else 'UNKNOWN_OR_OTHER_CODE'
        violations=[]
        if object_type=='CLASSIC_CT':
            for key in ('SOPClassUID','SOPInstanceUID','StudyInstanceUID','SeriesInstanceUID','Modality','Rows','Columns','SamplesPerPixel','PhotometricInterpretation','BitsAllocated','BitsStored','HighBit','PixelRepresentation'):
                if self.fields[key]['status'] in ('ABSENT','EMPTY','INVALID'):violations.append({'keyword':key,'reason_code':'CLASSIC_CT_REQUIRED_SELECTED_FIELD_'+self.fields[key]['status']})
        complete=self.root_completed and category in ('pixel_stop','complete')
        findings=[]
        v=self.values
        if object_type=='CLASSIC_CT' and complete:
            if v.get('Modality')!='CT':findings.append('CLASSIC_CT_MODALITY_MISMATCH')
            if not all(isinstance(v.get(k),int) and 2<=v[k]<=1024 for k in ('Rows','Columns')):findings.append('MATRIX_PROFILE_REJECTED')
            if v.get('SamplesPerPixel')!=1 or photo!='MONOCHROME2' or v.get('NumberOfFrames',1)!=1:findings.append('SINGLE_FRAME_MONOCHROME_PROFILE_REJECTED')
            if v.get('BitsAllocated') not in (8,16) or not isinstance(v.get('BitsStored'),int) or not 0<v.get('BitsStored',0)<=v.get('BitsAllocated',0) or v.get('HighBit')!=v.get('BitsStored',0)-1 or v.get('PixelRepresentation') not in (0,1):findings.append('PIXEL_BITS_PROFILE_REJECTED')
            if identity_match is not True:findings.append('META_DATASET_INSTANCE_MATCH_NOT_ESTABLISHED')
            if code=='ROOT_PIXEL_VALUE_BOUNDARY':
                if stopped['tag']!='7FE0,0010' or stopped['VR'] not in ('OB','OW'):findings.append('PIXEL_HEADER_PROFILE_REJECTED')
                elif v.get('TransferSyntaxUID')==diagnostics.v1.JPEG and stopped['declared_VL']!=0xffffffff:findings.append('ENCAPSULATED_PIXEL_LENGTH_PROFILE_REJECTED')
        return {'anonymous_member':self.member,'status':'COMPLETE_SELECTED_ROOT_HEADER' if complete else 'PARTIAL',
                'stop_code':code,'stop_class':category,'stop_context':stopped,'fields':self.fields,'object_type':object_type,
                'public_class_symbols':class_symbols,'meta_dataset_class_match':class_match,'meta_dataset_instance_match':identity_match,'technical_values':technical,'limited_technical_findings':findings,'absence_scope':'SCANNED_HEADER_ONLY_NOT_UNREAD_TRAILING_DATASET',
                'Classic_CT_selected_violations':violations,'full_IOD_conformance':'NOT_EVALUATED',
                'root_completed_up_to_pixel_or_member_end':self.root_completed,'meta_completed':self.meta_completed,
                'element_count':self.count,'structural_events':self.events,'structural_events_truncated':self.events_truncated,
                'consumed_prefix_bytes':self.s.emitted,'prefix_sha256':self.s.hash.hexdigest(),'pixel_values_emitted':0,
                'reason_to_propose_pixel_decode':'NO_REQUIRED_SELECTED_FIELD_VIOLATIONS' if complete and code=='ROOT_PIXEL_VALUE_BOUNDARY' and object_type=='CLASSIC_CT' and not violations and not findings and all(self.fields[k]['status']=='PRESENT_VALID' for k in META.values()) else 'NO_OR_NOT_ESTABLISHED',
                'pixel_decode_authorized':False}


def partial_row(member,code,category,retained=False):
    return {'anonymous_member':member,'status':'PARTIAL','stop_code':code,'stop_class':category,
            'fields':{key:{'status':'NOT_REACHED','reason_code':'PHASE_RESULT_NOT_RETAINED' if retained else 'STOP_BEFORE_MEMBER'} for key in list(META.values())+list(ROOT.values())},
            'object_type':'UNKNOWN','full_IOD_conformance':'NOT_EVALUATED','consumed_prefix_bytes':None,
            'pixel_values_emitted':0,'pixel_decode_authorized':False,'reason_to_propose_pixel_decode':'NO_OR_NOT_ESTABLISHED'}


def audit(request):
    budget=diagnostics.v1.Budget(CAPS);rows=[]
    archive=old.open_bound_archive(request)
    global_stop=False;attempted=0;started=0
    for selected in request['selection']:
        attempted+=1
        try:stream=old.Member(archive,selected['member'],budget,CAPS['inflated_header_prefix_bytes_per_member'],request['source_archive'])
        except old.GuardError as exc:
            code=str(exc)
            if code not in diagnostics.RESOURCE_CODES:raise
            rows.append(partial_row(selected['candidate_id'],code,'resource_stop'));global_stop=True;break
        started+=1
        try:row=Walker(stream,selected['candidate_id']).run()
        finally:stream.close()
        rows.append(row)
        if row['stop_class']=='resource_stop':global_stop=True;break
    if global_stop:
        retained={r['anonymous_member'] for r in rows}
        rows.extend(partial_row(s['candidate_id'],'STOP_BEFORE_MEMBER','not_attempted') for s in request['selection'] if s['candidate_id'] not in retained)
    return {'rows':rows,'global_stop':global_stop,'budget':budget.report(),'attempted_members':attempted,'header_scan_started_members':started,'attempts':1,'model_calls':0,'pixel_decodes':0}


def pipeline(request):
    start=time.monotonic();out=Path(request['output_root']);secure_parent(out);out.mkdir(mode=0o700,exist_ok=False)
    receipt={'status':'FAILED','attempts':1,'model_calls':0,'pixel_decodes':0}
    try:
        result=phase(audit,(request,),CAPS['wall_seconds'],start+OVERALL['wall_seconds'],out,OVERALL['disk_free_floor_bytes'])
        control=diagnostics.v1.Budget(dict(CAPS,output_bytes_total=CAPS['output_bytes_total']-32768))
        digest=old.json_output(out/'six-member-structure.json',result,control)
        receipt.update(status='PARTIAL' if result['global_stop'] or any(r['status']=='PARTIAL' for r in result['rows']) else 'COMPLETE_SELECTED_HEADER_AUDIT',
                       report_sha256=digest,report_bytes=control.report()['output_bytes'],audit_budget=result['budget'],global_stop=result['global_stop'],audited_members=result['header_scan_started_members'],reported_members=len(result['rows']),attempted_members=result['attempted_members'])
    except Exception as exc:
        code=str(exc)
        if code.startswith(('PHASE_FAILED:GuardError:','PHASE_FAILED:HeaderError:')):code=code.split(':',2)[2]
        safe=code in diagnostics.SAFE_PIPELINE_CODES|diagnostics.TRUNCATION_CODES|diagnostics.BOUNDARY_CODES
        receipt.update(reason_code=code if safe else 'BOUNDED_AUDIT_FAILURE',failure_type=type(exc).__name__)
        if code in diagnostics.RESOURCE_CODES | {'PHASE_OR_OVERALL_TIMEOUT','DISK_RESERVE'}:
            partial={'rows':[partial_row(s['candidate_id'],code,'resource_stop',True) for s in request['selection']],
                     'global_stop':True,'budget':'UNKNOWN_NO_PHASE_RESULT','attempts':1,'model_calls':0,'pixel_decodes':0}
            raw_report=old.encoded(partial)
            if len(raw_report)>CAPS['output_bytes_total']-32768:raise old.GuardError('OUTPUT_LIMIT')
            path=out/'six-member-structure.json'
            with os.fdopen(exclusive(path),'wb') as f:f.write(raw_report)
            receipt.update(status='PARTIAL',global_stop=True,report_sha256=old.sha(path),report_bytes=len(raw_report),audit_budget='UNKNOWN_NO_PHASE_RESULT',audited_members=0)
    finally:receipt['elapsed_seconds']=time.monotonic()-start
    raw=old.encoded(receipt)
    if len(raw)>32768:raise old.GuardError('RECEIPT_LIMIT')
    with os.fdopen(exclusive(out/'receipt.json'),'wb') as f:f.write(raw)
    return receipt


def validate(request):
    parent=bound_json(request['parent_request_path'],PARENT_SHA)
    for k in ('selection','source_archive','inventory_binding'):
        if request[k]!=parent[k]:raise old.GuardError('EXACT_ORIGINAL_SIX_REQUIRED')
    fields=[{'tag':'%04X,%04X'%tag,'keyword':key} for tag,key in list(META.items())+list(ROOT.items())]
    if request['schema']!='A3_STRUCTURE_AUDIT_V1' or request['selected_fields']!=fields or request['caps']!=CAPS or request['overall_caps']!=OVERALL:raise old.GuardError('EXACT_STRUCTURE_SCOPE_REQUIRED')
    if any(request[k] is not False for k in ('pixel_decode_permitted','models_permitted','new_codecs_permitted')):raise old.GuardError('HEADER_ONLY_REQUIRED')


def main():
    p=argparse.ArgumentParser()
    for f in ('request','request-sha256','readiness','readiness-sha256'):p.add_argument('--'+f,required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--start-notice');p.add_argument('--start-notice-sha256')
    args=p.parse_args();request=bound_json(args.request,args.request_sha256);b=bound_json(args.readiness,args.readiness_sha256)
    old.verify_readiness(b)
    python=b['python_binding']
    if Path(python['path']).resolve()!=Path(sys.executable).resolve() or old.sha(python['path'])!=python['sha256']:raise old.GuardError('PYTHON_BINDING_DRIFT')
    needed={str(Path(m.__file__).resolve()) for m in (diagnostics,diagnostics.v1,diagnostics.v1.meta)}|{str(Path(__file__).resolve())}
    if not needed.issubset({str(Path(i['path']).resolve()) for i in b['source_bindings']}):raise old.GuardError('A3_SOURCE_BINDING_REQUIRED')
    if b['request_sha256']!=args.request_sha256:raise old.GuardError('REQUEST_BINDING_MISMATCH')
    validate(request)
    if not args.execute:print(json.dumps({'status':'CHECK_ONLY_NO_MEMBER_ACCESS'}));return
    if not args.start_notice or not args.start_notice_sha256:raise old.GuardError('COORDINATOR_UNIQUE_START_NOTICE_REQUIRED')
    notice=bound_json(args.start_notice,args.start_notice_sha256)
    expected={'schema':'A3_STRUCTURE_UNIQUE_START','request_sha256':args.request_sha256,'readiness_sha256':args.readiness_sha256,'permit_structure_audit':True,'permit_pixel_decode':False,'permit_model':False,'max_attempts':1}
    if any(type(notice.get(k)) is not type(v) or notice.get(k)!=v for k,v in expected.items()):raise old.GuardError('UNIQUE_START_SCOPE_MISMATCH')
    if any(os.environ.get(k)!='1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')):raise old.GuardError('CPU_ONE_THREAD_REQUIRED')
    r=pipeline(request);print(json.dumps({'status':r['status']}))
    if r['status']=='FAILED':raise SystemExit(1)

if __name__=='__main__':main()
