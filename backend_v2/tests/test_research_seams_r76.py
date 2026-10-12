"""Generated saved-result seams only: no CT, weights, torch or medical calls."""
import copy
import hashlib
import io
import itertools
import json
import uuid
from pathlib import Path

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend_v2.api.app import app
from backend_v2.research_application import create_research_app
from backend_v2.services.common import digest
from backend_v2.tests.test_phase1 import ctx, USER_TOKEN, WORKER_TOKEN
from backend_v2.tests.test_next_application import request_for, TestTransport, DATA, H
from epilocate_next.contracts import ApplicationRequest, Prediction
from epilocate_next.e2_replay import ReplayBinding
from epilocate_next.e2_adapter_v5 import E2PrecomputedAdapterV5, check_raw_target
from epilocate_next.f0_replay import F0PrecomputedAdapter, F0ReplayBinding
from epilocate_next.research_contract import (ResearchBinding, ResearchHandler, expected_target,
    request_digest, validate_research_output, validate_research_wire_result, TARGET_SPEC_SHA)
from epilocate_next.runner import ApplicationRunner, HandlerContext
from worker.next_application import ApplicationWorkerAgent, ApplicationWorkerClient, ApplicationWorkerConfig

SPEC = Path('/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-localization/research/next-hospital-20261014/configs/explanation-target-contract-v5.json')


def target_metadata(req, policy='DECLARED_FIXED'):
    raw = SPEC.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == TARGET_SPEC_SHA
    return dict(schema=json.loads(raw)['schema'], prediction_scope='SLICE',
        class_labels=req.task.class_labels, source_label=dict(class_id=0, label='generated case source',
            scope='CASE', provenance_sha256='8'*64),
        explanation_target=dict(policy=policy, declared_class=req.task.target_class),
        loss_definition=json.loads(raw)['loss_definition'],
        model_binding=dict(model_sha256=req.model.checkpoint_sha256,
            preprocessing_sha256=req.model.preprocessing_sha256, model_adapter_sha256='9'*64,
            task_version=req.task.definition_id))


def replay_request(factory, ids, mode='E2'):
    req = request_for(factory, ids, mode)
    req['execution_mode'] = 'PRECOMPUTED'
    req['task']['target_class'] = 0  # Legal DECLARED_FIXED explanation != predicted class1.
    req['budget'].update(forward=0, backward=0, updates=0, output_bytes=4*1024*1024)
    return ApplicationRequest.model_validate(req)


def e2_saved(req, directory):
    metadata = target_metadata(req)
    pred = Prediction(logits=[-1, 1], predicted_class=1, class_label=req.task.class_labels[1])
    binding = ResearchBinding(digest(req.model_dump(mode='json')), metadata, SPEC)
    grid = [[0.0]*32 for _ in range(32)]
    raw = dict(schema='EPI_NEXT_E2_HANDLER_V5', evidence_type='SYNTHETIC',
        config_sha256=req.config_sha256, core_sha256='7'*64,
        input_binding=dict(input_sha256='6'*64, model_sha256=req.model.checkpoint_sha256,
            preprocessing_sha256=req.model.preprocessing_sha256, model_adapter_sha256='9'*64),
        original_logits=[[-1, 1]], original_class=1, execution_status='NO_RELIABLE_RESPONSE',
        native_space=dict(native_slice_index=0, scores=grid, reliable=grid),
        optimized_input_masks=[], candidates=[], method='GENERATED_E2_V5', psmi={},
        planned_branches=[], full_plan_completed=True, skipped_branches=[], unrun_branches=[],
        candidate_provisional=False, reused_historical_observations=[],
        new_cost=dict(forward=6, backward=4, optimizer_steps=4, elapsed_seconds=.01),
        target_contract=expected_target(req, metadata, SPEC, pred), publishable_target_metadata=True)
    path = directory/'generated-e2-v5.json'; path.write_text(json.dumps(raw))
    replay = ReplayBinding(path, hashlib.sha256(path.read_bytes()).hexdigest(), H, '6'*64,
                           '9'*64, '7'*64, 'd'*64, 'e'*64)
    return raw, binding, replay


