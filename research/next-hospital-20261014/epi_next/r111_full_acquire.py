"""Independent opaque full GET + bounded local ZIP directory; no member decode.
Uses existing A0 secure exclusive creation and same-inode no-clobber publish.
No HEAD, Range, resume, retry, ETag requirement or automatic source fallback.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import resource
import signal
import stat
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from urllib.parse import urljoin
import zipfile
from . import a0_acquire as a0

SCHEMA = 'R111_FULL_GET_BUNDLE_REQUEST_V1'
FILES = (('COVID-19-CT-Seg_20cases.zip', 1105395143, '873617e1fdcbe92f8aa0ce83a4798a1f', 1740),
         ('Infection_Mask.zip', 2572173, '98fa9f5401fa8409dccd1681a36febcf', 60))
CAPS = dict(body_bytes=1107967316, payload_GETs=2, redirect_GETs=2, total_GETs=4,
            redirects_per_file=1, wall_seconds=1800, RSS_bytes=268435456,
            output_metadata_bytes=2097152, disk_reserve_bytes=2147483648,
            chunk_bytes=1048576, directory_bytes=4194304, directory_entries=4096,
            max_member_uncompressed=1073741824, max_total_uncompressed=8589934592,
            max_ratio=4096)


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def source_url(key):
    return 'https://example.invalid/api/records/3757476/files/' + key + '/content'


def official_redirect_url(key):
    return 'https://example.invalid/records/3757476/files/' + key + '?download=1'


class NoAutoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # urllib raises HTTPError with the unopened body attached.


def http_open(url, headers, timeout):
    opener = urllib.request.build_opener(NoAutoRedirect())
    try:
        return opener.open(urllib.request.Request(url, headers=headers, method='GET'), timeout=timeout)
    except urllib.error.HTTPError as exc:
        return exc  # Caller inspects headers/status, closes without draining.


def headers(response, expected_url):
    require(response.geturl() == expected_url, 'FINAL_URL_DRIFT')
    result = {}
    for k, v in response.headers.items():
        k = k.lower()
        require(k not in result, 'DUPLICATE_HEADER')
        result[k] = v.strip()
    return result


class Budget:
    def __init__(self, root, remaining, guard=None, free_fn=None):
        self.root = Path(root); self.remaining = remaining; self.guard = guard
        self.free_fn = free_fn or (lambda p: os.statvfs(p).f_bavail * os.statvfs(p).f_frsize)
        self.start = time.monotonic(); self.deadline = self.start + CAPS['wall_seconds']
        self.phase_deadline = self.deadline; self.body = self.GETs = self.metadata = 0

    def check(self):
        require(time.monotonic() < min(self.deadline, self.phase_deadline), 'TIME_LIMIT')
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
        require(rss <= CAPS['RSS_bytes'], 'RSS_LIMIT')
        needed = self.remaining + CAPS['disk_reserve_bytes'] + CAPS['output_metadata_bytes']
        require(self.free_fn(self.root) >= needed, 'DISK_RESERVE')
        if self.guard:
            self.guard.check()


def bounded_directory(fd, expected_size, budget):
    """Inspect only stdlib ZIP central metadata, never ZipFile.open/read/testzip.
    Pin zipfile source in the request because the bounded precheck uses its
    runtime-specific EOCD parser before ZipFile can allocate the directory.
    """
    before = os.fstat(fd)
    require(stat.S_ISREG(before.st_mode) and before.st_size == expected_size, 'ARCHIVE_FD_SIZE')
    with os.fdopen(os.dup(fd), 'rb') as f:
        end = zipfile._EndRecData(f)
        require(end is not None, 'ZIP_EOCD')
        count, length, offset = end[zipfile._ECD_ENTRIES_TOTAL], end[zipfile._ECD_SIZE], end[zipfile._ECD_OFFSET]
        require(end[zipfile._ECD_DISK_NUMBER] == end[zipfile._ECD_DISK_START] == 0
                and count == end[zipfile._ECD_ENTRIES_THIS_DISK], 'MULTIDISK')
        require(0 < count <= CAPS['directory_entries'] and 46 <= length <= CAPS['directory_bytes'], 'DIRECTORY_LIMIT')
        require(0 <= offset and offset + length == end[zipfile._ECD_LOCATION], 'CONCAT_OR_DIRECTORY_BOUNDS')
        comment = end[zipfile._ECD_COMMENT]
        require(len(comment) == end[zipfile._ECD_COMMENT_SIZE], 'ZIP_COMMENT_TRUNCATED')
        tail = 76 if end[zipfile._ECD_SIGNATURE] == zipfile.stringEndArchive64 else 0
        require(end[zipfile._ECD_LOCATION] + tail + 22 + len(comment) == expected_size, 'ZIP_TRAILING_OR_EXTENSION_UNSUPPORTED')
        f.seek(0)
        with zipfile.ZipFile(f) as archive:
            require(archive.start_dir == offset and len(archive.infolist()) == count, 'DIRECTORY_COUNT')
            rows = []; seen = set(); offsets = set(); total = 0; spans = []
            for item in archive.infolist():
                budget.check(); name = item.orig_filename
                parts = name.rstrip('/').split('/')
                normalized = unicodedata.normalize('NFC', name).casefold()
                mode = item.external_attr >> 16
                require(name == item.filename and len(name.encode('utf-8')) <= 1024
                        and not name.startswith('/') and '\\' not in name and ':' not in name
                        and all(p not in ('', '.', '..') for p in parts)
                        and all(ord(c) >= 32 and ord(c) != 127 for c in name)
                        and stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR), 'UNSAFE_MEMBER_PATH_OR_TYPE')
                require(item.flag_bits & ~(0x800 | 8 | 6) == 0 and item.compress_type in (0, 8), 'ENCRYPTION_OR_COMPRESSION')
                require(normalized not in seen and item.header_offset not in offsets, 'DUPLICATE_MEMBER')
                require(len(item.extra) <= 4096 and len(item.comment) <= 4096, 'MEMBER_METADATA_LIMIT')
                require(0 <= item.file_size <= CAPS['max_member_uncompressed']
                        and (item.compress_size > 0 or item.file_size == 0)
                        and item.file_size <= max(item.compress_size, 1) * CAPS['max_ratio'], 'ZIP_BOMB_DECLARATION')
                require(item.compress_type != 0 or item.file_size == item.compress_size, 'STORED_SIZE_MISMATCH')
                # Minimum span is a declaration check, not verification of local
                # headers/descriptors/CRC/deflate EOF, which remain unread.
                end_min = item.header_offset + 30 + len(name.encode('utf-8' if item.flag_bits & 0x800 else 'cp437')) + item.compress_size
                require(0 <= item.header_offset and end_min <= offset, 'MEMBER_DECLARED_BOUNDS')
                spans.append((item.header_offset, end_min)); total += item.file_size
                require(total <= CAPS['max_total_uncompressed'], 'TOTAL_UNCOMPRESSED_LIMIT')
                seen.add(normalized); offsets.add(item.header_offset)
                rows.append(dict(name=name, header_offset=item.header_offset, compression=item.compress_type,
                    compressed_bytes=item.compress_size, uncompressed_bytes=item.file_size, declared_crc32=item.CRC))
            spans.sort(); require(all(a[1] <= b[0] for a,b in zip(spans,spans[1:])), 'DECLARED_OVERLAP')
    after = os.fstat(fd)
    require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns) ==
            (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns), 'LOCAL_ARCHIVE_DRIFT')
    return dict(entries=count, central_directory_bytes=length, members=rows,
                member_payload_decoded=False, local_member_headers_read=False,
                member_CRC_or_EOF_verified=False, medical_denominator=None)


def write_metadata(path, value, budget, limit):
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
    require(len(raw) <= limit and budget.metadata + len(raw) <= CAPS['output_metadata_bytes'], 'METADATA_OUTPUT_LIMIT')
    with os.fdopen(a0.exclusive(path), 'wb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    budget.metadata += len(raw)


def transfer_one(item, root, budget, transport, record):
    key, size, expected = item['key'], item['bytes'], item['md5']
    part, final = root/(key+'.part'), root/key
    require(not final.exists() and not part.exists() and not final.is_symlink() and not part.is_symlink(), 'NO_RESUME_NO_OVERWRITE')
    budget.phase_deadline = min(budget.deadline, time.monotonic()+item['seconds'])
    a0.secure_parent(part)
    fd = os.open(part,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    md5 = hashlib.md5(); sha = hashlib.sha256(); url = item['url']; total = 0
    record.update(part=str(part), final=str(final), GETs=0, redirects=[], bytes=0, promoted=False)
    try:
        for hop in range(CAPS['redirects_per_file']+1):
            budget.check(); require(budget.GETs < CAPS['total_GETs'], 'GET_LIMIT')
            budget.GETs += 1; record['GETs'] += 1
            with transport(url, {'Accept-Encoding':'identity'}, min(15, budget.phase_deadline-time.monotonic())) as response:
                h = headers(response, url); code = response.status
                if code in (301,302,303,307,308):
                    target = urljoin(url,h.get('location',''))
                    require(hop == 0 and url == source_url(key) and target == official_redirect_url(key), 'UNAPPROVED_REDIRECT')
                    record['redirects'].append(dict(status=code, source=url, target=target)); url = target
                    continue  # Context closes without reading redirect body.
                require(code == 200, 'GET_STATUS_BEFORE_BODY')
                require(h.get('content-encoding','identity').lower() == 'identity'
                        and 'transfer-encoding' not in h and 'content-range' not in h, 'ENCODING_OR_RANGE_RESPONSE')
                require(h.get('content-length') == str(size), 'EXACT_LENGTH_BEFORE_BODY')
                record['accepted_url'] = url
                while total < size:
                    budget.check(); amount=min(CAPS['chunk_bytes'],size-total)
                    require(budget.body+amount <= CAPS['body_bytes'],'BODY_LIMIT_BEFORE_READ')
                    chunk = response.read(amount)
                    require(0 < len(chunk) <= size-total, 'TRUNCATED_OR_OVERLONG_BODY')
                    total += len(chunk); budget.body += len(chunk); budget.remaining -= len(chunk); record['bytes'] = total
                    require(budget.body <= CAPS['body_bytes'], 'BODY_LIMIT')
                    md5.update(chunk); sha.update(chunk)
                    with memoryview(chunk) as view:
                        while view:
                            written=os.write(fd,view); require(written>0,'WRITE_FAILURE'); view=view[written:]
                require(getattr(response,'length',None) == 0, 'HTTP_FRAMED_EOF_UNPROVEN')
                record.update(md5=md5.hexdigest(), sha256=sha.hexdigest(), exact_size=total==size)
                require(total == size and md5.hexdigest() == expected, 'FULL_SIZE_OR_MD5_MISMATCH')
                os.fsync(fd); budget.check()
                directory = bounded_directory(fd,size,budget)
                write_metadata(root/(key+'.directory.json'),directory,budget,983040)
                budget.check(); require(time.monotonic() < budget.phase_deadline-1, 'FINALIZATION_TIME_RESERVE')
                held=os.fstat(fd); named=part.lstat()
                require(stat.S_ISREG(named.st_mode) and
                        (held.st_dev,held.st_ino,held.st_size,held.st_mtime_ns)==
                        (named.st_dev,named.st_ino,named.st_size,named.st_mtime_ns), 'PART_PATH_IDENTITY_DRIFT')
                # Existing A0 publication uses hardlink+unlink, same inode/data.
                a0.publish(part,final)
                published=final.lstat()
                require(stat.S_ISREG(published.st_mode) and
                        (published.st_dev,published.st_ino,published.st_size)==
                        (held.st_dev,held.st_ino,held.st_size), 'PUBLICATION_IDENTITY_UNCERTAIN')
                parent=os.open(root,os.O_RDONLY)
                try:os.fsync(parent)
                finally:os.close(parent)
                record.update(promoted=True, status='VERIFIED_OPAQUE_ARCHIVE_AND_DIRECTORY_ONLY',
                              directory_path=str(root/(key+'.directory.json')))
                return
        raise ValueError('REDIRECT_HOP_LIMIT')
    finally:
        record['bytes'] = total; record['part_exists'] = part.exists(); record['final_exists'] = final.exists()
        record['partial_md5'] = md5.hexdigest(); record['partial_sha256'] = sha.hexdigest()
        os.close(fd)


def acquire(q, transport, guard=None, free_fn=None, request_sha=None):
    root=Path(q['output_root']); a0.secure_parent(root);root.mkdir(mode=0o700,exist_ok=False)
    with os.fdopen(a0.exclusive(root/'CLAIM.json'),'w') as f:
        json.dump(dict(status='ONCE_ONLY_NO_RETRY'),f)
    budget=Budget(root,sum(x['bytes'] for x in q['files']),guard,free_fn)
    budget.metadata=(root/'CLAIM.json').stat().st_size
    result=dict(schema='R111_FULL_ACQUISITION_RECEIPT_V1',status='FAILED_STOP_NO_RETRY',files=[],
                request_sha256=request_sha,source_commit=q.get('source_commit'),
                HTTP_HEAD=0,HTTP_Range=0,member_payload_decoded=False,models=0,medical_denominator=None)
    previous=signal.getsignal(signal.SIGALRM)
    def alarm(*_):raise ValueError('WALL_LIMIT')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,CAPS['wall_seconds'])
    try:
        budget.check()
        for item in q['files']:
            record=dict(key=item['key'],status='FAILED_STOP_NO_RETRY');result['files'].append(record)
            signal.setitimer(signal.ITIMER_REAL,min(item['seconds'],max(.001,budget.deadline-time.monotonic())))
            transfer_one(item,root,budget,transport,record)
        budget.check();result['status']='FULL_ARCHIVES_AND_LOCAL_DIRECTORIES_ONLY'
    except BaseException as exc:
        result.update(error_type=type(exc).__name__,error=str(exc)[:300]);raise
    finally:
        result.update(GET_requests=budget.GETs,application_body_bytes=budget.body,elapsed_seconds=time.monotonic()-budget.start)
        try:write_metadata(root/'RECEIPT.json',result,budget,65536)
        finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)


def validate(q):
    require(q['schema']==SCHEMA and q['caps']==CAPS,'EXACT_REQUEST_SCOPE')
    require(q['files']==[dict(key=k,bytes=n,md5=m,seconds=s,url=source_url(k)) for k,n,m,s in FILES], 'EXACT_TWO_OFFICIAL_FILES')
    require(q['spec']['device']=='cpu' and q['spec']['max_forward']==q['spec']['max_backward']==0
            and q['spec']['timeout_seconds']==1800,'ZERO_MODEL_CPU_SCOPE')
    for r in q['source_bindings']+q['stdlib_bindings']:
        require(a0.digest_bytes(Path(r['path']).read_bytes())==r['sha256'],'SOURCE_DRIFT')
    require(a0.digest_bytes(Path(sys.executable).read_bytes())==q['runtime_sha256'],'RUNTIME_DRIFT')
    require(platform.python_version()==q['python_version'],'PYTHON_VERSION_DRIFT')
    for k,v in q['package_versions'].items():require(importlib.metadata.version(k)==v,'PACKAGE_DRIFT')
    for r in q['metadata_evidence']:a0.bound_json(r['path'],r['sha256']) if r['path'].endswith('.json') else require(a0.digest_bytes(Path(r['path']).read_bytes())==r['sha256'],'EVIDENCE_DRIFT')


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--sha256',required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--approval');p.add_argument('--approval-sha256')
    p.add_argument('--dispatch');p.add_argument('--dispatch-sha256');p.add_argument('--child',action='store_true');a=p.parse_args()
    q=a0.bound_json(a.request,a.sha256);validate(q)
    if not a.execute:print(json.dumps(dict(status='CHECK_ONLY_NO_HTTP_NO_FILES')));return
    require(all((a.approval,a.approval_sha256,a.dispatch,a.dispatch_sha256)),'NEW_APPROVAL_DISPATCH_REQUIRED')
    owner=a0.bound_json(a.approval,a.approval_sha256)
    expected=dict(schema='R111_FULL_GET_APPROVAL_V1',status='APPROVED_NEW_SCOPE',request_sha256=a.sha256,
                  permit_opaque_full_GET=True,permit_local_directory=True,permit_member_decode=False,permit_models=False,retry=False,resume=False)
    require(all(type(owner.get(k)) is type(v) and owner.get(k)==v for k,v in expected.items()),'NEW_EXACT_APPROVAL_REQUIRED')
    from . import r92_label_read_entry as original
    dispatch=a0.bound_json(a.dispatch,a.dispatch_sha256);original.validate_dispatch(q,a.sha256,a.approval_sha256,dispatch);shared=original.load_shared(q['supervisor'])
    if not a.child:
        command=[sys.executable,'-m','epi_next.r111_full_acquire','--request',a.request,'--sha256',a.sha256,'--execute','--child',
                 '--approval',a.approval,'--approval-sha256',a.approval_sha256,'--dispatch',a.dispatch,'--dispatch-sha256',a.dispatch_sha256]
        recovery=dispatch.get('administrative_recovery') or {}
        r=shared.run_supervised(shared.SupervisionSpec(**q['spec']),command,q['supervisor_output'],q['supervisor']['dependency_root'],q['supervisor']['dependency_sha256'],
             recovery_decision_path=recovery.get('path'),recovery_decision_sha=recovery.get('sha256'))
        require(r['status']=='SUCCESS' and r['slot_completed'],'SUPERVISOR_FAILED_STOP');return
    guard=shared.ChildGuard.from_environment()
    try:
        require(vars(guard.spec)==q['spec'],'CHILD_SPEC_DRIFT');acquire(q,http_open,guard,request_sha=a.sha256)
        guard.complete('SUCCESS',device_recovered=True,actual_forward=0,actual_backward=0)
    except BaseException:guard.complete('FAILED',device_recovered=True,actual_forward=0,actual_backward=0);raise


if __name__=='__main__':main()
