"""Exact P1 loader and serial planned continuation; execution needs NEW dispatch.

Preparation reads metadata plus authorized saved Mask/Adam/RNG state only;
no patient tensors or classifier weights. No medical calls are made by --prepare.
The original proposal/config/core bytes remain unchanged. Never cold-start P1.
"""
import argparse
import copy
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import platform
import sys
import time
import numpy as np
import torch
from .first_real_e1_e2 import (file_sha,locked_json,consume_inputs,baseline_source,
    DifferentiablePreparedModel,native_lookup,CONFIG_SHA,CHECKPOINT_SHA,SOURCE_HASHES)
from .shared_runner_binding_v3 import bind_child,finish_child,reconcile_counts,RESOURCE_SHA
from .runner_ledger_v3 import CounterLedger
from .spi_recovery_v2 import ComputeMeter,StopBudget,state_sha
from .hspi_core_v3 import (optimize_stage,adopt_wave1_checkpoint,spi_inputs,losses,
    frozen_classifier,rng_restore,BudgetStopped,tensor_hash)
from .hspi_profile_v3 import config_from_proposal,MeterBudget
from .p1_storage_v4 import BoundedStore,TraceStream
from .p1_retry_binding_v8 import activity_seconds,accounting_extra_roots,control_paths,time_accounting

P1_SHA='43c2822151f3a6425b8774f192616016cb580017188e6dde865d4fe7bb1ae61e'
PREPARED_SHA='0000000000000000000000000000000000000000000000000000000000000000'
LEGACY_RUN_SHA='0000000000000000000000000000000000000000000000000000000000000000'
CONSOLIDATED_SHA='0000000000000000000000000000000000000000000000000000000000000000'
APPROVAL_SHA='0000000000000000000000000000000000000000000000000000000000000000'
CAPS={'max_forward':27027,'max_backward':27000,'max_new_updates':27000,
      'extra_autograd':0,'total_seconds':3600,'per_case_cumulative_seconds':1200,
      'segment_seconds':1200,'max_planned_restores_per_case':3,'output_bytes':268435456}
MODULES=('p1_runner_v4.py','p1_storage_v4.py','p1_recovery_v5.py','p1_retry_binding_v8.py','hspi_core_v3.py','hspi_profile_v3.py',
         'first_real_e1_e2.py','preprocessed_localization.py','hspi.py','localization.py',
         'verification_vnext.py','controls_v2.py','spi_recovery_v2.py','runner_ledger_v3.py','shared_runner_binding_v3.py')


