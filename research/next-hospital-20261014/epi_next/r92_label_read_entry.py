"""One bounded A/B/C reader. Default check-only; no pixel or model interface."""
import argparse
import csv
import hashlib
import io
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import resource
import signal
import sys
import time
import urllib.request

import numpy as np
from . import a1_prepare as old
from . import a3_structure_audit as structural
from .slice_evaluation_registry import build_registry, MappingRejected, bound

DISCOVERY_URLS = (
    'https://api.figshare.com/v2/articles/12991592',
    'https://api.github.com/repos/ShahinSHH/COVID-CT-MD/contents')
CAPS = {'wall_seconds':1140, 'RSS_stop_bytes':512*1024**2,
        'compressed_input_bytes':1215037440 + 2097152,
        'inflated_header_prefix_bytes_total':607518720 + 2105344,
        'output_bytes_total':20*1024**2}
AB_CAPS = dict(CAPS,wall_seconds=240,compressed_input_bytes=2097152,
               inflated_header_prefix_bytes_total=2105344,output_bytes_total=1048576)


def read_bound(ref, limit=16*1024**2):
    if not bound(ref): raise ValueError('REFERENCE_REQUIRED')
    p=Path(ref['path'])
    if p.is_symlink() or p.stat().st_size > limit: raise ValueError('REFERENCE_LIMIT')
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ref['sha256']: raise ValueError('REFERENCE_DRIFT')
    return json.loads(raw)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): raise ValueError('REDIRECT_DENIED')


def discover():
    """Fixed official metadata endpoints only, never follow a payload URL."""
    opener=urllib.request.build_opener(NoRedirect)
    result=[]; remaining=2*1024**2; start=time.monotonic()
    for url in DISCOVERY_URLS:
        if time.monotonic()-start>120: raise ValueError('DISCOVERY_TIME_LIMIT')
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'EpiLocate-R92-metadata'})
            with opener.open(req,timeout=25) as f:
                raw=f.read(remaining+1)
            if len(raw)>remaining: raise old.GuardError('DISCOVERY_BYTE_LIMIT')
            remaining-=len(raw); d=json.loads(raw)
            files=d.get('files',[]) if isinstance(d,dict) else d
            # Metadata filenames/IDs only; no payload follow-up/download.
            candidates=[{k:r.get(k) for k in ('name','id','size','computed_md5','sha')}
                        for r in files if isinstance(r,dict) and r.get('name') in
                        ('Index.csv','Slice-level-labels.npy','Slice-level-labels-updated-1.npy')]
            result.append({'url':url,'status':'METADATA_ONLY','bytes':len(raw),
                           'sha256':hashlib.sha256(raw).hexdigest(),'candidates':candidates})
        except old.GuardError:raise
        except (OSError, ValueError):
            result.append({'url':url,'status':'DISCOVERY_UNKNOWN_NO_RETRY'})
    return result


class LimitedMember(old.Member):
    def __init__(self, *args, compressed_cap, **kwargs):
        self.local_compressed=0; self.local_cap=compressed_cap
        super().__init__(*args,**kwargs)
    def _compressed(self,n):
        if self.local_compressed+n>self.local_cap: raise old.GuardError('PER_MEMBER_COMPRESSED_LIMIT')
        self.local_compressed+=n
        return super()._compressed(n)


def payload(archive, member, budget, source):
    if member['name'] not in ('Index.csv','Slice-level-labels.npy'):
        raise ValueError('UNLOCKED_LABEL_MEMBER')
    limit=8192 if member['name']=='Index.csv' else 1024**2
    if member['uncompressed_bytes']>limit: raise ValueError('PAYLOAD_SIZE_LIMIT')
    s=LimitedMember(archive,member,budget,limit,source,compressed_cap=2*1024**2)
    try:
        raw=s.read(member['uncompressed_bytes']); sha=s.finish()
        return raw,sha
    finally:s.close()


