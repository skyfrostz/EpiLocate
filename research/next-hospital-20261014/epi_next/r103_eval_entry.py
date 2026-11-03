"""Prepared 0-model-call medical registry evaluation; default is binding only.

No real registry is read without exact new approval/resolution/admission/dispatch
and the original shared supervisor. R102 budgets/implementations are untouched.
"""

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[3]
import argparse
import ast
import datetime
import hashlib
import importlib.metadata
import json
import resource
import subprocess
import sys
from pathlib import Path
from .r103_slice_evaluation import evaluate,require,reference


DATA_ROOT=Path(str(_PUBLIC_ROOT / '.'))
REPO=Path(__file__).resolve().parents[3]
REPORTS=Path(__file__).parents[1]/'reports/r103_encoder'
TASK_KEY='R103-R18-FIXED8-SLICE-REFERENCE-EVALUATION-CPU-ONCE'
JOB_ID='r103-r18-slice-eval-01'
LIMITS=dict(seconds=60,rss_bytes=512*1024**2,output_bytes=8*1024**2,delivery_bytes=16*1024**2,
            model_forward=0,backward=0,updates=0,threads=1,retry=False,warmup=0)


class NoConfirmedReference(RuntimeError):
    """Scientific NOT_RUN branch, not a failed/retried evaluation."""


def sha(raw):return hashlib.sha256(raw).hexdigest()


def safe(path):
    p=Path(path)
    require(p.is_absolute() and not any(x.is_symlink() for x in (p,*p.parents)),'ABSOLUTE_NONSYMLINK_PATH')
    return p


def bound(ref,max_bytes=8*1024**2):
    require(reference(ref),'EXACT_PATH_SHA_REFERENCE')
    path=safe(ref['path']);require(path.stat().st_size<=max_bytes,'BOUNDED_JSON_SOURCE')
    raw=path.read_bytes();require(sha(raw)==ref['sha256'],'SHA_DRIFT')
    return json.loads(raw)


def source_closure():
    pending=[Path(__file__).resolve()];found=set()
    while pending:
        path=pending.pop()
        if path in found:continue
        found.add(path)
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node,ast.ImportFrom) and node.level==1:
                for name in ([node.module] if node.module else [a.name for a in node.names]):
                    child=path.parent/(name.split('.')[0]+'.py')
                    if child.is_file():pending.append(child)
    found.update(REPORTS/name for name in ('SLICE_EVALUATION_PROTOCOL_V1.json','SLICE_REFERENCE_REGISTRY_SCHEMA_V1.json','REGISTRY_LATE_BINDING_CONTRACT_V1.json'))
    return sorted(found)


def check_request(q):
    require(q['schema']=='R103_SAVED_SLICE_EVALUATION_REQUEST_V1' and q['limits']==LIMITS,'EXACT_R103_REQUEST')
    require(q['spec']['task_key']==TASK_KEY and q['spec']['job_id']==JOB_ID and q['spec']['owner']=='ENCODER'
            and q['spec']['device']=='cpu' and q['spec']['max_forward']==q['spec']['max_backward']==0
            and q['spec']['timeout_seconds']==60 and q['spec']['per_case_seconds'] is None,'EXACT_ZERO_MODEL_SPEC')
    require(isinstance(q['source_commit'],str) and len(q['source_commit'])==40 and all(c in '0123456789abcdef' for c in q['source_commit']),'COMMITTED_ENCODER_SOURCE_REQUIRED')
    require({safe(r['path']) for r in q['sources']}==set(source_closure()),'FULL_COMMITTED_SOURCE_CLOSURE')
    for r in q['sources']:
        raw=safe(r['path']).read_bytes();require(sha(raw)==r['sha256'],'SOURCE_DRIFT')
        blob=subprocess.check_output(['git','-C',str(REPO),'show',q['source_commit']+':'+str(Path(r['path']).relative_to(REPO))],timeout=5)
        require(sha(blob)==r['sha256'],'COMMITTED_SOURCE_REQUIRED')
    for r in q['runtime']['references']:require(sha(safe(r['path']).read_bytes())==r['sha256'],'RUNTIME_REFERENCE_DRIFT')
    require(sys.version.split()[0]==q['runtime']['python_version'] and Path(sys.executable).resolve()==Path(q['runtime']['executable']).resolve(),'PYTHON_RUNTIME_IDENTITY')
    for name,version in q['runtime']['packages'].items():require(importlib.metadata.version(name)==version,'PACKAGE_DRIFT')
    require(q['registry_contract']==dict(path=str(REPORTS/'REGISTRY_LATE_BINDING_CONTRACT_V1.json'),sha256=sha((REPORTS/'REGISTRY_LATE_BINDING_CONTRACT_V1.json').read_bytes())),'FIXED_REGISTRY_BINDING_CONTRACT')
    require(q['protocol']==dict(path=str(REPORTS/'SLICE_EVALUATION_PROTOCOL_V1.json'),sha256=sha((REPORTS/'SLICE_EVALUATION_PROTOCOL_V1.json').read_bytes())),'FIXED_METRIC_PROTOCOL')
    root=safe(q['delivery_root']);require(root in safe(q['output']).parents and root in safe(q['supervisor_output']).parents,'OUTPUT_BOUNDARY')
    return q


