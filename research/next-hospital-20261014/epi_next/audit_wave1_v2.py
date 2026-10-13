"""Saved-evidence audits plus bounded synthetic controls; zero real forwards."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import torch
import yaml
from .controls_v2 import run_controls


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path,expected=None):
    if expected is not None and sha(path)!=expected:raise ValueError('saved evidence SHA mismatch')
    return json.loads(Path(path).read_text())
def write(path,value):
    encoded=json.dumps(value,indent=2,allow_nan=False)+'\n'
    with Path(path).open('x') as f:f.write(encoded)


def e1_audit(root,baseline,classification,evaluation):
    old_source=root/'scripts/occlusion_runner.py';old_config=root/'configs/occlusion_instability_v1.yaml'
    parsed=ast.parse(old_source.read_text());node=next(n for n in parsed.body if isinstance(n,ast.FunctionDef) and n.name=='build_grid')
    env={};exec(compile(ast.Module(body=[node],type_ignores=[]),str(old_source),'exec'),env)
    grids=[]
    for size in (16,32,64):
        positions=env['build_grid'](224,size,size//2)
        old_starts=sorted({p[0] for p in positions});new_starts=list(range(0,224,size))
        grids.append(dict(scale=size,old_stride=size//2,old_starts=old_starts,old_windows=len(positions),
            old_tail_full_block_start=224-size,new_stride=size,new_starts=new_starts,
            new_windows=len(new_starts)**2,new_tail_extent=224-new_starts[-1],
            new_policy='disjoint tiles; clip at FOV, no shifted full tail window'))
    case_details=[]
    for record in baseline['records']:
        result=read(record['result_path'],record['result_sha256']);e1=result['E1'];z=e1['records'][0]['baseline_logits']
        per_scale=[]
        for grid in grids:
            records=[r for r in e1['records'] if r['scale_pixels']==grid['scale']]
            expected=[[[y,min(y+grid['scale'],224)],[x,min(x+grid['scale'],224)]] for y in grid['new_starts'] for x in grid['new_starts']]
            assert [r['bounds_yx'] for r in records]==expected
            assert sum(r['support_pixels'] for r in records)==224**2
            per_scale.append(dict(scale=grid['scale'],windows=len(records),accepted_windows=sum(r['accepted'] for r in records),
                zero_response_windows=sum(r['margin_delta']==0 for r in records),positive_response_windows=sum(r['margin_delta']>0 for r in records),
                evaluated_support_sum=sum(r['support_pixels'] for r in records)))
        case_details.append(dict(case_index=record['case_index'],fixed_target=result['target'],baseline_logits=z,
            baseline_argmax=int(np.argmax(z)),target_matches_prediction=int(np.argmax(z))==result['target'],
            margin=z[1]-z[0],positive_probability=e1['records'][0]['baseline_probability'],per_scale=per_scale))
    areas=[]
    for case in evaluation['case_results']:
        for budget,entry in case['budgets'].items():
            for scale,metrics in entry['scales'].items():
                areas.append(dict(case_index=case['case_index'],algorithm=case['algorithm'],scale=scale,budget=float(budget),
                    selected_pixels=metrics['candidate_voxels'],support_pixels=metrics['support_voxels'],
                    actual_fraction=metrics['actual_budget_fraction'],status=metrics['status']))
    config=yaml.safe_load(old_config.read_text())
    a=classification['metrics'][0]
    assert a['checkpoint_sha256']==baseline['checkpoint_sha256']
    return dict(schema='E1_SAVED_AUDIT_V2',new_real_forwards=0,grids=grids,
        historical_checkpoint_matches_real_E1=True,checkpoint_sha256=baseline['checkpoint_sha256'],
        historical_A_summary=a,classification_semantics='1A=collection proxy1, 1B=collection proxy0; mean slice p at patient threshold .5; not clinical truth',
        cases=case_details,actual_areas=areas,old_fill=config['preprocessing']['fill'],old_fill_domain='resized [0,1] grayscale before RGB ImageNet normalization',
        current_fill=0.,current_fill_domain='same domain; N(raw=0), not normalized RGB zero',
        old_fill_equivalent_window_HU=-600.,current_fill_equivalent_window_HU=-1350.,
        original_model_source_sha256=sha(old_source),old_configuration_sha256=sha(old_config),
        map_policy='current disjoint signed margin assignment, reliable=margin_delta>0; native inverse nearest rasterization; DATA floor area budget with C-order tie-break, no quota fill',
        historical_map_policy='overlapping blocks averaged by coverage; q0-qg positive clipped; epsilon1e-6; top10percent blocks with ties; 14x14 area projection',
        priority_factor='E1-FILL only: frozen constant0 vs predeclared Gaussian blur; density difference documented, no parallel density variant in wave1',
        other_hypotheses='density/model dependence/partial-reference mismatch not identified as unique causes')


def e2_saved_audit(telemetry):
    groups=[];reverse=0;replay_steps=0
    for record in telemetry['records']:
        result=read(record['result_path'],record['result_sha256'])
        path=Path(record['telemetry_path'])
        if sha(path)!=record['telemetry_sha256']:raise ValueError('telemetry SHA mismatch')
        events=[json.loads(s) for s in path.read_text().splitlines()]
        for stage in result['stages']:
            es=[e for e in events if e['scale_index']==stage['scale_index'] and e['stage']==stage['stage']]
            parameter=torch.nn.Parameter(torch.tensor(es[0]['mask_before'],dtype=torch.float32))
            optimizer=torch.optim.Adam([parameter],lr=result['config']['learning_rate'])
            max_before=0.;max_step=0.;ratios=[];common_shares=[];decomp_error=0.
            reference=np.array(stage['baseline_logits'],float)
            for event in es:
                max_before=max(max_before,float((parameter.detach()-torch.tensor(event['mask_before'])).abs().max()))
                optimizer.zero_grad(set_to_none=True);parameter.grad=torch.tensor(event['combined_gradient'],dtype=torch.float32)
                optimizer.step();replay_steps+=1
                max_step=max(max_step,float((parameter.detach()-torch.tensor(event['mask_before_projection'])).abs().max()))
                with torch.no_grad():parameter.clamp_(0,1)
                delta=reference-np.array(event['logits'],float);dc=delta.mean();dm=delta[1]-delta[0]
                common=2*dc**2;margin=.5*dm**2;total=common+margin
                decomp_error=max(decomp_error,abs(total-event['similarity']))
                common_shares.append(common/total if total else 0.)
                ratios.append(event['similarity_gradient_norm']/event['weighted_sparsity_gradient_norm'])
                reverse+=3 # 2 autograd.grad + 1 loss.backward, source-derived
            groups.append(dict(case_index=record['case_index'],grid=stage['grid'],epochs=len(es),
                optimizer_replay_before_max_error=max_before,optimizer_replay_step_max_error=max_step,
                optimizer_replay_last_step=int(optimizer.state[parameter]['step']),
                common_shift_share_median=float(np.median(common_shares)),common_shift_share_max=max(common_shares),
                common_shift_share_last=common_shares[-1],logits_L2_decomposition_max_error=decomp_error,
                grad_norm_ratio_median=float(np.median(ratios)),projection_clipped=sum(e['projection_below_zero']+e['projection_above_one'] for e in es),
                joint_feasible_epochs=sum(e['feasible'] for e in es),mask_updated_epochs=int(sum(np.any(np.asarray(e['mask_before'])!=np.asarray(e['mask_after_projection'])) for e in es))))
    assert reverse==1800 and replay_steps==600
    return dict(schema='E2_SAVED_MECHANISM_AUDIT_V2',new_real_forwards=0,
        branch='LOSS_TRADEOFF',branch_scope='observed100step prefix only; no proof of convergence or infeasibility; remaining causes unresolved',groups=groups,
        Ls='sum over complete logits, not mean MSE',Lm='mean abs of all trainable coarse mask cells, not retention after protected valid support',
        Lm_theoretical_lower_bound=0.,fixed_coarse_cells=0,protected_invalid_pixels='retention=1 after upsample; not included as fixed values in Lm; does not add theoretical floor',
        mask_domain='raw prepared scalar multiplied before RGB ImageNet normalization: N(m*x), replacement scalar0; not m*N(x)',
        original_real_cost=dict(forward_direct_measured=606,loss_backward_source_derived=600,autograd_grad_source_derived=1200,total_reverse_source_derived=reverse,
            autograd_create_graph=False,retain_graph='two per-step gradient queries retain the current graph; loss.backward then frees it; logs contain only detached values'),
        offline_audit_cost=dict(optimizer_replay_steps=replay_steps,forwards=0,backward_or_autograd=0),
        runtime_identity='not recorded in old real log; source + exact persistent Adam replay support update path; no invented runtime object-ID check',
        model_eval_and_frozen='verified source; no independent before-after in-memory BN snapshot in old real run; synthetic control checks snapshots')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('output','baseline','telemetry','classification','evaluation'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('existing audit preserved')
    started=time.monotonic();root=Path(__file__).resolve().parents[3]
    baseline=read(args.baseline,'0000000000000000000000000000000000000000000000000000000000000000')
    telemetry=read(args.telemetry,'0000000000000000000000000000000000000000000000000000000000000000')
    classification=read(args.classification);evaluation=read(args.evaluation,'0000000000000000000000000000000000000000000000000000000000000000')
    e1=e1_audit(root,baseline,classification,evaluation);e2=e2_saved_audit(telemetry)
    json.dumps([e1,e2],allow_nan=False) # validate offline outputs before controls
    controls=run_controls()
    args.output.mkdir(parents=True,exist_ok=False)
    for name,value in (('e1_audit',e1),('e2_saved_audit',e2),('synthetic_controls',controls)):write(args.output/(name+'.json'),value)
    write(args.output/'delivery.json',dict(status=controls['status'],new_real_forwards=0,elapsed_seconds=time.monotonic()-started,
        inputs={str(p.resolve()):sha(p) for p in (args.baseline,args.telemetry,args.classification,args.evaluation)},
        source_hashes={p.name:sha(p) for p in (Path(__file__),Path(__file__).with_name('controls_v2.py'),Path(__file__).with_name('hspi.py'))},
        outputs={p.name:sha(p) for p in args.output.glob('*.json')},controls_cost=controls['cost'],offline_optimizer_replay_steps=600))
    print(json.dumps(dict(status=controls['status'],new_real_forwards=0,controls_cost=controls['cost'],delivery_sha256=sha(args.output/'delivery.json'))))
    return 0 if controls['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
