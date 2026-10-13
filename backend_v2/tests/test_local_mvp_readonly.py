"""Generated saved-result reader, no Worker/model/DICOM decode/browser."""
import hashlib
import io
import json
import os
from pathlib import Path
from datetime import timedelta
import uuid
import subprocess
import sys
import time
import signal
import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from backend_v2.db.base import Base, make_engine
from backend_v2.models.entities import User, Patient, Case, Study, Series, Slice, ModelVersion, InferenceJob, InferenceResult, Asset, JobAttempt, WorkerNode
from backend_v2.services.common import now
from backend_v2.auth.credentials import issue_user_credential
from qa import local_mvp_readonly as reader


def fixture(tmp_path):
    source=tmp_path/'saved';source.mkdir();objects=source/'objects';objects.mkdir()
    engine=make_engine('sqlite:///'+str(source/'backend.sqlite'));Base.metadata.create_all(engine)
    inputs=[]
    with Session(engine) as db:
        user=User(auth_subject='generated_snapshot');model=ModelVersion(model_id='baseline_resnet18',version='GEN',checkpoint_sha256='a'*64,preprocessing_version='GEN',protocol_id='GEN')
        worker=WorkerNode(node_id='GEN_ONLY',token_hash='c'*64,display_name='GENERATED_NO_WORKER',supported_models=[])
        db.add_all([user,model,worker]);db.flush()
        _,old_token=issue_user_credential(db,user,expires_in=timedelta(hours=1))
        for n in range(3):
            raw=('GENERATED_NOT_DICOM_'+str(n)).encode();input_sha=hashlib.sha256(raw).hexdigest();inputs.append(input_sha)
            (objects/('input'+str(n))).write_bytes(raw);(objects/('input'+str(n)+'.media')).write_text('application/dicom')
            pat=Patient(owner_user_id=user.id,anonymous_id='patient-gen-'+str(n));db.add(pat);db.flush()
            case=Case(owner_user_id=user.id,patient_id=pat.id,anonymous_id='case-gen-'+str(n),status='READY');db.add(case);db.flush()
            study=Study(case_id=case.id,study_ref='study-gen-'+str(n));db.add(study);db.flush()
            series=Series(case_id=case.id,study_id=study.id,series_ref='series-gen-'+str(n));db.add(series);db.flush()
            sl=Slice(case_id=case.id,series_id=series.id,slice_ref='slice-gen-'+str(n),ordinal=0,width_px=32,height_px=32,source_sha256=input_sha,staging_object_key='input'+str(n),staging_expires_at=now()-timedelta(days=1));db.add(sl);db.flush()
            job=InferenceJob(public_id='job-gen-'+str(n),case_id=case.id,slice_id=sl.id,requested_by_user_id=user.id,model_version_id=model.id,kind='OCCLUSION',status='COMPLETED',request_json={},request_digest='a'*64,idempotency_key='gen-key-'+str(n));db.add(job);db.flush()
            attempt=JobAttempt(job_id=job.id,attempt_no=1,worker_node_id=worker.id,claim_key=uuid.uuid4(),claim_request_digest='d'*64,lease_token_hash='e'*64,leased_at=now(),lease_expire_time=now()+timedelta(seconds=30),outcome='SUCCEEDED');db.add(attempt);db.flush()
            row=InferenceResult(job_id=job.id,case_id=case.id,accepted_attempt_id=attempt.id,model_version_id=model.id,source='SYNTHETIC',result_json=dict(contract_version='2.0',source='SYNTHETIC',case_id=case.anonymous_id,slice_id=sl.slice_ref,kind='OCCLUSION',model_id='baseline_resnet18',model_version='a'*64,preprocessing_version='GEN',protocol_id='GEN',positions=[],scale_summaries=[],cross_scale=[]),metadata_json={},asset_manifest=[]);db.add(row);db.flush()
            for k in range(9):
                buffer=io.BytesIO();Image.new('L',(224,224),color=k).save(buffer,format='PNG');data=buffer.getvalue();key='asset-'+str(n)+'-'+str(k)
                (objects/key).write_bytes(data);(objects/(key+'.media')).write_text('image/png')
                db.add(Asset(result_id=row.id,asset_id='layer-'+str(k),object_key=key,layer_kind='MODEL_RESPONSE',width=224,height=224,coordinate_space='ALGORITHM_224',media_type='image/png',size_bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
        db.commit()
    engine.dispose()
    binding=dict(schema='LOCAL_MVP_READONLY_BINDING_V1',permission_scope='LOCAL_MVP_ONLY',mode='SYNTHETIC_TEST_ASSETS',source_db=dict(path=str(source/'backend.sqlite'),sha256=reader.sha(source/'backend.sqlite')),source_objects=str(objects),input_sha256=inputs,asset_count=27,source_sha256={str(Path(reader.__file__).resolve()):reader.sha(reader.__file__)})
    return binding,old_token


def config_and_client(tmp_path,monkeypatch):
    binding,old_token=fixture(tmp_path);config=reader.prepare_run(binding,tmp_path/'restored')
    for name in config['environment']:monkeypatch.setenv(name,os.environ.get(name,''))
    import backend_v2.api.app as api
    old_store=api.ObjectStore;monkeypatch.setattr(api,'ObjectStore',old_store)
    client=TestClient(reader.backend_app(config))
    token=(tmp_path/'restored/user.env').read_text().strip().split('=',1)[1]
    return binding,config,client,dict(Authorization='Bearer '+token),old_token


def test_saved_reads_fresh_auth_refresh_and_all_writes_refused(tmp_path,monkeypatch):
    binding,c,client,headers,old_token=config_and_client(tmp_path,monkeypatch)
    assert client.get('/api/v2/cases').status_code==401
    assert client.get('/api/v2/cases',headers=dict(Authorization='Bearer '+old_token)).status_code==401
    cases=client.get('/api/v2/cases',headers=headers);assert cases.status_code==200 and len(cases.json()['items'])==3
    for case in cases.json()['items']:
        raw=client.get('/api/v2/cases/'+case['case_id']+'/dicom',headers=headers)
        assert raw.status_code==200 and hashlib.sha256(raw.content).hexdigest() in binding['input_sha256']
    for rid in c['results']:
        first=client.get('/api/v2/results/'+rid,headers=headers);second=client.get('/api/v2/results/'+rid,headers=headers)
        assert first.status_code==200 and first.json()==second.json()
        layer=first.json()['assets'][0];assert client.get(layer['asset_url'],headers=headers).status_code==200
        assert client.get('/api/v2/results/'+rid+'/positions?scale=64',headers=headers).status_code==200
    for path in ['/api/v2/cases','/api/v2/cases/x/upload','/api/v2/predictions','/api/v2/jobs/occlusion','/api/v2/jobs/algorithm','/api/v2/workers/claim']:
        assert client.post(path,headers=headers,json={}).status_code==403
    assert client.get('/api/v2/workers/anything',headers=headers).status_code==403
    assert client.delete('/api/v2/cases/anything',headers=headers).status_code==403
    assert reader.sha(binding['source_db']['path'])==binding['source_db']['sha256']
    assert c['renewed_input_read_leases']==3


def test_object_integrity_original_preservation_and_no_clobber(tmp_path,monkeypatch):
    binding,c,client,headers,_=config_and_client(tmp_path,monkeypatch)
    assert reader.sha(binding['source_db']['path'])==binding['source_db']['sha256']
    with pytest.raises(FileExistsError):reader.prepare_run(binding,tmp_path/'restored')
    store=reader.ReadonlyStore(c)
    with pytest.raises(ValueError,match='READ_ONLY'):store.put(b'new','image/png','x')
    with pytest.raises(ValueError,match='OUTSIDE'):store.read('../outside')
    key=next(k for k in c['object_sha256'] if k.startswith('asset'))
    (Path(c['source_objects'])/key).write_bytes(b'GENERATED_TAMPER')
    with pytest.raises(ValueError,match='SHA_DRIFT'):store.read(key)
    assert b'\xe5\x8f\xaa\xe8\xaf\xbb' in reader.static_html(b'<body></body>')


def test_scope_and_binding_drift_are_rejected(tmp_path):
    binding,_=fixture(tmp_path);binding['input_sha256'][0]='0'*64
    with pytest.raises(ValueError,match='CASE_SCOPE'):reader.prepare_run(binding,tmp_path/'wrong')
    binding['permission_scope']='HOSPITAL'
    with pytest.raises(ValueError,match='LOCAL_MVP'):reader.validate_binding(binding)


def test_generated_loopback_https_login_saved_result_and_owned_exit(tmp_path):
    import httpx
    binding,_=fixture(tmp_path)
    dist=tmp_path/'dist';dist.mkdir();(dist/'index.html').write_text('<html><body><div id="app">GENERATED STATIC ONLY</div></body></html>')
    binding['dist']=str(dist);raw=json.dumps(binding).encode();path=tmp_path/'binding.json';path.write_bytes(raw)
    run=reader.ROOT/'.local'/('readonly-generated-service-'+uuid.uuid4().hex)
    proc=subprocess.Popen([sys.executable,str(Path(reader.__file__).resolve()),'--binding',str(path),'--binding-sha',hashlib.sha256(raw).hexdigest(),
                            '--run-directory',str(run),'--dist',str(dist),'--serve'],cwd=reader.ROOT,
                           env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(reader.ROOT)+os.pathsep+os.environ.get('PYTHONPATH','')),
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        deadline=time.monotonic()+15
        while not (run/'restore-ready.json').exists():
            assert proc.poll() is None
            assert time.monotonic()<deadline
            time.sleep(.05)
        c=json.loads((run/'private-config.json').read_bytes())
        with httpx.Client(verify=str(run/'tls.crt'),trust_env=False,base_url=c['origin']) as client:
            while True:
                assert proc.poll() is None
                try:
                    if client.get('/auth/session').status_code==401:break
                except httpx.HTTPError:pass
                assert time.monotonic()<deadline;time.sleep(.05)
            assert '只读历史结果' in client.get('/mvp/').text
            login=client.post('/auth/login',headers={'Origin':c['origin']},json=dict(username=c['username'],password=c['password']))
            assert login.status_code==200
            result=client.get('/api/v2/results/'+c['results'][0]);assert result.status_code==200
            assert client.get('/api/v2/results/'+c['results'][0]).json()==result.json()
            assert client.post('/api/v2/jobs/occlusion',json={}).status_code==403
            assert client.get('/generated-object/input0').status_code==403
    finally:
        if proc.poll() is None:proc.send_signal(signal.SIGTERM)
        stdout,stderr=proc.communicate(timeout=8)
    assert proc.returncode==0,stderr.decode()
    exit_receipt=json.loads((run/'restore-exit.json').read_bytes())
    assert len(exit_receipt['owned_services'])==3 and all(row['exit_code'] is not None for row in exit_receipt['owned_services'])
    assert exit_receipt['source_db_unchanged'] and not exit_receipt['worker_started'] and exit_receipt['model_calls']==0
    assert reader.sha(binding['source_db']['path'])==binding['source_db']['sha256']