def prepare(args):
    proposal=locked_json(args.proposal,P1_SHA)
    approval=locked_json(args.approval_receipt,APPROVAL_SHA)
    if (approval['P1']['status']!='CONDITIONALLY_APPROVED' or approval['P1']['config_sha256']!=P1_SHA
            or approval['proposal_sha256']!=CONSOLIDATED_SHA or any(approval['P1'][k]!=v for k,v in CAPS.items())):
        raise ValueError('conditional approval/config/caps mismatch')
    cfg=config_from_proposal(proposal)
    local=Path(__file__).parent
    scientific=proposal['source_binding']
    for path,key in ((local/'hspi_core_v3.py','core_sha256'),(local/'hspi_profile_v3.py','profile_adapter_sha256'),
                     (local/'spi_recovery_v2.py','old_wave1_spi_sha256'),
                     (local.parent/'scripts/review_hspi_saved_v3.py','offline_reader_sha256')):
        if file_sha(path)!=scientific[key]:raise ValueError('APPROVED_SCIENTIFIC_SOURCE_DRIFT')
    delivery=locked_json(args.prepared_delivery,PREPARED_SHA) # Metadata only; no arrays/weights.
    locked_json(args.baseline_config,CONFIG_SHA)
    legacy=locked_json(args.legacy_root/'run_delivery.json',LEGACY_RUN_SHA)
    old_command=legacy['command']
    old_lock_path=Path(old_command[old_command.index('--execution-lock')+1])
    old_lock=locked_json(old_lock_path,legacy['lock_sha256'])
    versions={n:importlib.metadata.version(n) for n in ('torch','torchvision','numpy')}
    if old_lock['model_runtime_packages']!=versions or old_lock['python_version']!=platform.python_version():
        raise ValueError('EXACT_W1_MODEL_RUNTIME_DRIFT')
    records=[]
    for index in (1,2,3):
        ref=next(r for r in legacy['records'] if r['case_index']==index and r['weight']==1.)
        old=locked_json(Path(ref['result_path']),ref['result_sha256'])
        asset=next(a for a in old['checkpoint_assets'] if a['step']==1000)
        folder=Path(ref['result_path']).parent;epochs=folder/'epochs.jsonl'
        rows=[json.loads(line) for line in epochs.read_text().splitlines()]
        if len(rows)!=1000 or old['mask_weight']!=1 or old['status']!='NO_FEASIBLE_MASK':raise ValueError('wrong W1 prefix')
        if file_sha(asset['path'])!=asset['sha256']:raise ValueError('legacy checkpoint byte drift')
        cp=torch.load(asset['path'],map_location='cpu',weights_only=True) # Saved optimizer only; no classifier.
        if cp['step']!=1000 or cp['mask'].dtype!=torch.float32:raise ValueError('legacy checkpoint step/dtype')
        prepared=next(r for r in delivery['records'] if r['case_index']==index)
        if old['prepared_record']!=prepared:raise ValueError('old/new prepared identity mismatch')
        records.append({'case_index':index,'result':{'path':ref['result_path'],'sha256':ref['result_sha256']},
                        'epochs':{'path':str(epochs),'sha256':file_sha(epochs)},'checkpoint':asset,
                        'execution_lock_sha256':old['lock_sha256'],'prepared_record':prepared})
    if [r['case_index'] for r in delivery['records']]!=[1,2,3]:raise ValueError('original case order mismatch')
    dependency=locked_json(args.dependency_root/'dependency_lock.json',args.dependency_sha)
    # Read/verify dependency bytes and package versions without starting ChildGuard.
    for entry in dependency['entries']:
        if Path(entry['name']).name!=entry['name'] or file_sha(args.dependency_root/entry['name'])!=entry['sha256']:
            raise ValueError('supervisor byte drift')
    for name,expected in dependency['packages'].items():
        if importlib.metadata.version(name)!=expected:raise ValueError('dependency package drift')
    for name,expected in SOURCE_HASHES.items():
        if file_sha(args.integration_source/name)!=expected:raise ValueError('baseline loader drift')
    if file_sha(args.resource_revision)!=RESOURCE_SHA:raise ValueError('resource revision drift')
    return {'schema':'P1_ENGINEERING_READINESS_V4','status':'PREPARED_NOT_DISPATCH','original_config_sha256':P1_SHA,
        'original_consolidated_proposal_sha256':CONSOLIDATED_SHA,'conditional_approval':{'path':str(args.approval_receipt.resolve()),'sha256':file_sha(args.approval_receipt)},
        'proposal':{'path':str(args.proposal.resolve()),'sha256':P1_SHA},
        'prepared_delivery':{'path':str(args.prepared_delivery.resolve()),'sha256':PREPARED_SHA},
        'baseline_config':{'path':str(args.baseline_config.resolve()),'sha256':CONFIG_SHA},
        'core_config_sha256':cfg.sha256(),'caps':CAPS,'milestones':[3000,6000,10000],
        'records':records,'dependency_root':str(args.dependency_root.resolve()),'dependency_sha256':args.dependency_sha,
        'integration_source':str(args.integration_source.resolve()),'resource_revision':str(args.resource_revision.resolve()),
        'local_source_bindings':{str((local/n).resolve()):file_sha(local/n) for n in MODULES},
        'python_version':platform.python_version(),'model_runtime_packages':versions,
        'legacy_execution_lock':{'path':str(old_lock_path.resolve()),'sha256':legacy['lock_sha256']},
        'execution_output':str((Path(__file__).resolve().parents[3]/'.local/phase2/p1-approved-v4/run-1').resolve()),
        'prepare_command':sys.argv,
        'real_model_forwards':0,'real_model_backwards':0,'automatic_retry':False,
        'execution_gate':'new exact dispatch + owner recovery confirmed + admitted existing ChildGuard; UNKNOWN refuses before loader'}


