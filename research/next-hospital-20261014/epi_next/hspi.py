"""Independent E2 SPI/CPF/PSMI reference variant, NOT author-code reproduction.

Paper: Hierarchical Salient Patch Identification for Interpretable Fundus
Disease Localization, IEEE BIBM 2024, equations 4-15 (local supplied PDF).
Eq4 compares ALL logits; target is intentionally absent from this API. Projected
Adam, reduced grids/epochs, valid-support handling and rejecting tied peaks are
explicit engineering choices. There is no GT input or pseudo-lesion claim.
"""
from dataclasses import dataclass, asdict
import math
import time
import torch
from .localization import _public_status
import torch.nn.functional as F


@dataclass(frozen=True)
class HSPIConfig:
    grids: tuple = ((4,4),(5,5),(6,6))
    stages: int = 3
    epochs: int = 100
    learning_rate: float = .01
    mask_weight: float = .1
    similarity_threshold: float = .005
    sparsity_threshold: float = .08
    min_peak_gap: float = 0.
    initial_mask: float = .5
    benchmark_scale: int = 0
    min_other_scale_support: int = 1
    max_model_calls: int | None = None
    timeout_seconds: float | None = None

    def validate(self):
        if not self.grids or len(set(self.grids)) != len(self.grids) or any(len(g)!=2 or min(g)<1 or math.prod(g)<2 for g in self.grids): raise ValueError('invalid distinct grids')
        if self.epochs < 1 or self.stages < 1: raise ValueError('invalid iteration counts')
        if not all(math.isfinite(x) for x in (self.learning_rate,self.mask_weight,self.similarity_threshold,self.sparsity_threshold,self.min_peak_gap,self.initial_mask)): raise ValueError('nonfinite config')
        if self.learning_rate <= 0 or self.mask_weight < 0 or self.similarity_threshold <= 0 or not 0 < self.sparsity_threshold <= 1 or self.min_peak_gap < 0 or not 0 < self.initial_mask < 1: raise ValueError('invalid optimization config')
        if not 0 <= self.benchmark_scale < len(self.grids) or not 0 <= self.min_other_scale_support <= len(self.grids)-1: raise ValueError('invalid PSMI setting')
        if self.max_model_calls is not None and (type(self.max_model_calls) is not int or self.max_model_calls<1):raise ValueError('invalid E2 call cap')
        if self.timeout_seconds is not None and (not math.isfinite(self.timeout_seconds) or self.timeout_seconds<=0):raise ValueError('invalid E2 timeout')


def psmi_filter(patches_by_scale, benchmark_scale, min_other_scale_support):
    """Eq13/14: one vote per OTHER scale with any overlapping patch.

    patches contain boolean native-resolution masks; a scale with many
    intersecting patches still contributes exactly one vote.
    """
    if not 0 <= benchmark_scale < len(patches_by_scale) or not 0 <= min_other_scale_support <= len(patches_by_scale)-1: raise ValueError('invalid PSMI settings')
    results=[]
    for patch in patches_by_scale[benchmark_scale]:
        votes=sum(any(bool((patch & other).any()) for other in patches)
                  for i,patches in enumerate(patches_by_scale) if i != benchmark_scale)
        results.append(dict(other_scale_support=int(votes),retained=votes>=min_other_scale_support))
    return results


