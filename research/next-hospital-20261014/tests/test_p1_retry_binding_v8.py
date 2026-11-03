"""Approved timing/output deltas only; no classifier/model/P1 optimization."""

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[3]
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from epi_next import p1_retry_binding_v8 as retry,p1_recovery_v5 as recovery,p1_runner_v4 as worker
from epi_next.p1_storage_v4 import BoundedStore
from epi_next.hspi_core_v3 import BudgetStopped
from epi_next.spi_recovery_v2 import ComputeMeter,StopBudget
from test_p1_recovery_v5 import fixture

PRIVATE=Path(str(_PUBLIC_ROOT / '.local/private-bindings/manifests/epi-next-phase2-coordinator/next-sprint-20261011'))
INVENTORY=Path(__file__).resolve().parents[3]/'.local/phase2/p1-storage-race-v6/failed-output-inventory.json'


def binding(control):
    inventory=json.loads(INVENTORY.read_text())
    return {**retry.EXPECTED,'max_manual_attempts':1,'historical_charge_is_measured':False,
        'original_total_administrative_seconds':3600,'old_tail_seconds':'UNKNOWN_NOT_ZERO',
        'request':recovery.reference(PRIVATE/'CONSOLIDATED_NEXT_ACTIONS_REQUEST_V1.json'),
        'owner_approval':recovery.reference(PRIVATE/'OWNER_APPROVAL_V1.json'),
        'old_output_inventory':recovery.reference(INVENTORY),'old_failed_roots':inventory['roots'],
        'control_root':str(control)}


def test_parent_binds_approved3540_and_preserves_case_caps_without_queue_call(tmp_path,monkeypatch):
    supervisor,_,_,ready,_,_,_=fixture(tmp_path,monkeypatch)
    control=tmp_path/'control';control.mkdir();ready['retry_budget']=binding(control)
    config=control/'config.json';config.write_text(json.dumps({'schema':'P1_APPROVED_RETRY_CONFIG_V8','retry_budget':ready['retry_budget'],
        'task_key':ready['supervisor_task_key'],'job_id':ready['supervisor_job_id'],
        'execution_output':ready['execution_output'],'supervision_output_root':ready['supervision_output_root']}))
    ready['retry_config']=recovery.reference(config)
    ready_ref_path=control/'ready.json';ready_ref_path.write_text(json.dumps(ready));ready_ref=recovery.reference(ready_ref_path)
    lock=recovery.dispatch_template(ready,ready_ref)
    lock.update(status='LOCKED_FOR_P1_CPU_EXECUTION',real_model_execution_authorized=True,unique_queue_verified_by_chief=True)
    lock_path=control/'lock.json';lock_path.write_text(json.dumps(lock));lock_ref=recovery.reference(lock_path)
    seen={}
    def capture(spec,*args,**kwargs):seen.update(spec=spec,kwargs=kwargs);return {'status':'NOT RUN'}
    monkeypatch.setattr(supervisor,'run_supervised',capture)
    for k,v in {'PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1',
        'PYTHONPATH':str(Path(worker.__file__).resolve().parents[1])}.items():monkeypatch.setenv(k,v)
    assert recovery.run_parent(ready_ref,lock_ref)['status']=='NOT RUN'
    spec=seen['spec'];assert spec.timeout_seconds==3540 and spec.per_case_seconds==1200
    assert spec.max_forward==27027 and spec.max_backward==27000
    assert lock['soft_timeout_seconds_total']==3540 and retry.activity_seconds(ready,lock)==3540
    assert seen['kwargs']['recovery_decision_sha']==ready['recovery_binding']['decision']['sha256']
    bad=copy.deepcopy(lock);bad['soft_timeout_seconds_total']=3600
    with pytest.raises(ValueError,match='DISPATCH'):worker.verify_dispatch(ready,ready_ref['sha256'],bad)
    config.write_text('{}')
    with pytest.raises(ValueError,match='SHA_DRIFT'):worker.verify_dispatch(ready,ready_ref['sha256'],lock)


def test_meter_global_clock_and_administrative_charge_do_not_reset(tmp_path):
    control=tmp_path/'control';control.mkdir();ready={'retry_budget':binding(control),
        'supervisor_job_id':'GENERATED-FRESH','supervisor_task_key':'GENERATED-FRESH',
        'execution_output':str(tmp_path/'runner'),'supervision_output_root':str(tmp_path/'supervision')}
    clock=[100.];guard=SimpleNamespace(started=100.,check=lambda:None)
    meter=ComputeMeter(max_forwards=27027,max_reverse=27000,max_seconds=retry.activity_seconds(ready),
        clock=lambda:clock[0],guard=guard)
    clock[0]=3639.999;meter.check()
    info=retry.time_accounting(ready,meter.receipt())
    assert info['historical_administrative_charge_seconds']==60 and info['historical_charge_is_measured'] is False
    assert info['administrative_total_elapsed_seconds']==pytest.approx(3599.999)
    assert info['old_tail_seconds']=='UNKNOWN_NOT_ZERO' and meter.started==100.
    clock[0]=3640.
    with pytest.raises(StopBudget,match='TIME_LIMIT'):meter.check()
    # Original standalone3600 path remains unchanged when no retry binding exists.
    assert retry.activity_seconds({})==3600


