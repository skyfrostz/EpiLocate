"""Generated/injected application chain. No CT, weights or scientific model calls."""
import copy
import hashlib
import io
import json
from pathlib import Path
import uuid
import httpx
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import select
from backend_v2.tests.test_phase1 import ctx, seeded_case, USER_TOKEN, WORKER_TOKEN
from backend_v2.api.app import app
from backend_v2.models.entities import Asset, InferenceJob, JobAttempt, Slice, ModelVersion, Series, Study
from backend_v2.services.common import digest
from epilocate_next.contracts import ApplicationRequest, HandlerResult, validate_output
from epilocate_next.runner import ApplicationRunner, HandlerOutput, HandlerContext
from worker.next_application import ApplicationWorkerAgent, ApplicationWorkerClient, ApplicationWorkerConfig

DATA=b'generated-array-control-not-patient-data'
H=hashlib.sha256(DATA).hexdigest()

def request_for(factory,ids,mode='E2'):
    cid,sid=seeded_case(factory,ids)
    with factory.begin() as db:
        sl=db.scalar(select(Slice).where(Slice.slice_ref==sid));sl.source_sha256=H
        series=db.get(Series,sl.series_id);study=db.get(Study,series.study_id)
        model=db.get(ModelVersion,ids[2])
        return dict(schema_version='EPI_NEXT_APPLICATION_REQUEST_V1',algorithm_mode=mode,method_mode='E2-CT' if mode=='E2' else 'CTFM-VOLUME-HEAD',algorithm_version='injected-control-v1',config_sha256='c'*64,execution_mode='SYNTHETIC',input=dict(case_id=cid,study_id=study.study_ref,series_id=series.series_ref,slice_id=sid,input_sha256=H,display_sha256=H,scope='SINGLE_SLICE' if mode=='E2' else 'VOLUME',display_kind='DICOM' if mode=='E2' else 'RESEARCH_ARRAY',source_identity_status='SYNTHETIC',native_shape_zyx=[1,32,32],model_shape=[32,32] if mode=='E2' else [1,1,64,64,64],native_slice_index=0,affine_lps=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],geometry_ledger_sha256='d'*64,mapping_qa_sha256='e'*64,mapping_verified=True),model=dict(model_id=model.model_id,checkpoint_sha256=model.checkpoint_sha256,encoder_sha256='1'*64 if mode=='CTFM' else None,head_sha256='2'*64 if mode=='CTFM' else None,preprocessing_version=model.preprocessing_version,preprocessing_sha256='f'*64,protocol_id=model.protocol_id),task=dict(definition_id='generated-only',unit='SLICE' if mode=='E2' else 'SOURCE_CASE_SELECTED_SERIES',class_labels=['control-a','control-b'],target_class=1),budget=dict(forward=1,backward=0,updates=0,seconds=5,output_bytes=1024*1024))

def handler(status='SUCCESS',fail=False):
    def run(req,input_path,output_dir,context):
        assert input_path.read_bytes()==DATA
        if status!='NOT RUN':context.forward()
        if fail:raise RuntimeError('private exception details must not escape')
        evidence='HSPI_CPF_GAP' if req.algorithm_mode=='E2' else 'SIGNED_FEATURE_CONTRIBUTION'
        png=io.BytesIO();Image.new('L',(32,32),64).save(png,format='PNG')
        layer=dict(asset_id='control.png',layer_kind=evidence,evidence_type=evidence,width=32,height=32,coordinate_space='RAW_PIXEL_EDGE',origin='TOP_LEFT_PIXEL_EDGE',x_axis='RIGHT',y_axis='DOWN',display_interpolation_only=True,value_min=-1.0,value_max=1.0,raw_values=[[-1.0 if x<16 else 1.0 for x in range(32)] for _ in range(32)],display_sha256=H,geometry_ledger_sha256='d'*64,mapping_qa_sha256='e'*64,native_slice_index=0)
        artifacts={};diagnostics={}
        if req.algorithm_mode=='CTFM':
            artifacts=dict(spatial_features='3'*64,gap512='4'*64,head='2'*64);diagnostics=dict(spatial_features_shape=[1,512,4,4,4],gap_shape=[1,512])
        result=HandlerResult(execution_status=status,algorithm_status='GENERATED_'+status,reason=None if status=='SUCCESS' else 'generated refusal',prediction=dict(logits=[-1.0,1.0],predicted_class=1,class_label='control-b',probabilities=None),candidates=[],layers=[layer],actual_forward=1,actual_backward=0,actual_updates=0,runtime_seconds=0.01,source_artifacts=artifacts,diagnostics=diagnostics)
        if status=='NOT RUN':
            result.prediction=None;result.layers=[];result.actual_forward=0
        return HandlerOutput(result,{'control.png':png.getvalue()} if result.layers else {})
    return run

