"""One approved opaque archive, bounded transfer and ZIP directory only. No member decode."""
import argparse
import fcntl
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path, PurePosixPath
import selectors
import re
import signal
import stat
import struct
import subprocess
import time

SOURCE = 'https://example.invalid/approved-source-archive-required'
SIZE = 11273767727
MD5 = '7cd2a4fdc7b1348c093b9a384d4b2240'


def digest_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def bound_json(path, expected):
    with open(path, 'rb') as f:
        raw = f.read(2*1024*1024+1)
    if len(raw)>2*1024*1024 or digest_bytes(raw)!=expected:
        raise ValueError('RAW_FILE_SHA_MISMATCH_OR_OVERSIZE')
    return json.loads(raw)


def secure_parent(path):
    path = Path(path)
    if not path.is_absolute(): raise ValueError('ABSOLUTE_PATH_REQUIRED')
    for item in reversed([path.parent, *path.parent.parents]):
        if item.exists() or item.is_symlink():
            if item.is_symlink() or not item.is_dir(): raise ValueError('UNSAFE_PARENT')
        else: item.mkdir(mode=0o700)


def exclusive(path):
    secure_parent(path)
    return os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)


def publish(part, final):
    """Atomic no-clobber name publication, same inode; no second archive copy."""
    os.link(part, final, follow_symlinks=False)
    os.unlink(part)


def _phase_child(conn, fn, args):
    try:
        os.setsid()
        conn.send(('READY', os.getpid(), os.getpgrp()))
        if conn.recv()!='GO':raise RuntimeError('START_HANDSHAKE_FAILED')
        conn.send(('OK', fn(*args)))
    except BaseException as exc:
        conn.send(('FAIL', type(exc).__name__, str(exc)[:160]))
    finally:
        conn.close()


def stop_child(child, owned_group=False):
    # Before READY, kill only our exact multiprocessing child PID. It has not
    # received GO and cannot start curl; never signal the parent's process group.
    if owned_group:
        try: os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError: pass
    elif child.is_alive():
        child.terminate()
    child.join(2)
    if owned_group:
        try: os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError: pass
    elif child.is_alive():
        child.kill()
    child.join(10)
    if child.is_alive(): raise RuntimeError('OWN_CHILD_NOT_REAPED')


def phase(fn, args, seconds, overall_deadline, disk_path, disk_floor, free_fn=None):
    """Watch blocking I/O in owned process group; no global queue or other PIDs."""
    free_fn = free_fn or (lambda p: os.statvfs(p).f_bavail*os.statvfs(p).f_frsize)
    if free_fn(disk_path)<disk_floor: raise RuntimeError('DISK_RESERVE')
    ctx=mp.get_context('fork'); read,write=ctx.Pipe(duplex=True)
    child=ctx.Process(target=_phase_child,args=(write,fn,args)); child.start();write.close()
    deadline=min(time.monotonic()+seconds,overall_deadline-12); checked=0;owned_group=False;ready=False
    try:
        while True:
            now=time.monotonic()
            if now>=deadline: raise TimeoutError('PHASE_OR_OVERALL_TIMEOUT')
            if now-checked>=1:
                if free_fn(disk_path)<disk_floor: raise RuntimeError('DISK_RESERVE')
                checked=now
            if read.poll(min(.2,max(0,deadline-now))):
                result=read.recv()
                if result[0]=='READY':
                    if ready or result[1:]!=(child.pid,child.pid) or os.getpgid(child.pid)!=child.pid:
                        raise RuntimeError('OWN_GROUP_HANDSHAKE_MISMATCH')
                    owned_group=True;ready=True;read.send('GO');continue
                if not ready:raise RuntimeError('PHASE_NOT_READY')
                child.join(1)
                if result[0]!='OK': raise RuntimeError('PHASE_FAILED:'+result[1]+':'+result[2])
                if child.is_alive() or child.exitcode!=0: raise RuntimeError('PHASE_EXIT_FAILURE')
                return result[1]
            if not child.is_alive(): raise RuntimeError('PHASE_NO_RECEIPT')
    finally:
        stop_child(child,owned_group);read.close()