def verify_dispatch(readiness,readiness_sha,lock):
    seconds=activity_seconds(readiness,lock)
    if lock.get('slot_status')!='RECOVERED_OWNER_CONFIRMED':raise ValueError('BLOCKED_UNKNOWN_OR_UNCONFIRMED_SLOT')
    if (readiness['conditional_approval']['sha256']!=APPROVAL_SHA
            or lock.get('status')!='LOCKED_FOR_P1_CPU_EXECUTION' or lock.get('real_model_execution_authorized') is not True
            or lock.get('readiness_sha256')!=readiness_sha or lock.get('proposal_sha256')!=P1_SHA
            or lock.get('conditional_approval_sha256')!=readiness['conditional_approval']['sha256']
            or lock.get('original_consolidated_proposal_sha256')!=CONSOLIDATED_SHA
            or lock.get('max_network_forwards')!=27027 or lock.get('max_reverse_calls')!=27000
            or lock.get('soft_timeout_seconds_total')!=seconds or lock.get('per_case_seconds')!=1200
            or lock.get('local_source_bindings')!=readiness['local_source_bindings']):
        raise ValueError('BLOCKED_NO_EXACT_P1_DISPATCH')
    if 'recovery_binding' in readiness:
        from .p1_recovery_v5 import verify_recovery_dispatch
        verify_recovery_dispatch(readiness,lock)
    else:
        receipt=locked_json(Path(lock['owner_recovery_confirmation']['path']),lock['owner_recovery_confirmation']['sha256'])
        if receipt.get('owner_explicitly_confirmed') is not True or receipt.get('administrative_recovery_only') is not True:
            raise ValueError('OWNER_RECOVERY_CONFIRMATION_REQUIRED')
    if readiness['original_config_sha256']!=P1_SHA or readiness['caps']!=CAPS:raise ValueError('readiness scope drift')
    if not set(MODULES)<={Path(p).name for p in readiness['local_source_bindings']}:
        raise ValueError('incomplete source readiness')
    locked_json(Path(readiness['conditional_approval']['path']),APPROVAL_SHA)
    proposal=locked_json(Path(readiness['proposal']['path']),P1_SHA)
    local=Path(__file__).parent
    for path,key in ((local/'hspi_core_v3.py','core_sha256'),(local/'hspi_profile_v3.py','profile_adapter_sha256'),
                     (local/'spi_recovery_v2.py','old_wave1_spi_sha256'),
                     (local.parent/'scripts/review_hspi_saved_v3.py','offline_reader_sha256')):
        if file_sha(path)!=proposal['source_binding'][key]:raise ValueError('APPROVED_SCIENTIFIC_SOURCE_DRIFT')
    for path,expected in readiness['local_source_bindings'].items():
        if file_sha(path)!=expected:raise ValueError('final local source drift')
    if lock.get('model_runtime_packages')!=readiness['model_runtime_packages'] or lock.get('python_version')!=readiness['python_version']:
        raise ValueError('runtime binding drift')


class SegmentBudget(MeterBudget):
    def __init__(self,meter,store,case_started,segment_started,target_updates,*,clock=time.monotonic):
        super().__init__(meter);self.store=store;self.case_started=case_started
        self.segment_started=segment_started;self.target_updates=target_updates;self.start_updates=meter.optimizer_steps;self.clock=clock
    def permits(self,forwards=0,backwards=0):
        now=self.clock()
        if now-self.case_started>=1200:self.reason='CASE_CUMULATIVE_DEADLINE';return False
        if now-self.segment_started>=1200:self.reason='SEGMENT_DEADLINE';return False
        if self.meter.optimizer_steps-self.start_updates>=self.target_updates:
            self.reason='PLANNED_SEGMENT_BOUNDARY';return False
        try:self.store.ensure(65536)
        except BudgetStopped as exc:self.reason=str(exc);return False
        return super().permits(forwards,backwards)


