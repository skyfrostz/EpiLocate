"""R76 fixed60 import: reuse RI geometry/grouping and V5 value-preserving codec.
No science changes to old RI or single-member V5. New exact approval required.
"""

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[3]
import argparse,ast,fcntl,hashlib,io,json,os,re,signal,struct,subprocess,sys,time
from pathlib import Path
import numpy as np
from pydicom.filereader import read_dataset
from . import research_import as ri,ri_hu_v5_precision as v5,ri_hu_v5_leased as lease
old=ri.old
COST_KEYS=('compressed_input_bytes','inflated_member_bytes_total','output_bytes_total')


def safe_error(exc,stage):
    record=v5.v4.exception_record(exc,stage)
    allowed={n.args[0].value for n in ast.walk(ast.parse(Path(__file__).read_text())) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='Reject' and n.args and isinstance(n.args[0],ast.Constant) and isinstance(n.args[0].value,str)}
    if isinstance(exc,ri.Reject) and len(exc.args)==1 and exc.args[0] in allowed:record['reason_code']=exc.args[0]
    elif ri.safe_reason(exc)!='GROUP_REJECTED_STOP_NO_RETRY':record['reason_code']=ri.safe_reason(exc)
    return record


class BufferedMember(io.BytesIO):
    """Only already CRC-verified bytes from RI's bounded reader."""
    def __init__(self,raw):super().__init__(raw);self.row={'uncompressed_bytes':len(raw)};self.emitted=0;self.hash=hashlib.sha256()
    def read(self,n):
        raw=super().read(n);self.emitted+=len(raw);self.hash.update(raw);return raw


class FrameOutput(v5.Output):
    def __init__(self,root,budget,used=0):super().__init__(root,used);self.budget=budget
    def write(self,name,content,final=False):
        # 1MiB cumulative/frame plus group retained/temp checks. Existing V5
        # owns the same atomic write. Group budget also counts replacements.
        if self.used+len(content)>2*1024**2:raise ri.Reject('FRAME_CUMULATIVE_OUTPUT_LIMIT')
        self.budget.count('output',len(content))
        return super().write(name,content,final)


class FrameTrace(v5.Trace):
    def __init__(self,out,source_status):super().__init__(out);self.source_status=source_status
    def record(self):return dict(super().record(),source_identity_status=self.source_status)


def parse_frame(raw,directory,budget,permit_opaque,source_status):
    directory.mkdir(mode=0o700,exist_ok=False);out=FrameOutput(directory,budget);t=FrameTrace(out,source_status)
    native=None;row={}
    try:
        scan=t.call('HEADER_CONDITIONS',lambda:v5.v4.TechnicalWalker(v5.v3.Capture(BufferedMember(raw)),t).scan());values=scan['values']
        t.precision['dicom']=v5.safe_dicom(values,scan['states']);t.snapshot()
        branch=t.call('UNIT_INTERPRETATION',lambda:v5.v3.interpret(values,scan['states'],True,False));t.unit_interpretation=branch
        if not scan['complete'] or t.field_errors or branch['unit_branch'] not in ('EXPLICIT_HU','DICOM_CONDITIONAL_HU'):raise ri.Reject('INSTANCE_UNIT_OR_HEADER_ISOLATED')
        geom=t.call('OBJECT_GEOMETRY',lambda:v5.v4.object_geometry(values))
        t.integrity.update(bytes_read=len(raw),declared_length_consumed=True,EOF_verified=True,CRC_verified=True,sha_computed=True,member_sha256=ri.digest(raw))
        end=144+struct.unpack_from('<I',raw,140)[0]
        ds=t.call('PIXELDATA_PROJECTION',lambda:read_dataset(io.BytesIO(raw[end:]),False,True,bytelength=len(raw)-end,specific_tags=[0x7fe00010]))
        payload=t.call('PIXELDATA_LAZY_VALUE',lambda:ds.PixelData)
        fingerprints={}
        if permit_opaque:
            def fingerprint():
                meta=read_dataset(io.BytesIO(raw[132:end]),False,True,bytelength=end-132,specific_tags=[ri.OPAQUE['MediaStorageSOPInstanceUID']])
                ds=read_dataset(io.BytesIO(raw[end:]),False,True,bytelength=len(raw)-end,specific_tags=[v for k,v in ri.OPAQUE.items() if k!='MediaStorageSOPInstanceUID'])
                return dict(ri.opaque(meta,{'MediaStorageSOPInstanceUID':ri.OPAQUE['MediaStorageSOPInstanceUID']}),**ri.opaque(ds,{k:v for k,v in ri.OPAQUE.items() if k!='MediaStorageSOPInstanceUID'}))
            fingerprints=t.call('OPAQUE_FINGERPRINTS',fingerprint)
        native,qa=v5.process(values,payload,t)
        if native is None:raise ri.Reject('DECODED_VALUE_SEMANTICS_UNRESOLVED')
        # Legacy wire enum maintained for exact60 v4 consumer. Actual unit
        # evidence always accompanies it; does NOT assert RescaleType present.
        row=dict(geom,source_dicom_identity_status=source_status,PIXEL_QA='PASS',RESCALE_QA='PASS_DECLARED_HU',
                 rescale_policy='V5_VERIFIED_EXPLICIT_OR_DICOM_CONDITIONAL_HU_NO_SOURCE_FALLBACK',unit_interpretation=branch,
                 full_member_sha256=ri.digest(raw),HU_array_sha256=ri.digest(native.tobytes()),opaque_fingerprints=fingerprints,
                 qa=qa,RescaleSlope=values['RescaleSlope'],RescaleIntercept=values['RescaleIntercept'],shape=list(native.shape),
                 states=scan['states'],precision=t.precision,value_semantics=t.value_semantics)
    except Exception as exc:
        if t.primary_error is None:t.primary_error=v5.v4.exception_record(exc,t.stage or 'FRAME')
        if isinstance(exc,ri.Reject):t.primary_error['reason_code']=exc.args[0]
    finally:
        try:t.snapshot()
        except Exception as exc:t.reporting_error=v5.v4.exception_record(exc,'FINAL_FRAME_CHECKPOINT')
    row['diagnostic']=t.record();row['diagnostic']['source_identity_status']=source_status
    return native,row


