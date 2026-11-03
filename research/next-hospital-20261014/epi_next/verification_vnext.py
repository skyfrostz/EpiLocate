"""Independent numerical/geometry witness; never loads CT, GT or model weights.

Saved outputs are audited without changing acceptance, thresholds or membership.
2D masks are in MODEL INPUT YX, not original DICOM coordinates.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .localization import fixed_target_response


def numerical_witness(result):
    records = result['records']
    recomputed = [fixed_target_response(r['baseline_logits'], r['perturbed_logits'], r['target']) for r in records]
    margin_order = sorted(range(len(records)), key=lambda i: (-recomputed[i]['margin_delta'], i))
    probability_order = sorted(range(len(records)), key=lambda i: (-recomputed[i]['probability_delta'], i))
    fields = ('baseline_margin', 'perturbed_margin', 'margin_delta', 'baseline_probability', 'perturbed_probability', 'probability_delta')
    mismatches = [i for i, (r, v) in enumerate(zip(records, recomputed))
                  if any(not np.isclose(r[f], v[f], rtol=0, atol=1e-12) for f in fields)]
    targets=sorted({r['target'] for r in records})
    return dict(status='FAIL' if mismatches or len(targets)>1 else 'PASS', fixed_targets=targets,
                numerical_mismatch_record_indices=mismatches, margin_order_record_indices=margin_order,
                probability_order_record_indices=probability_order,
                saturated_nonzero_margin_record_indices=[i for i,r in enumerate(recomputed) if r['probability_delta']==0 and r['margin_delta']!=0],
                records=[dict(record_index=i, bounds_yx=records[i]['bounds_yx'], accepted=records[i]['accepted'], **v)
                         for i,v in enumerate(recomputed)],
                acceptance_rule='UNCHANGED_FROM_SOURCE', model_calls=0)


def nearest_cell(grid, cell, shape):
    """Independent integer implementation of PyTorch nearest (not nearest-exact)."""
    if len(grid)!=2 or len(cell)!=2 or len(shape)!=2 or any(type(n) is not int or n<1 for n in (*grid,*shape)):
        raise ValueError('positive integer grid and H,W required')
    if any(type(c) is not int or not 0<=c<n for c,n in zip(cell,grid)): raise ValueError('cell outside grid')
    yy=np.arange(shape[0],dtype=np.int64)*grid[0]//shape[0]
    xx=np.arange(shape[1],dtype=np.int64)*grid[1]//shape[1]
    return (yy[:,None]==cell[0]) & (xx[None,:]==cell[1])


def hspi_witness(result, shape, valid_mask=None):
    """Recompute CPF and PSMI from saved rounds; geometry needs known support."""
    shape=tuple(shape)
    if len(shape)!=2 or any(type(n) is not int or n<1 for n in shape): raise ValueError('explicit H,W required')
    if valid_mask is not None and (valid_mask.dtype!=np.bool_ or valid_mask.shape!=shape): raise ValueError('boolean support required')
    cfg=result['config']; stages=[]; patches=[]; errors=[]; excluded={}
    for stage in result['stages']:
        si=stage['scale_index'];grid=stage['grid'];trace=stage['trace']
        conditions=[(t['similarity']<cfg['similarity_threshold'], t['sparsity']<cfg['sparsity_threshold'], t['peak_gap']>cfg['min_peak_gap']) for t in trace]
        feasible=[t for t,c in zip(trace,conditions) if all(c)]
        summary=dict(scale_index=si,stage=stage['stage'],grid=grid,
                     similarity_pass_epochs=sum(c[0] for c in conditions),sparsity_pass_epochs=sum(c[1] for c in conditions),
                     peak_pass_epochs=sum(c[2] for c in conditions),joint_feasible_epochs=len(feasible),
                     selected=None,status=stage['status'])
        if any(t['feasible']!=all(c) for t,c in zip(trace,conditions)):errors.append('CPF_TRACE_CONDITION_MISMATCH')
        selected=stage.get('selected')
        if selected:
            if not feasible or selected['peak_gap']!=max(t['peak_gap'] for t in feasible): errors.append('CPF_NOT_MAX_FEASIBLE_GAP')
            epoch=next((t for t in feasible if t['epoch']==selected['selected_epoch']),None)
            if epoch is None or any(epoch[k]!=selected[k] for k in ('similarity','sparsity','peak_gap')):errors.append('CPF_SELECTED_ROUND_MISMATCH')
            mask=np.zeros(shape,bool);indices=np.asarray(selected['mask_flat_indices'])
            if indices.ndim!=1 or not np.issubdtype(indices.dtype,np.integer) or not len(indices) or indices.min()<0 or indices.max()>=mask.size or len(np.unique(indices))!=len(indices): raise ValueError('invalid patch indices')
            mask.flat[indices]=True
            expected=nearest_cell(grid,selected['cell_yx'],shape)
            mapping=None if valid_mask is None else bool(np.array_equal(mask,expected & valid_mask))
            if mapping is False: errors.append('MODEL_GRID_REVERSE_MAPPING_MISMATCH')
            prior=excluded.setdefault(si,set())
            if tuple(selected['cell_yx']) in prior:errors.append('HIERARCHY_SELECTED_EXCLUDED_CELL')
            learned=np.asarray(selected['learned_mask'],float)
            if learned.shape!=tuple(grid) or not np.isfinite(learned).all():raise ValueError('invalid learned mask')
            active=learned.copy()
            for cell in prior:active[cell]=0
            values=np.sort(active.ravel())
            if not np.isclose(values[-1]-values[-2],selected['peak_gap'],rtol=0,atol=1e-7):errors.append('CPF_LEARNED_GAP_MISMATCH')
            if np.unravel_index(int(active.argmax()),active.shape)!=tuple(selected['cell_yx']):errors.append('CPF_LEARNED_PEAK_CELL_MISMATCH')
            prior.add(tuple(selected['cell_yx']))
            yy,xx=np.where(mask)
            summary['selected']=dict(cell_yx=selected['cell_yx'],selected_epoch=selected['selected_epoch'],
                similarity=selected['similarity'],sparsity=selected['sparsity'],peak_gap=selected['peak_gap'],
                bounds_yx=[[int(yy.min()),int(yy.max())+1],[int(xx.min()),int(xx.max())+1]],
                support_pixels=int(mask.sum()),model_grid_mapping_matches=mapping,
                native_dicom_mapping='NOT_VERIFIED')
            patches.append((si,stage['stage'],mask))
        stages.append(summary)
    pairs=[];selection=[]
    for si,sj,mask in patches:
        if si!=cfg['benchmark_scale']:continue
        supported=set()
        for oi,oj,other in patches:
            if oi==si:continue
            inter=int((mask & other).sum());union=int((mask | other).sum())
            pairs.append(dict(benchmark_scale=si,benchmark_stage=sj,other_scale=oi,other_stage=oj,
                              intersection_pixels=inter,iou=inter/union,intersects=inter>0))
            if inter:supported.add(oi)
        selection.append(dict(other_scale_support=len(supported),retained=len(supported)>=cfg['min_other_scale_support']))
    if selection!=result.get('psmi_selection',[]):errors.append('PSMI_SAVED_VOTE_MISMATCH')
    if sum(s['retained'] for s in selection)!=len(result['candidates']):errors.append('PSMI_CANDIDATE_COUNT_MISMATCH')
    return dict(status='FAIL' if errors else 'PASS',errors=errors,source_status=result['status'],source_reason=result.get('reason'),
                unchanged_config=cfg,stages=stages,pairwise_overlap=pairs,recomputed_psmi=selection,
                candidates_per_scale=[sum(si==i for si,_,_ in patches) for i in range(len(cfg['grids']))],
                geometry_scope='MODEL_INPUT_GRID_YX',support_known=valid_mask is not None,
                native_dicom_mapping='NOT_VERIFIED',model_calls=0,
                causal_limit='Spatial disagreement is observed; model instability requires repeat/input experiments and is not inferred here.')


def residual_region_witness(result, valid_mask, include_indices=False):
    """Distinguish completed checks from coarse proposals and diagnostic probes.

    Failed calls are not validated regions. Accepted support at the last stage
    is selected for later exclusion, but may never have been removed from input.
    """
    valid=np.asarray(valid_mask)
    if valid.dtype!=np.bool_ or list(valid.shape)!=result['volume_shape_zyx']:raise ValueError('boolean model-space valid support required')
    checked=np.zeros_like(valid);accepted=np.zeros_like(valid);diagnostic=np.zeros_like(valid);removed=np.zeros_like(valid)
    for record in result['records']:
        checked.flat[record['mask_flat_indices']]=True
        if record['accepted']:accepted.flat[record['mask_flat_indices']]=True
    for probe in result['probes']:diagnostic.flat[probe['mask_flat_indices']]=True
    last_stage=result['stages'][-1]['stage'] if result['stages'] else 1
    for record in result['candidates']:
        if record['stage']<last_stage:removed.flat[record['mask_flat_indices']]=True
    masks=dict(verified_candidates=accepted & valid,checked_nonpositive=checked & ~accepted & valid,
               unchecked=valid & ~checked,actually_removed_before_last_stage=removed & valid,
               diagnostic_probe_support=diagnostic & valid)
    return dict(coordinate_space='MODEL_INPUT_GRID_ZYX',initial_coarse_sha256=result.get('original_coarse_sha256'),
                coarse_proposals=[dict(stage=s['stage'],center_zyx=s.get('center_zyx'),coarse_sha256=s['coarse_sha256']) for s in result['stages']],
                regions={k:dict(voxels=int(m.sum()),mask_sha256=hashlib.sha256(m.tobytes()).hexdigest(),
                               **(dict(flat_indices=np.flatnonzero(m).tolist()) if include_indices else {})) for k,m in masks.items()},
                stop_status=result['status'],stop_reason=result['reason'],
                failed_calls=sum(c['status']=='FAILED' for c in result['calls']),
                timeout_enforcement=result['timeout_enforcement'],native_dicom_mapping='NOT_VERIFIED')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--input-sha256',required=True)
    parser.add_argument('--shape-yx',type=int,nargs=2,required=True);parser.add_argument('--all-valid-synthetic',action='store_true')
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('output exists; prior evidence preserved')
    raw=args.input.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.input_sha256:raise ValueError('source receipt hash mismatch')
    payload=json.loads(raw)
    if args.all_valid_synthetic and (payload.get('patient_count')!=0 or payload.get('evidence_scope')!='SYNTHETIC_INPUT_REAL_CHECKPOINT_EXECUTABILITY'):
        raise ValueError('all-valid support assertion restricted to known synthetic receipt')
    support=np.ones(args.shape_yx,bool) if args.all_valid_synthetic else None
    e1=numerical_witness(payload['E1']);e2=hspi_witness(payload['E2'],args.shape_yx,support)
    out=dict(evidence_type='SAVED_SYNTHETIC_RECEIPT_INDEPENDENT_WITNESS',source_receipt_sha256=args.input_sha256,
             source_git_sha=payload['git_sha'],source_checkpoint_sha256=payload['checkpoint_sha256'],source_input_sha256=payload['input_sha256'],
             E1=e1,E2=e2,model_calls=0,patient_count=0,status='PASS' if e1['status']==e2['status']=='PASS' else 'FAIL')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream:stream.write(json.dumps(out,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(status=out['status'],sha256=hashlib.sha256(args.output.read_bytes()).hexdigest())))
    return 0 if out['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
