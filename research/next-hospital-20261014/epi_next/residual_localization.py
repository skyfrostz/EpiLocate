"""EPI-NEXT F1 residual-input baseline and coarse-map refresh reference.

CPU-compatible model injection; no GT, DICOM reader, cache or feature masking.
`predict_with_map` must fully evaluate one input and return (class logits, a
same-spatial-shape coarse contribution map). All coordinates are model ZYX.
"""
from dataclasses import asdict
import hashlib
import time
import numpy as np

from .localization import BudgetConfig, _inputs, _fill, _logits, _public_status, fixed_target_response


class _BudgetStop(Exception):
    pass


def _digest(array):
    a = np.ascontiguousarray(array)
    header = (str(a.dtype) + ':' + str(a.shape) + ':').encode()
    return hashlib.sha256(header + a.tobytes()).hexdigest()


def residual_input_occlusion_3d(predict_with_map, volume, valid_mask, target,
                                spacing_mm, config=None, fill=0., clock=time.monotonic):
    """Three-stage bounded residual-input search, full model/map recomputation.

    Two seeded, spatially disjoint probes are diagnostics only. Their support
    remains eligible for later formal candidate selection and a new full model
    evaluation; diagnostic responses are never silently reused as candidates.
    Every stage selects one center from the current residual input's refreshed
    map and evaluates the declared scales against that stage's baseline logits.
    Positive candidate support is unioned and filled in all subsequent inputs.
    Before another stage, the residual input is fully re-evaluated for BOTH its
    baseline and map; this is one extra model evaluation, counted in the cap.

    Fill must already match model input units. Timeout is cooperative between
    calls; completed responses are preserved if a call returns after deadline.
    Models must not mutate inputs; defensive copies isolate caller state.
    """
    cfg = config or BudgetConfig()
    cfg.validate()
    for name in ('stages', 'max_extra_evaluations', 'random_probes', 'seed'):
        if isinstance(getattr(cfg, name), (bool, np.bool_)) or not isinstance(getattr(cfg, name), (int, np.integer)):
            raise ValueError(name + ' must be an integer, not bool')
    if isinstance(target, (bool, np.bool_)) or not isinstance(target, (int, np.integer)) or target < 0:
        raise ValueError('target must be a nonnegative integer, not bool')
    x, valid, state = _inputs(volume, valid_mask)
    if x.ndim != 3: raise ValueError('expected Z,Y,X volume')
    spacing = np.asarray(spacing_mm, dtype=float)
    if spacing.shape != (3,) or not np.isfinite(spacing).all() or (spacing <= 0).any():
        raise ValueError('spacing must be finite positive Z,Y,X millimeters')
    out = dict(algorithm='EPI-NEXT-F1-residual-input-refreshed-coarse-v2',
               evidence_type='INPUT_OCCLUSION_RESPONSE', status=state, reason='',
               config=asdict(cfg), target=int(target), volume_shape_zyx=list(x.shape),
               spacing_zyx_mm=spacing.tolist(), model_calls=0, extra_evaluations=0,
               random_probes_completed=0, probes=[], stages=[], records=[],
               candidates=[], calls=[], original_baseline_logits=None,
               elapsed_seconds=0., probe_policy='DIAGNOSTIC_ONLY_ALLOW_FULL_REEVALUATION_IN_FORMAL_SEARCH',
               timeout_enforcement='BETWEEN_FORWARDS', recomputation='FULL_RESIDUAL_INPUT_AND_MAP')
    if state: return _public_status(out)
    fill = _fill(x, fill)
    start = clock()
    excluded = np.zeros_like(valid)
    searched = np.zeros_like(valid)
    probe_support = np.zeros_like(valid)
    seen_masks = set()

    def budget_reason():
        if clock() - start >= cfg.timeout_seconds: return 'TIME_LIMIT'
        if out['extra_evaluations'] >= cfg.max_extra_evaluations: return 'EXTRA_EVALUATION_LIMIT'
        return None

    def predict(input_array, stage, kind, extra=True):
        reason = budget_reason()
        if reason: raise _BudgetStop(reason)
        out['model_calls'] += 1
        if extra: out['extra_evaluations'] += 1
        call = dict(index=out['model_calls'], stage=stage, kind=kind, extra=extra,
                    input_sha256=_digest(input_array), status='RUNNING')
        out['calls'].append(call)
        try:
            logits_value, coarse_value = predict_with_map(input_array.copy())
            logits = _logits(logits_value).copy()
            fixed_target_response(logits, logits, target)
            coarse = np.asarray(coarse_value)
            if coarse.shape != x.shape or not np.isfinite(coarse).all():
                raise ValueError('coarse map must be finite and same shape as input')
            coarse = coarse.copy()
            call.update(status='OK', logits=logits.tolist(), coarse_sha256=_digest(coarse))
            return logits, coarse, call
        except Exception as exc:
            # Record every attempted forward, including malformed output/exception.
            call.update(status='FAILED', reason='NUMERICAL_FAILURE' if isinstance(exc, (ValueError, FloatingPointError)) else 'MODEL_FAILURE', error=str(exc))
            raise

    def patch(center, scale, support):
        widths = np.maximum(1, np.ceil(scale / spacing).astype(int))
        lo = np.maximum(0, np.asarray(center) - widths // 2)
        hi = np.minimum(x.shape, lo + widths)
        mask = np.zeros_like(valid)
        mask[tuple(slice(int(a), int(b)) for a, b in zip(lo, hi))] = True
        mask &= support
        return mask, [[int(a), int(b)] for a, b in zip(lo, hi)]

    def final_success(reason):
        out['status'] = 'OK' if out['candidates'] else 'NO_RELIABLE_RESPONSE'
        out['reason'] = reason

    try:
        baseline, coarse, initial_call = predict(x, 1, 'ORIGINAL_BASELINE', extra=False)
        out['original_baseline_logits'] = baseline.tolist()
        out['original_coarse_sha256'] = _digest(coarse)
        original_baseline = baseline.copy()
        if fixed_target_response(baseline, baseline, target)['baseline_margin'] <= 0:
            final_success('TARGET_SUPPORT_LOST')
            return out
        current_input = x.copy()
        baseline_call = initial_call
        rng = np.random.default_rng(cfg.seed)
        for probe_index in range(cfg.random_probes):
            if budget_reason(): raise _BudgetStop(budget_reason())
            available = np.argwhere(valid & ~probe_support)
            if not len(available):
                out.update(status='INPUT_UNSUPPORTED', reason='INSUFFICIENT_PROBE_SUPPORT')
                return out
            center = available[rng.integers(len(available))]
            mask, bounds = patch(center, min(cfg.scales_mm), valid & ~probe_support)
            probe_support |= mask
            logits, _, call = predict(np.where(mask, fill, x), 0, 'SEEDED_UNSEARCHED_DIAGNOSTIC_PROBE')
            response = fixed_target_response(original_baseline, logits, target)
            response.update(probe_index=probe_index, call_index=call['index'],
                            center_zyx=center.tolist(), bounds_zyx=bounds,
                            mask_flat_indices=np.flatnonzero(mask).tolist(),
                            support_voxels=int(mask.sum()), scale_mm=float(min(cfg.scales_mm)),
                            supporting_response=response['margin_delta'] > cfg.min_response,
                            accepted=False, candidate_eligible=False)
            out['probes'].append(response)
            out['random_probes_completed'] += 1
        for stage in range(1, cfg.stages + 1):
            if budget_reason(): raise _BudgetStop(budget_reason())
            remaining = valid & ~excluded
            if not remaining.any():
                final_success('VALID_SUPPORT_EXHAUSTED'); break
            search_support = remaining & ~searched
            if not search_support.any():
                final_success('SEARCH_SUPPORT_EXHAUSTED'); break
            if stage > 1:
                current_input = np.where(excluded, fill, x)
                baseline, coarse, baseline_call = predict(current_input, stage, 'RESIDUAL_BASELINE_AND_COARSE_REFRESH')
            stage_record = dict(stage=stage, baseline_logits=baseline.tolist(),
                                baseline_call_index=baseline_call['index'],
                                baseline_input_sha256=_digest(current_input),
                                coarse_sha256=_digest(coarse),
                                coarse_min=float(coarse.min()), coarse_max=float(coarse.max()),
                                removed_voxels=int(excluded.sum()),
                                remaining_valid_voxels=int(remaining.sum()),
                                candidate_record_indices=[], accepted_union_voxels=0,
                                status='RUNNING')
            out['stages'].append(stage_record)
            if fixed_target_response(baseline, baseline, target)['baseline_margin'] <= 0:
                final_success('TARGET_SUPPORT_LOST')
                stage_record.update(status=out['status'], reason=out['reason'])
                break
            scores = np.where(search_support, coarse, -np.inf)
            center = np.unravel_index(int(scores.argmax()), x.shape)
            stage_record['center_zyx'] = [int(i) for i in center]
            accepted_this_stage = np.zeros_like(valid)
            for scale in cfg.scales_mm:
                if budget_reason(): raise _BudgetStop(budget_reason())
                mask, bounds = patch(center, scale, remaining)
                # Same effective input mask is not evaluated twice within a stage.
                # A different stage uses a different baseline and is not conflated.
                key = (stage, np.packbits(mask).tobytes())
                if not mask.any() or key in seen_masks: continue
                seen_masks.add(key); searched |= mask
                logits, _, call = predict(np.where(mask, fill, current_input), stage, 'RESIDUAL_INPUT_OCCLUSION')
                response = fixed_target_response(baseline, logits, target)
                original_comparison = fixed_target_response(original_baseline, logits, target)
                response.update(stage=stage, call_index=call['index'],
                                stage_baseline_call_index=baseline_call['index'],
                                original_baseline_logits=original_baseline.tolist(),
                                cumulative_margin_drop_from_original=original_comparison['margin_delta'],
                                scale_mm=float(scale), bounds_zyx=bounds,
                                center_zyx=[int(i) for i in center],
                                mask_flat_indices=np.flatnonzero(mask).tolist(),
                                support_voxels=int(mask.sum()),
                                accepted=response['margin_delta'] > cfg.min_response)
                stage_record['candidate_record_indices'].append(len(out['records']))
                out['records'].append(response)
                if response['accepted']:
                    out['candidates'].append(response)
                    accepted_this_stage |= mask
                # Register each accepted result immediately so failure/timeout
                # later in the scale loop preserves the completed union evidence.
                stage_record['accepted_union_voxels'] = int(accepted_this_stage.sum())
                stage_record['accepted_union_flat_indices'] = np.flatnonzero(accepted_this_stage).tolist()
            excluded |= accepted_this_stage
            stage_record['status'] = 'OK'
            if budget_reason(): raise _BudgetStop(budget_reason())
            if not (valid & ~excluded).any():
                final_success('VALID_SUPPORT_EXHAUSTED'); break
            if not (valid & ~excluded & ~searched).any():
                final_success('SEARCH_SUPPORT_EXHAUSTED'); break
        else:
            raise _BudgetStop('STAGE_LIMIT')
        if out['status'] is None: final_success('SEARCH_COMPLETE')
    except _BudgetStop as exc:
        out.update(status='PARTIAL_BUDGET', reason=str(exc))
    except Exception as exc:
        out.update(status='FAILED', reason='NUMERICAL_FAILURE' if isinstance(exc, (ValueError, FloatingPointError)) else 'MODEL_FAILURE', error=str(exc))
    finally:
        out['elapsed_seconds'] = clock() - start
        out['probe_status'] = 'OK' if out['random_probes_completed'] == cfg.random_probes else 'INCOMPLETE'
        for stage_record in out['stages']:
            if stage_record['status'] == 'RUNNING':
                stage_record['status'] = out['status']
                stage_record['reason'] = out['reason']
        # The union includes partial-stage candidates that were accepted before
        # a later model failure; it is evidence, not a resumable cache.
        accepted_indices = sorted({i for r in out['candidates'] for i in r['mask_flat_indices']})
        out['accepted_union_flat_indices'] = accepted_indices
        out['accepted_union_voxels'] = len(accepted_indices)
    return out


def main():
    """One-command, CPU numpy-only interaction experiment; no clinical inputs."""
    import argparse
    import json
    from pathlib import Path
    import platform
    import subprocess
    import sys
    parser=argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        parser.error('output already exists; use a fresh path to preserve prior numerical evidence')
    x=np.zeros((5,5,5),dtype=float)
    a,b,c=(1,1,1),(3,3,3),(1,3,1)
    for p in (a,b,c):x[p]=1.
    def interaction_model(value):
        va,vb,vc=value[a],value[b],value[c]
        score=4*va+2*vb+3*(1-va)*vc
        coarse=np.zeros_like(value)
        coarse[a]=10*va;coarse[b]=8*vb;coarse[c]=(1+19*(1-va))*vc
        return [0.,score],coarse
    cfg=BudgetConfig(seed=17,scales_mm=(1.,))
    result=residual_input_occlusion_3d(interaction_model,x,np.ones_like(x,bool),1,(1,1,1),cfg)
    checks=dict(baselines_updated=[s['baseline_logits'] for s in result['stages']]==[[0.,6.],[0.,5.],[0.,2.]],
                coarse_maps_updated=len({s['coarse_sha256'] for s in result['stages']})==3,
                refreshed_search_centers=[s['center_zyx'] for s in result['stages']]==[list(a),list(c),list(b)],
                residual_responses=[r['margin_delta'] for r in result['candidates']]==[1.,3.,2.],
                budget_counts_all_refreshes=result['model_calls']==8 and result['extra_evaluations']==7,
                probes_diagnostic_only=result['random_probes_completed']==2 and all(not p['accepted'] for p in result['probes']),
                stage_limit_preserved=result['status']=='PARTIAL_BUDGET' and result['reason']=='STAGE_LIMIT')
    source=Path(__file__)
    payload=dict(run_id='EPI-NEXT-F1-RESIDUAL-CPU-SYNTHETIC-20261009-V2',
                 status='PASS' if all(checks.values()) else 'FAIL',checks=checks,
                 evidence_type='SYNTHETIC_INTERACTION_MODEL_ONLY',
                 git_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                 source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                 config_sha256=hashlib.sha256(json.dumps(asdict(cfg),sort_keys=True).encode()).hexdigest(),
                 input_manifest_sha256=_digest(x),checkpoint_sha256=None,
                 model_definition='score=4*a+2*b+3*(1-a)*c; spatial coarse changes with a',
                 environment=dict(python=sys.version,numpy=np.__version__,platform=platform.platform(),device='cpu'),
                 GPU='NOT RUN',real_CT='NOT RUN',process_running=False,result=result)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream:
        stream.write(json.dumps(payload,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(status=payload['status'],checks=checks,sha256=hashlib.sha256(args.output.read_bytes()).hexdigest()),indent=2))
    return 0 if all(checks.values()) else 1


if __name__=='__main__':raise SystemExit(main())
