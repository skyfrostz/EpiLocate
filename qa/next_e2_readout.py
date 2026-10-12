#!/usr/bin/env python3
"""E2-R metadata check by default; one existing supervised child only on dispatch."""
import argparse
import copy
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qa.next_selected_fidelity import bound
from qa.next_selected_fidelity_parent import load_supervisor, CPU_ENVIRONMENT, PYTHON

REQUEST_SHA = '1d2611e8371a3d8074441f53e2832fdc46f4f38b5011a58ffb22f37ae9b3ae52'
INDEX_SHA = '12e808bcf23f80571886fa0e8c68efa88a11fb833a51db002ab1820d20fc1a6d'
TASK = 'EPI-NEXT-E2-R-CASE3-CPU-20261013-V5-INT-1'
JOB = 'e2-r-case3-20261013-v5-int-1'
COMPUTE = dict(device='CPU', forward=18, planned_forward=14, adapter_check_forward=2,
               readout_forward=12, unallocated_forward=4, backward=0, updates=0,
               seconds=120, output_bytes=67108864, retry=0)


def spec_for(value):
    return dict(job_id=value['job_id'], task_key=value['task_key'], device='cpu', owner='INTEGRATION',
        max_forward=18, max_backward=0, timeout_seconds=120, per_case_seconds=120,
        telemetry_startup_seconds=15, telemetry_max_gap_seconds=.25,
        request_grace_seconds=.25, term_grace_seconds=.75, recovery_seconds=2)


def command(binding_ref, dispatch_ref=None, *, child=False, execute=False):
    argv = [PYTHON, str(Path(__file__).resolve()), '--binding', binding_ref['path'],
            '--binding-sha', binding_ref['sha256']]
    if dispatch_ref:
        argv += ['--dispatch', dispatch_ref['path'], '--dispatch-sha', dispatch_ref['sha256']]
    if child: argv += ['--child']
    if execute: argv += ['--execute']
    return argv


