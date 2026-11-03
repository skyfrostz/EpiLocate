"""Exact2-call generated fixtures/fake model only. No real approval/slot/checkpoint."""
from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from epi_next import encoder_fov64_pair as pair


class Guard:
    def __init__(self): self.reserved = 0; self.stopped = False; self.completed = None
    def check(self):
        if self.stopped: raise RuntimeError('STOP_REQUESTED')
    def before_forward(self):
        self.check()
        if self.reserved >= 2: raise RuntimeError('GLOBAL_TWO_LIMIT')
        self.reserved += 1
    @contextmanager
    def ledger(self): yield dict(forward=self.reserved, backward=0)
    def complete(self, **values):
        assert values['actual_forward'] <= self.reserved
        self.completed = values


class FakeBackend:
    def __init__(self, fail=None): self.devices=[]; self.fail=fail; self.journal=None
    def load(self, journal): self.journal=journal
    def infer(self, value, device):
        self.journal.network_entry(); self.devices.append(device)
        if self.fail == device: raise RuntimeError('INJECTED_OPERATOR_FAILURE')
        return np.full((1,512,4,4,4), float(value.mean()), np.float32), dict(cold_forward_seconds=.001)


@pytest.fixture
def prepared(tmp_path):
    artifacts=pair.PrivateArtifacts(tmp_path/'new',16*1024**2)
    input_sha=artifacts.array('input64.npy',np.linspace(0,1,64**3,dtype=np.float32).reshape(1,1,64,64,64))
    ledger_sha=artifacts.json('ledger64.json',dict(task_key=pair.TASK,input_file_sha256=input_sha,
                                                field_of_view='FULL_APPROVED_SELECTED_SERIES'))
    record=dict(input_path=str(artifacts.directory/'input64.npy'),input_sha256=input_sha,
                ledger_path=str(artifacts.directory/'ledger64.json'),ledger_sha256=ledger_sha)
    return record,artifacts


def test_exact_two_global_entries_save_full_outputs_and_complete(prepared):
    record,assets=prepared;guard=Guard();journal=pair.CallJournal(guard,assets.directory/'calls.jsonl');backend=FakeBackend()
    result=pair.execute_pair(record,assets,guard,journal,backend,{'status':'PASS'})
    assert journal.actual==journal.adapter_attempts==guard.reserved==2 and backend.devices==['cpu','mps']
    with pytest.raises(RuntimeError,match='TWO_LIMIT'):journal.reserve(1,'mps',1)
    assert result['comparison']['elements']==32768 and result['comparison']['max_absolute_error']==0
    status=pair.finish_child(assets,guard,journal,result,dict(device_recovered=True),SimpleNamespace(report=lambda:{}))
    assert status==0 and guard.completed['actual_forward']==2 and guard.completed['status']=='SUCCESS'
    for device in ('cpu','mps'):
        assert np.load(assets.directory/(device+'_features.npy')).shape==(1,512,4,4,4)
        assert np.load(assets.directory/(device+'_gap512.npy')).shape==(1,512)


def test_first_failure_never_enters_mps_and_partial_exit_records_one(prepared):
    record,assets=prepared;guard=Guard();journal=pair.CallJournal(guard,assets.directory/'calls.jsonl');backend=FakeBackend('cpu')
    with pytest.raises(RuntimeError,match='OPERATOR'):
        pair.execute_pair(record,assets,guard,journal,backend,{'status':'FAIL'})
    assert backend.devices==['cpu'] and journal.actual==guard.reserved==1
    assert not (assets.directory/'mps_features.npy').exists()
    status=pair.finish_child(assets,guard,journal,{'status':'FAIL'},dict(device_recovered=True),SimpleNamespace(report=lambda:{}))
    assert status==2 and guard.completed['actual_forward']==1


def test_missing_cleanup_never_marks_device_recovered(prepared):
    _,assets=prepared;guard=Guard();journal=pair.CallJournal(guard,assets.directory/'calls.jsonl')
    status=pair.finish_child(assets,guard,journal,{'status':'PASS'},dict(device_recovered=False),SimpleNamespace(report=lambda:{}))
    assert status==2 and not guard.completed['device_recovered'] and guard.completed['status']=='FAILED'


@pytest.mark.parametrize('asset',['input','ledger'])
def test_frozen_asset_drift_blocks_before_model_load(prepared,asset):
    record,assets=prepared;path=Path(record[asset+'_path']);path.write_bytes(path.read_bytes()+b'corrupt')
    guard=Guard();journal=pair.CallJournal(guard,assets.directory/'calls.jsonl');backend=FakeBackend()
    with pytest.raises(ValueError,match='DRIFT'):pair.execute_pair(record,assets,guard,journal,backend,{})
    assert backend.devices==[] and backend.journal is None and journal.actual==guard.reserved==0