class ResumeHeaders:
    """Validate the final HTTP range response before permitting any append."""
    def __init__(self, offset, size):
        self.offset, self.size = offset, size
        self.pending = bytearray()
        self.approved = False

    def feed(self, data):
        self.pending.extend(data)
        while b'\r\n\r\n' in self.pending:
            block, remainder = self.pending.split(b'\r\n\r\n', 1)
            self.pending = bytearray(remainder)
            lines = bytes(block).split(b'\r\n')
            status = re.fullmatch(rb'HTTP/\S+ ([0-9]{3})(?: .*)?', lines[0])
            if status is None: raise ValueError('RESUME_HTTP_STATUS')
            code = int(status[1])
            if 100 <= code < 200 or 300 <= code < 400:
                continue
            # HTTPS proxies can emit a CONNECT response before origin headers.
            if code == 200 and lines[0].lower().endswith(b' connection established'):
                continue
            if code != 206 or self.approved: raise ValueError('RESUME_HTTP_NOT_206')
            headers = {}
            for line in lines[1:]:
                if b':' not in line: raise ValueError('RESUME_HTTP_HEADER')
                name, value = line.split(b':', 1)
                name = name.strip().lower()
                if name in headers: raise ValueError('RESUME_DUPLICATE_HEADER')
                headers[name] = value.strip()
            wanted = f'bytes {self.offset}-{self.size-1}/{self.size}'.encode()
            if headers.get(b'content-range') != wanted: raise ValueError('RESUME_CONTENT_RANGE')
            if headers.get(b'content-encoding', b'identity').lower() != b'identity':
                raise ValueError('RESUME_CONTENT_ENCODING')
            length = headers.get(b'content-length')
            if length is not None and length != str(self.size-self.offset).encode():
                raise ValueError('RESUME_CONTENT_LENGTH')
            self.approved = True


def transfer(fd, expected_size, plan, fake_argv=None, resume_offset=0):
    """Headers/body drained separately; never retain response/header/stderr content."""
    hr,hw=os.pipe()
    argv=fake_argv or ['curl','--disable','--fail','--location','--max-redirs','3','--proto','=https',
         '--proto-redir','=https','--connect-timeout',str(plan['connect_timeout_seconds']),
         '--max-time',str(plan['wall_timeout_seconds']),'--retry','0','--speed-limit',
         str(plan['low_speed_bytes_per_second']),'--speed-time',str(plan['low_speed_seconds']),
         '--max-filesize',str(expected_size),'--silent','--show-error','--dump-header',
         '/dev/fd/'+str(hw),'--header','Accept-Encoding: identity',
         *(['--range',str(resume_offset)+'-'] if resume_offset else []),'--output','-',SOURCE]
    proc=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,pass_fds=(hw,),env={**os.environ,'A0_TEST_HEADER_FD':str(hw)} if fake_argv else None)
    os.close(hw);sel=selectors.DefaultSelector(); total=headers=errors=0
    verifier=ResumeHeaders(resume_offset,expected_size) if resume_offset else None
    body_registered=not resume_offset
    for stream,kind in [(proc.stdout,'body'),(proc.stderr,'stderr'),(hr,'headers')]:
        os.set_blocking(stream if isinstance(stream,int) else stream.fileno(),False)
        # Backpressure in stdout's kernel pipe until final range headers pass.
        if kind!='body' or body_registered:sel.register(stream,selectors.EVENT_READ,kind)
    try:
        while sel.get_map():
            for key,_ in sel.select(.2):
                source=key.fileobj if isinstance(key.fileobj,int) else key.fileobj.fileno()
                chunk=os.read(source,65536)
                if not chunk:
                    if key.data=='headers' and verifier and not verifier.approved:
                        raise ValueError('RESUME_HEADERS_INCOMPLETE')
                    sel.unregister(key.fileobj);continue
                if key.data=='body':
                    total+=len(chunk)
                    if total>expected_size-resume_offset:raise ValueError('BODY_LIMIT')
                    view=memoryview(chunk)
                    while view: view=view[os.write(fd,view):]
                elif key.data=='headers':
                    headers+=len(chunk)
                    if headers>plan['max_http_header_bytes']:raise ValueError('HEADER_LIMIT')
                    if verifier:
                        verifier.feed(chunk)
                        if verifier.approved and not body_registered:
                            sel.register(proc.stdout,selectors.EVENT_READ,'body');body_registered=True
                else:
                    errors+=len(chunk)
                    if errors>65536:raise ValueError('STDERR_LIMIT')
        exit_code=proc.wait(timeout=2)
        if exit_code!=0:raise ValueError('TRANSFER_EXIT_'+str(exit_code))
        if total!=expected_size-resume_offset:raise ValueError('BODY_SHORT')
        os.fsync(fd)
        return dict(bytes=total,archive_bytes=resume_offset+total,resume_offset_bytes=resume_offset,
                    range_response_verified=bool(verifier and verifier.approved),
                    header_bytes=headers,stderr_bytes=errors,curl_exit_code=exit_code,attempts=1)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=2)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        sel.close();os.close(hr);proc.stdout.close();proc.stderr.close()


