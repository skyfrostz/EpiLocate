"""Isolated source-defined research import, not DICOM identity repair.
Real I/O only through a new exact request and itemized approval. No model API.
"""
import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import importlib
import importlib.metadata
import struct
import time
import warnings
import logging
import numpy as np
import pydicom
from pydicom.filereader import read_dataset
from . import a2_six_sop as codec, a2_diagnostic_v2 as diag
from .a0_acquire import bound_json, exclusive, phase, secure_parent

old=codec.old
CONTRACT=Path(__file__).with_name('research_import_contract_v2.json')
TECH={k:v for k,v in old.FIELD_VR.items() if k in codec.FIELDS and k not in {'MediaStorageSOPInstanceUID','SOPInstanceUID','StudyInstanceUID','SeriesInstanceUID','FrameOfReferenceUID'}}
TAGS={'SpecificCharacterSet':0x00080005,'ImageType':0x00080008,'SOPClassUID':0x00080016,'Modality':0x00080060,
 'SliceThickness':0x00180050,'ImagePositionPatient':0x00200032,'ImageOrientationPatient':0x00200037,
 'SamplesPerPixel':0x00280002,'PhotometricInterpretation':0x00280004,'NumberOfFrames':0x00280008,
 'Rows':0x00280010,'Columns':0x00280011,'PixelSpacing':0x00280030,'BitsAllocated':0x00280100,
 'BitsStored':0x00280101,'HighBit':0x00280102,'PixelRepresentation':0x00280103,'PixelPaddingValue':0x00280120,
 'PixelPaddingRangeLimit':0x00280121,'RescaleIntercept':0x00281052,'RescaleSlope':0x00281053,'RescaleType':0x00281054,'PixelData':0x7fe00010}
OPAQUE={'MediaStorageSOPInstanceUID':0x00020003,'SOPInstanceUID':0x00080018,'StudyInstanceUID':0x0020000d,'SeriesInstanceUID':0x0020000e,'FrameOfReferenceUID':0x00200052}
META_TAGS=[0x00020002,0x00020010]

class Reject(ValueError):pass

def safe_reason(exc):
    # Only constants defined by these bounded guards may be retained. No raw
    # exception messages, UID warnings, traceback, or arbitrary library values.
    allowed={node.args[0].value for node in ast.walk(ast.parse(Path(__file__).read_text()))
             if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='Reject'
             and node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str)}
    allowed.update(diag.RESOURCE_CODES|diag.SAFE_PIPELINE_CODES)
    message=str(exc)
    if message.startswith('PHASE_FAILED:'):message=message.split(':',2)[-1]
    return message if message in allowed else 'GROUP_REJECTED_STOP_NO_RETRY'


def digest(raw):return hashlib.sha256(raw).hexdigest()

def warn_safe(fn):
    # pydicom warn_and_log sends BOTH a warning and a logger record. Scope
    # redaction to this call; validation remains at its configured strictness.
    class Redact(logging.Filter):
        def filter(self, record):
            record.msg='PYDICOM_DIAGNOSTIC_REDACTED';record.args=();record.exc_info=None;return True
    logger=logging.getLogger('pydicom');redactor=Redact();logger.addFilter(redactor)
    try:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter('always')
            try:value=fn()
            except Reject:raise
            except Exception:raise Reject('SELECTED_FIELD_OR_CODEC_ERROR') from None
        return value,{'count':len(captured),'categories':sorted({w.category.__name__ for w in captured}),'raw_warning_text_retained':False}
    finally:logger.removeFilter(redactor)


def opaque(ds,tags):
    result={}
    for key,tag in tags.items():
        element=ds.get_item(tag,keep_deferred=True)
        raw=None if element is None else getattr(element,'value',None)
        if raw is not None and not isinstance(raw,bytes):raise Reject('OPAQUE_RAW_VALUE_NOT_AVAILABLE')
        result[key]={'status':'ABSENT' if raw is None else ('EMPTY' if not raw else 'PRESENT_OPAQUE'),
                     'raw_value_sha256':digest(raw) if raw else None}
    return result


