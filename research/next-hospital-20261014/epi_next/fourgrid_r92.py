"""Old case3 four-cell mechanism supplement. No new Mask optimization."""
import hashlib
import json
import numpy as np
import torch
from .target_contract_v5 import response_metrics


def byte_sha(t):
    return hashlib.sha256(t.detach().contiguous().cpu().numpy().tobytes()).hexdigest()


def perturb(image, retention, valid, fill=0.):
    if (image.shape != retention.shape or valid.shape != image.shape or image.dtype != torch.float32
            or retention.dtype != torch.float32 or valid.dtype != torch.bool
            or any(t.device.type != 'cpu' for t in (image,retention,valid))
            or not torch.isfinite(image).all() or not torch.isfinite(retention).all()
            or not ((retention>=0)&(retention<=1)).all() or fill != 0.):
        raise ValueError('EXACT_SHARED_SCALAR_ZERO_PERTURBATION_REQUIRED')
    return torch.where(valid,image*retention, image)


def four_masks(soft, peak):
    if soft.dtype != torch.float32 or peak.dtype != torch.bool or soft.shape != peak.shape:
        raise ValueError('SOFT_FP32_PEAK_BOOL_SAME_GRID_REQUIRED')
    p = peak.float()
    return dict(A=soft, B=soft*p, C=p, D=soft*(1-p)+p)


def effects(rows):
    """Signed output differences, not additive independent causal attribution."""
    vectors = {k: np.array([*v['logits'][0],v['target_logit_margin'],v['target_probability']],np.float64)
               for k,v in rows.items()}
    a,b,c,d = (vectors[k] for k in 'ABCD')
    return dict(fields=['logit0','logit1','fixed_target_margin','fixed_target_probability'],
        outside_removal_soft=(b-a).tolist(), inside_hardening_outside_zero=(c-b).tolist(),
        inside_hardening_outside_soft=(d-a).tolist(), outside_removal_hard=(c-d).tolist(),
        mean_outside_removal=((b-a+c-d)/2).tolist(), mean_inside_hardening=((d-a+c-b)/2).tolist(),
        interaction=(c-b-d+a).tolist(),
        hardening_effect_soft_outside_minus_zero_outside=(d-a-c+b).tolist(),
        interaction_definition='C-B-D+A; outside removal x inside hardening; descriptive finite differences')


def run_fourgrid(model, adapter_predict, image, valid, soft, peak, saved_bytes, request, meter, audit=None):
    """4F normal branch: two independent original checks, then B/D. A/C reused."""
    if hashlib.sha256(saved_bytes).hexdigest() != request['saved_readout']['sha256']:
        raise ValueError('SAVED_R91_READOUT_SHA')
    saved = json.loads(saved_bytes)
    if (saved['status'] != 'SUCCESS' or saved['selected_epoch'] != 3604 or saved['selected_cell'] != 43
            or saved['execution_binding_sha256'] != request['old_binding_sha256']
            or saved['input_binding'] != request['input_binding']
            or saved['target_contract']['explanation_target'] != dict(policy='ORIGINAL_ARGMAX_FIXED',declared_class=1,resolved_class=1)
            or byte_sha(image) != request['input_binding']['input_sha256']
            or byte_sha(valid) != request['input_binding']['valid_sha256']
            or soft.shape != (224,224) or not valid.any()):
        raise ValueError('EXACT_CASE3_READOUT_INPUT_TARGET_REQUIRED')
    masks = four_masks(soft,peak)
    inputs = {k:perturb(image,m,valid) for k,m in masks.items()}
    old = saved['responses']
    for name, key in (('full_mask_keep','A'),('peak_patch_keep','C')):
        if (byte_sha(inputs[key]) != old[name]['masked_input_sha256'] or byte_sha(peak if key=='C' else masks[key]) != old[name]['region_sha256']):
            raise ValueError('A_C_NOT_STRICTLY_COMPATIBLE_NO_FALLBACK')
    base = np.asarray(old['original']['logits'],np.float64)
    model.eval().requires_grad_(False)
    with torch.no_grad():
        a = meter.call('forward',lambda:adapter_predict(image.numpy().copy()),samples=1)
        b = meter.call('forward',lambda:model(image[None,None]),samples=1).detach().numpy()
        for x in (a,b):
            arr=np.asarray(x,np.float64).reshape(1,2)
            if not np.isfinite(arr).all() or not np.allclose(arr,base,atol=1e-6,rtol=0):
                raise ValueError('ORIGINAL_ADAPTER_MISMATCH_NO_RETRY')
        if not np.allclose(np.asarray(a).reshape(1,2),b,atol=1e-6,rtol=0):
            raise ValueError('ADAPTER_PAIR_MISMATCH')
        rows={}
        if audit is not None:audit.update(stage='FOURGRID',responses=rows)
        for k in 'ABCD':
            logits = old['full_mask_keep' if k=='A' else 'peak_patch_keep']['logits'] if k in 'AC' else meter.call('forward',lambda:model(inputs[k][None,None]),samples=1).detach().numpy()
            rows[k] = dict(response_metrics(base,logits,1),origin='REUSED_R91' if k in 'AC' else 'NEW_FORWARD',
                masked_input_sha256=byte_sha(inputs[k]),retention_sha256=byte_sha(masks[k]))
    return dict(schema='R92_FOURGRID_RESULT_V1',status='SUCCESS',fixed_target=1,
        responses=rows,effects=effects(rows),meter=meter.report(),
        limitation='old adaptive case3 mechanism, not R18 or medical localization; nonlinear interaction retained')


def translated_controls(region, valid, count=5, seed=17):
    """Rigid integer translations, no wrap/crop/rescale; missing stays missing."""
    from scipy.signal import correlate2d
    region=np.asarray(region);valid=np.asarray(valid)
    if region.dtype!=np.bool_ or valid.dtype!=np.bool_ or region.shape!=valid.shape or not region.any() or (region&~valid).any():
        raise ValueError('NONEMPTY_BOOL_VALID_REGION_REQUIRED')
    yy,xx=np.where(region);y0,y1,x0,x1=yy.min(),yy.max()+1,xx.min(),xx.max()+1
    template=region[y0:y1,x0:x1]
    overlap=correlate2d(valid.astype(np.float64),template.astype(np.float64),mode='valid')
    positions=np.argwhere(overlap==int(region.sum()))
    positions=positions[np.any(positions!=np.array([y0,x0]),axis=1)]
    order=np.random.Generator(np.random.PCG64(seed)).permutation(len(positions))
    rows=[]
    for y,x in positions[order[:count]]:
        moved=np.zeros_like(region);moved[y:y+len(template),x:x+template.shape[1]]=template
        rows.append(dict(dy=int(y-y0),dx=int(x-x0),region=moved))
    return dict(schema='R92_SAME_SHAPE_TRANSLATIONS_V1',requested=count,available=len(rows),
        eligible_positions=len(positions),missing=count-len(rows),seed=seed,controls=rows,
        status='COMPLETE' if len(rows)==count else 'MISSING_VALID_TRANSLATIONS',
        scope='model-grid area, topology and boundary identical under integer translation; native resampling not guaranteed equal')
