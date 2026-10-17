"""Generated DICOM + SQLite tests for the additive product annotation API."""
import copy
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, event
from sqlalchemy.orm import sessionmaker

from qa.annotation_workspace import seed, validate_generated_run, TestStorage as GeneratedStorage
from backend_v2.annotation_v1.api import create_app, world
from backend_v2.db.base import make_engine
from backend_v2.services.common import digest
from session_gateway.app import backend_token


@pytest.fixture
def ctx(tmp_path,monkeypatch):
    monkeypatch.setenv('EPILOCATE_V2_ALLOW_ENV_TOKENS','false')
    run=tmp_path/'isolated';config=seed(run)
    engine=make_engine('sqlite:///'+str(run/'backend.sqlite'));factory=sessionmaker(engine,expire_on_commit=False)
    def app():return create_app(factory,GeneratedStorage(run/'TEST_STORAGE'))
    client=TestClient(app())
    headers={'Authorization':'Bearer '+backend_token(str(run/'synthetic-doctor.env'))}
    other={'Authorization':'Bearer '+backend_token(str(run/'synthetic-observer.env'))}
    path='/api/v2/cases/'+config['binding']['case_id']+'/annotations'
    binding={k:v for k,v in config['binding'].items() if k!='geometry'}
    body=dict(annotation_id=str(uuid.uuid4()),operation_id=str(uuid.uuid4()),expected_version=0,binding=binding,vertices=[[10.,10.],[50.,10.],[50.,40.],[10.,40.]],category='SUSPECTED_INFECTION',state='ACTIVE',note='generated only')
    yield client,headers,other,path,body,factory,app,run
    client.close();engine.dispose()


def test_persist_refresh_edit_withdraw_restore_and_immutable_audit(ctx):
    c,h,_,path,b,factory,app,_=ctx
    r=c.post(path,headers=h,json=b);assert r.status_code==200,r.text
    one=r.json();assert one['version']==1 and one['author']=='synthetic-doctor' and not one['training_gt_eligible']
    assert one['world_vertices_lps_mm'][0]==[5.,46.,56.]
    # Recreate application to prove persistence independent of browser/session state.
    with TestClient(app()) as reopened:assert reopened.get(path,headers=h).json()['items']==[one]
    b.update(expected_version=1,operation_id=str(uuid.uuid4()));b['vertices'][0]=[11.,10.]
    two=c.post(path,headers=h,json=b).json();assert two['version']==2 and two['previous_revision_sha256']==one['revision_sha256']
    b.update(expected_version=2,operation_id=str(uuid.uuid4()),state='WITHDRAWN')
    three=c.post(path,headers=h,json=b).json();assert three['version']==3
    history=c.get(path+'/'+b['annotation_id']+'/history',headers=h).json()
    assert [r['version'] for r in history['revisions']]==[1,2,3]
    assert [e['action'] for e in history['events']]==['CREATE','UPDATE','WITHDRAW']
    assert history['revisions'][0]==one and c.get(path,headers=h).json()['items'][0]['state']=='WITHDRAWN'
    with factory() as db:
        for table in ['annotation_revisions_v1','annotation_events_v1','annotation_image_planes_v1']:
            with pytest.raises(Exception,match='IMMUTABLE_ANNOTATION_RECORD'):
                db.execute(text('DELETE FROM '+table));db.commit()
            db.rollback()
    b.update(expected_version=3,operation_id=str(uuid.uuid4()),state='ACTIVE')
    assert c.post(path,headers=h,json=b).json()['version']==4
    assert c.get(path+'/'+b['annotation_id']+'/history',headers=h).json()['events'][-1]['action']=='RESTORE'


def test_auth_owner_author_and_compute_closed(ctx):
    c,h,o,path,b,*_=ctx
    assert c.get(path).status_code==401
    assert c.post(path,headers=o,json=b).status_code==403
    assert c.get(path,headers=o).status_code==403
    assert c.post(path,headers=h,json=dict(b,author='forged')).status_code==422
    r=c.post(path,headers=h,json=b).json();assert r['author']=='synthetic-doctor'
    assert c.get(path+'/'+b['annotation_id']+'/history',headers=o).status_code==403
    assert c.post('/api/v2/jobs',headers=h,json={}).status_code==404
    assert c.post('/api/v2/workers/jobs/claim',headers=h,json={}).status_code==404


