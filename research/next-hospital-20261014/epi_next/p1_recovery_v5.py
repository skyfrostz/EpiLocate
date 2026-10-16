"""P1 administrative recovery adapter; prepare is read-only, dispatch separate.

The parent uses a fixed approved bundle and its serial/device gates. It never
repairs historical slots, grants model authority, or retries a failed process.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

from .first_real_e1_e2 import file_sha,locked_json
from .shared_runner_binding_v3 import load_supervisor_bundle,RESOURCE_SHA
from .p1_retry_binding_v8 import activity_seconds,control_paths

INDEX_SHA='0000000000000000000000000000000000000000000000000000000000000000'
DEPENDENCY_SHA='0000000000000000000000000000000000000000000000000000000000000000'
CHAIN_INDEX_SHA='0000000000000000000000000000000000000000000000000000000000000000'
CHAIN_DEPENDENCY_SHA='0000000000000000000000000000000000000000000000000000000000000000'
BUNDLES={INDEX_SHA:(DEPENDENCY_SHA,'epinext_wave1_supervisor_recovery_v3'),
    CHAIN_INDEX_SHA:(CHAIN_DEPENDENCY_SHA,'epinext_wave1_recovery_chain_v1')}
BASE_SHA='0000000000000000000000000000000000000000000000000000000000000000'
NAMES={'wave1_supervisor','execution_lock','coordinator_writer','artifacts',
       'hospital_runtime','hospital_contract','contracts','geometry'}


def bound_reference(ref):
    path=Path(ref['path'])
    if not path.is_absolute() or any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('RECOVERY_REFERENCE_PATH_UNSAFE')
    return locked_json(path,ref['sha256'])


def reference(path):
    path=Path(path).absolute()
    return {'path':str(path),'sha256':file_sha(path)}


def recovery_context(index_ref,decision_ref,task_key):
    """Verify byte closure and existing R0/R1 evidence, without acquiring any slot."""
    index=bound_reference(index_ref)
    expected=BUNDLES.get(index_ref['sha256'])
    if (expected is None or index['package']!=expected[1]
            or index['references']['dependency_lock']['sha256']!=expected[0]
            or set(index['modules'])!=NAMES):
        raise ValueError('EXACT_RECOVERY_V3_BUNDLE_REQUIRED')
    for ref in index['references'].values():
        path=Path(ref['path'])
        if not path.is_absolute() or any(p.is_symlink() for p in (path,*path.parents)) or file_sha(path)!=ref['sha256']:
            raise ValueError('RECOVERY_INDEX_REFERENCE_DRIFT')
    dependency=bound_reference(index['references']['dependency_lock'])
    if {e['name'] for e in dependency['entries']}!={n+'.py' for n in NAMES}:
        raise ValueError('EXACT_EIGHT_MODULE_CLOSURE_REQUIRED')
    root=Path(index['dependency_root'])
    for name,ref in index['modules'].items():
        if file_sha(Path(ref['path']))!=ref['sha256'] or file_sha(root/(name+'.py'))!=ref['sha256']:
            raise ValueError('RECOVERY_MODULE_DRIFT')
    supervisor=load_supervisor_bundle(root,expected[0])
    execution=sys.modules[supervisor.__package__+'.execution_lock']
    runtime=sys.modules[supervisor.__package__+'.hospital_runtime']
    decision=bound_reference(decision_ref)
    queue=Path(decision['queue_root'])
    if queue!=runtime.QUEUE_ROOT or any(p.is_symlink() for p in (queue,*queue.parents)):
        raise ValueError('EXACT_SHARED_QUEUE_REQUIRED')
    verified=execution.validate_administrative_recovery(queue,task_key,decision_ref['path'],decision_ref['sha256'])
    scope=decision['scope']
    def converted(ref):return {'path':ref['path'],'sha256':ref['digest']}
    approval=converted(decision['approval_reference'])
    old_start={'path':str(queue/'slots'/scope['old_job_id']/'started.json'),'sha256':scope['started_sha256']}
    r0=converted(scope['r0_reference'])
    r0_value=bound_reference(r0)
    raw=[{'path':str(Path(r0['path']).parent/name),'sha256':sha} for name,sha in sorted(r0_value['raw_sha256'].items())]
    binding={'index':index_ref,'decision':decision_ref,'owner_approval':approval,
        'old_started':old_start,'old_supervisor_receipt':converted(scope['supervisor_reference']),
        'r0':r0,'r0_raw':raw,'verified_recovery':verified,'queue_root':str(queue),
        'task_key':task_key,'modules':index['modules'],'dependency_lock':index['references']['dependency_lock']}
    if 'predecessor_recovery_reference' in scope:
        predecessor=converted(scope['predecessor_recovery_reference'])
        old=bound_reference(predecessor);previous=old['scope']
        previous_review=converted(previous['r0_reference']);review_value=bound_reference(previous_review)
        binding['predecessor_evidence']={'decision':predecessor,'owner_approval':converted(old['approval_reference']),
            'old_started':{'path':str(queue/'slots'/previous['old_job_id']/'started.json'),
                'sha256':previous['started_sha256']},'old_supervisor_receipt':converted(previous['supervisor_reference']),
            'r0':previous_review,'r0_raw':[{'path':str(Path(previous_review['path']).parent/name),'sha256':sha}
                for name,sha in sorted(review_value['raw_sha256'].items())]}
    return supervisor,binding


def prepare_recovery(base_ref,index_ref,decision_ref,*,job_id,task_key,supervision_root,execution_output):
    """New record from original immutable preparation; old records untouched."""
    from . import p1_runner_v4 as worker
    base=bound_reference(base_ref)
    if base_ref['sha256']!=BASE_SHA:raise ValueError('EXACT_P1_BASE_READINESS_REQUIRED')
    supervisor,binding=recovery_context(index_ref,decision_ref,task_key)
    # Reconstruct metadata-only prepare, including old authorized Mask/Adam/RNG.
    command=base['prepare_command']
    def option(name):return Path(command[command.index('--'+name)+1])
    args=SimpleNamespace(**{name.replace('-','_'):option(name) for name in
        ('proposal','approval-receipt','prepared-delivery','baseline-config','legacy-root','integration-source','resource-revision')},
        dependency_root=Path(binding['dependency_lock']['path']).parent,dependency_sha=binding['dependency_lock']['sha256'])
    new=worker.prepare(args)
    output=Path(execution_output).absolute();parent=Path(supervision_root).absolute()
    allowed=Path(worker.__file__).resolve().parents[3]/'.local/phase2'
    if not output.is_relative_to(allowed) or not parent.is_relative_to(allowed) or output.exists() or parent.exists():
        raise ValueError('NEW_PRIVATE_P1_OUTPUT_ROOTS_REQUIRED')
    if output.is_relative_to(parent) or parent.is_relative_to(output):
        raise ValueError('DISJOINT_OUTPUT_ROOTS_REQUIRED')
    supervisor.SupervisionSpec(job_id=job_id,task_key=task_key,owner='LOCALIZATION',device='cpu',
        max_forward=27027,max_backward=27000,timeout_seconds=3600,per_case_seconds=1200)
    new.update(schema='P1_RECOVERY_READINESS_V5',status='PREPARED_NOT_DISPATCH',
        previous_readiness=base_ref,recovery_binding=binding,supervisor_job_id=job_id,
        supervisor_task_key=task_key,supervision_output_root=str(parent),execution_output=str(output),
        parent_source_sha256=file_sha(__file__),python_executable=str(Path(sys.executable).absolute()),
        cwd=str(Path.cwd().resolve()),parent_prepare_command=sys.argv,
        execution_gate='chief exact dispatch + unique serial queue; administrative approval does not grant model authority')
    return new


def dispatch_template(ready,ready_ref):
    """Reviewable required fields, explicitly not an authorized execution lock."""
    from . import p1_runner_v4 as worker
    return {'schema':'P1_RECOVERY_DISPATCH_V5','status':'DISPATCH_TEMPLATE_NOT_AUTHORIZED',
        'slot_status':'RECOVERED_OWNER_CONFIRMED','real_model_execution_authorized':False,
        'readiness_sha256':ready_ref['sha256'],'readiness':ready_ref,
        'proposal_sha256':worker.P1_SHA,'conditional_approval_sha256':worker.APPROVAL_SHA,
        'original_consolidated_proposal_sha256':worker.CONSOLIDATED_SHA,
        'max_network_forwards':27027,'max_reverse_calls':27000,'soft_timeout_seconds_total':activity_seconds(ready),'per_case_seconds':1200,
        'local_source_bindings':ready['local_source_bindings'],'model_runtime_packages':ready['model_runtime_packages'],
        'python_version':ready['python_version'],'worker_source_sha256':file_sha(worker.__file__),
        'parent_source_sha256':file_sha(__file__),'dependency_lock_sha256':ready['dependency_sha256'],
        'resource_protection_revision_sha256':RESOURCE_SHA,'supervision_mode':'INTEGRATION_SHARED_SUPERVISOR',
        'supervisor_job_id':ready['supervisor_job_id'],'supervisor_task_key':ready['supervisor_task_key'],
        'supervision_output_root':ready['supervision_output_root'],'execution_output':ready['execution_output'],
        'caps':ready['caps'],'recovery_binding':copy.deepcopy(ready['recovery_binding']),
        **({'retry_budget':copy.deepcopy(ready['retry_budget'])} if 'retry_budget' in ready else {}),
        **({'retry_config':copy.deepcopy(ready['retry_config'])} if 'retry_config' in ready else {}),
        'unique_queue_verified_by_chief':False}


def verify_recovery_dispatch(ready,lock):
    from . import p1_runner_v4 as worker
    if (ready.get('schema')!='P1_RECOVERY_READINESS_V5' or lock.get('schema')!='P1_RECOVERY_DISPATCH_V5'
            or lock.get('recovery_binding')!=ready['recovery_binding']
            or lock.get('dependency_lock_sha256')!=ready['recovery_binding']['dependency_lock']['sha256']
            or ready['dependency_sha256']!=ready['recovery_binding']['dependency_lock']['sha256']
            or lock.get('parent_source_sha256')!=file_sha(__file__)
            or lock.get('worker_source_sha256')!=file_sha(worker.__file__)
            or lock.get('caps')!=worker.CAPS or lock.get('unique_queue_verified_by_chief') is not True
            or ready['parent_source_sha256']!=file_sha(__file__)
            or ready['python_executable']!=str(Path(sys.executable).absolute()) or ready['cwd']!=str(Path.cwd().resolve())):
        raise ValueError('EXACT_RECOVERY_P1_DISPATCH_REQUIRED')
    for key in ('supervisor_job_id','supervisor_task_key','supervision_output_root','execution_output'):
        if lock.get(key)!=ready[key]:raise ValueError('RECOVERY_JOB_OR_OUTPUT_DRIFT')
    binding=ready['recovery_binding']
    _,current=recovery_context(binding['index'],binding['decision'],ready['supervisor_task_key'])
    if current!=binding:raise ValueError('RECOVERY_EVIDENCE_DRIFT')
    if str(Path(ready['dependency_root'])/'dependency_lock.json')!=binding['dependency_lock']['path']:
        raise ValueError('RECOVERY_DEPENDENCY_ROOT_DRIFT')


def worker_command(ready,ready_ref,lock_ref):
    return [ready['python_executable'],'-m','epi_next.p1_runner_v4',
        '--readiness',ready_ref['path'],'--readiness-sha',ready_ref['sha256'],
        '--execution-lock',lock_ref['path'],'--lock-sha',lock_ref['sha256'],'--output',ready['execution_output']]


def run_parent(ready_ref,lock_ref):
    """No invocation until chief publishes the precise authorized dispatch."""
    from . import p1_runner_v4 as worker
    ready=bound_reference(ready_ref);lock=bound_reference(lock_ref)
    worker.verify_dispatch(ready,ready_ref['sha256'],lock)
    seconds=activity_seconds(ready,lock)
    control_paths(ready,ready_ref['path'],lock_ref['path'])
    if 'retry_budget' in ready:
        from .p1_storage_v4 import BoundedStore
        # Control files/parent stdout and all old failures consume the same cap
        # before any new child is spawned; no runner root is created here.
        BoundedStore(ready['retry_budget']['control_root'],extra_roots=ready['retry_budget']['old_failed_roots']).ensure(65536)
    supervisor=load_supervisor_bundle(ready['dependency_root'],ready['dependency_sha256'])
    for root in (ready['execution_output'],ready['supervision_output_root']):
        if Path(root).exists():raise ValueError('FAILURE_RETRY_OR_OUTPUT_REUSE_FORBIDDEN')
    spec=supervisor.SupervisionSpec(job_id=ready['supervisor_job_id'],task_key=ready['supervisor_task_key'],
        owner='LOCALIZATION',device='cpu',max_forward=27027,max_backward=27000,timeout_seconds=seconds,per_case_seconds=1200)
    decision=ready['recovery_binding']['decision']
    expected={'PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1',
              'PYTHONPATH':str(Path(worker.__file__).resolve().parents[1])}
    if any(os.environ.get(k)!=v for k,v in expected.items()):raise ValueError('EXACT_P1_PARENT_ENVIRONMENT_REQUIRED')
    return supervisor.run_supervised(spec,worker_command(ready,ready_ref,lock_ref),
        ready['supervision_output_root'],ready['dependency_root'],ready['dependency_sha256'],
        recovery_decision_path=decision['path'],recovery_decision_sha=decision['sha256'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepare',action='store_true');p.add_argument('--run',action='store_true')
    for name in ('base-readiness','index','decision','output','template-output','supervision-root','execution-output','readiness','dispatch'):
        p.add_argument('--'+name,type=Path)
    for name in ('base-sha','index-sha','decision-sha','job-id','task-key','readiness-sha','dispatch-sha'):
        p.add_argument('--'+name)
    args=p.parse_args()
    if args.prepare==args.run:p.error('choose prepare or run')
    if args.prepare:
        required=('base_readiness','base_sha','index','index_sha','decision','decision_sha','output',
                  'template_output','job_id','task_key','supervision_root','execution_output')
        if any(getattr(args,n) is None for n in required):p.error('complete immutable preparation bindings required')
        for out in (args.output,args.template_output):
            if '.local' not in out.absolute().parts:p.error('private new records required')
            if out.exists():p.error('immutable output exists')
        ready=prepare_recovery({'path':str(args.base_readiness.absolute()),'sha256':args.base_sha},
            {'path':str(args.index.absolute()),'sha256':args.index_sha},
            {'path':str(args.decision.absolute()),'sha256':args.decision_sha},job_id=args.job_id,task_key=args.task_key,
            supervision_root=args.supervision_root,execution_output=args.execution_output)
        for out,value in ((args.output,ready),(args.template_output,None)):
            out.parent.mkdir(parents=True,exist_ok=True)
            if value is None:value=dispatch_template(ready,reference(args.output))
            with out.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
        print(json.dumps({'readiness':reference(args.output),'dispatch_template':reference(args.template_output),
            'real_model_calls':0,'actual_dispatch_issued':False}))
    else:
        if any(getattr(args,n) is None for n in ('readiness','readiness_sha','dispatch','dispatch_sha')):p.error('exact chief dispatch required')
        result=run_parent({'path':str(args.readiness.absolute()),'sha256':args.readiness_sha},
                          {'path':str(args.dispatch.absolute()),'sha256':args.dispatch_sha})
        print(json.dumps(result,default=str))
        return 0 if result['status'] in ('SUCCESS','NO_RELIABLE_RESPONSE') else 2
    return 0


if __name__=='__main__':raise SystemExit(main())
