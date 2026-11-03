"""Actual generated parent/child lifecycle against the unchanged v12 bundle.

Only generated queues and plain Python processes; no medical assets or models.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from qa import e2_readout_output as output
from qa.next_selected_fidelity_parent import load_supervisor

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT/'hospital-release/20261011-recovery-chain-v12/manifest.json'


def setup(tmp_path, monkeypatch):
    index=json.loads(INDEX.read_bytes());modules=load_supervisor(index)
    wave=modules['wave1_supervisor'];native_monitor=wave.SystemMonitor
    calls=dict(processes=0,pressure=0)
    class Monitor:
        def processes(self):
            calls['processes']+=1
            return native_monitor().processes()
        def pressure(self):
            calls['pressure']+=1
            return dict(free_fraction=.9,swap_used_bytes=0)
    monkeypatch.setattr(wave,'SystemMonitor',Monitor)
    queue=tmp_path/'generated-queue'
    monkeypatch.setattr(modules['hospital_runtime'],'QUEUE_ROOT',queue)
    source=ROOT/'research/next-hospital-20261014/epi_next/wave1_supervisor.py'
    value=dict(supervision_root=str(tmp_path/'supervision'),output_root=str(tmp_path/'science'),
        queue_root=str(queue),job_id='generated-lifecycle',
        io_lock_source=dict(path=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    monkeypatch.setenv('PYTHONPATH',str(ROOT)+os.pathsep+index['bundle_root'])
    return value,index,modules,calls


@pytest.mark.parametrize('mode',['success','early_exit','deadline','unknown_identity','exit_race'])
def test_actual_supervised_generated_lifecycle(tmp_path,monkeypatch,mode):
    value,index,modules,calls=setup(tmp_path,monkeypatch);wave=modules['wave1_supervisor']
    child=tmp_path/'generated_child.py'
    child.write_text("""import sys,time,json
from qa.next_selected_fidelity_parent import load_supervisor
value=json.load(open(sys.argv[2]));index=json.load(open(sys.argv[3]));modules=load_supervisor(index)
from qa.e2_readout_output import bounded_child
wave=modules['wave1_supervisor'];ChildGuard=wave.ChildGuard;StopWork=wave.StopWork
if sys.argv[1] in ('early_exit','unknown_identity','exit_race'):
    time.sleep(.2 if sys.argv[1]=='early_exit' else .5 if sys.argv[1]=='unknown_identity' else 0)
    sys.exit(23)
with bounded_child(value,modules) as budget:
    guard=ChildGuard.from_environment()
    print('generated stdout',flush=True);print('generated stderr',file=sys.stderr,flush=True)
    if sys.argv[1]=='deadline':
        try:
            while True:guard.check();time.sleep(.01)
        except StopWork:
            budget.reporting=True
            guard.complete('PARTIAL_BUDGET',actual_forward=0,actual_backward=0)
    else:
        time.sleep(.1)
        budget.reporting=True
        guard.complete('SUCCESS',actual_forward=0,actual_backward=0)