def f0_saved(req, directory):
    req.task.definition_id='COVIDCTMD_SOURCE_CASE_WEAK_BINARY_V1'
    req.task.class_labels=['Normal_SOURCE','COVID-19_OR_CAP_SOURCE']
    def save(name, value, array=False):
        path = directory/name
        if array:
            stream = io.BytesIO(); np.save(stream, value, allow_pickle=False); path.write_bytes(stream.getvalue())
        else:
            path.write_text(json.dumps(value))
        return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    affine = np.eye(4)
    centers = np.array(list(itertools.product(range(4), repeat=3)), dtype=float)
    geometry = save('geometry.json', dict(native_shape_ZYX=[1,32,32], native_to_lps=affine.tolist(),
        nominal_feature_to_native=affine.tolist()))
    source = '5'*40; manifest = 'b'*64
    features = np.zeros((1,512,4,4,4), dtype=np.float32)
    features[:,0,:,:,0]=-1;features[:,0,:,:,1]=1
    feature_header = json.dumps(dict(shape=list(features.shape),dtype='float32'),
                                sort_keys=True,separators=(',', ':')).encode()
    identity = dict(input_sha=H, model_sha=req.model.encoder_sha256,
        preprocess_sha=req.model.preprocessing_sha256, geometry_sha=geometry['sha256'],
        config_sha=req.config_sha256, code_sha=source, split_manifest_sha=manifest, split='train')
    identity.update(study_key=req.input.study_id,series_key=req.input.series_id)
    stream = io.BytesIO()
    np.savez(stream, features=features, metadata=np.frombuffer(json.dumps(dict(identity=identity,
        feature_sha=hashlib.sha256(feature_header+features.tobytes()).hexdigest())).encode(), dtype=np.uint8))
    path = directory/'features.npz'; path.write_bytes(stream.getvalue())
    feature = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    gap = save('gap.npy', np.zeros((1,512),dtype=np.float64), True)
    cache = save('cache.json',dict(schema='CTFM_RESEARCH_CACHE_RECEIPT_V4',status='PASS',
        evidence_type='SYNTHETIC', model_sha256=req.model.encoder_sha256,
        config_sha256=req.config_sha256, source_commit=source, data_manifest_sha256=manifest,
        rows=[dict(record_id='generated-source', source_group_id='generated-group',
            split='train_weak', task_label=0, source_diagnosis='Normal',
            identity=identity, input=dict(sha256=H),feature=feature,gap=gap,geometry=geometry)]))
    weight=np.zeros((2,512),dtype=np.float32);weight[:,0]=1
    state = {name:save(name+'.npy',value,True) for name,value in {
        'mean':np.zeros(512,dtype=np.float32), 'scale':np.ones(512,dtype=np.float32),
        'linear.weight':weight,
        'linear.bias':np.array([-1,1],dtype=np.float32)}.items()}
    head = save('head.json',dict(schema='CTFM_RESEARCH_HEAD_CHECKPOINT_V4',status='PASS',
        evidence_type='SYNTHETIC', state=state, data_manifest_sha256=manifest,
        cache_receipt_sha256=cache['sha256'],model_sha256=req.model.encoder_sha256,
        final_update=100,seed=17,threshold=.5,tie='Normal'))
    signed = np.zeros((1,2,4,4,4),dtype=np.float64)
    signed[:, :, :, :, 0] = -1; signed[:, :, :, :, 1] = 1
    contribution = save('signed.npy',signed,True)
    version = dict(backbone_sha256=req.model.encoder_sha256,head_checkpoint_sha256=head['sha256'],
        feature_cache_receipt_sha256=cache['sha256'],data_manifest_sha256=manifest,
        source_commit=source,config_sha256=req.config_sha256,seed=17,
        precision='FP32 feature/train, FP64 GAP/evaluation/contribution')
    evaluation = save('evaluation.json',dict(schema='CTFM_RESEARCH_EVALUATION_V4',status='PASS',
        evidence_type='SYNTHETIC', calls=dict(attempted_forward=2),
        F0=[dict(record_id='generated-source',raw_logits=[-1,1],predicted_class=1,
            positive_probability=float(1/(1+np.exp(-2))),effective_bias=[-1,1],
            signed_contribution=contribution, geometry=geometry, geometry_valid=True,
            native_nominal_centers_ZYX=centers.tolist(),LPS_centers_mm=centers.tolist(),
            model_version=version)]))
    q = req.model_copy(deep=True)
    q.model.head_sha256=head['sha256'];q.input.geometry_ledger_sha256=geometry['sha256']
    app_binding=dict(case_id=req.input.case_id,study_id=req.input.study_id,series_id=req.input.series_id,
        slice_id=req.input.slice_id,input_sha256=req.input.input_sha256,display_sha256=req.input.display_sha256)
    replay = F0ReplayBinding(evaluation,head,cache,'generated-source',manifest,source,directory,app_binding)
    sources = dict(head=head['sha256'],evaluation=evaluation['sha256'],cache_receipt=cache['sha256'],
        spatial_features=feature['sha256'],gap512=gap['sha256'],geometry=geometry['sha256'],
        signed_contribution=contribution['sha256'],data_manifest=manifest,input=H)
    f0_identity=dict(record_id='generated-source',source_group_id='generated-group',
        data_manifest_sha256=manifest,study_key=identity['study_key'],series_key=identity['series_key'],
        head_sha256=head['sha256'],cache_receipt_sha256=cache['sha256'],source_commit=source,
        application_binding=app_binding)
    binding = ResearchBinding(request_digest(q), f0_sources=sources, f0_identity=f0_identity)
    return q, binding, replay


