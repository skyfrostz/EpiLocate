"""Prepared R1/R2 runner, separate from frozen HSPI. Execution needs a new lock.

Only single-scale SPI/CPF; no PSMI/hierarchy, GT selection or automatic retries.
"""
import argparse
import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import random
import resource
import sys
import time
import numpy as np
import torch
import torch.nn.functional as F
from .controls_v2 import graph_contains_leaf


class StopBudget(RuntimeError):pass


@dataclass
class ComputeMeter:
    max_forwards: int = 7000
    max_reverse: int = 10000
    max_seconds: float = 900.
    max_rss: int = 6*1024**3
    clock: object = time.monotonic
    guard: object = None
    ledger: object = None
    stop_file: object = None

    def __post_init__(self):
        self.started=self.clock();self.forwards=0;self.backward=0;self.autograd=0
        self.forward_completed=0;self.reverse_completed=0;self.optimizer_steps=0
        self.forward_entered=0;self.reverse_entered=0;self.phase={}
        if self.guard is not None:self.started=self.guard.started
        if self.ledger is not None:self._restore()
    def _restore(self):
        value=self.ledger.read();self.forwards=value['forward_attempts'];self.forward_completed=value['forward_completed']
        self.backward=value['loss_backward_calls'];self.autograd=value['autograd_grad_calls']
        self.reverse_completed=value['reverse_completed'];self.optimizer_steps=value['optimizer_steps']
        self.forward_entered=value['forward_entered'];self.reverse_entered=value['reverse_entered']
    def check(self):
        if self.stop_file is not None and Path(self.stop_file).exists():raise StopBudget('STOP_REQUESTED')
        if self.guard is not None:
            try:self.guard.check()
            except RuntimeError as exc:raise StopBudget(str(exc)) from exc
        if self.clock()-self.started>=self.max_seconds:raise StopBudget('TIME_LIMIT')
        rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)
        if rss>self.max_rss:raise StopBudget('RSS_LIMIT')
    def forward(self,model,value):
        self.check()
        if self.forwards>=self.max_forwards:raise StopBudget('FORWARD_LIMIT')
        return self._invoke('forward',lambda:model(value))
    def reverse(self,kind,function):
        self.check()
        if self.backward+self.autograd>=self.max_reverse:raise StopBudget('REVERSE_LIMIT')
        return self._invoke(kind,function)
    def _invoke(self,kind,function):
        if self.ledger is not None:
            try:self.ledger.begin(kind)
            except RuntimeError as exc:raise StopBudget(str(exc)) from exc
            self._restore()
        elif kind=='forward':self.forwards+=1
        elif kind=='backward':self.backward+=1
        else:self.autograd+=1
        completed=False;entered=False
        try:
            if self.guard is not None:
                try:
                    if kind=='forward':self.guard.before_forward()
                    else:self.guard.before_backward() # includes each autograd.grad
                except RuntimeError as exc:raise StopBudget(str(exc)) from exc
            self.check();entered=True
            if self.ledger is not None:self.ledger.entered(kind)
            if kind=='forward':self.forward_entered+=1
            else:self.reverse_entered+=1
            result=function();completed=True
            if kind=='forward':self.forward_completed+=1
            else:self.reverse_completed+=1
            return result
        finally:
            if self.ledger is not None:self.ledger.end(kind,completed,entered);self._restore()
    def set_phase(self,**phase):
        self.phase.update(phase)
        if self.ledger is not None:self.ledger.phase(self.phase)
    def did_optimizer_step(self):
        if self.ledger is not None:self.ledger.optimizer_step();self._restore()
        else:self.optimizer_steps+=1
    def receipt(self):
        return dict(forward_attempts=self.forwards,forward_completed=self.forward_completed,
            forward_entered=self.forward_entered,reverse_entered=self.reverse_entered,
            loss_backward_calls=self.backward,autograd_grad_calls=self.autograd,
            total_reverse_calls=self.backward+self.autograd,reverse_completed=self.reverse_completed,
            optimizer_steps=self.optimizer_steps,elapsed_seconds=self.clock()-self.started,
            timeout_enforcement='BETWEEN_OPERATIONS; no in-flight cancellation')


def state_sha(model):
    digest=hashlib.sha256()
    for key,tensor in sorted(model.state_dict().items()):
        value=tensor.detach().cpu().contiguous();digest.update(key.encode())
        digest.update(str(value.dtype).encode());digest.update(value.numpy().tobytes())
    return digest.hexdigest()


