"""Saved P1 metadata/Mask/trajectory analysis; never load CT, GT or weights.

Fixed descriptors: stable top-five ranks, coarse values >=.5 and >=.8.
They describe saved masks and never change CPF or candidate selection.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np

from review_p1_retry_v8 import case_review, flat, ref, rows

SEMANTIC_KEYS = ('mode', 'image_size', 'steps', 'zeta', 'lr', 'lam', 'alpha', 'beta',
                 'adam_betas', 'adam_eps', 'align_corners', 'adapter_policy',
                 'masking_policy', 'tie_policy')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def bound_json(binding):
    if ref(binding['path'])['sha256'] != binding['sha256']:
        raise ValueError('METADATA_SHA_DRIFT')
    return json.loads(Path(binding['path']).read_text())


def trajectory(values, selected_cell=None):
    cells = [int(np.asarray(flat(row['mask']), dtype=np.float32).argmax()) for row in values]
    runs = []
    for row, cell in zip(values, cells):
        if not runs or runs[-1]['cell'] != cell:
            runs.append({'cell': cell, 'first_epoch': row['epoch'], 'last_epoch': row['epoch'],
                         'observations': 1})
        else:
            runs[-1]['last_epoch'] = row['epoch']; runs[-1]['observations'] += 1
    count = Counter(cells)
    return {'observations': len(values), 'coordinate_frequency': dict(sorted(count.items())),
            'adjacent_observation_switches': max(0, len(runs)-1), 'runs': runs,
            'modal_cell': None if not cells else min(count, key=lambda c: (-count[c], c)),
            'selected_cell_observations': None if selected_cell is None else count[selected_cell],
            'selected_cell_fraction': None if selected_cell is None or not cells else count[selected_cell]/len(cells),
            'first_cell': None if not cells else cells[0], 'last_cell': None if not cells else cells[-1],
            'singleton_patch_coordinate_agreement': None if len(cells)<2 else
                sum(a == b for a, b in zip(cells, cells[1:]))/(len(cells)-1),
            'tie_policy': 'first flat argmax; epoch order preserved',
            'switch_semantics': 'adjacent recorded observations in this subset, not necessarily adjacent original epochs'}


def native_index(geometry):
    inverse = np.asarray(geometry['native_to_model_zyx'], dtype=np.float64)
    forward = np.asarray(geometry['model_to_native_zyx'], dtype=np.float64)
    if not np.allclose(inverse @ forward, np.eye(4), atol=1e-9, rtol=0):
        raise ValueError('GEOMETRY_INVERSE_MISMATCH')
    yy, xx = np.indices(geometry['native_shape_rc'])
    points = np.stack((np.full_like(yy, geometry['native_slice_index_zero_based']), yy, xx), axis=-1)
    mapped = points @ inverse[:3, :3].T + inverse[:3, 3]
    if not np.allclose(mapped[...,0], 0, atol=1e-9, rtol=0):
        raise ValueError('GEOMETRY_SLICE_MISMATCH')
    iy = np.floor(mapped[...,1]+.5).astype(int); ix = np.floor(mapped[...,2]+.5).astype(int)
    if iy.min()<0 or ix.min()<0 or iy.max()>=224 or ix.max()>=224:
        raise ValueError('GEOMETRY_OUTSIDE_MODEL_FOV')
    return iy, ix


def patch_description(cell, value, iy, ix):
    row, col = divmod(int(cell), 7)
    y0, y1, x0, x1 = row*32, (row+1)*32, col*32, (col+1)*32
    support = (iy>=y0)&(iy<y1)&(ix>=x0)&(ix<x1)
    yy, xx = np.nonzero(support)
    return {'cell': int(cell), 'coarse_rc': [row,col], 'value': float(value),
            'model_yx_bbox_half_open': [y0,y1,x0,x1], 'native_pixels': int(support.sum()),
            'native_yx_bbox_half_open': None if not len(yy) else
                [int(yy.min()),int(yy.max()+1),int(xx.min()),int(xx.max()+1)],
            'evidence_role': 'descriptive_saved_M_cell_only'}


def analyze(control, output):
    output.mkdir(parents=True, exist_ok=True)
    ready_path = control/'final-readiness-v8.json'
    if ref(ready_path)['sha256'] != '0000000000000000000000000000000000000000000000000000000000000000':
        raise ValueError('P1_READINESS_FROZEN_SHA_DRIFT')
    ready = json.loads(ready_path.read_text()); proposal = bound_json(ready['proposal'])
    prepared_delivery = bound_json(ready['prepared_delivery'])
    cfg = proposal['core_config']; semantic = {k: cfg[k] for k in SEMANTIC_KEYS}
    if digest(cfg) != ready['core_config_sha256']:
        raise ValueError('CORE_CONFIG_BINDING_DRIFT')
    src = ready['local_source_bindings']
    core_path = next(p for p in src if p.endswith('/hspi_core_v3.py'))
    adapter_path = next(p for p in src if p.endswith('/first_real_e1_e2.py'))
    for path in (core_path, adapter_path):
        if ref(path)['sha256'] != src[path]: raise ValueError('SCIENTIFIC_SOURCE_DRIFT')
    runner = Path(ready['execution_output']); cases = []
    for record in ready['records']:
        index = record['case_index']; audited = case_review(record, runner)
        result_path = runner/f'case-{index}-result.json'
        result = json.loads(result_path.read_text())
        if (result['observed_iterations']!=10000 or result['completed_steps']!=10000 or
            result['optimizer_updates']!=10000 or not result['best_is_full_plan']):
            raise ValueError('P1_NOT_FULL_TERMINAL_BRANCH')
        old, old_tail = rows(record['epochs']['path'])
        new, new_tail = rows(runner/f'case-{index}-new-epochs.jsonl')
        if old_tail or new_tail: raise ValueError('INCOMPLETE_TRACE_TAIL')
        values = [{'epoch':r['step'], 'ls':r['similarity'], 'lm':r['sparsity'],
                   'gap':r['peak_gap'], 'mask':r['mask_before'], 'logits':r['logits']} for r in old]+new
        baseline = np.asarray(result['baseline_logits'], dtype=np.float32)
        errors = {'ls':0.,'lm':0.,'gap':0.}
        for item in values:
            m = np.asarray(flat(item['mask']), dtype=np.float32)
            if m.size!=49 or not np.isfinite(m).all() or (m<0).any() or (m>1).any():
                raise ValueError('INVALID_SAVED_MASK')
            logits = np.asarray(item['logits'], dtype=np.float32)
            ranking = np.sort(m)
            reconstructed = {'ls':float(((baseline-logits)**2).sum()),
                             'lm':float(np.abs(m).mean()), 'gap':float(ranking[-1]-ranking[-2])}
            for k in errors: errors[k] = max(errors[k],abs(reconstructed[k]-item[k]))
        if max(errors.values())>1e-6: raise ValueError('NUMERIC_RECONSTRUCTION_MISMATCH')
        best = result['best']; selected_cell = result['cell']
        feasible = [r for r in values if r['ls']<cfg['alpha'] and r['lm']<cfg['beta']]
        geometry = bound_json(record['prepared_record']['geometry']); iy, ix = native_index(geometry)
        selected = None
        if best is not None:
            m = np.asarray(flat(best['mask']), dtype=np.float32); order = np.argsort(-m, kind='stable')
            selected = {'epoch':best['epoch'], 'full_mask':m.reshape(7,7).tolist(),
                'sum':float(m.sum()), 'mean':float(m.mean()), 'minimum':float(m.min()), 'maximum':float(m.max()),
                'coarse_count_ge_0_5':int((m>=.5).sum()), 'coarse_count_ge_0_8':int((m>=.8).sum()),
                'strict_positive_coarse_count':int((m>0).sum()),
                'top_five': [patch_description(int(c),m[c],iy,ix) for c in order[:5]],
                'logits':best['logits'], 'baseline_logits':result['baseline_logits'],
                'ls':best['ls'],'lm':best['lm'],'gap':best['gap'],
                'meaning':'all-logit consistency of full continuous Mask; peak-alone fidelity UNMEASURED'}
            selected['top_five'][0]['evidence_role']='selected_top1_candidate'
            for cell in selected['top_five'][1:]:cell['evidence_role']='descriptive_saved_M_cell_only'
        prepared = record['prepared_record']
        input_sha = prepared['arrays']['image']['array_sha256']
        if input_sha != prepared['prepared_contract']['input_sha256']:
            raise ValueError('SAVED_PREPARED_SCALAR_SHA_CONTRADICTION')
        payload = {'schema':'E2_VERIFIED_STAGE1_REUSE_V4', 'case_index':index,
            'verification':'FULL_TRACE_CPF_AND_SAME_STEP_MASK_VERIFIED',
            'core_sha256':src[core_path], 'branch_semantics':semantic,
            'input_binding':{'input_sha256':input_sha,
                'valid_sha256':prepared['arrays']['valid_mask']['array_sha256'],
                'model_sha256':prepared_delivery['checkpoint_sha256'],
                'preprocessing_sha256':prepared['preprocess_sha256'], 'model_adapter_sha256':src[adapter_path]},
            'grid':7,'stage':1,'observed_iterations':10000,'optimizer_updates':10000,
            'feasible_count':result['feasible_count'],'baseline_logits':result['baseline_logits'],'best':best,
            'source_refs':{'readiness':ref(ready_path), 'proposal':ready['proposal'],
                'prepared_delivery':ready['prepared_delivery'], 'old_trace':record['epochs'],
                'new_trace':ref(runner/f'case-{index}-new-epochs.jsonl'), 'result':ref(result_path),
                'geometry':prepared['geometry']},
            'numeric_reconstruction_max_abs_error':errors,
            'adapter_sha_semantics':'whole frozen first_real_e1_e2.py source including DifferentiablePreparedModel',
            'reuse_policy':'terminal selection import only; not cross-config optimizer restoration; real authority still required'}
        payload_path = output/f'case-{index}-stage1-reuse.json'
        payload_path.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n')
        cases.append({'case_index':index, 'status':result['status'], 'cpf_feasible_count':len(feasible),
            'selected':selected, 'numeric_reconstruction_max_abs_error':errors,
            'trajectory_all':trajectory(values,selected_cell), 'trajectory_feasible':trajectory(feasible,selected_cell),
            'trajectory_last100':trajectory(values[-100:],selected_cell),
            'selected_cell_comparison':{'selected_epoch':None if best is None else best['epoch'],
                'selected_cell':selected_cell,'last_epoch':values[-1]['epoch'],
                'last_cell':int(np.asarray(flat(values[-1]['mask']),dtype=np.float32).argmax())},
            'reuse':{'status':'VERIFIED_TERMINAL_SELECTION_METADATA', 'payload':ref(payload_path),
                'canonical_payload_sha256':digest(payload), 'real_dispatch':'NOT_AUTHORIZED'},
            'prior_audit':audited})
    analysis = {'schema':'P1_SAVED_MASK_ANALYSIS_V4', 'reader':ref(__file__),
        'mode':'SAVED_RESULT_METADATA_ONLY', 'new_model_calls':{'forward':0,'backward':0,'extra_autograd':0},
        'raw_CT_GT_weights_or_prepared_arrays_loaded':False,
        'descriptor_policy':'stable top-five ranks; >=.5 and >=.8 counts fixed before read; never candidate/GT reselection',
        'cases':cases, 'meaning':'trajectory coordinate stability measured from saved M; full-M consistency, peak-only importance and GT coverage distinct'}
    (output/'analysis.json').write_text(json.dumps(analysis,indent=2,allow_nan=False)+'\n')
    return analysis


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--control',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=analyze(args.control.absolute(),args.output.absolute())
    print(json.dumps({'analysis':ref(args.output/'analysis.json'), 'cases':[
        {'case_index':c['case_index'],'status':c['status'], 'feasible_count':c['cpf_feasible_count'],
         'all_switches':c['trajectory_all']['adjacent_observation_switches'],
         'feasible_switches':c['trajectory_feasible']['adjacent_observation_switches'],
         'payload_sha256':c['reuse']['canonical_payload_sha256']} for c in result['cases']]},indent=2))
