"""One separately approved ridge pilot on saved GAP features; never imports an encoder."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from . import ctfm_research_pipeline_v4 as p
from .ctfm_research_math_v4 import binary_metrics

CONFIG = dict(schema='CTFM_RIDGE_PILOT_R79_V1',lambda_L2=1.0,objective='mean squared error to +/-1 plus lambda*sum(weight^2); intercept unpenalized',standardization='train40 FP64 population std floor1e-6',train=40,validation=20,fit_calls=1,head_forward=2,backward=0,optimizer_updates=0,seconds=30,rss_bytes=1024**3,assets_bytes=16*1024**2,total_run_bytes=32*1024**2,seed=None,selection='fixed lambda1 before new results; no tuning/CV/validation selection',threshold=0.0,tie='Normal',device='cpu',threads=1,warmup=0,retry=False)


def fit_ridge(train,labels):
    x=np.asarray(train,dtype=np.float64);y=np.asarray(labels)
    if x.ndim!=2 or y.shape!=(len(x),) or not np.isfinite(x).all() or not np.isin(y,[0,1]).all() or set(y.tolist())!={0,1}:
        raise p.Blocked('RIDGE_TRAIN_DATA_INVALID')
    mean=x.mean(0);scale=np.maximum(x.std(0),1e-6);z=(x-mean)/scale
    target=2*y.astype(np.float64)-1;bias=float(target.mean())
    # Fixed lambda1 on mean objective -> n*lambda in dual normal equations.
    dual=np.linalg.solve(z@z.T+len(x)*CONFIG['lambda_L2']*np.eye(len(x)),target-bias)
    weight=z.T@dual
    if not np.isfinite(weight).all():raise p.Blocked('RIDGE_NONFINITE_SOLUTION')
    return dict(weight=weight,bias=bias,mean=mean,scale=scale)


def score(state,x):
    return ((np.asarray(x,dtype=np.float64)-state['mean'])/state['scale'])@state['weight']+state['bias']


def validate_request(r):
    if r.get('schema')!='CTFM_RIDGE_RESOLVED_REQUEST_R79_V1' or r.get('config')!=CONFIG or r.get('retry') is not False:
        raise p.Blocked('EXACT_NEW_RIDGE_REQUEST_REQUIRED')
    expected=dict(owner='ENCODER',device='cpu',max_forward=2,max_backward=0,timeout_seconds=30,per_case_seconds=None,task_key='CTFM-RIDGE-R79-SAVED60-FIT1-EVAL2-CPU',job_id='ctfm-ridge-r79-01')
    if any(r['spec'].get(k)!=v for k,v in expected.items()):raise p.Blocked('RIDGE_FIXED_BUDGET')
    if r['data_manifest']['sha256']!='0000000000000000000000000000000000000000000000000000000000000000':raise p.Blocked('RIDGE_FIXED_DATA')
    required=set(p.source_closure())|{Path(__file__).resolve()}
    if {p.safe_path(x['path']) for x in r['sources']}!=required:raise p.Blocked('RIDGE_SOURCE_CLOSURE')
    repo=Path(__file__).resolve().parents[3]
    for x in r['sources']:
        blob=subprocess.check_output(['git','-C',str(repo),'show',r['source_commit']+':'+str(Path(x['path']).relative_to(repo))],timeout=5)
        if p.digest(blob)!=x['sha256'] or p.file_sha(x['path'])!=x['sha256']:raise p.Blocked('RIDGE_SOURCE_DRIFT')
    for x in r['runtime']['references']:
        if p.file_sha(x['path'])!=x['sha256']:raise p.Blocked('RIDGE_RUNTIME_DRIFT')
    if r['runtime']['numpy_version']!=np.__version__:raise p.Blocked('RIDGE_NUMPY_VERSION')
    if p.safe_path(r['delivery_root']) not in p.safe_path(r['output']).parents or p.safe_path(r['delivery_root']) not in p.safe_path(r['supervisor_output']).parents:raise p.Blocked('RIDGE_OUTPUT_BOUNDARY')
    return r


class RidgeMeter(p.Meter):
    def __init__(self,guard,delivery):
        super().__init__('evaluate',guard,delivery);self.fit_attempts=0;self.fit_returned=0;self.forward_inflight=False
    def check(self):
        super().check()
        if self.delivery_root:
            view=type('DeliveryView',(),{'directory':self.delivery_root})()
            if sum(v[3] for v in p.PrivateArtifacts._disk_snapshot(view).values())>=CONFIG['total_run_bytes']:
                raise p.Blocked('RIDGE_TOTAL_RUN_ASSET_LIMIT')


def run_saved(r,guard,meter=None):
    # Only the published metadata and saved GAP arrays; native CT and encoder cache never read.
    meter=meter or RidgeMeter(guard,r['delivery_root'])
    rows=p.validate_records(p.bound_json(r['data_manifest'],guard.check))
    cached=p.bound_json(r['cache_receipt'],guard.check)
    if cached['status']!='PASS' or cached['data_manifest_sha256']!=r['data_manifest']['sha256'] or len(cached['rows'])!=60:raise p.Blocked('RIDGE_CACHE_BINDING')
    gaps=[]
    for row,old in zip(rows,cached['rows']):
        if any(row[k]!=old[k] for k in ('record_id','source_group_id','source_diagnosis','task_label','split')):raise p.Blocked('RIDGE_CACHE_ORDER')
        ref=old['gap']
        if p.file_sha(ref['path'],guard.check,8192)!=ref['sha256']:raise p.Blocked('RIDGE_GAP_SHA')
        x=np.load(ref['path'],allow_pickle=False)
        if x.shape!=(1,512) or x.dtype!=np.float64 or not np.isfinite(x).all():raise p.Blocked('RIDGE_GAP_SHAPE')
        gaps.append(x[0])
    x=np.stack(gaps);y=np.array([v['task_label'] for v in rows]);train=np.array([v['split']=='train_weak' for v in rows])
    store=p.PrivateArtifacts(p.safe_path(r['output']),CONFIG['assets_bytes']);meter.check()
    if meter.fit_attempts:raise p.Blocked('RIDGE_NO_SECOND_FIT')
    meter.fit_attempts=1
    store.json('fit-reservation.json',dict(fit_attempts=1,retry=False,request_config=CONFIG))
    state=fit_ridge(x[train],y[train]);meter.fit_returned=1;meter.check()
    refs={k:dict(path=str(store.directory/(k+'.npy')),sha256=store.array(k+'.npy',np.asarray(v))) for k,v in state.items()}
    store.json('ridge-checkpoint.json',dict(schema='CTFM_RIDGE_CHECKPOINT_R79_V1',config=CONFIG,state=refs,cache_receipt=r['cache_receipt'],data_manifest=r['data_manifest'],source_commit=r['source_commit'],fit_attempts=1,selection='fixed lambda1; not validated or calibrated'))
    results={};predictions=[]
    for split,mask in [('train_weak',train),('val_classification',~train)]:
        meter.before('forward');meter.forward_inflight=True
        margin=score(state,x[mask]);meter.returned_forward+=1;meter.forward_inflight=False;meter.check()
        # Monotone sigmoid for ranking only, not calibrated disease probability.
        probability=1/(1+np.exp(-np.clip(margin,-700,700)))
        results[split]=binary_metrics(y[mask],probability,margin>0)
        for row,m,s in zip([row for row,selected in zip(rows,mask) if selected],margin,probability):
            predictions.append(dict(record_id=row['record_id'],split=split,source_diagnosis=row['source_diagnosis'],task_label=row['task_label'],margin=float(m),raw_logits=[0.,float(m)],ranking_score=float(s),predicted_class=int(m>0),calibration='UNCALIBRATED_RIDGE_MARGIN'))
    store.json('evaluation.json',dict(config=CONFIG,metrics=results,predictions=predictions,calls=meter.report(),head_forward=2,fit_calls=1,backward=0,optimizer_updates=0,medical_encoder_forward=0,validation='development: original val20 observed and used to motivate this pilot, not independent final test',clinical_patient_independence='UNKNOWN',pretraining_overlap='UNKNOWN'))
    return dict(fit_calls=1,forward=2,backward=0,updates=0)


def main(argv=None):
    parser=argparse.ArgumentParser()
    for name in ('request','request-sha'):parser.add_argument('--'+name,required=True)
    for name in ('approval','approval-sha','dispatch','dispatch-sha'):parser.add_argument('--'+name)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--child',action='store_true')
    args=parser.parse_args(argv);guard=meter=None
    try:
        r=validate_request(p.bound_json(dict(path=args.request,sha256=args.request_sha)))
        if not args.execute:return 0
        if not all((args.approval,args.approval_sha,args.dispatch,args.dispatch_sha)):raise p.Blocked('RIDGE_NEW_AUTHORITY_REQUIRED')
        a=p.bound_json(dict(path=args.approval,sha256=args.approval_sha));d=p.bound_json(dict(path=args.dispatch,sha256=args.dispatch_sha))
        for value,schema,status in [(a,'CTFM_RIDGE_APPROVAL_R79_V1','APPROVED_NEW_SCOPE'),(d,'CTFM_RIDGE_DISPATCH_R79_V1','EXCLUSIVE_SLOT_ASSIGNED')]:
            if value.get('schema')!=schema or value.get('status')!=status or value.get('request_sha256')!=args.request_sha or value.get('task_key')!=r['spec']['task_key'] or value.get('retry') is not False:raise p.Blocked('RIDGE_EXACT_AUTHORITY')
        if d.get('approval_sha256')!=args.approval_sha:raise p.Blocked('RIDGE_DISPATCH_BINDING')
        shared=p.load_shared(r)
        if not args.child:
            command=[sys.executable,'-m','epi_next.ctfm_ridge_head_r79',*sys.argv[1:],'--child']
            recovery=r['administrative_recovery']
            result=shared.run_supervised(shared.SupervisionSpec(**r['spec']),command,r['supervisor_output'],r['supervisor']['dependency_root'],p.SHARED_SHA,recovery_decision_path=recovery['path'],recovery_decision_sha=recovery['sha256'])
            return 0 if result['status']=='SUCCESS' and result['slot_completed'] else 2
        guard=shared.ChildGuard.from_environment()
        if vars(guard.spec)!=vars(shared.SupervisionSpec(**r['spec'])):raise p.Blocked('RIDGE_CHILD_SPEC')
        meter=RidgeMeter(guard,r['delivery_root'])
        counts=run_saved(r,guard,meter);guard.complete('SUCCESS',device_recovered=True,actual_forward=counts['forward'],actual_backward=0)
        return 0
    except Exception as exc:
        if guard:
            actual=None if meter is None or meter.forward_inflight else meter.returned_forward
            p.PrivateArtifacts(p.safe_path(r['output']),CONFIG['assets_bytes']).json('failure-counts.json',dict(returned_forward=0 if meter is None else meter.returned_forward,actual_forward=actual,fit_attempts=0 if meter is None else meter.fit_attempts,fit_returned=0 if meter is None else meter.fit_returned))
            guard.complete('FAILED',reason=type(exc).__name__,device_recovered=False,actual_forward=actual,actual_backward=0)
        print(json.dumps(dict(status='BLOCKED' if isinstance(exc,p.Blocked) else 'FAIL',reason=str(exc))))
        return 3

if __name__=='__main__':raise SystemExit(main())