class TestTransport(httpx.BaseTransport):
    __test__=False
    def __init__(self,client):self.client=client;self.submits=0;self.queries=0;self.drop=False
    def handle_request(self,request):
        r=self.client.request(request.method,request.url.path,headers=dict(request.headers),content=request.read())
        if request.url.path.endswith('/result'):
            self.submits+=1
            if self.drop:raise httpx.ReadError('generated lost response',request=request)
        if request.url.path.endswith('/receipt'):self.queries+=1
        return httpx.Response(r.status_code,headers=r.headers,content=r.content,request=request)

@pytest.mark.parametrize('mode,status',[('E2','SUCCESS'),('E2','NO_RELIABLE_RESPONSE'),('E2','PARTIAL_BUDGET'),('E2','FAILED'),('E2','BLOCKED'),('E2','NOT RUN'),('CTFM','SUCCESS')])
def test_submit_handler_save_get_refresh_and_reconcile(ctx,tmp_path,monkeypatch,mode,status):
    factory,store,ids=ctx;req=request_for(factory,ids,mode)
    monkeypatch.setattr(app.state,'next_algorithms_enabled',True,raising=False)
    monkeypatch.setattr(app.state,'next_algorithm_worker_ids',{ids[4]},raising=False)
    monkeypatch.setattr(app.state,'next_algorithm_request_digests',{digest(ApplicationRequest.model_validate(req).model_dump(mode='json'))},raising=False)
    monkeypatch.setattr(store,'read',lambda key:(store.objects[key],'image/png'))
    if mode=='CTFM':
        def resolver(db,user,request,sl):return dict(object_key='generated-volume-only',sha256=H,expires_at=sl.staging_expires_at)
        monkeypatch.setattr(app.state,'next_algorithm_input_resolver',resolver,raising=False)
    with TestClient(app) as api:
        headers={'Authorization':'Bearer '+USER_TOKEN,'Idempotency-Key':'algorithm-'+mode+status}
        response=api.post('/api/v2/jobs/algorithm',json=req,headers=headers);assert response.status_code==202,response.text
        jid=response.json()['job_id'];assert api.post('/api/v2/jobs/algorithm',json=req,headers=headers).json()['job_id']==jid
        refreshed_headers=dict(headers,**{'Idempotency-Key':'refresh-new-uuid'})
        assert api.post('/api/v2/jobs/algorithm',json=req,headers=refreshed_headers).json()['job_id']==jid
        transport=TestTransport(api);transport.drop=True
        client=ApplicationWorkerClient('https://backend.example',WORKER_TOKEN,model_id=req['model']['model_id'],transport=transport)
        runner=ApplicationRunner({mode:handler(status)},tmp_path/'preserved')
        config=ApplicationWorkerConfig(ids[4],'https://backend.example',WORKER_TOKEN,req['model']['checkpoint_sha256'],tmp_path/'worker')
        agent=ApplicationWorkerAgent(config,client=client,runner=runner,download_transport=httpx.MockTransport(lambda _:httpx.Response(200,content=DATA)))
        agent.register();receipt=agent.run_once();agent.stop()
        assert receipt['accepted'] and transport.submits==transport.queries==1
        rid=receipt['result_id'];auth={'Authorization':'Bearer '+USER_TOKEN}
        first=api.get('/api/v2/results/'+rid,headers=auth);assert first.status_code==200,first.text
        assert api.get('/api/v2/results/'+rid,headers=auth).json()==first.json()
        body=first.json();assert body['source']=='SYNTHETIC' and body['application']['execution_status']==status
        assert body['application']['actual_forward']==(0 if status=='NOT RUN' else 1) and body['application_request']['algorithm_mode']==mode
        assert api.get('/api/v2/results/'+rid+'/assets/control.png',headers=auth).status_code==(404 if status=='NOT RUN' else 200)
        assert api.get('/api/v2/results/'+rid).status_code==401
        with factory() as db:
            job=db.scalar(select(InferenceJob).where(InferenceJob.public_id==jid));attempt=db.scalar(select(JobAttempt).where(JobAttempt.job_id==job.id));asset=db.scalar(select(Asset).where(Asset.result_id!=None))
            assert job.max_attempts==1 and job.attempt_no==1 and job.retry_count==0
            assert attempt.outcome=='SUCCEEDED' and attempt.submission_digest
            if status!='NOT RUN':assert asset.sha256==hashlib.sha256(store.objects[asset.object_key]).hexdigest()
        assert (tmp_path/'preserved'/jid/'result.json').exists()