def run_spi(model,image,valid,*,weight,steps=1000,learning_rate=.01,meter=None,
            gradient_steps=(1,100,300,1000),checkpoints=(100,300,1000),
            sink=None,checkpoint_sink=None,expected_prefix=None,expected_baseline=None):
    """Measured CPU path; callers supply already locked scalar CT preprocessing."""
    if image.ndim!=4 or image.shape[:2]!=(1,1) or not image.is_floating_point():raise ValueError('expected scalar [1,1,H,W]')
    if valid.dtype!=torch.bool or tuple(valid.shape)!=tuple(image.shape[2:]) or not valid.any():raise ValueError('invalid support')
    if image.device.type!='cpu' or valid.device.type!='cpu':raise ValueError('CPU only')
    if not torch.isfinite(image).all() or weight not in (.1,1.) or not 1<=steps<=1000 or learning_rate!=.01:raise ValueError('outside prepared trajectory')
    meter=meter or ComputeMeter();x=image.detach();before=state_sha(model)
    modes=[(m,m.training) for m in model.modules()];parameters=list(model.parameters());flags=[p.requires_grad for p in parameters]
    out=dict(algorithm='EPI-NEXT-v2-SINGLE-SCALE-SPI-CPF',status='RUNNING',grid=[7,7],mask_weight=weight,
        trace=[],candidates=[],PSMI='NOT_APPLICABLE_SINGLE_SCALE',hierarchy='NOT_RUN',best_so_far=None,
        prefix_exact_match=None,model_state_before_sha256=before)
    best=None
    try:
        model.eval()
        for p in parameters:p.requires_grad_(False)
        with torch.enable_grad():
            with torch.no_grad():baseline=meter.forward(model,x).detach()
            if baseline.shape!=(1,2) or not torch.isfinite(baseline).all():raise ValueError('invalid baseline')
            out['baseline_logits']=baseline.cpu().flatten().tolist()
            if expected_baseline is not None and out['baseline_logits']!=expected_baseline:raise ValueError('frozen baseline mismatch')
            mask=torch.nn.Parameter(torch.full((1,1,7,7),.5,dtype=x.dtype,device=x.device))
            optimizer=torch.optim.Adam([mask],lr=learning_rate,betas=(.9,.999),eps=1e-8,weight_decay=0,amsgrad=False)
            for epoch in range(steps):
                meter.set_phase(step=epoch+1)
                optimizer.zero_grad(set_to_none=True)
                retention=F.interpolate(mask,size=x.shape[2:],mode='bilinear',align_corners=False)
                logits=meter.forward(model,x*torch.where(valid[None,None],retention,torch.ones_like(retention)))
                if logits.shape!=(1,2) or not torch.isfinite(logits).all():raise ValueError('invalid masked logits')
                ls=((baseline-logits)**2).sum();lm=mask.abs().mean();loss=ls+weight*lm
                if not torch.isfinite(loss):raise ValueError('nonfinite loss')
                values,indices=torch.topk(mask.detach().flatten(),2);gap=float(values[0]-values[1])
                feasible=float(ls.detach())<.005 and float(lm.detach())<.08 and gap>0
                entry=dict(epoch=epoch,similarity=float(ls.detach()),sparsity=float(lm.detach()),peak_gap=gap,
                    feasible=feasible,logits=logits.detach().cpu().flatten().tolist())
                out['trace'].append(entry)
                if expected_prefix is not None and epoch<len(expected_prefix):
                    if entry!=expected_prefix[epoch]:raise ValueError('frozen prefix mismatch')
                if feasible and (best is None or gap>best['peak_gap']):
                    best=dict(entry,cell=int(indices[0]),mask=mask.detach().clone())
                telemetry=dict(step=epoch+1,loss=float(loss.detach()),mask_min=float(mask.detach().min()),
                    mask_max=float(mask.detach().max()),mask_mean=float(mask.detach().mean()),
                    mask_quantiles=torch.quantile(mask.detach().flatten(),mask.new_tensor([.25,.5,.75])).tolist(),
                    boundary_fraction=float(((mask.detach()==0)|(mask.detach()==1)).float().mean()),
                    optimizer_identity=id(optimizer),leaf_identity=id(mask),optimizer_param_is_forward_leaf=optimizer.param_groups[0]['params'][0] is mask,
                    mask_before=mask.detach().cpu()[0,0].tolist(),active_mask=mask.detach().cpu()[0,0].tolist(),
                    CPF_conditions=dict(similarity_pass=float(ls.detach())<.005,sparsity_pass=float(lm.detach())<.08,peak_gap_pass=gap>0))
                old=mask.detach().clone()
                if epoch+1 in gradient_steps:
                    gs=meter.reverse('autograd',lambda:torch.autograd.grad(ls,mask,retain_graph=True)[0])
                    gm=meter.reverse('autograd',lambda:torch.autograd.grad(lm,mask,retain_graph=True)[0])
                    telemetry.update(grad_ls_norm=float(gs.norm()),weighted_grad_lm_norm=float((weight*gm).norm()),
                        gradients_cosine=float((gs*gm).sum()/(gs.norm()*gm.norm()).clamp_min(1e-30)),
                        forward_graph_reaches_leaf=graph_contains_leaf(logits,mask),
                        similarity_gradient=gs.detach().cpu()[0,0].tolist(),sparsity_gradient=gm.detach().cpu()[0,0].tolist())
                meter.reverse('backward',loss.backward)
                if mask.grad is None or not torch.isfinite(mask.grad).all():raise ValueError('invalid mask gradient')
                telemetry['combined_gradient_norm']=float(mask.grad.norm())
                telemetry['combined_gradient']=mask.grad.detach().cpu()[0,0].tolist()
                meter.check();optimizer.step();meter.did_optimizer_step()
                with torch.no_grad():
                    telemetry.update(clip_below=int((mask<0).sum()),clip_above=int((mask>1).sum()),
                        mask_before_projection=mask.detach().cpu()[0,0].tolist())
                    mask.clamp_(0,1)
                telemetry.update(update_max=float((mask.detach()-old).abs().max()),
                    update_mean=float((mask.detach()-old).abs().mean()),optimizer_step=int(optimizer.state[mask]['step']),
                    mask_after_projection=mask.detach().cpu()[0,0].tolist())
                if sink is not None:sink(dict(entry,**telemetry))
                if epoch+1 in checkpoints and checkpoint_sink is not None:
                    checkpoint_sink(epoch+1,dict(mask=mask.detach().clone(),optimizer=copy.deepcopy(optimizer.state_dict()),
                        torch_rng=torch.get_rng_state().clone(),python_rng=random.getstate(),
                        numpy_rng=dict(name=np.random.get_state()[0],keys=torch.from_numpy(np.random.get_state()[1].astype(np.int64)),
                            position=np.random.get_state()[2],has_gauss=np.random.get_state()[3],cached_gauss=np.random.get_state()[4]),
                        config=dict(weight=weight,grid=[7,7],learning_rate=learning_rate,steps=steps),
                        step=epoch+1,baseline_logits=baseline.detach().clone(),
                        best_so_far=copy.deepcopy(best)))
                meter.check()
            out.update(status='OK' if best is not None else 'NO_FEASIBLE_MASK',final_mask=mask.detach().cpu()[0,0].tolist())
            if expected_prefix is not None:out['prefix_exact_match']=len(out['trace'])>=len(expected_prefix)
            if best is not None:
                patch=torch.zeros_like(mask);row,col=divmod(best['cell'],7);patch[0,0,row,col]=1
                pixels=F.interpolate(patch,size=x.shape[2:],mode='nearest')[0,0].bool()&valid
                out['candidates']=[dict(cell_yx=[row,col],selected_epoch=best['epoch'],peak_gap=best['peak_gap'],
                    mask_flat_indices=pixels.flatten().nonzero().flatten().tolist(),evidence_type='SINGLE_SCALE_CPF')]
    except StopBudget as exc:out.update(status='PARTIAL_BUDGET',reason=str(exc),CPF_selection='BEST_SO_FAR_NOT_FINAL')
    except Exception as exc:out.update(status='FAILED',reason=str(exc))
    finally:
        if 'mask' in locals():out['final_mask']=mask.detach().cpu()[0,0].tolist()
        if out['trace']:out['last_logits']=out['trace'][-1]['logits']
        if 'optimizer' in locals() and checkpoint_sink is not None and out['status'] in ('PARTIAL_BUDGET','FAILED'):
            checkpoint_sink('partial',dict(mask=mask.detach().clone(),optimizer=copy.deepcopy(optimizer.state_dict()),
                torch_rng=torch.get_rng_state().clone(),python_rng=random.getstate(),
                numpy_rng=dict(name=np.random.get_state()[0],keys=torch.from_numpy(np.random.get_state()[1].astype(np.int64)),
                    position=np.random.get_state()[2],has_gauss=np.random.get_state()[3],cached_gauss=np.random.get_state()[4]),
                step=int(optimizer.state.get(mask,{}).get('step',0)),best_so_far=copy.deepcopy(best),
                config=dict(weight=weight,grid=[7,7],learning_rate=learning_rate,steps=steps),
                reason=out.get('reason')))
        if best is not None:out['best_so_far']={k:(v.cpu()[0,0].tolist() if k=='mask' else v) for k,v in best.items()}
        for p,flag in zip(parameters,flags):p.requires_grad_(flag)
        for m,flag in modes:m.training=flag
        out['model_state_after_sha256']=state_sha(model);out['model_unchanged']=before==out['model_state_after_sha256']
        if not out['model_unchanged']:out.update(status='FAILED',reason='CLASSIFIER_STATE_CHANGED',candidates=[])
        out['cost_cumulative']=meter.receipt()
    return out


