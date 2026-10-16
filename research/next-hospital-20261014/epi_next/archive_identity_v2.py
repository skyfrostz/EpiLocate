"""One opaque sequential SHA256 scan and strict reuse of its bound receipt.
No ZIP parsing, decompression, HTTP, medical arrays or model imports.
"""
import hashlib
import os
from pathlib import Path
import resource
import signal
import stat
import sys
import time

CHUNK = 8 * 1024**2
WALL = 120
RSS = 512 * 1024**2


class IdentityError(ValueError):
    def __init__(self, code, evidence=None):
        super().__init__(code);self.evidence=evidence


def state(s):
    return {k:getattr(s,'st_'+k) for k in
            ('dev','ino','size','mtime_ns','ctime_ns','mode','nlink')}


def secure_open(path):
    """Walk absolute directory FDs with O_NOFOLLOW; never follow parent links."""
    p=Path(path)
    if not p.is_absolute() or '..' in p.parts:raise IdentityError('UNSAFE_PATH')
    directory=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    chain=[];prefix=Path('/')
    try:
        chain.append({'path':'/','dev':os.fstat(directory).st_dev,'ino':os.fstat(directory).st_ino})
        for name in p.parts[1:-1]:
            nxt=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
            os.close(directory);directory=nxt;prefix=prefix/name;s=os.fstat(directory)
            chain.append({'path':str(prefix),'dev':s.st_dev,'ino':s.st_ino})
        fd=os.open(p.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
        if not stat.S_ISREG(os.fstat(fd).st_mode):os.close(fd);raise IdentityError('NOT_REGULAR')
        return fd,chain
    except OSError as exc:raise IdentityError('UNSAFE_OR_CHANGED_PATH') from exc
    finally:os.close(directory)


def namespace(path,expected,chain):
    for c in chain:
        s=Path(c['path']).lstat()
        if stat.S_ISLNK(s.st_mode) or (s.st_dev,s.st_ino)!=(c['dev'],c['ino']):
            raise IdentityError('PARENT_NAMESPACE_DRIFT')
    s=Path(path).lstat()
    if stat.S_ISLNK(s.st_mode) or state(s)!=expected:raise IdentityError('PATH_STAT_DRIFT')


def peak_rss():
    n=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return n if sys.platform=='darwin' else n*1024


def scan(path,expected_sha256,expected_bytes, *, chunk=CHUNK):
    if not 0<chunk<=CHUNK:raise IdentityError('CHUNK_LIMIT')
    start=time.monotonic();fd=None
    result={'schema':'OPAQUE_ARCHIVE_IDENTITY_V2','status':'FAILED','path':str(Path(path)),
            'expected_sha256':expected_sha256,'expected_bytes':expected_bytes,'bytes_read':0,
            'EOF_verified':False,'sequential_passes':1,'decompression_calls':0,
            'label_parse_calls':0,'pixel_parse_calls':0,'model_calls':0,
            'caps':{'CPU_threads':1,'chunk_bytes':chunk,'wall_seconds':WALL,'RSS_bytes':RSS}}
    previous=signal.getsignal(signal.SIGALRM)
    def alarm(*_):raise IdentityError('IDENTITY_WALL_LIMIT')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,WALL)
    try:
        fd,chain=secure_open(path);before=state(os.fstat(fd));result['before']=before
        result['path_chain']=chain;namespace(path,before,chain)
        result['path_lstat_before']=state(Path(path).lstat())
        if result['path_lstat_before']!=before:raise IdentityError('PATH_STAT_DRIFT')
        if before['size']!=expected_bytes:raise IdentityError('IDENTITY_SIZE_MISMATCH')
        digest=hashlib.sha256()
        while True:
            if time.monotonic()-start>WALL:raise IdentityError('IDENTITY_WALL_LIMIT')
            if peak_rss()>RSS:raise IdentityError('IDENTITY_RSS_LIMIT')
            raw=os.read(fd,chunk)
            if not raw:result['EOF_verified']=True;break
            result['bytes_read']+=len(raw)
            if result['bytes_read']>expected_bytes:raise IdentityError('IDENTITY_SIZE_EXCEEDED')
            digest.update(raw)
            if state(os.fstat(fd))!=before:raise IdentityError('FD_STAT_DRIFT_DURING_SCAN')
        result['after']=state(os.fstat(fd));namespace(path,result['after'],chain)
        result['path_lstat_after']=state(Path(path).lstat())
        if result['path_lstat_after']!=result['after']:raise IdentityError('PATH_STAT_DRIFT')
        if result['after']!=before:raise IdentityError('FD_STAT_DRIFT_AFTER_SCAN')
        result['sha256']=digest.hexdigest()
        if result['bytes_read']!=expected_bytes or result['sha256']!=expected_sha256:
            raise IdentityError('ARCHIVE_CONTENT_MISMATCH')
        result['status']='CONTENT_IDENTITY_VERIFIED_STABLE_STAT'
        return result
    except Exception as exc:
        result['error']=str(exc) if isinstance(exc,IdentityError) else 'IDENTITY_IO_FAILURE'
        raise IdentityError(result['error'],result) from exc
    finally:
        result['elapsed_seconds']=time.monotonic()-start;result['peak_RSS_bytes']=peak_rss()
        if fd is not None:os.close(fd)
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)


def reuse(path,receipt):
    """No new content scan: any drift from the verified fresh stat stops."""
    if (receipt.get('status')!='CONTENT_IDENTITY_VERIFIED_STABLE_STAT'
            or receipt.get('EOF_verified') is not True
            or receipt.get('bytes_read')!=receipt.get('expected_bytes')
            or receipt.get('sha256')!=receipt.get('expected_sha256')
            or receipt.get('before')!=receipt.get('after')
            or str(Path(path))!=receipt.get('path')):
        raise IdentityError('VERIFIED_IDENTITY_RECEIPT_REQUIRED')
    fd,chain=secure_open(path)
    try:
        current=state(os.fstat(fd))
        if current!=receipt['after'] or chain!=receipt['path_chain']:
            raise IdentityError('VERIFIED_STAT_OR_NAMESPACE_DRIFT')
        namespace(path,current,chain)
        return fd,chain  # caller owns FD and keeps it until all reads finish
    except BaseException:os.close(fd);raise