def resolve_registry(binding,q,request_sha):
    contract=bound(q['registry_contract']);lock=contract['producer_lock']
    require(lock['status']=='EXACT_PRODUCER_LOCKED' and all(lock[k] for k in
        ('request','source_commit','sources','registry_path','science_receipt_path','science_receipt_schema','science_success_statuses',
         'receipt_request_sha_field','receipt_registry_ref_field','receipt_confirmed_positions_field','owner_schema','owner_success_status','owner_request_sha_field',
         'producer_job_id','producer_task_key','supervisor_receipt_path','slot_finished_path')),'BLOCKED_PENDING_EXACT_DATA_PRODUCER')
    require(type(contract.get('medical_evaluation_ready')) is bool,'EXPLICIT_PRODUCER_MEDICAL_READINESS')
    if contract['medical_evaluation_ready'] is False:
        raise NoConfirmedReference('BLOCKED_FROZEN_PRODUCER_HAS_NO_CONFIRMED_REFERENCE_PATH_NEW_VERSION_REQUIRED')
    require(set(binding)=={'schema','scientific_request_sha256','registry','producer_science_receipt','producer_owner_approval','producer_supervisor_receipt','producer_slot_finished'},'STRICT_LATE_BINDING_FIELDS')
    require(binding['schema']=='R103_DATA_REGISTRY_BINDING_V1' and binding['scientific_request_sha256']==request_sha,'REGISTRY_BINDING_REQUEST')
    producer_request=bound(lock['request'])
    declared=producer_request['source_bindings']
    require(all(set(r) in ({'path','sha256'},{'path','sha256','bytes'}) for r in declared),'STRICT_PRODUCER_SOURCE_FIELDS')
    require(producer_request['source_commit']==lock['source_commit']
            and [dict(path=r['path'],sha256=r['sha256']) for r in declared]==lock['sources'],'EXACT_COMPLETE_PRODUCER_REQUEST_SOURCE_CLOSURE')
    for r in declared:
        if 'bytes' in r:require(type(r['bytes']) is int and safe(r['path']).stat().st_size==r['bytes'],'PRODUCER_SOURCE_BYTE_DECLARATION')
    require(producer_request['consumer']==q['consumer'] and producer_request['ENC_fixed8_control']==q['fixed8_control'],'PRODUCER_FIXED_CONTROL_CONSUMER_BINDING')
    require(lock['registry_path']==str(Path(producer_request['output_root'])/'DEVELOPMENT20_V2.json')
        and lock['science_receipt_path']==str(Path(producer_request['output_root'])/'PRODUCER_RECEIPT_V2.json')
        and producer_request['spec']['job_id']==lock['producer_job_id'] and producer_request['spec']['task_key']==lock['producer_task_key']
        and producer_request['spec']['max_forward']==producer_request['spec']['max_backward']==0
        and lock['supervisor_receipt_path']==str(Path(producer_request['supervisor_output'])/lock['producer_job_id']/'supervisor-receipt.json'),'PRODUCER_OUTPUT_SPEC_PATH_CLOSURE')
    require(reference(binding['registry']) and binding['registry']['path']==lock['registry_path']
            and DATA_ROOT/'.local' in safe(binding['registry']['path']).parents,'EXACT_FIXED_PRODUCER_OUTPUT_PATH')
    commit=lock['source_commit'];require(isinstance(commit,str) and len(commit)==40 and all(c in '0123456789abcdef' for c in commit),'PRODUCER_COMMIT')
    source_root=DATA_ROOT/'research/next-hospital-20261014/epi_next'
    require(lock['sources'] and len({r['path'] for r in lock['sources']})==len(lock['sources']),'UNIQUE_LOCKED_PRODUCER_CLOSURE')
    for r in lock['sources']:
        require(reference(r) and source_root in safe(r['path']).parents,'EXACT_DATA_SOURCE_ROOT')
        raw=safe(r['path']).read_bytes();require(sha(raw)==r['sha256'],'PRODUCER_SOURCE_DRIFT')
        blob=subprocess.check_output(['git','-C',str(DATA_ROOT),'show',commit+':'+str(Path(r['path']).relative_to(DATA_ROOT))],timeout=5)
        require(sha(blob)==r['sha256'],'COMMITTED_DATA_PRODUCER_REQUIRED')
    def field(value,keys):
        require(isinstance(keys,list) and keys and all(isinstance(k,str) and k for k in keys),'LOCKED_RECEIPT_FIELD_PATH')
        for key in keys:value=value[key]
        return value
    require(binding['producer_science_receipt']['path']==lock['science_receipt_path'],'EXACT_SCIENCE_RECEIPT_PATH')
    science=bound(binding['producer_science_receipt'])
    require(science['schema']==lock['science_receipt_schema'] and science['status'] in lock['science_success_statuses'],'SUCCESSFUL_R103_PRODUCER_RECEIPT')
    require(field(science,lock['receipt_request_sha_field'])==lock['request']['sha256']
            and field(science,lock['receipt_registry_ref_field'])==binding['registry'],'PRODUCER_REQUEST_OUTPUT_RECEIPT_BINDING')
    permission=bound(binding['producer_owner_approval'])
    require(permission['schema']==lock['owner_schema'] and permission['status']==lock['owner_success_status']
            and field(permission,lock['owner_request_sha_field'])==lock['request']['sha256'],'NEW_DATA_REQUEST_PERMISSION_NOT_OLD_A')
    require(binding['producer_supervisor_receipt']['path']==lock['supervisor_receipt_path'] and binding['producer_slot_finished']['path']==lock['slot_finished_path'],'EXACT_PRODUCER_SUPERVISOR_SLOT')
    supervisor=bound(binding['producer_supervisor_receipt']);finished=bound(binding['producer_slot_finished'])
    require(supervisor['schema']=='EPI-NEXT-WAVE1-SUPERVISION-1' and supervisor['status']=='SUCCESS' and supervisor['slot_completed'] is True
        and supervisor['job_id']==lock['producer_job_id'] and supervisor['task_key']==lock['producer_task_key'],'SUCCESSFUL_EXACT_PRODUCER_SUPERVISION')
    require(supervisor['dependency_sha256']==q['supervisor']['dependency_sha256']
        and supervisor['actual_loaded_supervisor_modules']==q['supervisor']['modules'],'PINNED_PRODUCER_SUPERVISOR_DEPENDENCIES')
    require(supervisor['runner_actual_counts']==dict(forward=0,backward=0)
            and supervisor['counters']['forward']==supervisor['counters']['backward']==0,'DATA_PRODUCER_ZERO_MODEL_SCOPE')
    require(finished['status']=='SUCCESS' and finished['job_id']==lock['producer_job_id'] and finished['receipt_path']==binding['producer_supervisor_receipt']['path']
            and finished['receipt_sha256']==binding['producer_supervisor_receipt']['sha256'] and finished['children']
            and all(c['exit_code']==0 for c in finished['children']),'PRODUCER_SLOT_FINISHED_ZERO_EXIT')
    confirmed=field(science,lock['receipt_confirmed_positions_field'])
    if confirmed is None or type(confirmed) is int and confirmed==0:
        raise NoConfirmedReference('NOT_RUN_NO_CONFIRMED_REFERENCE_FROM_THE_SAME_FROZEN_DATA_REQUEST')
    require(type(confirmed) is int and 0<confirmed<=160,'EXACT_PRODUCER_CONFIRMED_DENOMINATOR')
    # Registry content includes medical labels: only admitted child calls bound().
    return dict(registry=binding['registry'],confirmed_positions=confirmed)