def test_disabled_unbound_and_missing_volume_are_explicit(ctx,monkeypatch):
    f,_,ids=ctx;req=request_for(f,ids,'CTFM')
    with TestClient(app) as api:
        headers={'Authorization':'Bearer '+USER_TOKEN,'Idempotency-Key':'new-app-1234'}
        monkeypatch.setattr(app.state,'next_algorithms_enabled',False,raising=False)
        assert api.post('/api/v2/jobs/algorithm',json=req,headers=headers).json()['code']=='ALGORITHM_APPLICATION_DISABLED'
        monkeypatch.setattr(app.state,'next_algorithms_enabled',True,raising=False)
        monkeypatch.setattr(app.state,'next_algorithm_request_digests',set(),raising=False)
        assert api.post('/api/v2/jobs/algorithm',json=req,headers=headers).json()['code']=='ALGORITHM_REQUEST_NOT_BOUND'
        monkeypatch.setattr(app.state,'next_algorithm_request_digests',{digest(ApplicationRequest.model_validate(req).model_dump(mode='json'))},raising=False)
        monkeypatch.setattr(app.state,'next_algorithm_input_resolver',None,raising=False)
        assert api.post('/api/v2/jobs/algorithm',json=req,headers=headers).json()['code']=='VOLUME_INPUT_HANDOFF_REQUIRED'

def test_overtime_keeps_actual_time_and_diagnostic_layer(ctx):
    f,_,ids=ctx;r=ApplicationRequest.model_validate(request_for(f,ids));h=handler('PARTIAL_BUDGET')(r,FakePath(),None,HandlerContext(r.budget)).result
    h.runtime_seconds=5.7;h.stop_events=[dict(kind='TIME_BUDGET',elapsed_seconds=5.05,deadline_elapsed_seconds=5.0,new_work_after_stop=False)]
    h=HandlerResult.model_validate(h.model_dump());assert validate_output(r,h).runtime_seconds==5.7 and h.layers
    h.execution_status='SUCCESS'
    with pytest.raises(ValueError,match='OVERTIME'):validate_output(r,h)
class FakePath:
    def read_bytes(self):return DATA

def test_mode_masquerade_nonconformant_ingress_and_signed_values(ctx):
    f,_,ids=ctx;req=request_for(f,ids,'CTFM');bad=copy.deepcopy(req);bad['input']['model_shape']=[64,64]
    with pytest.raises(ValueError,match='CTFM_REQUIRES'):ApplicationRequest.model_validate(bad)
    req['input']['source_identity_status']='DICOM_ID_NONCONFORMANT';req['input']['display_kind']='DICOM'
    with pytest.raises(ValueError,match='NONCONFORMANT'):ApplicationRequest.model_validate(req)

def test_new_call_after_budget_stops_before_entry_and_no_job_replay(ctx,tmp_path):
    f,_,ids=ctx;req=ApplicationRequest.model_validate(request_for(f,ids));context=HandlerContext(req.budget);context.forward()
    with pytest.raises(Exception,match='FORWARD_BUDGET'):context.forward()
    assert context.forward_count==1
    with pytest.raises(Exception,match='STOP_ALREADY'):context.forward()

def test_legacy_worker_cannot_claim_application_and_runner_cannot_replay_job(ctx,tmp_path,monkeypatch):
    f,_,ids=ctx;req=request_for(f,ids)
    monkeypatch.setattr(app.state,'next_algorithms_enabled',True,raising=False)
    monkeypatch.setattr(app.state,'next_algorithm_request_digests',{digest(ApplicationRequest.model_validate(req).model_dump(mode='json'))},raising=False)
    monkeypatch.setattr(app.state,'next_algorithm_worker_ids',set(),raising=False)
    with TestClient(app) as api:
        created=api.post('/api/v2/jobs/algorithm',json=req,headers={'Authorization':'Bearer '+USER_TOKEN,'Idempotency-Key':'isolated-app-1234'})
        assert created.status_code==202
        claim_body=dict(worker_id=ids[4],available_capacity=1,supported_model_versions=[dict(model_id=req['model']['model_id'],checkpoint_sha256=req['model']['checkpoint_sha256'])])
        headers={'Authorization':'Bearer '+WORKER_TOKEN,'Idempotency-Key':str(uuid.uuid4()),'X-Request-ID':str(uuid.uuid4())}
        assert api.post('/api/v2/workers/jobs/claim',json=claim_body,headers=headers).status_code==204
        monkeypatch.setattr(app.state,'next_algorithm_worker_ids',{ids[4]},raising=False)
        headers['Idempotency-Key']=str(uuid.uuid4())
        claim=api.post('/api/v2/workers/jobs/claim',json=claim_body,headers=headers).json()
        runner=ApplicationRunner({'E2':handler()},tmp_path/'immutable')
        generated=tmp_path/'control.bin';generated.write_bytes(DATA)
        runner.run(claim,generated,None)
        claim['attempt_id']='different-attempt'
        with pytest.raises(FileExistsError):runner.run(claim,generated,None)

def test_world_bounds_preserve_zyx_and_left_right():
    from epilocate_next.e2_assets import world_bounds
    affine=[[0,0,-2,100],[0,3,0,-20],[5,0,0,7],[0,0,0,1]]
    low,high=world_bounds([2,4,3,6],1,affine)
    assert low==(89,-15.5,9.5) and high==(95,-9.5,14.5)