def audit_restore(model,x,valid,config,cp,meter,store,index,segment):
    if not cp.get('resume_safe',True):raise ValueError('UNSAFE_OPTIMIZER_RESUME')
    if x.dtype!=torch.float32 or x.device.type!='cpu':raise ValueError('P1 exact float32 CPU only')
    if not bool(torch.isfinite(cp['mask']).all()):raise ValueError('invalid saved mask')
    meter.check();store.ensure(65536)
    omega=torch.ones_like(cp['mask']);residual,masked=spi_inputs(x,omega,cp['mask'],config,valid)
    with frozen_classifier(model),torch.no_grad():
        baseline=meter.forward(model,residual).detach()
        if not torch.equal(baseline,cp['baseline']):raise ValueError('RESTORED_BASELINE_MISMATCH')
        meter.check();store.ensure(65536)
        logits=meter.forward(model,masked).detach()
    if logits.shape!=(1,2) or not torch.isfinite(logits).all():raise ValueError('RESTORED_MASKED_LOGITS_INVALID')
    ls,lm,loss=losses(baseline,logits,cp['mask'],config)
    store.json(f'case-{index}-restore-{segment}-audit.json',{'completed_steps':cp['completed_steps'],
        'baseline_logits':baseline.tolist(),'post_update_mask_logits':logits.tolist(),'ls':float(ls),'lm':float(lm),
        'loss':float(loss),'mask_sha256':tensor_hash(cp['mask']),
        'post_update_logit_exact_reference':'NOT_AVAILABLE_IN_LEGACY_CHECKPOINT; finite/domain/state binding audit, not invented equality'})
    rng_restore(cp['rng']) # Audits cannot alter the restored optimization RNG.


def continue_case(model,x,valid,config,cp,meter,store,index,identity,*,milestones=(3000,6000,10000),clock=time.monotonic,guard=None,case_started=None):
    """Generated-test injectable milestones; real CLI hard-binds original three."""
    if case_started is None:
        if guard is not None:guard.begin_case(f'P1-case-{index}')
        case_started=clock() if guard is None else guard.case_started
    times={'case_started_monotonic':case_started,'restores':0,'segments':[]}
    cp=copy.deepcopy(cp);cp['record_history']=False;cp['history']=[];cp['include_masks']=True
    stream=TraceStream(store,f'case-{index}-new-epochs.jsonl')
    store.json(f'case-{index}-prefix-reference.json',{'completed_legacy_steps':cp['completed_steps'],
                  'legacy_provenance':cp.get('legacy_provenance'),'legacy_prefix':cp.get('legacy_prefix'),
                  'trace_policy':'immutable W1 prefix + append-only new one-based observations'})
    result=None
    for segment,target in enumerate(milestones,1):
        if segment>3:raise ValueError('PLANNED_RESTORE_LIMIT')
        seg_started=clock();times['restores']+=1
        times.update(active_segment=segment,segment_started_monotonic=seg_started,next_target=target,phase='RESTORE_AUDIT')
        store.json(f'case-{index}-time.json',times,replace=True)
        state={'core':cp,'time':times,'counters':meter.receipt(),'trace':stream.binding(),'identity':identity}
        digest=store.checkpoint(f'case-{index}-latest.pt',state,replace=True)
        restored=store.load_checkpoint(f'case-{index}-latest.pt',digest)
        if restored['trace']!=stream.binding() or restored['counters']!=state['counters']:raise ValueError('RESTORE_RECORD_MISMATCH')
        if meter.ledger is not None and meter.ledger.read()['pending'] is not None:
            raise ValueError('UNKNOWN_INFLIGHT_COUNTER_TRANSACTION')
        current=meter.receipt()
        if any(restored['counters'][key]!=current[key] for key in
               ('forward_attempts','forward_entered','forward_completed','loss_backward_calls',
                'autograd_grad_calls','reverse_entered','reverse_completed','optimizer_steps')):
            raise ValueError('RESTORE_COUNTER_PREFIX_MISMATCH')
        cp=restored['core']
        if cp['completed_steps']>=target:raise ValueError('non-increasing plan')
        audit_restore(model,x,valid,config,cp,meter,store,index,segment)
        times['phase']='OPTIMIZING'
        budget=SegmentBudget(meter,store,case_started,seg_started,target-cp['completed_steps'],clock=clock)
        def save(current):
            nonlocal digest
            digest=store.checkpoint(f'case-{index}-latest.pt',{'core':current,'time':times,
                'counters':meter.receipt(),'trace':stream.binding(),'identity':identity},replace=True)
        result=optimize_stage(model,x,torch.ones_like(cp['mask']),config,grid=7,stage=1,identity=identity,
            resume=cp,budget=budget,valid=valid,record_history=False,include_masks=True,
            trace_sink=stream.append,checkpoint_sink=save,checkpoint_every=100,checkpoint_steps=milestones)
        cp=result['checkpoint']
        times['phase']='PLANNED_BOUNDARY' if cp['completed_steps']==target and target<config.steps else result['status']
        digest=store.checkpoint(f'case-{index}-latest.pt',{'core':cp,'time':times,
            'counters':meter.receipt(),'trace':stream.binding(),'identity':identity},replace=True,terminal=True)
        times['segments'].append({'segment':segment,'target':target,'completed_steps':cp['completed_steps'],
            'observed_iterations':result['observed_iterations'],'elapsed_seconds':clock()-seg_started,
            'case_cumulative_seconds':clock()-case_started,'stop_reason':budget.reason,'checkpoint_sha256':digest})
        store.json(f'case-{index}-time.json',times,replace=True,terminal=True)
        if result['status']=='FAILED' or cp['completed_steps']!=target or (target<config.steps and budget.reason!='PLANNED_SEGMENT_BOUNDARY'):
            break # Failure/timeout/resource stops NEVER automatically resume.
    if guard is not None:guard.end_case()
    return result,times,stream.binding()