def parse_decode(raw,permit_opaque=False,source_identity_status='NOT_EVALUATED'):
    (array,row),warning_evidence=warn_safe(lambda:_parse_decode(raw,permit_opaque,source_identity_status))
    row['parser_warning_evidence'].append(warning_evidence)
    return array,row


def _parse_decode(raw,permit_opaque=False,source_identity_status='NOT_EVALUATED'):
    if len(raw)<144 or raw[128:132]!=b'DICM' or raw[132:140]!=b'\x02\0\0\0UL\x04\0':raise Reject('PART10_META_BOUNDARY_REQUIRED_NO_FORCE')
    end=144+struct.unpack_from('<I',raw,140)[0]
    if not 144<=end<=min(len(raw),128*1024):raise Reject('META_BOUNDARY_INVALID')
    meta_tags=META_TAGS+([OPAQUE['MediaStorageSOPInstanceUID']] if permit_opaque else [])
    meta,w1=warn_safe(lambda:read_dataset(io.BytesIO(raw[132:end]),False,True,bytelength=end-132,specific_tags=meta_tags))
    if str(meta.get('TransferSyntaxUID',''))!=codec.JPEG or str(meta.get('MediaStorageSOPClassUID',''))!=old.CT:raise Reject('EXACT_CT_JPEG_SYNTAX_REQUIRED')
    root_tags=list(TAGS.values())+([v for k,v in OPAQUE.items() if k!='MediaStorageSOPInstanceUID'] if permit_opaque else [])
    ds,w2=warn_safe(lambda:read_dataset(io.BytesIO(raw[end:]),False,True,bytelength=len(raw)-end,specific_tags=root_tags))
    fingerprints={}
    if permit_opaque:
        fingerprints.update(opaque(meta,{'MediaStorageSOPInstanceUID':OPAQUE['MediaStorageSOPInstanceUID']}))
        fingerprints.update(opaque(ds,{k:v for k,v in OPAQUE.items() if k!='MediaStorageSOPInstanceUID'}))
    # Convert only selected nonidentity technical fields. UID values never
    # materialized by this loop or passed to the minimal decoder Dataset.
    def convert():
        values={}
        for key in TAGS:
            if key not in ds or key=='PixelData':continue
            value=ds.get(key)
            if key in ('ImagePositionPatient','ImageOrientationPatient','PixelSpacing'):
                value=[float(v) for v in value]
            elif key in ('Rows','Columns','SamplesPerPixel','NumberOfFrames','BitsAllocated','BitsStored','HighBit','PixelRepresentation'):
                value=int(value)
            elif key in ('RescaleSlope','RescaleIntercept','SliceThickness'):
                value=None if value in (None,'') else float(value)
            elif key=='ImageType':value='\\'.join(value) if not isinstance(value,str) else value
            else:value=str(value)
            values[key]=value
        return values
    values,w3=warn_safe(convert)
    values.update(TransferSyntaxUID=codec.JPEG,MediaStorageSOPClassUID=old.CT)
    if values.get('SOPClassUID')!=old.CT or values.get('Modality')!='CT':raise Reject('CT_OBJECT_PROFILE_MISMATCH')
    if any(s in values.get('ImageType','').upper().split('\\') for s in ('LOCALIZER','SCOUT')):raise Reject('LOCALIZER')
    if values.get('SamplesPerPixel')!=1 or values.get('NumberOfFrames',1)!=1 or values.get('PhotometricInterpretation')!='MONOCHROME2':raise Reject('SINGLE_FRAME_MONOCHROME_REQUIRED')
    if not all(2<=values.get(k,0)<=512 for k in ('Rows','Columns')):raise Reject('MATRIX_LIMIT')
    if values.get('BitsAllocated') not in (8,16) or not 0<values.get('BitsStored',0)<=values['BitsAllocated'] or values.get('HighBit')!=values['BitsStored']-1 or values.get('PixelRepresentation') not in (0,1):raise Reject('PIXEL_BITS')
    iop=np.asarray(values.get('ImageOrientationPatient'),dtype=float);ipp=np.asarray(values.get('ImagePositionPatient'),dtype=float);spacing=np.asarray(values.get('PixelSpacing'),dtype=float)
    if iop.shape!=(6,) or ipp.shape!=(3,) or spacing.shape!=(2,) or not all(np.isfinite(a).all() for a in (iop,ipp,spacing)):raise Reject('MISSING_NATIVE_GEOMETRY')
    if abs(np.linalg.norm(iop[:3])-1)>1e-4 or abs(np.linalg.norm(iop[3:])-1)>1e-4 or abs(iop[:3]@iop[3:])>1e-4 or np.any(spacing<=0):raise Reject('NATIVE_GEOMETRY_REJECTED')
    if values.get('RescaleSlope') in (None,0) or values.get('RescaleIntercept') is None or values.get('RescaleType')!='HU':raise Reject('DECLARED_HU_RESCALE_REQUIRED_NO_DEFAULT_NO_LUT_FALLBACK')
    if 'PixelData' not in ds:raise Reject('PIXEL_DATA_ABSENT')
    array,w4=warn_safe(lambda:codec.decode_pixels(values,ds.PixelData))
    hu=array.astype(np.float32)*np.float32(values['RescaleSlope'])+np.float32(values['RescaleIntercept'])
    if not np.isfinite(hu).all():raise Reject('NONFINITE_HU')
    result={'source_dicom_identity_status':source_identity_status,'PIXEL_QA':'PASS','GEOMETRY_QA':'PASS_NATIVE_SINGLE_FRAME','RESCALE_QA':'PASS_DECLARED_HU',
            'research_status':'LIMITED_SINGLE_FRAME','single_frame_is_trainable_case':False,'shape':list(array.shape),'stored_dtype':str(array.dtype),
            'IPP':ipp.tolist(),'IOP':iop.tolist(),'PixelSpacing':spacing.tolist(),'RescaleSlope':values['RescaleSlope'],'RescaleIntercept':values['RescaleIntercept'],
            'BitsAllocated':values['BitsAllocated'],'BitsStored':values['BitsStored'],'HighBit':values['HighBit'],'PixelRepresentation':values['PixelRepresentation'],
            'full_member_sha256':digest(raw),'HU_array_sha256':digest(hu.tobytes()),'opaque_fingerprints':fingerprints,
            'parser_warning_evidence':[w1,w2,w3,w4],'force_read':False,'global_validation_settings_changed':False,'full_IOD_conformance':'NOT_EVALUATED'}
    return hu,result


