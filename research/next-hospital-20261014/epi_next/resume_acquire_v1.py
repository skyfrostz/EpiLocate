"""One explicit prefix-copy + exact CT range, then original full Mask GET.

Frozen full-GET code, shared queue, ChildGuard and .25s stale rule are unchanged.
No real prefix is read by validate/check-only. No member is opened or decoded.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import sys
import time
from urllib.parse import urljoin
from . import r111_full_acquire as frozen
from . import full_get_header_policy_v2 as policy

SCHEMA = 'R112_RESUME_REQUEST_V1'
APPROVAL = 'R112_RESUME_APPROVAL_V1'
PREFIX_BYTES = 839909376
NETWORK_BYTES = 268057940
require = frozen.require


def identity(s):
    return dict(bytes=s.st_size, device=s.st_dev, inode=s.st_ino, mtime_ns=s.st_mtime_ns)


def check_prefix(p, snapshot, fd=None):
    s = p.lstat() if fd is None else os.fstat(fd)
    require(stat.S_ISREG(s.st_mode) and identity(s) ==
            {k: snapshot[k] for k in ('bytes', 'device', 'inode', 'mtime_ns')}, 'PREFIX_IDENTITY_DRIFT')


def write_all(fd, chunk):
    with memoryview(chunk) as view:
        while view:
            n = os.write(fd, view)
            require(n > 0, 'WRITE_FAILURE')
            view = view[n:]


class Budget(frozen.Budget):
    def __init__(self, root, remaining, network_limit, guard=None, free_fn=None):
        self.network_limit = network_limit
        super().__init__(root, remaining, guard, free_fn)

    def check(self):
        super().check()
        require(self.body <= self.network_limit, 'NETWORK_BODY_LIMIT')


def copy_prefix(snapshot, fd, budget, md5, sha, record):
    p = Path(snapshot['path'])
    check_prefix(p, snapshot)
    source = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        check_prefix(p, snapshot, source)
        while record['prefix_read_bytes'] < snapshot['bytes']:
            budget.check()
            n = min(frozen.CAPS['chunk_bytes'], snapshot['bytes'] - record['prefix_read_bytes'])
            chunk = os.read(source, n)
            require(0 < len(chunk) <= n, 'PREFIX_TRUNCATED')
            write_all(fd, chunk); md5.update(chunk); sha.update(chunk)
            record['prefix_read_bytes'] += len(chunk)
            record['bytes'] += len(chunk); budget.remaining -= len(chunk)
        check_prefix(p, snapshot, source); check_prefix(p, snapshot)
        os.fsync(fd)
        record.update(prefix_md5=md5.hexdigest(), prefix_sha256=sha.hexdigest())
        frozen.write_metadata(budget.root/'PREFIX_COPY_COMPLETE.json',
            dict(prefix=snapshot, prefix_read_bytes=record['prefix_read_bytes'],
                 prefix_md5=record['prefix_md5'], prefix_sha256=record['prefix_sha256'],
                 original_prefix_unchanged=True, member_decoded=False), budget, 8192)
    finally:
        os.close(source)


def finish(fd, part, final, item, budget, md5, sha, record):
    require(record['bytes'] == item['bytes'] and md5.hexdigest() == item['md5'], 'FULL_SIZE_OR_MD5_MISMATCH')
    record.update(md5=md5.hexdigest(), sha256=sha.hexdigest(), exact_size=True)
    os.fsync(fd); budget.check()
    directory = frozen.bounded_directory(fd, item['bytes'], budget)
    frozen.write_metadata(part.parent/(item['key']+'.directory.json'), directory, budget, 983040)
    budget.check()
    require(time.monotonic() < budget.phase_deadline-1, 'FINALIZATION_TIME_RESERVE')
    held = os.fstat(fd); named = part.lstat()
    require(stat.S_ISREG(named.st_mode) and identity(held) == identity(named), 'PART_PATH_IDENTITY_DRIFT')
    frozen.a0.publish(part, final)
    published = final.lstat()
    require(stat.S_ISREG(published.st_mode) and
            (published.st_dev, published.st_ino, published.st_size) ==
            (held.st_dev, held.st_ino, held.st_size), 'PUBLICATION_IDENTITY_UNCERTAIN')
    parent = os.open(part.parent, os.O_RDONLY)
    try: os.fsync(parent)
    finally: os.close(parent)
    record.update(promoted=True, status='VERIFIED_OPAQUE_ARCHIVE_AND_DIRECTORY_ONLY',
                  directory_path=str(part.parent/(item['key']+'.directory.json')))


def resume_CT(item, snapshot, root, budget, transport, record):
    size = item['bytes']; start = snapshot['bytes']; url = item['url']
    require(0 < start < size, 'PREFIX_RANGE')
    part = root/(item['key']+'.part'); final = root/item['key']
    require(not part.exists() and not part.is_symlink() and not final.exists() and not final.is_symlink(), 'NO_OVERWRITE')
    fd = os.open(part, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    md5 = hashlib.md5(); sha = hashlib.sha256()
    record.update(part=str(part), final=str(final), bytes=0, prefix_read_bytes=0, GETs=0,
                  redirects=[], promoted=False, status='FAILED_STOP_NO_RETRY')
    budget.phase_deadline = min(budget.deadline, time.monotonic()+item['seconds'])
    try:
        copy_prefix(snapshot, fd, budget, md5, sha, record)
        for hop in range(frozen.CAPS['redirects_per_file']+1):
            budget.check(); require(budget.GETs < frozen.CAPS['total_GETs'], 'GET_LIMIT')
            budget.GETs += 1; record['GETs'] += 1
            request_headers = {'Accept-Encoding': 'identity', 'Range': f'bytes={start}-{size-1}'}
            with transport(url, request_headers, min(15, budget.phase_deadline-time.monotonic())) as response:
                h = frozen.headers(response, url); code = response.status
                if code in (301, 302, 303, 307, 308):
                    target = urljoin(url, h.get('location', ''))
                    require(hop == 0 and url == frozen.source_url(item['key']) and
                            target == frozen.official_redirect_url(item['key']), 'UNAPPROVED_REDIRECT')
                    record['redirects'].append(dict(status=code, source=url, target=target)); url = target
                    continue
                require(code == 206, 'RANGE_206_REQUIRED_NO_FULL_GET_FALLBACK')
                require(h.get('content-range') == f'bytes {start}-{size-1}/{size}' and
                        h.get('content-length') == str(size-start), 'EXACT_CONTENT_RANGE_AND_LENGTH')
                require(h.get('content-encoding', 'identity').lower() == 'identity' and
                        'transfer-encoding' not in h, 'ENCODING_RESPONSE')
                while record['bytes'] < size:
                    budget.check(); n = min(frozen.CAPS['chunk_bytes'], size-record['bytes'])
                    require(budget.body+n <= budget.network_limit, 'NETWORK_BODY_LIMIT_BEFORE_READ')
                    chunk = response.read(n)
                    require(0 < len(chunk) <= n, 'TRUNCATED_OR_OVERLONG_BODY')
                    budget.body += len(chunk); write_all(fd, chunk)
                    md5.update(chunk); sha.update(chunk)
                    record['bytes'] += len(chunk); budget.remaining -= len(chunk)
                require(response.length == 0, 'HTTP_FRAMED_EOF_UNPROVEN')
                check_prefix(Path(snapshot['path']), snapshot)
                finish(fd, part, final, item, budget, md5, sha, record)
                return
        raise ValueError('REDIRECT_HOP_LIMIT')
    finally:
        record.update(part_exists=part.exists(), final_exists=final.exists(),
                      partial_md5=md5.hexdigest(), partial_sha256=sha.hexdigest())
        os.close(fd)


def acquire(q, raw_transport, guard=None, free_fn=None, request_sha=None):
    root = Path(q['output_root'])
    require(not root.exists() and not root.is_symlink(), 'OUTPUT_ALREADY_EXISTS')
    frozen.a0.secure_parent(root); root.mkdir(mode=0o700, exist_ok=False)
    budget = Budget(root, sum(x['bytes'] for x in q['files']), q['network_body_bytes'], guard, free_fn)
    frozen.write_metadata(root/'CLAIM.json', dict(status='ONCE_ONLY_NO_AUTO_RETRY'), budget, 1024)
    audit = policy.Audit()
    def transport(url, headers, timeout):
        response = raw_transport(url, headers, timeout)
        try:
            try: projected = audit.observe(response, url)
            finally:
                if audit.records:
                    # At most four <=8KiB snapshots; no values or unknown raw URL.
                    frozen.write_metadata(root/f'HTTP_HEADER_AUDIT_{len(audit.records):02d}.json',
                        dict(request_sha256=request_sha, transaction=audit.records[-1],
                             request_was_range='Range' in headers, header_values_saved=False), budget, 8192)
            return policy.ResponseAdapter(response, projected)
        except BaseException:
            response.close(); raise
    result = dict(schema='R112_RESUME_RECEIPT_V1', status='FAILED_STOP_NO_RETRY',
        request_sha256=request_sha, files=[], medical_denominator=None, models=0,
        member_payload_decoded=False, HTTP_HEAD=0)
    previous = signal.getsignal(signal.SIGALRM)
    def alarm(*_): raise ValueError('WALL_LIMIT')
    signal.signal(signal.SIGALRM, alarm)
    try:
        budget.check()
        for i, item in enumerate(q['files']):
            signal.setitimer(signal.ITIMER_REAL, min(item['seconds'], max(.001, budget.deadline-time.monotonic())))
            record = dict(key=item['key'], status='FAILED_STOP_NO_RETRY'); result['files'].append(record)
            if i == 0: resume_CT(item, q['prefix'], root, budget, transport, record)
            else: frozen.transfer_one(item, root, budget, transport, record)
        budget.check(); result['status'] = 'FULL_ARCHIVES_AND_LOCAL_DIRECTORIES_ONLY'
    except BaseException as exc:
        result.update(error_type=type(exc).__name__, error=str(exc)[:300]); raise
    finally:
        result.update(actual_GETs=budget.GETs, network_body_bytes=budget.body,
            prefix_read_bytes=sum(x.get('prefix_read_bytes', 0) for x in result['files']),
            elapsed_seconds=time.monotonic()-budget.start)
        try: frozen.write_metadata(root/'RECEIPT.json', result, budget, 65536)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)


def validate(q):
    require(q['schema'] == SCHEMA, 'NEW_RESUME_SCHEMA_REQUIRED')
    policy.validate(dict(q, schema=policy.SCHEMA))
    require(q['network_body_bytes'] == NETWORK_BYTES and q['prefix']['bytes'] == PREFIX_BYTES, 'EXACT_RESUME_BUDGET')
    original = frozen.a0.bound_json(q['prefix_failure_result']['path'], q['prefix_failure_result']['sha256'])
    require(q['prefix'] == {k: original['CT_part'][k] for k in ('path', 'bytes', 'device', 'inode', 'mtime_ns')}, 'EXACT_FAILED_PREFIX')
    check_prefix(Path(q['prefix']['path']), q['prefix'])
    require(hashlib.sha256(json.dumps(q['source_bindings'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            == q['source_closure_sha256'], 'SOURCE_CLOSURE_DRIFT')


def main():
    p = argparse.ArgumentParser(); p.add_argument('--request', required=True); p.add_argument('--sha256', required=True)
    p.add_argument('--execute', action='store_true'); p.add_argument('--child', action='store_true')
    p.add_argument('--approval'); p.add_argument('--approval-sha256'); p.add_argument('--dispatch'); p.add_argument('--dispatch-sha256')
    a = p.parse_args(); q = frozen.a0.bound_json(a.request, a.sha256); validate(q)
    if not a.execute: print(json.dumps(dict(status='CHECK_ONLY_NO_PREFIX_READ_NO_HTTP'))); return
    require(all((a.approval, a.approval_sha256, a.dispatch, a.dispatch_sha256)), 'NEW_RESUME_APPROVAL_DISPATCH_REQUIRED')
    owner = frozen.a0.bound_json(a.approval, a.approval_sha256)
    expected = dict(schema=APPROVAL, status='APPROVED_NEW_SCOPE', request_sha256=a.sha256,
        permit_prefix_read_copy_hash=True, permit_CT_range_tail=True, permit_Mask_full_GET=True,
        permit_local_directory=True, permit_member_decode=False, permit_models=False, retry=False, resume=True)
    require(all(type(owner.get(k)) is type(v) and owner.get(k) == v for k, v in expected.items()), 'NEW_EXACT_RESUME_APPROVAL_REQUIRED')
    from . import r92_label_read_entry as entry
    dispatch = frozen.a0.bound_json(a.dispatch, a.dispatch_sha256)
    entry.validate_dispatch(q, a.sha256, a.approval_sha256, dispatch); shared = entry.load_shared(q['supervisor'])
    if not a.child:
        command = [sys.executable, '-m', 'epi_next.resume_acquire_v1', '--request', a.request, '--sha256', a.sha256,
            '--execute', '--child', '--approval', a.approval, '--approval-sha256', a.approval_sha256,
            '--dispatch', a.dispatch, '--dispatch-sha256', a.dispatch_sha256]
        recovery = dispatch.get('administrative_recovery') or {}
        r = shared.run_supervised(shared.SupervisionSpec(**q['spec']), command, q['supervisor_output'],
            q['supervisor']['dependency_root'], q['supervisor']['dependency_sha256'],
            recovery_decision_path=recovery.get('path'), recovery_decision_sha=recovery.get('sha256'))
        require(r['status'] == 'SUCCESS' and r['slot_completed'], 'SUPERVISOR_FAILED_STOP'); return
    guard = shared.ChildGuard.from_environment()
    try:
        require(vars(guard.spec) == q['spec'], 'CHILD_SPEC_DRIFT')
        acquire(q, frozen.http_open, guard, request_sha=a.sha256)
        guard.complete('SUCCESS', device_recovered=True, actual_forward=0, actual_backward=0)
    except BaseException:
        guard.complete('FAILED', device_recovered=True, actual_forward=0, actual_backward=0); raise


if __name__ == '__main__': main()
