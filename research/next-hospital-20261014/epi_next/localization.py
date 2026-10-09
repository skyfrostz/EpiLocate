"""EPI-NEXT fixed-target input perturbation. No ground-truth inputs.

All masks index array axes (2D: y,x; 3D: z,y,x). Fill values must already be
in the same input units as the image; the caller owns HU/preprocessing semantics.
Thresholds here are development settings, not frozen research thresholds.
"""
from dataclasses import dataclass, asdict
from itertools import product
import math
import time
import numpy as np


def _public_status(result):
    """Map algorithm outcomes to the shared EPI-NEXT public status vocabulary."""
    mapping = {
        'COMPLETE': ('OK', None),
        'NUMERICAL_FAILURE': ('FAILED', 'NUMERICAL_FAILURE'),
        'MODEL_FAILURE': ('FAILED', 'MODEL_FAILURE'),
        'UNKNOWN_VALID_SUPPORT': ('INPUT_UNSUPPORTED', 'UNKNOWN_VALID_SUPPORT'),
        'EMPTY_VALID_DOMAIN': ('INPUT_UNSUPPORTED', 'EMPTY_VALID_DOMAIN'),
        'NO_MULTISCALE_SUPPORT': ('NO_RELIABLE_RESPONSE', 'NO_MULTISCALE_SUPPORT'),
    }
    for item in [result, *result.get('stages', [])]:
        if item.get('status') in mapping:
            status, reason = mapping[item['status']]
            item['status'] = status
            if reason: item['reason'] = reason
    return result


def _logits(value):
    a = np.asarray(value, dtype=np.float64)
    if a.ndim != 1 or a.size < 2 or not np.isfinite(a).all():
        raise ValueError('logits must be finite 1D, with at least two classes')
    return a


def fixed_target_response(baseline_logits, perturbed_logits, target):
    """Margin = target logit - max non-target; positive delta supports target.

    Multiclass competitor may change but target never follows argmax. Float64
    softmax is a diagnostic only: it cannot recover precision lost upstream.
    """
    a, b = _logits(baseline_logits), _logits(perturbed_logits)
    if a.shape != b.shape or isinstance(target, (bool, np.bool_)) or not isinstance(target, (int, np.integer)) or not 0 <= target < a.size:
        raise ValueError('invalid fixed target or logits shape')
    def summary(x):
        p = np.exp(x - x.max()); p /= p.sum()
        return float(x[target] - np.max(np.delete(x, target))), float(p[target])
    am, ap = summary(a); bm, bp = summary(b)
    delta = am - bm
    if not np.isfinite([am, bm, delta]).all():
        raise ValueError('nonfinite margin arithmetic')
    return dict(target=int(target), baseline_logits=a.tolist(), perturbed_logits=b.tolist(),
                baseline_margin=am, perturbed_margin=bm, margin_delta=delta,
                baseline_probability=ap, perturbed_probability=bp,
                probability_delta=ap-bp, baseline_argmax=int(a.argmax()),
                perturbed_argmax=int(b.argmax()), evidence_type='INPUT_OCCLUSION_RESPONSE')


def _inputs(image, valid_mask):
    x = np.asarray(image)
    if valid_mask is None:
        return x, None, 'UNKNOWN_VALID_SUPPORT'
    raw = np.asarray(valid_mask)
    if raw.dtype != np.bool_ or raw.shape != x.shape:
        raise ValueError('valid_mask must be boolean with input spatial shape')
    if not np.issubdtype(x.dtype, np.floating):
        raise ValueError('input must have floating dtype (avoid silent fill truncation)')
    if not np.isfinite(x).all():
        return x, raw, 'NUMERICAL_FAILURE'
    if not raw.any():
        return x, raw, 'EMPTY_VALID_DOMAIN'
    return x, raw, None


def _fill(x, fill):
    f = np.asarray(fill, dtype=x.dtype)
    if f.shape not in ((), x.shape) or not np.isfinite(f).all():
        raise ValueError('fill must be finite scalar or same-shape input-space baseline')
    return f


