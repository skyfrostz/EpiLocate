"""Affected-seam/generated tests only; no patient input or medical model access."""
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
import pytest
import torch
from epi_next.preprocessed_localization import Prepared2DInput
from epi_next.e2_handler_v4 import digest, semantics, input_binding, selected_fidelity as old_fidelity
from epi_next.e2_handler_v5 import selected_fidelity, run_prepared_e2
from epi_next.e2_readout_v5 import run_readout, construct_regions, NAMES
from epi_next.e2_readout_request_v5 import validate_request_value
from epi_next.e2_request_v4 import config_from_request
from epi_next.hspi_core_v3 import Budget, upsample, source_sha
from epi_next.target_contract_v5 import resolve, response_metrics, validate_persisted, validate_metadata

ROOT = Path(__file__).parents[1]
torch.set_num_threads(1)


class Generated(torch.nn.Module):
    def __init__(self):
        super().__init__(); self.weight = torch.nn.Parameter(torch.tensor(.01)); self.calls = 0
    def forward(self, x):
        self.calls += 1
        score = 1+x.mean((1,2,3))*self.weight
        return torch.stack([score*0,score],1)
    def numpy(self, x):
        return self(torch.from_numpy(x)[None,None]).detach().numpy()[0]


@pytest.fixture
def setup():
    request = json.loads((ROOT/'configs/e2-r-readout-v5.json').read_bytes())
    request['profile'] = 'GENERATED_E2_READOUT_V5'
    config = config_from_request(request)
    image = np.ones((224,224),np.float32); valid = np.ones_like(image,dtype=bool)
    prepared = Prepared2DInput(image,valid,hashlib.sha256(image.tobytes()).hexdigest(),'generated-preproc','generated-slice-task')
    identity = {'classifier_kind':'2D_SLICE_CLASSIFIER', 'model_sha256':'a'*64,
        'preprocessing_sha256':'b'*64,'model_adapter_sha256':'c'*64}
    mask = torch.zeros(1,1,7,7); mask.flatten()[43] = .9
    vals = mask.flatten().sort(descending=True).values
    base = [[0.,float(torch.tensor(1.)+torch.tensor(.01))]]
    soft = upsample(mask,(224,224),'bilinear',False)
    full = [[0.,float(1+soft.mean()*.01)]]
    payload = {'schema':'E2_VERIFIED_STAGE1_REUSE_V4','case_index':3,'grid':7,'stage':1,
        'verification':'FULL_TRACE_CPF_AND_SAME_STEP_MASK_VERIFIED','core_sha256':source_sha(),
        'branch_semantics':semantics(config),'input_binding':input_binding(prepared,identity),
        'observed_iterations':10000,'optimizer_updates':10000,'feasible_count':1,
        'baseline_logits':base,'best':{'epoch':3604,'mask':mask.tolist(), 'logits':full,
            'ls':float(((np.asarray(base)-full)**2).sum()),
            'lm':float(mask.abs().mean()),'gap':float(vals[0]-vals[1])}}
    identity['reused_stage1_sha256'] = digest(payload)
    request['reuse_payload_canonical_sha256'] = digest(payload)
    request['input_binding'] = input_binding(prepared,identity)
    request['target_contract']['model_binding'] = {**{k:identity[k] for k in ('model_sha256','preprocessing_sha256','model_adapter_sha256')},'task_version':'GENERATED_ONLY'}
    model = Generated()
    saved = old_fidelity(prepared,model,config,payload,identity=identity)
    saved['source_binding'] = request['saved_fidelity']['source_binding']
    raw = json.dumps(saved).encode()
    request['saved_fidelity']['file_sha256'] = hashlib.sha256(raw).hexdigest()
    geometry = {'schema':'EPI_NEXT_2D_NATIVE_LEDGER_V1','status':'TECHNICAL_PASS',
        'model_shape_yx':[224,224],'native_shape_rc':[512,512], 'native_slice_index_zero_based':123,
        'model_to_native_zyx':np.diag([1.,512/224,512/224,1.]).tolist(),
        'native_to_model_zyx':np.diag([1.,224/512,224/512,1.]).tolist()}
    # native_lookup requires exact slice translation, no inference from array size.
    geometry['model_to_native_zyx'][0][3] = 123
    geometry['model_to_native_zyx'][1][3] = (512/224-1)/2
    geometry['model_to_native_zyx'][2][3] = (512/224-1)/2
    geometry['native_to_model_zyx'] = np.linalg.inv(geometry['model_to_native_zyx']).tolist()
    return prepared,identity,config,payload,request,raw,geometry


