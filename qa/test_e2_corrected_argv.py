"""Generated metadata only; real main parser and real exact dispatch checks."""
import json
import copy
import hashlib
import sys
from pathlib import Path
import pytest
from qa import next_e2_readout as entry
from qa.e2_corrected_argv import derive


def put(root,name,value):
    path=root/name;path.write_text(json.dumps(value))
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def fixture(tmp):
    value=dict(supervision_spec={'generated':True},output_root=str(tmp/'science'),queue_root=str(tmp/'never-created-queue'))
    binding=put(tmp,'binding.json',value)
    request=put(tmp,'request.json',dict(items=[dict(id='E2-R',binding=binding,limits=entry.COMPUTE,
        task_key=entry.TASK,job_id=entry.JOB,output_root=value['output_root'])]))
    owner=put(tmp,'owner.json',dict(status='EXPLICIT_ITEMIZED_APPROVAL',approved_item_ids=['E2-R'],request=request))
    admission=put(tmp,'admission.json',dict(status='APPROVED_ADMINISTRATIVE_RECOVERY',queue_root=value['queue_root'],
        scope=dict(allowed_next_task_keys=[entry.TASK],basis=dict(e2_r_itemized_owner=dict(digest=owner['sha256']),e2_r_itemized_request=dict(digest=request['sha256'])))))
    d=dict(schema='EPI_NEXT_E2_R_DISPATCH_V1',status='READY_FOR_CHIEF_DISPATCH',binding=binding,
        task_key=entry.TASK,job_id=entry.JOB,compute=entry.COMPUTE,supervision_spec=value['supervision_spec'],
        owner_receipt=owner,new_admission_decision=admission,execution_window=dict(status='CHIEF_SLOT_GRANTED',slot_id='GENERATED-NOT-RESERVED'))
    return value,binding,put(tmp,'dispatch.json',d)


def parser_check(monkeypatch,argv,value):
    def check(reference,dispatch_ref,*,execute=False):
        assert not execute
        entry.check_dispatch(reference,value,dispatch_ref,executing=False)
        return dict(status='SYNTHETIC_CHECK_ONLY')
    # Boundary substitution only prevents supervisor entry; parser and comparison remain production.
    monkeypatch.setattr(entry,'run',check)
    monkeypatch.setattr(sys,'argv',argv[1:])
    return entry.main()


def test_absolute_vector_and_cwd_independence(tmp_path,monkeypatch):
    value,binding,dispatch=fixture(tmp_path);out=derive(dispatch)
    assert '--execute' not in out['argv'] and out['argv'][3]==binding['path']
    monkeypatch.chdir(tmp_path.parent)
    assert parser_check(monkeypatch,out['argv'],value)==0
    assert not Path(value['queue_root']).exists() and not Path(value['output_root']).exists()


def test_relative_representation_rejected_by_same_parser(tmp_path,monkeypatch):
    value,binding,dispatch=fixture(tmp_path);argv=derive(dispatch)['argv'];argv[3]='binding.json'
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError,match='NEW_EXACT'):parser_check(monkeypatch,argv,value)


@pytest.mark.parametrize('bad',['sha','task','job','compute'])
def test_generated_tampering_rejected(tmp_path,bad):
    value,binding,dispatch=fixture(tmp_path)
    if bad=='sha':dispatch['sha256']='0'*64
    else:
        d=json.load(open(dispatch['path']));d[{'task':'task_key','job':'job_id','compute':'compute'}[bad]]='wrong'
        dispatch=put(tmp_path,'dispatch.json',d)
    with pytest.raises(ValueError):derive(dispatch)


def test_binding_bytes_drift_rejected(tmp_path):
    _,binding,dispatch=fixture(tmp_path);Path(binding['path']).write_text('{}')
    with pytest.raises(ValueError,match='BOUND_REFERENCE_DRIFT'):derive(dispatch)
