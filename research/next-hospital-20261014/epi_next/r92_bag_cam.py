"""R92 true pre-GAP ResNet18 feature capture and signed BAG-CAM algebra.

No command line real-data runner: admission/dispatch and the original shared
supervisor remain required before any real extraction. Does not load weights.
"""
import numpy as np
from .r92_r18_contributions import effective_head, close, policy


def validate_backbone(model):
    import torch
    from torchvision.models.resnet import ResNet, BasicBlock
    if (not isinstance(model, ResNet) or model.training or any(p.requires_grad for p in model.parameters())
            or not isinstance(model.fc, torch.nn.Identity)
            or not isinstance(model.avgpool, torch.nn.AdaptiveAvgPool2d)
            or model.avgpool.output_size != (1, 1)):
        raise ValueError('frozen eval torchvision ResNet18 with Identity fc required')
    if [len(getattr(model, 'layer'+str(i))) for i in range(1,5)] != [2,2,2,2]:
        raise ValueError('exact ResNet18 block counts required')
    if any(not isinstance(b, BasicBlock) for i in range(1,5) for b in getattr(model,'layer'+str(i))):
        raise ValueError('BasicBlock required')


def capture_pre_gap(model, images, *, input_grad=False):
    """Exactly one caller-counted backbone batch. Hooks always removed.

    Capture layer4 output == avgpool INPUT (post residual/BN/ReLU). Raw final
    conv2 is upstream of those operations and is not the GAP feature tensor.
    input_grad=True preserves graph; freezing parameters does not disable it.
    """
    import torch
    validate_backbone(model)
    if (images.shape != (8,3,224,224) or images.dtype != torch.float32
            or images.device.type != 'cpu' or not torch.isfinite(images).all()
            or (input_grad and not images.requires_grad)):
        raise ValueError('finite CPU FP32 frozen K8 RGB224 input required')
    seen = {}
    def block_hook(_module, _args, output):
        seen['layer4'] = output
    def pool_hook(_module, args):
        seen['pool_input'] = args[0]
    hooks = [model.layer4.register_forward_hook(block_hook), model.avgpool.register_forward_pre_hook(pool_hook)]
    try:
        with torch.set_grad_enabled(input_grad):
            gap = model(images)
    finally:
        for hook in hooks:
            hook.remove()
    a = seen['pool_input']
    if (seen['layer4'] is not a or a.shape != (8,512,7,7) or gap.shape != (8,512)
            or not torch.isfinite(a).all() or not torch.isfinite(gap).all()):
        raise ValueError('true layer4 pre-GAP 7x7 shape/flow required')
    return gap, a, dict(hook='avgpool.forward_pre_hook', feature='layer4 post-residual BatchNorm/ReLU output',
                        raw_last_conv='layer4.1.conv2 (not the pooled tensor)', shape=[8,512,7,7],
                        backbone_batch_calls=1, slice_positions=8, input_gradient_enabled=input_grad)


def signed_cam(spatial, pooled_fp32, state):
    a = np.asarray(spatial)
    gap = np.asarray(pooled_fp32)
    if (a.shape != (8,512,7,7) or a.dtype != np.float32 or gap.shape != (8,512)
            or gap.dtype != np.float32 or not np.isfinite(a).all() or not np.isfinite(gap).all()):
        raise ValueError('real 7x7 FP32 feature map and original FP32 GAP required')
    coeff, beta = effective_head(state)
    maps = np.einsum('kfhw,cf->kchw', a.astype(np.float64), coeff, optimize=False)
    gap64 = a.astype(np.float64).mean((2,3))
    cam_logits = beta + maps.mean((0,2,3))
    bag_gap64 = gap.astype(np.float64).mean(0)
    direct = ((bag_gap64-state['mean'].astype(np.float64))/state['scale'].astype(np.float64)) @ state['linear.weight'].astype(np.float64).T + state['linear.bias'].astype(np.float64)
    # FP32 adaptive pooling sums 49 nonnegative post-ReLU values. This bound
    # includes rounding and conversion, not architecture or preprocessing drift.
    u = np.finfo(np.float32).eps/2
    gamma49 = 49*u/(1-49*u)
    gap_envelope = gamma49*np.abs(a.astype(np.float64)).mean((2,3)) + np.finfo(np.float32).tiny
    logit_envelope = np.abs(coeff) @ gap_envelope.mean(0)
    return dict(signed_class_maps=maps, signed_margin_maps=maps[:,1]-maps[:,0],
                display_positive_margin_maps=np.maximum(maps[:,1]-maps[:,0],0),
                effective_bias=beta, effective_margin_bias=beta[1]-beta[0],
                cam_reconstructed_logits=cam_logits, original_pool_fp64_head_logits=direct,
                pooling_gap_absolute_errors=np.abs(gap64-gap),
                pooling_roundoff_envelope=gap_envelope, logit_roundoff_envelope=logit_envelope,
                cam_logit_absolute_errors=np.abs(cam_logits-direct),
                gap_tolerance_pass=close(gap64,gap,policy()['future_spatial_fp32_gap']),
                logit_tolerance_pass=close(cam_logits,direct,policy()['future_spatial_logits']),
                pooling_envelope_pass=bool(np.all(np.abs(gap64-gap)<=gap_envelope)),
                # FP64 algebra adds a small separately declared acceptance term.
                logit_envelope_pass=bool(np.all(np.abs(cam_logits-direct)<=logit_envelope+1e-8)),
                residual_added_to_maps=False)


def map_centers_to_native(geometry):
    """Nominal feature centers, not segmentation boundaries or local RF extent."""
    if geometry['model_shape'] != [8,3,224,224] or len(geometry['indices_Z']) != 8:
        raise ValueError('frozen geometry K8 RGB224 required')
    native = np.array(geometry['native_shape_ZYX'],dtype=int)
    affine = np.array(geometry['native_to_LPS'],dtype=np.float64)
    if native.shape != (3,) or np.any(native <= 0) or affine.shape != (4,4) or not np.isfinite(affine).all():
        raise ValueError('native ZYX affine required')
    indices = np.array(geometry['indices_Z'],dtype=int)
    if np.any(indices<0) or np.any(indices>=native[0]) or len(set(indices)) != 8:
        raise ValueError('unique in-bounds original sampled slices required')
    coordinates = np.empty((8,7,7,3),np.float64)
    coordinates[:,:,:,0] = indices[:,None,None]
    centers = (np.arange(7)*32+.5)/224
    coordinates[:,:,:,1] = (centers*native[1]-.5)[None,:,None]
    coordinates[:,:,:,2] = (centers*native[2]-.5)[None,None,:]
    lps = np.concatenate([coordinates,np.ones((8,7,7,1))],axis=-1) @ affine.T
    return dict(native_ZYX_centers=coordinates, LPS_centers=lps[:,:,:,:3],
                input_center_offset=0, input_center_stride=32, nominal_receptive_field=435,
                interpretation='nominal ResNet18 lattice centers; receptive field overlaps input/padding broadly; no voxel probability or lesion boundary')
