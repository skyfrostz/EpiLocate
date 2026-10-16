"""Actual random ResNet18 architecture, generated inputs; no medical weights."""
import numpy as np
import pytest
import torch
from torchvision.models import resnet18
from epi_next.r92_bag_cam import capture_pre_gap, signed_cam, map_centers_to_native


def test_true_layer4_capture_pool_roundoff_and_input_gradient():
    torch.set_num_threads(1)
    with torch.random.fork_rng():
        torch.manual_seed(17)
        model=resnet18(weights=None).eval().requires_grad_(False)
        model.fc=torch.nn.Identity()
        images=torch.randn(8,3,224,224,requires_grad=True)
    gap, spatial, info=capture_pre_gap(model,images,input_grad=True)
    assert info['backbone_batch_calls']==1 and spatial.requires_grad
    rng=np.random.default_rng(17)
    state={'linear.weight':rng.normal(0,.01,(2,512)).astype(np.float32),
           'linear.bias':np.array([.1,-.2],np.float32), 'mean':np.zeros(512,np.float32),
           'scale':np.ones(512,np.float32)}
    cam=signed_cam(spatial.detach().numpy(),gap.detach().numpy(),state)
    assert all(cam[k] for k in ['gap_tolerance_pass','logit_tolerance_pass','pooling_envelope_pass','logit_envelope_pass'])
    assert np.allclose(cam['signed_margin_maps'].mean()+cam['effective_margin_bias'],np.diff(cam['cam_reconstructed_logits'])[0])
    # Signed CAM algebra and direct FP32-pool head retain the same input graph.
    coeff=torch.from_numpy(state['linear.weight']).double()
    direct=(gap.double().mean(0)@coeff.T).diff().sum()
    from_map=torch.einsum('kfhw,cf->kchw',spatial.double(),coeff).mean((0,2,3)).diff().sum()
    g1=torch.autograd.grad(direct,images,retain_graph=True)[0]
    g2=torch.autograd.grad(from_map,images)[0]
    assert torch.isfinite(g1).all() and g1.abs().max()>0
    assert torch.allclose(g1,g2,atol=1e-8,rtol=1e-4)
    assert not model.avgpool._forward_pre_hooks and not model.layer4._forward_hooks
    with pytest.raises(ValueError):signed_cam(np.zeros((8,512,1,1),np.float32),gap.detach().numpy(),state)


def test_center_mapping_and_architecture_receptive_field():
    # Derive stride/offset/max receptive field along actual longest residual path.
    model=resnet18(weights=None)
    r,j,o=1,1,0
    ops=[model.conv1,model.maxpool]
    for i in range(1,5):
        for block in getattr(model,'layer'+str(i)):ops.extend([block.conv1,block.conv2])
    for op in ops:
        k=op.kernel_size[0] if isinstance(op.kernel_size,tuple) else op.kernel_size
        s=op.stride[0] if isinstance(op.stride,tuple) else op.stride
        p=op.padding[0] if isinstance(op.padding,tuple) else op.padding
        o+=((k-1)/2-p)*j; r+=(k-1)*j; j*=s
    assert (r,j,o)==(435,32,0)
    geo=dict(model_shape=[8,3,224,224],native_shape_ZYX=[16,448,448],indices_Z=list(range(0,16,2)),native_to_LPS=np.eye(4).tolist())
    mapped=map_centers_to_native(geo)
    assert np.array_equal(mapped['native_ZYX_centers'][0,0,0],[0,.5,.5])
    assert np.array_equal(mapped['LPS_centers'],mapped['native_ZYX_centers'])
