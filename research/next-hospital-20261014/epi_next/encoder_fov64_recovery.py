"""Read-only readiness and dispatch-gated C1 adapter for pinned recovery v3.

The scientific config, pair implementation and two-call budget are unchanged.
Only the existing shared supervisor acquires locks or creates a device slot.
"""
from __future__ import annotations
import argparse
import importlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from . import encoder_fov64_pair as pair

PACKAGE = 'epinext_wave1_supervisor_recovery_v3'
DEPENDENCY_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
P1_TASK = 'EPI-NEXT-HSPI-P1-CPU-EXACT-CONTINUATION-V4'
Blocked = pair.AdmissionBlocked


def bound(reference):
    path = Path(reference['path'])
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise Blocked('UNSAFE_BOUND_REFERENCE')
    return pair.read_bound_json(path, reference['digest'])


def load_shared(binding):
    bundle = binding['supervisor_bundle']; root = Path(bundle['package_path'])
    index = bound(bundle['consumption_index']); receipt = bound(bundle['bundle_receipt'])
    bound(bundle['dependency_lock'])
    names = {'wave1_supervisor', 'execution_lock', 'coordinator_writer', 'artifacts',
             'hospital_runtime', 'hospital_contract', 'contracts', 'geometry'}
    if (root.name != PACKAGE or index['package'] != PACKAGE or receipt['package'] != PACKAGE
            or set(bundle['modules']) != names or index['modules'] != bundle['modules']
            or receipt['loaded_modules'] != bundle['modules']
            or receipt['dependency_root'] != bundle['dependency_root']
            or receipt['dependency_lock_sha256'] != DEPENDENCY_SHA
            or bundle['dependency_lock']['digest'] != DEPENDENCY_SHA
            or pair.file_sha(root/'__init__.py') != bundle['initializer_sha256']):
        raise Blocked('RECOVERY_V3_BUNDLE_BINDING_MISMATCH')
    for name, ref in bundle['modules'].items():
        if Path(ref['path']) != root/(name+'.py') or pair.file_sha(ref['path']) != ref['sha256']:
            raise Blocked('RECOVERY_V3_MODULE_DRIFT:'+name)
    if str(root.parent) not in sys.path: sys.path.insert(0, str(root.parent))
    shared = importlib.import_module(PACKAGE+'.wave1_supervisor')
    loaded = shared.verify_loaded_bundle(bundle['dependency_root'], DEPENDENCY_SHA)
    if loaded != bundle['modules']: raise Blocked('RECOVERY_V3_LOADED_LOCATION_DRIFT')
    return shared


def validate_condition(binding, config):
    refs = binding['authority_references']; approval = bound(refs['conditional_approval'])
    proposal = bound(refs['consolidated_proposal'])
    bound(refs['original_source_binding']); bound(refs['original_command'])
    c1 = approval.get('C1', {})
    if (approval.get('schema') != 'EPI_NEXT_HUMAN_CONDITIONAL_APPROVAL_V3'
            or approval.get('proposal_path') != refs['consolidated_proposal']['path']
            or approval.get('proposal_sha256') != refs['consolidated_proposal']['digest']
            or c1.get('status') != 'CONDITIONALLY_APPROVED'
            or c1.get('max_forward') != 2 or c1.get('max_backward') != 0
            or c1.get('total_seconds') != 180 or c1.get('per_case_seconds') != 120
            or proposal['C1_optional_encoder']['execution_config'] !=
               dict(path=binding['config_path'], sha256=binding['config_sha256'])
            or config['spec'] != pair.SPEC or config['tolerance'] != pair.TOLERANCE
            or config['calls'] != dict(cpu=1, mps=1, warmup=0, repeats=0, backward=0, retry=False)
            or config['shape'] != [1,1,64,64,64] or config['feature_shape'] != [1,512,4,4,4]):
        raise Blocked('UNCHANGED_CONDITIONAL_C1_SCOPE_REQUIRED')
    decision = bound(refs['administrative_decision'])
    if (decision['approval_reference'] != refs['owner_recovery_approval']
            or decision['scope']['r0_reference'] != refs['r0_result']
            or decision['scope']['supervisor_reference'] != refs['old_supervisor_receipt']
            or decision['scope']['started_sha256'] != refs['old_started']['digest']
            or decision['scope']['basis']['conditional_approval_sha256'] != refs['conditional_approval']['digest']):
        raise Blocked('ADMINISTRATIVE_EVIDENCE_BINDING_MISMATCH')
    for key in ('owner_recovery_approval', 'r0_result', 'old_supervisor_receipt', 'old_started'):
        bound(refs[key])
    return refs


