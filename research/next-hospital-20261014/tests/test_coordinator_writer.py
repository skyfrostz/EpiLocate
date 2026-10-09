import json
import multiprocessing as mp
import os

import pytest

from epi_next.artifacts import canonical_json, sha256
from epi_next.coordinator_writer import update, reconcile, read_events


def fixture(tmp_path):
    state=tmp_path/'state.json'
    state.write_bytes(canonical_json({'revision':11,'status':'READY','use_permissions':{'hospital':False}}))
    policy=tmp_path/'policy.json'
    policy.write_bytes(canonical_json({'writer_id':'CHIEF','uid':os.geteuid(),'state_path':str(state),
                                       'allowed_pointers':['/status','/result','/use_permissions/hospital']}))
    return (state,policy,sha256(policy.read_bytes()),11,sha256(state.read_bytes()))


def call(args, key='one', **kwargs):
    return update(*args,'CHIEF',key,'isolated synthetic fixture',{'/status':'PASS'},**kwargs)


def test_cas_duplicate_permission_and_snapshot(tmp_path):
    args=fixture(tmp_path);state=args[0]
    result=call(args)
    assert result['revision']==12 and reconcile(state)['status']=='CONSISTENT'
    assert json.loads(state.read_bytes())['use_permissions']=={'hospital':False}
    assert __import__('pathlib').Path(result['snapshot_path']).read_bytes()==state.read_bytes()
    with pytest.raises(RuntimeError,match='DUPLICATE'):call(args)
    with pytest.raises(RuntimeError,match='STALE'):call(args,'two')
    fresh=(*args[:3],12,result['sha256'])
    with pytest.raises(PermissionError,match='IMMUTABLE'):
        update(*fresh,'CHIEF','permission','must reject',{'/use_permissions/hospital':True})
    with pytest.raises(PermissionError,match='NESTED_PERMISSION'):
        update(*fresh,'CHIEF','nested','must reject',{'/result':{'hospital_authorized':True}})
    with pytest.raises(PermissionError,match='IDENTITY'):
        update(*fresh,'OTHER','wrong','must reject',{'/status':'READY'})
    state.write_bytes(canonical_json({'revision':11,'status':'READY','use_permissions':{'hospital':False}}))
    assert reconcile(state)['status']=='EXTERNAL_STATE_CHANGE'
    with pytest.raises(RuntimeError,match='EXTERNAL_STATE'):call(args,'three')


def worker(args, key, barrier, queue):
    barrier.wait()
    try:queue.put(call(args,key)['status'])
    except RuntimeError as e:queue.put(str(e))


def test_simultaneous_writers_only_one_commit(tmp_path):
    args=fixture(tmp_path);ctx=mp.get_context('spawn');barrier=ctx.Barrier(2);queue=ctx.Queue()
    children=[ctx.Process(target=worker,args=(args,str(i),barrier,queue)) for i in range(2)]
    for child in children:child.start()
    for child in children:child.join(15);assert child.exitcode==0
    statuses=[queue.get(timeout=2) for _ in children]
    assert statuses.count('COMMITTED')==1
    assert any(s in {'WRITER_BUSY','STALE_REVISION_OR_SHA'} for s in statuses)
    assert json.loads(args[0].read_bytes())['revision']==12


def test_corrupt_event_or_snapshot_blocks_updates(tmp_path):
    args=fixture(tmp_path);result=call(args)
    from pathlib import Path
    Path(result['snapshot_path']).write_bytes(b'corrupt snapshot')
    with pytest.raises(RuntimeError,match='SNAPSHOT_HASH'):reconcile(args[0])
    with pytest.raises(RuntimeError,match='SNAPSHOT_HASH'):call(args,'next')


def crash_worker(args, phase):
    def stop(observed):
        if observed==phase:os._exit(71)
    call(args,_checkpoint=stop)


@pytest.mark.parametrize('phase',['prepared','snapshot','temporary','replaced'])
def test_killed_writer_fences_retry_without_rollback(tmp_path,phase):
    args=fixture(tmp_path);ctx=mp.get_context('spawn');child=ctx.Process(target=crash_worker,args=(args,phase))
    child.start();child.join(15);assert child.exitcode==71
    observed=reconcile(args[0])
    assert observed['status']==('APPLIED_PENDING_EVENT' if phase=='replaced' else 'NOT_APPLIED_RECONCILE_REQUIRED')
    with pytest.raises(RuntimeError,match='UNKNOWN_TRANSACTION'):call(args,'next')
    assert json.loads(args[0].read_bytes())['revision']==(12 if phase=='replaced' else 11)
    events=read_events(args[0].parent/(args[0].name+'.writer'))
    assert len(events)==1 and events[0]['phase']=='PREPARED'
