"""Generated DB/PNG scope attacks. Never opens historical DB, DICOM or weights."""
import copy
import json
from pathlib import Path
import os
import signal
import subprocess
import sys
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend_v2.db.base import make_engine
from backend_v2.models.entities import InferenceResult, InferenceJob, Slice, Asset
from backend_v2.tests.test_local_mvp_readonly import fixture
from qa import local_mvp_readonly as legacy
from qa import local_mvp_demo64 as demo


def generated(tmp_path):
    binding, old_token = fixture(tmp_path)
    rows = []
    engine = make_engine('sqlite:///'+binding['source_db']['path'])
    with Session(engine) as db:
        for i, result in enumerate(db.scalars(select(InferenceResult)), 1):
            job = db.get(InferenceJob, result.job_id); sl = db.get(Slice, job.slice_id)
            assets = list(db.scalars(select(Asset).where(Asset.result_id == result.id).order_by(Asset.asset_id)))
            summaries = []; expected = {}
            for n, scale in enumerate((16, 32, 64)):
                summary = dict(block_size=scale)
                for k, (kind, field) in enumerate((('candidate','candidate_layer'),('response','response_layer'),('comparison','comparison_grid_layer'))):
                    a = assets[3*n+k]; a.asset_id=f'{kind}-{scale}.png'
                    summary[field] = dict(asset_id=a.asset_id, layer_kind=a.layer_kind, coordinate_space=a.coordinate_space, width=a.width, height=a.height)
                    if scale == 64: expected[a.asset_id]=dict(object_key=a.object_key,sha256=a.sha256)
                summaries.append(summary)
            result.result_json = dict(result.result_json, scale_summaries=summaries,
                                      cross_scale=[dict(scales=[16,32,64])], secret_auxiliary_16='MUST_NOT_LEAK')
            rows.append(dict(case_index=i,case_id=result.result_json['case_id'],slice_id=sl.slice_ref,
                result_id='result_'+result.id.hex,job_id=job.public_id,input_sha256=sl.source_sha256,assets=expected))
        db.commit()
    engine.dispose()
    binding['source_db']['sha256']=legacy.sha(binding['source_db']['path'])
    bp=tmp_path/'legacy-binding.json';bp.write_text(json.dumps(binding))
    policy=dict(schema='MVP_DEMO64_PROJECTION_V1',permission_scope='LOCAL_MVP_ONLY',allowed_scale=64,
        records=rows,model=dict(model_id='baseline_resnet18',checkpoint_sha256='a'*64,preprocessing_version='GEN',protocol_id='GEN'),
        original_binding=dict(path=str(bp),sha256=legacy.sha(bp)))
    return binding, policy, old_token


def ready(tmp_path, monkeypatch):
    binding,policy,old_token=generated(tmp_path)
    config=demo.restrict_config(legacy.prepare_run(binding,tmp_path/'run'),policy)
    import backend_v2.api.app as api
    monkeypatch.setattr(api,'ObjectStore',api.ObjectStore)
    for name in config['environment']:monkeypatch.setenv(name,os.environ.get(name,''))
    client=TestClient(demo.backend_app(config))
    token=(tmp_path/'run/user.env').read_text().strip().split('=',1)[1]
    return binding,policy,config,client,dict(Authorization='Bearer '+token),old_token


def test_exact_reads_refresh_auth_and_projection(tmp_path,monkeypatch):
    binding,policy,config,client,headers,old=ready(tmp_path,monkeypatch)
    assert len(config['object_sha256'])==12
    for row in policy['records']:
        url='/api/v2/results/'+row['result_id']
        assert client.get(url).status_code==401
        assert client.get(url,headers={'Authorization':'Bearer '+old}).status_code==401
        result=client.get(url,headers=headers);assert result.status_code==200
        assert result.json()==client.get(url,headers=headers).json()
        body=result.json();assert [s['block_size'] for s in body['scale_summaries']]==[64]
        assert body['cross_scale']==[] and 'secret_auxiliary_16' not in body
        assert {a['asset_id'] for a in body['assets']}==set(row['assets'])
        for a in body['assets']:assert client.get(a['asset_url'],headers=headers).status_code==200
        assert client.get('/api/v2/cases/'+row['case_id'],headers=headers).status_code==200
        assert client.get('/api/v2/cases/'+row['case_id']+'/dicom',headers=headers).status_code==200
    assert legacy.sha(binding['source_db']['path'])==binding['source_db']['sha256']


