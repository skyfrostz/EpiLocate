"""Generated opaque bytes only; no ZIP member or medical parsing."""
import copy,hashlib,os
from pathlib import Path
import pytest
from epi_next import archive_identity_v2 as identity


def fixture(tmp_path):
    p=tmp_path/'opaque.bin';p.write_bytes(b'generated opaque bytes'*1024)
    return p,hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_size


def test_device_change_accepted_only_after_full_content_scan(tmp_path):
    p,h,n=fixture(tmp_path)
    old_dev=p.stat().st_dev+3  # historical device numbers are not content identity
    r=identity.scan(p,h,n,chunk=1024)
    assert r['before']['dev']!=old_dev and r['sha256']==h and r['bytes_read']==n
    fd,chain=identity.reuse(p,r);os.close(fd)
    assert r['EOF_verified'] and r['before']==r['after']


def test_content_changed_same_size_rejected(tmp_path):
    p,h,n=fixture(tmp_path);p.write_bytes(b'X'*n)
    with pytest.raises(identity.IdentityError,match='CONTENT_MISMATCH'):identity.scan(p,h,n)


def test_cached_receipt_stat_drift_rejected(tmp_path):
    p,h,n=fixture(tmp_path);r=identity.scan(p,h,n);p.write_bytes(b'X'*n)
    with pytest.raises(identity.IdentityError,match='STAT_OR_NAMESPACE'):identity.reuse(p,r)


@pytest.mark.parametrize('parent',[False,True])
def test_symlink_rejected(tmp_path,parent):
    p,h,n=fixture(tmp_path)
    link=tmp_path/'link';link.symlink_to(tmp_path if parent else p)
    with pytest.raises(identity.IdentityError):identity.scan(link/p.name if parent else link,h,n)


def test_mutation_during_scan_rejected(tmp_path,monkeypatch):
    p,h,n=fixture(tmp_path);original=identity.os.read;once=[]
    def raced(fd,size):
        data=original(fd,size)
        if not once:once.append(True);p.write_bytes(b'Z'*n)
        return data
    monkeypatch.setattr(identity.os,'read',raced)
    with pytest.raises(identity.IdentityError,match='STAT_DRIFT'):identity.scan(p,h,n,chunk=1024)


def test_limits_and_forged_receipt(tmp_path,monkeypatch):
    p,h,n=fixture(tmp_path)
    with pytest.raises(identity.IdentityError,match='CHUNK_LIMIT'):identity.scan(p,h,n,chunk=identity.CHUNK+1)
    with pytest.raises(identity.IdentityError,match='RECEIPT_REQUIRED'):identity.reuse(p,{})
    monkeypatch.setattr(identity,'peak_rss',lambda:identity.RSS+1)
    with pytest.raises(identity.IdentityError,match='RSS_LIMIT'):identity.scan(p,h,n)


def test_timeout_fails_no_rescan(tmp_path,monkeypatch):
    p,h,n=fixture(tmp_path);times=iter([0,121,122])
    monkeypatch.setattr(identity.time,'monotonic',lambda:next(times))
    with pytest.raises(identity.IdentityError,match='WALL_LIMIT') as e:identity.scan(p,h,n)
    assert e.value.evidence['bytes_read']==0
