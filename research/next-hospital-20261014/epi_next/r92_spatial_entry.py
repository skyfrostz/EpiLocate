"""One admitted CPU pass over the original20 validation bags; no implicit calls.

Default validates binding only. Real mode requires exact new owner/dispatch plus
the original shared supervisor. Frozen R91 source files are imported unchanged.
"""
import argparse
import ast
import gc
import importlib.metadata
import io
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from . import ctfm_research_pipeline_v4 as p
from . import resnet18_mil_v1 as r18
from .r92_r18_contributions import bound_json, bound_bytes, read_features, canonical, digest, effective_head, close, policy, POLICY_PATH, POLICY_SHA
from .r92_bag_cam import capture_pre_gap, signed_cam, map_centers_to_native, validate_backbone


TASK_KEY = 'R18-R92-DEV20-K8-TRUE-SPATIAL-CPU-ONCE'
JOB_ID = 'r18-r92-spatial-dev20-01'
LIMITS = dict(forward=20, backward=0, updates=0, seconds=3600, per_case=120,
              rss=5*1024**3, assets=64*1024**2, delivery=512*1024**2)
_ACTIVE_GUARD = None


def source_closure():
    """Static closure including lazy imports and frozen model/config sources."""
    repo=Path(__file__).resolve().parents[3]
    pending=[Path(__file__).resolve()]; found=set()
    while pending:
        path=pending.pop()
        if path in found: continue
        found.add(path)
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node,ast.ImportFrom) and node.level==1:
                for name in ([node.module] if node.module else [a.name for a in node.names]):
                    child=path.parent/(name.split('.')[0]+'.py')
                    if child.is_file():pending.append(child)
    found.update({r18.CONFIG_PATH.resolve(),repo/'src/model.py',repo/'src/data_checks.py',POLICY_PATH.resolve()})
    initializer=Path(__file__).parent/'__init__.py'
    if initializer.is_file():found.add(initializer)
    return sorted(found)


def validate_request(q):
    if (q['schema']!='R92_R18_SPATIAL_REQUEST_V1' or q['phase']!='spatial' or q['limits']!=LIMITS
            or q['retry'] is not False or q['warmup']!=0 or q['extra_adapter_forward']!=0
            or q['spec']['task_key']!=TASK_KEY or q['spec']['job_id']!=JOB_ID
            or q['spec']['owner']!='ENCODER' or q['spec']['device']!='cpu'
            or q['spec']['max_forward']!=20 or q['spec']['max_backward']!=0
            or q['spec']['timeout_seconds']!=3600 or q['spec']['per_case_seconds']!=120):
        raise p.Blocked('EXACT_R92_SPATIAL_SPEC_REQUIRED')
    if q['numerical_policy']!={'path':str(POLICY_PATH),'sha256':POLICY_SHA}:
        raise p.Blocked('PRELOCKED_NUMERICAL_POLICY_REQUIRED')
    if {p.safe_path(x['path']) for x in q['sources']}!=set(source_closure()):
        raise p.Blocked('FULL_R92_SOURCE_CLOSURE_REQUIRED')
    repo=Path(__file__).resolve().parents[3]
    for ref in q['sources']:
        if p.file_sha(ref['path'])!=ref['sha256']:raise p.Blocked('SOURCE_DRIFT')
        blob=subprocess.check_output(['git','-C',str(repo),'show',q['source_commit']+':'+str(Path(ref['path']).relative_to(repo))],timeout=5)
        if p.digest(blob)!=ref['sha256']:raise p.Blocked('COMMITTED_SOURCE_REQUIRED')
    for ref in q['runtime']['references']:
        if p.file_sha(ref['path'])!=ref['sha256']:raise p.Blocked('RUNTIME_REFERENCE_DRIFT')
    frozen=bound_json(q['frozen_reference'])
    if q['data_manifest']!=frozen['consumer'] or q['checkpoint']['sha256']!=r18.IMAGENET_SHA:
        raise p.Blocked('FROZEN_INPUT_REFERENCE_REQUIRED')
    if q['runtime']['packages']!={'torch':'2.14.0','torchvision':'0.29.0','numpy':'2.4.6','pandas':'3.0.6','PyYAML':'6.0.3'} or q['runtime']['python_version']!='3.11.15':
        raise p.Blocked('PINNED_RUNTIME_REQUIRED')
    root=p.safe_path(q['delivery_root'])
    for name in ('output','supervisor_output'):
        if root not in p.safe_path(q[name]).parents:raise p.Blocked('OUTPUT_BOUNDARY')
    return q


