"""R92 worker entry under the EXISTING admitted child guard, never a scheduler.

LOC providers reuse ENC loaders/hooks and INT supervision/IO. The SHA-locked provider: open_guard() must use existing
ChildGuard.from_environment(), load_bundle(request, meter) does approved loading.
A request/proposal alone can only run --check. Missing provider blocks execution.
"""
import argparse
import hashlib
import importlib.util
import importlib.metadata
import sys
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def locked(ref):
    path=Path(ref['path'])
    if not path.is_absolute() or path.is_symlink() or sha(path)!=ref['sha256']:
        raise ValueError('EXACT_ABSOLUTE_REFERENCE_REQUIRED')
    return json.loads(path.read_bytes())


def check_request(reference):
    q=locked(reference)
    if q['schema']!='R92_LOC_EXECUTION_PREPARATION_V1' or q['retry']!=0:
        raise ValueError('R92_REQUEST_SCOPE_REQUIRED')
    for ref in q['source_lock']+q['runtime_lock']:
        if sha(ref['path'])!=ref['sha256']:raise ValueError('SOURCE_OR_RUNTIME_DRIFT')
    if q['stage'] not in ('BAG_COMPARE','FOURGRID'):raise ValueError('STAGE')
    config=locked(q['scientific_config'])
    if q['limits']!=config['limits'][q['stage']]:raise ValueError('FIXED_BUDGET_REQUIRED')
    if q['provider'] not in q['source_lock']:raise ValueError('PROVIDER_NOT_IN_CLOSURE')
    return q


def run_admitted(reference, provider):
    """Provider is part of the exact future approved source closure, not authority.

    Parent must validate fresh approval/dispatch BEFORE spawning this worker.
    Existing guard checks admitted job identity, deadlines and durable F/B caps.
    No catch-and-retry; failures preserve counts through existing completion.
    """
    q=check_request(reference)
    if q['execution_readiness']!='FULLY_BOUND_PENDING_APPROVAL' or not q.get('provider'):
        raise ValueError('NOT_READY_MISSING_PROVIDER_OR_INPUT_BINDING')
    guard=provider.open_guard(q) # existing admitted child environment or rejection
    lim=q['limits']
    if (guard.spec.job_id!=q['job_id'] or guard.spec.task_key!=q['task_key']
            or guard.spec.max_forward!=lim['forward'] or guard.spec.max_backward!=lim['backward']
            or guard.spec.timeout_seconds!=lim['seconds'] or guard.spec.device!='cpu'):
        raise ValueError('NEW_EXACT_EXISTING_GUARD_REQUIRED')
    from .conditional_bag_r92 import Meter,Limit
    class GuardedMeter(Meter):
        def call(self,kind,fn,samples=0):
            def guarded():
                if kind=='forward':guard.before_forward()
                elif kind=='backward':guard.before_backward()
                else:guard.check()
                return fn()
            return super().call(kind,guarded,samples)
    m=GuardedMeter(lim['forward'],lim['backward'],lim['updates'],lim['encoder_samples'],
        lim['seconds'],check=guard.check)
    m.started=guard.started # includes imports/loading, never resets scientific clock
    guard.begin_case(q['job_id'])
    terminal_status='FAILED';reason='ENTRY_FAILED';bundle={}
    try:
        if sys.version.split()[0]!=q['runtime']['python_version']:raise ValueError('PYTHON_RUNTIME_DRIFT')
        if Path(sys.executable).resolve()!=Path(q['runtime']['executable']).resolve():raise ValueError('PYTHON_EXECUTABLE_DRIFT')
        for name,version in q['runtime']['packages'].items():
            if importlib.metadata.version(name)!=version:raise ValueError('PACKAGE_RUNTIME_DRIFT')
        import torch
        torch.set_num_threads(1)
        if torch.get_num_interop_threads()!=1:torch.set_num_interop_threads(1)
        bundle=provider.load_bundle(q,m)
        if q['stage']=='BAG_COMPARE':
            from .bag_compare_r92 import run_compare
            result=run_compare(bundle,m,generated=q.get('evidence_scope')=='GENERATED_ONLY')
        else:
            from .fourgrid_r92 import run_fourgrid
            result=run_fourgrid(**bundle,request=q,meter=m)
        if any(m.returned[k]!=q['limits'][k] for k in ('forward','backward','updates')) or m.returned['samples']!=q['limits']['encoder_samples']:
            raise ValueError('NORMAL_BRANCH_ACTUAL_COUNT_MISMATCH')
        if q['stage']=='BAG_COMPARE' and q['limits'].get('head_aggregations',47)!=result['adapter']['bag_aggregations']:
            raise ValueError('BAG_AGGREGATION_COUNT_MISMATCH')
        result['request_file_sha256']=reference['sha256']
        # Provider uses already bound cumulative output limiter, including failure.
        provider.write_result(q,result)
        terminal_status='SUCCESS';reason=None
        return result
    except BaseException as exc:
        reason=type(exc).__name__
        if isinstance(exc,Limit):terminal_status='PARTIAL_BUDGET'
        try:provider.write_result(q,dict(status=terminal_status,error_type=reason,meter=m.report(),partial_audit=bundle.get('audit',{})))
        except Exception:pass # durable supervisor remains authoritative if output fails
        raise
    finally:
        guard.end_case()
        guard.complete(terminal_status,reason=reason,
            actual_forward=m.returned['forward'] if m.returned['forward']==m.reserved['forward'] else None,
            actual_backward=m.returned['backward'] if m.returned['backward']==m.reserved['backward'] else None)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--request',required=True);parser.add_argument('--sha',required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();ref=dict(path=args.request,sha256=args.sha);q=check_request(ref)
    if not args.execute:
        print(json.dumps(dict(status='CHECK_ONLY_NO_EXECUTE',stage=q['stage'],
            readiness=q['execution_readiness'],missing=q['missing_bindings'],limits=q['limits']),sort_keys=True));return
    if q['execution_readiness']!='FULLY_BOUND_PENDING_APPROVAL' or not q.get('provider'):
        raise ValueError('NOT_READY_MISSING_PROVIDER_OR_INPUT_BINDING')
    p=q['provider']
    if sha(p['path'])!=p['sha256']:raise ValueError('PROVIDER_SOURCE_DRIFT')
    spec=importlib.util.spec_from_file_location('_r92_bound_provider',p['path']);provider=importlib.util.module_from_spec(spec);spec.loader.exec_module(provider)
    run_admitted(ref,provider)


if __name__=='__main__':main()
