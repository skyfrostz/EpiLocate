"""Generated parent metadata/dispatch tests; never calls the real supervisor."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from qa import next_selected_fidelity_parent as parent
from qa import next_selected_fidelity as original


def ref(path, value):
    raw = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(raw)
    return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest())


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(parent, 'ROOT', tmp_path)
    environment = dict(parent.CPU_ENVIRONMENT, PYTHONPATH=str(tmp_path))
    monkeypatch.setattr(parent, 'CPU_ENVIRONMENT', environment)
    index_ref = ref(tmp_path/'index.json', dict(dependency_root='GENERATED_ONLY', dependency_sha256='0'*64))
    monkeypatch.setattr(parent, 'INDEX_SHA', index_ref['sha256'])
    source = tmp_path/'generated-source.py'; source.write_text('# GENERATED\n')
    sources = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in (source, Path(original.__file__))}
    binding = dict(schema='EPI_NEXT_SELECTED_FIDELITY_APPLICATION_BINDING_V2',
                   status='ENGINEERING_BOUND_NOT_DISPATCHED', source_sha256=sources,
                   job_id='generated_job', task_key='generated_task',
                   compute=dict(device='CPU', forward=5, backward=0, updates=0, seconds=120, output_bytes=67108864),
                   output_root=str(tmp_path/'.local/phase2/generated_job'), supervisor_index=index_ref)
    binding_ref = ref(tmp_path/'binding.json', binding)
    monkeypatch.setattr(parent, 'BINDING_SHA', binding_ref['sha256'])
    request_ref = ref(tmp_path/'request.json', dict(items=[dict(id='E2-FIDELITY-5F', binding=binding_ref,
                     limits=binding['compute'], task_key=binding['task_key'], job_id=binding['job_id'], output_root=binding['output_root'])]))
    monkeypatch.setattr(parent, 'REQUEST_SHA', request_ref['sha256'])
    owner_ref = ref(tmp_path/'owner.json', dict(status='EXPLICIT_ITEMIZED_APPROVAL', request=request_ref, approved_item_ids=['E2-FIDELITY-5F']))
    monkeypatch.setattr(parent, 'OWNER_SHA', owner_ref['sha256'])
    admission_ref = ref(tmp_path/'admission.json', dict(status='APPROVED_ADMINISTRATIVE_RECOVERY', scope=dict(
                      allowed_next_task_keys=[binding['task_key']], basis=dict(v4_itemized_owner=dict(digest=owner_ref['sha256']), v4_itemized_request=dict(digest=request_ref['sha256'])))))
    monkeypatch.setattr(parent, 'ADMISSION_SHA', admission_ref['sha256'])
    draft = dict(schema='EPI_NEXT_SELECTED_FIDELITY_PARENT_DISPATCH_V1', status='DRAFT_WAITING_CHIEF_EXECUTION_SLOT',
                 binding=binding_ref, binding_sha256=binding_ref['sha256'], source_sha256=sources,
                 parent_source_sha256={str(Path(parent.__file__).resolve()):hashlib.sha256(Path(parent.__file__).read_bytes()).hexdigest()},
                 task_key=binding['task_key'], job_id=binding['job_id'], compute=binding['compute'],
                 owner_receipt=owner_ref, new_admission_decision=admission_ref, supervisor_index=index_ref,
                 supervision_spec=parent.spec_for(binding), supervision_root=str(tmp_path/'.local/phase2/generated_job-supervision'),
                 environment=dict(environment), torch_threads=dict(intra_op=1, inter_op=1), execution_window=None)
    calls=[]
    wave=SimpleNamespace(SupervisionSpec=lambda **kw:SimpleNamespace(**kw),
                         run_supervised=lambda *args,**kw:(calls.append((args,kw)) or dict(status='SUCCESS',slot_completed=True)))
    loader=lambda _:dict(wave1_supervisor=wave)
    return draft, source, calls, loader


def test_generated_parent_draft_metadata_never_starts_or_allocates(tmp_path, monkeypatch):
    draft, _, calls, loader = fixture(tmp_path, monkeypatch)
    dispatch_ref=ref(tmp_path/'draft.json', draft)
    result=parent.run(dispatch_ref, supervisor_loader=loader)
    assert result['processes_started']==result['model_calls']==result['queue_writes']==0
    assert not result['arrays_weights_masks_read'] and not calls
    with pytest.raises(ValueError,match='WAIT_CHIEF'):
        parent.run(dispatch_ref,execute=True,supervisor_loader=loader)
    assert not calls


def test_generated_ready_window_delegates_exactly_once_to_existing_supervisor(tmp_path, monkeypatch):
    draft, _, calls, loader = fixture(tmp_path, monkeypatch)
    now=datetime.now(timezone.utc)
    draft.update(status='READY_FOR_CHIEF_DISPATCH',execution_window=dict(status='CHIEF_SLOT_GRANTED',slot_id='GENERATED_ONLY',
                  not_before_utc=(now-timedelta(seconds=10)).isoformat(),not_after_utc=(now+timedelta(seconds=600)).isoformat()))
    for name in draft['environment']:monkeypatch.setenv(name,os.environ.get(name,''))
    monkeypatch.delenv('EPI_NEXT_SUPERVISOR_DIR',raising=False)
    dispatch_ref=ref(tmp_path/'ready.json',draft)
    out=parent.run(dispatch_ref,execute=True,supervisor_loader=loader)
    assert out['status']=='SUCCESS' and len(calls)==1
    args,kw=calls[0]
    assert args[0].max_forward==5 and args[0].max_backward==0 and args[0].timeout_seconds==120
    assert args[1][-1]=='--child' and args[2]==draft['supervision_root']
    assert kw['recovery_decision_sha']==draft['new_admission_decision']['sha256']
    assert all(os.environ[name]==expected for name,expected in draft['environment'].items())


@pytest.mark.parametrize('tamper', ['source','threads','scope','window'])
def test_generated_tamper_and_missing_time_slot_stop_before_supervisor(tmp_path,monkeypatch,tamper):
    draft,source,calls,loader=fixture(tmp_path,monkeypatch)
    if tamper=='source':source.write_text('# CHANGED\n')
    elif tamper=='threads':draft['environment']['OMP_NUM_THREADS']='2'
    elif tamper=='scope':draft['supervision_spec']['max_forward']=6
    else:draft['status']='READY_FOR_CHIEF_DISPATCH'
    expected={'source':'SOURCE_DRIFT','threads':'EXACT_SCOPE_SPEC','scope':'EXACT_SCOPE_SPEC','window':'WAIT_CHIEF'}[tamper]
    with pytest.raises(ValueError,match=expected):parent.run(ref(tmp_path/'tampered.json',draft),execute=True,supervisor_loader=loader)
    assert not calls


def test_thread_receipt_is_measurement_only_using_generated_torch_double(tmp_path,monkeypatch):
    events=[]
    fake=SimpleNamespace(__version__='GENERATED',set_num_threads=lambda n:events.append(('intra',n)),
                         set_num_interop_threads=lambda n:events.append(('inter',n)),get_num_threads=lambda:1,get_num_interop_threads=lambda:1)
    writer=SimpleNamespace(write_new=lambda path,raw:path.write_bytes(raw))
    monkeypatch.setenv('EPI_NEXT_JOB_STARTED_MONOTONIC','GENERATED_ORIGINAL_CLOCK')
    value=dict(job_id='generated',task_key='generated',environment={},torch_threads=dict(intra_op=1,inter_op=1))
    receipt=parent.thread_receipt(fake,tmp_path,dict(coordinator_writer=writer),dict(path='GENERATED',sha256='0'*64),value)
    assert events==[('intra',1),('inter',1)]
    assert receipt['model_calls_for_thread_measurement']==0 and not receipt['budget_clock_reset']


def test_only_exact_admitted_child_may_reuse_created_supervision_directory(tmp_path,monkeypatch):
    draft,_,calls,loader=fixture(tmp_path,monkeypatch)
    draft.update(status='READY_FOR_CHIEF_DISPATCH',execution_window=dict(status='CHIEF_SLOT_GRANTED'))
    directory=Path(draft['supervision_root'])/draft['job_id'];directory.mkdir(parents=True)
    dispatch_ref=ref(tmp_path/'generated.json',draft)
    with pytest.raises(ValueError,match='RECONCILE_NO_RETRY'):
        parent.validate_plan(dispatch_ref,supervisor_loader=loader)
    monkeypatch.setenv('EPI_NEXT_SUPERVISOR_DIR',str(directory))
    parent.validate_plan(dispatch_ref,supervised_child=True,supervisor_loader=loader)
    monkeypatch.setenv('EPI_NEXT_SUPERVISOR_DIR',str(tmp_path/'unknown'))
    with pytest.raises(ValueError,match='EXACT_ADMITTED_CHILD'):
        parent.validate_plan(dispatch_ref,supervised_child=True,supervisor_loader=loader)
    assert not calls
