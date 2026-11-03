"""Independent retry preparation: verified identity/stat before cached metadata/payload.
Old A1/R92/shared modules are imported unchanged. No HTTP or header branch.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import sys
import time
import zlib

from . import r92_label_read_entry as prior
from . import archive_identity_v2 as identity

CAPS = prior.AB_CAPS
SCHEMA = 'ARCHIVE_BOUND_AB_RETRY_REQUEST_V2'


class SecureMember(prior.old.Member):
    """Reuse mature raw inflater/CRC/EOF and ZIP64 header semantics on dup FD."""
    def __init__(self,lease,row,budget,receipt):
        if identity.state(os.fstat(lease))!=receipt['after']:raise identity.IdentityError('LEASE_STAT_DRIFT')
        fd=os.dup(lease)
        self.f=os.fdopen(fd,'rb');self.row=row;self.budget=budget
        self.lease=lease;self.receipt=receipt
        self.limit=8192 if row['name']=='Index.csv' else 1048576
        self.emitted=0;self.crc=0;self.hash=hashlib.sha256();self.pending=b''
        self.remaining=row['compressed_bytes'];self.decoder=None
        try:
            if row['name'] not in ('Index.csv','Slice-level-labels.npy') or row['uncompressed_bytes']>self.limit:
                raise ValueError('EXACT_SMALL_LABEL_MEMBERS_ONLY')
            self.f.seek(row['header_offset']);header=self._compressed(30)
            sig,ver,flags,method,tm,dt,crc,cs,us,nl,el=struct.unpack('<4s5H3I2H',header)
            if sig!=b'PK\x03\x04' or flags&1 or method not in (0,8) or nl>4096 or el>65535:
                raise ValueError('LOCAL_ZIP_HEADER')
            name=self._compressed(nl).decode('utf-8' if flags&0x800 else 'cp437');extra=self._compressed(el)
            if name!=row['name'] or method!=row['compression_method']:raise ValueError('LOCAL_CENTRAL_MISMATCH')
            if not flags&8:
                if cs==0xffffffff or us==0xffffffff:
                    pos=0;data=None
                    while pos+4<=len(extra):
                        tag,n=struct.unpack_from('<HH',extra,pos);pos+=4
                        if pos+n>len(extra):raise ValueError('ZIP64_EXTRA_BOUNDS')
                        if tag==1:data=extra[pos:pos+n]
                        pos+=n
                    if data is None:raise ValueError('ZIP64_EXTRA_MISSING')
                    pos=0
                    if us==0xffffffff:
                        if len(data)<pos+8:raise ValueError('ZIP64_EXTRA_SHORT')
                        us=struct.unpack_from('<Q',data,pos)[0];pos+=8
                    if cs==0xffffffff:
                        if len(data)<pos+8:raise ValueError('ZIP64_EXTRA_SHORT')
                        cs=struct.unpack_from('<Q',data,pos)[0]
                if (crc,cs,us)!=(row['crc32'],row['compressed_bytes'],row['uncompressed_bytes']):
                    raise ValueError('LOCAL_CENTRAL_SIZE_CRC')
            if self.f.tell()+self.remaining>receipt['after']['size']:raise ValueError('ZIP_MEMBER_BOUNDS')
            if method==8:self.decoder=zlib.decompressobj(-15)
        except BaseException:self.f.close();raise

    def verify(self):
        expected=self.receipt['after']
        if identity.state(os.fstat(self.lease))!=expected or identity.state(os.fstat(self.f.fileno()))!=expected:
            raise identity.IdentityError('MEMBER_OR_LEASE_STAT_DRIFT')
        identity.namespace(self.receipt['path'],expected,self.receipt['path_chain'])

    def _compressed(self,n):
        self.verify();raw=super()._compressed(n);self.verify();return raw

    def close(self):
        try:self.verify()
        finally:self.f.close()


def validate(request,sha,approval=None):
    if request['schema']!=SCHEMA or request['caps']!=CAPS:raise ValueError('EXACT_RETRY_REQUEST_REQUIRED')
    for ref in request['source_bindings']:
        if prior.old.sha(ref['path'])!=ref['sha256']:raise ValueError('SOURCE_DRIFT')
    if prior.old.sha(sys.executable)!=request['runtime_sha256']:raise ValueError('RUNTIME_DRIFT')
    if approval is not None:
        expected={'schema':'ARCHIVE_BOUND_AB_RETRY_APPROVAL_V2','request_sha256':sha,
                  'permit_cached_official_metadata':True,'permit_original_Index':True,
                  'permit_original_slice_labels':True,'permit_new_HTTP':False,
                  'permit_full_archive_rescan':False,'permit_C':False,'permit_pixels':False,
                  'permit_models':False,'retry':False}
        if any(type(approval.get(k)) is not type(v) or approval.get(k)!=v for k,v in expected.items()):
            raise ValueError('NEW_EXACT_OWNER_APPROVAL_REQUIRED')


def bound_identity(request):
    receipt=prior.read_bound(request['identity_receipt'])
    source=request['original_source']
    original=prior.read_bound(request['original_anchor_request'])['source_archive']
    if (any(source[k]!=original[k] for k in ('path','sha256','bytes'))
            or request['original_A0_receipt']['path']!=original['receipt_path']
            or request['original_A0_receipt']['sha256']!=original['receipt_sha256']):
        raise ValueError('ORIGINAL_ANCHOR_BINDING_MISMATCH')
    historical=prior.read_bound(request['original_A0_receipt'])
    integrity=historical['phases']['integrity']
    if (receipt['expected_sha256']!=original['sha256'] or receipt['sha256']!=original['sha256']
            or receipt['expected_bytes']!=original['bytes'] or receipt['bytes_read']!=original['bytes']
            or integrity['sha256']!=original['sha256'] or integrity['bytes']!=original['bytes']):
        raise ValueError('HISTORICAL_CONTENT_BINDING_MISMATCH')
    fd,chain=identity.reuse(source['path'],receipt)
    return receipt,fd,chain


def run(request,sha,approval=None,guard=None):
    validate(request,sha,approval)
    if approval is None:return {'status':'CHECK_ONLY_NO_ARCHIVE_BODY_HTTP_OR_LABEL_ACCESS'}
    # Open and verify before cached metadata or new payload access. Failure here
    # does not consume a new output claim and can never trigger an auto rehash.
    receipt,lease,chain=bound_identity(request)
    out=Path(request['output_root']);budget=prior.old.Budget(CAPS)
    original_check=budget.check
    def check():
        original_check()
        if guard is not None:guard.check()
        if identity.state(os.fstat(lease))!=receipt['after']:raise identity.IdentityError('LEASE_STAT_DRIFT')
        identity.namespace(request['original_source']['path'],receipt['after'],chain)
    budget.check=check
    previous=signal.getsignal(signal.SIGALRM)
    def alarm(*_):raise ValueError('AB_WALL_LIMIT')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,240)
    result={'schema':'ARCHIVE_BOUND_AB_RESULT_V2','status':'FAILED_STOP_NO_RETRY',
            'request_sha256':sha,'identity_receipt':request['identity_receipt'],
            'identity_preflight':'VERIFIED_BEFORE_CACHED_METADATA_OR_PAYLOAD',
            'full_archive_scan_bytes_in_this_execution':0,'new_HTTP_calls':0,
            'model_calls':0,'pixel_decodes':0,'new_headers_read':0,'registry':'NOT_RUN'}
    claimed=False
    try:
        out.mkdir(mode=0o700,exist_ok=False);claimed=True;budget.check()
        cached=prior.read_bound(request['cached_discovery'])
        result['official_metadata']={'binding':request['cached_discovery'],
            'observation_date':'2026-10-15','semantics':'HISTORICAL_METADATA_ONLY_NOT_REFRESHED',
            'sources':cached['sources']}
        inventory=Path(request['inventory']['path'])
        if prior.old.sha(inventory)!=request['inventory']['sha256']:raise ValueError('INVENTORY_DRIFT')
        rows={r['name']:r for r in (json.loads(line) for line in inventory.read_text().splitlines())}
        members=request['label_members']
        if len(members)!=2 or {m['name'] for m in members}!={'Index.csv','Slice-level-labels.npy'}:
            raise ValueError('EXACT_MEMBERS_REQUIRED')
        for m in members:
            if rows.get(m['name'])!=m:raise ValueError('MEMBER_INVENTORY_DRIFT')
            budget.check();stream=SecureMember(lease,m,budget,receipt)
            try:raw=stream.read(m['uncompressed_bytes']);digest=stream.finish()
            finally:stream.close()
            budget.check()
            # Validate NPY/CSV before publishing a private cached payload.
            if m['name'].endswith('.npy'):
                array=prior.parse_labels(raw);result['label_shape']=list(array.shape)
            else:
                import csv,io
                csvrows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
                result['index_columns_observed']=list(csvrows[0]) if csvrows else []
                result['index_rows_observed']=len(csvrows)
            budget.count('output',len(raw));target=out/m['name'];part=target.with_name(target.name+'.part')
            with os.fdopen(prior.old.exclusive(part),'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
            budget.check();prior.old.publish(part,target)
            result.setdefault('payloads',[]).append({'path':str(target),'sha256':digest,
                'bytes':len(raw),'CRC_EOF_verified':True})
        budget.check();result['status']='AB_EVIDENCE_SAVED_MAPPING_UNKNOWN'
        result['missing_semantics']=['Index columns/base binding','version/corrected subjects',
                                     'valid row extents/padding','publisher order direction']
    except Exception as exc:
        result['error']=str(exc) if isinstance(exc,identity.IdentityError) else type(exc).__name__
        raise
    finally:
        try:
            if claimed:
                result['budget_before_final_receipt']=budget.report()
                result['elapsed_seconds']=time.monotonic()-budget.start
                result['peak_RSS_bytes']=identity.peak_rss()
                # Bounded final control receipt must survive a source-stat failure;
                # output/RSS/wall caps remain enforced by the original budget.
                budget.check=original_check
                prior.old.json_output(out/'receipt.json',result,budget)
        finally:
            os.close(lease);signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
    return {'status':result['status'],'receipt_path':str(out/'receipt.json'),
            'receipt_sha256':prior.old.sha(out/'receipt.json')}


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--sha256',required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--approval');p.add_argument('--approval-sha256')
    p.add_argument('--dispatch');p.add_argument('--dispatch-sha256');p.add_argument('--child',action='store_true');a=p.parse_args()
    req=prior.read_bound({'path':a.request,'sha256':a.sha256})
    if not a.execute:print(json.dumps(run(req,a.sha256)));return
    if not all((a.approval,a.approval_sha256,a.dispatch,a.dispatch_sha256)):raise ValueError('NEW_OWNER_AND_CHIEF_DISPATCH_REQUIRED')
    app=prior.read_bound({'path':a.approval,'sha256':a.approval_sha256})
    dispatch=prior.read_bound({'path':a.dispatch,'sha256':a.dispatch_sha256})
    validate(req,a.sha256,app);prior.validate_dispatch(req,a.sha256,a.approval_sha256,dispatch)
    shared=prior.load_shared(req['supervisor'])
    if not a.child:
        cmd=[sys.executable,'-m','epi_next.archive_bound_ab_v2','--request',a.request,'--sha256',a.sha256,
             '--approval',a.approval,'--approval-sha256',a.approval_sha256,
             '--dispatch',a.dispatch,'--dispatch-sha256',a.dispatch_sha256,'--execute','--child']
        recovery=dispatch.get('administrative_recovery') or {}
        result=shared.run_supervised(shared.SupervisionSpec(**req['spec']),cmd,req['supervisor_output'],
            req['supervisor']['dependency_root'],req['supervisor']['dependency_sha256'],
            recovery_decision_path=recovery.get('path'),recovery_decision_sha=recovery.get('sha256'))
        if result['status']!='SUCCESS' or not result['slot_completed']:raise ValueError('SUPERVISOR_NOT_SUCCESS')
        print(json.dumps(result));return
    guard=shared.ChildGuard.from_environment()
    try:
        if vars(guard.spec)!=req['spec']:raise ValueError('CHILD_SPEC_DRIFT')
        result=run(req,a.sha256,app,guard)
        guard.complete('SUCCESS',device_recovered=True,actual_forward=0,actual_backward=0)
        print(json.dumps(result))
    except Exception:
        guard.complete('FAILED',reason='ARCHIVE_BOUND_AB_FAILURE',device_recovered=False,actual_forward=0,actual_backward=0)
        raise


if __name__=='__main__':main()
