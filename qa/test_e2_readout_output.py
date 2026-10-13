"""Generated cumulative output and pipe tests; never acquire a compute slot."""
import hashlib
import json
import os
import subprocess
from pathlib import Path
import sys
import time
from types import ModuleType

import pytest
from qa import e2_readout_output as output
from qa.next_selected_fidelity_parent import load_supervisor

ROOT=Path(__file__).resolve().parents[1]


def value(tmp):
    source=ROOT/'research/next-hospital-20261014/epi_next/wave1_supervisor.py'
    return dict(supervision_root=str(tmp/'supervision'),output_root=str(tmp/'science'),queue_root=str(tmp/'generated-queue'),
        job_id='generated-output-test',io_lock_source=dict(path=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest()))


def budget(tmp,monkeypatch):
    monkeypatch.setattr(output,'CAP',256*1024);monkeypatch.setattr(output,'RESERVE',64*1024)
    v=value(tmp);Path(v['supervision_root']).mkdir();Path(v['output_root']).mkdir()
    return output.OutputBudget(v)


def test_cumulative_science_failed_residual_supervision_and_slot_charged(tmp_path,monkeypatch):
    b=budget(tmp_path,monkeypatch)
    b.write_new(b.science/'result.json',b'a'*100000)
    b.write_new(b.root/'child-samples.jsonl',b'b'*60000)
    b.slot.mkdir(parents=True);(b.slot/'started.json').write_bytes(b'c'*1000)
    (b.science/'failed.pending').write_bytes(b'd'*12000)
    with pytest.raises(Exception,match='OUTPUT_BYTE_LIMIT'):b.write_new(b.science/'next.json',b'x'*30000)
    assert not (b.science/'next.json').exists()
    b.write_new(b.science/'failure.json',b'{}',terminal=True)
    report=b.final();assert report['retained_bytes_before_audit']>=173002
    b.refresh();assert b.store.size()<256*1024


def test_atomic_old_plus_temporary_peak_is_charged(tmp_path,monkeypatch):
    b=budget(tmp_path,monkeypatch)
    b.write_new(b.root/'telemetry.json',b'a'*100000)
    b.write_new(b.science/'partial.bin',b'b'*60000)
    with pytest.raises(Exception,match='OUTPUT_BYTE_LIMIT'):b.atomic(b.root/'telemetry.json',dict(x='c'*100000))
    assert (b.root/'telemetry.json').read_bytes()==b'a'*100000
    assert not list(b.root.glob('*.tmp'))


def test_native_stdout_stderr_are_drained_bounded_and_failure_recorded(tmp_path,monkeypatch):
    monkeypatch.setattr(output,'LOG_CAP',32768)
    wave,writer,execution=[ModuleType(n) for n in ('generated-wave','generated-writer','generated-execution')]
    for m in (wave,writer,execution):m.write_new=lambda p,b:Path(p).write_bytes(b)
    wave.atomic_json=lambda p,v:Path(p).write_text(json.dumps(v));wave.subprocess=output.subprocess
    wave.SystemMonitor=lambda:type('Monitor',(),dict(processes=lambda self:{},pressure=lambda self:{}))()
    v=value(tmp_path)
    index=json.loads((ROOT/'hospital-release/20261011-recovery-chain-v12/manifest.json').read_bytes())
    execution_lock=load_supervisor(index)['execution_lock']
    with output.bounded_supervisor(v,dict(wave1_supervisor=wave,coordinator_writer=writer,execution_lock=execution)) as (b,monitor):
        os.write(1,b'p'*100000)  # native parent output also belongs to this task
        job=b.root/'job';job.mkdir()
        with (job/'stdout.log').open('xb') as out,(job/'stderr.log').open('xb') as err:
            p=wave.subprocess.Popen([sys.executable,'-c','import sys; sys.stdout.buffer.write(b"x"*200000); sys.stderr.buffer.write(b"y"*100000)'],stdout=out,stderr=err)
            assert isinstance(p, subprocess.Popen)
            slot_dir=b.root/'generated-slot';slot_dir.mkdir()
            slot=execution_lock.DeviceSlot(slot_dir, {'job_id': v['job_id']})
            slot.track_child(p)
            deadline=time.monotonic()+5
            while p.poll() is None:
                assert time.monotonic()<deadline;time.sleep(.01)
        assert p.returncode==0 and b.errors and sum(b.discarded.values())>0
        assert (job/'stdout.log').stat().st_size<=32768 and (job/'stderr.log').stat().st_size<=32768
        with pytest.raises(RuntimeError,match='OUTPUT_LIMIT_STOP'):monitor.pressure()
    report=json.loads((Path(v['supervision_root'])/'output-budget.json').read_bytes())
    assert report['discarded_log_bytes'] and report['cap']==67108864
    assert report['discarded_log_bytes'][str(Path(v['supervision_root'])/'parent-stdout.log')]>0


