"""Exact R92 parent/child CLI using original supervisor, queue and cumulative IO.

No new approval writer, queue or retry. Owner/admission/dispatch are independent
SHA-bound external receipts. Default is metadata-only, no queue observations.
"""
import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import sys
from .r92_entry import check_request, locked, run_admitted


def command(reference,owner,admission,dispatch,*,child=False,execute=True):
    q=check_request(reference)
    argv=[q['runtime']['executable'],'-m','epi_next.r92_parent','--request',reference['path'],'--sha',reference['sha256']]
    for name,ref in (('owner',owner),('admission',admission),('dispatch',dispatch)):
        if ref is None:raise ValueError('ALL_THREE_INDEPENDENT_RECEIPTS_REQUIRED')
        argv += ['--'+name,ref['path'],'--'+name+'-sha',ref['sha256']]
    if execute:argv+=['--execute']
    if child:argv+=['--child']
    return argv


def authority(reference,q,owner_ref,admission_ref,dispatch_ref,*,executing=False,child=False,now=None):
    if any(r is None for r in (owner_ref,admission_ref,dispatch_ref)):
        raise ValueError('NEW_OWNER_ADMISSION_DISPATCH_REQUIRED')
    if len({r['path'] for r in (owner_ref,admission_ref,dispatch_ref)})!=3:
        raise ValueError('INDEPENDENT_RECEIPTS_REQUIRED')
    owner,admission,dispatch=(locked(r) for r in (owner_ref,admission_ref,dispatch_ref))
    item_id='R92-LOC-'+q['stage']
    if owner.get('status')!='EXPLICIT_ITEMIZED_APPROVAL' or item_id not in owner.get('approved_item_ids',[]):
        raise ValueError('ITEMIZED_OWNER_APPROVAL_REQUIRED')
    approval_request=locked(owner['request'])
    items=[r for r in approval_request['items'] if r.get('id')==item_id]
    expected=dict(id=item_id,request=reference,task_key=q['task_key'],job_id=q['job_id'],
        limits=q['limits'],supervision_spec=q['spec'],output_root=q['output_root'],supervision_root=q['supervision_root'])
    if len(items)!=1 or any(items[0].get(k)!=v for k,v in expected.items()):
        raise ValueError('ITEMIZED_SCOPE_MISMATCH')
    fields=dict(schema='EPI_NEXT_R92_LOC_DISPATCH_V1',status='READY_FOR_CHIEF_DISPATCH',
        request=reference,task_key=q['task_key'],job_id=q['job_id'],limits=q['limits'],
        supervision_spec=q['spec'],output_root=q['output_root'],supervision_root=q['supervision_root'],
        owner_receipt=owner_ref,new_admission_decision=admission_ref)
    if any(dispatch.get(k)!=v for k,v in fields.items()):raise ValueError('EXACT_NEW_DISPATCH_REQUIRED')
    scope=admission.get('scope',{});basis=scope.get('basis',{})
    if (admission.get('status')!='APPROVED_ADMINISTRATIVE_RECOVERY'
            or admission.get('queue_root')!=q['queue_root']
            or q['task_key'] not in scope.get('allowed_next_task_keys',[])
            or basis.get('r92_loc_itemized_owner',{}).get('digest')!=owner_ref['sha256']
            or basis.get('r92_loc_itemized_request',{}).get('digest')!=owner['request']['sha256']):
        raise ValueError('ORIGINAL_QUEUE_NEW_TASK_ADMISSION_REQUIRED')
    window=dispatch.get('execution_window',{})
    if window.get('status')!='CHIEF_SLOT_GRANTED' or not window.get('slot_id'):
        raise ValueError('NEW_EXCLUSIVE_WINDOW_REQUIRED')
    if executing:
        start,end=(datetime.fromisoformat(window[k]) for k in ('not_before_utc','not_after_utc'))
        now=now or datetime.now(timezone.utc)
        reserve=q['spec']['timeout_seconds']+(0 if child else 3)
        if start.utcoffset() is None or end.utcoffset() is None or not start<=now or now+timedelta(seconds=reserve)>end:
            raise ValueError('OUTSIDE_EXACT_WINDOW')
        if not child and 'EPI_NEXT_SUPERVISOR_DIR' in os.environ:
            raise ValueError('NO_NESTED_SUPERVISION')
    return dispatch


def modules_for(q):
    sys.path.insert(0,q['integration_root'])
    from qa.next_selected_fidelity_parent import load_supervisor
    b=locked(q['old_binding'])
    return load_supervisor(locked(b['supervisor_index']))


