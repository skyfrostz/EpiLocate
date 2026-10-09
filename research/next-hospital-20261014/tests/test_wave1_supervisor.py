import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from epi_next import hospital_runtime
from epi_next.artifacts import canonical_json
from epi_next.wave1_supervisor import (ChildGuard, SupervisionSpec, StopWork,
                                       SystemMonitor, run_supervised, owned_group, GIB)
from epi_next.execution_lock import dependency_snapshot


def locked_source(tmp_path):
    repo=tmp_path/'repo';repo.mkdir();source=Path(__file__).parents[1]/'epi_next'
    names=['wave1_supervisor.py','execution_lock.py','coordinator_writer.py','artifacts.py',
           'hospital_runtime.py','hospital_contract.py','contracts.py','geometry.py']
    for name in names:(repo/name).write_bytes((source/name).read_bytes())
    subprocess.run(['git','init','-q',str(repo)],check=True)
    subprocess.run(['git','add','.'],cwd=repo,check=True)
    subprocess.run(['git','-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture'],cwd=repo,check=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    from epi_next.artifacts import sha256
    entries=[{'name':name,'repo':str(repo),'relative_path':name,'commit':commit,'sha256':sha256((repo/name).read_bytes())} for name in names]
    import importlib.metadata
    root=tmp_path/'dependencies';digest=dependency_snapshot(root,'EPI-NEXT-fixture-dependencies',entries,{'numpy':importlib.metadata.version('numpy')})
    return root/'EPI-NEXT-fixture-dependencies',digest,repo,entries


class Monitor(SystemMonitor):
    def __init__(self, mode='normal'):self.mode=mode;self.reads=0
    def pressure(self):
        self.reads+=1
        return {'free_fraction':.5 if self.mode!='pressure' or self.reads<5 else .1,
                'free_bytes':4*GIB,'total_bytes':8*GIB,
                'swap_used_bytes':2*GIB if self.mode=='swap' and self.reads>=5 else 0}
    def processes(self):
        table=super().processes()
        if self.mode=='failure' and self.reads>=5:raise RuntimeError('injected monitor fault')
        if self.mode=='rss' and self.reads>=5:
            for record in table.values():
                if record['ppid']==os.getpid():record['rss_bytes']=5*GIB
        return table


def run(tmp_path,monkeypatch,body,*,mode='normal',device='cpu',timeout=2.,case=None):
    dependency,digest,_,_=locked_source(tmp_path)
    monkeypatch.setattr(hospital_runtime,'QUEUE_ROOT',tmp_path/'queue')
    command=[sys.executable,'-c',body]
    spec=SupervisionSpec('fixture-job','fixture-task',device,'ENCODER' if device=='mps' else 'DATA',
                         2,1,timeout,per_case_seconds=case,telemetry_startup_seconds=.5,
                         telemetry_max_gap_seconds=.25,request_grace_seconds=.05,term_grace_seconds=.1,recovery_seconds=.1)
    return run_supervised(spec,command,tmp_path/'outputs',dependency,digest,_monitor=Monitor(mode))


IMPORT='from epi_next.wave1_supervisor import ChildGuard, StopWork\nfrom pathlib import Path\nimport time, signal\ng=ChildGuard.from_environment()\n'


def test_data_zero_model_calls_and_preserved_asset(tmp_path,monkeypatch):
    body=IMPORT+"(g.directory/'partial.json').write_text('{}')\ng.complete(actual_forward=0,actual_backward=0)\n"
    result=run(tmp_path,monkeypatch,body)
    assert result['status']=='SUCCESS' and result['slot_completed']
    assert result['runner_actual_counts']=={'forward':0,'backward':0}
    assert 'partial.json' in result['asset_hashes'] and result['counters']['forward']==0


@pytest.mark.parametrize('mode,reason',[('rss','RSS_PRESTOP'),('swap','SWAP_GROWTH_PRESTOP'),('pressure','SYSTEM_FREE_PRESTOP')])
def test_sampled_pre_stop_preserves_partial_and_own_exit(tmp_path,monkeypatch,mode,reason):
    body=IMPORT+"(g.directory/'partial.json').write_text('{}')\ntry:\n while True: g.check();time.sleep(.01)\nexcept StopWork: g.complete('PARTIAL_BUDGET',actual_forward=0,actual_backward=0)\n"
    result=run(tmp_path,monkeypatch,body,mode=mode)
    assert result['reason']==reason and result['exit_monotonic'] is not None
    assert result['status'] in {'PARTIAL_BUDGET','BLOCKED'}
    assert 'partial.json' in result['asset_hashes']


def test_loading_deadline_and_bounded_own_kill(tmp_path,monkeypatch):
    body="import signal,time\nsignal.signal(signal.SIGUSR1,signal.SIG_IGN)\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\ntime.sleep(10)\n"
    result=run(tmp_path,monkeypatch,body,timeout=.1)
    assert result['reason']=='GLOBAL_DEADLINE' and result['exit_monotonic'] is not None
    assert any(e['kind']=='KILL_REQUEST' for e in result['events'])
    assert result['slot_completed']


def test_missing_mps_or_monitor_fault_is_fail_closed(tmp_path,monkeypatch):
    body=IMPORT+"try:\n while True: g.check();time.sleep(.01)\nexcept StopWork: g.complete('PARTIAL_BUDGET',actual_forward=0,actual_backward=0)\n"
    result=run(tmp_path,monkeypatch,body,device='mps')
    assert result['reason']=='MPS_DRIVER_MISSING' and not result['slot_completed']
    slots=tmp_path/'queue'/'slots'/'fixture-job';assert not (slots/'finished.json').exists()


def test_monitor_failure_stops_group_and_retains_evidence(tmp_path,monkeypatch):
    body=IMPORT+"try:\n while True: g.check();time.sleep(.01)\nexcept StopWork: g.complete('PARTIAL_BUDGET',actual_forward=0,actual_backward=0)\n"
    result=run(tmp_path,monkeypatch,body,mode='failure')
    assert result['reason'].startswith('MONITOR_FAILURE') and result['exit_monotonic'] is not None
    assert result['asset_hashes'] and any(e['kind']=='MONITOR_EXCEPTION' for e in result['events'])


def test_global_attempt_counter_no_reset_and_stop_fences_work(tmp_path):
    spec=SupervisionSpec('job','task','cpu','DATA',1,0,2)
    (tmp_path/'ADMITTED').write_text('{}')
    (tmp_path/'counters.json').write_bytes(canonical_json({'job_id':'job','forward':0,'backward':0,'sequence':0,'cases':{}}))
    g=ChildGuard(tmp_path,spec,time.monotonic());g.before_forward();g.close()
    g=ChildGuard(tmp_path,spec,time.monotonic())
    with pytest.raises(StopWork,match='CALL_BUDGET'):g.before_forward()
    (tmp_path/'STOP').write_text('{}')
    with pytest.raises(StopWork,match='STOP_REQUESTED'):g.before_backward()
    g.close();assert json.loads((tmp_path/'counters.json').read_bytes())['forward']==1


def test_identity_change_never_authorizes_foreign_group_signal():
    class Process:pid=123
    Process.poll=lambda self:None
    with pytest.raises(RuntimeError,match='IDENTITY_CHANGED'):
        owned_group({123:{'pid':123,'pgid':123,'start':'other'}},Process(),{'start':'original'})


def test_global_unknown_cpu_slot_blocks_mps(tmp_path,monkeypatch):
    monkeypatch.setattr(hospital_runtime,'QUEUE_ROOT',tmp_path/'queue')
    slot=tmp_path/'queue'/'slots'/'cpu-unknown';slot.mkdir(parents=True)
    with pytest.raises(RuntimeError,match='GLOBAL_UNKNOWN'):
        run_supervised(SupervisionSpec('next','task','mps','ENCODER',1,0,1),['unused'],tmp_path,Path('unused'),'unused')


def test_case_deadline_is_not_reset(tmp_path,monkeypatch):
    body=IMPORT+"g.begin_case('one')\ntry:\n while True:g.check();time.sleep(.01)\nexcept StopWork:\n (g.directory/'partial.json').write_text('{}')\n g.complete('PARTIAL_BUDGET',actual_forward=0,actual_backward=0)\n"
    result=run(tmp_path,monkeypatch,body,case=.1)
    assert result['status']=='PARTIAL_BUDGET'
    assert result['counters']['cases']['one']>=result['started_monotonic']


def test_real_child_mps_samples_and_recovery_marker_without_mps_compute(tmp_path,monkeypatch):
    body="from epi_next.wave1_supervisor import ChildGuard\ng=ChildGuard.from_environment(mps_driver=lambda:{'driver_bytes':123,'tensor_bytes':0})\ng.complete('NO_RELIABLE_RESPONSE',device_recovered=True,actual_forward=0,actual_backward=0)\n"
    result=run(tmp_path,monkeypatch,body,device='mps')
    assert result['status']=='NO_RELIABLE_RESPONSE' and result['slot_completed']
    assert any(s.get('mps_driver_bytes')==123 for s in result['samples'])


def test_group_termination_does_not_touch_unrelated_owned_fixture(tmp_path,monkeypatch):
    unrelated=subprocess.Popen([sys.executable,'-c','import time;time.sleep(2)'],start_new_session=True)
    try:
        result=run(tmp_path,monkeypatch,"import time;time.sleep(10)",timeout=.1)
        assert result['exit_monotonic'] is not None and unrelated.poll() is None
    finally:
        unrelated.terminate();unrelated.wait(timeout=2)


def test_zero_model_slot_and_duplicate_scope_cannot_reset_budget(tmp_path,monkeypatch):
    dependency,digest,_,_=locked_source(tmp_path)
    monkeypatch.setattr(hospital_runtime,'QUEUE_ROOT',tmp_path/'queue')
    spec=SupervisionSpec('zero','label-scope','cpu','DATA',0,0,2)
    body=IMPORT+"g.complete(actual_forward=0,actual_backward=0)\n"
    result=run_supervised(spec,[sys.executable,'-c',body],tmp_path/'outputs',dependency,digest,_monitor=Monitor())
    assert result['status']=='SUCCESS' and result['counters']['forward']==0
    slot=json.loads((tmp_path/'queue/slots/zero/started.json').read_bytes())
    assert slot['resource_limits']['max_model_calls']==0
    with pytest.raises(RuntimeError,match='DUPLICATE_TASK_SCOPE'):
        run_supervised(SupervisionSpec('other','label-scope','cpu','DATA',0,0,2),['unused'],tmp_path/'outputs',dependency,digest)


def test_serial_lock_applies_across_devices(tmp_path,monkeypatch):
    import fcntl
    monkeypatch.setattr(hospital_runtime,'QUEUE_ROOT',tmp_path)
    with (tmp_path/'wave1.serial.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(RuntimeError,match='SERIAL_SLOT_BUSY'):
            run_supervised(SupervisionSpec('next','task','mps','ENCODER',1,0,1),['unused'],tmp_path,Path('unused'),'unused')


def test_independent_bundle_imports_never_borrow_loaded_epi_next(tmp_path):
    bundle=tmp_path/'epinext_wave1_supervisor_v1';bundle.mkdir()
    source=Path(__file__).parents[1]/'epi_next'
    names=['__init__.py','wave1_supervisor.py','execution_lock.py','coordinator_writer.py','artifacts.py',
           'hospital_runtime.py','hospital_contract.py','contracts.py','geometry.py']
    for name in names:(bundle/name).write_bytes((source/name).read_bytes())
    code="import epi_next.wave1_supervisor;import epinext_wave1_supervisor_v1.wave1_supervisor;import sys,json;print(json.dumps({k:v.__file__ for k,v in sys.modules.items() if k.startswith('epinext_wave1_supervisor_v1') and hasattr(v,'__file__')}))"
    env=dict(os.environ,PYTHONPATH=str(tmp_path)+os.pathsep+os.environ['PYTHONPATH'])
    result=subprocess.run([sys.executable,'-c',code],env=env,text=True,capture_output=True)
    assert result.returncode==0,result.stderr
    files=json.loads(result.stdout)
    assert len(files)==9 and all(Path(p).parent==bundle for p in files.values())