def parse_labels(raw):
    """Validate NPY header before allocation; pickle/object/trailing data rejected."""
    f=io.BytesIO(raw);version=np.lib.format.read_magic(f)
    if version==(1,0): shape,fortran,dtype=np.lib.format.read_array_header_1_0(f)
    elif version==(2,0): shape,fortran,dtype=np.lib.format.read_array_header_2_0(f)
    else: raise ValueError('NPY_VERSION_UNSUPPORTED')
    if (len(shape)!=2 or not 0<shape[0]<=512 or not 0<shape[1]<=2048
            or dtype.hasobject or dtype.kind not in 'biu' or fortran
            or math.prod(shape)*dtype.itemsize>1024**2):
        raise ValueError('NPY_HEADER_REJECTED')
    if f.tell()+math.prod(shape)*dtype.itemsize!=len(raw): raise ValueError('NPY_LENGTH_REJECTED')
    arr=np.load(io.BytesIO(raw),allow_pickle=False)
    if not np.isin(arr,[0,1]).all(): raise ValueError('NONBINARY_LABELS')
    return arr


class LocationWalker(structural.Walker):
    """Reuse existing nested-container/pixel-boundary walker; retain one new DS."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.location=None;self.seen_location=False
    def selected(self,key,vr,n,end):
        if key=='TransferSyntaxUID': return super().selected(key,vr,n,end)
        self.skip(n,end)  # no new UID/clinical values parsed or retained
    def skip(self,n,end):
        if self.ctx['domain']=='dataset' and self.ctx['tag']=='0020,1041':
            if self.seen_location or self.ctx['VR']!='DS' or not 0<n<=16:
                self.fail('SLICE_LOCATION_INVALID')
            self.seen_location=True
            try:value=float(self.read(n,end).decode('ascii').strip())
            except (ValueError,UnicodeError):self.fail('SLICE_LOCATION_INVALID')
            if not math.isfinite(value):self.fail('SLICE_LOCATION_INVALID')
            self.location=value
        else:super().skip(n,end)


def location(archive, member, budget, source):
    caps=dict(structural.CAPS);caps.update(inflated_header_prefix_bytes_per_member=131072)
    s=LimitedMember(archive,member,budget,131072,source,compressed_cap=262144)
    try:
        w=LocationWalker(s,member,caps);report=w.run()
        # The structural report may say selected identity fields NOT_REACHED;
        # do not publish or reinterpret it as an identity/geometry QA result.
        if report['stop_code']!='ROOT_PIXEL_VALUE_BOUNDARY' or not w.root_completed or w.location is None: raise ValueError('LOCATION_OR_ROOT_BOUNDARY_UNPROVEN')
        return {'slice_location':w.location,'header_prefix_sha256':s.hash.hexdigest(),
                'inflated_prefix_bytes':s.emitted,'full_member_CRC_verified':False,
                'pixel_value_read':False}
    finally:s.close()


def parse_index(raw,semantics,groups):
    """Exact declared CSV schema, no guesses about columns or case-number base."""
    rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    columns=semantics['index_columns']
    required={'subject','diagnosis','annotation_index'}
    if set(columns)!=required or type(semantics['index_base']) is not int or semantics['index_base'] not in (0,1): raise ValueError('INDEX_SCHEMA_UNPROVEN')
    owners={};result=[]
    for row in rows:
        if set(columns.values())-row.keys(): raise ValueError('INDEX_COLUMN_MISSING')
        key=(row[columns['diagnosis']],row[columns['subject']])
        if key in owners:raise ValueError('DUPLICATE_INDEX_SUBJECT')
        v=int(row[columns['annotation_index']])-semantics['index_base']
        if v<0 or v in owners.values(): raise ValueError('DUPLICATE_OR_INVALID_INDEX')
        owners[key]=v
    for g in groups:
        # Both exact class directory and subject are already provenance-bound.
        diagnosis,subject=g['source_subject_directory'].split('/')
        if (diagnosis,subject) in owners:
            result.append({'source_group_id':g['source_group_id'],
                           'annotation_case_index':owners[(diagnosis,subject)]})
    return result


def run(request, request_sha, approval=None, guard=None):
    if (request['schema']!='R92_DATA_LABEL_READER_EXECUTABLE_V1'
            or request['caps']!=(AB_CAPS if request['semantics'] is None else CAPS)):
        raise ValueError('EXACT_REQUEST_REQUIRED')
    for ref in request['source_bindings']:
        if old.sha(ref['path'])!=ref['sha256']:raise ValueError('SOURCE_DRIFT')
    if old.sha(sys.executable)!=request['runtime_sha256']:raise ValueError('RUNTIME_DRIFT')
    if approval is None:return {'status':'CHECK_ONLY_NO_ZIP_LABEL_HEADER_NETWORK_ACCESS'}
    validate_approval(request,request_sha,approval)
    out=Path(request['output_root']);out.mkdir(mode=0o700,exist_ok=False)  # single claim, no overwrite/retry
    budget=old.Budget(request['caps']);overall_wall=request['caps']['wall_seconds']
    if guard is not None:
        local_check=budget.check
        def checked():local_check();guard.check()
        budget.check=checked
    previous=signal.getsignal(signal.SIGALRM)
    def deadline(*_):raise ValueError('OVERALL_WALL_LIMIT')
    signal.signal(signal.SIGALRM,deadline);signal.setitimer(signal.ITIMER_REAL,overall_wall)
    result={'schema':'R92_LABEL_READ_RECEIPT_V1','status':'IN_PROGRESS','request_sha256':request_sha,
            'model_calls':0,'pixel_decodes':0,'pixel_value_reads':0,'registry':'NOT_RUN'}
    try:
        # A can end UNKNOWN without granting payload-discovery expansion.
        result['A']=discover();budget.check()
        old.json_output(out/'official-discovery-lock.json',{'sources':result['A'],'payload_followed':False},budget)
        if request.get('run_discovery') is not True:raise ValueError('DISCOVERY_SCOPE_REQUIRED')
        audit=read_bound(request['audit']);base=read_bound(request['original_batch_request'])
        archive=old.open_bound_archive(base)
        members=request['label_members'];raw_index=raw_labels=None
        inventory=Path(base['inventory_binding']['path'])
        saved={r['name']:r for r in (json.loads(line) for line in inventory.read_text().splitlines())}
        if len(members)!=2 or {m['name'] for m in members}!={'Index.csv','Slice-level-labels.npy'}:
            raise ValueError('EXACT_LABEL_MEMBERS_REQUIRED')
        if any(saved.get(m['name'])!=m for m in members):raise ValueError('LABEL_INVENTORY_DRIFT')
        before=time.monotonic();signal.setitimer(signal.ITIMER_REAL,min(120,overall_wall-(before-budget.start)))
        for m in members:
            if time.monotonic()-before>120:raise ValueError('LABEL_PHASE_WALL_LIMIT')
            raw,sha=payload(archive,m,budget,base['source_archive'])
            cache_path=out/m['name'];budget.count('output',len(raw))
            part=cache_path.with_name(cache_path.name+'.part')
            with os.fdopen(old.exclusive(part),'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
            old.publish(part,cache_path)
            result.setdefault('B',[]).append({'name':m['name'],'sha256':sha,'bytes':len(raw),
                                             'CRC_EOF_verified':True,'private_cache_path':str(cache_path)})
            if m['name']=='Index.csv':raw_index=raw
            else:raw_labels=raw
        result['index_columns_observed']=next(csv.reader(io.StringIO(raw_index.decode('utf-8-sig'))),[])
        result['index_rows_observed']=sum(1 for _ in csv.DictReader(io.StringIO(raw_index.decode('utf-8-sig'))))
        labels=parse_labels(raw_labels)
        signal.setitimer(signal.ITIMER_REAL,max(.001,overall_wall-(time.monotonic()-budget.start)))
        result['label_shape']=list(labels.shape)
        if request['semantics'] is None:
            result.update(status='UNKNOWN_SEMANTICS_NO_PAIRING',missing=['index_columns/base','version/corrected_subjects','row_extent','publisher_direction'])
        else:
            semantics=read_bound(request['semantics']);evidence=semantics['evidence']
            for name in ('publisher_order','index_base','version','row_extent','source_subject_binding'):
                proof=evidence[name]
                if not bound(proof) or old.sha(proof['path'])!=proof['sha256']:raise ValueError('SEMANTICS_EVIDENCE_DRIFT')
            # No row-tail truncation without separately bound extent evidence.
            index=parse_index(raw_index,semantics,audit['rows'])
            brefs={x['name']:x['sha256'] for x in result['B']}
            if evidence['index']['sha256']!=brefs['Index.csv'] or evidence['labels']['sha256']!=brefs['Slice-level-labels.npy']:
                raise ValueError('SEMANTICS_PAYLOAD_DRIFT')
            if not evidence.get('label_version_resolved'):raise ValueError('VERSION_UNRESOLVED')
            accepted=[];rejected=[];start=time.monotonic();members_read=0
            signal.setitimer(signal.ITIMER_REAL,min(900,max(.001,overall_wall-(start-budget.start))))
            byid={g['source_group_id']:g for g in base['stages']['RI-c']['groups']}
            lookup={x['source_group_id']:x['annotation_case_index'] for x in index}
            for original in audit['rows']:
                group=dict(original);gid=group['source_group_id']
                if (gid not in lookup or group['task_label']!=1
                        or group['source_subject_directory'].rsplit('/',1)[-1] in ('P001','P006')):
                    accepted.append(build_registry([group],[],[],evidence));continue
                try:
                    if time.monotonic()-start>900:raise old.GuardError('HEADER_PHASE_WALL_LIMIT')
                    l=read_bound(group['geometry_binding']);frames=l['frame_ledgers'];native=[]
                    for k,ordinal in enumerate(group['native_order_to_frame_ordinal']):
                        members_read+=1
                        if members_read>4635:raise old.GuardError('HEADER_MEMBER_CAP')
                        frame=frames[ordinal];m=byid[gid]['members'][frame['member_index']]
                        if m['header_offset'] is None:raise ValueError('MEMBER_BINDING_MISSING')
                        loc=location(archive,m,budget,base['source_archive'])
                        normal=group_normal(l['affine_LPS'])
                        native.append({'native_index':k,'member_key':frame['full_member_sha256'],
                                       'ipp_normal_position':sum(a*b for a,b in zip(frame['IPP'],normal)),**loc})
                    group['native_slices']=native
                    row=lookup[gid];extent=semantics['row_extents'].get(str(row))
                    if extent!=group['depth'] or row>=labels.shape[0]:raise ValueError('ROW_EXTENT_UNPROVEN')
                    if labels.shape[1]<extent:raise ValueError('ROW_SHORTER_THAN_EXTENT')
                    if labels.shape[1]!=extent:
                        if semantics.get('padded_tail')!='IGNORE_BEYOND_EXPLICIT_EXTENT':raise ValueError('PADDED_TAIL_UNPROVEN')
                    ann={'annotation_case_index':row,'coverage':'FULL_SELECTED_STACK_EXPLICIT',
                         'labels':[int(x) for x in labels[row,:extent]]}
                    accepted.append(build_registry([group],[{'source_group_id':gid,'annotation_case_index':row}],[ann],evidence))
                except old.GuardError:raise
                except (ValueError,KeyError,IndexError):
                    rejected.append({'source_group_id':gid,'reason':'MAPPING_UNRESOLVED_NO_PAIR'})
            result.update(status='EVALUATION_REGISTRY_COMPLETE_WITH_UNKNOWN',registry=accepted,
                          rejected_groups=rejected,original_group_denominator=len(audit['rows']),header_members_read=members_read)
        result['budget']=budget.report();result['RSS_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)
        result['elapsed_seconds']=time.monotonic()-budget.start
    except Exception:
        result.update(status='FAILED_STOP_NO_RETRY',error='BOUNDED_READER_FAILURE',budget=budget.report())
        raise
    finally:
        try:old.json_output(out/'receipt.json',result,budget)
        finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
    return {'status':result['status'],'receipt_path':str(out/'receipt.json'),'receipt_sha256':old.sha(out/'receipt.json')}


def group_normal(affine):
    v=[row[0] for row in affine[:3]];norm=math.sqrt(sum(x*x for x in v))
    if not math.isfinite(norm) or norm<=0:raise ValueError('SAVED_AFFINE_INVALID')
    return [x/norm for x in v]  # saved orientation for order matching, no geometry repair




def validate_approval(request,request_sha,approval):
    expected={'schema':'R92_DATA_LABEL_READ_APPROVAL_V1','request_sha256':request_sha,
              'permit_A':True,'permit_B':True,'permit_C':request['semantics'] is not None,'permit_pixels':False,
              'permit_models':False,'retry':False}
    if any(type(approval.get(k)) is not type(v) or approval.get(k)!=v for k,v in expected.items()):
        raise ValueError('EXACT_NEW_APPROVAL_REQUIRED')


def validate_dispatch(request,sha,approval_sha,dispatch):
    if (dispatch.get('status')!='EXCLUSIVE_SLOT_ASSIGNED'
            or dispatch.get('launch_release')!='RELEASED_BY_CHIEF'
            or dispatch.get('request_sha256')!=sha or dispatch.get('approval_sha256')!=approval_sha
            or dispatch.get('task_key')!=request['spec']['task_key']
            or dispatch.get('owner')!='DATA' or dispatch.get('retry') is not False):
        raise ValueError('EXACT_CHIEF_SERIAL_DISPATCH_REQUIRED')


def load_shared(config):
    # Import the original pinned package; no copied queue or writer implementation.
    for r in config['modules'].values():
        if old.sha(r['path'])!=r['sha256']:raise ValueError('SHARED_SOURCE_DRIFT')
    package=Path(config['package_path'])
    if old.sha(package/'__init__.py')!=config['initializer_sha256']:raise ValueError('SHARED_INIT_DRIFT')
    name='_r92_original_shared'
    spec=importlib.util.spec_from_file_location(name,package/'__init__.py',submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return importlib.import_module(name+'.wave1_supervisor')


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--sha256',required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--approval');p.add_argument('--approval-sha256')
    p.add_argument('--dispatch');p.add_argument('--dispatch-sha256');p.add_argument('--child',action='store_true');a=p.parse_args()
    req=read_bound({'path':a.request,'sha256':a.sha256})
    if a.execute and not (a.approval and a.approval_sha256):raise ValueError('NEW_APPROVAL_REQUIRED')
    app=read_bound({'path':a.approval,'sha256':a.approval_sha256}) if a.execute else None
    if not a.execute:
        print(json.dumps(run(req,a.sha256)));return
    if not a.dispatch or not a.dispatch_sha256:raise ValueError('EXISTING_QUEUE_DISPATCH_REQUIRED')
    dispatch=read_bound({'path':a.dispatch,'sha256':a.dispatch_sha256})
    run(req,a.sha256)  # verify exact code/runtime before entering the original queue
    validate_approval(req,a.sha256,app)
    validate_dispatch(req,a.sha256,a.approval_sha256,dispatch)
    shared=load_shared(req['supervisor'])
    if not a.child:
        command=[sys.executable,'-m','epi_next.r92_label_read_entry','--request',a.request,'--sha256',a.sha256,
                 '--approval',a.approval,'--approval-sha256',a.approval_sha256,
                 '--dispatch',a.dispatch,'--dispatch-sha256',a.dispatch_sha256,'--execute','--child']
        recovery=dispatch.get('administrative_recovery') or {}
        receipt=shared.run_supervised(shared.SupervisionSpec(**req['spec']),command,req['supervisor_output'],
            req['supervisor']['dependency_root'],req['supervisor']['dependency_sha256'],
            recovery_decision_path=recovery.get('path'),recovery_decision_sha=recovery.get('sha256'))
        if receipt['status']!='SUCCESS' or not receipt['slot_completed']:raise ValueError('SUPERVISOR_NOT_SUCCESS')
        print(json.dumps({'status':'SUPERVISED_READER_FINISHED','receipt':receipt}));return
    guard=shared.ChildGuard.from_environment()
    try:
        if vars(guard.spec)!=req['spec']:raise ValueError('CHILD_SPEC_DRIFT')
        result=run(req,a.sha256,app,guard)
        guard.complete('SUCCESS',device_recovered=True,actual_forward=0,actual_backward=0)
        print(json.dumps(result))
    except Exception:
        guard.complete('FAILED',reason='DATA_READER_FAILURE',device_recovered=False,actual_forward=0,actual_backward=0)
        raise


if __name__=='__main__':main()