def test_old_failure_control_tmp_and_new_outputs_share_cap(tmp_path):
    control=tmp_path/'control';control.mkdir();(control/'approval-control.json').write_bytes(b'c'*17)
    job=tmp_path/'supervision'/'new-job';job.mkdir(parents=True);(job/'telemetry.json').write_bytes(b't'*29)
    runner=tmp_path/'runner';runner.mkdir();(runner/'new.bin').write_bytes(b'n'*31)
    ready={'retry_budget':binding(control),'supervisor_job_id':'GENERATED-FRESH','supervisor_task_key':'GENERATED-FRESH',
        'execution_output':str(runner),'supervision_output_root':str(job.parent)}
    retry.validate_retry(ready)
    store=BoundedStore(runner,extra_roots=retry.accounting_extra_roots(ready,job))
    assert store.size()==14445+17+29+31
    (runner/'new.pending').write_bytes(b'p'*13);assert store.size()==14445+17+29+31+13
    # Sparse generated file, no large allocation: accounting cap must include old files.
    with (runner/'too-large.bin').open('xb') as f:f.truncate(268435456-31)
    with pytest.raises(BudgetStopped,match='OUTPUT_BYTE_LIMIT'):store.ensure(0,terminal=True)
    bad=copy.deepcopy(ready);bad['retry_budget']['historical_administrative_charge_seconds']=0
    with pytest.raises(ValueError,match='BUDGET_DRIFT'):retry.activity_seconds(bad)
    with pytest.raises(ValueError,match='CHARGED_ROOT'):retry.control_paths(ready,tmp_path/'outside.json',control/'lock.json')


def test_final_chain_consumer_check_only_no_queue_or_model(monkeypatch):
    """Current fixed real metadata only; reuse INT's 20 generated chain checks."""
    root=Path(worker.__file__).resolve().parents[3]
    ready_path=root/'.local/phase2/p1-retry-v8/control/final-readiness-v8.json'
    ready_ref=recovery.reference(ready_path);ready=recovery.bound_reference(ready_ref)
    queue=Path(ready['recovery_binding']['queue_root'])
    old_jobs=ready['recovery_binding']['verified_recovery']['old_job_ids']
    before={job:(queue/'slots'/job/'started.json').read_bytes() for job in old_jobs}
    finished={job:(queue/'slots'/job/'finished.json').exists() for job in old_jobs}
    monkeypatch.setattr(worker,'consume_inputs',lambda *a:pytest.fail('no CT read'))
    monkeypatch.setattr(worker,'bind_child',lambda *a,**k:pytest.fail('no child guard'))
    supervisor=recovery.load_supervisor_bundle(ready['dependency_root'],ready['dependency_sha256'])
    monkeypatch.setattr(supervisor,'run_supervised',lambda *a,**k:pytest.fail('no real dispatch'))
    template=recovery.dispatch_template(ready,ready_ref)
    with pytest.raises(ValueError,match='DISPATCH'):worker.verify_dispatch(ready,ready_ref['sha256'],template)
    # In-memory field validation is not an issued lock and never enters run_parent.
    lock=copy.deepcopy(template)
    lock.update(status='LOCKED_FOR_P1_CPU_EXECUTION',real_model_execution_authorized=True,unique_queue_verified_by_chief=True)
    worker.verify_dispatch(ready,ready_ref['sha256'],lock)
    assert ready['dependency_sha256']==recovery.CHAIN_DEPENDENCY_SHA
    assert len(old_jobs)==2 and 'predecessor_evidence' in ready['recovery_binding']
    bad=copy.deepcopy(lock);bad['dependency_lock_sha256']=recovery.DEPENDENCY_SHA
    with pytest.raises(ValueError,match='RECOVERY'):worker.verify_dispatch(ready,ready_ref['sha256'],bad)
    bad=copy.deepcopy(ready);bad['supervisor_job_id']='different-manual-attempt'
    with pytest.raises(ValueError,match='IDENTITY_DRIFT'):retry.activity_seconds(bad,lock)
    assert before=={job:(queue/'slots'/job/'started.json').read_bytes() for job in old_jobs}
    assert finished=={job:(queue/'slots'/job/'finished.json').exists() for job in old_jobs}
    assert not Path(ready['execution_output']).exists() and not Path(ready['supervision_output_root']).exists()
