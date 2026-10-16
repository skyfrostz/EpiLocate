#!/usr/bin/env python3
"""One bound 5F child command for the existing supervisor; default metadata only."""
import argparse
import hashlib
import json
from pathlib import Path


def bound(reference):
    path=Path(reference['path']);raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=reference['sha256']:raise ValueError('BOUND_REFERENCE_DRIFT')
    return json.loads(raw)


def validate_bindings(value,binding_sha,dispatch_reference):
    if value['schema']!='EPI_NEXT_SELECTED_FIDELITY_APPLICATION_BINDING_V2' or value['compute']!=dict(device='CPU',forward=5,backward=0,updates=0,seconds=120,output_bytes=67108864):raise ValueError('EXACT_FIVE_FORWARD_BINDING_REQUIRED')
    # Immutable execution binding contains no approval references. The external
    # dispatch binds its hash, never the reverse, so the chain is constructible.
    if any(k in value for k in ('owner_receipt','new_admission_decision','chief_dispatch')):raise ValueError('APPROVAL_MUST_BE_EXTERNAL')
    if dispatch_reference is None:raise ValueError('NEW_OWNER_ADMISSION_DISPATCH_NOT_BOUND')
    dispatch=bound(dispatch_reference)
    if dispatch['binding_sha256']!=binding_sha or dispatch['task_key']!=value['task_key'] or dispatch['source_sha256']!=value['source_sha256']:raise ValueError('CHIEF_EXACT_COMMAND_BINDING_REQUIRED')
    if dispatch.get('status')!='READY_FOR_CHIEF_DISPATCH' or any(dispatch.get(k) is None for k in ('owner_receipt','new_admission_decision')):raise ValueError('NEW_OWNER_ADMISSION_DISPATCH_NOT_BOUND')
    # Receipts are chief supplied. This command neither signs nor creates one.
    bound(dispatch['owner_receipt']);bound(dispatch['new_admission_decision'])
    if str(Path(__file__).resolve()) not in value['source_sha256']:raise ValueError('LAUNCHER_SOURCE_BINDING_REQUIRED')
    for name,expected in value['source_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=expected:raise ValueError('LAUNCH_SOURCE_DRIFT')
    if Path(value['output_root']).exists():raise ValueError('EXISTING_OUTPUT_RECONCILE_NO_RETRY')
    return dispatch


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding',type=Path,required=True);parser.add_argument('--binding-sha',required=True)
    parser.add_argument('--dispatch',type=Path);parser.add_argument('--dispatch-sha')
    parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    value=bound(dict(path=str(args.binding),sha256=args.binding_sha))
    if not args.execute:
        print(json.dumps(dict(status=value['status'],task_key=value['task_key'],compute=value['compute'],model_calls=0,queue_observations=0)));return 0
    if bool(args.dispatch)!=bool(args.dispatch_sha):raise ValueError('DISPATCH_PATH_SHA_PAIR_REQUIRED')
    dispatch_reference=dict(path=str(args.dispatch),sha256=args.dispatch_sha) if args.dispatch else None
    dispatch=validate_bindings(value,args.binding_sha,dispatch_reference)
    # Reuse the exact existing bundle importer/ChildGuard, no new lock or queue.
    from hospital_mvp_protected import supervisor
    modules=supervisor(bound(value['supervisor_index']))
    decision=bound(dispatch['new_admission_decision'])
    modules['execution_lock'].validate_administrative_recovery(Path(decision['queue_root']),value['task_key'],dispatch['new_admission_decision']['path'],dispatch['new_admission_decision']['sha256'])
    guard=modules['wave1_supervisor'].ChildGuard.from_environment()
    terminal_started=False
    try:
        if guard.spec.task_key!=value['task_key'] or guard.spec.max_forward!=5 or guard.spec.max_backward!=0 or guard.spec.timeout_seconds!=120:raise ValueError('EXISTING_SUPERVISOR_SCOPE_MISMATCH')
        from epilocate_next.e2_launch import ExistingE2Binding,run_existing_selected_fidelity
        fields=dict(value['existing_e2_binding']);fields['localization_root']=Path(fields['localization_root']);fields['integration_bridge_source']=Path(fields['integration_bridge_source'])
        result=run_existing_selected_fidelity(ExistingE2Binding(**fields),guard,Path(value['output_root']))
        status=result['status'];terminal_started=True
        guard.complete(status,actual_forward=result['cost']['forward'],actual_backward=result['cost']['backward'])
        return 0 if status=='SUCCESS' else 1
    except BaseException:
        if not terminal_started:
            guard.complete('FAILED',reason='SELECTED_FIDELITY_ENTRY_FAILED',actual_forward=None,actual_backward=None)
        raise


if __name__=='__main__':raise SystemExit(main())
