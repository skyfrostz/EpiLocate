import numpy as np
import pytest
from epi_next import ctfm_ridge_head_r79 as m


def test_fixed_ridge_matches_primal_and_train_only_stats():
    rng=np.random.default_rng(17);train=rng.normal(size=(40,12));labels=np.tile([0,1],20)
    state=m.fit_ridge(train,labels);z=(train-state['mean'])/state['scale']
    primal=np.linalg.solve(z.T@z+40*np.eye(12),z.T@(2*labels-1))
    np.testing.assert_allclose(state['weight'],primal,atol=1e-14,rtol=1e-12)
    np.testing.assert_array_equal(state['mean'],train.mean(0))
    np.testing.assert_allclose(m.score(state,train),z@primal,atol=1e-14)
    validation=rng.normal(size=(20,12))+100
    before=state['mean'].copy();m.score(state,validation);np.testing.assert_array_equal(state['mean'],before)
    assert m.CONFIG['lambda_L2']==1 and m.CONFIG['seed'] is None


def test_ridge_constant_scale_and_missing_authority():
    x=np.ones((40,512));y=np.tile([0,1],20);s=m.fit_ridge(x,y)
    assert np.all(s['scale']==1e-6) and np.all(s['weight']==0)
    with pytest.raises(m.p.Blocked):m.fit_ridge(x,np.ones(40))
    with pytest.raises(m.p.Blocked):m.validate_request(dict(schema='unapproved'))


@pytest.mark.parametrize('fail_second',[False,True])
def test_saved_entry_generated_fit_and_score_failure(tmp_path,monkeypatch,fail_second):
    import json
    class Guard:
        def __init__(self):self.attempts=0
        def check(self):pass
        def before_forward(self):self.attempts+=1
    guard=Guard();rng=np.random.default_rng(17);records=[];cached=[]
    for i in range(60):
        row=dict(record_id='SYN_'+str(i),source_group_id='SYN_G'+str(i),source_diagnosis='Normal' if i%2==0 else 'CAP',task_label=i%2,split='train_weak' if i<40 else 'val_classification')
        path=tmp_path/(str(i)+'.npy');np.save(path,rng.normal(size=(1,512)).astype(np.float64))
        cached.append(dict(row,gap=dict(path=str(path),sha256=m.p.file_sha(path))));records.append(row)
    manifest=tmp_path/'manifest.json';manifest.write_bytes(m.p.encoded(records));cache=tmp_path/'cache.json';cache.write_bytes(m.p.encoded(dict(status='PASS',rows=cached,data_manifest_sha256=m.p.file_sha(manifest))))
    req=dict(data_manifest=dict(path=str(manifest),sha256=m.p.file_sha(manifest)),cache_receipt=dict(path=str(cache),sha256=m.p.file_sha(cache)),output=str(tmp_path/'science'),delivery_root=str(tmp_path),source_commit='generated')
    monkeypatch.setattr(m.p,'validate_records',lambda x:x)
    real_score=m.score;calls=[]
    def score(state,x):
        calls.append(len(x))
        if fail_second and len(calls)==2:raise RuntimeError('generated second scoring failure')
        return real_score(state,x)
    monkeypatch.setattr(m,'score',score);meter=m.RidgeMeter(guard,str(tmp_path))
    if fail_second:
        with pytest.raises(RuntimeError):m.run_saved(req,guard,meter)
        assert meter.returned_forward==1 and meter.forward_inflight and guard.attempts==2
    else:
        assert m.run_saved(req,guard,meter)==dict(fit_calls=1,forward=2,backward=0,updates=0)
        assert meter.returned_forward==2 and not meter.forward_inflight
        out=json.loads((tmp_path/'science/evaluation.json').read_bytes());assert len(out['predictions'])==60
    assert meter.fit_attempts==meter.fit_returned==1


def test_ridge_actual_entry_failure_completion_preserves_counts(monkeypatch,tmp_path):
    from types import SimpleNamespace
    import json
    r=dict(spec={},delivery_root=str(tmp_path),output=str(tmp_path/'science'))
    a=dict(schema='CTFM_RIDGE_APPROVAL_R79_V1',status='APPROVED_NEW_SCOPE',request_sha256='r',task_key='k',retry=False)
    d=dict(schema='CTFM_RIDGE_DISPATCH_R79_V1',status='EXCLUSIVE_SLOT_ASSIGNED',request_sha256='r',task_key='k',retry=False,approval_sha256='a');r['spec']['task_key']='k'
    values={'r':r,'a':a,'d':d};monkeypatch.setattr(m.p,'bound_json',lambda ref:values[ref['sha256']]);monkeypatch.setattr(m,'validate_request',lambda x:x)
    completed=[]
    guard=SimpleNamespace(spec=SimpleNamespace(**r['spec']),complete=lambda *a,**kw:completed.append(kw))
    shared=SimpleNamespace(ChildGuard=SimpleNamespace(from_environment=lambda:guard),SupervisionSpec=lambda **x:SimpleNamespace(**x))
    monkeypatch.setattr(m.p,'load_shared',lambda r:shared)
    def failing(r,g,meter):meter.returned_forward=1;meter.forward=2;meter.forward_inflight=True;raise RuntimeError('score failed')
    monkeypatch.setattr(m,'run_saved',failing)
    args=['--request','r','--request-sha','r','--approval','a','--approval-sha','a','--dispatch','d','--dispatch-sha','d','--execute','--child']
    assert m.main(args)==3 and completed[0]['actual_forward'] is None
    saved=json.loads((tmp_path/'science/failure-counts.json').read_bytes());assert saved['returned_forward']==1