def group_worker(request,group,out,caps,permit_opaque,single):
    budget=ri.diag.v1.Budget(caps);directory=Path(out)/group['record_id'];directory.mkdir(mode=0o700)
    old.json_output(directory/'group-identity.json',lease.process_identity(os.getpid()),budget)
    records=[];frames=[];failed=None
    for i,member in enumerate(group['members']):
        status='SOURCE_DICOM_ID_NONCONFORMANT' if member['name'] in request['A3_known_nonconformant_members'] else 'NOT_EVALUATED'
        try:
            raw=ri.load_member(request,member,budget)
            native,row=parse_frame(raw,directory/f'frame-{i:04d}',budget,permit_opaque,status)
            row['member_index']=i;row['research_sample_key']=ri.sample_key(request,member,ri.digest(raw));records.append(row)
            if native is None or row['diagnostic']['primary_error'] or row['diagnostic']['reporting_error']:
                failed=row['diagnostic']['primary_error'] or row['diagnostic']['reporting_error'];break
            frames.append(native);budget.check()
        except Exception as exc:failed=safe_error(exc,'MEMBER_READ_OR_GROUP_RESOURCE');break
    result=dict(group);result.pop('members');result.update(frame_ledgers=records,training_eligible=False,source_group_status='UNKNOWN',clinical_patient_independence_status='UNKNOWN',PROVENANCE_BOUND=True,publisher_group_evidence_bound=True,
                  source_dicom_identity_status='SOURCE_DICOM_ID_NONCONFORMANT' if group['A3_seed_identity_nonconformant'] else 'NOT_EVALUATED',rescale_policy='V5_VERIFIED_EXPLICIT_OR_DICOM_CONDITIONAL_HU_NO_SOURCE_FALLBACK')
    if failed:result.update(research_status='QUARANTINED',reason_code=failed['reason_code'],primary_error=failed)
    else:
        try:
            array,geometry=(frames[0],{'GEOMETRY_QA':'PASS_NATIVE_SINGLE_FRAME'}) if single else ri.volume(frames,records)
            if not single:validate_series_identity(records)
            if not single and min(array.shape)<64:raise ri.Reject('EXACT60_MODEL_MINIMUM_STACK_SHAPE')
            # Intra-group duplicates, including identical decoded slices, are
            # quarantined; affine/IOP/SOP conflicts are never repaired.
            for key in ('full_member_sha256','HU_array_sha256'):
                if len({r[key] for r in records})!=len(records):raise ri.Reject('INTRA_GROUP_EXACT_DUPLICATE')
            sop=[r['opaque_fingerprints'].get('SOPInstanceUID',{}).get('raw_value_sha256') for r in records];sop=[x for x in sop if x]
            if len(set(sop))!=len(sop):raise ri.Reject('DUPLICATE_OPAQUE_SOP')
            buf=io.BytesIO();np.save(buf,array,allow_pickle=False);content=buf.getvalue();budget.count('output',len(content));p=directory/'native-HU.npy'
            with os.fdopen(ri.exclusive(p),'wb') as f:f.write(content)
            result.update(geometry,PIXEL_QA='PASS',RESCALE_QA='PASS_DECLARED_HU',research_status='LIMITED_SINGLE_FRAME' if single else 'LIMITED_PENDING_COHORT_GROUP_AUDIT',
                         tensor_artifact={'path':str(p),'sha256':old.sha(p),'shape':list(array.shape),'axis_order':'Y,X' if single else 'Z,Y,X'},
                         source_group_fingerprints={k:records[0]['opaque_fingerprints'].get(k,{}).get('raw_value_sha256') for k in ('StudyInstanceUID','SeriesInstanceUID','FrameOfReferenceUID')})
        except Exception as exc:
            result.update(research_status='QUARANTINED',reason_code=safe_error(exc,'COMPLETE_STACK')['reason_code'],primary_error=safe_error(exc,'COMPLETE_STACK'))
    result['budget']=budget.report();old.json_output(directory/'research-ledger.json',result,budget)
    result['geometry_ledger']={'path':str(directory/'research-ledger.json'),'sha256':old.sha(directory/'research-ledger.json')};result['budget']=budget.report();return result


