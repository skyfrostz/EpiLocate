"""Generated-only numerical and fail-closed checks; no R91 arrays accessed."""
import numpy as np
import pytest
from epi_next.r92_r18_contributions import decompose, generated_validation, close


def test_prelocked_generated_fp32_domain():
    report = generated_validation()
    assert report['status'] == 'PASS' and report['real_reads'] == 0
    assert len(report['scenarios']) == 3


def test_components_margin_and_bag_replacement_scaling():
    rng = np.random.default_rng(92)
    f = rng.normal(size=(8,512)).astype(np.float32)
    state = {'linear.weight': rng.normal(size=(2,512)).astype(np.float32),
             'linear.bias': np.array([3., -2.], np.float32),
             'mean': rng.normal(size=512).astype(np.float32), 'scale': np.ones(512,np.float32)}
    d = decompose(f,state)
    assert np.allclose(d['slice_component_logits'].mean(0),d['direct_fp64_logits'])
    assert np.allclose(d['slice_component_margin'].mean(),np.diff(d['direct_fp64_logits'])[0])
    changed=f.copy(); changed[3] += np.float32(.25)
    other=decompose(changed,state)
    bag_delta=other['direct_fp64_logits']-d['direct_fp64_logits']
    slice_delta=other['slice_component_logits'][3]-d['slice_component_logits'][3]
    assert np.allclose(bag_delta,slice_delta/8,atol=1e-12)
    assert np.allclose(np.sum(bag_delta**2),np.sum(slice_delta**2)/64)


def test_rejects_placeholder_as_spatial_and_wrong_values():
    state={'linear.weight':np.zeros((2,512),np.float32),'linear.bias':np.zeros(2,np.float32),
           'mean':np.zeros(512,np.float32),'scale':np.ones(512,np.float32)}
    with pytest.raises(ValueError): decompose(np.zeros((8,512,1,1,1),np.float32),state)
    state['scale'][0]=0
    with pytest.raises(ValueError): decompose(np.zeros((8,512),np.float32),state)
    assert not close([float('nan')],[0],{'atol':1,'rtol':0})
