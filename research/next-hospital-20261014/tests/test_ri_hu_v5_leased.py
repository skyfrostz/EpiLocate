"""Generated process controls only: no real archive, queue admission or execution."""
import json,os,signal,sys
from pathlib import Path
from epi_next import ri_hu_v5_leased as lease


def child(tmp_path,code,update=None,seconds=3):
    return lease.bounded_child([sys.executable,'-c',code],tmp_path,dict(os.environ),tmp_path,update or (lambda _:None),seconds)


def test_capture_and_normal_exit(tmp_path):
    r=child(tmp_path,"print('generated')")
    assert r['exit_code']==0 and r['stdout']=='generated\n' and r['child_exited']
    assert r['phase_final_state']['status']=='UNKNOWN_NO_PHASE_CHECKPOINT'


def test_capture_limit_during_read(tmp_path):
    events=[]
    r=child(tmp_path,"import os,time;os.write(1,b'x'*1000000);time.sleep(10)",events.append)
    assert r['stdout_bytes']+r['stderr_bytes']<=lease.CAPTURE_LIMIT and r['capture_limit_stop']
    assert any(e.get('capture_limit_stop') for e in events) and r['exit_code']!=0


def test_cooperative_term(tmp_path):
    events=[]
    r=child(tmp_path,"import time;time.sleep(10)",events.append,1)
    assert r['exit_code']==-signal.SIGTERM and any(e.get('cooperative_cli_TERM') for e in events)


def test_hard_stop(tmp_path):
    events=[]
    r=child(tmp_path,"import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(10)",events.append,1)
    assert r['exit_code']==-signal.SIGKILL and any('hard_escalation_phase_state' in e for e in events)
    assert lease.process_identity(next(e['child_pid'] for e in events if 'child_pid' in e)) is None


def test_update_failure_reaps_cli(tmp_path):
    import pytest
    observed=[]
    def fail(e):observed.append(e['child_pid']);raise RuntimeError('generated receipt failure')
    with pytest.raises(RuntimeError):child(tmp_path,"import time;time.sleep(10)",fail,1)
    assert lease.process_identity(observed[0]) is None


def test_identity_gate_never_signals_conflict(monkeypatch,tmp_path):
    identity={'pid':999991,'ppid':7,'pgid':999991,'process_start':'generated'}
    (tmp_path/'stage-checkpoint-v5.json').write_text(json.dumps({'worker_identity':identity}))
    calls=[];monkeypatch.setattr(lease.os,'killpg',lambda *a:calls.append(a))
    assert lease.phase_state(tmp_path,8)['status']=='UNKNOWN_IDENTITY_CONFLICT'
    monkeypatch.setattr(lease,'process_identity',lambda _:dict(identity,process_start='different'))
    assert not lease.stop_owned_phase({'status':'VERIFIED_OWN_WORKER_ALIVE','identity':identity}) and not calls
    assert lease.phase_state(tmp_path,7)['status']=='VERIFIED_ORIGINAL_WORKER_GONE'
    monkeypatch.setattr(lease,'process_identity',lambda _:identity)
    monkeypatch.setattr(lease.time,'sleep',lambda _:None)
    assert lease.stop_owned_phase(lease.phase_state(tmp_path,7))
    assert calls==[(999991,signal.SIGTERM),(999991,signal.SIGKILL)]


def test_exited_cli_with_phase_inherited_pipe(tmp_path):
    import subprocess,time
    events=[]
    worker="import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(10)"
    code=("import subprocess,sys,os,json;from pathlib import Path;"
          f"p=subprocess.Popen([sys.executable,'-c',{worker!r}],start_new_session=True);"
          "birth=subprocess.check_output(['ps','-p',str(p.pid),'-o','lstart='],text=True).strip();"
          "Path('stage-checkpoint-v5.json').write_text(json.dumps({'worker_identity':{'pid':p.pid,'ppid':os.getpid(),'pgid':p.pid,'process_start':birth}}))")
    start=time.monotonic()
    r=child(tmp_path,code,events.append,1)
    assert r['exit_code']==0 and time.monotonic()-start<3
    assert any(e.get('exact_owned_phase_signalled') for e in events)
    identity=json.loads((tmp_path/'stage-checkpoint-v5.json').read_text())['worker_identity']
    # Orphan reaping belongs to init; a zombie is no longer an executing phase.
    state=subprocess.run(['ps','-p',str(identity['pid']),'-o','stat='],capture_output=True,text=True).stdout.strip()
    assert not state or state.startswith('Z')


def test_cleanup_reporting_keeps_primary(monkeypatch,tmp_path):
    import pytest
    events=[]
    def fail_update(e):
        events.append(e)
        if 'child_pid' in e:raise ValueError('generated primary')
    def fail_phase(_):raise RuntimeError('generated cleanup')
    monkeypatch.setattr(lease,'stop_owned_phase',fail_phase)
    with pytest.raises(ValueError):child(tmp_path,"import time;time.sleep(10)",fail_update,1)
    assert any('reporting_error' in e for e in events)
    assert lease.process_identity(events[0]['child_pid']) is None
