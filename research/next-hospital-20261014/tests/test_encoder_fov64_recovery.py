"""Recovery adapter only: generated JSON/fake supervisor, zero model calls."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from epi_next import encoder_fov64_recovery as recovery


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value))
    return dict(path=str(path),digest=recovery.pair.file_sha(path))


def test_default_refuses_before_readiness_or_any_assets(monkeypatch,capsys):
    monkeypatch.setattr(recovery.sys,'argv',['recovery','--config','unused','--config-sha','x',
        '--binding','unused','--binding-sha','x','--command-template','unused','--command-sha','x'])
    monkeypatch.setattr(recovery,'verify_readiness',lambda args:pytest.fail('must refuse first'))
    assert recovery.main()==3
    assert 'CHIEF_DISPATCH_REQUIRED_NO_REAL_ACCESS' in capsys.readouterr().out


def test_bound_metadata_tamper_and_symlink_fail_closed(tmp_path):
    ref=write(tmp_path/'a.json',{'fake':True})
    assert recovery.bound(ref)=={'fake':True}
    Path(ref['path']).write_text('{}')
    with pytest.raises(ValueError,match='SHA'):recovery.bound(ref)
    link=tmp_path/'alias.json';link.symlink_to(ref['path'])
    with pytest.raises(recovery.Blocked,match='UNSAFE'):recovery.bound(dict(path=str(link),digest=ref['digest']))


def test_only_validated_old_exception_and_other_unknown_stays_blocked(tmp_path):
    write(tmp_path/'slots'/'old'/'started.json',dict(job_id='old',task_key='old-task'))
    with pytest.raises(recovery.Blocked,match='OTHER_UNKNOWN'):
        recovery.queue_gate(tmp_path,dict(old_job_id='unrelated'))
    observed=recovery.queue_gate(tmp_path,dict(old_job_id='old'))
    assert observed[0]['historical_status']=='UNKNOWN'
    assert not (tmp_path/'slots'/'old'/'finished.json').exists()
    write(tmp_path/'slots'/'p1'/'started.json',dict(job_id='p1',task_key=recovery.P1_TASK))
    with pytest.raises(recovery.Blocked,match='OTHER_UNKNOWN'):
        recovery.queue_gate(tmp_path,dict(old_job_id='old'))


def test_same_c1_task_cannot_reset_global_budget(tmp_path):
    write(tmp_path/'slots'/'another-job'/'started.json',dict(job_id='another-job',task_key=recovery.pair.TASK))
    with pytest.raises(recovery.Blocked,match='NO_RETRY'):
        recovery.queue_gate(tmp_path,dict(old_job_id='another-job'))


@pytest.fixture
def dispatch_fixture(tmp_path):
    args=SimpleNamespace(config_sha='c'*64,binding_sha='b'*64,command_sha='m'*64,
                         dispatch=tmp_path/'dispatch.json',dispatch_sha=None)
    config=dict(queue_root=str(tmp_path/'queue'),selection=dict(source_input_sha256='i'*64,source_ledger_sha256='l'*64))
    binding=dict(authority_references={'generated':'fixtures'})
    receipt=dict(job_id='p1',task_key=recovery.P1_TASK,status='NO_RELIABLE_RESPONSE',
                 slot_completed=True,exit_monotonic=10.,recovered_monotonic=11.)
    ref=write(tmp_path/'supervisor.json',receipt)
    write(tmp_path/'queue'/'slots'/'p1'/'started.json',dict(job_id='p1',task_key=recovery.P1_TASK))
    write(tmp_path/'queue'/'slots'/'p1'/'finished.json',dict(receipt_path=ref['path'],receipt_sha256=ref['digest']))
    dispatch=dict(recovery.identity(args,binding,config),schema='CTFM_C1_RECOVERY_DISPATCH_V1',
                  status='EXCLUSIVE_C1_AFTER_P1',p1_released_reference=ref)
    args.dispatch_sha=write(args.dispatch,dispatch)['digest']
    return args,binding,config,dispatch,receipt


def test_dispatch_binds_exact_p1_shared_release_and_budget(dispatch_fixture):
    args,binding,config,dispatch,_=dispatch_fixture
    assert recovery.validate_dispatch(args,binding,config)['max_forward']==2
    dispatch['max_forward']=3;args.dispatch_sha=write(args.dispatch,dispatch)['digest']
    with pytest.raises(recovery.Blocked,match='EXACT_RECOVERY'):recovery.validate_dispatch(args,binding,config)


@pytest.mark.parametrize('change',[{'slot_completed':False},{'recovered_monotonic':None},
                                   {'recovered_monotonic':9.},{'task_key':'other-task'}])
def test_dispatch_refuses_unreleased_p1(dispatch_fixture,change):
    args,binding,config,dispatch,receipt=dispatch_fixture;receipt.update(change)
    dispatch['p1_released_reference']=write(Path(dispatch['p1_released_reference']['path']),receipt)
    args.dispatch_sha=write(args.dispatch,dispatch)['digest']
    with pytest.raises(recovery.Blocked,match='P1_NOT_RELEASED'):recovery.validate_dispatch(args,binding,config)


def test_dispatch_cannot_use_receipt_without_matching_queue_terminal(dispatch_fixture):
    args,binding,config,_,_=dispatch_fixture
    write(Path(config['queue_root'])/'slots'/'p1'/'finished.json',dict(receipt_path='other',receipt_sha256='x'))
    with pytest.raises(recovery.Blocked,match='SHARED_SLOT'):recovery.validate_dispatch(args,binding,config)


def test_adapter_passes_recovery_arguments_to_existing_supervisor_without_model(tmp_path):
    args=SimpleNamespace(config='cfg',config_sha='c',binding='binding',binding_sha='b',
        command_template='command',command_sha='m',dispatch='dispatch',dispatch_sha='d')
    config=dict(supervisor_output_root=str(tmp_path/'no-created-output'))
    binding=dict(authority_references=dict(administrative_decision=dict(path='/generated/decision',digest='a'*64)),
                 supervisor_bundle=dict(dependency_root='/generated/dependency'))
    seen=[]
    def fake(spec,argv,output,dep,sha,**kwargs):
        seen.append((spec,argv,output,dep,sha,kwargs))
        return dict(status='SUCCESS',job_id=recovery.pair.JOB,slot_completed=True)
    shared=SimpleNamespace(SupervisionSpec=lambda **v:v,run_supervised=fake)
    assert recovery.supervise(args,config,binding,shared)==0 and len(seen)==1
    spec,argv,_,_,sha,kwargs=seen[0]
    assert spec==recovery.pair.SPEC and spec['max_forward']==2 and spec['max_backward']==0
    assert argv[argv.index('--mode')+1]=='child' and argv[2]=='epi_next.encoder_fov64_recovery'
    assert sha==recovery.DEPENDENCY_SHA
    assert kwargs==dict(recovery_decision_path='/generated/decision',recovery_decision_sha='a'*64)
    assert not Path(config['supervisor_output_root']).exists()
