"""Optional explicit LOC-source synthetic integration; no patient/model loader."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import types
import httpx
import pytest
from fastapi.testclient import TestClient
from backend_v2.tests.test_phase1 import ctx, USER_TOKEN, WORKER_TOKEN
from backend_v2.tests.test_next_application import request_for, TestTransport, DATA, H
from backend_v2.api.app import app
from backend_v2.services.common import digest
from epilocate_next.contracts import ApplicationRequest, Budget
from epilocate_next.runner import ApplicationRunner, HandlerContext
from epilocate_next.e2_adapter import E2HandlerAdapter, PreparedBinding, CoreBudgetAdapter
from worker.next_application import ApplicationWorkerAgent, ApplicationWorkerClient, ApplicationWorkerConfig


def test_core_budget_completed_step_and_backward_deadline_are_preserved():
    tick=[0.0];context=HandlerContext(Budget(forward=2,backward=2,updates=2,seconds=1,output_bytes=1000),clock=lambda:tick[0])
    adapter=CoreBudgetAdapter(context)
    context.forward();tick[0]=1.2;adapter.did_optimizer_step()
    assert context.update_count==1 and not adapter.permits()
    assert context.stop_events[0]['elapsed_seconds']==1.2
    tick[0]=0;context=HandlerContext(context.budget,clock=lambda:tick[0]);adapter=CoreBudgetAdapter(context)
    def delayed_backward():tick[0]=1.1
    with pytest.raises(Exception,match='TIMEOUT'):adapter.backward_call(delayed_backward)
    assert context.backward_count==1 and context.update_count==0


@pytest.mark.skipif(not os.environ.get('EPI_NEXT_SYNTHETIC_LOC_ROOT'),reason='LOC source must be explicitly supplied')
def test_actual_loc_synthetic_handler_worker_save_refresh(ctx,tmp_path,monkeypatch):
    # Load the LOC-owned code in a distinct namespace. Never copy its algorithms.
    root=Path(os.environ['EPI_NEXT_SYNTHETIC_LOC_ROOT']).resolve()
    namespace='epinext_loc_application_synthetic'
    package=types.ModuleType(namespace);package.__path__=[str(root)];sys.modules[namespace]=package
    modules=['e2_handler_v4.py','hspi_core_v3.py','first_real_e1_e2.py','preprocessed_localization.py','hspi.py','localization.py','verification_vnext.py']
    hashes={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in modules}
    lock=json.loads((root.parent/'configs/e2-handler-dependency-lock-v4.json').read_bytes())
    assert all(value==lock['module_sha256']['epi_next/'+name] for name,value in hashes.items())
    core=importlib.import_module(namespace+'.e2_handler_v4');prep=importlib.import_module(namespace+'.preprocessed_localization')
    np=importlib.import_module('numpy');torch=importlib.import_module('torch')
    class Generated2D(torch.nn.Module):
        def forward(self,x):
            signal=x.mean(dim=(1,2,3))*.01
            return torch.stack((signal,signal+1),dim=1)
    f,store,ids=ctx;req=request_for(f,ids)
    config=core.HSPIConfig(mode='E2-CT',image_size=(32,32),grids=(2,3),stages=1,steps=2,reference_grid=2,epsilon=1,masking_policy='preserve_exterior')
    req['config_sha256']=config.sha256();req['budget'].update(forward=6,backward=4,updates=4,seconds=10)
    image=np.ones((32,32),dtype=np.float32)
    prepared=prep.Prepared2DInput(image,np.ones_like(image,dtype=bool),hashlib.sha256(image.tobytes()).hexdigest(),req['model']['preprocessing_version'],req['task']['definition_id'])
    geometry=dict(native_shape_rc=[32,32],native_slice_index_zero_based=0,native_to_model_zyx=np.eye(4).tolist(),model_to_native_zyx=np.eye(4).tolist(),model_shape_yx=[32,32])
    binding=PreparedBinding(prepared,geometry,H,req['model']['preprocessing_sha256'],req['input']['geometry_ledger_sha256'],req['input']['mapping_qa_sha256'])
    handler=E2HandlerAdapter(core.run_prepared_e2,lambda *_:binding,lambda _:Generated2D(),lambda _:config,model_adapter_sha256='9'*64,stop_exception=core.BudgetStopped)
    monkeypatch.setattr(app.state,'next_algorithms_enabled',True,raising=False)
    monkeypatch.setattr(app.state,'next_algorithm_worker_ids',{ids[4]},raising=False)
    monkeypatch.setattr(app.state,'next_algorithm_request_digests',{digest(ApplicationRequest.model_validate(req).model_dump(mode='json'))},raising=False)
    monkeypatch.setattr(store,'read',lambda key:(store.objects[key],'image/png'))
    with TestClient(app) as api:
        auth={'Authorization':'Bearer '+USER_TOKEN,'Idempotency-Key':'loc-generated-one-run'}
        created=api.post('/api/v2/jobs/algorithm',json=req,headers=auth);assert created.status_code==202,created.text
        transport=TestTransport(api)
        client=ApplicationWorkerClient('https://backend.example',WORKER_TOKEN,model_id=req['model']['model_id'],transport=transport)
        runner=ApplicationRunner({'E2':handler},tmp_path/'preserved')
        config_worker=ApplicationWorkerConfig(ids[4],'https://backend.example',WORKER_TOKEN,req['model']['checkpoint_sha256'],tmp_path/'worker')
        agent=ApplicationWorkerAgent(config_worker,client=client,runner=runner,download_transport=httpx.MockTransport(lambda _:httpx.Response(200,content=DATA)))
        try:agent.register();receipt=agent.run_once()
        finally:agent.stop()
        assert receipt['accepted'],receipt
        response=api.get('/api/v2/results/'+receipt['result_id'],headers=auth)
        body=response.json();assert body['source']=='SYNTHETIC',body
        out=body['application'];assert out['execution_status'] in {'SUCCESS','NO_RELIABLE_RESPONSE'},out
        assert (out['actual_forward'],out['actual_backward'],out['actual_updates'])==(6,4,4)
        assert out['source_artifacts']['prepared_input']!=H
        assert {'HSPI_CPF_GAP','HSPI_CPF_PSMI_PATCH_SUPPORT'}.issubset({l['layer_kind'] for l in out['layers']})
        # A two-step control may have no feasible Mask. Do not relax the
        # scientific threshold or manufacture one just to populate the UI.
        assert all(l['evidence_type']==l['layer_kind'] for l in out['layers'])
        for asset in body['assets']:
            read=api.get('/api/v2/results/'+receipt['result_id']+'/assets/'+asset['asset_id'],headers=auth)
            assert hashlib.sha256(read.content).hexdigest()==asset['sha256']
        assert api.get('/api/v2/results/'+receipt['result_id'],headers=auth).json()==body
        assert transport.submits==1
        saved=tmp_path/'preserved'/body['job_id']/'e2-handler-result.json.gz'
        assert (saved.parent/'trace.jsonl.gz').exists() and list(saved.parent.glob('checkpoint-*.json.gz'))
        # Exercise the same application chain in explicit zero-model replay.
        from epilocate_next.e2_replay import ReplayBinding,E2PrecomputedAdapter
        import copy
        replay_req=copy.deepcopy(req);replay_req['execution_mode']='PRECOMPUTED';replay_req['budget'].update(forward=0,backward=0,updates=0)
        source_sha=hashlib.sha256(saved.read_bytes()).hexdigest()
        replay_binding=ReplayBinding(saved,source_sha,H,prepared.input_sha256,'9'*64,out['source_artifacts']['core'],req['input']['geometry_ledger_sha256'],req['input']['mapping_qa_sha256'])
        monkeypatch.setattr(app.state,'next_algorithm_request_digests',{digest(ApplicationRequest.model_validate(replay_req).model_dump(mode='json'))},raising=False)
        replay_created=api.post('/api/v2/jobs/algorithm',json=replay_req,headers=auth);assert replay_created.status_code==202,replay_created.text
        replay_runner=ApplicationRunner({'E2':E2PrecomputedAdapter(lambda _:replay_binding)},tmp_path/'preserved',permit_real=True,context_factory=lambda q:HandlerContext(q.budget),model_id=req['model']['model_id'],hardware={'accelerator':'NONE','max_concurrent_jobs':1})
        replay_agent=ApplicationWorkerAgent(config_worker,client=client,runner=replay_runner,download_transport=httpx.MockTransport(lambda _:httpx.Response(200,content=DATA)))
        try:replay_receipt=replay_agent.run_once()
        finally:replay_agent.stop()
        replay_body=api.get('/api/v2/results/'+replay_receipt['result_id'],headers=auth).json()
        replay_output=replay_body['application']
        assert replay_body['source']=='PRECOMPUTED'
        assert (replay_output['actual_forward'],replay_output['actual_backward'],replay_output['actual_updates'])==(0,0,0)
        assert replay_output['diagnostics']['source_evidence_type']=='SYNTHETIC'
        assert replay_output['source_artifacts']['precomputed_source_result']==source_sha
        assert replay_output['layers']==out['layers']
        assert api.get('/api/v2/results/'+replay_receipt['result_id'],headers=auth).json()==replay_body
        assert transport.submits==2
    assert hashes=={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in modules}
    evidence=os.environ.get('EPI_NEXT_SMOKE_RECEIPT_DIRECTORY')
    if evidence:
        report=dict(scope='SYNTHETIC_LOC_CORE_APPLICATION_CHAIN',medical_forward=0,medical_backward=0,medical_updates=0,synthetic_forward=6,synthetic_backward=4,synthetic_updates=4,source_hashes=hashes,configuration_sha256=req['config_sha256'],terminal=out['execution_status'],assets=[dict(asset_id=a['asset_id'],sha256=a['sha256']) for a in body['assets']],job_id=body['job_id'],result_id=body['result_id'],precomputed_replay=dict(source='SYNTHETIC',actual_forward=0,actual_backward=0,actual_updates=0,result_id=replay_receipt['result_id'],source_result_sha256=source_sha))
        (Path(evidence)/'loc-synthetic-chain.json').write_text(json.dumps(report,indent=2)+'\n')