def queue_gate(queue, recovery, *, own_job=None):
    """Mirror only the one validated exception; all other unresolved slots block."""
    observed = []; slots = Path(queue)/'slots'
    if not slots.exists(): raise Blocked('BOUND_HISTORICAL_QUEUE_MISSING')
    for slot in slots.iterdir():
        if slot.is_symlink() or not slot.is_dir(): raise Blocked('UNKNOWN_QUEUE_ENTRY')
        start = json.loads((slot/'started.json').read_bytes())
        if own_job == slot.name:
            if start['job_id'] != pair.JOB or start['task_key'] != pair.TASK:
                raise Blocked('OWN_SLOT_SCOPE_MISMATCH')
            continue
        if start['task_key'] == pair.TASK: raise Blocked('NO_RETRY_OR_COUNTER_RESET')
        if not (slot/'finished.json').is_file():
            if slot.name != recovery['old_job_id']: raise Blocked('OTHER_UNKNOWN_SLOT:'+slot.name)
            observed.append(dict(job_id=slot.name, historical_status='UNKNOWN',
                                 exception='VALIDATED_ADMINISTRATIVE_DECISION_ONLY'))
            continue
        terminal = json.loads((slot/'finished.json').read_bytes())
        if pair.file_sha(terminal['receipt_path']) != terminal['receipt_sha256']:
            raise Blocked('TERMINAL_RECEIPT_SHA_MISMATCH')
        observed.append(dict(job_id=slot.name, terminal_sha256=terminal['receipt_sha256']))
    return observed


def identity(args, binding, config):
    return dict(task_key=pair.TASK, job_id=pair.JOB, owner='ENCODER', max_forward=2, max_backward=0,
                timeout_seconds=180, per_case_seconds=120, case_index=1, retry=False, head_training=False,
                config_sha256=args.config_sha, binding_sha256=args.binding_sha,
                command_template_sha256=args.command_sha, dependency_sha256=DEPENDENCY_SHA,
                source_input_sha256=config['selection']['source_input_sha256'],
                source_ledger_sha256=config['selection']['source_ledger_sha256'],
                authority_references=binding['authority_references'])


def validate_dispatch(args, binding, config):
    if not args.dispatch or not args.dispatch_sha: raise Blocked('CHIEF_DISPATCH_REQUIRED_NO_REAL_ACCESS')
    dispatch = bound(dict(path=str(args.dispatch), digest=args.dispatch_sha))
    if (dispatch.get('schema') != 'CTFM_C1_RECOVERY_DISPATCH_V1'
            or dispatch.get('status') != 'EXCLUSIVE_C1_AFTER_P1'
            or any(dispatch.get(k) != v for k,v in identity(args,binding,config).items())):
        raise Blocked('EXACT_RECOVERY_DISPATCH_REQUIRED')
    predecessor = dispatch.get('p1_released_reference')
    if not isinstance(predecessor,dict): raise Blocked('P1_RELEASE_RECEIPT_REQUIRED')
    receipt = bound(predecessor)
    exit_at, recovered_at = receipt.get('exit_monotonic'), receipt.get('recovered_monotonic')
    if (receipt.get('task_key') != P1_TASK
            or receipt.get('status') not in {'SUCCESS','NO_RELIABLE_RESPONSE','PARTIAL_BUDGET','FAILED'}
            or receipt.get('slot_completed') is not True
            or any(type(t) not in (int,float) or not math.isfinite(t) for t in (exit_at,recovered_at))
            or recovered_at < exit_at):
        raise Blocked('P1_NOT_RELEASED_WITH_VERIFIED_RECOVERY')
    # Require the queue terminal for this exact P1 receipt, beyond its claimed status.
    slot = Path(config['queue_root'])/'slots'/receipt['job_id']
    started = json.loads((slot/'started.json').read_bytes())
    finished = json.loads((slot/'finished.json').read_bytes())
    if (started['task_key'] != P1_TASK or started['job_id'] != receipt['job_id']
            or finished['receipt_path'] != predecessor['path']
            or finished['receipt_sha256'] != predecessor['digest']):
        raise Blocked('P1_SHARED_SLOT_RELEASE_BINDING_MISMATCH')
    return dict(dispatch_sha256=args.dispatch_sha, **identity(args,binding,config),
                p1_released_reference=predecessor)


def verify_readiness(args):
    config = pair.read_bound_json(args.config,args.config_sha)
    binding = pair.read_bound_json(args.binding,args.binding_sha)
    command = pair.read_bound_json(args.command_template,args.command_sha)
    if (binding['config_path'] != str(args.config) or binding['config_sha256'] != args.config_sha
            or command['config_sha256'] != args.config_sha or command['binding_sha256'] != args.binding_sha
            or binding['supervisor_bundle']['dependency_lock']['digest'] != DEPENDENCY_SHA
            or command['runner_module'] != 'epi_next.encoder_fov64_recovery'
            or command['cwd'] != str(Path(__file__).resolve().parents[3])
            or Path(command['python']).resolve() != Path(sys.executable).resolve()):
        raise Blocked('RECOVERY_READINESS_BINDING_MISMATCH')
    names = set(json.loads(Path(binding['authority_references']['original_source_binding']['path']).read_bytes())['source_sha256'])
    if set(binding['source_sha256']) != names|{'encoder_fov64_recovery.py'}:
        raise Blocked('INCOMPLETE_TRANSITIVE_C1_SOURCE_BINDING')
    for name,sha in binding['source_sha256'].items():
        if pair.file_sha(Path(__file__).parent/name) != sha: raise Blocked('C1_SOURCE_DRIFT:'+name)
    refs = validate_condition(binding,config)
    if (pair.file_sha(binding['spec_path']) != binding['spec_sha256']
            or json.loads(Path(binding['spec_path']).read_bytes()) != pair.SPEC):
        raise Blocked('ORIGINAL_C1_SPEC_DRIFT')
    shared = load_shared(binding)
    if config['queue_root'] != str(shared.hospital_runtime.QUEUE_ROOT): raise Blocked('QUEUE_ROOT_DRIFT')
    decision = refs['administrative_decision']
    recovery = shared.validate_administrative_recovery(config['queue_root'],pair.TASK,
                                                      decision['path'],decision['digest'])
    if recovery is None: raise Blocked('VALIDATED_RECOVERY_REQUIRED')
    queue = queue_gate(config['queue_root'],recovery,own_job=pair.JOB if args.mode=='child' else None)
    return config,binding,command,shared,recovery,queue