def check_binding(reference, *, supervisor_loader=load_supervisor, child=False):
    value = bound(reference)
    if (value['schema'] != 'EPI_NEXT_E2_R_EXECUTION_BINDING_V1'
            or value['task_key'] != TASK or value['job_id'] != JOB or value['compute'] != COMPUTE
            or value['readout_request']['sha256'] != REQUEST_SHA
            or value['supervisor_index']['sha256'] != INDEX_SHA
            or value['environment'] != CPU_ENVIRONMENT
            or value['supervision_spec'] != spec_for(value)
            or value['output_root'] != str(ROOT / '.local/phase2' / JOB)
            or value['supervision_root'] != str(ROOT / '.local/phase2' / (JOB + '-supervision'))):
        raise ValueError('EXACT_E2_R_BINDING_REQUIRED')
    request = bound(value['readout_request'])
    if request['cost'] != dict(maximum_forward=18, planned_new_forward=14,
        adapter_check_forward=2, new_readout_forward=12, historical_objects_reused=4,
        unallocated_forward=4, backward=0, optimizer_updates=0, extra_autograd=0,
        retry=0, restore=0, audit_replay=0):
        raise ValueError('E2_R_COST_DRIFT')
    lock = bound(value['existing_e2_binding']['loc_dependency_lock'])
    if (lock['module_sha256'] != request['source_binding']['module_sha256']
            or lock['core_sha256'] != request['source_binding']['core_sha256']):
        raise ValueError('E2_R_LOC_CLOSURE_DRIFT')
    loc = Path(value['existing_e2_binding']['localization_root']).parent
    for relative, expected in lock['module_sha256'].items():
        if hashlib.sha256((loc / relative).read_bytes()).hexdigest() != expected:
            raise ValueError('LOC_SOURCE_DRIFT')
    for path, expected in value['source_sha256'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('INT_SOURCE_DRIFT')
    if str(Path(__file__).resolve()) not in value['source_sha256']:
        raise ValueError('ENTRY_SOURCE_NOT_BOUND')
    # Legacy loader's metadata references only. No prepared arrays/reuse/weights read.
    old = bound(value['existing_e2_binding']['scientific_request'])
    if (old['core_config'] != request['core_config'] or old['data_bindings'] != request['data_bindings']
            or value['saved_fidelity']['sha256'] != request['saved_fidelity']['file_sha256']):
        raise ValueError('ORIGINAL_LOADER_OR_SAVED_BINDING_DRIFT')
    if value['loader_provenance']['sha256'] != 'cb5468820ab76aa0de5736ef1a6bac7ea630dc438743afe7c9428274ab48dc73':
        raise ValueError('ORIGINAL_LOADER_PROVENANCE_REQUIRED')
    baseline = bound(value['loader_provenance'])
    expected = copy.deepcopy(baseline['existing_e2_binding'])
    expected['job_id'] = JOB
    expected['loc_dependency_lock'] = value['existing_e2_binding']['loc_dependency_lock']
    q = expected['application_request']
    q['algorithm_version'] = 'E2_R_READOUT_V5'
    q['model'].update(model_id='epi_next_resnet18_e2_r_v5', protocol_id='EPI_NEXT_E2_R_READOUT_V5')
    q['task'].update(definition_id=request['target_contract']['model_binding']['task_version'], target_class=1)
    q['budget'].update(forward=18)
    if value['existing_e2_binding'] != expected:
        raise ValueError('EXACT_ORIGINAL_CASE3_LOADER_REQUIRED')
    required = set(baseline['source_sha256']) | {
        str(ROOT/'qa/next_selected_fidelity_parent.py'), str(Path(__file__).resolve()),
        str(ROOT/'epilocate_next/e2_readout_launch.py'), str(ROOT/'qa/e2_readout_output.py'),
        str(ROOT/'research/next-hospital-20261014/epi_next/wave1_supervisor.py'),
        '/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-localization/research/next-hospital-20261014/epi_next/p1_storage_v4.py'}
    if set(value['source_sha256']) != required:
        raise ValueError('INCOMPLETE_INT_SOURCE_CLOSURE')
    if value['preserved_mvp_binding']['sha256'] != 'b03d88d251eb658d285d66462f550f4d2c392798c930c13bf7dd4e0ce1c0d1e4':
        raise ValueError('ORIGINAL_MVP_BINDING_REQUIRED')
    preserved = bound(value['preserved_mvp_binding'])
    if len(preserved['source_sha256']) != 66 or any(hashlib.sha256(Path(p).read_bytes()).hexdigest()!=s
            for p,s in preserved['source_sha256'].items()):
        raise ValueError('MVP66_SOURCE_DRIFT')
    index = bound(value['supervisor_index'])
    modules = supervisor_loader(index)  # shared verified dependencies; no queue calls
    modules['wave1_supervisor'].SupervisionSpec(**value['supervision_spec'])
    if (not child and (Path(value['output_root']).exists() or Path(value['supervision_root']).exists())):
        raise ValueError('EXISTING_OUTPUT_RECONCILE_NO_RETRY')
    if value['io_lock_source'] != dict(path=str(ROOT/'research/next-hospital-20261014/epi_next/wave1_supervisor.py'),
        sha256=value['source_sha256'][str(ROOT/'research/next-hospital-20261014/epi_next/wave1_supervisor.py')]):
        raise ValueError('EXACT_EXISTING_IO_LOCK_SOURCE_REQUIRED')
    if value['output_policy'] != dict(total_retained_cap=67108864,total_cumulative_written_cap=67108864,
        ledger_write_charge_each=512,reporting_reserve=8388608,
        stdout_stderr_cap_each=1048576,roots=['science','supervision_including_parent_child_logs','exact_owned_slot']):
        raise ValueError('CUMULATIVE_OUTPUT_POLICY_REQUIRED')
    return value, index, modules


def check_dispatch(reference, value, dispatch_ref, *, executing=False):
    dispatch = bound(dispatch_ref)
    if (dispatch['schema'] != 'EPI_NEXT_E2_R_DISPATCH_V1'
            or dispatch['status'] != 'READY_FOR_CHIEF_DISPATCH'
            or dispatch['binding'] != reference or dispatch['task_key'] != TASK
            or dispatch['job_id'] != JOB or dispatch['compute'] != COMPUTE
            or dispatch['supervision_spec'] != value['supervision_spec']):
        raise ValueError('NEW_EXACT_E2_R_DISPATCH_REQUIRED')
    owner = bound(dispatch['owner_receipt'])
    request = bound(owner['request'])
    if owner['status'] != 'EXPLICIT_ITEMIZED_APPROVAL' or 'E2-R' not in owner['approved_item_ids']:
        raise ValueError('E2_R_ITEMIZED_APPROVAL_REQUIRED')
    items = [i for i in request['items'] if i['id'] == 'E2-R']
    expected = dict(binding=reference, limits=COMPUTE, task_key=TASK, job_id=JOB,
                    output_root=value['output_root'])
    if len(items) != 1 or any(items[0][k] != v for k, v in expected.items()):
        raise ValueError('E2_R_APPROVAL_SCOPE_DRIFT')
    admission = bound(dispatch['new_admission_decision'])
    if (admission['status'] != 'APPROVED_ADMINISTRATIVE_RECOVERY'
            or admission['queue_root'] != value['queue_root']
            or TASK not in admission['scope']['allowed_next_task_keys']
            or admission['scope']['basis']['e2_r_itemized_owner']['digest'] != dispatch['owner_receipt']['sha256']
            or admission['scope']['basis']['e2_r_itemized_request']['digest'] != owner['request']['sha256']):
        raise ValueError('NEW_TASK_SAME_RECOVERED_QUEUE_ADMISSION_REQUIRED')
    window = dispatch['execution_window']
    if window['status'] != 'CHIEF_SLOT_GRANTED' or not window['slot_id']:
        raise ValueError('CHIEF_SAME_SLOT_REQUIRED')
    if executing:
        start, end = [datetime.fromisoformat(window[k]) for k in ('not_before_utc','not_after_utc')]
        now = datetime.now(timezone.utc)
        if start.utcoffset() is None or end.utcoffset() is None or not start <= now or now + timedelta(seconds=123) > end:
            raise ValueError('OUTSIDE_CHIEF_EXECUTION_WINDOW')
        if 'EPI_NEXT_SUPERVISOR_DIR' in os.environ:
            raise ValueError('NO_NESTED_PARENT_SUPERVISION')
    return dispatch


def run(reference, dispatch_ref=None, *, execute=False, supervisor_loader=load_supervisor, supervision_adapter=None):
    value, index, modules = check_binding(reference, supervisor_loader=supervisor_loader)
    if not execute:
        return dict(status='ENGINEERING_READY_OWNER_ADMISSION_SLOT_PENDING', model_calls=0,
                    queue_observations=0, arrays_weights_read=False, torch_imported='torch' in sys.modules)
    if dispatch_ref is None: raise ValueError('NEW_E2_R_DISPATCH_REQUIRED')
    dispatch = check_dispatch(reference, value, dispatch_ref, executing=True)
    os.environ.update(value['environment'])
    from qa.e2_readout_output import bounded_supervisor
    with (supervision_adapter or bounded_supervisor)(value,modules) as (budget,monitor):
        result=modules['wave1_supervisor'].run_supervised(
            modules['wave1_supervisor'].SupervisionSpec(**value['supervision_spec']),
            command(reference, dispatch_ref, child=True), value['supervision_root'],
            index['dependency_root'], index['dependency_sha256'], _monitor=monitor,
            recovery_decision_path=dispatch['new_admission_decision']['path'],
            recovery_decision_sha=dispatch['new_admission_decision']['sha256'])
        if budget.errors:result=dict(result,status='FAILED',output_guard_errors=budget.errors)
        print(json.dumps({k:result.get(k) for k in ('status','reason','slot_completed')},sort_keys=True))
    return result


def run_child(reference, dispatch_ref):
    value, _, modules = check_binding(reference, child=True)
    check_dispatch(reference, value, dispatch_ref)
    directory = Path(value['supervision_root']) / JOB
    if (os.environ.get('EPI_NEXT_SUPERVISOR_DIR') != str(directory)
            or json.loads((directory/'spec.json').read_bytes()) != value['supervision_spec']
            or json.loads((directory/'ADMITTED').read_bytes())['pid'] != os.getpid()
            or any(os.environ.get(k) != v for k,v in value['environment'].items())):
        raise ValueError('EXACT_ADMITTED_CHILD_REQUIRED')
    from qa.e2_readout_output import bounded_child
    with bounded_child(value,modules) as budget:
        return admitted_child(reference,value,modules,directory,budget)


def admitted_child(reference,value,modules,directory,budget):
    guard=modules['wave1_supervisor'].ChildGuard.from_environment()
    terminal = False
    known_forward=known_backward=None
    try:
        guard.check()
        import torch
        torch.set_num_threads(1); torch.set_num_interop_threads(1)
        actual = dict(intra_op=torch.get_num_threads(), inter_op=torch.get_num_interop_threads())
        if actual != dict(intra_op=1, inter_op=1): raise ValueError('CPU1_REQUIRED')
        modules['coordinator_writer'].write_new(directory/'runtime-threads.json',
            json.dumps(dict(actual_threads=actual, model_calls=0, clock_reset=False),sort_keys=True).encode())
        from epilocate_next.e2_readout_launch import run_existing_readout
        value['_binding_sha256'] = reference['sha256']
        value['_output_reserved_by_parent']=True
        result = run_existing_readout(value, guard,output_budget=budget)
        terminal = True
        budget.reporting=True
        guard.complete(result['status'], actual_forward=result['new_cost']['forward'], actual_backward=0)
        return 0 if result['status'] == 'SUCCESS' else 2
    except BaseException as exc:
        known_forward=getattr(exc,'actual_forward',None);known_backward=getattr(exc,'actual_backward',None)
        raise
    finally:
        if not terminal:
            budget.reporting=True
            guard.complete('FAILED',reason='E2_R_ENTRY_FAILED',actual_forward=known_forward,actual_backward=known_backward)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding',type=Path,required=True); parser.add_argument('--binding-sha',required=True)
    parser.add_argument('--dispatch',type=Path); parser.add_argument('--dispatch-sha')
    parser.add_argument('--execute',action='store_true'); parser.add_argument('--child',action='store_true')
    args=parser.parse_args()
    if bool(args.dispatch) != bool(args.dispatch_sha): parser.error('DISPATCH_PATH_SHA_PAIR_REQUIRED')
    reference=dict(path=str(args.binding),sha256=args.binding_sha)
    dispatch=dict(path=str(args.dispatch),sha256=args.dispatch_sha) if args.dispatch else None
    if args.child:
        if args.execute or dispatch is None: parser.error('EXACT_SUPERVISED_CHILD_ONLY')
        return run_child(reference,dispatch)
    try:result=run(reference,dispatch,execute=args.execute)
    except BaseException:
        if args.execute:return 2  # execution errors belong to bounded parent logs, not a second traceback
        raise
    if not args.execute:
        print(json.dumps({k:result.get(k) for k in ('status','model_calls','queue_observations','arrays_weights_read','torch_imported','slot_completed')},sort_keys=True))
    return 0 if not args.execute or result['status']=='SUCCESS' else 2


if __name__=='__main__': raise SystemExit(main())