def open_guard(q):
    """Also available to LOC provider; never creates a queue or dispatch."""
    global _ACTIVE_GUARD
    shared=p.load_shared(q)
    if _ACTIVE_GUARD is None:
        _ACTIVE_GUARD=shared.ChildGuard.from_environment()
    guard=_ACTIVE_GUARD
    if 'spec' in q and vars(guard.spec)!=vars(shared.SupervisionSpec(**q['spec'])):
        raise p.Blocked('EXACT_ADMITTED_CHILD_SPEC_REQUIRED')
    return guard


def scalar_gap_wrapper(backbone):
    """LOC: variable-N post-resize scalar FP32 → original normalize → GAP.

    No detach/no_grad is introduced. Callers count every invocation. Exposes
    actual layer4 tensor as last_spatial; no calls during construction.
    """
    import torch
    validate_backbone(backbone)
    class ScalarGap(torch.nn.Module):
        def __init__(self):
            super().__init__(); self.backbone=backbone; self.last_spatial=None
        def forward(self, scalar):
            if scalar.ndim!=4 or scalar.shape[1:]!=(1,224,224) or scalar.shape[0]<1:
                raise ValueError('N scalar224 required')
            images=r18.normalize_windowed(scalar)
            def hook(_module,_args,output): self.last_spatial=output
            handle=self.backbone.layer4.register_forward_hook(hook)
            try:return self.backbone(images)
            finally:handle.remove()
    return ScalarGap().eval()


def load_bundle(q, meter):
    """LOC provider contract; admitted child only, zero hidden model forwards.

    q.encoder_inputs binds frozen_reference and one original record_id. The
    provider must bind the supervisor and all source/runtime references itself.
    Native HU / exact ImageNet weight bytes are accessed only in this function
    after the existing ChildGuard is successfully opened.
    """
    open_guard(q).check(); meter.check()
    import torch
    inputs=q['encoder_inputs']; frozen=bound_json(inputs['frozen_reference'])
    records=p.validate_records(bound_json(frozen['consumer']))
    row=next(x for x in records if x['record_id']==inputs['record_id'])
    cache=bound_json(frozen['cache']); cached=next(x for x in cache['rows'] if x['record_id']==row['record_id'])
    pred=next(x for x in bound_json(frozen['evaluation'])['predictions'] if x['record_id']==row['record_id'])
    checkpoint=bound_json(frozen['head'])
    if (checkpoint['cache_receipt']!=frozen['cache'] or checkpoint['context']!=cache['context']
            or checkpoint['state']!=frozen['head_state'] or row['split']!='val_classification'
            or any(row[k]!=cached[k] or pred[k]!=row[k] for k in ('record_id','source_group_id','split','source_diagnosis'))):
        raise p.Blocked('BUNDLE_HEAD_CACHE_BINDING')
    scalar=[]
    def observe(name,value):
        if name=='post_resize_pre_normalize': scalar.append(value)
    images,geo=r18.prepare_bag(row,meter,observe=observe)
    recovered,_=r18.recover_resize_roundoff(scalar[0])
    if digest(canonical(dict(shape=list(images.shape),dtype='float32'))+images.numpy().tobytes())!=cached['identity']['input_sha']:
        raise p.Blocked('BUNDLE_ORIGINAL_INPUT_MISMATCH')
    if geo!=bound_json(cached['geometry']):raise p.Blocked('BUNDLE_GEOMETRY_MISMATCH')
    state={k:np.load(io.BytesIO(bound_bytes(ref)),allow_pickle=False) for k,ref in checkpoint['state'].items()}
    if any(v.dtype!=np.float32 for v in state.values()):raise p.Blocked('BUNDLE_HEAD_FP32_REQUIRED')
    effective_head(state)
    backbone=r18.build_backbone(cache['context']['checkpoint_reference'])
    return dict(images=recovered, cached_gap=torch.from_numpy(read_features(cached).copy()),
                members=[f"{row['record_id']}:native_Z={z}" for z in geo['indices_Z']],
                native_indices_Z=list(geo['indices_Z']), record_id=row['record_id'],encoder=scalar_gap_wrapper(backbone),
                mean=torch.from_numpy(state['mean']).double(),scale=torch.from_numpy(state['scale']).double(),
                weight=torch.from_numpy(state['linear.weight']).double(),bias=torch.from_numpy(state['linear.bias']).double(),
                saved_bag_logits=torch.tensor([pred['raw_logits']],dtype=torch.float64),
                valid=torch.ones((224,224),dtype=torch.bool),
                valid_semantics='FULL_MODEL224_NO_PADDING; no lung/lesion ROI', geometry=geo,
                counts=dict(hidden_backbone_forward=0,hidden_head_forward=0))