def run(reference,owner_ref=None,admission_ref=None,dispatch_ref=None,*,execute=False,child=False,
        loader=modules_for,io_factory=None,now=None):
    q=check_request(reference)
    expected_spec=dict(job_id=q['job_id'],task_key=q['task_key'],device='cpu',owner='LOCALIZATION',
        max_forward=q['limits']['forward'],max_backward=q['limits']['backward'],timeout_seconds=120,per_case_seconds=120,
        telemetry_startup_seconds=15,telemetry_max_gap_seconds=.25,request_grace_seconds=.25,term_grace_seconds=.75,recovery_seconds=2)
    if q.get('parent_entry')!='epi_next.r92_parent' or q['spec']!=expected_spec:
        raise ValueError('COMPLETE_EXACT_PARENT_SPEC_REQUIRED')
    policy=q['output_policy']
    if any(policy[k]!=q[k] for k in ('output_root','supervision_root','queue_root','job_id')):
        raise ValueError('EXACT_OUTPUT_AND_EXISTING_QUEUE_BINDING_REQUIRED')
    if not execute:
        if any(r is not None for r in (owner_ref,admission_ref,dispatch_ref)):
            authority(reference,q,owner_ref,admission_ref,dispatch_ref)
        return dict(status='CHECK_ONLY_NO_EXECUTE',request=reference,model_calls=0,queue_observations=0)
    authority(reference,q,owner_ref,admission_ref,dispatch_ref,executing=True,child=child,now=now)
    if not child and any(Path(q[k]).exists() for k in ('output_root','supervision_root')):
        raise ValueError('EXISTING_OUTPUT_NO_RETRY')
    mods=loader(q)
    if child:
        directory=Path(q['supervision_root'])/q['job_id']
        if (os.environ.get('EPI_NEXT_SUPERVISOR_DIR')!=str(directory)
                or json.loads((directory/'spec.json').read_bytes())!=q['spec']
                or json.loads((directory/'ADMITTED').read_bytes())['pid']!=os.getpid()
                or any(os.environ.get(k)!=v for k,v in q['command_environment'].items())):
            raise ValueError('EXACT_ADMITTED_CHILD_ENVIRONMENT_REQUIRED')
        from qa.e2_readout_output import bounded_child
        from .r92_entry import sha
        import importlib.util
        p=q['provider']
        if sha(p['path'])!=p['sha256']:raise ValueError('PROVIDER_SOURCE_DRIFT')
        spec=importlib.util.spec_from_file_location('_r92_bound_provider',p['path']);provider=importlib.util.module_from_spec(spec);spec.loader.exec_module(provider)
        with bounded_child(q['output_policy'],mods):return run_admitted(reference,provider)
    if io_factory is None:
        from qa.e2_readout_output import bounded_supervisor
        io_factory=bounded_supervisor
    prior={k:os.environ.get(k) for k in q['command_environment']}
    os.environ.update(q['command_environment'])
    try:
        with io_factory(q['output_policy'],mods) as (budget,monitor):
            receipt=mods['wave1_supervisor'].run_supervised(
                mods['wave1_supervisor'].SupervisionSpec(**q['spec']),
                command(reference,owner_ref,admission_ref,dispatch_ref,child=True),
                q['supervision_root'],q['supervisor_dependency_root'],
                q['supervisor_dependency_sha256'],_monitor=monitor,
                recovery_decision_path=admission_ref['path'],recovery_decision_sha=admission_ref['sha256'])
            if receipt.get('status')=='SUCCESS' and (not receipt.get('slot_completed') or receipt.get('runner_actual_counts')!=dict(forward=q['limits']['forward'],backward=q['limits']['backward'])):
                receipt=dict(receipt,status='FAILED',reason='SUCCESS_TERMINAL_COUNTS_OR_SLOT_MISMATCH')
            if budget.errors:receipt=dict(receipt,status='FAILED',output_guard_errors=list(budget.errors))
            return receipt
    finally:
        for k,v in prior.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--sha',required=True)
    for name in ('owner','admission','dispatch'):
        p.add_argument('--'+name);p.add_argument('--'+name+'-sha')
    p.add_argument('--execute',action='store_true');p.add_argument('--child',action='store_true')
    a=p.parse_args()
    def ref(name):
        path=getattr(a,name);digest=getattr(a,name+'_sha')
        if bool(path)!=bool(digest):raise ValueError('PATH_AND_SHA_PAIR_REQUIRED')
        return dict(path=path,sha256=digest) if path else None
    result=run(dict(path=a.request,sha256=a.sha),ref('owner'),ref('admission'),ref('dispatch'),execute=a.execute,child=a.child)
    print(json.dumps({k:result.get(k) for k in ('status','reason','slot_completed','runner_actual_counts')},sort_keys=True))
    return 0 if result['status'] in ('CHECK_ONLY_NO_EXECUTE','SUCCESS') else 2


if __name__=='__main__':raise SystemExit(main())
