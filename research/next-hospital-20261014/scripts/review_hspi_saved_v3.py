"""Read exactly six saved Wave1 trajectories; never import or execute a model.

Output is private because it binds local case-indexed assets. No patient arrays
are opened. Torch is used only for safe checkpoint decoding and Adam restoration
onto a dummy parameter without an optimizer update.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def first(rows, predicate):
    return next((r['step'] for r in rows if predicate(r)), None)


def series(rows, key):
    values = [r[key] for r in rows]
    tail = values[-100:]
    center = (len(tail) - 1) / 2
    mean = statistics.mean(tail)
    slope = sum((i-center)*(v-mean) for i, v in enumerate(tail)) / sum((i-center)**2 for i in range(len(tail)))
    return dict(first=values[0], last=values[-1], min=min(values), max=max(values),
                tail100_mean=mean, tail100_std=statistics.pstdev(tail),
                tail100_slope_per_step=slope, tail100_delta=tail[-1]-tail[0],
                tail100_decreasing_transitions=sum(b<a for a,b in zip(tail,tail[1:])),
                tail100_increasing_transitions=sum(b>a for a,b in zip(tail,tail[1:])))


def inspect_checkpoint(asset, rows, result, folder):
    import torch
    path = Path(asset['path']).resolve()
    if path.parent != folder.resolve():
        raise ValueError('checkpoint outside exact trajectory folder')
    if sha(path) != asset['sha256']:
        raise ValueError('checkpoint byte binding mismatch')
    state = torch.load(path, map_location='cpu', weights_only=True)
    required = {'mask','optimizer','torch_rng','python_rng','numpy_rng','config','step','baseline_logits','best_so_far','proposal_sha256','execution_lock_sha256'}
    if not required <= state.keys():
        raise ValueError('incomplete saved checkpoint')
    step = asset['step']
    mask = state['mask']
    if mask.shape != (1,1,7,7) or not torch.isfinite(mask).all():
        raise ValueError('invalid saved mask')
    matches = torch.equal(mask[0,0], torch.tensor(rows[step-1]['mask_after_projection'],dtype=mask.dtype))
    dummy = torch.nn.Parameter(torch.zeros_like(mask))
    optimizer = torch.optim.Adam([dummy],lr=.01,betas=(.9,.999),eps=1e-8)
    optimizer.load_state_dict(state['optimizer'])
    restored = optimizer.state[dummy]
    original = next(iter(state['optimizer']['state'].values()))
    restored_exact = all(torch.equal(restored[k],v) if torch.is_tensor(v) else restored[k]==v for k,v in original.items())
    checks = dict(checkpoint_step_matches=state['step']==step,
        adam_step_matches=int(restored['step'])==step, mask_matches_post_projection=matches,
        adam_moments_shape_matches=restored['exp_avg'].shape==mask.shape==restored['exp_avg_sq'].shape,
        adam_moments_finite=bool(torch.isfinite(restored['exp_avg']).all() and torch.isfinite(restored['exp_avg_sq']).all()),
        optimizer_state_restores_exactly=restored_exact,
        baseline_matches=torch.equal(state['baseline_logits'].flatten(),torch.tensor(result['baseline_logits'],dtype=mask.dtype)),
        proposal_binding_matches=state['proposal_sha256']==result['proposal_sha256'],
        execution_binding_matches=state['execution_lock_sha256']==result['lock_sha256'],
        config_matches=state['config']==dict(weight=result['mask_weight'],grid=[7,7],learning_rate=.01,steps=1000),
        torch_rng_present=state['torch_rng'].dtype==torch.uint8,
        python_rng_present=len(state['python_rng'])==3,
        numpy_rng_present=state['numpy_rng']['name']=='MT19937' and len(state['numpy_rng']['keys'])==624)
    if not all(checks.values()):
        raise ValueError(f'checkpoint checks failed: {checks}')
    return dict(step=step,sha256=asset['sha256'],bytes=path.stat().st_size,checks=checks,
                optimizer_param_group=state['optimizer']['param_groups'][0],
                adam_exp_avg_norm=float(restored['exp_avg'].norm()),
                adam_exp_avg_sq_norm=float(restored['exp_avg_sq'].norm()))


def review(root):
    import torch
    expected = {f'case-{case}-lambda-{weight}' for case in (1,2,3) for weight in ('0.1','1.0')}
    actual = {p.name for p in root.glob('case-*') if p.is_dir()}
    if expected != actual:
        raise ValueError('reader requires exact original six trajectories')
    output = dict(schema='HSPI_SAVED_TRAJECTORY_REVIEW_V3',new_model_forwards=0,
                  new_model_backwards=0,new_optimizer_updates=0,alpha=.005,beta=.08,
                  near_beta_diagnostic=.088,near_beta_is_not_a_cpf_threshold=True,records=[])
    for folder in sorted(root.glob('case-*')):
        result = json.loads((folder/'result.json').read_text())
        rows = [json.loads(line) for line in (folder/'epochs.jsonl').read_text().splitlines()]
        if len(rows)!=1000 or [r['step'] for r in rows]!=list(range(1,1001)):
            raise ValueError('trajectory step coverage mismatch')
        keys=('similarity','sparsity','peak_gap','logits','epoch','feasible')
        if any(any(r[k]!=t[k] for k in keys) for r,t in zip(rows,result['trace'])):
            raise ValueError('epochs/result trace mismatch')
        if not all(math.isfinite(r[k]) for r in rows for k in ('similarity','sparsity','peak_gap','loss')):
            raise ValueError('nonfinite saved trajectory')
        baseline=torch.tensor(result['baseline_logits'],dtype=torch.float32)
        for row in rows:
            mask=torch.tensor(row['mask_before'],dtype=torch.float32)
            sorted_mask=torch.sort(mask.flatten(),descending=True).values
            independent_ls=float(((baseline-torch.tensor(row['logits'],dtype=torch.float32))**2).sum())
            independent_lm=float(mask.abs().mean())
            independent_gap=float(sorted_mask[0]-sorted_mask[1])
            independent_loss=float(torch.tensor(independent_ls)+result['mask_weight']*torch.tensor(independent_lm))
            if (independent_ls!=row['similarity'] or independent_lm!=row['sparsity']
                    or independent_gap!=row['peak_gap'] or independent_loss!=row['loss']):
                raise ValueError('saved scalar/mask/logit numerical mismatch')
            if row['feasible'] != (independent_ls<.005 and independent_lm<.08 and independent_gap>0):
                raise ValueError('saved historical CPF policy mismatch')
        minrow = min(rows,key=lambda r:r['sparsity'])
        record = dict(case_index=result['case_index'],weight=result['mask_weight'],status=result['status'],steps=len(rows),
            result_sha256=sha(folder/'result.json'),epochs_sha256=sha(folder/'epochs.jsonl'),
            all_step_numerical_reconstruction='EXACT_FLOAT32_LS_LM_GAP_LOSS',
            conditions=dict(similarity_pass=sum(r['similarity']<.005 for r in rows),
                sparsity_pass=sum(r['sparsity']<.08 for r in rows),
                positive_gap=sum(r['peak_gap']>0 for r in rows),
                paper_joint=sum(r['similarity']<.005 and r['sparsity']<.08 for r in rows),
                historical_joint=sum(r['feasible'] for r in rows)),
            first_steps=dict(similarity_pass=first(rows,lambda r:r['similarity']<.005),
                sparsity_pass=first(rows,lambda r:r['sparsity']<.08),
                paper_joint=first(rows,lambda r:r['similarity']<.005 and r['sparsity']<.08),
                near_beta_diagnostic=first(rows,lambda r:r['sparsity']<=.088),
                similarity_and_near_beta=first(rows,lambda r:r['similarity']<.005 and r['sparsity']<=.088)),
            series={key:series(rows,key) for key in ('similarity','sparsity','peak_gap')},
            min_sparsity_paired=dict(step=minrow['step'],similarity=minrow['similarity'],sparsity=minrow['sparsity'],peak_gap=minrow['peak_gap']),
            sampled_gradient_rows=[{k:r[k] for k in ('step','grad_ls_norm','weighted_grad_lm_norm','gradients_cosine','combined_gradient_norm','update_max','clip_below','clip_above')} for r in rows if 'grad_ls_norm' in r],
            nonzero_update_rows=sum(r['update_max']>0 for r in rows),
            classifier_unchanged=result['model_unchanged'],
            checkpoints=[inspect_checkpoint(a,rows,result,folder) for a in result['checkpoint_assets']])
        output['records'].append(record)
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if '.local' not in args.output.resolve().parts:
        raise ValueError('case-indexed output must remain ignored/private .local')
    result=review(args.root.resolve())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(output=str(args.output.resolve()),sha256=sha(args.output),records=len(result['records']),new_model_calls=0)))


if __name__=='__main__':
    main()