def integrity(path, expected_size, expected_md5):
    md5=hashlib.md5();sha=hashlib.sha256();total=0
    with open(path,'rb') as f:
        while chunk:=f.read(8*1024*1024):
            total+=len(chunk)
            if total>expected_size:raise ValueError('INTEGRITY_SIZE')
            md5.update(chunk);sha.update(chunk)
    if total!=expected_size or md5.hexdigest()!=expected_md5:raise ValueError('INTEGRITY_MISMATCH')
    return dict(bytes=total,md5=md5.hexdigest(),sha256=sha.hexdigest())


def _read(f, length):
    data=f.read(length)
    if len(data)!=length:raise ValueError('ZIP_METADATA_SHORT')
    return data


def directory(path, output, limits):
    """Read EOCD/ZIP64 and central records only; never open/decompress members."""
    output=Path(output);output.mkdir(mode=0o700,exist_ok=False)
    listing=output/'inventory.jsonl.part'; summary=output/'summary.json.part'
    seen=set();groups={};written=total_uncompressed=group_bytes=0
    with open(path,'rb') as f, os.fdopen(exclusive(listing),'wb') as dst:
        length=f.seek(0,2)
        if length<22:raise ValueError('NOT_ZIP')
        f.seek(length-22);end=struct.unpack('<4s4H2IH',_read(f,22))
        # No tail search into possible member bytes: comments fail closed.
        if end[0]!=b'PK\x05\x06' or end[-1]!=0:raise ValueError('EOCD_COMMENT_OR_FORMAT_UNSUPPORTED')
        _,disk,start_disk,n_disk,n_total,cd_size,cd_offset,_=end
        boundary=length-22
        if disk or start_disk or n_disk!=n_total:raise ValueError('MULTIDISK_UNSUPPORTED')
        if n_total==65535 or cd_size==0xffffffff or cd_offset==0xffffffff:
            if length<42:raise ValueError('ZIP64_SHORT')
            f.seek(length-42);loc=struct.unpack('<4sIQI',_read(f,20))
            if loc[0]!=b'PK\x06\x07' or loc[1]!=0 or loc[3]!=1:raise ValueError('ZIP64_LOCATOR')
            if loc[2]+56>length-42:raise ValueError('ZIP64_BOUNDS')
            f.seek(loc[2]);z=struct.unpack('<4sQ2H2I4Q',_read(f,56))
            if z[0]!=b'PK\x06\x06' or z[1]!=44 or z[4] or z[5] or z[6]!=z[7]:raise ValueError('ZIP64_RECORD_UNSUPPORTED')
            n_total,cd_size,cd_offset=z[7],z[8],z[9];boundary=loc[2]
        if n_total>limits['max_directory_entries'] or cd_size>limits['max_central_directory_bytes'] or cd_offset+cd_size!=boundary:raise ValueError('DIRECTORY_LIMIT_OR_BOUNDS')
        f.seek(cd_offset)
        for _ in range(n_total):
            if f.tell()+46>cd_offset+cd_size:raise ValueError('CENTRAL_BOUNDS')
            h=struct.unpack('<4s6H3I5H2I',_read(f,46))
            if h[0]!=b'PK\x01\x02':raise ValueError('CENTRAL_SIGNATURE')
            flags,method,crc,compressed,uncompressed=h[3],h[4],h[7],h[8],h[9]
            name_len,extra_len,comment_len,disk=h[10:14];attrs,offset=h[15],h[16]
            if f.tell()+name_len+extra_len+comment_len>cd_offset+cd_size:raise ValueError('CENTRAL_VARIABLE_BOUNDS')
            raw=_read(f,name_len);extra=_read(f,extra_len);f.seek(comment_len,1)
            name=raw.decode('utf-8' if flags&0x800 else 'cp437')
            parts=PurePosixPath(name).parts
            if not name or '\\' in name or '\x00' in name or name.startswith('/') or '..' in parts or ':' in name or disk or stat.S_ISLNK(attrs>>16):raise ValueError('UNSAFE_MEMBER')
            fingerprint=hashlib.sha256(name.encode()).digest()
            if fingerprint in seen:raise ValueError('DUPLICATE_MEMBER')
            seen.add(fingerprint)
            if 0xffffffff in (uncompressed,compressed,offset):
                pos=0;zdata=None
                while pos+4<=len(extra):
                    tag,n=struct.unpack_from('<HH',extra,pos);pos+=4
                    if pos+n>len(extra):raise ValueError('EXTRA_BOUNDS')
                    if tag==1:zdata=extra[pos:pos+n]
                    pos+=n
                if zdata is None:raise ValueError('ZIP64_EXTRA_MISSING')
                pos=0;values=[]
                for v in [uncompressed,compressed,offset]:
                    if v==0xffffffff:
                        if pos+8>len(zdata):raise ValueError('ZIP64_EXTRA_SHORT')
                        v=struct.unpack_from('<Q',zdata,pos)[0];pos+=8
                    values.append(v)
                uncompressed,compressed,offset=values
            if offset>=cd_offset:raise ValueError('LOCAL_OFFSET_BOUNDS')
            row=dict(name=name,compression_method=method,compressed_bytes=compressed,uncompressed_bytes=uncompressed,crc32=crc,header_offset=offset)
            data=(json.dumps(row,ensure_ascii=True)+'\n').encode();written+=len(data)
            if written>limits['max_technical_inventory_output_bytes']:raise ValueError('OUTPUT_LIMIT')
            dst.write(data);total_uncompressed+=uncompressed
            # Category/patient directory counts; scan-level folders stay in the
            # complete per-member inventory. The summary byte budget is the cap.
            group='/'.join(parts[:2])
            if group not in groups:
                group_bytes+=len(json.dumps(group,ensure_ascii=True).encode())+24
                if group_bytes>limits['max_summary_output_bytes']-512:raise ValueError('GROUP_SUMMARY_BYTES')
            groups[group]=groups.get(group,0)+1
        if f.tell()!=cd_offset+cd_size:raise ValueError('CENTRAL_COUNT_MISMATCH')
        dst.flush();os.fsync(dst.fileno())
    result=dict(entries=n_total,central_directory_bytes=cd_size,inventory_bytes=written,declared_uncompressed_bytes=total_uncompressed,member_bodies_read=False,member_decode=False,groups=groups,patient_identity='UNVERIFIED')
    raw=json.dumps(result,ensure_ascii=True).encode()
    if len(raw)>limits['max_summary_output_bytes']:raise ValueError('SUMMARY_LIMIT')
    with os.fdopen(exclusive(summary),'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    publish(listing,output/'inventory.jsonl');publish(summary,output/'summary.json')
    return {k:v for k,v in result.items() if k!='groups'}


def acquire(config, fake_argv=None, free_fn=None):
    start=time.monotonic();deadline=start+config['phase_time_caps_seconds']['overall_including_stopping']
    dest=Path(config['destination']);part=Path(config['temporary_destination']);secure_parent(part)
    resume=config.get('resume_plan',{})
    offset=resume.get('offset_bytes',0) if resume.get('enabled') is True else 0
    if type(offset) is not int or offset<0 or offset>config['file']['compressed_bytes']:
        raise ValueError('RESUME_OFFSET')
    if offset==config['file']['compressed_bytes'] and resume.get('finalize_only') is not True:
        raise ValueError('FINALIZE_ONLY_NOT_BOUND')
    if dest.exists() or dest.is_symlink() or part.is_symlink():raise ValueError('EXISTING_DESTINATION')
    if not offset and part.exists():raise ValueError('EXISTING_DESTINATION')
    disk=config['disk_plan'];floor=disk['reserve_bytes']+disk['technical_metadata_budget_bytes']
    free_fn=free_fn or (lambda p: os.statvfs(p).f_bavail*os.statvfs(p).f_frsize)
    if free_fn(part.parent)<floor+config['file']['compressed_bytes']-offset:raise RuntimeError('PREFLIGHT_DISK_RESERVE')
    if time.monotonic()-start>config['phase_time_caps_seconds']['preflight']:raise TimeoutError('PREFLIGHT_TIMEOUT')
    if offset:
        before=part.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size!=offset:raise ValueError('RESUME_PART_IDENTITY')
        fd=os.open(part,(os.O_RDONLY if offset==config['file']['compressed_bytes'] else os.O_WRONLY)|os.O_NOFOLLOW)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            actual=os.fstat(fd)
            if (actual.st_dev,actual.st_ino,actual.st_size)!=(before.st_dev,before.st_ino,offset):
                raise ValueError('RESUME_PART_IDENTITY')
            os.lseek(fd,offset,os.SEEK_SET)
        except BaseException:
            os.close(fd);raise
    else:fd=exclusive(part)
    receipt={'status':'FAILED','phases':{},'member_decode':False,'model_calls':0,'resume_offset_bytes':offset}
    caps=config['phase_time_caps_seconds']
    try:
        if offset<config['file']['compressed_bytes']:
            receipt['phases']['transfer']=phase(transfer,(fd,config['file']['compressed_bytes'],config['transfer_plan'],fake_argv,offset),caps['transfer'],deadline,part.parent,floor,free_fn)
        else:
            receipt['phases']['transfer']={'bytes':0,'archive_bytes':offset,'resume_offset_bytes':offset,
                                           'range_response_verified':False,'finalize_only':True,'attempts':0}
        os.close(fd);fd=None
        receipt['phases']['integrity']=phase(integrity,(part,config['file']['compressed_bytes'],config['file']['expected_md5']),caps['integrity_md5_sha256'],deadline,part.parent,floor,free_fn)
        try:
            receipt['phases']['directory']=phase(directory,(part,config['directory_plan']['output_destination'],config['directory_plan']),caps['technical_directory'],deadline,part.parent,floor,free_fn)
        except Exception:
            receipt['directory_status']='INCOMPLETE_NOT_READY';raise
        if time.monotonic()>deadline-12:raise TimeoutError('FINALIZATION_DEADLINE')
        phase(publish,(part,dest),caps['finalization'],deadline,part.parent,floor,free_fn)
        receipt['phases']['finalization']='PUBLISHED_NO_CLOBBER_SAME_INODE'
        receipt['status']='OPAQUE_CONTAINER_AND_TECHNICAL_DIRECTORY_COMPLETE'
        return receipt
    except Exception as exc:
        receipt['failure']=type(exc).__name__+':'+str(exc)[:160]
        return receipt
    finally:
        if fd is not None:os.close(fd)
        receipt['elapsed_seconds']=time.monotonic()-start


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--request',required=True);parser.add_argument('--request-sha256',required=True)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--approval');parser.add_argument('--approval-sha256')
    args=parser.parse_args();request=bound_json(args.request,args.request_sha256);config=next(r for r in request['requests'] if r['id']=='A0')
    file=config['file']
    if file['source_url']!=SOURCE or file['file_id']!=26069987 or file['compressed_bytes']!=SIZE or file['expected_md5']!=MD5:raise ValueError('SCOPE_MISMATCH')
    if config['entrypoint']['source_sha256']!=digest_bytes(Path(__file__).read_bytes()):raise ValueError('SOURCE_HASH_MISMATCH')
    if Path(config['temporary_destination'])!=Path(config['destination']+'.part'):raise ValueError('PART_PATH_MISMATCH')
    if Path(config['directory_plan']['output_destination']).parent!=Path(config['destination']).parent:raise ValueError('DIRECTORY_PATH_MISMATCH')
    if not args.execute:
        print(json.dumps({'status':'CHECK_ONLY_NO_NETWORK_NO_FILES','request_sha256':args.request_sha256,'source_sha256':digest_bytes(Path(__file__).read_bytes())}));return
    if not args.approval or not args.approval_sha256:raise ValueError('EXACT_APPROVAL_REQUIRED')
    approval=bound_json(args.approval,args.approval_sha256)
    expected={'request_sha256':args.request_sha256,'file_id':26069987,'permit_download_opaque_container':True,'permit_directory_metadata':True,'permit_member_decode':False,'permit_model':False,'source_sha256':digest_bytes(Path(__file__).read_bytes())}
    resume=config.get('resume_plan',{})
    if resume.get('enabled') is True:
        expected.update(permit_resume=True,resume_offset_bytes=resume.get('offset_bytes'))
        if resume.get('offset_bytes')==file['compressed_bytes']:
            expected.update(permit_finalize_full_archive=True)
    if any(type(approval.get(k)) is not type(v) or approval.get(k)!=v for k,v in expected.items()):raise ValueError('APPROVAL_SCOPE_MISMATCH')
    # Human approval provenance is supplied by coordinator; these flags never self-authorize.
    try:
        receipt=acquire(config)
    except Exception as exc:
        receipt={'status':'FAILED','phases':{},'failure':type(exc).__name__+':'+str(exc)[:160],
                 'member_decode':False,'model_calls':0}
    receipt.update(request_sha256=args.request_sha256,approval_sha256=args.approval_sha256,source_sha256=digest_bytes(Path(__file__).read_bytes()))
    path=Path(config['destination']).parent/'a0-receipt.json'
    with os.fdopen(exclusive(path),'w') as f:json.dump(receipt,f,indent=2)
    print(json.dumps({'status':receipt['status'],'receipt_path':str(path)}))
    if receipt['status']=='FAILED':raise SystemExit(1)


if __name__=='__main__':main()
