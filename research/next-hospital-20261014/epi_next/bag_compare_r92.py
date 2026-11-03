"""Bounded same-function CAM/E1/E2-inspired diagnostic, independent of old HSPI.

Caller supplies ENC-owned verified bundle and admitted meter. No CT/weight IO.
"""
import torch
from torch.nn import functional as F
from .conditional_bag_r92 import ConditionalBag, bag_losses, finite
from .fourgrid_r92 import perturb
from .target_contract_v5 import response_metrics

PROTOCOL = dict(K=8, member_rule='first original sampled member (position0), no GT/score selection',
    target_policy='ORIGINAL_ARGMAX_FIXED', patch=64, grid=7, steps=8, initialization=.5,
    adam_lr=.01, lambda_sparse=1., loss='K2_COMPONENT_LS_R92_V1',
    cpf='NOT_CALIBRATED_NOT_APPLIED', selection='FIXED_POST_UPDATE8_MASK_NO_CPF',
    percentages=[5,10,20], saved_atol=1e-8, saved_rtol=1e-10,
    gap_atol=1e-5, gap_rtol=1e-6, logits_atol=1e-4, logits_rtol=1e-5,
    forward=46, backward=9, updates=8, encoder_samples=53, seconds=120,
    output_bytes=67108864, model_device='cpu', threads=1)