time.sleep(.15)
""")
    value_path=tmp_path/'value.json';value_path.write_text(json.dumps(value))
    spec=wave.SupervisionSpec(job_id=value['job_id'],task_key='GENERATED-LIFECYCLE',device='cpu',
        owner='INTEGRATION',max_forward=0,max_backward=0,timeout_seconds=.7 if mode=='deadline' else 5,
        telemetry_startup_seconds=2,request_grace_seconds=.1,term_grace_seconds=.1,recovery_seconds=.3)
    start=time.monotonic();processes=[]
    with output.bounded_supervisor(value,modules) as (budget,monitor):
        popen=wave.subprocess.Popen
        def observed(*a,**k):
            p=popen(*a,**k);processes.append(p)
            if mode=='exit_race':
                p.wait(timeout=2)  # deterministic exited child before creation identity check
            return p
        wave.subprocess.Popen=observed
        if mode in {'unknown_identity','exit_race'}:
            native_processes=monitor.processes
            first=True
            def identity_table():
                nonlocal first
                table=native_processes()
                if first and processes:
                    first=False;p=processes[0]
                    if mode=='unknown_identity':table.pop(p.pid,None)
                    else:table[p.pid]=dict(pid=p.pid,ppid=os.getpid(),pgid=p.pid,rss_bytes=0,start='generated-stale',state='S')
                return table
            monitor.processes=identity_table
        receipt=wave.run_supervised(spec,[sys.executable,str(child),mode,str(value_path),str(INDEX)],value['supervision_root'],
            index['dependency_root'],index['dependency_sha256'],_monitor=monitor)
        assert all(isinstance(p,subprocess.Popen) for p in processes)
    for p in processes:p.wait(timeout=2)  # reap only this generated child, never signal unknown identities
    assert time.monotonic()-start<5
    assert calls['processes'] and calls['pressure']
    directory=Path(value['supervision_root'])/value['job_id']
    assert (directory/'supervisor-receipt.json').exists()
    assert receipt['counters']['forward']==receipt['counters']['backward']==0
    if mode=='success':
        assert receipt['status']=='SUCCESS' and receipt['slot_completed']
        assert receipt['runner_actual_counts']==dict(forward=0,backward=0)
        assert 'generated stdout' in (directory/'stdout.log').read_text()
        assert 'generated stderr' in (directory/'stderr.log').read_text()
    elif mode=='early_exit':
        assert receipt['status']=='FAILED' and receipt['slot_completed']
        assert receipt['reason']=='RUNNER_FAILURE_OR_MISSING_COMPLETION'
        assert receipt['runner_actual_counts'] is None
    elif mode=='deadline':
        assert receipt['status']=='PARTIAL_BUDGET' and receipt['slot_completed']
        assert receipt['reason']=='GLOBAL_DEADLINE'
    elif mode=='unknown_identity':
        assert receipt['status']=='BLOCKED' and not receipt['slot_completed']
        assert receipt['runner_actual_counts'] is None and not (directory/'ADMITTED').exists()
        assert not any(e['kind'] in {'STOP_REQUEST_SIGNAL','FAIL_CLOSED_SIGNAL'} for e in receipt['events'])
    else:
        assert receipt['reason']=='MONITOR_FAILURE_ProcessLookupError'
        assert receipt['runner_actual_counts'] is None and not (directory/'ADMITTED').exists()
    (tmp_path/'verification.json').write_text(json.dumps(dict(mode=mode,status=receipt['status'],
        reason=receipt['reason'],slot_completed=receipt['slot_completed'],callbacks=calls,
        durable=receipt['counters'],actual=receipt['runner_actual_counts'],medical_calls=0),indent=2))


def test_inherited_pipe_does_not_block_poll_and_drains_stop(tmp_path,monkeypatch):
    value,index,modules,calls=setup(tmp_path,monkeypatch)
    wave=modules['wave1_supervisor'];owned=[]
    with output.bounded_supervisor(value,modules) as (budget,monitor):
        with (budget.root/'stdout.log').open('xb') as out,(budget.root/'stderr.log').open('xb') as err:
            # This explicitly created fixture owns the inherited pipes for one second.
            code='import subprocess,sys; subprocess.Popen([sys.executable,"-c","import time; time.sleep(1)"],start_new_session=True); print("root-exit",flush=True)'
            p=wave.subprocess.Popen([sys.executable,'-c',code],stdout=out,stderr=err);owned.append(p)
            p.wait(timeout=2)
            deadline=time.monotonic()+2;latencies=[]
            while True:
                before=time.monotonic();result=p.poll();latencies.append(time.monotonic()-before)
                monitor.processes()
                if result is not None:break
                assert time.monotonic()<deadline
                time.sleep(.01)
            assert max(latencies)<.1
            assert 'CHILD_LOG_DRAIN_TIMEOUT' in budget.errors
            assert all(not t.is_alive() for t in p._e2_drain_threads)
            with pytest.raises(RuntimeError,match='OUTPUT_LIMIT_STOP'):monitor.pressure()
        assert 'root-exit' in (budget.root/'stdout.log').read_text()
    # The fixture descendant has a fixed self-exit; never signal an untracked process.
    time.sleep(1)
    assert calls['processes']>2


def test_shared_tracking_rejects_proxy_and_disappeared_identity(tmp_path,monkeypatch):
    _,_,modules,_=setup(tmp_path,monkeypatch);execution=modules['execution_lock']
    slot=execution.DeviceSlot(tmp_path,dict(job_id='generated'))
    with pytest.raises(ValueError,match='LIVE_TASK_OWNED_CHILD_REQUIRED'):
        slot.track_child(SimpleNamespace(pid=os.getpid(),poll=lambda:None))
    p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(.2)'])
    try:
        def absent(*_):raise ProcessLookupError('generated vanished identity')
        monkeypatch.setattr(execution,'process_identity',absent)
        with pytest.raises(ProcessLookupError):slot.track_child(p)
        assert not slot.children and not list(tmp_path.glob('child-*.json'))
    finally:p.wait(timeout=2)