def hspi_reference(model, image, config=None, valid_mask=None, clock=time.monotonic,
                   telemetry_sink=None, resource_guard=None):
    """Freeze model parameters while retaining differentiability through input.

    image [1,C,H,W]; valid_mask [H,W] bool. Unknown support returns no candidates.
    Model mode/requires_grad are restored on exit. Model must return [1,K] logits.
    """
    cfg=config or HSPIConfig(); cfg.validate()
    out=dict(algorithm='EPI-NEXT-E2-HSPI-independent-projected-Adam-v1',
             evidence_type='FULL_LOGITS_CONSISTENCY_MASK',status=None,config=asdict(cfg),
             model_calls=0,stages=[],candidates=[],optimization='PROJECTED_ADAM',
             paper_reproduction=False,variant_label='HSPI-inspired variant',elapsed_seconds=0.,
             timeout_enforcement='BETWEEN_FORWARDS',completed_scale_patches=[])
    if image.ndim != 4 or image.shape[0] != 1 or min(image.shape[2:]) < 1 or not image.is_floating_point(): raise ValueError('expected floating [1,C,H,W]')
    if not torch.isfinite(image).all(): out['status']='NUMERICAL_FAILURE'; return _public_status(out)
    if valid_mask is None: out['status']='UNKNOWN_VALID_SUPPORT'; return _public_status(out)
    if valid_mask.dtype != torch.bool or tuple(valid_mask.shape) != tuple(image.shape[2:]): raise ValueError('invalid boolean support')
    if not valid_mask.any(): out['status']='EMPTY_VALID_DOMAIN'; return _public_status(out)
    if valid_mask.device != image.device: raise ValueError('support/image device mismatch')
    x=image.detach(); valid=valid_mask[None,None]
    params=list(model.parameters()); old_grad=[p.requires_grad for p in params]
    old_modes=[(module,module.training) for module in model.modules()]
    by_scale=[]; all_patch_records=[]
    started=clock()
    class BudgetStop(Exception):pass
    def budget_reason():
        if cfg.timeout_seconds is not None and clock()-started>=cfg.timeout_seconds:return 'TIME_LIMIT'
        if cfg.max_model_calls is not None and out['model_calls']>=cfg.max_model_calls:return 'MODEL_CALL_LIMIT'
        return None
    def predict(value):
        if resource_guard is not None:resource_guard()
        reason=budget_reason()
        if reason:raise BudgetStop(reason)
        out['model_calls']+=1
        logits=model(value)
        if logits.ndim!=2 or logits.shape[0]!=1 or logits.shape[1]<2 or not torch.isfinite(logits).all(): raise ValueError('invalid classifier logits')
        return logits
    def up(mask, mode):
        return F.interpolate(mask,size=x.shape[2:],mode=mode,**({'align_corners':False} if mode=='bilinear' else {}))
    try:
        model.eval()
        for p in params: p.requires_grad_(False)
        with torch.enable_grad():
            for si,grid in enumerate(cfg.grids):
                omega=torch.ones((1,1,*grid),device=x.device,dtype=x.dtype)
                patches=[]; patch_records=[]
                for stage in range(cfg.stages):
                    trace=[]
                    stage_record=dict(scale_index=si,grid=list(grid),stage=stage+1,baseline_logits=None,trace=trace,status='RUNNING')
                    out['stages'].append(stage_record)
                    # Nearest-neighbour rigid exclusion, equation 7.
                    stage_x=torch.where(valid,x*up(omega,'nearest'),x)
                    with torch.no_grad(): baseline=predict(stage_x).detach()
                    stage_record['baseline_logits']=baseline.cpu().flatten().tolist()
                    mask=torch.nn.Parameter(torch.full_like(omega,cfg.initial_mask))
                    optimizer=torch.optim.Adam([mask],lr=cfg.learning_rate)
                    best=None
                    for epoch in range(cfg.epochs):
                        optimizer.zero_grad(set_to_none=True)
                        retention=up(omega*mask,'bilinear')
                        # Preserve invalid pixels; unknown is never invented as valid.
                        retention=torch.where(valid,retention,torch.ones_like(retention))
                        logits=predict(stage_x*retention)
                        similarity=((baseline-logits)**2).sum()  # equation 4
                        sparsity=mask.abs().mean()               # equation 5
                        loss=similarity+cfg.mask_weight*sparsity  # equation 8
                        if not torch.isfinite(loss): raise ValueError('nonfinite loss')
                        active=(omega*mask).detach().flatten()
                        values,indices=torch.topk(active,2)
                        gap=float(values[0]-values[1])
                        feasible=(float(similarity.detach())<cfg.similarity_threshold and
                                  float(sparsity.detach())<cfg.sparsity_threshold and gap>cfg.min_peak_gap)
                        entry=dict(epoch=epoch,similarity=float(similarity.detach()),sparsity=float(sparsity.detach()),peak_gap=gap,feasible=feasible,
                                   logits=logits.detach().cpu().flatten().tolist())
                        trace.append(entry)
                        if feasible and (best is None or gap>best['peak_gap']):
                            best=dict(entry,cell=int(indices[0]),mask=mask.detach().clone())
                        # Read-only gradient queries retain the graph; the original
                        # loss.backward/Adam path below remains the only update.
                        telemetry=None
                        if telemetry_sink is not None:
                            gs=(torch.autograd.grad(similarity,mask,retain_graph=True,allow_unused=True)[0]
                                if similarity.requires_grad else None)
                            if gs is None:gs=torch.zeros_like(mask)
                            gp=torch.autograd.grad(sparsity,mask,retain_graph=True)[0]
                            telemetry=dict(scale_index=si,stage=stage+1,epoch=epoch,
                                mask_before=mask.detach().cpu()[0,0].tolist(),
                                active_mask=(omega*mask).detach().cpu()[0,0].tolist(),
                                similarity_gradient=gs.detach().cpu()[0,0].tolist(),
                                sparsity_gradient=gp.detach().cpu()[0,0].tolist(),
                                similarity_gradient_norm=float(gs.norm()),
                                weighted_sparsity_gradient_norm=float((cfg.mask_weight*gp).norm()))
                        loss.backward()
                        if mask.grad is None or not torch.isfinite(mask.grad).all(): raise ValueError('invalid mask gradient')
                        if telemetry is not None:
                            telemetry.update(combined_gradient=mask.grad.detach().cpu()[0,0].tolist(),
                                combined_gradient_norm=float(mask.grad.norm()),
                                gradient_decomposition_max_error=float((mask.grad-gs-cfg.mask_weight*gp).abs().max()))
                        optimizer.step()
                        with torch.no_grad():
                            if telemetry is not None:
                                telemetry.update(projection_below_zero=int((mask<0).sum()),projection_above_one=int((mask>1).sum()),
                                    mask_before_projection=mask.detach().cpu()[0,0].tolist())
                            mask.clamp_(0,1)
                        if telemetry is not None:
                            telemetry['mask_after_projection']=mask.detach().cpu()[0,0].tolist()
                            telemetry_sink(dict(entry,**telemetry))
                        if resource_guard is not None:resource_guard()
                    if cfg.timeout_seconds is not None and clock()-started>=cfg.timeout_seconds:raise BudgetStop('TIME_LIMIT')
                    stage_record['status']='NO_FEASIBLE_MASK' if best is None else 'COMPLETE'
                    if telemetry_sink is not None:
                        stage_record['telemetry_final_mask']=mask.detach().cpu()[0,0].tolist()
                    if best is None: break
                    row,col=divmod(best['cell'],grid[1]); patch=torch.zeros_like(omega)
                    patch[0,0,row,col]=1
                    native=up(patch,'nearest')[0,0].bool() & valid_mask
                    if not native.any(): stage_record['status']='EMPTY_VALID_DOMAIN'; break
                    record=dict(scale_index=si,grid=list(grid),stage=stage+1,cell_yx=[row,col],
                                selected_epoch=best['epoch'],similarity=best['similarity'],
                                sparsity=best['sparsity'],peak_gap=best['peak_gap'],
                                learned_mask=best['mask'].cpu()[0,0].tolist(),
                                mask_flat_indices=native.flatten().nonzero().flatten().cpu().tolist(),
                                evidence_type='FULL_LOGITS_CONSISTENCY_MASK')
                    stage_record['selected']=record
                    out['completed_scale_patches'].append(record)
                    patches.append(native); patch_records.append(record)
                    omega[0,0,row,col]=0
                by_scale.append(patches); all_patch_records.append(patch_records)
        selection=psmi_filter(by_scale,cfg.benchmark_scale,cfg.min_other_scale_support)
        for record,vote in zip(all_patch_records[cfg.benchmark_scale],selection):
            record.update(vote)
            if vote['retained']: out['candidates'].append(record)
        out['psmi_selection']=selection
        out['status']='COMPLETE' if out['candidates'] else ('NO_FEASIBLE_MASK' if not any(by_scale) else 'NO_MULTISCALE_SUPPORT')
    except BudgetStop as exc:
        out.update(status='PARTIAL_BUDGET',reason=str(exc),psmi_status='NOT_FINALIZED_INCOMPLETE_OPTIMIZATION')
    except Exception as exc:
        out['status']='NUMERICAL_FAILURE' if isinstance(exc,ValueError) else 'MODEL_FAILURE';out['error']=str(exc)
    finally:
        out['elapsed_seconds']=clock()-started
        for stage_record in out['stages']:
            if stage_record['status']=='RUNNING':stage_record.update(status=out['status'],reason=out.get('reason',out['status']))
        for p,flag in zip(params,old_grad): p.requires_grad_(flag)
        for module,flag in old_modes: module.training=flag
    return _public_status(out)