def run_child(q,binding_ref,request_sha,shared):
    guard=shared.ChildGuard.from_environment()
    require(vars(guard.spec)==vars(shared.SupervisionSpec(**q['spec'])),'ADMITTED_CHILD_SPEC')
    guard.begin_case(JOB_ID)
    output=safe(q['output']);require(not output.exists(),'NO_OUTPUT_REUSE')
    output.mkdir(parents=True)
    def check():
        guard.check()
        rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)
        require(rss<LIMITS['rss_bytes'],'RSS_LIMIT')
        require(sum(p.stat().st_size for p in safe(q['delivery_root']).rglob('*') if p.is_file())<LIMITS['delivery_bytes'],'DELIVERY_LIMIT')
    try:
        check();binding=bound(binding_ref);resolution=resolve_registry(binding,q,request_sha);registry_ref=resolution['registry']
        scores=bound(q['scores']);control=bound(q['fixed8_control']);original=bound(scores['source_artifact'])
        require(scores['fixed8_control']==q['fixed8_control'] and control['consumer']==q['consumer'],'SAVED_CONTROL_CLOSURE')
        require(scores['source_artifact']==q['original_contributions'] and scores['cases']==[r for r in original['cases'] if r['split']=='val_classification'],'EXISTING_JSON_NUMBERS_ONLY')
        registry=bound(registry_ref);require(registry['denominators']['confirmed_positions']==resolution['confirmed_positions'],'SUCCESS_RECEIPT_REGISTRY_DENOMINATOR_MISMATCH');check()
        result=evaluate(scores,control,registry,bound(q['protocol']));check()
        result.update(request_sha256=request_sha,registry_binding=binding_ref,registry=registry_ref,scores=q['scores'],fixed8_control=q['fixed8_control'])
        raw=(json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+'\n').encode();require(len(raw)<LIMITS['output_bytes'],'OUTPUT_LIMIT')
        with (output/'evaluation.json').open('xb') as stream:stream.write(raw)
        check();guard.end_case();guard.complete('SUCCESS',device_recovered=True,actual_forward=0,actual_backward=0)
        return result
    except BaseException as exc:
        failure=dict(status='FAILED',reason=type(exc).__name__,detail=str(exc),model_forward=0,backward=0,updates=0)
        with (output/'failure.json').open('x') as stream:json.dump(failure,stream,sort_keys=True,allow_nan=False)
        guard.complete('FAILED',reason=type(exc).__name__,device_recovered=False,actual_forward=0,actual_backward=0)
        raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('request','request-sha'):parser.add_argument('--'+name,required=True)
    for name in ('approval','approval-sha','dispatch','dispatch-sha','admission','admission-sha','registry-binding','registry-binding-sha'):parser.add_argument('--'+name)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--child',action='store_true')
    args=parser.parse_args(argv);request_ref=dict(path=args.request,sha256=args.request_sha);q=check_request(bound(request_ref))
    if not args.execute:
        print(json.dumps(dict(status='PASS_BINDING_ONLY',execution_readiness=q.get('execution_readiness','NOT_RUN'),medical_evaluation='NOT RUN',registry_read=False,torch_imported='torch' in sys.modules)));return 0
    require(all(getattr(args,n) for n in ('approval','approval_sha','dispatch','dispatch_sha','admission','admission_sha','registry_binding','registry_binding_sha')),'NEW_APPROVAL_BOUND_REGISTRY_ADMISSION_DISPATCH_REQUIRED')
    if bound(q['registry_contract'])['medical_evaluation_ready'] is False:
        print(json.dumps(dict(status='BLOCKED_FROZEN_PRODUCER_NO_REFERENCE_SCOPE',medical_evaluation='NOT RUN',queue_entered=False,model_calls=0)));return 0
    registry_ref=dict(path=args.registry_binding,sha256=args.registry_binding_sha)
    for path,digest,schema,status in ((args.approval,args.approval_sha,'R103_SLICE_EVALUATION_APPROVAL_V1','APPROVED_NEW_SCOPE'),(args.dispatch,args.dispatch_sha,'R103_SLICE_EVALUATION_DISPATCH_V1','EXCLUSIVE_SLOT_ASSIGNED')):
        value=bound(dict(path=path,sha256=digest))
        require(all(value.get(k)==v for k,v in dict(schema=schema,status=status,request_sha256=args.request_sha,registry_binding_sha256=args.registry_binding_sha,owner='ENCODER',task_key=TASK_KEY,retry=False).items()),'EXACT_NEW_AUTHORITY_AND_REGISTRY_SHA')
        if path==args.dispatch:
            require(value['approval_sha256']==args.approval_sha and value['spec']==q['spec'] and value['limits']==LIMITS,'EXACT_DISPATCH_SPEC')
            window=value['execution_window'];now=datetime.datetime.now(datetime.timezone.utc)
            require(window['status']=='CHIEF_SLOT_GRANTED' and datetime.datetime.fromisoformat(window['not_before_utc'])<=now<datetime.datetime.fromisoformat(window['not_after_utc']),'LIVE_EXECUTION_WINDOW')
    admission=bound(dict(path=args.admission,sha256=args.admission_sha))
    require(set(admission)=={'schema','request_sha256','approval_sha256','registry_binding_sha256','owner','task_key','recovery_decision'}
        and all(admission[k]==v for k,v in dict(schema='R103_SLICE_ADMINISTRATIVE_BINDING_V1',request_sha256=args.request_sha,approval_sha256=args.approval_sha,registry_binding_sha256=args.registry_binding_sha,owner='ENCODER',task_key=TASK_KEY).items()),'STRICT_INDEPENDENT_ADMISSION')
    recovery=admission['recovery_decision'];bound(recovery)
    require(bound(q['registry_contract'])['producer_lock']['status']=='EXACT_PRODUCER_LOCKED','PRODUCER_NOT_READY_NO_QUEUE_ENTRY')
    try:resolve_registry(bound(registry_ref),q,args.request_sha)
    except NoConfirmedReference as exc:
        print(json.dumps(dict(status='NOT_RUN_NO_CONFIRMED_REFERENCE',reason=str(exc),model_calls=0,queue_entered=False)));return 0
    from . import ctfm_research_pipeline_v4 as p
    shared=p.load_shared(q)
    if args.child:run_child(q,registry_ref,args.request_sha,shared);return 0
    child=[sys.executable,'-m','epi_next.r103_eval_entry',*sum(([flag,value] for flag,value in
        [('--request',args.request),('--request-sha',args.request_sha),('--approval',args.approval),('--approval-sha',args.approval_sha),
         ('--dispatch',args.dispatch),('--dispatch-sha',args.dispatch_sha),('--admission',args.admission),('--admission-sha',args.admission_sha),
         ('--registry-binding',args.registry_binding),('--registry-binding-sha',args.registry_binding_sha)]),[]),'--execute','--child']
    receipt=shared.run_supervised(shared.SupervisionSpec(**q['spec']),child,q['supervisor_output'],q['supervisor']['dependency_root'],p.SHARED_SHA,
        recovery_decision_path=recovery['path'],recovery_decision_sha=recovery['sha256'])
    return 0 if receipt['status']=='SUCCESS' and receipt['slot_completed'] else 2


if __name__=='__main__':raise SystemExit(main())