def volume(frames,records):
    if len(frames)<2:raise Reject('SINGLE_FRAME_NOT_COMPLETE_STACK')
    if len(frames)!=len(records):raise Reject('FRAME_LEDGER_COUNT_MISMATCH')
    first=records[0];iop=np.asarray(first['IOP']);spacing=np.asarray(first['PixelSpacing']);normal=np.cross(iop[:3],iop[3:])
    positions=np.asarray([r['IPP'] for r in records]);coordinate=positions@normal
    for f,r in zip(frames,records):
        if f.shape!=frames[0].shape or not np.allclose(r['IOP'],iop,atol=1e-4,rtol=0) or not np.allclose(r['PixelSpacing'],spacing,atol=1e-4,rtol=0):raise Reject('MIXED_STACK_GEOMETRY')
    order=np.argsort(coordinate);delta=np.diff(coordinate[order]);distance=float(np.median(delta))
    if distance<=0 or np.any(delta<=1e-4):raise Reject('DUPLICATE_OR_NONPOSITIVE_LAYER')
    if not np.allclose(delta,distance,atol=1e-3,rtol=1e-3):raise Reject('NONUNIFORM_OR_MISSING_LAYER')
    inplane=positions-np.outer(coordinate,normal)
    if not np.allclose(inplane,inplane[0],atol=1e-3,rtol=0):raise Reject('INPLANE_DRIFT_NO_FORCE_CORRECTION')
    for key in ('StudyInstanceUID','SeriesInstanceUID','FrameOfReferenceUID'):
        ids={r['opaque_fingerprints'].get(key,{}).get('raw_value_sha256') for r in records}
        ids.discard(None)
        if len(ids)>1:raise Reject('OPAQUE_SOURCE_GROUP_CONFLICT')
    array=np.stack([frames[i] for i in order])
    affine=np.eye(4);affine[:3,0]=normal*distance;affine[:3,1]=iop[3:]*spacing[0];affine[:3,2]=iop[:3]*spacing[1];affine[:3,3]=positions[order[0]]
    ledger={'GEOMETRY_QA':'PASS_COMPLETE_SELECTED_STACK','shape':list(array.shape),'axis_order':'Z,Y,X','affine_LPS':affine.tolist(),
            'spacing_ZYX_mm':[distance,*spacing.tolist()],'sorted_member_indices':order.tolist(),'native_volume_sha256':digest(array.tobytes()),
            'anatomical_complete':'NOT_ESTABLISHED','resampling':'NONE','clinical_patient_independence_status':'UNKNOWN'}
    return array,ledger


