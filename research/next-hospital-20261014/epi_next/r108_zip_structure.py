"""Bounded public ZIP directory preflight. No local headers/member/pixel reads.

Supported profile: nonempty, single disk, no archive comment, contiguous central
directory; ZIP64 fixed 44-byte payload only. Unsupported layouts stop, no scan.
Actual transport is reachable from CLI only after fresh approval/dispatch.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import struct
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

CAPS = dict(body_bytes=5242880, HEAD_requests=1, Range_requests=3,
            wall_seconds=60, RSS_bytes=134217728, output_bytes=1048576,
            central_directory_bytes=4194304, zip64_record_bytes=56,
            max_entries=4096, max_member_uncompressed=1073741824,
            max_total_uncompressed=8589934592, max_ratio=4096)
SCHEMA = 'R108_ZIP_STRUCTURE_REQUEST_V1'
ALGORITHM = 'FOOTER42_ZIP64_FIXED56_EXACT_CENTRAL_V1'
BUNDLE_SCHEMA = 'R108_ZIP_STRUCTURE_BUNDLE_REQUEST_V1'
BUNDLE_CAPS = dict(archives=2, HEAD_requests=2, Range_requests=6, body_bytes=10485760,
                   wall_seconds=120, RSS_bytes=134217728, output_bytes=2097152)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(ref):
    p = Path(ref['path'])
    require(p.stat().st_size <= 2 * 1024**2, 'CONTROL_SIZE')
    raw = p.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == ref['sha256'], 'CONTROL_SHA')
    return json.loads(raw)


class Budget:
    def __init__(self, guard=None):
        self.start = time.monotonic()
        self.body = self.heads = self.ranges = 0
        self.guard = guard

    def check(self):
        require(time.monotonic() - self.start < CAPS['wall_seconds'], 'WALL_LIMIT')
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform != 'darwin':
            rss *= 1024
        require(rss <= CAPS['RSS_bytes'], 'RSS_LIMIT')
        if self.guard:
            self.guard.check()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        fp.close()  # Never let the default redirect handler drain the body.
        raise ValueError('REDIRECT_FORBIDDEN')


def http_open(url, method, headers, timeout):
    # No decompression, redirect, retry, cookie or range fallback handler.
    opener = urllib.request.build_opener(NoRedirect())
    try:
        return opener.open(urllib.request.Request(url, method=method, headers=headers), timeout=timeout)
    except urllib.error.HTTPError as exc:
        exc.close()  # Includes 412/416/403; do not drain rejected error bodies.
        raise ValueError('HTTP_STATUS_BEFORE_BODY') from exc


def response_headers(response, url, status):
    require(response.status == status, 'HTTP_STATUS_BEFORE_BODY')
    require(response.geturl() == url, 'RESPONSE_URL_DRIFT')
    headers = {}
    for key, value in response.headers.items():
        key = key.lower()
        require(key not in headers, 'DUPLICATE_HTTP_HEADER')
        headers[key] = value.strip()
    require(headers.get('content-encoding', 'identity').lower() == 'identity', 'CONTENT_ENCODING')
    require('transfer-encoding' not in headers, 'TRANSFER_ENCODING_UNSUPPORTED')
    return headers


def strong_etag(value):
    return (isinstance(value, str) and 2 < len(value) <= 256 and value[0] == value[-1] == '"'
            and all(33 <= ord(c) <= 126 and c != '"' for c in value[1:-1]))


def integer_header(headers, key):
    raw = headers.get(key, '')
    require(re.fullmatch(r'[0-9]{1,20}', raw) is not None, 'HTTP_INTEGER_HEADER')
    return int(raw)


def fetch_range(source, etag, start, end, budget, transport):
    size = source['bytes']; count = end - start + 1
    require(0 <= start <= end < size and 0 < count <= CAPS['central_directory_bytes'], 'RANGE_BOUNDS')
    require(budget.ranges < CAPS['Range_requests'] and budget.body + count <= CAPS['body_bytes'], 'RANGE_BUDGET')
    budget.check(); budget.ranges += 1
    headers = {'Range': f'bytes={start}-{end}', 'If-Match': etag, 'Accept-Encoding': 'identity'}
    with transport(source['url'], 'GET', headers, min(10, 60 - (time.monotonic() - budget.start))) as response:
        h = response_headers(response, source['url'], 206)
        require(h.get('etag') == etag, 'ETAG_DRIFT')
        require(h.get('content-range') == f'bytes {start}-{end}/{size}', 'CONTENT_RANGE')
        require(integer_header(h, 'content-length') == count, 'RANGE_LENGTH_BEFORE_BODY')
        # Length is checked BEFORE read, and no cap+1 byte is consumed. The HTTP
        # framing counter establishes EOF at Content-Length, not socket EOF.
        raw = bytearray()
        while len(raw) < count:
            budget.check()
            chunk = response.read(min(65536, count - len(raw)))
            require(0 < len(chunk) <= count - len(raw), 'TRUNCATED_OR_OVERLONG_RESPONSE')
            raw.extend(chunk); budget.body += len(chunk)
        require(getattr(response, 'length', None) == 0, 'HTTP_FRAMED_EOF_UNPROVEN')
        budget.check()
        return bytes(raw)


def footer_plan(tail, total):
    require(len(tail) == 42 and total >= 98, 'FOOTER_SIZE')
    end = struct.unpack('<4s4H2IH', tail[-22:])
    require(end[0] == b'PK\x05\x06' and end[-1] == 0, 'EOCD_OR_COMMENT_UNSUPPORTED')
    _, disk, cd_disk, on_disk, count, length, offset, _ = end
    require(disk == cd_disk == 0 and on_disk == count and count > 0, 'MULTIDISK_OR_EMPTY_UNSUPPORTED')
    if count == 65535 or length == 0xffffffff or offset == 0xffffffff:
        locator = struct.unpack('<4sIQI', tail[:20])
        require(locator[0] == b'PK\x06\x07' and locator[1] == 0 and locator[3] == 1, 'ZIP64_LOCATOR')
        require(0 <= locator[2] and locator[2] + 56 == total - 42, 'ZIP64_EXTENSION_OR_LAYOUT_UNSUPPORTED')
        return dict(zip64=True, zip64_offset=locator[2], eocd_values=end[3:7])
    require(46 <= length <= CAPS['central_directory_bytes'] and offset + length == total - 22, 'CENTRAL_LIMIT_OR_BOUNDS')
    return dict(zip64=False, offset=offset, length=length, count=count, boundary=total - 22)


def zip64_plan(raw, first):
    require(len(raw) == 56, 'ZIP64_SHORT')
    z = struct.unpack('<4sQ2H2I4Q', raw)
    require(z[0] == b'PK\x06\x06' and z[1] == 44 and (z[2] & 255) <= 63 and z[3] <= 45,
            'ZIP64_RECORD_UNSUPPORTED')
    require(z[4] == z[5] == 0 and z[6] == z[7] and 0 < z[7] <= CAPS['max_entries'], 'ZIP64_MULTIDISK_OR_COUNT')
    require(46 <= z[8] <= CAPS['central_directory_bytes'] and z[9] + z[8] == first['zip64_offset'], 'ZIP64_CENTRAL_BOUNDS')
    for value, sentinel, actual in zip(first['eocd_values'], (65535, 65535, 0xffffffff, 0xffffffff), (z[6], z[7], z[8], z[9])):
        require(value in (sentinel, actual), 'ZIP64_EOCD_DISAGREES')
    return dict(zip64=True, offset=z[9], length=z[8], count=z[7], boundary=first['zip64_offset'])


def extra_fields(raw):
    fields = {}; pos = 0
    while pos < len(raw):
        require(pos + 4 <= len(raw), 'EXTRA_TRUNCATED')
        key, n = struct.unpack_from('<HH', raw, pos); pos += 4
        require(pos + n <= len(raw) and key not in fields, 'EXTRA_BOUNDS_OR_DUPLICATE')
        fields[key] = raw[pos:pos+n]; pos += n
    return fields


def central_directory(raw, plan):
    require(len(raw) == plan['length'] and 0 < plan['count'] <= CAPS['max_entries'], 'CENTRAL_SIZE_OR_COUNT')
    pos = total = 0; rows = []; seen = set(); offsets = set(); spans = []
    for _ in range(plan['count']):
        require(pos + 46 <= len(raw), 'CENTRAL_EOF')
        h = struct.unpack_from('<4s6H3I5H2I', raw, pos); pos += 46
        require(h[0] == b'PK\x01\x02' and h[2] <= 45, 'CENTRAL_SIGNATURE_OR_VERSION')
        flags, method, crc, comp, uncomp = h[3], h[4], h[7], h[8], h[9]
        nl, el, cl, disk = h[10:14]; attrs, offset = h[15], h[16]
        require(flags & ~(0x800 | 8 | 6) == 0 and method in (0, 8), 'ENCRYPTION_FLAGS_OR_COMPRESSION_UNSUPPORTED')
        require(0 < nl <= 1024 and el <= 4096 and cl <= 4096 and pos + nl + el + cl <= len(raw), 'CENTRAL_VARIABLE_BOUNDS')
        name = raw[pos:pos+nl].decode('utf-8' if flags & 0x800 else 'cp437')
        fields = extra_fields(raw[pos+nl:pos+nl+el]); pos += nl + el + cl
        values = [uncomp, comp, offset, disk]; zp = 0
        for i, marker in enumerate((0xffffffff, 0xffffffff, 0xffffffff, 65535)):
            if values[i] != marker:
                continue
            n = 4 if i == 3 else 8; z = fields.get(1, b'')
            require(zp + n <= len(z), 'ZIP64_EXTRA_MISSING_OR_SHORT')
            values[i] = int.from_bytes(z[zp:zp+n], 'little'); zp += n
        uncomp, comp, offset, disk = values
        parts = name.rstrip('/').split('/')
        require(name and not name.startswith('/') and '\\' not in name and ':' not in name
                and all(x not in ('', '.', '..') for x in parts)
                and all(ord(c) >= 32 and ord(c) != 127 for c in name)
                and not stat.S_ISLNK(attrs >> 16), 'PATH_TRAVERSAL_OR_SYMLINK')
        require(disk == 0 and name not in seen and offset not in offsets, 'MULTIDISK_OR_DUPLICATE_MEMBER')
        require(0 <= offset and offset + 30 + nl + comp <= plan['offset'], 'LOCAL_DECLARED_EXTENT_BOUNDS')
        require((comp > 0 or uncomp == 0) and 0 <= uncomp <= CAPS['max_member_uncompressed']
                and uncomp <= max(comp, 1) * CAPS['max_ratio'], 'ZIP_BOMB_DECLARATION')
        require(method != 0 or comp == uncomp, 'STORED_SIZE_MISMATCH')
        total += uncomp
        require(total <= CAPS['max_total_uncompressed'], 'UNCOMPRESSED_TOTAL_LIMIT')
        seen.add(name); offsets.add(offset)
        spans.append((offset, offset + 30 + nl + comp))
        rows.append(dict(name=name, header_offset=offset, compression=method,
                         compressed_bytes=comp, uncompressed_bytes=uncomp, crc32=crc))
    require(pos == len(raw), 'CENTRAL_TRAILING_OR_COUNT_MISMATCH')
    spans.sort()
    require(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), 'DECLARED_MEMBER_OVERLAP')
    return rows


def validate_request(q):
    require(q['schema'] == SCHEMA and q['caps'] == CAPS and q['algorithm'] == ALGORITHM, 'EXACT_SCOPE')
    s = q['source']; url = urlsplit(s['url'])
    require(re.fullmatch(r'[A-Za-z0-9_.-]+\.zip', s['key']) is not None
            and url.scheme == 'https' and url.netloc == 'example.invalid' and not url.query and not url.fragment
            and url.path == f"/api/records/3757476/files/{s['key']}/content", 'PINNED_PUBLIC_URL')
    require(s['record_id'] == 3757476 and s['version'] == 'Verson 1.0'
            and type(s['bytes']) is int and s['bytes'] >= 98
            and re.fullmatch('md5:[0-9a-f]{32}', s['checksum']) is not None, 'SOURCE_METADATA_BINDING')
    record = read_json(q['metadata_binding'])
    matches = [f for f in record['files'] if f['key'] == s['key']]
    require(record['id'] == s['record_id'] and record['metadata']['version'] == s['version']
            and len(matches) == 1 and matches[0]['size'] == s['bytes']
            and matches[0]['checksum'] == s['checksum'] and matches[0]['links']['self'] == s['url'],
            'PUBLIC_METADATA_SOURCE_DRIFT')
    require(q['spec']['device'] == 'cpu' and q['spec']['max_forward'] == q['spec']['max_backward'] == 0
            and q['spec']['timeout_seconds'] == 60, 'ZERO_MODEL_CPU_SPEC')
    for item in q['source_bindings']:
        require(digest(item['path']) == item['sha256'], 'SOURCE_DRIFT')
    require(digest(sys.executable) == q['runtime_sha256'], 'RUNTIME_DRIFT')
    for package, version in q.get('package_versions', {}).items():
        require(importlib.metadata.version(package) == version, 'PACKAGE_DRIFT')


def validate_bundle(q):
    require(q['schema'] == BUNDLE_SCHEMA and q['caps'] == BUNDLE_CAPS, 'EXACT_BUNDLE_SCOPE')
    require(len(q['components']) == 2 and q['spec']['device'] == 'cpu'
            and q['spec']['max_forward'] == q['spec']['max_backward'] == 0
            and q['spec']['timeout_seconds'] == 120, 'BUNDLE_ZERO_MODEL_SERIAL_SPEC')
    for item, key, role, directory in zip(q['components'],
            ('COVID-19-CT-Seg_20cases.zip', 'Infection_Mask.zip'), ('CT', 'INFECTION'), ('ct', 'infection')):
        component = read_json(item['request'])
        validate_request(component)
        require(item['role'] == role and component['source']['key'] == key
                and component.get('bundle_only') is True
                and component['output_root'] == str(Path(q['output_root'])/directory), 'BUNDLE_COMPONENT_IDENTITY')
        for field in ('source_commit', 'source_bindings', 'runtime_sha256', 'package_versions', 'supervisor'):
            require(component[field] == q[field], 'BUNDLE_CLOSURE_DRIFT')


def preflight(q, transport, guard=None, budget=None):
    """Injected transport enables generated tests; actual transport only in CLI."""
    source = q['source']; budget = budget or Budget(guard); budget.check()
    require(budget.heads < CAPS['HEAD_requests'], 'HEAD_BUDGET')
    budget.heads += 1
    with transport(source['url'], 'HEAD', {'Accept-Encoding': 'identity'}, 10) as response:
        h = response_headers(response, source['url'], 200)
        require(integer_header(h, 'content-length') == source['bytes'], 'HEAD_SOURCE_LENGTH')
        etag = h.get('etag')
        require(strong_etag(etag), 'STRONG_ETAG_REQUIRED')
        require(h.get('accept-ranges', '').lower() == 'bytes', 'RANGES_NOT_ADVERTISED')
        # HEAD body is never read. ETag is an observed run-local identity lease,
        # not a claimed full-archive MD5/SHA verification.
    size = source['bytes']
    tail = fetch_range(source, etag, size-42, size-1, budget, transport)
    plan = footer_plan(tail, size)
    if plan['zip64']:
        z = fetch_range(source, etag, plan['zip64_offset'], plan['zip64_offset']+55, budget, transport)
        plan = zip64_plan(z, plan)
    directory = fetch_range(source, etag, plan['offset'], plan['offset']+plan['length']-1, budget, transport)
    rows = central_directory(directory, plan)
    return dict(schema='R108_ZIP_STRUCTURE_RESULT_V1', status='STRUCTURE_ONLY_MEDICAL_NOT_EVALUATED',
                source=source, observed_strong_etag=etag, plan=plan, members=rows,
                HEAD_requests=budget.heads, Range_requests=budget.ranges, body_bytes=budget.body,
                directory_sha256=hashlib.sha256(directory).hexdigest(),
                full_archive_checksum_verified=False, member_local_headers_read=False,
                member_bodies_read=False, decompression=False, medical_denominator=None)


def write_exclusive(path, value, limit):
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
    require(len(raw) <= limit, 'OUTPUT_LIMIT')
    with Path(path).open('xb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())


def execute(q, sha, guard, output_limit=CAPS['output_bytes']):
    out = Path(q['output_root']); out.mkdir(mode=0o700, exist_ok=False)
    receipt = dict(schema='R108_ZIP_PREFLIGHT_RECEIPT_V1', request_sha256=sha,
                   status='FAILED_STOP_NO_RETRY', medical_denominator=None, models=0)
    budget = Budget(guard)
    previous = signal.getsignal(signal.SIGALRM)
    def alarm(*_):
        raise ValueError('WALL_LIMIT')
    signal.signal(signal.SIGALRM, alarm); signal.setitimer(signal.ITIMER_REAL, 60)
    try:
        result = preflight(q, http_open, guard, budget)
        require(16384 <= output_limit <= CAPS['output_bytes'], 'OUTPUT_SUBBUDGET')
        write_exclusive(out/'STRUCTURE.json', result, output_limit-16384)
        receipt.update(status=result['status'], structure_sha256=digest(out/'STRUCTURE.json'))
    except BaseException as exc:
        receipt.update(error_type=type(exc).__name__, error=str(exc)[:300]); raise
    finally:
        try:
            receipt.update(HEAD_requests=budget.heads, Range_requests=budget.ranges,
                           body_bytes=budget.body, elapsed_seconds=time.monotonic()-budget.start)
            write_exclusive(out/'RECEIPT.json', receipt, 16384)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)


def execute_bundle(q, sha, guard):
    """One original queue job, two exact components in order; failure stops all."""
    out = Path(q['output_root']); out.mkdir(mode=0o700, exist_ok=False)
    start = time.monotonic()
    receipt = dict(schema='R108_STRUCTURE_BUNDLE_RECEIPT_V1', request_sha256=sha,
                   status='FAILED_STOP_NO_RETRY', completed=[], attempted=[],
                   medical_denominator=None, members_read=0, models=0)
    try:
        for item in q['components']:
            require(time.monotonic()-start < BUNDLE_CAPS['wall_seconds'], 'BUNDLE_WALL_LIMIT')
            if guard:
                guard.check()
            component = read_json(item['request']); validate_request(component)
            receipt['attempted'].append(item['role'])
            execute(component, item['request']['sha256'], guard, CAPS['output_bytes']-8192)
            receipt['completed'].append(item['role'])
        require(time.monotonic()-start < BUNDLE_CAPS['wall_seconds'], 'BUNDLE_WALL_LIMIT')
        receipt['status'] = 'STRUCTURE_ONLY_MEDICAL_NOT_EVALUATED'
    except BaseException as exc:
        receipt.update(error_type=type(exc).__name__, error=str(exc)[:300]); raise
    finally:
        receipt['elapsed_seconds'] = time.monotonic()-start
        receipt['costs'] = {}
        for item, directory in zip(q['components'], ('ct', 'infection')):
            p = out/directory/'RECEIPT.json'
            if p.exists():
                value = json.loads(p.read_text())
                receipt['costs'][item['role']] = {k: value.get(k) for k in ('HEAD_requests', 'Range_requests', 'body_bytes', 'status')}
        write_exclusive(out/'BUNDLE_RECEIPT.json', receipt, 8192)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--request', required=True); p.add_argument('--sha256', required=True)
    p.add_argument('--execute', action='store_true'); p.add_argument('--approval'); p.add_argument('--approval-sha256')
    p.add_argument('--dispatch'); p.add_argument('--dispatch-sha256'); p.add_argument('--child', action='store_true')
    a = p.parse_args(); q = read_json(dict(path=a.request, sha256=a.sha256))
    bundle = q.get('schema') == BUNDLE_SCHEMA
    (validate_bundle if bundle else validate_request)(q)
    if not a.execute:
        print(json.dumps(dict(status='CHECK_ONLY_NO_HTTP_OR_PAYLOAD'))); return
    require(bundle or not q.get('bundle_only'), 'COMPONENT_ONLY_UNDER_EXACT_BUNDLE')
    require(all((a.approval, a.approval_sha256, a.dispatch, a.dispatch_sha256)), 'NEW_APPROVAL_DISPATCH_REQUIRED')
    owner = read_json(dict(path=a.approval, sha256=a.approval_sha256))
    expected = dict(schema='R108_ZIP_STRUCTURE_BUNDLE_APPROVAL_V1' if bundle else 'R108_ZIP_STRUCTURE_APPROVAL_V1',
                    status='APPROVED_NEW_SCOPE', request_sha256=a.sha256,
                    permit_structure_HEAD_Range=True, permit_member_reads=False, permit_models=False, retry=False)
    require(all(type(owner.get(k)) is type(v) and owner.get(k) == v for k, v in expected.items()), 'NEW_EXACT_OWNER_REQUIRED')
    dispatch = read_json(dict(path=a.dispatch, sha256=a.dispatch_sha256))
    from . import r92_label_read_entry as original
    original.validate_dispatch(q, a.sha256, a.approval_sha256, dispatch)
    shared = original.load_shared(q['supervisor'])
    if not a.child:
        command = [sys.executable, '-m', 'epi_next.r108_zip_structure', '--request', a.request, '--sha256', a.sha256,
                   '--execute', '--child', '--approval', a.approval, '--approval-sha256', a.approval_sha256,
                   '--dispatch', a.dispatch, '--dispatch-sha256', a.dispatch_sha256]
        recovery = dispatch.get('administrative_recovery') or {}
        result = shared.run_supervised(shared.SupervisionSpec(**q['spec']), command, q['supervisor_output'],
                    q['supervisor']['dependency_root'], q['supervisor']['dependency_sha256'],
                    recovery_decision_path=recovery.get('path'), recovery_decision_sha=recovery.get('sha256'))
        require(result['status'] == 'SUCCESS' and result['slot_completed'], 'SUPERVISOR_FAILED_STOP')
        return
    guard = shared.ChildGuard.from_environment()
    try:
        require(vars(guard.spec) == q['spec'], 'CHILD_SPEC_DRIFT')
        (execute_bundle if bundle else execute)(q, a.sha256, guard)
        guard.complete('SUCCESS', device_recovered=True, actual_forward=0, actual_backward=0)
    except BaseException:
        guard.complete('FAILED', device_recovered=True, actual_forward=0, actual_backward=0); raise


if __name__ == '__main__':
    main()
