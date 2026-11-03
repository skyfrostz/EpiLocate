#!/usr/bin/env python3
"""Audit a 5F dispatch draft; execute once only in a chief-granted time slot.

The immutable v17 child and v12 supervisor remain unchanged. Metadata mode
does not inspect the device queue, arrays, masks or weights, or spawn a child.
"""

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[1]
from datetime import datetime, timezone, timedelta
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qa.next_selected_fidelity import bound, validate_bindings

BINDING_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
OWNER_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
ADMISSION_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
REQUEST_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
INDEX_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
PYTHON = str(_PUBLIC_ROOT / '.venv/bin/python')
CPU_ENVIRONMENT = dict(PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT),
                       OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')


def load_supervisor(index):
    sys.path.insert(0, str(ROOT / 'qa'))
    from hospital_mvp_protected import supervisor
    return supervisor(index)


def spec_for(binding):
    return dict(job_id=binding['job_id'], task_key=binding['task_key'],
                device='cpu', owner='INTEGRATION', max_forward=5, max_backward=0,
                timeout_seconds=120, per_case_seconds=120,
                telemetry_startup_seconds=15, telemetry_max_gap_seconds=.25,
                request_grace_seconds=.25, term_grace_seconds=.75, recovery_seconds=2)


def child_command(binding_ref, dispatch_ref):
    return [PYTHON, str(Path(__file__).resolve()),
            '--dispatch', dispatch_ref['path'], '--dispatch-sha', dispatch_ref['sha256'],
            '--child']