def test_direct_bypass_routes_methods_queries_and_store(tmp_path,monkeypatch):
    _,policy,config,client,headers,_=ready(tmp_path,monkeypatch)
    row=policy['records'][0];url='/api/v2/results/'+row['result_id']
    forbidden=['/api/v2/cases','/api/v2/cases/other','/api/v2/results/other','/api/v2/jobs/'+row['job_id'],
        '/api/v2/workers/register','/generated-object/input0','/api/v2/predictions/other',
        url+'/positions?scale=16',url+'/positions?scale=64',url+'?scale=16',url+'?scale=64&scale=16',
        url+'/assets/candidate-16.png',url+'/assets/response-32.png',url+'/assets/unknown.png',
        url+'/assets/%2e%2e%2fcandidate-64.png',url+'/assets/candidate-64.png?download=1']
    for path in forbidden:
        for method in ['GET','HEAD','POST','PUT','PATCH','DELETE']:
            assert client.request(method,path,headers=headers).status_code==403,(method,path)
    for path in [url,'/api/v2/cases/'+row['case_id'],url+'/assets/candidate-64.png','/api/v2/jobs/occlusion','/api/v2/jobs/algorithm']:
        for method in ['POST','PUT','PATCH','DELETE']:assert client.request(method,path,headers=headers).status_code==403
    store=legacy.ReadonlyStore(config)
    for k in ['asset-0-0','asset-0-4','../input0','unlisted']:
        with pytest.raises(ValueError,match='OUTSIDE'):store.read(k)


@pytest.mark.parametrize('field',['job_id','input_sha256','model','asset'])
def test_projection_drift_stops_before_service(tmp_path,field):
    binding,policy,_=generated(tmp_path);config=legacy.prepare_run(binding,tmp_path/'run')
    if field=='model':policy['model']['checkpoint_sha256']='b'*64
    elif field=='asset':policy['records'][0]['assets']['candidate-64.png']['sha256']='c'*64
    else:policy['records'][0][field]='wrong'
    with pytest.raises(ValueError):demo.restrict_config(config,policy)


def test_live_result_drift_is_refused(tmp_path,monkeypatch):
    _,policy,config,client,headers,_=ready(tmp_path,monkeypatch)
    engine=make_engine(config['environment']['EPILOCATE_V2_DATABASE_URL'])
    with Session(engine) as db:
        r=db.scalar(select(InferenceResult));r.result_json=dict(r.result_json,model_version='b'*64);rid='result_'+r.id.hex;db.commit()
    engine.dispose()
    assert client.get('/api/v2/results/'+rid,headers=headers).status_code==403


def test_generated_https_full_service_and_owned_cleanup(tmp_path):
    import httpx
    binding,policy,_=generated(tmp_path)
    dist=tmp_path/'dist';dist.mkdir();(dist/'index.html').write_text('<html><body>GENERATED DEMO64</body></html>')
    plan=tmp_path/'generated-plan.json';plan.write_text(json.dumps(dict(frozen=dict(dist=str(dist)),policy=policy)))
    run=tmp_path/'services'
    program='import json,sys; from pathlib import Path; from qa.local_mvp_demo64 import serve; d=json.load(open(sys.argv[1])); serve(d["frozen"],d["policy"],Path(sys.argv[2]))'
    p=subprocess.Popen([sys.executable,'-c',program,str(plan),str(run)],cwd=demo.ROOT,
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(demo.ROOT)+os.pathsep+os.environ.get('PYTHONPATH','')),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        deadline=time.monotonic()+20
        while not (run/'restore-ready.json').exists():
            assert p.poll() is None;assert time.monotonic()<deadline;time.sleep(.05)
        c=json.loads((run/'private-config.json').read_text())
        with httpx.Client(base_url=c['origin'],verify=str(run/'tls.crt'),trust_env=False) as client:
            assert 'GENERATED DEMO64' in client.get('/mvp/').text
            login=client.post('/auth/login',headers={'Origin':c['origin']},json=dict(username=c['username'],password=c['password']))
            assert login.status_code==200
            assert client.get('/api/v2/cases?limit=1').status_code==403
            assert client.get('/api/v2/cases/').status_code==403
            row=policy['records'][0];url='/api/v2/results/'+row['result_id']
            assert client.get(url).status_code==200
            assert len(client.get(url).json()['assets'])==3
            assert client.get(url+'/assets/response-64.png').status_code==200
            assert client.get(url+'/assets/response-16.png').status_code==403
            assert client.post('/api/v2/jobs/occlusion',json={}).status_code==403
            assert client.get('/generated-object/input0').status_code==403
            assert client.post('/auth/logout',headers={'Origin':c['origin'],'X-CSRF-Token':login.json()['csrf_token']}).status_code==204
            assert client.get(url).status_code==401
    finally:
        if p.poll() is None:p.send_signal(signal.SIGTERM)
        _,stderr=p.communicate(timeout=12)
    assert p.returncode==0,stderr.decode()
    receipt=json.loads((run/'restore-exit.json').read_text())
    assert receipt['source_db_unchanged'] and receipt['model_calls']==0 and receipt['worker_started'] is False
    assert len(receipt['owned_services'])==3 and all(x['exit_code'] is not None for x in receipt['owned_services'])
