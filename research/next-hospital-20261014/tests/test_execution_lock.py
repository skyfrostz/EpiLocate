import subprocess
import sys

import pytest

from epi_next.artifacts import canonical_json, sha256
from epi_next.execution_lock import dependency_snapshot, verify_dependencies, load_locked_module, tracked_device_slot
from epi_next import hospital_runtime


def locked_source(tmp_path):
    repo=tmp_path/'repo';repo.mkdir();(repo/'source.py').write_text('VALUE = 7\n')
    subprocess.run(['git','init','-q',str(repo)],check=True)
    subprocess.run(['git','add','source.py'],cwd=repo,check=True)
    subprocess.run(['git','-c','user.name=fixture','-c','user.email=fixture@example.invalid',
                    'commit','-qm','isolated fixture'],cwd=repo,check=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    root=tmp_path/'snapshots';name='EPI-NEXT-dependency'
    entries=[{'name':'source.py','repo':str(repo),'relative_path':'source.py','commit':commit,
              'sha256':sha256((repo/'source.py').read_bytes())}]
    digest=dependency_snapshot(root,name,entries,{})
    return root/name,digest,repo,entries


def test_source_snapshot_load_drift_and_dirty_bytes(tmp_path):
    root,digest,repo,entries=locked_source(tmp_path)
    assert load_locked_module(root,digest,'source.py','fixture_source').VALUE==7
    (repo/'source.py').write_text('VALUE = 8\n')
    with pytest.raises(ValueError,match='LIVE_DEPENDENCY_DRIFT'):verify_dependencies(root,digest)
    entries[0]['sha256']=sha256((repo/'source.py').read_bytes())
    with pytest.raises(ValueError,match='DIRTY_DEPENDENCY'):dependency_snapshot(root.parent,'EPI-NEXT-dirty',entries,{})
    entries[0]['allow_dirty_bytes']=True
    new_digest=dependency_snapshot(root.parent,'EPI-NEXT-dirty',entries,{})
    assert verify_dependencies(root.parent/'EPI-NEXT-dirty',new_digest)['entries'][0]['source_dirty']


def test_slot_unknown_and_confirmed_completion(tmp_path,monkeypatch):
    root,digest,_,_=locked_source(tmp_path)
    monkeypatch.setattr(hospital_runtime,'QUEUE_ROOT',tmp_path/'queue')
    args=dict(owner='INTEGRATION',task_key='synthetic',budget={'max_model_calls':1,'max_seconds':2,'max_rss_bytes':1000000},
              dependency_root=root,dependency_sha=digest)
    with tracked_device_slot('cpu',job_id='known',**args) as slot:
        assert slot.record['pid']>0 and slot.record['process_start']
        with pytest.raises(RuntimeError,match='DEVICE_QUEUE_BUSY'):
            with tracked_device_slot('cpu',job_id='parallel',**args):pass
        receipt=tmp_path/'terminal.json';receipt.write_bytes(canonical_json({'job_id':'known','status':'NOT RUN'}))
        process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(.2)'])
        slot.track_child(process)
        with pytest.raises(RuntimeError,match='TASK_CHILD_STILL_RUNNING'):
            slot.complete(receipt,sha256(receipt.read_bytes()))
        assert process.wait(timeout=5)==0
        slot.complete(receipt,sha256(receipt.read_bytes()))
    with tracked_device_slot('cpu',job_id='interrupted',**args):pass
    with pytest.raises(RuntimeError,match='PRIOR_SLOT_UNKNOWN'):
        with tracked_device_slot('cpu',job_id='next',**args):pass