def validate_series_identity(records):
    for key in ('StudyInstanceUID','SeriesInstanceUID','FrameOfReferenceUID'):
        identities={(rec['opaque_fingerprints'].get(key,{}).get('status'),rec['opaque_fingerprints'].get(key,{}).get('raw_value_sha256')) for rec in records}
        if len(identities)>1:raise ri.Reject('INCONSISTENT_OPAQUE_SERIES_IDENTITY_STATUS')


def bind_groups(cases):
    ri.bind_groups(cases);owners={};bad=set()
    for i,case in enumerate(cases):
        for row in case.get('frame_ledgers',[]):
            keys=[('decoded_frame',row['HU_array_sha256'])]
            sop=row['opaque_fingerprints'].get('SOPInstanceUID',{}).get('raw_value_sha256')
            if sop:keys.append(('opaque_sop',sop))
            for key in keys:
                if key in owners and owners[key]!=i:bad.update((i,owners[key]))
                owners[key]=i
    for i in bad:cases[i].update(research_status='QUARANTINED',training_eligible=False,source_group_status='CONFLICT',cross_group_duplicate_audit='CONFLICT',reason_code='CROSS_GROUP_DECODED_FRAME_OR_SOP_DUPLICATE')
    return cases


def pipeline(request):
    start=time.monotonic();out=Path(request['output_root']);ri.secure_parent(out);out.mkdir(mode=0o700,exist_ok=False)
    result={'schema':'R76_RI_BATCH_RESULT_V5','attempts':1,'model_calls':0,'training_calls':0,'stages':{'RI-a':{'status':'HISTORICAL_CONSUMED_NO_NEW_DISPATCH'}},'source_fallback':False};prior={};stopped=False
    for stage in request['active_stages']:
        spec=request['stages'][stage];stage_start=time.monotonic();rows=[];used={k:0 for k in COST_KEYS};all_ok=True
        for group in spec['groups']:
            if stopped:rows.append({'record_id':group['record_id'],'research_status':'NOT_RUN','reason_code':'PRIOR_STOP_NO_RETRY'});continue
            if stage=='RI-c' and group['source_group_id'] in prior:
                rows.append(dict(prior[group['source_group_id']],record_id=group['record_id'],split=group['split'],reuse_lineage='SAME_R76_RUN_COMPLETE_PILOT_NO_NEW_READ'));continue
            caps=group['caps'];seconds=min(spec['per_group_wall_seconds'],spec['stage_wall_seconds']-(time.monotonic()-stage_start))
            if seconds<=0 or any(used[k]+caps[k]>spec['caps'][k] for k in COST_KEYS):stopped=True;all_ok=False;rows.append({'record_id':group['record_id'],'research_status':'NOT_RUN','reason_code':'CUMULATIVE_STAGE_RESERVATION_OR_TIME_LIMIT'});continue
            for k in COST_KEYS:used[k]+=caps[k]
            try:
                directory=out/group['record_id']
                def monitor(path):
                    identity_path=directory/'group-identity.json'
                    if identity_path.exists():
                        identity=ri.bound_json(identity_path,old.sha(identity_path))
                        if identity['ppid']!=os.getpid() or identity['pgid']!=identity['pid']:raise ri.Reject('GROUP_WORKER_IDENTITY_CONFLICT')
                        current=lease.process_identity(identity['pid'])
                        if current is not None:
                            if current!=identity:raise ri.Reject('GROUP_WORKER_IDENTITY_CONFLICT')
                            rss=int(subprocess.check_output(['ps','-p',str(identity['pid']),'-o','rss='],text=True,timeout=2).strip())*1024
                            if rss>caps['RSS_stop_bytes']:raise ri.Reject('GROUP_WORKER_RSS_LIMIT')
                    stat=os.statvfs(path);return stat.f_bavail*stat.f_frsize
                row=ri.phase(group_worker,(request,group,str(out),caps,True,stage=='RI-a'),seconds,start+request['overall_wall_seconds'],out,request['disk_free_floor_bytes'],free_fn=monitor)
                row['phase_exit_and_reap_verified_by_shared_supervisor']=True;rows.append(row)
                # Stop even if a returned group was isolated: conservative
                # explicit rule, no substitute/no uncosted failure continuation.
                if row.get('PIXEL_QA')!='PASS':all_ok=False;stopped=True
            except Exception as exc:
                all_ok=False;stopped=True
                checkpoints=sorted((out/group['record_id']).glob('frame-*/stage-checkpoint-v5.json'))
                recovered=ri.bound_json(checkpoints[-1],old.sha(checkpoints[-1])) if checkpoints else None
                rows.append({'record_id':group['record_id'],'research_status':'QUARANTINED','reason_code':safe_error(exc,'GROUP_PHASE')['reason_code'],'primary_error':safe_error(exc,'GROUP_PHASE'),'failed_actual_costs':'UNKNOWN_RESERVED_CAP_RETAINED','last_durable_frame':recovered,'phase_reaped_by_existing_supervisor':True})
        if stage!='RI-a':bind_groups([r for r in rows if 'native_volume_sha256' in r])
        if any(r.get('research_status')=='QUARANTINED' for r in rows):stopped=True;all_ok=False
        if stage=='RI-b' and all_ok and not stopped:prior={r['source_group_id']:r for r in rows if r.get('training_eligible')}
        result['stages'][stage]={'rows':rows,'reserved_attempt_upper_bounds':used,'all_selected_groups_passed':all_ok and not stopped,'status':'STOPPED_NO_RETRY' if stopped else 'PASS'}
        if stage=='RI-c' and not stopped and len(rows)==60 and all(r.get('training_eligible') for r in rows):
            consumer=ri.consumer_records(rows)
            for row in consumer:row['rescale_policy']='V5_VERIFIED_EXPLICIT_OR_DICOM_CONDITIONAL_HU_NO_SOURCE_FALLBACK'
            budget=ri.diag.v1.Budget(dict(spec['caps'],output_bytes_total=request['consumer_bytes_max']))
            old.json_output(out/'ENC_RESEARCH_SOURCE_CASES_V2.json',consumer,budget)
            result['consumer_binding']={'path':str(out/'ENC_RESEARCH_SOURCE_CASES_V2.json'),'sha256':old.sha(out/'ENC_RESEARCH_SOURCE_CASES_V2.json')}
    result.update(status='PARTIAL_STOPPED_NO_RETRY' if stopped else 'FIXED60_COMPLETE_RESEARCH_ONLY',elapsed_seconds=time.monotonic()-start)
    old.json_output(out/'receipt.json',result,ri.diag.v1.Budget(dict(ri.codec.B,output_bytes_total=request['receipt_bytes_max'])))
    return result