def bind_groups(cases):
    """Directory evidence != clinical identity. No unresolved cross-split links."""
    owners={};bad=set()
    for i,c in enumerate(cases):
        keys=[('group',c['source_group_id']),('volume',c['native_volume_sha256'])]+[('content',r['full_member_sha256']) for r in c.get('frame_ledgers',[])]+[('opaque:'+k,v) for k,v in c.get('source_group_fingerprints',{}).items() if v]
        for key in keys:
            if key in owners and owners[key]!=i:bad.update((i,owners[key]))
            owners[key]=i
    for i,c in enumerate(cases):
        if i in bad:c.update(source_group_status='CONFLICT',research_status='QUARANTINED',reason_code='CROSS_SOURCE_GROUP_EXACT_DUPLICATE_OR_OPAQUE_CONFLICT',training_eligible=False)
        elif c.get('PIXEL_QA')!='PASS' or c.get('RESCALE_QA')!='PASS_DECLARED_HU' or c.get('PROVENANCE_BOUND') is not True or not c.get('publisher_group_evidence_bound') or c.get('source_diagnosis') not in ('COVID-19','CAP','Normal') or c.get('task_label') != int(c.get('source_diagnosis')!='Normal') or c.get('GEOMETRY_QA')!='PASS_COMPLETE_SELECTED_STACK':c.update(source_group_status='UNKNOWN',research_status='QUARANTINED',reason_code='PUBLISHER_GROUP_EVIDENCE_UNKNOWN',training_eligible=False)
        else:c.update(source_group_status='PUBLISHER_SOURCE_SUBJECT_LOCKED',research_status='RESEARCH_READY_SOURCE_DEFINED_EXPLORATORY',training_eligible=True)
        c['clinical_patient_independence_status']='UNKNOWN';c['pretraining_overlap_status']='UNKNOWN';c['independent_test_claim']=False
        c['cross_group_duplicate_audit']='CONFLICT' if i in bad else 'PASS'
    return cases


def consumer_records(cases):
    if any(not c.get('training_eligible') or c.get('research_status')!='RESEARCH_READY_SOURCE_DEFINED_EXPLORATORY' for c in cases):raise Reject('COHORT_HAS_UNRESOLVED_QUARANTINE_NO_SILENT_REPLACEMENT')
    if len({c['record_id'] for c in cases})!=len(cases) or len({c['source_group_id'] for c in cases})!=len(cases):raise Reject('DUPLICATE_RESEARCH_RECORD_OR_CROSS_SPLIT_GROUP')
    return [{'record_id':c['record_id'],'source_group_id':c['source_group_id'],'source_group_status':c['source_group_status'],
             'clinical_patient_independence_status':'UNKNOWN','split':c['split'],'task_label':c['task_label'],
             'source_diagnosis':c['source_diagnosis'],'label_provenance':c['label_provenance'],'label_definition_id':'MD_SOURCE_DIAGNOSIS_WEAK_V1',
             'tensor_artifact':c['tensor_artifact'],'research_status':c['research_status'],'source_dicom_identity_status':c['source_dicom_identity_status'],
             'PIXEL_QA':c['PIXEL_QA'],'RESCALE_QA':c['RESCALE_QA'],'PROVENANCE_BOUND':c['PROVENANCE_BOUND'],
             'cross_split_duplicate_audit':c['cross_group_duplicate_audit'],
             'GEOMETRY_QA':c['GEOMETRY_QA'],'complete_selected_stack':True,'affine_LPS':c['affine_LPS'],'spacing_ZYX_mm':c['spacing_ZYX_mm'],
             'geometry_ledger':c['geometry_ledger'],'cross_group_duplicate_audit':c['cross_group_duplicate_audit'],
             'approved_consumer_use':'CPU_IMPORT_AUDIT_ONLY_PENDING_ENCODER_APPROVAL',
             'pretraining_overlap_status':'UNKNOWN','independent_test_claim':False,'model_input_projection':['tensor','task_label']} for c in cases]