def occlusion_2d(predict, image, valid_mask, target, patch_sizes=(16,32,64), fill=0., min_response=0.):
    """Disjoint grid per scale; clipping at edges, deterministic ties, no Top-k.

    Only strictly positive responses above min_response are candidates. Every
    attempted model invocation is counted, including a failed baseline call.
    """
    x, valid, state = _inputs(image, valid_mask)
    if x.ndim != 2: raise ValueError('expected H,W image')
    if not np.isfinite(min_response) or min_response < 0: raise ValueError('invalid response threshold')
    sizes = tuple(patch_sizes)
    if not sizes or any(not isinstance(s, int) or s <= 0 for s in sizes): raise ValueError('invalid pixel sizes')
    out = dict(algorithm='EPI-NEXT-E1-fixed-target-margin-v1', evidence_type='INPUT_OCCLUSION_RESPONSE',
               status=state, model_calls=0, records=[], candidates=[], scale_units='pixels', target=int(target))
    if state: return _public_status(out)
    fill = _fill(x, fill)
    try:
        out['model_calls'] += 1
        baseline = _logits(predict(x.copy()))
        fixed_target_response(baseline, baseline, target)
        for size in dict.fromkeys(sizes):
            for y, z in product(range(0, x.shape[0], size), range(0, x.shape[1], size)):
                mask = np.zeros_like(valid); mask[y:y+size,z:z+size] = True; mask &= valid
                if not mask.any(): continue
                occluded = np.where(mask, fill, x)
                out['model_calls'] += 1
                response = fixed_target_response(baseline, predict(occluded), target)
                response.update(bounds_yx=[[y,min(y+size,x.shape[0])],[z,min(z+size,x.shape[1])]],
                                scale_pixels=size, support_pixels=int(mask.sum()),
                                accepted=response['margin_delta'] > min_response)
                out['records'].append(response)
                if response['accepted']: out['candidates'].append(response)
        out['status'] = 'COMPLETE' if out['candidates'] else 'NO_RELIABLE_RESPONSE'
    except (ValueError, RuntimeError, FloatingPointError) as exc:
        out['status'] = 'NUMERICAL_FAILURE' if isinstance(exc, (ValueError,FloatingPointError)) else 'MODEL_FAILURE'
        out['error'] = str(exc)
    return _public_status(out)


@dataclass(frozen=True)
class BudgetConfig:
    stages: int = 3
    max_extra_evaluations: int = 32
    timeout_seconds: float = 120.
    random_probes: int = 2
    seed: int = 20261009
    scales_mm: tuple = (16.,32.,64.)
    min_response: float = 0.

    def validate(self):
        if not 1 <= self.stages <= 3: raise ValueError('stages must be 1..3')
        if not 2 <= self.random_probes <= self.max_extra_evaluations <= 32: raise ValueError('invalid evaluation budget')
        if not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 120: raise ValueError('timeout must be (0,120]')
        if not self.scales_mm or any(not math.isfinite(s) or s <= 0 for s in self.scales_mm): raise ValueError('invalid physical scales')
        if not math.isfinite(self.min_response) or self.min_response < 0: raise ValueError('invalid response threshold')


