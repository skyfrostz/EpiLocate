"""Narrow approved P1 manual retry timing/output binding; no scheduler.

Scientific maxima are unchanged. Administrative charge60 is not a measurement
of the failed run's UNKNOWN tail. Device recovery remains a separate gate.
"""
import hashlib
import json
from pathlib import Path

REQUEST_SHA='0000000000000000000000000000000000000000000000000000000000000000'
OWNER_SHA='0000000000000000000000000000000000000000000000000000000000000000'
INVENTORY_SHA='0000000000000000000000000000000000000000000000000000000000000000'
EXPECTED={'new_activity_seconds':3540,'historical_administrative_charge_seconds':60,
    'new_updates_max':27000,'forward_max':27027,'backward_max':27000,'extra_autograd':0,
    'case_seconds':1200,'segment_seconds':1200,'planned_restores_per_case_max':3,
    'output_global_bytes_max':268435456,'old_failed_asset_bytes_included':14445}


def read(ref,expected=None):
    path=Path(ref['path'])
    if not path.is_absolute() or any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('RETRY_REFERENCE_PATH_UNSAFE')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ref['sha256'] or (expected and ref['sha256']!=expected):
        raise ValueError('RETRY_REFERENCE_SHA_DRIFT')
    return json.loads(raw)


def validate_retry(ready,lock=None):
    binding=ready.get('retry_budget')
    if binding is None:return None # Existing original3600 entry remains distinct.
    request=read(binding['request'],REQUEST_SHA);owner=read(binding['owner_approval'],OWNER_SHA)
    if (owner['schema']!='EPI_NEXT_SPRINT_OWNER_DECISION_V1' or 'P1_RETRY' not in owner['approved_items']
            or owner['request_sha256']!=REQUEST_SHA or owner['automatic_retry'] is not False
            or owner['request_path']!=binding['request']['path']):
        raise ValueError('EXPLICIT_MANUAL_RETRY_APPROVAL_REQUIRED')
    approved=request['items']['P1_RETRY']
    if any(approved.get(k)!=v or binding.get(k)!=v for k,v in EXPECTED.items()):
        raise ValueError('APPROVED_RETRY_BUDGET_DRIFT')
    if (binding.get('max_manual_attempts')!=1 or binding.get('historical_charge_is_measured') is not False
            or binding.get('original_total_administrative_seconds')!=3600
            or binding.get('old_tail_seconds')!='UNKNOWN_NOT_ZERO'):
        raise ValueError('RETRY_TIME_ACCOUNTING_DRIFT')
    inventory=read(binding['old_output_inventory'],INVENTORY_SHA)
    if inventory['bytes']!=14445 or binding['old_failed_roots']!=inventory['roots']:
        raise ValueError('OLD_FAILED_OUTPUT_SCOPE_DRIFT')
    for entry in inventory['files']:
        path=Path(entry['path'])
        if path.stat().st_size!=entry['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError('OLD_FAILED_ASSET_DRIFT')
    # Fresh identity is not a retry permit by itself. The unchanged serial/device
    # gate enforces non-spent task identity and the new recovery decision.
    if (ready['supervisor_job_id']=='EPI-NEXT-HSPI-P1-CPU-20261010-01'
            or ready['supervisor_task_key']=='EPI-NEXT-HSPI-P1-CPU-EXACT-CONTINUATION-V4'):
        raise ValueError('SPENT_P1_IDENTITY_REFUSED')
    control=Path(binding['control_root'])
    roots=[*map(Path,binding['old_failed_roots']),control,Path(ready['execution_output']),Path(ready['supervision_output_root'])]
    for i,p in enumerate(roots):
        if not p.is_absolute() or any(q.is_symlink() for q in (p,*p.parents)):
            raise ValueError('RETRY_OUTPUT_PATH_UNSAFE')
        if any(p.is_relative_to(q) or q.is_relative_to(p) for q in roots[:i]):
            raise ValueError('RETRY_OUTPUT_ROOTS_MUST_BE_DISJOINT')
    if lock is not None and lock.get('retry_budget')!=binding:
        raise ValueError('EXACT_RETRY_DISPATCH_BUDGET_REQUIRED')
    if lock is not None:
        config_ref=ready.get('retry_config')
        if config_ref is None or lock.get('retry_config')!=config_ref:
            raise ValueError('EXACT_RETRY_CONFIG_BINDING_REQUIRED')
        config=read(config_ref)
        if config.get('schema')!='P1_APPROVED_RETRY_CONFIG_V8' or config.get('retry_budget')!=binding:
            raise ValueError('RETRY_CONFIG_CONTENT_DRIFT')
        for config_key,ready_key in (('task_key','supervisor_task_key'),('job_id','supervisor_job_id'),
                ('execution_output','execution_output'),('supervision_output_root','supervision_output_root')):
            if config.get(config_key)!=ready[ready_key]:
                raise ValueError('RETRY_CONFIG_IDENTITY_DRIFT')
    return binding


def activity_seconds(ready,lock=None):
    binding=validate_retry(ready,lock)
    return 3600 if binding is None else binding['new_activity_seconds']


def accounting_extra_roots(ready,job_root):
    binding=ready.get('retry_budget')
    return (job_root,) if binding is None else (*binding['old_failed_roots'],binding['control_root'],job_root)


def control_paths(ready,ready_path,lock_path):
    binding=ready.get('retry_budget')
    if binding is not None:
        control=Path(binding['control_root']).resolve()
        if Path(ready_path).resolve().parent!=control or Path(lock_path).resolve().parent!=control:
            raise ValueError('P1_CONTROL_FILES_MUST_BE_IN_CHARGED_ROOT')


def time_accounting(ready,cost):
    binding=ready.get('retry_budget')
    if binding is None:return {'activity_limit_seconds':3600}
    elapsed=cost.get('elapsed_seconds')
    return {'activity_limit_seconds':3540,'activity_started_at':'existing v3 supervisor monotonic start',
        'observed_activity_elapsed_seconds':elapsed,'historical_administrative_charge_seconds':60,
        'administrative_total_elapsed_seconds':None if elapsed is None else 60+elapsed,
        'administrative_total_limit_seconds':3600,'historical_charge_is_measured':False,
        'old_measured_through_recovery_seconds':0.8805550420074724,'old_tail_seconds':'UNKNOWN_NOT_ZERO'}