def load_member(request,member,budget):
    s=old.Member(old.open_bound_archive(request),member,budget,request['full_member_bytes_max'],request['source_archive'])
    try:
        pieces=[];left=member['uncompressed_bytes']
        while left:n=min(left,32768);pieces.append(s.read(n));left-=n
        full_sha=s.finish();raw=b''.join(pieces)
    finally:s.close()
    if digest(raw)!=full_sha:raise Reject('FULL_MEMBER_DIGEST_MISMATCH')
    return raw


def sample_key(request,member,full_sha):
    return digest(old.encoded([request['source_archive']['version'],request['source_archive']['sha256'],member['name'],full_sha]))


def group_worker(request,group,out,caps,permit_opaque,single):
    budget=diag.v1.Budget(caps);frames=[];records=[];source_status='SOURCE_DICOM_ID_NONCONFORMANT' if group.get('A3_seed_identity_nonconformant') else 'NOT_EVALUATED'
    for member in group['members']:
        raw=load_member(request,member,budget)
        frame_status=source_status if member['name'] in request.get('A3_known_nonconformant_members',[]) else 'NOT_EVALUATED'
        hu,row=parse_decode(raw,permit_opaque,frame_status)
        row['research_sample_key']=sample_key(request,member,row['full_member_sha256']);records.append(row);frames.append(hu);budget.check()
    directory=Path(out)/group['record_id'];directory.mkdir(mode=0o700)
    if single:arr=frames[0];geom={'GEOMETRY_QA':'PASS_NATIVE_SINGLE_FRAME','training_eligible':False}
    else:arr,geom=volume(frames,records)
    memory=io.BytesIO();np.save(memory,arr,allow_pickle=False);raw=memory.getvalue();budget.count('output',len(raw));p=directory/'native-HU.npy'
    with os.fdopen(exclusive(p),'wb') as f:f.write(raw)
    identity=source_status
    # RI-b/c preserve known nonconformant seed facts from A3 within original 6.
    if group.get('A3_seed_identity_nonconformant'):identity='SOURCE_DICOM_ID_NONCONFORMANT'
    row=dict(group);row.update(geom)
    row.update(source_dicom_identity_status=identity,PIXEL_QA='PASS',RESCALE_QA='PASS_DECLARED_HU',PROVENANCE_BOUND=True,
             research_status='LIMITED_SINGLE_FRAME' if single else 'LIMITED_PENDING_COHORT_GROUP_AUDIT',source_group_status='UNKNOWN',
             clinical_patient_independence_status='UNKNOWN',training_eligible=False,frame_ledgers=records,
             tensor_artifact={'path':str(p),'sha256':old.sha(p),'shape':list(arr.shape),'axis_order':'Y,X' if single else 'Z,Y,X'})
    # Exact cached publisher evidence bound in request, not directory uniqueness.
    row['publisher_group_evidence_bound']=request['publisher_group_semantics']=='PUBLISHER_SUBJECT_DIRECTORY_BOUND' and bool(request['publisher_evidence'])
    row['source_group_fingerprints']={k:records[0]['opaque_fingerprints'].get(k,{}).get('raw_value_sha256') for k in ('StudyInstanceUID','SeriesInstanceUID')}
    row.pop('members');row['budget']=budget.report()
    old.json_output(directory/'research-ledger.json',row,budget)
    row['geometry_ledger']={'path':str(directory/'research-ledger.json'),'sha256':old.sha(directory/'research-ledger.json')}
    row['budget']=budget.report();return row


