"""Read saved P1 observations only; no model imports, forwards or gradients."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

ALPHA=.005
BETA=.08


def ref(path):
    path=Path(path)
    return {'path':str(path.absolute()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'bytes':path.stat().st_size}


def rows(path):
    raw=Path(path).read_bytes()
    complete=raw.splitlines(keepends=True)
    tail=0
    if complete and not complete[-1].endswith(b'\n'):
        tail=len(complete.pop())
    return [json.loads(line) for line in complete],tail


def flat(value):
    if isinstance(value,list):return [v for x in value for v in flat(x)]
    return [value]


def trend(values):
    if not values:return None
    early=values[:min(100,len(values))];late=values[-min(100,len(values)):]
    return {'window':min(100,len(values)),'first_epoch':values[0]['epoch'],'last_epoch':values[-1]['epoch'],
        'first100_mean':{k:statistics.mean(r[k] for r in early) for k in ('ls','lm','gap')},
        'last100_mean':{k:statistics.mean(r[k] for r in late) for k in ('ls','lm','gap')},
        'last100_endpoint_lm_change':late[-1]['lm']-late[0]['lm']}


def case_review(record,runner):
    index=record['case_index'];old_path=Path(record['epochs']['path'])
    if ref(old_path)['sha256']!=record['epochs']['sha256']:raise ValueError('OLD_PREFIX_SHA_DRIFT')
    old,_=rows(old_path)
    converted=[{'epoch':r['step'],'ls':r['similarity'],'lm':r['sparsity'],'gap':r['peak_gap'],
        'mask':r['mask_before'],'logits':r['logits']} for r in old]
    trace=runner/f'case-{index}-new-epochs.jsonl'
    new,tail=rows(trace) if trace.exists() else ([],0)
    if [r['epoch'] for r in converted]!=list(range(1,1001)):raise ValueError('LEGACY_PREFIX_GAP')
    if [r['epoch'] for r in new]!=list(range(1001,1001+len(new))):raise ValueError('NEW_TRACE_GAP')
    if any(r['feasible']!=(r['ls']<ALPHA and r['lm']<BETA) for r in new):
        raise ValueError('SAVED_JOINT_CONDITION_MISMATCH')
    values=converted+new
    feasible=[r for r in values if r['ls']<ALPHA and r['lm']<BETA]
    best=max(feasible,key=lambda r:(r['gap'],-r['epoch'])) if feasible else None
    result_path=runner/f'case-{index}-result.json'
    result=json.loads(result_path.read_text()) if result_path.exists() else None
    if result is not None:
        if result['observed_iterations']!=len(values) or result['feasible_count']!=len(feasible):
            raise ValueError('RESULT_DENOMINATOR_MISMATCH')
        binding=result['trace'];trace_ref=ref(trace)
        if (binding['sha256']!=trace_ref['sha256'] or binding['bytes']!=trace_ref['bytes']
                or binding['rows']!=len(new) or binding['last_epoch']!=new[-1]['epoch']):
            raise ValueError('DURABLE_TRACE_BINDING_MISMATCH')
        stored=result['best']
        if (stored is None)!=(best is None):raise ValueError('CPF_EMPTY_SET_MISMATCH')
        if best is not None:
            if any(stored[k]!=best[k] for k in ('epoch','ls','lm','gap','logits')) or flat(stored['mask'])!=flat(best['mask']):
                raise ValueError('FULL_SET_SAME_STEP_CPF_MISMATCH')
    selected=None
    if best is not None:
        mask=flat(best['mask']);cell=max(range(len(mask)),key=lambda k:mask[k]);row,col=divmod(cell,7)
        selected={k:best[k] for k in ('epoch','ls','lm','gap','logits')}
        selected.update(cell_flat=cell,coarse_row=row,coarse_column=col,
            model_patch_yx_half_open=[row*32,(row+1)*32,col*32,(col+1)*32],mask=best['mask'],
            selection_covers_full_planned_iterations=False if result is None else result['best_is_full_plan'])
        if result is not None and result['cell']!=cell:raise ValueError('PATCH_CELL_MISMATCH')
    min_lm=min(values,key=lambda r:r['lm'])
    summary={'case_index':index,'status':'NOT_STARTED' if not new and result is None else 'RUNNING' if result is None else result['status'],
        'legacy_observations':len(old),'new_durable_observations':len(new),'observed_denominator':len(values),
        'new_completed_updates':None if result is None else result['completed_steps']-1000,
        'planned_total_observations':10000,'unobserved_total':10000-len(values),
        'conditions':{'ls_pass':sum(r['ls']<ALPHA for r in values),'lm_pass':sum(r['lm']<BETA for r in values),
            'joint_pass':len(feasible),'gap_positive_diagnostic_only':sum(r['gap']>0 for r in values)},
        'first_joint_epoch':None if not feasible else feasible[0]['epoch'],
        'minimum_lm_paired':{k:min_lm[k] for k in ('epoch','ls','lm','gap')},
        'last_observation':{k:values[-1][k] for k in ('epoch','ls','lm','gap')},
        'selected':selected,'new_trajectory_trend':trend(new),'incomplete_line_bytes':tail,
        'psmi':'NOT_APPLICABLE_SINGLE_SCALE','result':None if result is None else ref(result_path)}
    if trace.exists():summary['trace']=ref(trace)
    if result is not None:
        summary.update(error=result['error'],restores=result['time']['restores'],segments=result['time']['segments'],
            best_is_full_plan=result['best_is_full_plan'])
    native=runner/f'case-{index}-single-scale-CPF-native.npz'
    if native.exists():
        # Read saved candidate arrays, never original CT or GT.
        import numpy as np
        with np.load(native,allow_pickle=False) as saved:
            reliable=saved['reliable'];yy,xx=np.nonzero(reliable)
            summary['native']={**ref(native),'shape':list(reliable.shape),'reliable_pixels':int(reliable.sum()),
                'yx_bbox_half_open':None if not len(yy) else [int(yy.min()),int(yy.max()+1),int(xx.min()),int(xx.max()+1)],
                'native_slice_index':int(saved['native_slice_index']),
                'candidate_score_values':np.unique(saved['scores'][reliable]).tolist(),
                'score_semantics':'CPF coarse Mask peak gap; not lesion probability'}
            if bool(len(yy))!=(best is not None):raise ValueError('NATIVE_RELIABLE_EMPTY_MISMATCH')
            prepared=record['prepared_record'];geometry_ref=prepared['geometry']
            if ref(geometry_ref['path'])['sha256']!=geometry_ref['sha256']:
                raise ValueError('GEOMETRY_SHA_DRIFT')
            geometry=json.loads(Path(geometry_ref['path']).read_text())
            if (str(saved['SOPInstanceUID'])!=prepared['source_sop_uid']
                    or str(saved['native_case_manifest_sha256'])!=prepared['native_manifest_sha256']
                    or int(saved['native_slice_index'])!=prepared['native_slice_index_zero_based']):
                raise ValueError('NATIVE_CASE_BINDING_MISMATCH')
            inverse=np.asarray(geometry['native_to_model_zyx']);forward=np.asarray(geometry['model_to_native_zyx'])
            if not np.allclose(inverse@forward,np.eye(4),atol=1e-9,rtol=0):raise ValueError('INVERSE_LEDGER_MISMATCH')
            rr,cc=np.indices(reliable.shape)
            pts=np.stack((np.full_like(rr,int(saved['native_slice_index'])),rr,cc),axis=-1)
            mapped=pts@inverse[:3,:3].T+inverse[:3,3]
            if not np.allclose(mapped[...,0],0,atol=1e-9,rtol=0):raise ValueError('WRONG_NATIVE_SLICE')
            iy=np.floor(mapped[...,1]+.5).astype(int);ix=np.floor(mapped[...,2]+.5).astype(int)
            if iy.min()<0 or ix.min()<0 or iy.max()>223 or ix.max()>223:raise ValueError('OUTSIDE_FOV')
            expected=np.zeros_like(reliable)
            if selected is not None:
                y0,y1,x0,x1=selected['model_patch_yx_half_open']
                expected=(iy>=y0)&(iy<y1)&(ix>=x0)&(ix<x1)
                world=np.asarray(geometry['model_to_lps'])
                points=np.asarray([[0,y0,x0,1],[0,y0,x1-1,1],[0,y1-1,x0,1],[0,y1-1,x1-1,1]])
                summary['native']['model_patch_corner_centres_lps_mm']=(points@world.T)[:,:3].tolist()
            if not np.array_equal(reliable,expected):raise ValueError('NATIVE_PATCH_RASTER_MISMATCH')
            if best is not None and not np.all(saved['scores'][reliable]==np.float32(best['gap'])):
                raise ValueError('NATIVE_SCORE_MISMATCH')
            summary['native']['inverse_raster_check']='PASS_FROM_BOUND_GEOMETRY_LEDGER'
            summary['native']['case_binding_check']='PASS_EXACT_SOP_SLICE_NATIVE_MANIFEST'
    return summary


def review(control):
    ready_path=control/'final-readiness-v8.json';ready=json.loads(ready_path.read_text())
    runner=Path(ready['execution_output']);job=Path(ready['supervision_output_root'])/ready['supervisor_job_id']
    result={'schema':'P1_REAL_SAVED_REVIEW_V8','mode':'OFFLINE_READ_ONLY_NO_NEW_MODEL_CALL',
        'readiness':ref(ready_path),'dispatch':ref(control/'chief-dispatch-v8.json'),
        'alpha':ALPHA,'beta':BETA,'selection':'max gap over all strict feasible iterations; earliest epoch tie',
        'cases':[case_review(r,runner) for r in ready['records']]}
    for name,path in {'algorithm_counters':runner/'algorithm-counters.json','supervisor_counters':job/'counters.json',
            'run_delivery':runner/'run_delivery.json','supervisor_receipt':job/'supervisor-receipt.json'}.items():
        if path.exists():result[name]={'reference':ref(path),'value':json.loads(path.read_text())}
    if 'supervisor_receipt' in result:
        for case in result['cases']:
            if case['status']=='RUNNING':case['status']='NO_TERMINAL_CASE_RESULT_AFTER_SUPERVISOR_EXIT'
        result['terminal_denominators']={'planned_cases':3,
            'cases_with_terminal_result':sum(c['result'] is not None for c in result['cases']),
            'cases_without_terminal_result':sum(c['result'] is None for c in result['cases']),
            'cases_with_selected_CPF':sum(c['selected'] is not None for c in result['cases']),
            'cases_with_empty_CPF':sum(c['result'] is not None and c['selected'] is None for c in result['cases']),
            'planned_new_updates':27000,
            'new_durable_observations':sum(c['new_durable_observations'] for c in result['cases']),
            'legacy_plus_new_observations':sum(c['observed_denominator'] for c in result['cases'])}
    result['new_calls_by_this_reader']={'forward':0,'backward':0,'extra_autograd':0}
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--control',type=Path,required=True)
    args=p.parse_args();print(json.dumps(review(args.control.absolute()),indent=2))