def test_contract_mismatch_prediction_and_scope(setup):
    p,i,c,payload,r,raw,g = setup
    meta = r['target_contract']; resolved = resolve(meta,payload['baseline_logits'])
    assert resolved['predicted_class'] == resolved['explanation_target']['resolved_class'] == 1
    wrong = copy.deepcopy(meta); wrong['explanation_target']['declared_class'] = 0
    with pytest.raises(ValueError,match='DECLARED_RESOLVED'): resolve(wrong,payload['baseline_logits'])
    wrong['explanation_target']['policy'] = 'DECLARED_FIXED'
    other = resolve(wrong,payload['baseline_logits'])
    assert other['predicted_class'] == 1 and other['explanation_target']['resolved_class'] == 0
    wrong['prediction_scope'] = 'BAG'
    with pytest.raises(ValueError,match='SLICE'): validate_metadata(wrong)
    for key in ('explanation_target','predicted_class','source_label','loss_definition'):
        changed = copy.deepcopy(resolved); changed[key] = 'changed'
        with pytest.raises(ValueError,match='PERSISTED'): validate_persisted(meta,changed,payload['baseline_logits'])


def test_saturation_and_fixed_target():
    row = response_metrics([[0.,1000.]],[[1000.,0.]],1)
    assert row['fixed_target'] == 1 and row['perturbed_predicted_class'] == 0
    assert row['margin_drop'] == 2000 and row['probability_drop'] == 1
    tiny = response_metrics([[0.,1000.]],[[0.,999.]],1)
    assert tiny['probability_drop'] == 0 and tiny['margin_drop'] == 1


def test_v5_reject_before_calls_and_fresh_first_baseline(setup):
    p,i,c,payload,r,raw,g = setup
    meta = copy.deepcopy(r['target_contract']); meta['explanation_target']['declared_class'] = 0
    model = Generated()
    with pytest.raises(ValueError,match='DECLARED_RESOLVED'):
        selected_fidelity(p,model,c,payload,target_contract=meta,identity=i)
    assert model.calls == 0
    meter = Budget()
    with pytest.raises(ValueError,match='DECLARED_RESOLVED'):
        run_prepared_e2(p,model,g,c,target_contract=meta,identity=i,budget=meter)
    assert model.calls == meter.forward == 1 and meter.backward == 0
    valid = selected_fidelity(p,Generated(),c,payload,target_contract=r['target_contract'],identity=i)
    assert valid['schema'] == 'E2_SELECTED_FIDELITY_V5' and valid['cost']['forward'] == 5
    assert valid['target_contract']['explanation_target']['resolved_class'] == 1


def test_fov_ties_random_rounding_and_equal_area():
    valid = np.array([[1,0,1,1],[1,1,0,1],[1,1,1,1]],bool)
    soft = np.ones(valid.shape,np.float32); peak = np.zeros_like(valid); peak[0,:] = True
    regions = construct_regions(soft,peak,valid); indices = np.flatnonzero(valid)
    permutation = np.random.Generator(np.random.PCG64(17)).permutation(indices)
    for percent in (5,10,20):
        n = valid.sum()*percent//100
        ranked = regions[f'ranked_{percent}_keep']; random = regions[f'random_{percent}_keep']
        assert ranked.sum() == random.sum() == n
        assert np.array_equal(np.flatnonzero(ranked),indices[:n])
        assert set(np.flatnonzero(random)) == set(permutation[:n])
        assert not (ranked & ~valid).any()
        assert np.array_equal(regions[f'ranked_{percent}_remove'],valid & ~ranked)


def test_readout_counts_reuse_spatial_and_frozen_flags(setup):
    p,i,c,payload,r,raw,g = setup
    model = Generated(); model.train(); meter = Budget(max_forward=18,max_backward=0)
    meter.forward = 2
    out = run_readout(p,model,g,c,payload,request=r,identity=i,saved_fidelity_bytes=raw,adapter_predict=model.numpy,budget=meter)
    assert out['status'] == 'SUCCESS',out['error']
    assert out['new_cost']['forward'] == model.calls == 14 and out['cumulative_meter_cost']['forward'] == 16
    assert out['new_cost']['backward'] == out['new_cost']['optimizer_steps'] == 0
    assert out['historical_logits_reused'] == 4 and list(out['responses']) == NAMES
    assert len(out['adapter_checks']) == 2 and not out['unrun_objects']
    assert model.training and model.weight.requires_grad and model.weight.grad is None
    for percent, n in ((5,2508),(10,5017),(20,10035)):
        for method in ('ranked','random'):
            row = out['responses'][f'{method}_{percent}_keep']
            assert row['selected_pixels'] == n and row['native_region'].shape == (512,512)
    assert {row['fixed_target'] for row in out['responses'].values()} == {1}