@pytest.mark.parametrize('mode',['E2','CTFM'])
def test_generated_precomputed_backend_save_refresh(ctx,tmp_path,monkeypatch,mode):
    factory,store,ids=ctx;req=replay_request(factory,ids,mode)
    if mode=='E2':
        _,binding,replay=e2_saved(req,tmp_path)
        adapter=E2PrecomputedAdapterV5(lambda _:replay,lambda _:binding)
    else:
        req,binding,replay=f0_saved(req,tmp_path)
        adapter=F0PrecomputedAdapter(lambda _:replay)
        monkeypatch.setattr(app.state,'next_algorithm_input_resolver',
            lambda db,user,q,sl:dict(object_key='generated-input',sha256=H,expires_at=sl.staging_expires_at),raising=False)
    monkeypatch.setattr(app.state,'next_algorithms_enabled',True,raising=False)
    monkeypatch.setattr(app.state,'next_algorithm_worker_ids',{ids[4]},raising=False)
    monkeypatch.setattr(app.state,'next_algorithm_request_digests',{binding.request_digest},raising=False)
    monkeypatch.setattr(store,'read',lambda key:(store.objects[key],'image/png'))
    research=create_research_app(lambda q:binding)
    research.dependency_overrides.update(app.dependency_overrides)
    with TestClient(research) as api:
        auth={'Authorization':'Bearer '+USER_TOKEN,'Idempotency-Key':'generated-r76'}
        response=api.post('/api/v2/jobs/algorithm',json=req.model_dump(mode='json'),headers=auth)
        assert response.status_code==202,response.text
        transport=TestTransport(api)
        client=ApplicationWorkerClient('https://generated.invalid',WORKER_TOKEN,
            model_id=req.model.model_id,transport=transport)
        runner=ApplicationRunner({mode:ResearchHandler(adapter,lambda _:binding)},tmp_path/'results',
            permit_real=True,context_factory=lambda q:HandlerContext(q.budget),
            model_id=req.model.model_id,hardware={'accelerator':'NONE','max_concurrent_jobs':1})
        config=ApplicationWorkerConfig(ids[4],'https://generated.invalid',WORKER_TOKEN,
            req.model.checkpoint_sha256,tmp_path/'worker')
        agent=ApplicationWorkerAgent(config,client=client,runner=runner,
            download_transport=httpx.MockTransport(lambda _:httpx.Response(200,content=DATA)))
        try:
            agent.register();receipt=agent.run_once()
        finally:
            agent.stop()
        assert receipt['accepted'],receipt
        rid=receipt['result_id'];body=api.get('/api/v2/results/'+rid,headers=auth).json()
        assert body['source']=='PRECOMPUTED'
        assert body['application']['diagnostics']['source_evidence_type']=='SYNTHETIC'
        assert [body['application'][k] for k in ('actual_forward','actual_backward','actual_updates')]==[0,0,0]
        assert api.get('/api/v2/results/'+rid,headers=auth).json()==body
        assert api.get('/api/v2/results/'+rid).status_code==401
        assert transport.submits==1
        saved=json.loads((tmp_path/'results'/body['job_id']/'result.json').read_text())
        validate_research_wire_result(saved,binding)
        if mode=='E2':
            contract=body['application']['diagnostics']['target_contract']
            assert contract['explanation_target']['resolved_class']==0 and contract['predicted_class']==1
            assert contract['source_label']['scope']=='CASE'  # Never promoted to slice truth.
        else:
            f0=body['application']['diagnostics']['f0']
            assert np.min(f0['signed_values'])==-1 and np.max(f0['signed_values'])==1
            assert f0['source_label']['scope']=='SOURCE_GROUP'
            assert body['application']['diagnostics']['research_contract']['f0_identity']==binding.f0_identity
        # Validate before mutation/storage, through the real independent submit route.
        corrupted=copy.deepcopy(saved)
        if mode=='E2':corrupted['application']['diagnostics']['target_contract']['explanation_target']['resolved_class']=1
        else:corrupted['application']['diagnostics']['f0']['effective_bias'][0]=99
        manifest=dict(outcome='SUCCEEDED',result=corrupted)
        headers={'Authorization':'Bearer '+WORKER_TOKEN,'X-Request-ID':str(uuid.uuid4())}
        rejected=api.post('/api/v2/workers/jobs/'+body['job_id']+'/result',
            files={'manifest':(None,json.dumps(manifest))},headers=headers)
        assert rejected.status_code==422,rejected.text
        assert rejected.json()['code']=='RESEARCH_RESULT_CONTRACT_REJECTED'
        assert api.get('/api/v2/results/'+rid,headers=auth).json()==body