def validate_plan(dispatch_ref, *, execute=False, supervised_child=False, supervisor_loader=load_supervisor):
    value = bound(dispatch_ref)
    if value['schema'] != 'EPI_NEXT_SELECTED_FIDELITY_PARENT_DISPATCH_V1':
        raise ValueError('PARENT_DISPATCH_SCHEMA')
    binding_ref = value['binding']
    if binding_ref['sha256'] != BINDING_SHA or value['binding_sha256'] != BINDING_SHA:
        raise ValueError('IMMUTABLE_V17_BINDING_REQUIRED')
    binding = bound(binding_ref)
    if (value['source_sha256'] != binding['source_sha256']
            or value['task_key'] != binding['task_key']
            or value['job_id'] != binding['job_id']
            or value['compute'] != binding['compute']
            or value['supervision_spec'] != spec_for(binding)
            or value['environment'] != CPU_ENVIRONMENT
            or value['torch_threads'] != dict(intra_op=1, inter_op=1)):
        raise ValueError('EXACT_SCOPE_SPEC_REQUIRED')
    if value['owner_receipt']['sha256'] != OWNER_SHA or value['new_admission_decision']['sha256'] != ADMISSION_SHA:
        raise ValueError('EXACT_NEW_OWNER_ADMISSION_REQUIRED')
    owner = bound(value['owner_receipt'])
    request_ref = owner['request']
    if request_ref['sha256'] != REQUEST_SHA or 'E2-FIDELITY-5F' not in owner['approved_item_ids'] or owner['status'] != 'EXPLICIT_ITEMIZED_APPROVAL':
        raise ValueError('ITEMIZED_5F_APPROVAL_REQUIRED')
    request = bound(request_ref)
    items = [item for item in request['items'] if item['id'] == 'E2-FIDELITY-5F']
    if len(items) != 1:
        raise ValueError('APPROVED_5F_ITEM_REQUIRED')
    item = items[0]
    for key, expected in [('binding', binding_ref), ('limits', binding['compute']),
                          ('task_key', binding['task_key']), ('job_id', binding['job_id']),
                          ('output_root', binding['output_root'])]:
        actual = item[key]
        if key == 'binding':
            actual = {k: actual[k] for k in ('path', 'sha256')}
        if actual != expected:
            raise ValueError('APPROVED_SCIENTIFIC_SCOPE_DRIFT')
    admission = bound(value['new_admission_decision'])
    scope = admission['scope']
    if admission['status'] != 'APPROVED_ADMINISTRATIVE_RECOVERY' or binding['task_key'] not in scope['allowed_next_task_keys']:
        raise ValueError('EXACT_NEW_TASK_ADMISSION_REQUIRED')
    for key, expected in [('v4_itemized_owner', OWNER_SHA), ('v4_itemized_request', REQUEST_SHA)]:
        if scope['basis'][key]['digest'] != expected:
            raise ValueError('ADMISSION_APPROVAL_BASIS_DRIFT')
    if binding['supervisor_index']['sha256'] != INDEX_SHA:
        raise ValueError('FIXED_V12_SUPERVISOR_REQUIRED')
    index = bound(binding['supervisor_index'])
    if value['supervisor_index'] != binding['supervisor_index']:
        raise ValueError('SUPERVISOR_INDEX_DRIFT')
    hashes = dict(binding['source_sha256'])
    parent = str(Path(__file__).resolve())
    if value['parent_source_sha256'].keys() != {parent}:
        raise ValueError('EXACT_PARENT_SOURCE_REQUIRED')
    hashes.update(value['parent_source_sha256'])
    for name, expected in hashes.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError('SOURCE_DRIFT')
    expected_root = ROOT / '.local/phase2' / (binding['job_id'] + '-supervision')
    if value['supervision_root'] != str(expected_root):
        raise ValueError('EXACT_SUPERVISION_ROOT_REQUIRED')
    if Path(binding['output_root']).exists() or (not supervised_child and (expected_root / binding['job_id']).exists()):
        raise ValueError('EXISTING_OUTPUT_RECONCILE_NO_RETRY')
    if value['status'] not in {'DRAFT_WAITING_CHIEF_EXECUTION_SLOT', 'READY_FOR_CHIEF_DISPATCH'}:
        raise ValueError('DISPATCH_STATUS')
    if supervised_child:
        if value['status'] != 'READY_FOR_CHIEF_DISPATCH' or not value.get('execution_window'):
            raise ValueError('WAIT_CHIEF_UNIQUE_EXECUTION_SLOT')
        if os.environ.get('EPI_NEXT_SUPERVISOR_DIR') != str(expected_root / binding['job_id']):
            raise ValueError('EXACT_ADMITTED_CHILD_DIRECTORY_REQUIRED')
    if execute:
        # A science approval does not allocate a time slot. Do not wait/poll.
        window = value.get('execution_window')
        if value['status'] != 'READY_FOR_CHIEF_DISPATCH' or not window or window.get('status') != 'CHIEF_SLOT_GRANTED' or not window.get('slot_id'):
            raise ValueError('WAIT_CHIEF_UNIQUE_EXECUTION_SLOT')
        start = datetime.fromisoformat(window['not_before_utc'])
        end = datetime.fromisoformat(window['not_after_utc'])
        if start.utcoffset() is None or end.utcoffset() is None:
            raise ValueError('AWARE_EXECUTION_WINDOW_REQUIRED')
        now = datetime.now(timezone.utc)
        if not start <= now or now + timedelta(seconds=123) > end:
            raise ValueError('OUTSIDE_CHIEF_EXECUTION_WINDOW')
        validate_bindings(binding, BINDING_SHA, dispatch_ref)
        if 'EPI_NEXT_SUPERVISOR_DIR' in os.environ:
            raise ValueError('PARENT_MUST_NOT_NEST_SUPERVISORS')
    modules = supervisor_loader(index)  # verifies existing code/package snapshot; no queue APIs
    modules['wave1_supervisor'].SupervisionSpec(**value['supervision_spec'])
    return value, binding, index, modules


