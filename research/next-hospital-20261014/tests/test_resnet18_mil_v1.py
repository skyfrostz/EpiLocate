"""New 2D seams only. Existing generated HU fixtures, random ResNet18, CPU1."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest
import torch

from epi_next import ctfm_research_pipeline_v4 as p
from epi_next import resnet18_mil_v1 as m
from epi_next.encoder import CaseLinearHead


from test_ctfm_research_v4 import generated

@pytest.fixture(scope='module')
def generated_rows(generated):
    _, rows, _, _, _, _, _, _, manifest_sha = generated
    return rows, manifest_sha


def test_actual_hu_bag_preprocessing_and_native_sampling(generated_rows):
    rows,_=generated_rows
    images,geo=m.prepare_bag(rows[0],p.Meter('cache'))
    assert images.shape==(8,3,224,224) and images.dtype==torch.float32
    assert geo['indices_Z']==[4,12,20,28,36,44,52,60]
    assert geo['crop']=='NONE' and geo['unit']=='HU_ALREADY_RESCALED_ONCE'
    assert m.sample_indices(65)==[4,12,20,28,36,44,52,60]
    # First synthetic HU=-900 except unsampled voxel0: windowed scalar is .3.
    expected=(torch.tensor(.3)-torch.tensor([.485,.456,.406]))/torch.tensor([.229,.224,.225])
    torch.testing.assert_close(images[:, :, 0, 0],expected.expand(8,3),atol=1e-6,rtol=0)
    with pytest.raises(p.Blocked):m.sample_indices(7)
    print('generated bag8 / native mapping / HU preprocessing PASS')


def test_random_resnet_slice_gradient_preserves_eval_and_frozen_parameters():
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(17)
        backbone=m.build_backbone()  # NO existing weights/checkpoint is loaded.
        head=CaseLinearHead(512,2)
    predictor=m.build_slice_predictor(backbone,head)
    predictor.train(True)
    assert all(not module.training for module in predictor.modules())
    before={k:v.clone() for k,v in backbone.state_dict().items() if 'running_' in k}
    scalar=torch.linspace(.05,.95,224*224).reshape(1,1,224,224).requires_grad_()
    logits=predictor(scalar)
    assert logits.shape==(1,2) and logits.dtype==torch.float32
    (logits[0,1]-logits[0,0]).backward()
    assert scalar.grad is not None and torch.isfinite(scalar.grad).all() and scalar.grad.abs().max()>0
    assert all(v.grad is None and not v.requires_grad for v in predictor.parameters())
    assert all(torch.equal(v,backbone.state_dict()[k]) for k,v in before.items())
    with pytest.raises(p.Blocked,match='NO_BAG_SUBSTITUTION'):
        predictor(torch.ones(8,1,224,224))
    print(f'random_ResNet18_input_gradient_maxabs={float(scalar.grad.abs().max())!r}; frozen BN unchanged')


def test_loc_v5_contract_blocks_bag_label_and_scope():
    model_binding=dict(model_sha256='a'*64,preprocessing_sha256='b'*64,adapter_sha256='c'*64,
                       task_version=m.config()['task'])
    target=dict(policy='DECLARED_FIXED',declared_class=1)
    request=m.slice_contract(model_binding,target)
    assert request['contract_sha256']==m.LOC_SHA and request['source_label'] is None
    assert request['loss_definition']['optimization_objective']=='ALL_LOGITS'
    assert request['loss_definition']['response_metric']=='FIXED_TARGET_LOGIT_MARGIN'
    for source,scope in ((dict(class_id=1,scope='BAG'),'SLICE'),(None,'BAG')):
        with pytest.raises(p.Blocked):m.slice_contract(model_binding,target,source,scope)
    with pytest.raises(p.Blocked):m.slice_contract(model_binding,dict(policy='DECLARED_FIXED',declared_class=True))
    with pytest.raises(p.Blocked):m.slice_contract(dict(model_binding,model_sha256='bad'),target)
    assert m.resolve_loc_target([[2.,1.]],dict(policy='ORIGINAL_ARGMAX_FIXED',declared_class=0))['resolved_class']==0
    assert m.resolve_loc_target([[2.,1.]],dict(policy='DECLARED_FIXED',declared_class=1))['predicted_class']==0
    with pytest.raises(p.Blocked,match='TARGET_MISMATCH'):
        m.resolve_loc_target([[2.,1.]],dict(policy='ORIGINAL_ARGMAX_FIXED',declared_class=1))
    with pytest.raises(p.Blocked,match='FINITE_SINGLE_SLICE'):
        m.resolve_loc_target([[2.,float('nan')]],dict(policy='DECLARED_FIXED',declared_class=0))


def test_2d_cache_fit_restore_eval_single_new_generated_seam(generated_rows,tmp_path):
    rows,manifest_sha=generated_rows
    class GeneratedBackbone:
        def __init__(self):self.calls=0
        def __call__(self,images):
            self.calls+=1
            assert images.shape==(8,3,224,224)
            feature=images.mean((1,2,3))[:,None]*torch.linspace(.5,1.5,512)[None,:]
            feature[:,0]=.125
            return feature
    backend=GeneratedBackbone();cm=p.Meter('cache')
    context=dict(backbone_sha256='a'*64,config_sha256=p.digest(p.encoded(m.config())),source_commit='a'*40,
                 evidence_type='GENERATED_BACKEND_NO_RESNET_WEIGHTS')
    cache=m.cache_phase(rows,manifest_sha,context,tmp_path/'cache',backend,cm)
    assert backend.calls==60 and cm.returned_forward==60 and cache['slice_evaluations']==480
    assert all(np.load(row['gap']['path'],allow_pickle=False).shape==(1,512) for row in cache['rows'])
    cache_ref=dict(path=str(tmp_path/'cache/cache-receipt.json'),sha256=p.file_sha(tmp_path/'cache/cache-receipt.json'))
    tm=p.Meter('train');gap=m.read_cache(cache,rows,manifest_sha,tm)
    mask=np.array([r['split']=='train_weak' for r in rows]);labels=[r['task_label'] for r in rows]
    head,losses=m.fit_head(gap,labels,mask,tm)
    assert (tm.returned_forward,tm.returned_backward,tm.returned_updates)==(100,100,100)
    np.testing.assert_array_equal(head.mean.numpy(),torch.from_numpy(gap[mask]).float().mean(0).numpy())
    checkpoint=m.save_head(head,losses,cache_ref,cache,tmp_path/'head',tm)
    em=p.Meter('evaluate');restored=m.restore_head(checkpoint,em)
    for name,value in head.state_dict().items():
        torch.testing.assert_close(value.double(),restored.state_dict()[name],rtol=0,atol=0)
    evaluation=m.evaluate_phase(restored,gap,rows,em)
    assert em.returned_forward==2 and em.backward==0
    assert len(evaluation['predictions'])==60
    assert evaluation['metrics']['train_weak']['model']['n']==40
    assert evaluation['metrics']['val_classification']['model']['n']==20
    assert evaluation['metrics']['val_classification']['source_subgroups']['CAP']['n']==5
    assert evaluation['metrics']['val_classification']['source_subgroups']['CAP']['discrimination_metrics']=='UNDEFINED_SINGLE_SOURCE_CLASS'
    assert all(r['prediction_scope']=='BAG' and r['source_label']['scope']=='BAG' for r in evaluation['predictions'])
    assert not evaluation['clinical_accuracy_claim'] and not evaluation['independent_test_claim']
    # Verify MIL mean-logit equality for nonidentical synthetic per-slice features.
    slice_features=np.arange(8*512,dtype=np.float64).reshape(8,512)/100
    with torch.no_grad():
        each=restored(torch.from_numpy(slice_features)).numpy()
        pooled=restored(torch.from_numpy(slice_features.mean(0,keepdims=True))).numpy()
    error=float(np.abs(each.mean(0)-pooled[0]).max())
    np.testing.assert_allclose(each.mean(0),pooled[0],atol=1e-8,rtol=1e-12)
    print(f'MIL_mean_logits_maxabs={error!r}; generated-only cache60/fit100/eval2; medical calls0')
    # Consumer changing a split/input/cache identity cannot silently reuse features.
    bad=copy.deepcopy(cache);bad['rows'][0]['identity']['split_manifest_sha']='b'*64
    with pytest.raises(p.Blocked,match='VERSION_INPUT_SPLIT'):m.read_cache(bad,rows,manifest_sha,p.Meter('train'))
    bad=copy.deepcopy(checkpoint);bad['state']['linear.bias']['sha256']='0'*64
    with pytest.raises(p.Blocked,match='HEAD_SHA'):m.restore_head(bad,p.Meter('evaluate'))
    # Save raw integration result locally; never report generated metrics as real performance.
    (tmp_path/'generated-seam.json').write_bytes(p.encoded(dict(scope='GENERATED_ONLY',losses=losses,
        calls=dict(cache=cm.report(),train=tm.report(),evaluate=em.report()),mil_maxabs=error,
        real_checkpoint_load=0,real_CT_read=0,MPS_calls=0)))


def test_candidate_and_partial_fit_rejected_without_training(tmp_path):
    with pytest.raises(p.Blocked,match='EXACT_APPROVED'):
        m.validate_request(dict(schema='R18_MIL_CANDIDATE_CONFIG_V1'))
    meter=p.Meter('train')
    with pytest.raises(p.Blocked,match='NO_PARTIAL_REAL'):
        m.save_head(CaseLinearHead(512,2),[.5],{}, {},tmp_path/'head',meter)
    assert meter.forward==meter.backward==meter.updates==0 and not (tmp_path/'head').exists()
    with pytest.raises(p.Blocked,match='FEATURE_LABEL_TYPES'):
        m.fit_head(np.zeros((60,512),np.float64),[1.0]*60,np.array([True]*40+[False]*20),meter)
    assert meter.forward==meter.backward==meter.updates==0


def test_cli_missing_authority_stops_before_shared_slot_or_model(monkeypatch,tmp_path):
    monkeypatch.setattr(p,'bound_json',lambda *args: {})
    monkeypatch.setattr(m,'validate_request',lambda request: request)
    def forbidden(*args):
        raise AssertionError('must not reserve slot or load model without exact authority')
    monkeypatch.setattr(p,'load_shared',forbidden)
    monkeypatch.setattr(m,'build_backbone',forbidden)
    args=['--request',str(tmp_path/'metadata-only.json'),'--request-sha','a'*64]
    assert m.main(args)==3
    assert m.main(args+['--execute'])==3
