"""Bind LOCALIZATION workers to INTEGRATION's fixed supervision bundle."""
import importlib
import importlib.metadata
import hashlib
import json
import os
import platform
from pathlib import Path
import sys
import types
from .first_real_e1_e2 import locked_json,file_sha,write_json

RESOURCE_SHA='0000000000000000000000000000000000000000000000000000000000000000'


def load_supervisor_bundle(root,expected):
    root=Path(root).resolve();manifest=locked_json(root/'dependency_lock.json',expected)
    names={entry['name'] for entry in manifest['entries']}
    required={'wave1_supervisor.py','execution_lock.py','coordinator_writer.py','artifacts.py','hospital_runtime.py',
        'hospital_contract.py','contracts.py','geometry.py'}
    if not required<=names:raise ValueError('shared supervision dependencies incomplete')
    for entry in manifest['entries']:
        name=entry['name']
        if Path(name).name!=name or file_sha(root/name)!=entry['sha256']:raise ValueError('fixed dependency bytes mismatch')
    for name,version in manifest['packages'].items():
        if importlib.metadata.version(name)!=version:raise ValueError('fixed dependency version mismatch')
    if manifest.get('python_version',platform.python_version())!=platform.python_version():raise ValueError('fixed Python version mismatch')
    # Distinct snapshots with identical bytes still need distinct import paths.
    alias='_epi_next_fixed_shared_'+expected[:16]+'_'+hashlib.sha256(str(root).encode()).hexdigest()[:16]
    if alias not in sys.modules:
        package=types.ModuleType(alias);package.__path__=[str(root)];sys.modules[alias]=package
    execution=importlib.import_module(alias+'.execution_lock')
    execution.verify_dependencies(root,expected)
    module=importlib.import_module(alias+'.wave1_supervisor')
    if Path(module.__file__).resolve()!=root/'wave1_supervisor.py':raise ValueError('shared import resolved outside fixed bundle')
    module.verify_loaded_bundle(root,expected)
    return module


def verify_model_runtime(lock):
    versions=lock.get('model_runtime_packages',{})
    if not {'torch','torchvision','numpy'}<=versions.keys():raise ValueError('model runtime versions must be pinned separately')
    if lock.get('python_version')!=platform.python_version():raise ValueError('model Python version mismatch')
    for name,expected in versions.items():
        if importlib.metadata.version(name)!=expected:raise ValueError('model runtime version mismatch')


def bind_child(args,lock,proposal_sha,*,max_forward,max_reverse,seconds):
    revision=locked_json(args.resource_revision,RESOURCE_SHA)
    if revision['status']!='APPROVED_RESOURCE_SEMANTICS_REVISION':raise ValueError('resource revision not approved')
    if lock.get('resource_protection_revision_sha256')!=RESOURCE_SHA or lock.get('supervision_mode')!='INTEGRATION_SHARED_SUPERVISOR':raise ValueError('resource revision/shared supervision binding required')
    if lock.get('dependency_lock_sha256')!=args.dependency_sha:raise ValueError('execution dependency binding mismatch')
    if lock.get('worker_source_sha256')!=file_sha(args.worker_path):raise ValueError('final worker source drift')
    if lock.get('proposal_sha256')!=proposal_sha:raise ValueError('scientific config binding mismatch')
    verify_model_runtime(lock)
    local_bindings=lock.get('local_source_bindings',{})
    required_local={'first_real_e1_e2.py','preprocessed_localization.py','hspi.py','localization.py',
        'verification_vnext.py','controls_v2.py','spi_recovery_v2.py','runner_ledger_v3.py','shared_runner_binding_v3.py',Path(args.worker_path).name}
    if Path(args.worker_path).name=='e1_fill_runner_v3.py':required_local.add('e1_fill_v2.py')
    if not required_local<={Path(p).name for p in local_bindings}:raise ValueError('local runtime dependency bindings incomplete')
    for path,expected in local_bindings.items():
        if file_sha(path)!=expected:raise ValueError('local source drift')
    supervisor=load_supervisor_bundle(args.dependency_root,args.dependency_sha)
    guard=supervisor.ChildGuard.from_environment() # mandatory, before model load
    try:
        spec=guard.spec
        if (spec.job_id!=lock.get('supervisor_job_id') or spec.task_key!=lock.get('supervisor_task_key')
            or spec.owner!='LOCALIZATION' or spec.device!='cpu' or spec.max_forward!=max_forward
            or spec.max_backward!=max_reverse or spec.timeout_seconds!=seconds):raise ValueError('shared job scope/budget mismatch')
        guard.check()
    except Exception:
        guard.complete(status='BLOCKED',reason='shared job scope/budget mismatch',device_recovered=True,actual_forward=0,actual_backward=0);raise
    return guard,dict(shared_import_path=supervisor.__file__,shared_source_sha256=file_sha(supervisor.__file__),
        dependency_lock_sha256=args.dependency_sha,resource_revision_sha256=RESOURCE_SHA,
        supervisor_job_id=guard.spec.job_id,actual_child_pid=os.getpid())


def reconcile_counts(guard,cost,actual_forward):
    with guard.ledger() as shared:shared=dict(shared)
    if actual_forward>shared['forward'] or cost['reverse_entered']>shared['backward']:
        raise ValueError('actual entered count exceeds shared reserved attempts')
    return dict(shared_reserved_forward=shared['forward'],shared_reserved_reverse=shared['backward'],
        algorithm_reserved_forward=cost.get('forward_attempts',0),algorithm_reserved_reverse=cost.get('total_reverse_calls',0),
        actual_entered_forward=actual_forward,actual_entered_reverse=cost['reverse_entered'],
        reservations_equal=(cost.get('forward_attempts',0)==shared['forward'] and cost.get('total_reverse_calls',0)==shared['backward']),
        scope='reservations may precede stop; entered measured separately; no quota reset')


def finish_child(guard,result_path,status,cost,*,actual_forward,reason=None):
    # Completion is separate from algorithm acceptance; rejection is a valid
    # completed experiment. Parent alone determines resource/exit recovery.
    public_status=status if status in ('NO_RELIABLE_RESPONSE','PARTIAL_BUDGET','FAILED','BLOCKED') else 'SUCCESS'
    guard.complete(status=public_status,reason=reason,device_recovered=True,
        actual_forward=actual_forward,actual_backward=cost['reverse_entered'])