def test_unknown_queue_and_same_scope_replay_default_rejection(tmp_path):
    slot=tmp_path/'slots'/'old';slot.mkdir(parents=True)
    (slot/'started.json').write_text(json.dumps(dict(job_id='old',task_key='prior-task')))
    with pytest.raises(pair.AdmissionBlocked,match='UNKNOWN_SLOT'):pair.queue_gate(tmp_path)
    receipt=tmp_path/'prior.json';receipt.write_text('{}')
    (slot/'finished.json').write_text(json.dumps(dict(receipt_path=str(receipt),receipt_sha256=pair.file_sha(receipt))))
    assert len(pair.queue_gate(tmp_path))==1
    (slot/'started.json').write_text(json.dumps(dict(job_id='old',task_key=pair.TASK)))
    with pytest.raises(pair.AdmissionBlocked,match='NO_RETRY'):pair.queue_gate(tmp_path)


def test_missing_approval_blocks_before_any_receipt_or_pixels(monkeypatch):
    def must_not_read(*args):raise AssertionError('missing approval should not read files')
    monkeypatch.setattr(pair,'read_bound_json',must_not_read)
    with pytest.raises(pair.AdmissionBlocked,match='APPROVAL_AND_DISPATCH'):
        pair.load_authority(SimpleNamespace(),{}, {})


def test_complete_scope_authority_and_wrong_budget_rejected(monkeypatch,tmp_path):
    selection=dict(source_input_sha256='i'*64,source_ledger_sha256='l'*64)
    args=SimpleNamespace(approval='a',approval_sha='a'*64,dispatch='d',dispatch_sha='d'*64,
                         config_sha='c'*64,binding_sha='b'*64,command_sha='e'*64)
    identity=dict(task_key=pair.TASK,job_id=pair.JOB,config_sha256=args.config_sha,binding_sha256=args.binding_sha,
                  command_template_sha256=args.command_sha,dependency_sha256=pair.DEPENDENCY_SHA,max_forward=2,
                  max_backward=0,timeout_seconds=180,per_case_seconds=120,case_index=1,**selection)
    a=dict(identity,schema='CTFM_V3_PAIR_APPROVAL_V1',status='APPROVED_NEW_SCOPE',owner='ENCODER',retry=False,
           head_training=False,prior_unknown_reconciliation=dict(status='EXTERNALLY_VERIFIED_RECOVERY',path='r',sha256='r'*64))
    d=dict(identity,schema='CTFM_V3_PAIR_DISPATCH_V1',status='EXCLUSIVE_SLOT_ASSIGNED',owner='ENCODER',retry=False,
           head_training=False,approval_sha256=args.approval_sha)
    documents={'a':a,'d':d,'r':{}}
    monkeypatch.setattr(pair,'read_bound_json',lambda path,sha:documents[path])
    assert pair.load_authority(args,dict(selection=selection),{})['identity']['max_forward']==2
    d['max_forward']=3
    with pytest.raises(pair.AdmissionBlocked,match='MISMATCH'):pair.load_authority(args,dict(selection=selection),{})


def test_generated_saved128_preparation_freezes_64_and_geometry(tmp_path):
    parent=tmp_path/'generated128.npy';np.save(parent,np.zeros((1,1,128,128,128),np.float32))
    ledger=tmp_path/'generated128.json';ledger.write_text(json.dumps(dict(input_file_sha256=pair.file_sha(parent),
        model_to_native=np.eye(4).tolist(),model_to_lps=np.eye(4).tolist(),proposed_spacing_spl_mm=[1,1,1])))
    config=dict(selection=dict(source_input_path=str(parent),source_input_sha256=pair.file_sha(parent),
                               source_ledger_path=str(ledger),source_ledger_sha256=pair.file_sha(ledger)))
    assets=pair.PrivateArtifacts(tmp_path/'new',16*1024**2);guard=Guard()
    prepared=pair.prepare_input(config,assets,guard);value=pair.verify_prepared(prepared,assets)
    result=json.loads(Path(prepared['ledger_path']).read_bytes())
    assert value.shape==(1,1,64,64,64) and guard.reserved==0
    assert result['model_to_native'][0]==[2.,0.,0.,.5]
    assert result['edge_error_voxels']==0 and len(result['cell_average_probes'])==9


def test_stop_after_reservation_before_adapter_preserves_zero_actual(prepared):
    record,assets=prepared;guard=Guard();original=guard.before_forward
    def stop():original();guard.stopped=True
    guard.before_forward=stop;journal=pair.CallJournal(guard,assets.directory/'calls.jsonl');backend=FakeBackend()
    with pytest.raises(RuntimeError,match='STOP'):pair.execute_pair(record,assets,guard,journal,backend,{})
    assert guard.reserved==1 and journal.actual==journal.adapter_attempts==0 and backend.devices==[]