def pipeline(request,approval):
    start=time.monotonic();out=Path(request['output_root']);secure_parent(out);out.mkdir(mode=0o700,exist_ok=False)
    result={'status':'PARTIAL','attempts':1,'model_calls':0,'stages':{},'training_or_encoder_calls':0};passed_a=set();prior={};passed_b=False
    stopped=False
    for stage in ('RI-a','RI-b','RI-c'):
        spec=request['stages'][stage];stage_start=time.monotonic();rows=[]
        used={k:0 for k in ('compressed_input_bytes','inflated_member_bytes_total','output_bytes_total')}
        observed=dict(used);cost_unknown=False
        if stopped:result['stages'][stage]={'status':'NOT_RUN_PRIOR_FAILURE'};continue
        if not approval.get('permit_'+stage):result['stages'][stage]={'status':'NOT_APPROVED'};continue
        if stage=='RI-b' and not passed_a or stage=='RI-c' and not passed_b:
            result['stages'][stage]={'status':'CONDITION_NOT_MET'};continue
        for group in spec['groups']:
            if stopped:
                rows.append({'record_id':group['record_id'],'research_status':'NOT_RUN','reason_code':'PRIOR_FAILURE_NO_RETRY'});continue
            if stage=='RI-b' and group['source_group_id'] not in passed_a:
                rows.append({'record_id':group['record_id'],'research_status':'QUARANTINED','reason_code':'RIA_MEMBER_FAILED'});continue
            if stage=='RI-c' and group['source_group_id'] in prior:
                row=dict(prior[group['source_group_id']],record_id=group['record_id'],split=group['split'],reuse_lineage='SAME_APPROVED_RUN_RIB_NO_NEW_READ');rows.append(row);continue
            # Reserve exact inventory upper bounds BEFORE dispatch. Failed workers
            # retain this reservation; never reset remaining quota after failure.
            caps=group['caps'];seconds=min(spec['per_group_wall_seconds'],spec['stage_wall_seconds']-(time.monotonic()-stage_start))
            try:
                if seconds<=0:raise Reject('STAGE_WALL_LIMIT')
                if any(used[k]+caps[k]>spec['caps'][k] for k in used):raise Reject('STAGE_RESERVED_BUDGET_LIMIT')
                for k in used:used[k]+=caps[k]
                row=phase(group_worker,(request,group,str(out),caps,approval['permit_opaque_uid_fingerprints'][stage],stage=='RI-a'),seconds,start+request['overall_wall_seconds'],out,request['disk_free_floor_bytes'])
                rows.append(row)
                for k,report in (('compressed_input_bytes','compressed_input_bytes'),('inflated_member_bytes_total','inflated_bytes'),('output_bytes_total','output_bytes')):observed[k]+=row['budget'][report]
                if stage=='RI-a':passed_a.add(group['source_group_id'])
            except Exception as exc:
                rows.append({'record_id':group['record_id'],'source_group_id':group['source_group_id'],'research_status':'QUARANTINED',
                             'reason_code':safe_reason(exc),'failure_type':type(exc).__name__,'raw_error_text_retained':False})
                cost_unknown=True;stopped=True
        if stage!='RI-a':bind_groups([r for r in rows if 'native_volume_sha256' in r])
        all_pass=bool(rows) and len(rows)==len(spec['groups']) and all(r.get('PIXEL_QA')=='PASS' and r.get('research_status')!='QUARANTINED' for r in rows) and not stopped
        if stage=='RI-b':
            passed_b=all_pass and all(r.get('training_eligible') for r in rows)
            prior={r['source_group_id']:r for r in rows if r.get('training_eligible')}
        receipt={'status':'STOPPED_NO_RETRY' if stopped else 'COMPLETE_WITH_REPORTED_QUARANTINES','rows':rows,
                 'reserved_attempt_upper_bounds':used,'observed_successful_groups':observed,
                 'failed_group_actual_costs':'UNKNOWN_RETAINED_WITHIN_RESERVED_CAP' if cost_unknown else 'NO_FAILED_GROUP',
                 'all_selected_groups_passed':all_pass}
        if stage=='RI-c' and len(rows)==60 and all_pass:
            consumer=consumer_records(rows);control=diag.v1.Budget(dict(spec['caps'],output_bytes_total=request['consumer_bytes_max']))
            old.json_output(out/'ENC_RESEARCH_SOURCE_CASES_V2.json',consumer,control)
            receipt['consumer_path']=str(out/'ENC_RESEARCH_SOURCE_CASES_V2.json');receipt['consumer_sha256']=old.sha(out/'ENC_RESEARCH_SOURCE_CASES_V2.json')
        result['stages'][stage]=receipt
    result['status']='PARTIAL_STOPPED_NO_RETRY' if stopped else 'FINISHED_APPROVED_STAGES_NO_SCIENTIFIC_CLAIM'
    result['elapsed_seconds']=time.monotonic()-start
    result['retained_output_bytes_before_receipt']=sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
    old.json_output(out/'receipt.json',result,diag.v1.Budget(dict(codec.B,output_bytes_total=request['receipt_bytes_max'])))
    return result


