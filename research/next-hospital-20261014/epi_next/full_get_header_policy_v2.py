"""Independent, explicit response adapter; frozen R111 code is not patched.

Only security/framing/redirect headers enter the existing R111 semantic parser.
Repeated informational headers are counted but their values are never retained.
Full GET, TLS, source, length, MD5/SHA, disk, ZIP and publish rules stay in R111.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
from . import r111_full_acquire as frozen

SCHEMA = 'FULL_GET_HEADER_POLICY_V2_REQUEST_V1'
APPROVAL = 'FULL_GET_HEADER_POLICY_V2_APPROVAL_V1'
CRITICAL = frozenset(('content-length', 'content-encoding', 'transfer-encoding',
    'content-range', 'location', 'connection', 'trailer', 'upgrade', 'te', 'host',
    'etag', 'last-modified', 'content-md5', 'digest', 'content-digest', 'repr-digest',
    'www-authenticate', 'proxy-authenticate', 'authorization', 'proxy-authorization'))
MAX_FIELDS = 100
MAX_NAMES = 64
AUDIT_BYTES = 32768


class HeaderItems:
    def __init__(self, pairs):
        self.pairs = pairs
    def items(self):
        return iter(self.pairs)


class Audit:
    def __init__(self):
        self.records = []
        self.owned_root = None

    def observe(self, response, requested_url):
        row = dict(transaction=len(self.records)+1, status_code=response.status,
                   response_URL_matches_requested=response.geturl()==requested_url,
                   field_counts={}, duplicate_names=[], values_saved=False,
                   policy='CRITICAL_SINGLE_VALUE_OTHER_VALUES_OMITTED', decision='REJECTED')
        self.records.append(row)
        frozen.require(len(self.records)<=frozen.CAPS['total_GETs'], 'AUDIT_TRANSACTION_LIMIT')
        counts = row['field_counts']; critical = {}; occurrences = 0
        for key,value in response.headers.items():
            occurrences += 1
            frozen.require(occurrences<=MAX_FIELDS, 'RESPONSE_HEADER_FIELD_LIMIT')
            frozen.require(isinstance(key,str) and len(key)<=64 and
                re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+",key) is not None, 'INVALID_HEADER_NAME')
            name = key.lower()
            frozen.require(name in counts or len(counts)<MAX_NAMES, 'HEADER_NAME_COUNT_LIMIT')
            counts[name] = counts.get(name,0)+1
            if name in CRITICAL:
                if name in critical:
                    row['duplicate_names'] = sorted(n for n,c in counts.items() if c>1)
                    row['critical_duplicate'] = name
                    raise ValueError('DUPLICATE_CRITICAL_HEADER')
                critical[name] = value
        row['field_occurrences'] = occurrences
        row['duplicate_names'] = sorted(n for n,c in counts.items() if c>1)
        frozen.require(row['response_URL_matches_requested'], 'RESPONSE_URL_DRIFT')
        frozen.require(len(json.dumps(self.records,ensure_ascii=True).encode())<=AUDIT_BYTES-1024, 'HEADER_AUDIT_BYTES')
        row['decision'] = 'PASS_TO_UNCHANGED_R111_FRAMING_STATUS_AND_DIGEST_CHECKS'
        # Noncritical values (including Set-Cookie) never reach the scientific
        # parser, log or persisted audit; no joining or last-value-wins policy.
        return HeaderItems(list(critical.items()))


class ResponseAdapter:
    def __init__(self, response, projected_headers):
        self.response = response; self.headers = projected_headers
        self.status = response.status
    def geturl(self):return self.response.geturl()
    @property
    def length(self):return self.response.length
    def read(self,n):return self.response.read(n)
    def __enter__(self):return self
    def __exit__(self,*_):self.response.close()


def acquire(q, raw_transport, guard=None, free_fn=None, request_sha=None):
    root=Path(q['output_root']);audit=Audit()
    frozen.require(not root.exists() and not root.is_symlink(), 'OUTPUT_ALREADY_EXISTS')
    def transport(url,headers,timeout):
        # R111 has exclusively created CLAIM before its first transport call.
        s=root.lstat();audit.owned_root=(s.st_dev,s.st_ino)
        response=raw_transport(url,headers,timeout)
        try:return ResponseAdapter(response,audit.observe(response,url))
        except BaseException:
            response.close();raise
    try:
        frozen.acquire(q,transport,guard,free_fn,request_sha)
    finally:
        # Never append diagnostics to a pre-existing/foreign acquisition root.
        if audit.owned_root is not None:
            s=root.lstat();frozen.require((s.st_dev,s.st_ino)==audit.owned_root,'AUDIT_ROOT_DRIFT')
            result=dict(schema='FULL_GET_RESPONSE_HEADER_AUDIT_V2',request_sha256=request_sha,
                transactions=audit.records,header_values_saved=False,body_saved_here=False)
            raw=(json.dumps(result,ensure_ascii=True,indent=2)+'\n').encode()
            frozen.require(len(raw)<=AUDIT_BYTES,'AUDIT_OUTPUT_LIMIT')
            names=['CLAIM.json','RECEIPT.json']+[k+'.directory.json' for k,*_ in frozen.FILES]
            used=sum((root/name).stat().st_size for name in names if (root/name).exists())
            frozen.require(used+len(raw)<=frozen.CAPS['output_metadata_bytes'],'COMBINED_METADATA_LIMIT')
            with os.fdopen(frozen.a0.exclusive(root/'HTTP_HEADER_AUDIT.json'),'wb') as f:
                f.write(raw);f.flush();os.fsync(f.fileno())


def validate(q):
    frozen.require(q['schema']==SCHEMA,'NEW_HEADER_POLICY_REQUEST_REQUIRED')
    # Deliberate schema projection only; original globals/functions are unchanged.
    projected=dict(q,schema=frozen.SCHEMA)
    frozen.validate(projected)
    frozen.require(q['header_policy']==dict(version='V2',critical_names=sorted(CRITICAL),
        max_fields=MAX_FIELDS,max_names=MAX_NAMES,audit_bytes=AUDIT_BYTES,
        noncritical_values='OMITTED',critical_duplicates='REJECT'), 'EXACT_HEADER_POLICY')


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--sha256',required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--approval');p.add_argument('--approval-sha256')
    p.add_argument('--dispatch');p.add_argument('--dispatch-sha256');p.add_argument('--child',action='store_true');a=p.parse_args()
    q=frozen.a0.bound_json(a.request,a.sha256);validate(q)
    if not a.execute:print(json.dumps(dict(status='CHECK_ONLY_NO_HTTP_NO_FILES')));return
    frozen.require(all((a.approval,a.approval_sha256,a.dispatch,a.dispatch_sha256)),'NEW_APPROVAL_DISPATCH_REQUIRED')
    owner=frozen.a0.bound_json(a.approval,a.approval_sha256)
    expected=dict(schema=APPROVAL,status='APPROVED_NEW_SCOPE',request_sha256=a.sha256,
        permit_opaque_full_GET=True,permit_local_directory=True,permit_member_decode=False,permit_models=False,retry=False,resume=False)
    frozen.require(all(type(owner.get(k)) is type(v) and owner.get(k)==v for k,v in expected.items()),'NEW_EXACT_APPROVAL_REQUIRED')
    from . import r92_label_read_entry as original
    dispatch=frozen.a0.bound_json(a.dispatch,a.dispatch_sha256);original.validate_dispatch(q,a.sha256,a.approval_sha256,dispatch)
    shared=original.load_shared(q['supervisor'])
    if not a.child:
        command=[sys.executable,'-m','epi_next.full_get_header_policy_v2','--request',a.request,'--sha256',a.sha256,'--execute','--child',
            '--approval',a.approval,'--approval-sha256',a.approval_sha256,'--dispatch',a.dispatch,'--dispatch-sha256',a.dispatch_sha256]
        recovery=dispatch.get('administrative_recovery') or {}
        r=shared.run_supervised(shared.SupervisionSpec(**q['spec']),command,q['supervisor_output'],q['supervisor']['dependency_root'],q['supervisor']['dependency_sha256'],
            recovery_decision_path=recovery.get('path'),recovery_decision_sha=recovery.get('sha256'))
        frozen.require(r['status']=='SUCCESS' and r['slot_completed'],'SUPERVISOR_FAILED_STOP');return
    guard=shared.ChildGuard.from_environment()
    try:
        frozen.require(vars(guard.spec)==q['spec'],'CHILD_SPEC_DRIFT')
        acquire(q,frozen.http_open,guard,request_sha=a.sha256)
        guard.complete('SUCCESS',device_recovered=True,actual_forward=0,actual_backward=0)
    except BaseException:guard.complete('FAILED',device_recovered=True,actual_forward=0,actual_backward=0);raise


if __name__=='__main__':main()
