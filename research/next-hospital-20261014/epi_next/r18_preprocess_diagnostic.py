"""One bound source preprocessing only; callable under existing admitted supervision.

Default CLI only validates metadata/source/runtime. Real I/O requires new exact authority and original supervision.
"""
import argparse
import json
from pathlib import Path
from . import ctfm_research_pipeline_v4 as p
from . import resnet18_mil_v1 as m


def validate(request):
    if request['schema']!='R18_PREPROCESS_DIAGNOSTIC_V1' or request['status']!='PROPOSED_NOT_APPROVED':
        raise p.Blocked('DIAGNOSTIC_REQUEST_REQUIRED')
    if request['limits']!=dict(model_calls=0,weight_loads=0,forward=0,backward=0,updates=0,cpu_threads=1,seconds=120,rss_pre_stop_bytes=5368709120,rss_sample_stop_bytes=6442450944,structured_output_bytes=4194304,retry=0):
        raise p.Blocked('NO_MODEL_OR_WEIGHTS')
    if any(request['spec'][k]!=v for k,v in dict(owner='ENCODER',device='cpu',max_forward=0,max_backward=0,timeout_seconds=120,per_case_seconds=120).items()):raise p.Blocked('DIAGNOSTIC_ZERO_MODEL_SPEC')
    for ref in request['sources']+request['runtime']['references']:
        if p.file_sha(ref['path'])!=ref['sha256']:raise p.Blocked('DIAGNOSTIC_SOURCE_RUNTIME_DRIFT')
    records=p.bound_json(request['data_manifest'])
    if records[0]!=request['record'] or m.sample_indices(records[0]['tensor_artifact']['shape'][0])!=request['indices_Z']:
        raise p.Blocked('ORIGINAL_FIRST_RECORD_AND_INDICES_REQUIRED')
    return request


def diagnose(row,meter):
    import numpy as np
    import torch
    stages=[]
    def observe(stage,value):
        if isinstance(value,dict):summary=value
        else:
            x=torch.from_numpy(value) if isinstance(value,np.ndarray) else value
            d=m.windowed_diagnostic(x)
            summary={k:d[k] for k in ('python_type','shape','dtype','device','stride','contiguous','finite','nonfinite_count','finite_min','finite_max')}
        stages.append(dict(stage=stage,observed=summary))
    try:
        images,geometry=m.prepare_bag(row,meter,observe=observe)
        result=dict(status='PREPROCESS_PASS',geometry=geometry)
        del images
    except p.Blocked as error:
        if not hasattr(error,'diagnostic') and str(error) not in ('NONFINITE_SELECTED_HU','BOUND_COMPLETE_HU_GEOMETRY_LABEL_QA_REQUIRED','NATIVE_Z_AXIAL_GEOMETRY_REQUIRED'):
            raise
        result=dict(status='PREPROCESS_REJECTED',diagnostic=getattr(error,'diagnostic',None),reason=str(error))
    return dict(result,stages=stages,weights_loaded=0,model_calls=0,cache_written=0)


def main(argv=None):
    import sys
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('request','request-sha'):parser.add_argument('--'+name,required=True)
    for name in ('approval','approval-sha','dispatch','dispatch-sha'):parser.add_argument('--'+name)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--child',action='store_true')
    args=parser.parse_args(argv)
    request=validate(p.bound_json(dict(path=args.request,sha256=args.request_sha)))
    import importlib.metadata
    if sys.version.split()[0]!=request['runtime']['python_version']:raise p.Blocked('DIAGNOSTIC_PYTHON_DRIFT')
    for name,version in request['runtime']['packages'].items():
        if importlib.metadata.version(name)!=version:raise p.Blocked('DIAGNOSTIC_RUNTIME_VERSION')
    if not args.execute:
        print(json.dumps(dict(status='CHECK_ONLY',arrays_read=0,weights_loaded=0,model_calls=0)));return 0
    if not all((args.approval,args.approval_sha,args.dispatch,args.dispatch_sha)):
        raise p.Blocked('EXACT_DIAGNOSTIC_AUTHORITY_REQUIRED')
    approval=p.bound_json(dict(path=args.approval,sha256=args.approval_sha))
    dispatch=p.bound_json(dict(path=args.dispatch,sha256=args.dispatch_sha))
    for value,status in ((approval,'APPROVED_NEW_SCOPE'),(dispatch,'EXCLUSIVE_SLOT_ASSIGNED')):
        if (value.get('status')!=status or value.get('request_sha256')!=args.request_sha
                or value.get('task_key')!=request['spec']['task_key'] or value.get('retry') is not False
                or value.get('phase')!='preprocess_diagnostic' or value.get('owner')!='ENCODER'):
            raise p.Blocked('EXACT_DIAGNOSTIC_AUTHORITY_REQUIRED')
    if dispatch.get('approval_sha256')!=args.approval_sha:raise p.Blocked('DIAGNOSTIC_DISPATCH_APPROVAL')
    shared=p.load_shared(request)
    if not args.child:
        if Path(request['output']).exists() or Path(request['supervisor_output']).exists():
            raise p.Blocked('DIAGNOSTIC_SINGLE_ATTEMPT_NO_RETRY')
        child=[sys.executable,'-m','epi_next.r18_preprocess_diagnostic',
            '--request',args.request,'--request-sha',args.request_sha,
            '--approval',args.approval,'--approval-sha',args.approval_sha,
            '--dispatch',args.dispatch,'--dispatch-sha',args.dispatch_sha,'--execute','--child']
        recovery=dispatch['administrative_recovery']
        receipt=shared.run_supervised(shared.SupervisionSpec(**request['spec']),child,request['supervisor_output'],
            request['supervisor']['dependency_root'],p.SHARED_SHA,
            recovery_decision_path=recovery['path'],recovery_decision_sha=recovery['sha256'])
        return 0 if receipt['status']=='SUCCESS' and receipt['slot_completed'] else 2
    guard=shared.ChildGuard.from_environment();completed=False
    try:
        if vars(guard.spec)!=vars(shared.SupervisionSpec(**request['spec'])):raise p.Blocked('EXACT_DIAGNOSTIC_SPEC')
        import torch
        torch.set_num_threads(1);torch.set_num_interop_threads(1)
        meter=p.Meter('cache',guard)
        meter.limits=dict(meter.limits,forward=0,backward=0,updates=0,seconds=120,assets=4*1024**2)
        meter.check()
        result=diagnose(request['record'],meter)
        meter.check()
        store=p.PrivateArtifacts(p.safe_path(request['output']),4*1024**2)
        store.json('diagnostic.json',result)
        guard.complete('SUCCESS',actual_forward=0,actual_backward=0);completed=True
        return 0
    finally:
        if not completed:guard.complete('FAILED',reason='PREPROCESS_DIAGNOSTIC_FAILED',actual_forward=0,actual_backward=0)

if __name__=='__main__':raise SystemExit(main())