def validate_request(r):
    if r['schema']!='RI_EXACT_BOUNDED_REQUEST_V1' or r['contract_sha256']!=old.sha(CONTRACT):raise Reject('EXACT_CONTRACT_REQUIRED')
    if r['models_permitted'] is not False or r['training_permitted'] is not False or r['source_repair_permitted'] is not False:raise Reject('RESEARCH_IMPORT_ONLY')
    for evidence in r['publisher_evidence']:bound_json(evidence['path'],evidence['sha256']) if evidence['path'].endswith('.json') else assert_file(evidence)
    inventory=Path(r['inventory_binding']['path']);assert_file(r['inventory_binding'])
    rows=[json.loads(line) for line in inventory.read_text().splitlines()];names={m['name']:m for m in rows}
    from .research_import_prepare import selected_groups
    expected=selected_groups(rows)
    selected=r['stages']['RI-c']['groups']
    if [{k:g[k] for k in ('directory','source_diagnosis','task_label','split','members')} for g in selected]!=expected:raise Reject('FIXED_DETERMINISTIC_COHORT_DRIFT')
    parents=[bound_json(p['path'],p['sha256']) for p in r['parent_bindings']]
    if r['source_archive']!=parents[0]['source_archive'] or r['inventory_binding']!=parents[0]['inventory_binding']:raise Reject('SOURCE_ARCHIVE_BINDING_DRIFT')
    seed=parents[0]['selection'];seed_names={x['member']['name'] for x in seed};seed_dirs={x['directory'] for x in seed}
    if set(r['A3_known_nonconformant_members'])!=seed_names:raise Reject('A3_IDENTITY_EVIDENCE_DRIFT')
    for stage in ('RI-a','RI-b'):
        if {g['directory'] for g in r['stages'][stage]['groups']}!=seed_dirs:raise Reject('ORIGINAL_SIX_ONLY')
        for g in r['stages'][stage]['groups']:
            locked=[next(x['member'] for x in seed if x['directory']==g['directory'])] if stage=='RI-a' else next(x['members'] for x in expected if x['directory']==g['directory'])
            if g['members']!=locked:raise Reject('ORIGINAL_LOCKED_MEMBERS_DRIFT')
    if set(r['stages'])!={'RI-a','RI-b','RI-c'}:raise Reject('EXACT_STAGE_SET_REQUIRED')
    if [len(r['stages'][s]['groups']) for s in ('RI-a','RI-b','RI-c')]!=[6,6,60]:raise Reject('EXACT_FIXED_GROUP_COUNTS_REQUIRED')
    for spec in r['stages'].values():
        if len({g['source_group_id'] for g in spec['groups']})!=len(spec['groups']):raise Reject('SOURCE_GROUP_DUPLICATE')
        for group in spec['groups']:
            if group['A3_seed_identity_nonconformant'] != (group['directory'] in seed_dirs):raise Reject('IDENTITY_NOT_PERMISSION_EVIDENCE')
            if not group['members'] or any(m['name'].rsplit('/',1)[0]!=group['directory'] for m in group['members']):raise Reject('MIXED_SOURCE_DIRECTORY')
            for m in group['members']:
                if names.get(m['name'])!=m:raise Reject('EXACT_MEMBER_METADATA_DRIFT')
    if any(m['uncompressed_bytes']>r['full_member_bytes_max'] for s in r['stages'].values() for g in s['groups'] for m in g['members']):raise Reject('MEMBER_CAP_NOT_SUFFICIENT')