def test_preflight_and_adaptation_fail_closed(setup):
    p,i,c,payload,r,raw,g = setup
    model = Generated()
    with pytest.raises(ValueError,match='FILE_MISMATCH'):
        run_readout(p,model,g,c,payload,request=r,identity=i,saved_fidelity_bytes=raw+b' ',adapter_predict=model.numpy)
    assert model.calls == 0
    def mismatch(x): return model.numpy(x)+np.array([0.,.01])
    out = run_readout(p,model,g,c,payload,request=r,identity=i,saved_fidelity_bytes=raw,adapter_predict=mismatch)
    assert out['status'] == 'FAILED' and out['new_cost']['forward'] == model.calls == 2
    assert not out['responses'] and out['error']['message'].startswith('ADAPTER_OR_SAVED')


def test_partial_and_inflight_deadline(setup):
    p,i,c,payload,r,raw,g = setup
    model = Generated()
    out = run_readout(p,model,g,c,payload,request=r,identity=i,saved_fidelity_bytes=raw,adapter_predict=model.numpy,budget=Budget(max_forward=4))
    assert out['status'] == 'PARTIAL_BUDGET' and model.calls == 4 and out['unrun_objects']
    clock = [0.]
    class Slow(Generated):
        def forward(self,x): clock[0] += 121; return super().forward(x)
    model = Slow()
    out = run_readout(p,model,g,c,payload,request=r,identity=i,saved_fidelity_bytes=raw,adapter_predict=model.numpy,budget=Budget(clock=lambda:clock[0]))
    assert out['status'] == 'PARTIAL_BUDGET' and model.calls == 1 and not out['responses']


def test_encoder_input_gradient_preserved(setup):
    p,i,c,payload,r,raw,g = setup
    from epi_next.hspi_core_v3 import frozen_classifier
    model = Generated(); initial = model.weight.detach().clone()
    x = torch.ones(1,1,224,224,requires_grad=True)
    with frozen_classifier(model): model(x)[0,1].backward()
    assert x.grad is not None and float(x.grad.abs().sum()) > 0
    assert model.weight.grad is None and torch.equal(model.weight,initial) and model.weight.requires_grad


def test_declared_fixed_metrics_and_case_reference_remain_separate(setup):
    p,i,c,payload,r,raw,g = setup
    meta = copy.deepcopy(r['target_contract'])
    meta['explanation_target'] = {'policy':'DECLARED_FIXED','declared_class':0}
    meta['source_label'] = {'class_id':1,'label':'case_source_reference',
        'scope':'CASE','provenance_sha256':'d'*64}
    out = selected_fidelity(p,Generated(),c,payload,target_contract=meta,identity=i)
    assert out['target_contract']['predicted_class'] == 1
    assert out['target_contract']['source_label'] == meta['source_label']
    assert {row['fixed_target'] for row in out['responses'].values()} == {0}
    assert out['responses']['original']['target_logit_margin'] < 0
    assert out['cost']['forward'] == 5


def test_public_template_rejects_real_bindings_and_generated_policy_rejection(setup):
    r = json.loads((ROOT/'configs/e2-r-readout-v5.json').read_bytes())
    with pytest.raises(ValueError,match='LEGACY_SCIENCE_DRIFT'):
        validate_request_value(r)
    r=setup[4]
    validate_request_value(r,synthetic=True)
    for field in ('rounding','rank_ties','random','fill'):
        wrong = copy.deepcopy(r); wrong['readout_policy'][field] = 'changed'
        with pytest.raises(ValueError,match='POLICY'): validate_request_value(wrong,synthetic=True)
    wrong = copy.deepcopy(r); wrong['authority'] = 'APPROVED'
    with pytest.raises(ValueError,match='AUTHORITY'): validate_request_value(wrong)


def test_two_dimensional_encoder_contract_keeps_case_and_slice_semantics_distinct():
    contract = json.loads((ROOT/'configs/two-dimensional-encoder-localization-interface-v1.json').read_bytes())
    assert contract['supervision']['slice_label'].startswith('UNAVAILABLE')
    assert 'never copy case/bag label' in contract['supervision']['prohibition']
    assert contract['predictor_contract']['bag_explanation'].startswith('requires separately versioned adapter')
    assert 'absolute logit losses' in contract['matched_algorithm_comparison']['interpretation']
    assert contract['matched_algorithm_comparison']['E1'].startswith('same fixed 16/32/64')
