"""Isolated generated reproduction; no queues, medical imports, model calls."""
import os
from pathlib import Path
import threading
import pytest
from epi_next import wave1_supervisor as supervisor


# Verbatim old BoundedStore.size body, isolated from its torch imports.
# Deterministic os.walk -> rename -> stat interleaving from the incident.
def old_size(root):
    total=0
    for folder,dirs,files in os.walk(root,followlinks=False):
        for name in (*dirs,*files):
            p=Path(folder)/name
            if p.is_symlink():raise ValueError('OUTPUT_SYMLINK_REFUSED')
        total+=sum((Path(folder)/name).stat().st_size for name in files)
    return total


LEGACY_SOURCE = """def atomic_json(path, value):
    temporary = path.with_name(path.name + f'.{os.getpid()}.{threading.get_ident()}.tmp')
    with temporary.open('xb') as stream:
        stream.write(canonical_json(value)); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path); fsync_dir(path.parent)
"""
legacy_namespace = {'os': os, 'threading': threading,
                    'canonical_json': supervisor.canonical_json, 'fsync_dir': supervisor.fsync_dir}
exec(compile(LEGACY_SOURCE, '<original-v3-atomic-json>', 'exec'), legacy_namespace)
legacy_atomic_json = legacy_namespace['atomic_json']


def test_original_writer_reader_race_deterministically_reproduced(tmp_path,monkeypatch):
    prepared=threading.Event();replace=threading.Event();done=threading.Event();errors=[]
    real_replace=os.replace;real_stat=Path.stat
    def paused_replace(src,dst):
        prepared.set();assert replace.wait(2);real_replace(src,dst)
    monkeypatch.setattr(os,'replace',paused_replace)
    def writer():
        try:legacy_atomic_json(tmp_path/'telemetry.json',{'scalar':1})
        except BaseException as exc:errors.append(exc)
        finally:done.set()
    t=threading.Thread(target=writer);t.start();assert prepared.wait(2)
    def stat_after_replace(path,*args,**kw):
        # is_symlink uses lstat, while old size sums Path.stat.
        if path.name.endswith('.tmp') and not kw.get('follow_symlinks') is False:
            replace.set();assert done.wait(2)
        return real_stat(path,*args,**kw)
    monkeypatch.setattr(Path,'stat',stat_after_replace)
    try:
        with pytest.raises(FileNotFoundError,match='telemetry.json'):old_size(tmp_path)
    finally:replace.set();t.join(2)
    assert not errors and not t.is_alive()
    assert (tmp_path/'telemetry.json').exists()


def test_new_accounting_waits_for_writer_replace(tmp_path,monkeypatch):
    prepared=threading.Event();release=threading.Event();scanned=threading.Event();attempt=threading.Event();errors=[];sizes=[]
    real_replace=os.replace
    def paused_replace(src,dst):
        prepared.set();assert release.wait(2);real_replace(src,dst)
    monkeypatch.setattr(os,'replace',paused_replace)
    def writer():
        try:supervisor.atomic_json(tmp_path/'telemetry.json',{'scalar':1})
        except BaseException as exc:errors.append(exc)
    def reader():
        attempt.set()
        try:sizes.append(supervisor.supervisor_output_size(tmp_path,timeout_seconds=1))
        except BaseException as exc:errors.append(exc)
        finally:scanned.set()
    t=threading.Thread(target=writer);t.start();assert prepared.wait(2)
    r=threading.Thread(target=reader);r.start();assert attempt.wait(2)
    try:
        assert not scanned.wait(.02)
    finally:release.set();t.join(2);r.join(2)
    assert not errors and not t.is_alive() and not r.is_alive()
    assert sizes==[len(supervisor.canonical_json({'scalar':1}))]


def test_retained_temps_charged_and_symlinks_rejected(tmp_path):
    (tmp_path/'telemetry.json.1.1.tmp').write_bytes(b'x'*17)
    assert supervisor.supervisor_output_size(tmp_path)==17
    (tmp_path/'alias').symlink_to(tmp_path/'telemetry.json.1.1.tmp')
    with pytest.raises(ValueError,match='OUTPUT_SYMLINK'):supervisor.supervisor_output_size(tmp_path)


def test_lock_timeout_never_becomes_zero_bytes(tmp_path):
    with supervisor.supervisor_output_lock(tmp_path):
        with pytest.raises(TimeoutError,match='OUTPUT_LOCK_TIMEOUT'):
            supervisor.supervisor_output_size(tmp_path,timeout_seconds=.01)


def test_reader_walk_errors_fail_closed(tmp_path,monkeypatch):
    def failed_walk(root,**kw):
        kw['onerror'](PermissionError('fixture unreadable'));yield
    monkeypatch.setattr(os,'walk',failed_walk)
    with pytest.raises(PermissionError):supervisor.supervisor_output_size(tmp_path)


@pytest.mark.parametrize('timeout', [0, -1, True, float('nan'), float('inf')])
def test_invalid_io_lock_timeout_refused(tmp_path, timeout):
    with pytest.raises(ValueError, match='FINITE_IO_LOCK_TIMEOUT'):
        supervisor.supervisor_output_size(tmp_path, timeout_seconds=timeout)