def run(dispatch_ref, *, execute=False, supervisor_loader=load_supervisor):
    value, binding, index, modules = validate_plan(dispatch_ref, execute=execute, supervisor_loader=supervisor_loader)
    if not execute:
        return dict(status=value['status'], science_owner_approval='VERIFIED',
                    task_admission_metadata='VERIFIED_QUEUE_NOT_CHECKED',
                    supervisor_bundle='VERIFIED', bound_source_files=len(binding['source_sha256']) + 1,
                    execution_window=value.get('execution_window'), model_calls=0,
                    queue_observations=0, queue_writes=0, processes_started=0,
                    arrays_weights_masks_read=False, torch_imported='torch' in sys.modules)
    # Exactly one call to the unchanged supervisor. It owns queue admission,
    # durable counters, child identity, stop escalation, exit/recovery and receipt.
    os.environ.update(value['environment'])
    wave = modules['wave1_supervisor']
    return wave.run_supervised(wave.SupervisionSpec(**value['supervision_spec']),
                              child_command(value['binding'], dispatch_ref), value['supervision_root'],
                              index['dependency_root'], index['dependency_sha256'],
                              recovery_decision_path=value['new_admission_decision']['path'],
                              recovery_decision_sha=ADMISSION_SHA)


def thread_receipt(torch, directory, modules, dispatch_ref, value):
    """Thread configuration/measurement only; zero tensor/model operations."""
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    actual = dict(intra_op=torch.get_num_threads(), inter_op=torch.get_num_interop_threads())
    receipt = dict(schema='EPI_NEXT_5F_ACTUAL_THREAD_CONFIGURATION_V1',
                   dispatch=dispatch_ref, job_id=value['job_id'], task_key=value['task_key'],
                   environment={name: os.environ.get(name) for name in value['environment']},
                   torch_version=str(torch.__version__), actual_torch_threads=actual,
                   model_calls_for_thread_measurement=0,
                   global_started_monotonic=os.environ['EPI_NEXT_JOB_STARTED_MONOTONIC'],
                   budget_clock_reset=False)
    modules['coordinator_writer'].write_new(directory / 'runtime-threads.json',
                                           json.dumps(receipt, sort_keys=True).encode())
    if actual != value['torch_threads']:
        raise ValueError('CPU_ONE_THREAD_CONFIGURATION_FAILED')
    return receipt


def run_child(dispatch_ref):
    # Validate metadata without nesting a supervisor or touching its queue.
    value, binding, _, modules = validate_plan(dispatch_ref, supervised_child=True)
    directory = Path(os.environ['EPI_NEXT_SUPERVISOR_DIR'])
    if json.loads((directory / 'spec.json').read_bytes()) != value['supervision_spec']:
        raise ValueError('CHILD_SUPERVISOR_SPEC_MISMATCH')
    admitted = json.loads((directory / 'ADMITTED').read_bytes())
    if admitted['pid'] != os.getpid():
        raise ValueError('CHILD_NOT_ADMITTED_OWN_PID')
    if any(os.environ.get(name) != expected for name, expected in value['environment'].items()):
        raise ValueError('CHILD_CPU_ENVIRONMENT_DRIFT')
    # Parent's 120-second clock is already running before this import. The
    # unchanged original entry creates the one ChildGuard before loading data.
    import torch
    thread_receipt(torch, directory, modules, dispatch_ref, value)
    sys.argv = [str(ROOT / 'qa/next_selected_fidelity.py'),
                '--binding', value['binding']['path'], '--binding-sha', BINDING_SHA,
                '--dispatch', dispatch_ref['path'], '--dispatch-sha', dispatch_ref['sha256'], '--execute']
    from qa.next_selected_fidelity import main as unchanged_child_main
    return unchanged_child_main()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dispatch', type=Path, required=True)
    parser.add_argument('--dispatch-sha', required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--child', action='store_true')
    args = parser.parse_args()
    dispatch_ref = dict(path=str(args.dispatch), sha256=args.dispatch_sha)
    if args.child:
        if args.execute: parser.error('child cannot start a second supervisor')
        return run_child(dispatch_ref)
    result = run(dispatch_ref, execute=args.execute)
    print(json.dumps({key: result.get(key) for key in
                      ('status', 'science_owner_approval', 'task_admission_metadata', 'supervisor_bundle',
                       'bound_source_files', 'execution_window', 'model_calls', 'queue_observations',
                       'queue_writes', 'processes_started', 'arrays_weights_masks_read', 'torch_imported',
                       'reason', 'slot_completed')}, ensure_ascii=False))
    return 0 if not args.execute or result['status'] in {'SUCCESS', 'NO_RELIABLE_RESPONSE'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
