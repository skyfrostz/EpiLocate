"""Independent bounded cache diagnostics; NOT a complete true-pairing runner.
No DICOM/header/pixel/HTTP/model API. No old A authorization accepted.
Execute, if ever approved, must enter the pinned original supervisor.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import sys
from . import archive_bound_ab_v2 as provenance
from . import label_pairing_diagnostics_v3 as diagnostic

SCHEMA = 'BOUNDED_LABEL_CACHE_DIAGNOSTIC_REQUEST_V4'
CAPS = dict(wall_seconds=60, RSS_stop_bytes=536870912, compressed_input_bytes=0,
            inflated_header_prefix_bytes_total=0, output_bytes_total=1048576)
LIMITS = {'Index': 8192, 'original': 126528, 'updated': 63328}


def cached_bytes(binding, cap, budget):
    """One secure FD, exact saved SHA/bytes, all parents no-follow, no reread."""
    fd, chain = provenance.identity.secure_open(binding['path'])
    try:
        before = provenance.identity.state(os.fstat(fd))
        if before['size'] != binding['bytes'] or not 0 < before['size'] <= cap:
            raise ValueError('EXACT_CACHE_SIZE_CAP')
        provenance.identity.namespace(binding['path'], before, chain)
        raw = bytearray()
        while len(raw) < before['size']:
            budget.check()
            part = os.read(fd, min(65536, before['size'] - len(raw)))
            if not part: raise ValueError('CACHE_TRUNCATED')
            raw.extend(part)
        # No extra payload byte beyond the declared cap: the exact regular-file
        # size and before/after namespace/FD states establish the bounded extent.
        if os.lseek(fd, 0, os.SEEK_CUR) != before['size']:
            raise ValueError('CACHE_READ_EXTENT_DRIFT')
        if provenance.identity.state(os.fstat(fd)) != before:
            raise ValueError('CACHE_STAT_DRIFT')
        provenance.identity.namespace(binding['path'], before, chain)
        if hashlib.sha256(raw).hexdigest() != binding['sha256']:
            raise ValueError('CACHE_SHA_DRIFT')
        return bytes(raw)
    finally:
        os.close(fd)


def extent_gate(proof, group, label_sha):
    """Technical schema only; exact evidence must be independently owner-reviewed.
    Missing evidence returns a blocker, never invents valid columns/padding.
    """
    if proof is None: return 'AUTHOR_EXTENT_AND_MEMBER_DOMAIN_MISSING'
    if (proof.get('schema') != 'OWNER_REVIEWED_AUTHOR_COLUMN_DOMAIN_V1'
            or proof.get('source_group_id') != group['source_group_id']
            or proof.get('label_sha256') != label_sha
            or proof.get('effective_native_count') != group['depth']
            or proof.get('valid_label_columns') != list(range(group['depth']))
            or proof.get('owner_reviewed_under_this_new_request') is not True
            or not proof.get('author_statement_reference')
            or proof.get('padding_semantics') != 'EXPLICIT_OUTSIDE_VALID_DOMAIN'
            or proof.get('member_domain_complete') is not True):
        raise ValueError('AUTHOR_EXTENT_PROOF_NOT_QUALIFIED')
    return 'SCHEMA_ONLY_REQUIRES_BOUND_EVIDENCE_AND_FULL_HEADER_STAGE'


def validate(request, sha, owner=None):
    if request['schema'] != SCHEMA or request['caps'] != CAPS:
        raise ValueError('NEW_DIAGNOSTIC_ONLY_EXACT_SCOPE')
    if request['spec']['max_forward'] != 0 or request['spec']['max_backward'] != 0:
        raise ValueError('ZERO_MODEL_SCOPE')
    if request['spec']['task_key'] == 'DATA-R103-VERSION-INDEX-AUDIT-01':
        raise ValueError('OLD_A_TASK_FORBIDDEN')
    for item in request['source_bindings']:
        if provenance.prior.old.sha(item['path']) != item['sha256']:
            raise ValueError('SOURCE_DRIFT')
    if provenance.prior.old.sha(sys.executable) != request['runtime_sha256']:
        raise ValueError('RUNTIME_DRIFT')
    for package, version in request['package_versions'].items():
        if importlib.metadata.version(package) != version: raise ValueError('PACKAGE_DRIFT')
    if owner is not None:
        expected = dict(schema='BOUNDED_LABEL_CACHE_DIAGNOSTIC_APPROVAL_V4',
                        status='APPROVED_NEW_SCOPE', request_sha256=sha,
                        permit_exact_cache_read=True, permit_HTTP=False,
                        permit_headers=False, permit_pixels=False, permit_models=False,
                        permit_archive_body=False, retry=False)
        if any(type(owner.get(k)) is not type(v) or owner.get(k) != v for k,v in expected.items()):
            raise ValueError('NEW_EXACT_OWNER_REQUIRED_NOT_OLD_A')


def run(request, sha, owner=None, guard=None):
    validate(request, sha, owner)
    if owner is None: return dict(status='CHECK_ONLY_NO_PAYLOAD_ACCESS')
    out = Path(request['output_root']); out.mkdir(mode=0o700,exist_ok=False)
    budget = provenance.prior.old.Budget(CAPS); check = budget.check
    def guarded_check():
        check()
        if guard is not None: guard.check()
    budget.check = guarded_check
    receipt = dict(schema='BOUNDED_LABEL_CACHE_DIAGNOSTIC_RECEIPT_V4',
                   request_sha256=sha, status='FAILED_STOP_NO_RETRY',
                   reads={}, HTTP=0, archive_body=0, headers=0, pixels=0,
                   forward=0, backward=0, medical_denominator=None, pairing_execution='NOT_RUN')
    prior_alarm = signal.getsignal(signal.SIGALRM)
    def stop(*_): raise ValueError('DIAGNOSTIC_WALL_LIMIT')
    signal.signal(signal.SIGALRM,stop);signal.setitimer(signal.ITIMER_REAL,60)
    try:
        meta = json.loads(cached_bytes(request['metadata'],32*1024**2,budget))
        index = cached_bytes(request['cache']['Index'],LIMITS['Index'],budget)
        receipt['reads']['Index'] = len(index)
        matrices = {}; versions = {}
        for key in ('original','updated'):
            item = request['cache'].get(key)
            if item is None: continue
            raw = cached_bytes(item,LIMITS[key],budget); receipt['reads'][key]=len(raw)
            array = provenance.prior.parse_labels(raw)
            matrices[key] = array
            versions[key] = dict(rows=int(array.shape[0]),columns=int(array.shape[1]),
                                 dtype=str(array.dtype),sha256=item['sha256'],
                                 binary_values_validated=True,allow_pickle=False)
        if 'original' not in matrices: raise ValueError('EXACT_ORIGINAL_REQUIRED')
        result = diagnostic.diagnose_index(index,matrices['original'].shape[0],meta['groups'])
        result['matrix_versions'] = diagnostic.matrix_pairing(versions['original'],versions.get('updated'))
        result['scope_status'] = 'DIAGNOSTICS_ONLY_FULL_PAIRING_STAGE_NOT_IMPLEMENTED'
        p = out/'INDEX_DIAGNOSTICS_V4.json'
        digest = provenance.prior.old.json_output(p,result,budget)
        receipt.update(status='DIAGNOSTICS_COMPLETE_PAIRING_BLOCKED',output={'path':str(p),'sha256':digest})
    except BaseException as exc:
        receipt['error_type']=type(exc).__name__;receipt['error']=str(exc)[:200];raise
    finally:
        try: provenance.prior.old.json_output(out/'RECEIPT_V4.json',receipt,budget)
        finally: signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,prior_alarm)
    return receipt


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--sha256',required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--owner');p.add_argument('--owner-sha256')
    p.add_argument('--dispatch');p.add_argument('--dispatch-sha256');p.add_argument('--child',action='store_true');a=p.parse_args()
    q=provenance.prior.read_bound({'path':a.request,'sha256':a.sha256})
    if not a.execute: print(json.dumps(run(q,a.sha256)));return
    if not all((a.owner,a.owner_sha256,a.dispatch,a.dispatch_sha256)): raise ValueError('NEW_OWNER_DISPATCH_REQUIRED')
    o=provenance.prior.read_bound({'path':a.owner,'sha256':a.owner_sha256})
    d=provenance.prior.read_bound({'path':a.dispatch,'sha256':a.dispatch_sha256})
    validate(q,a.sha256,o);provenance.prior.validate_dispatch(q,a.sha256,a.owner_sha256,d)
    shared=provenance.prior.load_shared(q['supervisor'])
    if not a.child:
        command=[sys.executable,'-m','epi_next.bounded_label_diagnostic_v4',
                 '--request',a.request,'--sha256',a.sha256,'--owner',a.owner,
                 '--owner-sha256',a.owner_sha256,'--dispatch',a.dispatch,
                 '--dispatch-sha256',a.dispatch_sha256,'--execute','--child']
        recovery=d.get('administrative_recovery') or {}
        result=shared.run_supervised(shared.SupervisionSpec(**q['spec']),command,q['supervisor_output'],
                    q['supervisor']['dependency_root'],q['supervisor']['dependency_sha256'],
                    recovery_decision_path=recovery.get('path'),recovery_decision_sha=recovery.get('sha256'))
        if result['status']!='SUCCESS' or not result['slot_completed']:raise ValueError('SUPERVISOR_STOP_NO_RETRY')
        print(json.dumps(result));return
    guard=shared.ChildGuard.from_environment()
    try:
        if vars(guard.spec)!=q['spec']:raise ValueError('EXACT_CHILD_SPEC')
        result=run(q,a.sha256,o,guard);guard.complete('SUCCESS',device_recovered=True,actual_forward=0,actual_backward=0)
        print(json.dumps(result))
    except BaseException:
        guard.complete('FAILED',device_recovered=True,actual_forward=0,actual_backward=0);raise


if __name__=='__main__':main()