@pytest.mark.parametrize('key',['ct_sha256','sop_instance_uid','series_uid','study_uid','slice_id','frame_of_reference_uid','geometry_sha256','case_id'])
def test_exact_ct_native_identity_binding(ctx,key):
    c,h,_,path,b,*_=ctx;b['binding'][key]='f'*64 if key.endswith('sha256') else 'wrong'
    assert c.post(path,headers=h,json=b).status_code==409
    assert c.get(path,headers=h).json()['items']==[]


@pytest.mark.parametrize('vertices',[
    [[-1.,1.],[2.,1.],[2.,3.]],[[0.,0.],[112.,0.],[0.,3.]],
    [[0.,0.],[20.,20.],[0.,20.],[20.,0.]],[[0.,0.],[1.,1.],[2.,2.]],
    [[1.,1.],[4.,1.],[1.,1.]],[[1.,1.,2.],[4.,1.],[1.,4.]],
])
def test_invalid_native_polygons_rejected(ctx,vertices):
    c,h,_,path,b,*_=ctx;b['vertices']=vertices
    assert c.post(path,headers=h,json=b).status_code==422


def test_nan_infinity_and_fake_world_rejected(ctx):
    c,h,_,path,b,*_=ctx
    for token in ['NaN','Infinity','-Infinity']:
        raw=json.dumps(b).replace('10.0',token,1)
        assert c.post(path,headers={**h,'Content-Type':'application/json'},content=raw).status_code==422
    assert c.post(path,headers=h,json=dict(b,world_vertices_lps_mm=[[0,0,0]]*4)).status_code==422


def test_concurrent_cas_one_winner_and_operation_reconciliation(ctx):
    c,h,_,path,b,factory,app,_=ctx
    assert c.post(path,headers=h,json=b).status_code==200
    barrier=Barrier(2)
    def simultaneous_update(conn,cursor,statement,parameters,context,executemany):
        if statement.startswith('UPDATE annotation_heads_v1'):barrier.wait(timeout=5)
    engine=factory.kw['bind'];event.listen(engine,'before_cursor_execute',simultaneous_update)
    def submit(i):
        value=copy.deepcopy(b);value.update(expected_version=1,operation_id=str(uuid.uuid4()),note=str(i))
        with TestClient(app()) as client:return value,client.post(path,headers=h,json=value)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,[1,2]))
    event.remove(engine,'before_cursor_execute',simultaneous_update)
    assert sorted(r.status_code for _,r in results)==[200,409]
    value,r=next((v,r) for v,r in results if r.status_code==200)
    assert c.post(path,headers=h,json=value).json()==r.json()
    root=path.rsplit('/',1)[0]
    assert c.get(root+'/annotation-operations/'+value['operation_id'],headers=h).json()==r.json()
    value['note']='different';assert c.post(path,headers=h,json=value).status_code==409
    assert len(c.get(path+'/'+b['annotation_id']+'/history',headers=h).json()['revisions'])==2
    with factory() as db:
        assert db.execute(text('select count(*) from annotation_events_v1')).scalar()==2


def test_ct_bytes_tamper_does_not_pass_dicom_read(ctx):
    c,h,_,path,_,_,_,run=ctx
    url=path.rsplit('/',1)[0]+'/dicom'
    assert c.get(url,headers=h).status_code==200
    (run/'TEST_STORAGE/generated-ct.dcm').write_bytes(b'not dicom')
    assert c.get(url,headers=h).status_code==503


def test_body_is_actually_bounded_missing_or_chunked_length_rejected(ctx):
    c,h,_,path,_,*_=ctx
    large=b'x'*131073
    assert c.post(path,headers=h,content=large).status_code==413
    assert c.post(path,headers={**h,'Content-Length':'1'},content=large).status_code==413
    assert c.post(path,headers=h,content=iter([b'{}'])).status_code==411