def ranked(mask, valid, percent):
    flat=torch.nonzero(valid.flatten(),as_tuple=False).flatten()
    order=torch.argsort(mask.flatten()[flat],descending=True,stable=True)
    keep=torch.zeros_like(valid).flatten()
    keep[flat[order[:len(flat)*percent//100]]]=True
    return keep.reshape(valid.shape)


def run_compare(bundle, meter, *, generated=False):
    """Normal branch 46F/9B/8 Mask-only updates; no head/backbone updates.

    bundle encoder consumes post-resize recovered scalar FP32, includes original
    RGB normalization, returns actual GAP, and exposes actual last_spatial.
    Hook/maps are ENC owned; absence/mismatch stops, never fake a GAP map.
    """
    audit=bundle.setdefault('audit',{});audit['stage']='BINDING_AND_BASELINE'
    protocol=PROTOCOL
    images=bundle['images'];cache=bundle['cached_gap'];members=bundle['members']
    finite(images)
    if images.shape != (8,1,224,224) or images.dtype!=torch.float32 or cache.shape!=(8,512) or cache.dtype!=torch.float32:
        raise ValueError('EXACT_EIGHT_R18_INPUTS_AND_512_GAP_REQUIRED')
    if torch.get_num_threads()!=1: raise ValueError('CPU_ONE_THREAD_REQUIRED')
    model=ConditionalBag(bundle['encoder'],cache, bundle['mean'],bundle['scale'],bundle['weight'],bundle['bias'],members,meter)
    base=model.current_logits.detach().clone();saved=finite(bundle['saved_bag_logits'],(1,2)).double()
    if not torch.allclose(base,saved,atol=protocol['saved_atol'],rtol=protocol['saved_rtol']):
        raise ValueError('CACHED_BAG_RECONSTRUCTION_MISMATCH')
    with torch.no_grad():
        direct=model.features(images)
        maps=finite(getattr(model.encoder,'last_spatial',None))
        if maps.shape!=(8,512,7,7) or maps.dtype!=torch.float32:
            raise ValueError('ACTUAL_NONTRIVIAL_PRE_GAP_SPATIAL_FEATURE_REQUIRED')
        map_gap=F.adaptive_avg_pool2d(maps,1).flatten(1).double()
        if not torch.allclose(direct,map_gap,atol=protocol['gap_atol'],rtol=protocol['gap_rtol']) or not torch.allclose(direct,cache.double(),atol=protocol['gap_atol'],rtol=protocol['gap_rtol']):
            raise ValueError('SPATIAL_GAP_CACHE_MISMATCH')
        direct_logits=model.aggregate(direct)
        if not torch.allclose(direct_logits,saved,atol=protocol['logits_atol'],rtol=protocol['logits_rtol']):
            raise ValueError('DIRECT_BAG_LOGITS_MISMATCH')
        a=model.weight/model.scale
        beta=model.bias-(a*model.mean).sum(1)
        signed=torch.einsum('cd,ndhw->nchw',a,maps.double())
        cam_logits=beta+signed.mean((0,2,3))
        n=maps.shape[-1]*maps.shape[-2];u=2**-24
        gamma=n*u/(1-n*u)
        pool_bound=gamma*maps.double().abs().mean((2,3))+torch.finfo(torch.float32).tiny
        pool_residual=(maps.double().mean((2,3))-map_gap).abs()
        if not bool((pool_residual<=pool_bound).all()):
            raise ValueError('PER_CHANNEL_FP32_POOLING_ENVELOPE_EXCEEDED')
        cam_bound=torch.einsum('cd,nd->c',a.abs(),pool_bound)/8
        cam_bound=cam_bound+1e-8 # ENC prelocked FP64 algebra acceptance term
        if not bool(((cam_logits-direct_logits[0]).abs()<=cam_bound).all()):
            raise ValueError('CAM_FP32_POOLING_ENVELOPE_EXCEEDED')
        if not torch.allclose(cam_logits[None],saved,atol=protocol['logits_atol'],rtol=protocol['logits_rtol']):
            raise ValueError('SIGNED_CAM_RECONSTRUCTION_MISMATCH')
        cam_margin=signed[:,model.target]-signed[:,1-model.target]
    member=members[0];one=model.member(member);image=images[:1]
    with torch.no_grad(): check=one(image)
    if not torch.allclose(check,base,atol=protocol['logits_atol'],rtol=protocol['logits_rtol']):
        raise ValueError('SINGLE_MEMBER_ADAPTER_MISMATCH')
    probe=image.detach().clone().requires_grad_(True)
    logits=one(probe)
    grad=meter.call('backward',lambda:torch.autograd.grad(logits[0,model.target]-logits[0,1-model.target],probe)[0])
    if not torch.isfinite(grad).all():raise ValueError('NONFINITE_INPUT_GRADIENT')
    valid=bundle['valid']
    if valid.shape!=(224,224) or valid.dtype!=torch.bool or valid.device.type!='cpu' or not valid.any():
        raise ValueError('BOUND_COMMON_VALID_DOMAIN_REQUIRED')
    def evaluate(retention):
        masked=perturb(image[0,0],retention.float(),valid)
        return one(masked[None,None])
    base_np=base.numpy();target=model.target
    scores=torch.zeros_like(valid,dtype=torch.float32);tiles=[]
    audit.update(stage='E1',E1_tiles=tiles)
    with torch.no_grad():
        for y in range(0,224,protocol['patch']):
            for x in range(0,224,protocol['patch']):
                keep=torch.ones_like(valid);keep[y:y+64,x:x+64]=False
                z=evaluate(keep)
                row=response_metrics(base_np,z.numpy(),target);row['bounds_yx']=[y,min(y+64,224),x,min(x+64,224)]
                tiles.append(row);scores[y:y+64,x:x+64]=row['margin_drop']
    mask=torch.full((1,1,7,7),.5,requires_grad=True)
    opt=torch.optim.Adam([mask],lr=protocol['adam_lr']);trace=[]
    audit.update(stage='E2',E2_trace=trace)
    for step in range(protocol['steps']):
        opt.zero_grad(set_to_none=True)
        soft=F.interpolate(mask,(224,224),mode='bilinear',align_corners=False,antialias=False)[0,0]
        z=evaluate(soft);losses=bag_losses(base,z);sparse=mask.abs().mean()
        objective=losses['K2_COMPONENT_LS_R92_V1']+protocol['lambda_sparse']*sparse
        meter.call('backward',objective.backward)
        if mask.grad is None or not torch.isfinite(mask.grad).all():raise ValueError('NONFINITE_MASK_GRADIENT')
        trace.append(dict(step=step+1,raw_bag_ls=float(losses['RAW_BAG_LS_R92_V1'].detach()),
            component_ls=float(losses['K2_COMPONENT_LS_R92_V1'].detach()),sparsity=float(sparse.detach()),
            gradient_norm=float(mask.grad.norm())))
        meter.call('updates',opt.step)
        with torch.no_grad(): mask.clamp_(0,1)
    soft=F.interpolate(mask.detach(),(224,224),mode='bilinear',align_corners=False,antialias=False)[0,0]
    rows={}
    audit.update(stage='FIXED_AREA_READOUT',responses=rows)
    with torch.no_grad():
        rows['E2_final_soft_keep']=response_metrics(base_np,evaluate(soft).numpy(),target)
        cam=F.interpolate(cam_margin[:1,None].float(),(224,224),mode='bilinear',align_corners=False,antialias=False)[0,0]
        for method,score in (('CAM',cam),('E1',scores),('E2',soft)):
            for percent in protocol['percentages']:
                selected=ranked(score,valid,percent)
                for action,retention in (('keep',selected),('remove',~selected)):
                    row=response_metrics(base_np,evaluate(retention).numpy(),target)
                    row.update(selected_pixels=int(selected.sum()),valid_pixels=int(valid.sum()),
                        area_percent=percent,selection='fixed top rank; no GT',candidate_status='UNCALIBRATED_DIAGNOSTIC')
                    rows[f'{method}_{percent}_{action}']=row
    return dict(schema='R92_SAME_BAG_COMPARISON_V1',status='SUCCESS',evidence='GENERATED_ONLY' if generated else 'APPROVED_DEVELOPMENT',
        protocol=protocol,adapter=model.metadata(),checks=dict(saved_logits=saved.tolist(),direct_logits=direct_logits.tolist(),
        cam_logits=cam_logits.tolist(),pooling_max_abs=float(pool_residual.max()),cam_pooling_bound=cam_bound.tolist(),
        cam_direct_residual=(cam_logits-direct_logits[0]).tolist(),gradient_norm=float(grad.norm()),
        gap_max_abs=float((direct-cache).abs().max())),cam=dict(signed_class_maps=signed.tolist(),
        signed_margin_1_minus_0_maps=(signed[:,1]-signed[:,0]).tolist(),
        signed_fixed_target_margin_maps=cam_margin.tolist(),beta=beta.tolist(),
        conditional_member0_bias=float(beta[target]-beta[1-target]+cam_margin[1:].mean((1,2)).sum()/8),
        conditional_member0_map_scale=1/8,relu_used_for_identity=False),
        source_geometry=bundle.get('geometry'), source_group_id=bundle.get('source_group_id'),
        expert_reference_status=bundle.get('expert_reference_status','UNKNOWN'),
        E1_tiles=tiles,E2_trace=trace,E2_final_mask=mask.detach().tolist(),responses=rows,
        reliable_candidates=[],candidate_status='NO_CALIBRATED_RELIABILITY_RULE',
        methods=dict(CAM='signed affine pre-GAP BAG-CAM',E1='E1_64_TILED_DIAGNOSTIC_R92',E2='HSPI_INSPIRED_K2_FIXED8_NO_CPF_R92'),
        model_parameter_updates=0,mask_optimizer_updates=protocol['steps'],
        limitation='HSPI-inspired K2 diagnostic, no inherited CPF/PSMI claim; no slice or pixel lesion truth')