def child_argv(args):
    result = [sys.executable,'-m','epi_next.encoder_fov64_recovery','--mode','child']
    for key in ('config','config_sha','binding','binding_sha','command_template','command_sha','dispatch','dispatch_sha'):
        result.extend(['--'+key.replace('_','-'),str(getattr(args,key))])
    return result


def supervise(args, config, binding, shared):
    """Tiny API adapter; no alternative locks, scheduler, slots or retries."""
    decision = binding['authority_references']['administrative_decision']
    receipt = shared.run_supervised(shared.SupervisionSpec(**pair.SPEC),child_argv(args),
        config['supervisor_output_root'],binding['supervisor_bundle']['dependency_root'],DEPENDENCY_SHA,
        recovery_decision_path=decision['path'],recovery_decision_sha=decision['digest'])
    print(json.dumps(dict(status=receipt['status'],job_id=receipt['job_id'],slot_completed=receipt['slot_completed'])))
    return 0 if receipt['status']=='SUCCESS' else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('readiness','preflight','launch','supervise','child'),default='preflight')
    for key in ('config','binding','command-template'): parser.add_argument('--'+key,type=Path,required=True)
    for key in ('config-sha','binding-sha','command-sha'): parser.add_argument('--'+key,required=True)
    parser.add_argument('--dispatch',type=Path); parser.add_argument('--dispatch-sha')
    args = parser.parse_args()
    try:
        # Default gate precedes even the read-only evidence verification; no implicit dispatch.
        if args.mode!='readiness' and (not args.dispatch or not args.dispatch_sha):
            raise Blocked('CHIEF_DISPATCH_REQUIRED_NO_REAL_ACCESS')
        config,binding,command,shared,recovery,queue = verify_readiness(args)
        if args.mode=='readiness':
            print(json.dumps(dict(status='READINESS_VERIFIED_NOT_EXECUTED',recovery=recovery,
                                  queue=queue,torch_imported='torch' in sys.modules,real_model_calls=0)))
            return 0
        authority = validate_dispatch(args,binding,config)
        output=Path(config['output']).resolve(); private=Path(__file__).resolve().parents[3]/'.local/ctfm-v3-fov64-pair'
        if output.exists() or output==private or not output.is_relative_to(private): raise Blocked('NO_RESUME_NEW_OUTPUT_REQUIRED')
        if args.mode=='preflight':
            print(json.dumps(dict(status='PREFLIGHT_PASS_NOT_EXECUTED',real_model_calls=0))); return 0
        if args.mode=='child':
            if (os.environ.get('EPI_NEXT_DEPENDENCY_SHA')!=DEPENDENCY_SHA
                    or Path(os.environ['EPI_NEXT_DEPENDENCY_ROOT']).resolve()!=Path(binding['supervisor_bundle']['dependency_root']).resolve()
                    or json.loads((Path(os.environ['EPI_NEXT_SUPERVISOR_DIR'])/'spec.json').read_bytes())!=pair.SPEC):
                raise Blocked('ACTUAL_RECOVERY_CHILD_SUPERVISION_MISMATCH')
            return pair.run_child(config,binding,authority,shared)
        if args.mode=='supervise': return supervise(args,config,binding,shared)
        os.umask(0o077); local=output.parent; local.mkdir(parents=True,exist_ok=True,mode=0o700)
        argv=child_argv(args); argv[argv.index('child')]='supervise'
        pair.write_new(local/'actual_command_binding.json',dict(argv=argv,environment=command['environment'],
            cwd=command['cwd'],authority=authority,administrative_recovery=recovery,
            supervisor_bundle=binding['supervisor_bundle']))
        completed=subprocess.run(argv,cwd=command['cwd'],env=dict(os.environ,**command['environment']))
        pair.write_new(local/'launch_exit.json',dict(exit_code=completed.returncode)); return completed.returncode
    except (Blocked,ValueError,KeyError,OSError,RuntimeError) as exc:
        print(json.dumps(dict(status='BLOCKED',reason=str(exc),
            real_model_calls=0 if args.mode in ('readiness','preflight') or not args.dispatch else 'UNKNOWN'))); return 3


if __name__=='__main__': raise SystemExit(main())