def assert_file(item):
    if old.sha(item['path'])!=item['sha256']:raise Reject('CONTROL_FILE_DRIFT')


def main():
    p=argparse.ArgumentParser()
    for f in ('request','request-sha256','readiness','readiness-sha256'):p.add_argument('--'+f,required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--approval');p.add_argument('--approval-sha256')
    args=p.parse_args();r=bound_json(args.request,args.request_sha256);b=bound_json(args.readiness,args.readiness_sha256);old.verify_readiness(b)
    if b['request_sha256']!=args.request_sha256 or not {str(Path(__file__).resolve()),str(CONTRACT.resolve())}.issubset({str(Path(i['path']).resolve()) for i in b['source_bindings']}):raise Reject('NEW_RI_BINDING_REQUIRED')
    for package,version in b['decoder_distributions'].items():
        if importlib.metadata.version(package)!=version:raise Reject('DECODER_VERSION_DRIFT')
    for i in b['decoder_module_bindings']:
        module=importlib.import_module(i['module'])
        if Path(module.__file__).resolve()!=Path(i['path']).resolve():raise Reject('LOADED_DECODER_PATH_DRIFT')
        assert_file(i)
    for i in b['decoder_binary_bindings']:assert_file(i)
    validate_request(r)
    if not args.execute:print(json.dumps({'status':'CHECK_ONLY_NO_ARCHIVE_BODY_ACCESS'}));return
    if not args.approval or not args.approval_sha256:raise Reject('NEW_ITEMIZED_RI_APPROVAL_REQUIRED')
    a=bound_json(args.approval,args.approval_sha256)
    expected={'schema':'RI_ITEMIZED_APPROVAL_V1','request_sha256':args.request_sha256,'readiness_sha256':args.readiness_sha256,'permit_model':False,'permit_training':False,'permit_source_repair':False}
    if any(type(a.get(k)) is not type(v) or a.get(k)!=v for k,v in expected.items()) or any(type(a.get(k)) is not bool for k in ('permit_RI-a','permit_RI-b','permit_RI-c','permit_full_member_reads')):raise Reject('EXACT_ITEMIZED_APPROVAL_REQUIRED')
    if a.get('permit_full_member_reads') is not True or not isinstance(a.get('permit_opaque_uid_fingerprints'),dict) or any(type(a['permit_opaque_uid_fingerprints'].get(s)) is not bool for s in ('RI-a','RI-b','RI-c')):raise Reject('PER_STAGE_OPAQUE_AND_FULL_MEMBER_APPROVAL_REQUIRED')
    if any(os.environ.get(k)!='1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')):raise Reject('CPU_ONE_THREAD_REQUIRED')
    result=pipeline(r,a);print(json.dumps({'status':result['status']}))
    if result['status']=='PARTIAL_STOPPED_NO_RETRY':raise SystemExit(1)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'status':'REJECTED','reason_code':str(exc) if isinstance(exc,Reject) else 'CONTROL_OR_RUNTIME_ERROR','raw_error_text_retained':False}))
        raise SystemExit(1) from None