def load_legacy(record,x,valid,cfg,identity,readiness):
    old=locked_json(Path(record['result']['path']),record['result']['sha256'])
    epochs=record['epochs'];raw=Path(epochs['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=epochs['sha256']:raise ValueError('legacy trace drift')
    asset=record['checkpoint']
    if file_sha(asset['path'])!=asset['sha256']:raise ValueError('legacy checkpoint drift')
    cp=torch.load(asset['path'],weights_only=True,map_location='cpu')
    if (cp['step']!=1000 or cp['execution_lock_sha256']!=record['execution_lock_sha256']
            or cp['proposal_sha256']!=old['proposal_sha256']):raise ValueError('legacy optimizer lock drift')
    prov={'checkpoint_sha256':asset['sha256'],'source_sha256':readiness['local_source_bindings'][str(Path(__file__).with_name('spi_recovery_v2.py').resolve())],
          'input_sha256':record['prepared_record']['arrays']['image']['sha256'],'model_sha256':CHECKPOINT_SHA,
          'preprocessing_sha256':CONFIG_SHA,'execution_lock_sha256':record['execution_lock_sha256']}
    converted=adopt_wave1_checkpoint(cp,[json.loads(line) for line in raw.splitlines()],x,valid,cfg,
                                  identity=identity,provenance=prov,expected_baseline=old['baseline_logits'])
    converted['legacy_prefix']={key:record[key] for key in ('result','epochs','checkpoint')}
    return converted


def execute(args):
    ready=locked_json(args.readiness,args.readiness_sha);lock=locked_json(args.execution_lock,args.lock_sha)
    verify_dispatch(ready,args.readiness_sha,lock) # Before ANY prepared arrays/classifier load.
    seconds=activity_seconds(ready,lock)
    control_paths(ready,args.readiness,args.execution_lock)
    args.proposal=Path(ready['proposal']['path']);args.worker_path=Path(__file__)
    args.dependency_root=Path(ready['dependency_root']);args.dependency_sha=ready['dependency_sha256']
    args.resource_revision=Path(ready['resource_revision'])
    allowed=Path(__file__).resolve().parents[3]/'.local'/'phase2'
    output=args.output.resolve()
    if str(output)!=ready['execution_output'] or not output.is_relative_to(allowed) or output.exists():
        raise ValueError('exact new ignored P1 output required; failure retry forbidden')
    guard,binding=bind_child(args,lock,P1_SHA,max_forward=27027,max_reverse=27000,seconds=seconds)
    if guard.spec.per_case_seconds!=1200:
        finish_child(guard,output,'BLOCKED',{'reverse_entered':0},actual_forward=0,reason='case deadline mismatch')
        raise ValueError('per-case supervisor deadline mismatch')
    store=None;meter=None;model=None;status='FAILED';reason=None;records=[]
    try:
        output.mkdir(parents=True,exist_ok=False)
        store=BoundedStore(output,extra_roots=accounting_extra_roots(ready,guard.directory))
        ledger=CounterLedger(output/'algorithm-counters.json',experiment_id=guard.spec.job_id,max_forwards=27027,max_reverse=27000,create=True)
        meter=ComputeMeter(max_forwards=27027,max_reverse=27000,max_seconds=seconds,guard=guard,ledger=ledger,stop_file=guard.directory/'STOP')
        proposal=locked_json(args.proposal,P1_SHA);cfg=config_from_proposal(proposal)
        store.json('submission.json',{'readiness_path':str(args.readiness.resolve()),'readiness_sha256':args.readiness_sha,
            'dispatch_path':str(args.execution_lock.resolve()),'dispatch_sha256':args.lock_sha,'binding':binding,'original_config_sha256':P1_SHA})
        meter.check();torch.set_num_threads(1)
        if torch.get_default_dtype()!=torch.float32:raise ValueError('P1 default dtype drift')
        delivery,_,spec,inputs=consume_inputs(ready['prepared_delivery']['path'],PREPARED_SHA,ready['baseline_config']['path'],CONFIG_SHA)
        for _,_,geometry in inputs:native_lookup(geometry)
        meter.check();adapter=baseline_source(Path(ready['integration_source']))
        model=DifferentiablePreparedModel(adapter.load_verified_resnet18(Path(delivery['checkpoint_path']),CHECKPOINT_SHA),spec)
        model_state=state_sha(model)
        for record,p,geometry in inputs:
            index=record['case_index'];legacy=next(r for r in ready['records'] if r['case_index']==index)
            guard.begin_case(f'P1-case-{index}')
            case_started=guard.case_started # Includes initial legacy reload/hash/validation.
            if record!=legacy['prepared_record']:raise ValueError('dispatch prepared identity drift')
            x=torch.from_numpy(p.image.copy())[None,None];valid=torch.from_numpy(p.valid_mask.copy())
            identity=json.dumps({'case_index':index,'readiness_sha256':args.readiness_sha,'input_sha256':record['arrays']['image']['sha256'],
                                 'model_sha256':CHECKPOINT_SHA,'preprocessing_sha256':CONFIG_SHA},sort_keys=True)
            cp=load_legacy(legacy,x,valid,cfg,identity,ready)
            result,times,trace=continue_case(model,x,valid,cfg,cp,meter,store,index,identity,guard=guard,case_started=case_started)
            if state_sha(model)!=model_state:raise ValueError('CLASSIFIER_STATE_CHANGED')
            best=result['best'];public={k:v for k,v in result.items() if k not in ('checkpoint','omega_before','omega_after','best','patch')}
            public.update(case_index=index,time=times,trace=trace,selection_version='PAPER_CPF_RAW_M_NO_GAP_GATE_V3',
                          best=None if best is None else {k:(v.tolist() if torch.is_tensor(v) else v) for k,v in best.items()})
            store.json(f'case-{index}-result.json',public,terminal=True)
            if result['status'] in ('FAILED','PARTIAL_BUDGET'):
                status=result['status'];reason=result['error'] or times['segments'][-1]['stop_reason'];break
            reliable=np.zeros(p.image.shape,dtype=bool);score=np.zeros(p.image.shape,dtype=np.float32)
            if result['patch'] is not None:
                reliable=result['patch'].numpy()&p.valid_mask;score[reliable]=best['gap']
            iy,ix=native_lookup(geometry);buf=io.BytesIO()
            np.savez_compressed(buf,scores=score[iy,ix],reliable=reliable[iy,ix],
                native_case_manifest_sha256=np.asarray(record['native_manifest_sha256']),SOPInstanceUID=np.asarray(record['source_sop_uid']),
                native_slice_index=np.asarray(record['native_slice_index_zero_based']))
            native_sha=store.write(f'case-{index}-single-scale-CPF-native.npz',buf.getvalue(),terminal=True)
            records.append({'case_index':index,'status':result['status'],'selected_epoch':None if best is None else best['epoch'],'native_sha256':native_sha})
        else:status='NO_RELIABLE_RESPONSE' if all(r['status']=='NO_FEASIBLE_MASK' for r in records) else 'SUCCESS'
    except (StopBudget,BudgetStopped) as exc:status='PARTIAL_BUDGET';reason=str(exc)
    except Exception as exc:status='FAILED';reason=f'{type(exc).__name__}: {exc}'
    finally:
        cost=meter.receipt() if meter else {'forward_attempts':0,'reverse_entered':0,'forward_entered':0}
        actual=0 if model is None else model.classifier_calls
        try:
            comparison=reconcile_counts(guard,cost,actual)
            if status in ('SUCCESS','NO_RELIABLE_RESPONSE') and not comparison['reservations_equal']:raise ValueError('global reservations mismatch')
            if store:store.json('run_delivery.json',{'status':status,'reason':reason,'records':records,'cost':cost,
                'actual_classifier_forward_entered':actual,'counter_comparison':comparison,'readiness_sha256':args.readiness_sha,
                'GT_access':False,'automatic_retry':False,'time_accounting':time_accounting(ready,cost),
                'output_bytes_at_receipt':store.size()},terminal=True)
        except Exception as exc:status='FAILED';reason='FINAL_RECEIPT_FAILED: '+str(exc)
        finally:
            if store:
                try:store.ensure(65536,terminal=True)
                except BudgetStopped:status='FAILED';reason='OUTPUT_TERMINAL_RESERVE_EXHAUSTED'
            finish_child(guard,output/'run_delivery.json',status,cost,actual_forward=actual,reason=reason)
            if store:
                try:
                    store.ensure(0,terminal=True)
                    store.json('output-final-size.json',{'bytes_measured_after_child_shutdown':store.size(),
                        'cap':store.cap,'reserve':store.reserve,'scope_roots':[str(store.root),*map(str,store.extra_roots)],
                        'scope':'runner + supervisor + bound old failure/control roots; parent may still write its receipt'},terminal=True)
                except Exception as exc:status='FAILED';reason='FINAL_OUTPUT_SIZE_CHECK_FAILED: '+str(exc)
    return 0 if status in ('SUCCESS','NO_RELIABLE_RESPONSE') else 2


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepare',action='store_true')
    for name in ('proposal','approval-receipt','prepared-delivery','baseline-config','legacy-root','integration-source','dependency-root','resource-revision','output','readiness','execution-lock'):
        p.add_argument('--'+name,type=Path)
    for name in ('dependency-sha','readiness-sha','lock-sha'):p.add_argument('--'+name)
    args=p.parse_args()
    if args.prepare:
        required=('proposal','approval_receipt','prepared_delivery','baseline_config','legacy_root','integration_source','dependency_root','dependency_sha','resource_revision','output')
        if any(getattr(args,k) is None for k in required):p.error('prepare needs every metadata/dependency binding')
        if '.local' not in args.output.resolve().parts:p.error('readiness must remain private')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        value=prepare(args)
        with args.output.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
        print(json.dumps({'readiness_path':str(args.output.resolve()),'sha256':file_sha(args.output),'real_model_calls':0}))
        return 0
    if any(getattr(args,k) is None for k in ('readiness','readiness_sha','execution_lock','lock_sha','output')):p.error('new exact dispatch required')
    return execute(args)

if __name__=='__main__':raise SystemExit(main())