@pytest.mark.parametrize('field',['target','scope','labels','source','loss','model'])
def test_e2_persisted_metadata_mutation_rejected(ctx,tmp_path,field):
    f,_,ids=ctx;req=replay_request(f,ids)
    raw,binding,_=e2_saved(req,tmp_path)
    if field=='target':raw['target_contract']['explanation_target']['resolved_class']=1
    if field=='scope':raw['target_contract']['prediction_scope']='BAG'
    if field=='labels':raw['target_contract']['class_labels'].reverse()
    if field=='source':raw['target_contract']['source_label']['scope']='SLICE'
    if field=='loss':raw['target_contract']['loss_definition']['optimization_objective']='TARGET_SCORE'
    if field=='model':raw['input_binding']['model_adapter_sha256']='0'*64
    with pytest.raises(ValueError):check_raw_target(req,raw,binding)


def test_argmax_policy_rejects_declared0_actual1_and_ties_are_first(ctx,tmp_path):
    f,_,ids=ctx;req=replay_request(f,ids);metadata=target_metadata(req,'ORIGINAL_ARGMAX_FIXED')
    p=Prediction(logits=[-1,1],predicted_class=1,class_label=req.task.class_labels[1])
    with pytest.raises(ValueError,match='DECLARED_RESOLVED'):expected_target(req,metadata,SPEC,p)
    p.logits=[1,1];p.predicted_class=0
    assert expected_target(req,metadata,SPEC,p)['predicted_class']==0
    metadata['prediction_scope']='BAG'
    with pytest.raises(ValueError,match='SCOPE'):expected_target(req,metadata,SPEC,p)


def test_failed_e2_keeps_bound_target_and_actual_completed_call(ctx,tmp_path):
    factory,_,ids=ctx;req=ApplicationRequest.model_validate(request_for(factory,ids))
    target=target_metadata(req)
    binding=ResearchBinding(request_digest(req),target,SPEC)
    context=HandlerContext(req.budget)
    def failed(*_):
        context.forward()
        raise RuntimeError('generated failure')
    output=ResearchHandler(failed,lambda _:binding)(req,None,tmp_path,context)
    assert output.result.execution_status=='FAILED'
    assert output.result.actual_forward==1 and output.result.prediction is None
    validate_research_output(req,output.result,binding)


@pytest.mark.parametrize('field',['head','gap','coordinate','signed','source_sha'])
def test_f0_handoff_tampering_is_rejected(ctx,tmp_path,field):
    f,_,ids=ctx;req,binding,replay=f0_saved(replay_request(f,ids,'CTFM'),tmp_path)
    if field=='head':req.model.head_sha256='0'*64
    elif field=='source_sha':replay.evaluation['sha256']='0'*64
    else:
        value=json.loads(Path(replay.evaluation['path']).read_text())
        if field=='coordinate':value['F0'][0]['LPS_centers_mm'][0][0]=999
        if field=='signed':value['F0'][0]['effective_bias'][0]=99
        if field=='gap':
            cached=json.loads(Path(replay.cache['path']).read_text())
            path=Path(cached['rows'][0]['gap']['path']);np.save(path,np.ones((1,512),dtype=np.float32))
        path=Path(replay.evaluation['path']);path.write_text(json.dumps(value))
        if field != 'source_sha':
            replay.evaluation['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        F0PrecomputedAdapter(lambda _:replay)(req,None,tmp_path,HandlerContext(req.budget))