def test_case_and_revision_quotas_are_atomic_and_keep_history(ctx):
    from backend_v2.annotation_v1.api import MAX_ANNOTATIONS,MAX_REVISIONS
    c,h,_,path,b,factory,_,_=ctx
    for _ in range(MAX_ANNOTATIONS):
        value=dict(b,annotation_id=str(uuid.uuid4()),operation_id=str(uuid.uuid4()))
        assert c.post(path,headers=h,json=value).status_code==200
    assert c.post(path,headers=h,json=b).status_code==409
    first=c.get(path,headers=h).json()['items'][0]
    for version in range(1,MAX_REVISIONS):
        value=dict(b,annotation_id=first['annotation_id'],operation_id=str(uuid.uuid4()),expected_version=version)
        assert c.post(path,headers=h,json=value).status_code==200
    value.update(expected_version=MAX_REVISIONS,operation_id=str(uuid.uuid4()))
    assert c.post(path,headers=h,json=value).json()['code']=='ANNOTATION_QUOTA_REACHED'
    history=c.get(path+'/'+first['annotation_id']+'/history',headers=h).json()
    assert len(history['revisions'])==len(history['events'])==MAX_REVISIONS
    assert len(c.get(path,headers=h).json()['items'])==MAX_ANNOTATIONS
    with factory() as db:
        assert db.execute(text('select count(*) from annotation_events_v1')).scalar()==MAX_ANNOTATIONS+MAX_REVISIONS-1


def test_generated_child_run_identity_before_mount(ctx,tmp_path):
    *_,run=ctx
    assert validate_generated_run(run,require_local=False)['scope']=='SYNTHETIC_ONLY'
    with pytest.raises(ValueError,match='TASK_LOCAL'):validate_generated_run(run)
    p=run/'private-config.json';config=json.loads(p.read_bytes());config['scope']='REAL'
    p.write_text(json.dumps(config));p.chmod(0o600)
    with pytest.raises(ValueError,match='IDENTITY_DRIFT'):validate_generated_run(run,require_local=False)


def test_gateway_csrf_owner_and_localhost_cookie_isolation(ctx):
    import httpx
    from session_gateway.app import Settings, create_app as gateway_app, COOKIE
    _,_,_,path,b,_,app,run=ctx
    config=json.loads((run/'private-config.json').read_bytes());origin=config['origin']
    gateway=gateway_app(Settings(origin,'http://127.0.0.1:8890',run/'accounts.json',run/'gateway-test.sqlite',run/'session.key'),backend_transport=httpx.ASGITransport(app=app()))
    with TestClient(gateway,base_url=origin) as client:
        client.cookies.set(COOKIE,'old-host-session',domain='127.0.0.1',path='/')
        account=config['accounts']['synthetic-doctor']
        login=client.post('/auth/login',headers={'Origin':origin},json=account)
        assert login.status_code==200
        assert 'Domain=' not in login.headers['set-cookie']
        assert client.cookies.get(COOKIE,domain='127.0.0.1')=='old-host-session'
        assert client.get('/auth/session').status_code==200
        assert client.get('https://127.0.0.1:8890/auth/session').status_code==401
        assert client.post(path,headers={'Origin':origin},json=b).status_code==403
        csrf=login.json()['csrf_token']
        assert client.post(path,headers={'Origin':origin,'X-CSRF-Token':csrf},json=b).status_code==200
        account=config['accounts']['synthetic-observer']
        login=client.post('/auth/login',headers={'Origin':origin},json=account)
        assert client.get(path).status_code==403
        assert client.post(path,headers={'Origin':origin,'X-CSRF-Token':login.json()['csrf_token']},json=dict(b,operation_id=str(uuid.uuid4()))).status_code==403


def test_concurrent_new_annotations_cannot_exceed_case_quota(ctx):
    from backend_v2.annotation_v1.api import MAX_ANNOTATIONS
    c,h,_,path,b,factory,app,_=ctx
    for _ in range(MAX_ANNOTATIONS-1):
        assert c.post(path,headers=h,json=dict(b,annotation_id=str(uuid.uuid4()),operation_id=str(uuid.uuid4()))).status_code==200
    barrier=Barrier(2)
    def submit(_):
        value=dict(b,annotation_id=str(uuid.uuid4()),operation_id=str(uuid.uuid4()))
        with TestClient(app()) as client:
            barrier.wait(timeout=5)
            return client.post(path,headers=h,json=value)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,[1,2]))
    assert sorted(r.status_code for r in results)==[200,409]
    with factory() as db:
        for table in ['annotation_heads_v1','annotation_revisions_v1','annotation_events_v1']:
            assert db.execute(text('select count(*) from '+table)).scalar()==MAX_ANNOTATIONS