def test_actual_shared_guard_completion_persists_known_partial_counts(tmp_path):
    # Reuse fixed shared guard in generated directories; no tracked_device_slot call.
    index=json.loads((ROOT/'hospital-release/20261011-recovery-chain-v12/manifest.json').read_bytes())
    modules=load_supervisor(index);wave=modules['wave1_supervisor'];v=value(tmp_path)
    sup=Path(v['supervision_root']);science=Path(v['output_root']);sup.mkdir();science.mkdir()
    directory=sup/v['job_id'];directory.mkdir()
    (directory/'ADMITTED').write_text('{}')
    (directory/'counters.json').write_text(json.dumps(dict(job_id=v['job_id'],forward=2,backward=0,sequence=2,cases={})))
    spec=wave.SupervisionSpec(job_id=v['job_id'],task_key='generated-output-task',device='cpu',owner='INTEGRATION',max_forward=18,max_backward=0,timeout_seconds=120)
    with output.bounded_child(v,modules) as b:
        guard=wave.ChildGuard(directory,spec,time.monotonic())
        b.reporting=True
        guard.complete('FAILED',actual_forward=2,actual_backward=0)
    marker=json.loads((directory/'runner-complete.json').read_bytes())
    assert marker['actual_forward']==2 and marker['actual_backward']==0 and marker['status']=='FAILED'


def test_atomic_replacements_accumulate_without_refund(tmp_path,monkeypatch):
    b=budget(tmp_path,monkeypatch);accepted=0
    with pytest.raises(RuntimeError,match='CUMULATIVE_WRITTEN_BYTE_LIMIT'):
        for _ in range(30):
            b.atomic(b.root/'telemetry.json',dict(x='a'*10000));accepted+=1
    assert 1<accepted<30 and (b.root/'telemetry.json').stat().st_size<11000
    assert b.ledger_value()['cumulative_reserved_bytes']>=accepted*10000


def test_parent_child_instances_share_one_no_reset_ledger(tmp_path,monkeypatch):
    parent=budget(tmp_path,monkeypatch);v=value(tmp_path);child=output.OutputBudget(v)
    parent.write_new(parent.science/'first.json',b'x'*10000)
    before=child.ledger_value()['cumulative_reserved_bytes']
    child.atomic(child.root/'telemetry.json',dict(x='a'*10000))
    assert parent.ledger_value()==child.ledger_value()
    assert parent.ledger_value()['cumulative_reserved_bytes']>before+10000


def test_failed_payload_reservation_is_not_refunded(tmp_path,monkeypatch):
    b=budget(tmp_path,monkeypatch);before=b.ledger_value()['cumulative_reserved_bytes'];target=b.science/'failed.json'
    original=output.os.open
    def broken(path,*args,**kwargs):
        if Path(path)==target:raise OSError('generated write failure')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(output.os,'open',broken)
    with pytest.raises(OSError):b.write_new(target,b'x'*10000)
    assert not target.exists()
    assert b.ledger_value()['cumulative_reserved_bytes']==before+10000+output.LEDGER_WRITE_CHARGE