def validate_request(r):
    if r['schema']!='R76_RI_HU_V5_BATCH_REQUEST' or r['max_attempts']!=1 or r['failure_policy']!='STOP_ALL_ON_FIRST_FAILURE_NO_RETRY_NO_REPLACEMENT' or r['active_stages']!=['RI-a','RI-b','RI-c']:raise ri.Reject('EXACT_R76_REQUEST_REQUIRED')
    parent=ri.bound_json(r['parent_request']['path'],r['parent_request']['sha256']);ri.validate_request(parent)
    for key in ('source_archive','inventory_binding','A3_known_nonconformant_members','publisher_evidence','split_counts','full_member_bytes_max'):
        if r[key]!=parent[key]:raise ri.Reject('R76_FIXED_PARENT_DRIFT')
    archive=Path(r['source_archive']['path']);st=archive.lstat();binding=r['source_archive']['stat_binding']
    if (st.st_dev,st.st_ino,st.st_mtime_ns,st.st_size)!=(binding['device'],binding['inode'],binding['mtime_ns'],r['source_archive']['bytes']):raise ri.Reject('ARCHIVE_STAT_DRIFT_NO_RESCAN')
    for stage in ('RI-a','RI-b','RI-c'):
        if [{k:v for k,v in g.items() if k!='caps'} for g in r['stages'][stage]['groups']]!=[{k:v for k,v in g.items() if k!='caps'} for g in parent['stages'][stage]['groups']]:raise ri.Reject('R76_EXACT_GROUP_MEMBER_SPLIT_DRIFT')
        for g in r['stages'][stage]['groups']:
            parent_group=next(p for p in parent['stages'][stage]['groups'] if p['record_id']==g['record_id'])
            if g['caps']['compressed_input_bytes']!=parent_group['caps']['compressed_input_bytes']:raise ri.Reject('R76_READ_BUDGET_DRIFT')
            if g['caps']['output_bytes_total']!=parent_group['caps']['output_bytes_total']+len(g['members'])*2*1024**2:raise ri.Reject('R76_OUTPUT_BUDGET_DRIFT')
        if r['stages'][stage]['caps']['output_bytes_total']!=sum(g['caps']['output_bytes_total'] for g in r['stages'][stage]['groups']):raise ri.Reject('R76_STAGE_OUTPUT_BUDGET_DRIFT')
    old.verify_readiness(r['bindings'])
    import importlib.metadata
    for package,version in r['bindings']['decoder_distributions'].items():
        if importlib.metadata.version(package)!=version:raise ri.Reject('DECODER_VERSION_DRIFT')
    from pydicom.pixels.decoders.pylibjpeg import _DECODERS
    if [(name,fn.__module__,fn.__name__) for name,fn in _DECODERS[ri.codec.JPEG].items()]!=[('libjpeg','libjpeg.utils','decode_pixel_data')]:raise ri.Reject('FIXED_DECODER_ENTRYPOINT_DRIFT')
    if r['output_budget_changes']['total_hard_reserved_bytes']!=sum(x['caps']['output_bytes_total'] for x in r['stages'].values())+r['control_output_reserve_bytes']:raise ri.Reject('R76_TOTAL_OUTPUT_BUDGET_DRIFT')
    for ref in r['bindings']['source_bindings']+r['bindings']['runtime_bindings']+r['bindings'].get('closure_file_bindings',[])+r['bindings']['decoder_module_bindings']+r['bindings']['decoder_binary_bindings']+r['evidence_bindings']:ri.assert_file(ref)
    if r['source_fallback'] is not False or r['models_permitted'] is not False or r['training_permitted'] is not False:raise ri.Reject('R76_DATA_ONLY')


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--request-sha256',required=True);p.add_argument('--execute',action='store_true');p.add_argument('--approval');p.add_argument('--approval-sha256');a=p.parse_args();r=ri.bound_json(a.request,a.request_sha256);validate_request(r)
    if not a.execute:print(json.dumps({'status':'CHECK_ONLY_NO_NEW_BODY_READ'}));return
    if not a.approval or not a.approval_sha256:raise ri.Reject('NEW_BATCH_APPROVAL_REQUIRED')
    grant=ri.bound_json(a.approval,a.approval_sha256)
    expected={'schema':'R76_RI_HU_V5_BATCH_APPROVAL','request_sha256':a.request_sha256,'permit_RI-a':True,'permit_RI-b':True,'permit_RI-c':True,'permit_full_member_reads':True,'permit_opaque_uid_fingerprints':True,'permit_precision_discrepancy_decode':True,'permit_raw_diagnostic_save':True,'permit_conditional_HU':True,'permit_stop_all_on_first_failure':True,'permit_model':False,'permit_training':False,'permit_retry':False,'permit_source_fallback':False}
    if any(type(grant.get(k)) is not type(v) or grant.get(k)!=v for k,v in expected.items()):raise ri.Reject('EXACT_NEW_BATCH_APPROVAL_REQUIRED')
    if any(os.environ.get(k)!='1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')):raise ri.Reject('CPU1_REQUIRED')
    claim=Path(r['output_root']+'-claim');claim.mkdir(mode=0o700,exist_ok=False);locks=[]
    control_budget=ri.diag.v1.Budget(dict(ri.codec.B,output_bytes_total=1024**2,wall_seconds=r['overall_wall_seconds']))
    lease_record={'schema':'R76_BATCH_LEASE','status':'CLAIMED_NOT_RUN','request_sha256':a.request_sha256,'approval_sha256':a.approval_sha256,'identity':lease.process_identity(os.getpid()),'attempts':0}
    old.json_output(claim/'claimed.json',lease_record,control_budget)
    try:
        for name in ('wave1.serial.lock','cpu.lock'):
            fd=os.open(Path(str(_PUBLIC_ROOT / '.local/private-bindings/epi-next-device-queue'))/name,os.O_RDWR|os.O_NOFOLLOW)
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BaseException:os.close(fd);raise
            locks.append(fd)
        queue=Path(str(_PUBLIC_ROOT / '.local/private-bindings/epi-next-device-queue'))
        unfinished={x.name for x in (queue/'slots').iterdir() if x.is_dir() and (x/'started.json').exists() and not (x/'finished.json').exists()}
        if unfinished!={'ctfm-fov128-wave1-20261009-01','ctfm-v3-fullseries64-pair-01'}:raise ri.Reject('NEW_UNRECOVERED_SLOT')
        for ref in r['administrative_recovery_bindings']:
            if ri.bound_json(ref['path'],ref['sha256'])['status']!='APPROVED_ADMINISTRATIVE_RECOVERY':raise ri.Reject('RECOVERY_DECISION_REQUIRED')
        procs=subprocess.check_output(['ps','-Ao','pid=,command='],text=True)
        if any(int(line.strip().split()[0])!=os.getpid() and re.match(r'^\s*\d+\s+\S*python\S*\s+-m\s+epi_next\.(research_import(?:_v5)?|ri_hu_v5_(?:precision|leased))(?:\s|$)',line) for line in procs.splitlines()):raise ri.Reject('DUPLICATE_IMPORT_TASK')
        previous=signal.getsignal(signal.SIGTERM)
        def interrupt(*_):raise InterruptedError('OWN_BATCH_CLI_TERM')
        signal.signal(signal.SIGTERM,interrupt)
        lease_record.update(status='DISPATCHED',attempts=1);old.json_output(claim/'dispatch.json',lease_record,control_budget)
        try:result=pipeline(r)
        finally:signal.signal(signal.SIGTERM,previous)
        lease_record.update(status=result['status'],finished_elapsed_seconds=result['elapsed_seconds'],attempted_group_stages={k:v['status'] for k,v in result['stages'].items()},scientific_forward_calls=result['model_calls'],training_calls=result['training_calls'],phase_reap_verified_by_shared_supervisor=all(row.get('phase_exit_and_reap_verified_by_shared_supervisor') for st in result['stages'].values() for row in st.get('rows',[]) if 'phase_exit_and_reap_verified_by_shared_supervisor' in row))
        print(json.dumps({'status':result['status']}))
        if result['status']!='FIXED60_COMPLETE_RESEARCH_ONLY':raise SystemExit(1)
    finally:
        released=len(locks)
        for fd in reversed(locks):fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
        lease_record.update(released_lock_count=released,no_followup_dispatch=True,lock_release_is_not_phase_exit_proof=True)
        old.json_output(claim/'release.json',lease_record,control_budget)

if __name__=='__main__':
    try:main()
    except Exception as exc:print(json.dumps({'status':'REJECTED_NO_RETRY','primary_error':safe_error(exc,'BATCH_CONTROL')}));raise SystemExit(1) from None