def hierarchical_input_occlusion_3d(predict, volume, valid_mask, coarse_map, target,
                                    spacing_mm, config=None, fill=0., clock=time.monotonic):
    """F1 static-coarse/original-input search-exclusion variant.

    This does NOT implement the planned residual-input F1 baseline/coarse-map
    update between stages. All response deltas reference the original volume.

    Two seeded unsearched probes run first, reserving budget even when proposals
    exhaust it. Accepted support is excluded from subsequent search (not from
    the original prediction). No feature cache, no feature-level masking.
    Timeout is cooperative between forwards; an in-flight predict cannot be
    forcibly cancelled by this synchronous function. Returning PARTIAL_BUDGET
    preserves completed responses and reports the observed elapsed time.
    """
    cfg = config or BudgetConfig(); cfg.validate()
    x, valid, state = _inputs(volume, valid_mask)
    if x.ndim != 3: raise ValueError('expected Z,Y,X volume')
    spacing = np.asarray(spacing_mm, dtype=float)
    if spacing.shape != (3,) or not np.isfinite(spacing).all() or (spacing <= 0).any(): raise ValueError('invalid z,y,x spacing')
    coarse = np.asarray(coarse_map)
    if coarse.shape != x.shape or not np.isfinite(coarse).all(): raise ValueError('invalid coarse map')
    out = dict(algorithm='EPI-NEXT-F1-static-coarse-original-input-search-exclusion-v1', status=state,
               evidence_type='INPUT_OCCLUSION_RESPONSE', target=int(target), config=asdict(cfg),
               model_calls=0, extra_evaluations=0, random_probes_completed=0,
               records=[], candidates=[], elapsed_seconds=0., timeout_enforcement='BETWEEN_FORWARDS',
               volume_shape_zyx=list(x.shape), scale_units='mm', recomputation='FULL_ORIGINAL_INPUT', exclusion='ACCEPTED_SEARCH_SUPPORT', planned_residual_input_f1='NOT_IMPLEMENTED')
    if state: return _public_status(out)
    fill = _fill(x, fill); started = clock()
    searched = np.zeros_like(valid); excluded = np.zeros_like(valid); seen = set()
    def exhausted():
        return out['extra_evaluations'] >= cfg.max_extra_evaluations or clock()-started >= cfg.timeout_seconds
    def evaluate(center, scale, stage, kind):
        widths = np.maximum(1,np.ceil(scale/spacing).astype(int))
        lo = np.maximum(0,np.asarray(center)-widths//2)
        hi = np.minimum(np.asarray(x.shape),lo+widths)
        slices = tuple(slice(int(a),int(b)) for a,b in zip(lo,hi))
        mask = np.zeros_like(valid); mask[slices] = True; mask &= valid & ~excluded
        if kind == 'SEEDED_UNSEARCHED_PROBE': mask &= ~searched
        # Exactly the same set of perturbed voxels must not be evaluated twice.
        key = np.packbits(mask).tobytes()
        if not mask.any() or key in seen: return False
        if exhausted(): return False
        seen.add(key); searched[mask] = True
        out['model_calls'] += 1; out['extra_evaluations'] += 1
        response = fixed_target_response(baseline, predict(np.where(mask,fill,x)), target)
        response.update(stage=stage, kind=kind, scale_mm=float(scale),
                        bounds_zyx=[[int(a),int(b)] for a,b in zip(lo,hi)],
                        center_zyx=[int(i) for i in center], support_voxels=int(mask.sum()),
                        mask_flat_indices=np.flatnonzero(mask).tolist(),
                        accepted=response['margin_delta'] > cfg.min_response)
        out['records'].append(response)
        if kind == 'SEEDED_UNSEARCHED_PROBE': out['random_probes_completed'] += 1
        if response['accepted']: out['candidates'].append(response)
        return True
    try:
        if clock()-started >= cfg.timeout_seconds:
            out['status']='PARTIAL_BUDGET'; return out
        out['model_calls'] += 1; baseline = _logits(predict(x.copy()))
        fixed_target_response(baseline,baseline,target)
        rng = np.random.default_rng(cfg.seed)
        # Probes deliberately bypass coarse-map ranking and use smallest scale.
        for _ in range(cfg.random_probes):
            available = np.argwhere(valid & ~searched)
            if not len(available) or exhausted(): break
            evaluate(available[rng.integers(len(available))], min(cfg.scales_mm), 0, 'SEEDED_UNSEARCHED_PROBE')
        for stage in range(1,cfg.stages+1):
            if exhausted(): break
            available = valid & ~excluded & ~searched
            if not available.any(): break
            scores = np.where(available,coarse,-np.inf)
            # Stable index tie-break applies to proposals only, never acceptance.
            center = np.unravel_index(int(scores.argmax()),x.shape)
            start_record = len(out['records'])
            for scale in cfg.scales_mm:
                if exhausted(): break
                evaluate(center,scale,stage,'COARSE_PROPOSAL')
            for record in out['records'][start_record:]:
                if record['accepted']: excluded.flat[record['mask_flat_indices']] = True
        # Report overlap support, do not require all scales or force a minimum k.
        for candidate in out['candidates']:
            own = set(candidate['mask_flat_indices'])
            candidate['support_scales_mm'] = sorted({r['scale_mm'] for r in out['candidates']
                                                    if own.intersection(r['mask_flat_indices'])})
        out['probe_status'] = 'COMPLETE' if out['random_probes_completed'] >= cfg.random_probes else 'INCOMPLETE_UNSEARCHED_SUPPORT_OR_BUDGET'
        out['status'] = ('PARTIAL_BUDGET' if exhausted() else
                         'INPUT_UNSUPPORTED' if out['random_probes_completed'] < cfg.random_probes else
                         'COMPLETE' if out['candidates'] else 'NO_RELIABLE_RESPONSE')
        if out['status'] == 'INPUT_UNSUPPORTED': out['reason'] = 'INSUFFICIENT_PROBE_SUPPORT'
    except (ValueError,RuntimeError,FloatingPointError) as exc:
        out['status']='NUMERICAL_FAILURE' if isinstance(exc,(ValueError,FloatingPointError)) else 'MODEL_FAILURE'
        out['error']=str(exc)
    finally:
        out['elapsed_seconds']=clock()-started
    return _public_status(out)
