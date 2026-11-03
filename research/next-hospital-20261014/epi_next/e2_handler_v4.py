"""In-memory 2D E2 handler; LOC owns algorithms, INT owns job/IO/dispatch.

No CT/GT/checkpoint loader, lease, model training or hidden dimension adapter.
P1 reuse imports a verified terminal selection, never a cross-config optimizer.
"""
from dataclasses import asdict
import hashlib
import json
import time

import numpy as np
import torch

from .hspi_core_v3 import (Budget, HSPIConfig, optimize_stage, psmi, cell_patch,
                          source_sha, frozen_classifier, upsample, BudgetStopped)
from .first_real_e1_e2 import native_lookup

SEMANTIC_KEYS=('mode','image_size','steps','zeta','lr','lam','alpha','beta','adam_betas',
               'adam_eps','align_corners','adapter_policy','masking_policy','tie_policy')


def plain(value):
    if torch.is_tensor(value):return value.detach().cpu().tolist()
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,dict):return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [plain(v) for v in value]
    return value


def digest(value):
    return hashlib.sha256(json.dumps(plain(value),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def semantics(config):
    return {k:plain(asdict(config)[k]) for k in SEMANTIC_KEYS}


def input_binding(prepared,identity):
    return {'input_sha256':prepared.input_sha256,
        'valid_sha256':hashlib.sha256(np.ascontiguousarray(prepared.valid_mask).tobytes()).hexdigest(),
        **{k:identity[k] for k in ('model_sha256','preprocessing_sha256','model_adapter_sha256')}}


def check_input(prepared,config,identity,allow_real):
    prepared.validate();config.validate()
    if prepared.scope!='SYNTHETIC' and not allow_real:raise ValueError('BLOCKED_REAL_CALL_REQUIRES_INT_DISPATCH')
    if identity.get('classifier_kind')!='2D_SLICE_CLASSIFIER':raise ValueError('EXPLICIT_2D_CLASSIFIER_REQUIRED')
    if config.mode!='E2-CT' or config.masking_policy!='preserve_exterior':raise ValueError('EXPLICIT_CT_MASK_POLICY_REQUIRED')
    if prepared.image.dtype!=np.float32 or tuple(prepared.image.shape)!=config.image_size:
        raise ValueError('EXACT_SCALAR_FLOAT32_MODEL_GRID_REQUIRED')
    input_binding(prepared,identity)
    if torch.is_inference_mode_enabled():raise ValueError('MASK_OPTIMIZATION_CANNOT_USE_INFERENCE_MODE')


def import_stage1(payload,prepared,config,identity):
    """Fail closed before any calls; immutable payload SHA is bound by caller."""
    if (payload.get('schema')!='E2_VERIFIED_STAGE1_REUSE_V4'
            or identity.get('reused_stage1_sha256')!=digest(payload)
            or payload.get('input_binding')!=input_binding(prepared,identity)
            or payload.get('branch_semantics')!=semantics(config)
            or payload.get('core_sha256')!=source_sha()
            or payload.get('verification')!='FULL_TRACE_CPF_AND_SAME_STEP_MASK_VERIFIED'
            or payload.get('observed_iterations')!=config.steps
            or payload.get('optimizer_updates')!=config.steps
            or payload.get('grid')!=7 or 7 not in config.grids
            or not 0<=payload.get('feasible_count',-1)<=config.steps):
        raise ValueError('INCOMPATIBLE_STAGE1_REUSE_NO_FRESH_FALLBACK')
    baseline=np.asarray(payload['baseline_logits'])
    if baseline.shape!=(1,2) or not np.isfinite(baseline).all():raise ValueError('REUSED_BASELINE_INVALID')
    best=payload['best'];omega=torch.ones(1,1,7,7);after=omega.clone();patch=None;cell=None
    if best is not None:
        best=dict(best);mask=torch.tensor(best['mask'],dtype=torch.float32)
        if (tuple(mask.shape)!=(1,1,7,7) or not bool(torch.isfinite(mask).all())
                or bool((mask<0).any()) or bool((mask>1).any())
                or not (best['ls']<config.alpha and best['lm']<config.beta)):
            raise ValueError('REUSED_SELECTION_INVALID')
        best['mask']=mask;cell=int(mask.flatten().argmax());after.flatten()[cell]=0
        ordered=mask.flatten().sort(descending=True).values
        if (abs(float(mask.abs().mean())-best['lm'])>1e-7
                or abs(float(ordered[0]-ordered[1])-best['gap'])>1e-7
                or not 1<=best['epoch']<=config.steps or payload['feasible_count']<1):
            raise ValueError('REUSED_MASK_METRICS_MISMATCH')
        patch=cell_patch(7,cell,config.image_size)
    elif payload['feasible_count']!=0:raise ValueError('REUSED_EMPTY_CPF_MISMATCH')
    return {'grid':7,'stage':1,'status':'SELECTED' if best else 'NO_FEASIBLE_MASK',
        'baseline_logits':payload['baseline_logits'],'residual_class':int(np.argmax(payload['baseline_logits'])),
        'observed_iterations':config.steps,'completed_steps':config.steps,'optimizer_updates':config.steps,
        'feasible_count':payload['feasible_count'],'best':best,'best_is_full_plan':True,
        'cell':cell,'patch':patch,'omega_before':omega,'omega_after':after,'error':None,
        'origin':'REUSED_VERIFIED_P1_STAGE1','source_reuse_sha256':digest(payload)}


def trace_record(row):
    row=dict(row);mask=np.asarray(row.pop('mask'),dtype=np.float32).reshape(-1)
    order=np.argsort(-mask,kind='stable')
    row.update(top1cell=int(order[0]),top2cell=int(order[1]),
               top1value=float(mask[order[0]]),top2value=float(mask[order[1]]))
    return row


class Checked2D(torch.nn.Module):
    def __init__(self,model):
        super().__init__();self.model=model
    def forward(self,x):
        result=self.model(x)
        if tuple(result.shape)!=(1,2):raise ValueError('EXACT_BINARY_SLICE_LOGITS_REQUIRED')
        return result


class BranchBudget:
    """One delegated meter, additional cooperative branch deadline, no counters."""
    def __init__(self,parent,seconds):
        if seconds is not None and (not np.isfinite(seconds) or seconds<0):
            raise ValueError('INVALID_BRANCH_SECONDS')
        self.parent=parent;self.seconds=seconds;self.started=parent.clock()
    @property
    def reason(self):return self.parent.reason
    @reason.setter
    def reason(self,value):self.parent.reason=value
    def permits(self,forwards=0,backwards=0):
        if self.seconds is not None and self.parent.clock()-self.started>=self.seconds:
            self.reason='BRANCH_TIMEOUT'
        return self.parent.permits(forwards,backwards)
    def forward_call(self,fn):return self.parent.forward_call(fn)
    def backward_call(self,fn):return self.parent.backward_call(fn)
    def did_optimizer_step(self):return self.parent.did_optimizer_step()
    def counts(self):return self.parent.counts()


def cost_delta(before,after):
    return {**after,**{k:after[k]-before[k] for k in
        ('forward','backward','extra_autograd','optimizer_steps','elapsed_seconds')}}


def bbox(mask):
    yy,xx=np.nonzero(mask)
    return None if not len(yy) else [int(yy.min()),int(yy.max()+1),int(xx.min()),int(xx.max()+1)]


def run_prepared_e2(prepared,model,geometry,config,*,identity,budget=None,reused_stage1=None,
                    trace_sink=None,stage_sink=None,checkpoint_sink=None,allow_real=False,
                    branch_seconds=None):
    """Actual shared optimizer->CPF->hierarchy->PSMI->native pipeline.

    Fresh run only. Checkpoints permit preservation, not an automatic retry.
    Reuse incompatibility/invalid input raises before model entry; INT maps errors.
    Arrays are returned in memory; INT persists with its bounded atomic writer.
    """
    check_input(prepared,config,identity,allow_real)
    if allow_real and budget is None:raise ValueError('REAL_CALL_REQUIRES_EXTERNAL_METER')
    if any(t.device.type!='cpu' for t in [*model.parameters(),*model.buffers()]):
        raise ValueError('V4_CPU_ONLY_ADAPTER')
    iy,ix=native_lookup(geometry) # Geometry failure is pre-call.
    if tuple(geometry['model_shape_yx'])!=config.image_size:raise ValueError('GEOMETRY_MODEL_GRID_MISMATCH')
    imported=None if reused_stage1 is None else import_stage1(reused_stage1,prepared,config,identity)
    budget=Budget() if budget is None else budget
    before=budget.counts();model=Checked2D(model)
    x=torch.from_numpy(prepared.image.copy())[None,None]
    valid=torch.from_numpy(prepared.valid_mask.copy())
    stages=[];skipped=[];stop=None
    stage_identity=digest({'input':input_binding(prepared,identity),'config':config.sha256()})
    for grid in config.grids:
        omega=torch.ones(1,1,grid,grid);first=1
        if grid==7 and imported is not None:
            stages.append(imported);omega=imported['omega_after'].clone();first=2
            if stage_sink is not None:
                stage_sink(plain({k:v for k,v in imported.items() if k!='patch'}))
            if imported['best'] is None:
                skipped.extend({'grid':grid,'stage':j,'reason':'REUSED_STAGE1_NO_FEASIBLE_MASK'} for j in range(2,config.stages+1))
                continue
        for stage in range(first,config.stages+1):
            emit=None if trace_sink is None else lambda row:trace_sink(trace_record(row))
            save=None if checkpoint_sink is None else lambda cp:checkpoint_sink(grid,stage,cp)
            result=optimize_stage(model,x,omega,config,grid=grid,stage=stage,identity=stage_identity,
                budget=BranchBudget(budget,branch_seconds),valid=valid,record_history=False,include_masks=True,trace_sink=emit,
                checkpoint_sink=save,checkpoint_every=1000)
            result['origin']='NEW_OPTIMIZATION';stages.append(result)
            if stage_sink is not None:
                stage_sink(plain({k:v for k,v in result.items() if k not in ('checkpoint','history','patch')}))
            if result['status'] in ('FAILED','PARTIAL_BUDGET'):
                stop=result['status'];break
            omega=result['omega_after'].clone()
            if result['status']=='NO_FEASIBLE_MASK':
                skipped.extend({'grid':grid,'stage':j,'reason':'PRIOR_NO_FEASIBLE_MASK'} for j in range(stage+1,config.stages+1))
                break
        if stop:break
    observed={(s['grid'],s['stage']) for s in stages}|{(s['grid'],s['stage']) for s in skipped}
    unrun=[{'grid':g,'stage':j,'reason':'NOT_REACHED_AFTER_STOP'} for g in config.grids for j in range(1,config.stages+1) if (g,j) not in observed]
    full_plan=stop is None and not skipped and not unrun
    support=psmi(stages,config,complete=full_plan)
    if stop is not None:
        support['observed_status']=support['status'];support['status']='PARTIAL_VOTES'
    scores=np.zeros(config.image_size,dtype=np.float32);reliable=np.zeros(config.image_size,dtype=bool);candidates=[]
    refs=[s for s in stages if s['grid']==config.reference_grid and s.get('patch') is not None]
    for stage,vote in zip(refs,support['votes']):
        if vote['retained']:
            region=stage['patch'].cpu().numpy()&prepared.valid_mask
            scores[region]=np.maximum(scores[region],stage['best']['gap']);reliable|=region
            native=region[iy,ix]
            if region.any() and native.any():
                candidates.append({'grid':stage['grid'],'stage':stage['stage'],'cell':stage['cell'],
                    'selected_epoch':stage['best']['epoch'],'response':stage['best']['gap'],
                    'response_kind':'CPF_TOP1_TOP2_MASK_GAP','peak_tie':stage['best']['gap']==0,
                    'votes':vote,'provisional':stop is not None,
                    'model_bounds_yx_half_open':bbox(region),'native_bounds_yx_half_open':bbox(native),
                    'model_mask':region,'native_mask':native,'native_pixels':int(native.sum())})
    status=stop or ('SUCCESS' if reliable.any() else 'NO_RELIABLE_RESPONSE')
    original=next((s['baseline_logits'] for s in stages if s['stage']==1 and s['baseline_logits'] is not None),None)
    masks=[]
    for s in stages:
        if s['best'] is None:continue
        m=upsample(s['best']['mask'],config.image_size,'bilinear',config.align_corners)[0,0].cpu().numpy()
        q=upsample(s['omega_before']*s['best']['mask'],config.image_size,'bilinear',config.align_corners)[0,0].cpu().numpy()
        q=np.where(prepared.valid_mask,q,np.float32(1.))
        masks.append({'grid':s['grid'],'stage':s['stage'],'selected_epoch':s['best']['epoch'],
            'layer_type':'OPTIMIZED_INPUT_MASK','model_values':q,'native_values':q[iy,ix],
            'parameter_m_model_values':m,'parameter_m_native_values':m[iy,ix],
            'meaning':'Q=bilinear(Omega*M), outside valid support 1; multiplies residual X_ij. M parameter separately preserved; NOT final patch support'})
    return {'schema':'EPI_NEXT_E2_HANDLER_V4','execution_status':status,'evidence_type':identity.get('evidence_type'),
        'method':'E2-CT_HSPI_INSPIRED_CT_ADAPTER','config_sha256':config.sha256(),'core_sha256':source_sha(),
        'input_binding':input_binding(prepared,identity),'original_logits':original,
        'original_class':None if original is None else int(np.argmax(original)),
        'stages':plain([{k:v for k,v in s.items() if k not in ('checkpoint','history','patch')} for s in stages]),
        'planned_branches':len(config.grids)*config.stages,'full_plan_completed':full_plan,
        'termination_policy_completed':stop is None,'skipped_branches':skipped,'unrun_branches':unrun,
        'psmi':plain({k:v for k,v in support.items() if k not in ('patches','sum_map')}),
        'votes_finalized':stop is None,'candidate_provisional':stop is not None,
        'model_space':{'scores':scores,'reliable':reliable},'native_space':{'scores':scores[iy,ix],'reliable':reliable[iy,ix],
            'native_slice_index':geometry['native_slice_index_zero_based']},
        'psmi_whole_patch_support':{'model_values':support['sum_map'].numpy()>0,
            'native_values':support['sum_map'].numpy()[iy,ix]>0,
            'meaning':'unclipped union of whole retained reference patches; model/native reliable display separately intersects valid_support'},
        'score_semantics':'CPF continuous Mask top1-top2 gap, NOT lesion probability',
        'optimized_input_masks':masks,'new_cost':cost_delta(before,budget.counts()),
        'candidates':candidates,
        'cumulative_meter_cost':budget.counts(),'reused_historical_observations':0 if imported is None else config.steps,
        'clinical_validity':'NOT_ESTABLISHED'}


def selected_fidelity(prepared,model,config,payload,*,identity,budget=None,allow_real=False):
    """Five prospective no-gradient forwards, fixed scalar-zero fill/objects."""
    check_input(prepared,config,identity,allow_real)
    if allow_real and budget is None:raise ValueError('REAL_CALL_REQUIRES_EXTERNAL_METER')
    stage=import_stage1(payload,prepared,config,identity)
    if stage['best'] is None:raise ValueError('NO_SELECTED_MASK_FOR_FIDELITY')
    budget=Budget() if budget is None else budget
    x=torch.from_numpy(prepared.image.copy())[None,None];v=torch.from_numpy(prepared.valid_mask.copy())[None,None]
    soft=upsample(stage['best']['mask'],config.image_size,'bilinear',config.align_corners)
    hard=stage['patch'][None,None]
    masks={'original':torch.ones_like(x),'full_mask_keep':soft,'peak_patch_keep':hard,
           'full_mask_remove':1-soft,'peak_patch_remove':~hard}
    responses={};status='SUCCESS'
    with frozen_classifier(model),torch.no_grad():
        for name,mask in masks.items():
            if not budget.permits(forwards=1):status='PARTIAL_BUDGET';break
            try:out=budget.forward_call(lambda: model(torch.where(v,x*mask,x))).detach()
            except BudgetStopped:status='PARTIAL_BUDGET';break
            except Exception as exc:
                return {'schema':'E2_SELECTED_FIDELITY_V4','status':'FAILED',
                    'error':{'type':type(exc).__name__,'message':str(exc)},'responses':responses,'cost':budget.counts()}
            if tuple(out.shape)!=(1,2) or not bool(torch.isfinite(out).all()):status='FAILED';break
            responses[name]={'logits':out.cpu().tolist()}
        if status=='SUCCESS' and not budget.permits():status='PARTIAL_BUDGET'
    if 'original' in responses:
        base=np.asarray(responses['original']['logits']);target=int(base.argmax());other=1-target
        for response in responses.values():
            logits=np.asarray(response['logits']);p=np.exp(logits-logits.max());p/=p.sum()
            response.update(fixed_target=target,all_logits_squared_difference=float(((base-logits)**2).sum()),
                target_logit_margin=float(logits[0,target]-logits[0,other]),target_probability=float(p[0,target]))
    return {'schema':'E2_SELECTED_FIDELITY_V4','status':status,'selected_epoch':stage['best']['epoch'],
        'selected_cell':stage['cell'],'fill':'0 in prepared scalar domain BEFORE frozen normalization; preserve exterior valid_support',
        'responses':responses,'cost':budget.counts(),'GT_selection':False,'clinical_validity':'NOT_ESTABLISHED'}