def extract(q, guard):
    import torch
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    meter=p.Meter('cache',guard,q['delivery_root'])
    meter.limits=dict(forward=20,backward=0,updates=0,seconds=3600,per_case=120,rss=LIMITS['rss'])
    for name,version in q['runtime']['packages'].items():
        if importlib.metadata.version(name)!=version:raise p.Blocked('RUNTIME_VERSION')
    if sys.version.split()[0]!=q['runtime']['python_version']:raise p.Blocked('PYTHON_VERSION')
    frozen=bound_json(q['frozen_reference'])
    records=p.validate_records(p.bound_json(q['data_manifest'],meter.check))
    projection=[{k:r[k] for k in ('record_id','source_group_id','source_diagnosis','task_label','split')} for r in records]
    if digest(canonical(projection))!=q['fixed_group_projection_sha256']:raise p.Blocked('FIXED60_PROJECTION')
    selected=[r for r in records if r['split']=='val_classification']
    if [r['record_id'] for r in selected]!=q['selected_record_ids'] or len(selected)!=20:
        raise p.Blocked('ORIGINAL_DEV20_ORDER_REQUIRED')
    cache=bound_json(frozen['cache']); head=bound_json(frozen['head']); evaluation=bound_json(frozen['evaluation'])
    if (head['context']!=cache['context'] or evaluation['context']!=cache['context']
            or head['cache_receipt']!=frozen['cache'] or evaluation['cache_receipt']!=frozen['cache']
            or evaluation['head_checkpoint']!=frozen['head'] or head['state']!=frozen['head_state']):
        raise p.Blocked('R91_FROZEN_CLOSURE')
    state={k:np.load(io.BytesIO(bound_bytes(ref)),allow_pickle=False) for k,ref in head['state'].items()}
    if any(v.dtype!=np.float32 for v in state.values()):raise p.Blocked('FROZEN_HEAD_FP32_REQUIRED')
    effective_head(state)
    store=p.PrivateArtifacts(p.safe_path(q['output']),LIMITS['assets'])
    # Counter exists before loading, so exceptions never silently claim success.
    backbone=None; rows=[]
    try:
        backbone=r18.build_backbone(q['checkpoint']); meter.check()
        for i,row in enumerate(selected):
            meter.begin(row['record_id'])
            cached=next(x for x in cache['rows'] if x['record_id']==row['record_id'])
            pred=next(x for x in evaluation['predictions'] if x['record_id']==row['record_id'])
            images,geo=r18.prepare_bag(row,meter)
            if geo!=bound_json(cached['geometry']) or digest(canonical(dict(shape=list(images.shape),dtype='float32'))+images.numpy().tobytes())!=cached['identity']['input_sha']:
                raise p.Blocked('ORIGINAL_INPUT_GEOMETRY_REQUIRED')
            saved=read_features(cached)
            meter.before('forward')
            gap,spatial,hook=capture_pre_gap(backbone,images)
            meter.returned_forward+=1;meter.check()
            gap=gap.numpy(); spatial=spatial.numpy()
            if not close(gap,saved,policy()['future_spatial_fp32_gap']):raise p.Blocked('SAVED_GAP_MISMATCH')
            cam=signed_cam(spatial,gap,state)
            if not all(cam[k] for k in ('gap_tolerance_pass','logit_tolerance_pass','pooling_envelope_pass','logit_envelope_pass')):
                raise p.Blocked('SPATIAL_NUMERICAL_GATE')
            if not close(cam['cam_reconstructed_logits'],pred['raw_logits'],policy()['future_spatial_logits']):
                raise p.Blocked('SAVED_LOGIT_MISMATCH')
            maps=map_centers_to_native(geo)
            assets={}
            for name,array in [('layer4',spatial),('gap',gap),('signed_class',cam['signed_class_maps']),('signed_margin',cam['signed_margin_maps']),('positive_margin_display',cam['display_positive_margin_maps']),('native_centers',maps['native_ZYX_centers']),('lps_centers',maps['LPS_centers'])]:
                filename=f'case_{i:02d}_{name}.npy'; sha=store.array(filename,array)
                assets[name]=dict(path=str(store.directory/filename),sha256=sha)
            rows.append(dict(record_id=row['record_id'],source_group_id=row['source_group_id'],geometry=geo,
                geometry_reference=cached['geometry'],head_reference=frozen['head'],model_context=cache['context'],hook=hook,assets=assets,
                effective_bias=cam['effective_bias'].tolist(),saved_logits=pred['raw_logits'],cam_logits=cam['cam_reconstructed_logits'].tolist(),
                original_pool_logits=cam['original_pool_fp64_head_logits'].tolist(),
                gap_saved_max_error=float(np.max(np.abs(gap.astype(np.float64)-saved.astype(np.float64)))),
                pooling_max_error=float(cam['pooling_gap_absolute_errors'].max()),cam_logit_errors=cam['cam_logit_absolute_errors'].tolist(),
                logit_roundoff_envelope=cam['logit_roundoff_envelope'].tolist(),residual_correction=False))
            meter.end();del images,gap,spatial,cam,maps;gc.collect();meter.check()
        result=dict(schema='R92_TRUE_SPATIAL_RECEIPT_V1',status='PASS',rows=rows,calls=meter.report(),
            actual_slice_positions=meter.returned_forward*8,numpy_bag_affine_evaluations=len(rows),
            head_training=0,expert_labels='UNKNOWN',clinical_validity='NOT ESTABLISHED',frozen_reference=q['frozen_reference'])
        store.json('spatial-receipt.json',result)
        guard.complete('SUCCESS',device_recovered=True,actual_forward=meter.returned_forward,actual_backward=0)
        return result
    except BaseException as exc:
        actual=meter.returned_forward if meter.forward==meter.returned_forward else None
        failure=dict(status='FAIL',reason=type(exc).__name__,detail=str(exc),completed_rows=rows,calls=meter.report(),actual_forward=actual)
        try:store.json('failure-receipt.json',failure)
        finally:guard.complete('FAILED',reason=type(exc).__name__,device_recovered=False,actual_forward=actual,actual_backward=0)
        raise
    finally:
        backbone=None;gc.collect()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('request','request-sha'):parser.add_argument('--'+name,required=True)
    for name in ('approval','approval-sha','dispatch','dispatch-sha','admission','admission-sha'):parser.add_argument('--'+name)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--child',action='store_true')
    args=parser.parse_args(argv)
    q=validate_request(p.bound_json(dict(path=args.request,sha256=args.request_sha)))
    if not args.execute:
        print(json.dumps(dict(status='PASS_BINDING_ONLY',real_execution='NOT RUN',torch_imported='torch' in sys.modules)))
        return 0
    if not all((args.approval,args.approval_sha,args.dispatch,args.dispatch_sha,args.admission,args.admission_sha)):
        raise p.Blocked('NEW_APPROVAL_ADMISSION_AND_EXCLUSIVE_DISPATCH_REQUIRED')
    for path,sha,schema,status in ((args.approval,args.approval_sha,'R92_R18_SPATIAL_APPROVAL_V1','APPROVED_NEW_SCOPE'),(args.dispatch,args.dispatch_sha,'R92_R18_SPATIAL_DISPATCH_V1','EXCLUSIVE_SLOT_ASSIGNED')):
        receipt=p.bound_json(dict(path=path,sha256=sha))
        if any(receipt.get(k)!=v for k,v in dict(schema=schema,status=status,request_sha256=args.request_sha,phase='spatial',owner='ENCODER',task_key=TASK_KEY,retry=False).items()):
            raise p.Blocked('EXACT_NEW_AUTHORITY_REQUIRED')
        if path==args.dispatch and receipt['approval_sha256']!=args.approval_sha:raise p.Blocked('DISPATCH_APPROVAL_BINDING')
    admission=p.bound_json(dict(path=args.admission,sha256=args.admission_sha))
    if any(admission.get(k)!=v for k,v in dict(schema='R92_SPATIAL_ADMINISTRATIVE_BINDING_V1',request_sha256=args.request_sha,
            approval_sha256=args.approval_sha,task_key=TASK_KEY,owner='ENCODER').items()):
        raise p.Blocked('EXACT_INDEPENDENT_ADMISSION_BINDING_REQUIRED')
    recovery=admission['recovery_decision']
    p.bound_json(recovery)
    shared=p.load_shared(q)
    if args.child:
        extract(q,open_guard(q));return 0
    child=[sys.executable,'-m','epi_next.r92_spatial_entry','--request',args.request,'--request-sha',args.request_sha,'--approval',args.approval,'--approval-sha',args.approval_sha,'--dispatch',args.dispatch,'--dispatch-sha',args.dispatch_sha,'--admission',args.admission,'--admission-sha',args.admission_sha,'--execute','--child']
    receipt=shared.run_supervised(shared.SupervisionSpec(**q['spec']),child,q['supervisor_output'],q['supervisor']['dependency_root'],p.SHARED_SHA,recovery_decision_path=recovery['path'],recovery_decision_sha=recovery['sha256'])
    return 0 if receipt['status']=='SUCCESS' and receipt['slot_completed'] else 2


if __name__=='__main__':
    raise SystemExit(main())