def verify_execution_lock(lock,proposal_sha):
    if (lock.get('status')!='LOCKED_FOR_E2_R1_R2_CPU_EXECUTION'
        or lock.get('proposal_sha256')!=proposal_sha or lock.get('real_model_execution_authorized') is not True):
        raise ValueError('R1/R2 preparation is not execution authorization')
    if (lock.get('resource_protection_revision_sha256')!='0000000000000000000000000000000000000000000000000000000000000000'
        or lock.get('supervision_mode')!='INTEGRATION_SHARED_SUPERVISOR'):
        raise ValueError('approved resource revision and shared supervision binding required')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('execution-lock','proposal','prepared-delivery','baseline-config','baseline-run','integration-source','output','resource-revision','dependency-root'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--lock-sha',required=True);parser.add_argument('--dependency-sha',required=True)
    args=parser.parse_args();args.worker_path=Path(__file__)
    from .first_real_e1_e2 import (locked_json,file_sha,consume_inputs,CONFIG_SHA,CHECKPOINT_SHA,
        baseline_source,DifferentiablePreparedModel,write_json,native_lookup)
    lock=locked_json(args.execution_lock,args.lock_sha);proposal_sha=file_sha(args.proposal)
    verify_execution_lock(lock,proposal_sha) # before prepared access or model loading
    if proposal_sha!='a890238732589802382f6a8cee9840f199b852a5bf6951688707c6dc555f9442':raise ValueError('runner binds only this exact R1/R2 proposal')
    proposal=locked_json(args.proposal,proposal_sha)
    if proposal.get('id')!='E2-R1-R2' or proposal.get('status')!='PREPARED_NOT_AUTHORIZATION':raise ValueError('wrong prepared proposal')
    if lock.get('max_network_forwards')!=7000 or lock.get('max_reverse_calls')!=10000 or lock.get('soft_timeout_seconds_total')!=900:raise ValueError('budget lock mismatch')
    output=args.output.resolve();allowed=Path(__file__).resolve().parents[3]/'.local'/'phase2'
    if not output.is_relative_to(allowed) or output.exists():raise ValueError('new private local output required')
    from .shared_runner_binding_v3 import bind_child,finish_child
    from .runner_ledger_v3 import CounterLedger
    guard,binding=bind_child(args,lock,proposal_sha,max_forward=7000,max_reverse=10000,seconds=900)
    meter=None;model=None;summaries=[];status='FAILED';reason=None
    try:
        allowed.mkdir(parents=True,exist_ok=True)
        write_json(allowed/'R1-R2-wave1-d9eca7166f74a1bc-attempt.json',dict(output=str(output),lock_sha256=args.lock_sha))
        output.mkdir(parents=True,exist_ok=False)
        torch.set_num_threads(1);torch.manual_seed(20261009);np.random.seed(20261009);random.seed(20261009)
        ledger=CounterLedger(output/'algorithm-counters.json',experiment_id=guard.spec.job_id,max_forwards=7000,max_reverse=10000,create=True)
        meter=ComputeMeter(guard=guard,ledger=ledger,stop_file=guard.directory/'STOP')
        write_json(output/'submission.json',dict(binding=binding,proposal_sha256=proposal_sha,lock_sha256=args.lock_sha,status='STARTED'))
        delivery,_,spec,inputs=consume_inputs(args.prepared_delivery,proposal['prepared_delivery_sha256'],args.baseline_config,CONFIG_SHA)
        baseline=locked_json(args.baseline_run,'0000000000000000000000000000000000000000000000000000000000000000')
        meter.check();adapter=baseline_source(args.integration_source)
        classifier=adapter.load_verified_resnet18(Path(delivery['checkpoint_path']),CHECKPOINT_SHA)
        model=DifferentiablePreparedModel(classifier,spec)
        for weight in (.1,1.):
            for record,p,geometry in inputs:
                folder=output/f"case-{record['case_index']}-lambda-{weight}";folder.mkdir()
                prior=next(r for r in baseline['records'] if r['case_index']==record['case_index'])
                old=locked_json(prior['result_path'],prior['result_sha256'])['E2']
                previous=next(s for s in old['stages'] if s['grid']==[7,7])
                prefix=previous['trace'] if weight==.1 else None
                checkpoint_assets=[]
                def checkpoint_sink(step,state):
                    state.update(proposal_sha256=proposal_sha,execution_lock_sha256=args.lock_sha)
                    path=folder/f'checkpoint-{step}.pt'
                    with path.open('xb') as stream:torch.save(state,stream)
                    checkpoint_assets.append(dict(step=step,path=str(path),sha256=file_sha(path)))
                before=meter.receipt()
                meter.set_phase(algorithm='E2-R1-R2',case_index=record['case_index'],weight=weight,step=0)
                with (folder/'epochs.jsonl').open('x') as stream:
                    def sink(event):stream.write(json.dumps(event,allow_nan=False)+'\n');stream.flush()
                    result=run_spi(model,torch.from_numpy(p.image.copy())[None,None],torch.from_numpy(p.valid_mask.copy()),
                        weight=weight,meter=meter,sink=sink,checkpoint_sink=checkpoint_sink,expected_prefix=prefix,
                        expected_baseline=previous['baseline_logits'] if weight==.1 else None)
                result.update(checkpoint_assets=checkpoint_assets,cost_before=before,proposal_sha256=proposal_sha,lock_sha256=args.lock_sha,
                    case_index=record['case_index'],prepared_record=record,geometry_source_sha256=record['geometry']['sha256'])
                write_json(folder/'result.json',result)
                score=np.zeros(p.image.shape);reliable=np.zeros(p.image.shape,dtype=bool)
                for candidate in result['candidates']:
                    reliable.flat[candidate['mask_flat_indices']]=True;score.flat[candidate['mask_flat_indices']]=candidate['peak_gap']
                iy,ix=native_lookup(geometry);native=folder/'single-scale-CPF-native.npz'
                with native.open('xb') as stream:np.savez_compressed(stream,scores=score[iy,ix],reliable=reliable[iy,ix],
                    native_case_manifest_sha256=np.asarray(record['native_manifest_sha256']),SOPInstanceUID=np.asarray(record['source_sop_uid']),native_slice_index=np.asarray(record['native_slice_index_zero_based']))
                summaries.append(dict(case_index=record['case_index'],weight=weight,status=result['status'],
                    result_path=str(folder/'result.json'),result_sha256=file_sha(folder/'result.json'),native_path=str(native),native_sha256=file_sha(native)))
                if result['status'] in ('PARTIAL_BUDGET','FAILED'):
                    status=result['status'];reason=result.get('reason');break
            if status in ('PARTIAL_BUDGET','FAILED') and reason is not None:break
        else:status='NO_RELIABLE_RESPONSE' if all(r['status']=='NO_FEASIBLE_MASK' for r in summaries) else 'SUCCESS'
    except StopBudget as exc:status='PARTIAL_BUDGET';reason=str(exc)
    except Exception as exc:status='FAILED';reason=str(exc)
    finally:
        from .shared_runner_binding_v3 import reconcile_counts
        cost=meter.receipt() if meter is not None else dict(forward_attempts=0,forward_entered=0,reverse_entered=0)
        actual=0 if model is None else model.classifier_calls
        try:comparison=reconcile_counts(guard,cost,actual)
        except Exception as exc:
            status='FAILED';reason='COUNTER_RECONCILIATION_FAILED: '+str(exc)
            comparison=dict(error=str(exc),reservations_equal=False)
        if status in ('SUCCESS','NO_RELIABLE_RESPONSE') and not comparison['reservations_equal']:
            status='FAILED';reason='GLOBAL_COUNTER_MISMATCH'
        try:
            if output.exists():
                write_json(output/'run_delivery.json',dict(status=status,reason=reason,cost=cost,records=summaries,
                    actual_classifier_forward_entered=actual,counter_comparison=comparison,
                    proposal_sha256=proposal_sha,lock_sha256=args.lock_sha,GT_access=False,automatic_retries=0,
                    source_sha256=file_sha(__file__),binding=binding,command=sys.argv))
        except Exception as exc:status='FAILED';reason='RESULT_WRITE_FAILED: '+str(exc)
        finally:finish_child(guard,output/'run_delivery.json',status,cost,actual_forward=actual,reason=reason)
    return 0 if status in ('SUCCESS','NO_RELIABLE_RESPONSE') else 2


if __name__=='__main__':raise SystemExit(main())
