import io
import json
import numpy as np
import pytest
import torch
from torch import nn
from epi_next.encoder import (
    CaseLinearHead, FeatureCache, FrozenEncoderAdapter, HeadConfig, ModelUnavailable,
    class_contribution_map, feature_cache_key, fit_patient_head, load_ctfm_local, scale_hu,
)


def test_freezing_preserves_mask_gradient_and_batchnorm():
    backbone = nn.Sequential(nn.Conv3d(1, 3, 1), nn.BatchNorm3d(3))
    adapter = FrozenEncoderAdapter(backbone)
    adapter.train()
    before = backbone[1].running_mean.clone()
    mask = torch.ones(1, 1, 3, 4, 5, requires_grad=True)
    adapter.extract(mask, preserve_input_grad=True).square().sum().backward()
    assert mask.grad is not None and mask.grad.abs().sum() > 0
    assert all(p.grad is None and not p.requires_grad for p in backbone.parameters())
    assert torch.equal(before, backbone[1].running_mean)
    assert not backbone.training and not adapter.training
    assert not adapter.extract(mask).requires_grad
    assert adapter.actual_queries == 2


def test_map_equals_logits_with_nontrivial_standardization():
    torch.manual_seed(17)
    x = torch.randn(2, 4, 3, 5, 7, dtype=torch.float64)
    head = CaseLinearHead(4).double()
    head.mean.copy_(torch.tensor([0.4, -1., 2., 3.]))
    head.scale.copy_(torch.tensor([0.5, 1.2, 3., 5.]))
    for t in (0, 1):
        cam = class_contribution_map(x, head, t)
        torch.testing.assert_close(cam.mean((1, 2, 3)) + head.linear.bias[t], head(x)[:, t], atol=1e-12, rtol=1e-12)


def fixture_inputs():
    return torch.tensor([[-2., 1.], [-1., 2.], [1., 4.], [2., 3.], [100., 100.]]), torch.tensor([0, 0, 1, 1, 1]), list('abcde'), ['train'] * 4 + ['observed_validation']


def test_patient_train_only_and_seed_determinism():
    x, y, patients, splits = fixture_inputs()
    cfg = HeadConfig(epochs=12)
    first, log = fit_patient_head(x, y, patients, splits, cfg)
    x[-1] = 10000
    second, log2 = fit_patient_head(x, y, patients, splits, cfg)
    assert log == log2
    torch.testing.assert_close(first.mean, torch.tensor([0., 2.5]))
    assert all(torch.equal(v, second.state_dict()[k]) for k, v in first.state_dict().items())
    assert log['training_patients'] == 4
    assert len(log['losses']) == 12


@pytest.mark.parametrize('change', ['duplicate', 'sealed', 'unknown', 'legacy_validation', 'development', 'synthetic', 'labels', 'seed'])
def test_patient_boundary_rejections(change):
    x, y, patients, splits = fixture_inputs()
    seed = 17
    if change == 'duplicate': patients[-1] = patients[0]
    if change == 'sealed': splits[-1] = 'test'
    if change == 'unknown': splits[-1] = 'unknown'
    if change == 'legacy_validation': splits[-1] = 'validation'
    if change == 'development': splits[-1] = 'development'
    if change == 'synthetic': splits[-1] = 'synthetic'
    if change == 'labels': y[1] = -1
    if change == 'seed': seed = 19
    with pytest.raises(ValueError): fit_patient_head(x, y, patients, splits, HeadConfig(epochs=1), seed=seed)


def metadata():
    return dict(split='synthetic', **{k: 'a' * (40 if k == 'code_sha' else 64) for k in ['input_sha', 'model_sha', 'preprocess_sha', 'geometry_sha', 'config_sha', 'code_sha', 'split_manifest_sha']})


def test_cache_identity_integrity_and_no_overwrite(tmp_path):
    cache = FeatureCache(tmp_path)
    meta = metadata()
    x = torch.arange(24.).reshape(1, 2, 2, 2, 3)
    key = cache.write(meta, x)
    assert feature_cache_key(dict(reversed(list(meta.items())))) == key
    torch.testing.assert_close(cache.read(meta), x)
    with pytest.raises(FileExistsError): cache.write(meta, x)
    other = dict(meta, geometry_sha='b' * 64)
    with pytest.raises(FileNotFoundError): cache.read(other)
    path = tmp_path / (key + '.npz')
    with np.load(path, allow_pickle=False) as z:
        saved = z['metadata'].copy()
    # Simulate undetected storage bit corruption with valid zip structure.
    np.savez(path, features=x.numpy() + 1, metadata=saved)
    with pytest.raises(ValueError, match='mismatch'): cache.read(meta)


def test_hu_range_and_nonfinite_rejection():
    torch.testing.assert_close(scale_hu(torch.tensor([-2000., -1024., 512., 2048., 3000.])), torch.tensor([0., 0., .5, 1., 1.]))
    with pytest.raises(ValueError): scale_hu(torch.tensor([float('nan')]))


def test_invalid_output_and_missing_checkpoint(tmp_path):
    with pytest.raises(ModelUnavailable): load_ctfm_local(tmp_path / 'missing.safetensors', 'a' * 64)
    with pytest.raises(ValueError): FrozenEncoderAdapter(nn.Flatten()).extract(torch.zeros(1, 1, 2, 2, 2))
    with pytest.raises(ValueError): HeadConfig(seeds=(1, 2, 3, 4))
    with pytest.raises(ValueError): HeadConfig(epochs=101)


def test_cache_rejects_sealed_identity():
    with pytest.raises(ValueError, match="nonsealed"):
        feature_cache_key(dict(metadata(), split="test"))


@pytest.mark.parametrize("split", ["validation", "development"])
def test_cache_rejects_ambiguous_split_aliases(split):
    with pytest.raises(ValueError):
        feature_cache_key(dict(metadata(), split=split))
