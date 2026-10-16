"""Isolated filesystem race/byte-budget tests; no model or real run assets."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import stat
import threading

import numpy as np
import pytest

from epi_next.encoder_volume_runner import PrivateArtifacts, json_bytes


def rename_on_stat(monkeypatch, source, destination, nth):
    original = Path.stat; seen = []
    def injected(path, *args, **kwargs):
        if path == source:
            seen.append(path)
            if len(seen) == nth: os.replace(source, destination)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', injected)
    return seen


def test_legacy_double_stat_reproduces_atomic_rename_filenotfound(tmp_path,monkeypatch):
    directory=tmp_path/'generated';directory.mkdir()
    pending=directory/'telemetry.json.123.456.tmp';pending.write_bytes(b'x'*200)
    final=directory/'telemetry.json';seen=rename_on_stat(monkeypatch,pending,final,2)
    # Exact pre-fix expression retained only in this synthetic reproducer.
    with pytest.raises(FileNotFoundError):
        sum(p.stat().st_size for p in directory.rglob('*') if p.is_file())
    assert len(seen)==2 and final.read_bytes()==b'x'*200


def test_disappearing_tmp_restarts_whole_scan_and_counts_renamed_output(tmp_path,monkeypatch):
    artifacts=PrivateArtifacts(tmp_path/'generated',150)
    pending=artifacts.directory/'telemetry.json.123.456.tmp';pending.write_bytes(b'x'*200)
    final=artifacts.directory/'telemetry.json';rename_on_stat(monkeypatch,pending,final,1)
    with pytest.raises(RuntimeError,match='TASK_OUTPUT_LIMIT'):artifacts.json('next.json',{})
    assert final.stat().st_size==200 and not (artifacts.directory/'next.json').exists()


def test_transient_rename_under_limit_succeeds_without_losing_bytes(tmp_path,monkeypatch):
    artifacts=PrivateArtifacts(tmp_path/'generated',210)
    pending=artifacts.directory/'small.tmp';pending.write_bytes(b'x'*200)
    rename_on_stat(monkeypatch,pending,artifacts.directory/'small.json',1)
    artifacts.check_disk(10)
    with pytest.raises(RuntimeError,match='TASK_OUTPUT_LIMIT'):artifacts.check_disk(11)


def test_each_check_counts_current_complete_scan_without_stability_pair(tmp_path,monkeypatch):
    artifacts=PrivateArtifacts(tmp_path/'generated',100);original=artifacts._disk_snapshot;calls=[]
    def scan():
        result=original();calls.append(1)
        if len(calls)==1:(artifacts.directory/'new.json').write_bytes(b'x'*101)
        return result
    monkeypatch.setattr(artifacts,'_disk_snapshot',scan)
    artifacts.check_disk()
    assert len(calls)==1
    with pytest.raises(RuntimeError,match='TASK_OUTPUT_LIMIT'):artifacts.check_disk()
    assert len(calls)==2  # external writes are observed next check, not an atomic quota


def test_persistent_missing_entry_stops_after_three_attempts_without_writing(tmp_path,monkeypatch):
    artifacts=PrivateArtifacts(tmp_path/'generated',100);calls=[]
    def missing():calls.append(1);raise FileNotFoundError('generated race')
    monkeypatch.setattr(artifacts,'_disk_snapshot',missing)
    with pytest.raises(RuntimeError,match='TASK_OUTPUT_SCAN_UNSTABLE'):artifacts.json('new.json',{})
    assert len(calls)==3 and not (artifacts.directory/'new.json').exists()


def test_complete_scan_does_not_require_two_identical_snapshots(tmp_path,monkeypatch):
    artifacts=PrivateArtifacts(tmp_path/'generated',100);calls=[]
    def changed():
        calls.append(1)
        return {artifacts.directory/'changing':(1,1,stat.S_IFREG,len(calls),0,0)}
    monkeypatch.setattr(artifacts,'_disk_snapshot',changed)
    artifacts.check_disk()
    assert len(calls)==1


def test_permission_error_is_not_swallowed_or_retried(tmp_path,monkeypatch):
    artifacts=PrivateArtifacts(tmp_path/'generated',100);calls=[]
    def denied():calls.append(1);raise PermissionError('generated permission failure')
    monkeypatch.setattr(artifacts,'_disk_snapshot',denied)
    with pytest.raises(PermissionError):artifacts.json('new.json',{})
    assert len(calls)==1 and not (artifacts.directory/'new.json').exists()


@pytest.mark.parametrize('kind',['symlink','fifo'])
def test_nonregular_entries_fail_closed(tmp_path,kind):
    artifacts=PrivateArtifacts(tmp_path/'generated',100)
    if kind=='symlink':
        outside=tmp_path/'outside';outside.write_bytes(b'x'*200)
        (artifacts.directory/'unsafe').symlink_to(outside)
    else:os.mkfifo(artifacts.directory/'unsafe')
    with pytest.raises(RuntimeError,match='TASK_OUTPUT_UNSAFE_ENTRY'):artifacts.check_disk()


def test_complete_scan_counts_nested_and_unpublished_tmp_bytes(tmp_path):
    artifacts=PrivateArtifacts(tmp_path/'generated',50)
    child=artifacts.directory/'nested';child.mkdir()
    (child/'one.tmp').write_bytes(b'x'*30);(artifacts.directory/'two.json').write_bytes(b'x'*20)
    artifacts.check_disk()
    with pytest.raises(RuntimeError,match='TASK_OUTPUT_LIMIT'):artifacts.check_disk(1)


def test_json_budget_uses_exact_pretty_serialization_and_no_partial_write(tmp_path):
    value=[{'values':list(range(20))} for _ in range(100)]
    old_estimate=len(json.dumps(value,allow_nan=False).encode())+4096
    actual=len(json_bytes(value));assert actual>old_estimate
    artifacts=PrivateArtifacts(tmp_path/'reject',old_estimate)
    with pytest.raises(RuntimeError,match='TASK_OUTPUT_LIMIT'):artifacts.json('large.json',value)
    assert not (artifacts.directory/'large.json').exists()
    accepted=PrivateArtifacts(tmp_path/'accept',actual)
    accepted.json('large.json',value)
    assert (accepted.directory/'large.json').read_bytes()==json_bytes(value)


def test_own_concurrent_writers_cannot_double_spend_budget(tmp_path):
    value={'generated':'x'*1000};size=len(json_bytes(value))
    artifacts=PrivateArtifacts(tmp_path/'generated',size);barrier=threading.Barrier(2)
    def worker(name):
        barrier.wait(timeout=2)
        try:artifacts.json(name,value);return 'saved'
        except RuntimeError as exc:return str(exc)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(worker,['a.json','b.json']))
    assert sorted(results)==['TASK_OUTPUT_LIMIT','saved']
    assert sum(p.stat().st_size for p in artifacts.directory.iterdir())==size


@pytest.mark.parametrize('change',['delete','truncate'])
def test_committed_asset_cannot_disappear_from_budget(tmp_path,change):
    artifacts=PrivateArtifacts(tmp_path/'generated',1000)
    artifacts.json('committed.json',{'generated':'x'*100})
    path=artifacts.directory/'committed.json'
    if change=='delete':path.unlink()
    else:path.write_bytes(b'{}')
    with pytest.raises(RuntimeError,match='COMMITTED_ASSET_MISSING_OR_TRUNCATED'):
        artifacts.json('next.json',{})
    assert not (artifacts.directory/'next.json').exists()


def test_generated_numpy_output_records_header_bytes_and_refuses_overwrite(tmp_path):
    artifacts=PrivateArtifacts(tmp_path/'generated',8192)
    value=np.arange(16,dtype=np.float32).reshape(1,1,2,2,4)
    artifacts.array('generated.npy',value)
    path=artifacts.directory/'generated.npy'
    assert artifacts._asset_sizes['generated.npy']==path.stat().st_size>value.nbytes
    assert np.array_equal(np.load(path,allow_pickle=False),value)
    with pytest.raises(FileExistsError):artifacts.array('generated.npy',value)
