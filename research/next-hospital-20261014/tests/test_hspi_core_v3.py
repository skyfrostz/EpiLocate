"""Generated inputs only. Selector oracles are distinct from optimization tests."""
import copy
from dataclasses import replace
import pytest
import torch
from torch import nn
from epi_next.hspi_core_v3 import (HSPIConfig, Budget, cpf_select, peak_gap, psmi,
    cell_patch, upsample, spi_inputs, losses, optimize_stage, run_hspi, adopt_wave1_checkpoint)

torch.set_num_threads(1)

class Peaks(nn.Module):
    def __init__(self, positions=((7,7),(75,75))):
        super().__init__(); self.positions=positions
    def forward(self,x):
        s=torch.stack([x[:,0,y,z] for y,z in self.positions],dim=1).amax(dim=1).clamp(0,1)
        return torch.stack((s,torch.zeros_like(s)),dim=1)

def config(**kw):
    return replace(HSPIConfig(image_size=(84,84), grids=(5,6,7), stages=2,
                              steps=180, reference_grid=5, epsilon=2), **kw)

def image():
    x=torch.zeros(1,1,84,84); x[0,0,7,7]=3; x[0,0,75,75]=2
    return x


def test_full_profile_expressible_and_invalid_votes_rejected():
    c=HSPIConfig().validate()
    assert c.worst_cost()==dict(baseline_forward=150,mask_forward=1500000,
                               forward=1500150,backward=1500000,extra_autograd=0,optimizer_steps=1500000)
    with pytest.raises(ValueError): config(epsilon=3).validate()
    with pytest.raises(ValueError): config(mode='E2-REF',masking_policy='preserve_exterior').validate()
    assert config(grids=(5,),reference_grid=5,epsilon=0).validate()


def test_formula_oracle_double_omega_full_logits_coarse_denominator():
    c=config(image_size=(11,13),grids=(3,),reference_grid=3,epsilon=0)
    m=torch.tensor([.9,.8,.1,.1,.5,.2,.2,.1,.3]).reshape(1,1,3,3)
    o=torch.ones_like(m); o.flatten()[0]=0
    x=torch.ones(1,1,11,13)
    residual, masked=spi_inputs(x,o,m,c)
    assert torch.equal(residual,upsample(o,(11,13),'nearest'))
    assert torch.equal(masked,upsample(o*m,(11,13),'bilinear')*residual)
    assert not torch.allclose(masked,upsample(o,(11,13),'bilinear')*upsample(m,(11,13),'bilinear')*residual)
    ls,lm,_=losses(torch.tensor([[1.,2.,3.]]),torch.tensor([[0.,0.,0.]]),m,c)
    assert ls==14 and lm==m.mean()
    assert not torch.isclose(lm,upsample(m,(11,13),'bilinear').mean(),atol=1e-7)
    raw=torch.tensor([.9,.8,.1,.1]); omega=torch.tensor([0.,1.,1.,1.])
    assert peak_gap(raw)==pytest.approx(.1)
    assert peak_gap(raw*omega)==pytest.approx(.7)


def test_cpf_entire_feasible_set_no_gap_gate_strict_ties():
    rows=[dict(epoch=1,ls=.001,lm=.07,gap=0),dict(epoch=2,ls=.001,lm=.07,gap=.3),
          dict(epoch=3,ls=.001,lm=.07,gap=.3),dict(epoch=4,ls=.005,lm=.07,gap=.9),
          dict(epoch=5,ls=.001,lm=.08,gap=.95)]
    assert cpf_select(rows,.005,.08)['epoch']==2
    assert cpf_select(rows[:1],.005,.08)['epoch']==1
    assert cpf_select(rows[3:],.005,.08) is None


def test_psmi_cross_stage_whole_patch_duplicate_scale_equality_and_no_overlap():
    c=config(image_size=(11,13),grids=(3,4,5),reference_grid=3,epsilon=2)
    q=torch.zeros(11,13,dtype=torch.bool); q[:4,:4]=True
    tiny=torch.zeros_like(q);tiny[3,3]=True
    far=torch.zeros_like(q);far[4,4]=True
    stages=[dict(grid=3,stage=1,patch=q),dict(grid=4,stage=2,patch=tiny),
            dict(grid=4,stage=1,patch=tiny),dict(grid=5,stage=2,patch=tiny)]
    r=psmi(stages,c)
    assert r['votes'][0]['votes']==2
    assert torch.equal(r['patches'][0],q) and torch.equal(r['sum_map'],q.long())
    assert not psmi(stages[:-1],c)['patches']
    assert not psmi([stages[0],dict(grid=4,stage=1,patch=far),dict(grid=5,stage=1,patch=far)],c)['patches']


def test_nondivisible_nearest_cells_partition_and_adjacent_boundaries():
    masks=[cell_patch(3,i,(11,13)) for i in range(9)]
    assert torch.equal(torch.stack(masks).sum(0),torch.ones(11,13,dtype=torch.int64))
    assert not bool(torch.any(masks[0]&masks[1]))
    # PyTorch nearest uses floor(output_coordinate*input_size/output_size).
    for y in range(11):
        for x in range(13):
            assert masks[(y*3//11)*3+x*3//13][y,x]


def test_known_feasible_witness_before_autonomous_chain():
    c=config(); x=image(); model=Peaks()
    # Analytic witness BEFORE optimizer: one coarse cell; bilinear weight at
    # pixel7 is 1-u (or clamped1). Both independent peaks saturate logits1.
    for grid in c.grids:
        u=max(0,(7+.5)*grid/84-.5)
        for amplitude,cell in ((3,0),(2,grid*grid-1)):
            score=min(1,amplitude*(1-u)**2)
            assert (1-score)**2<c.alpha and 1/(grid*grid)<c.beta
    r=run_hspi(model,x,c,identity='generated-two-peaks')
    assert r['status']=='COMPLETED' and r['full_plan_completed']
    assert r['psmi']['status']=='SUPPORTED' and len(r['psmi']['patches'])==2
    for grid in c.grids:
        a,b=[s for s in r['stages'] if s['grid']==grid]
        assert a['cell']==0 and b['cell']==grid*grid-1
        assert a['baseline_logits']==b['baseline_logits']==[[1.,0.]]
        assert a['patch'][7,7] and b['patch'][75,75]
        assert a['feasible_count'] and b['feasible_count']
        best=max((row for row in a['history'] if row['feasible']),key=lambda row:(row['gap'],-row['epoch']))
        assert a['best']['epoch']==best['epoch']
    assert r['cost']['forward']==1086 and r['cost']['backward']==1080


def test_dependency_moves_autonomous_candidate():
    c=config(grids=(5,),reference_grid=5,epsilon=0,stages=1)
    x=image()
    left=run_hspi(Peaks(((7,7),)),x,c,identity='left-dependency')
    right=run_hspi(Peaks(((75,75),)),x,c,identity='right-dependency')
    assert left['stages'][0]['cell']==0 and right['stages'][0]['cell']==24


class Distributed(nn.Module):
    def forward(self,x):
        s=x.mean((1,2,3));return torch.stack([s,torch.zeros_like(s)],dim=1)


def test_distributed_no_feasible_preserves_unrun_denominators():
    c=config(image_size=(28,28),grids=(7,8,9),reference_grid=7)
    r=run_hspi(Distributed(),torch.ones(1,1,28,28),c,identity='distributed')
    assert r['status']=='NO_RELIABLE_RESPONSE'
    assert all(s['status']=='NO_FEASIBLE_MASK' for s in r['stages'])
    assert len(r['skipped_branches'])==3 and r['completed_branches']==3
    assert r['termination_policy_completed'] and not r['full_plan_completed']
    assert not r['psmi']['complete']


class Constant(nn.Module):
    def forward(self,x):
        s=x.sum((1,2,3))*0;return torch.stack([s,s],dim=1)


def test_tie_policy_does_not_add_gate_or_hide_repeated_exclusion():
    c=config(grids=(5,),reference_grid=5,epsilon=0,steps=70)
    r=run_hspi(Constant(),image(),c,identity='constant-tie')
    assert all(s['best']['gap']==0 and s['cell']==0 for s in r['stages'])
    assert r['stages'][1]['repeated_exclusion']


def test_full_stage_and_run_resume_exact_no_extra_baseline():
    c=config(steps=70)
    x=image();full=run_hspi(Peaks(),x,c,identity='resume')
    prefix=run_hspi(Peaks(),x,c,identity='resume',budget=Budget(max_backward=35))
    assert prefix['status']=='PARTIAL_BUDGET' and prefix['cost']['forward']==36
    assert prefix['stages'][0]['observed_iterations']==prefix['stages'][0]['optimizer_updates']==35
    restored=run_hspi(Peaks(),x,c,identity='resume',resume=prefix['checkpoint'])
    assert restored['status']==full['status']
    for a,b in zip(full['stages'],restored['stages']):
        assert a['history']==b['history']
        assert torch.equal(a['checkpoint']['mask'],b['checkpoint']['mask'])
        assert a['cell']==b['cell']
    assert prefix['cost']['forward']+restored['cost']['forward']==full['cost']['forward']
    assert prefix['cost']['backward']+restored['cost']['backward']==full['cost']['backward']
    with pytest.raises(ValueError):run_hspi(Peaks(),x+1,c,identity='resume',resume=prefix['checkpoint'])


def test_forward_crosses_deadline_preserves_pending_no_backward_and_replay():
    clock=[0.]
    class Slow(Peaks):
        def forward(self,x):
            clock[0]+=5
            return super().forward(x)
    c=config(grids=(5,),reference_grid=5,epsilon=0,stages=1,steps=4)
    b=Budget(seconds=8,clock=lambda:clock[0])
    p=run_hspi(Slow(),image(),c,identity='slow-generated',budget=b)
    assert p['status']=='PARTIAL_BUDGET' and p['cost']['forward']==2 and p['cost']['backward']==0
    assert p['stages'][0]['observed_iterations']==1 and p['stages'][0]['optimizer_updates']==0
    assert p['checkpoint']['active']['pending_observation']['epoch']==1
    r=run_hspi(Slow(),image(),c,identity='slow-generated',resume=p['checkpoint'])
    f=run_hspi(Slow(),image(),c,identity='slow-generated')
    assert r['stages'][0]['history']==f['stages'][0]['history']
    assert r['stages'][0]['observed_forward_replays_this_invocation']==1
    assert r['cost']['forward']==4 and r['cost']['backward']==4


def test_checkpoint_cadence_before_deepcopy_and_streaming():
    c=config(grids=(5,),reference_grid=5,epsilon=0,stages=1,steps=70)
    checkpoints=[];rows=[]
    optimize_stage(Peaks(),image(),torch.ones(1,1,5,5),c,grid=5,stage=1,identity='cadence',
        checkpoint_every=25,checkpoint_steps=(10,),record_history=False,
        checkpoint_sink=lambda cp:checkpoints.append(cp['completed_steps']),trace_sink=rows.append)
    assert checkpoints==[10,25,50,70] and len(rows)==70


def test_classifier_modes_flags_buffers_grads_restored_and_mask_grad_enabled():
    model=nn.Sequential(nn.BatchNorm2d(1),nn.Flatten(),nn.Linear(84*84,2))
    model.train();model[0].eval();model[2].weight.requires_grad_(False)
    states=copy.deepcopy(model.state_dict());flags=[p.requires_grad for p in model.parameters()]
    modes=[m.training for m in model.modules()]
    c=config(grids=(5,),reference_grid=5,epsilon=0,stages=1,steps=3)
    with torch.no_grad():r=run_hspi(model,image(),c,identity='BN-freeze')
    assert r['cost']['optimizer_steps']==3
    assert modes==[m.training for m in model.modules()]
    assert flags==[p.requires_grad for p in model.parameters()]
    assert all(torch.equal(states[k],model.state_dict()[k]) for k in states)
    assert all(p.grad is None for p in model.parameters())


def test_failure_retains_error_cost_and_freeze_state():
    class Bad(nn.Module):
        def forward(self,x):return torch.full((1,2),float('nan'))
    m=Bad();m.train()
    r=run_hspi(m,image(),config(),identity='bad-generated')
    assert r['status']=='FAILED' and r['cost']['forward']==1
    assert r['stages'][0]['error']['type']=='FloatingPointError' and m.training
    assert not r['full_plan_completed'] and not r['psmi']['complete']


def test_wave1_optimizer_continuity_on_generated_model_only():
    from epi_next.spi_recovery_v2 import run_spi
    torch.manual_seed(10)
    x=torch.rand(1,1,28,28);valid=torch.zeros(28,28,dtype=torch.bool);valid[3:25,3:25]=True
    saved={};rows=[]
    old=run_spi(Distributed(),x,valid,weight=1.,steps=60,gradient_steps=(),checkpoints=(60,),
                sink=rows.append,checkpoint_sink=lambda n,cp:saved.update({n:cp}))
    c=config(mode='E2-CT',image_size=(28,28),grids=(7,),reference_grid=7,epsilon=0,
             stages=1,steps=100,masking_policy='preserve_exterior',
             adapter_policy='W1 scalar CT domain; outside valid support retained; f includes normalization')
    provenance={k:'a'*64 for k in ('checkpoint_sha256','source_sha256','input_sha256',
                'model_sha256','preprocessing_sha256','execution_lock_sha256')}
    cp=adopt_wave1_checkpoint(saved[60],rows,x,valid,c,identity='generated-W1-continuity',
                             provenance=provenance,expected_baseline=old['baseline_logits'])
    restored=optimize_stage(Distributed(),x,torch.ones(1,1,7,7),c,grid=7,stage=1,
                           identity='generated-W1-continuity',resume=cp,valid=valid)
    full_rows=[]
    full=run_spi(Distributed(),x,valid,weight=1.,steps=100,gradient_steps=(),checkpoints=(),sink=full_rows.append)
    assert restored['status']=='NO_FEASIBLE_MASK'
    assert restored['history'][60:]==[{ 'grid':7,'stage':1,'epoch':r['epoch']+1,
          'ls':r['similarity'],'lm':r['sparsity'],'gap':r['peak_gap'],
          'loss':r['loss'], 'logits':[r['logits']],
          'feasible':r['similarity']<.005 and r['sparsity']<.08} for r in full_rows[60:]]
    assert torch.equal(restored['checkpoint']['mask'][0,0],torch.tensor(full['final_mask']))
    with pytest.raises(ValueError):adopt_wave1_checkpoint(saved[60],rows,x,valid,
        replace(c,mode='E2-REF'),identity='generated-W1-continuity',provenance=provenance,
        expected_baseline=old['baseline_logits'])


def test_existing_meter_hook_counts_partial_and_guard_before_backward():
    from epi_next.spi_recovery_v2 import ComputeMeter
    from epi_next.hspi_profile_v3 import MeterBudget, refuse_execution
    meter=ComputeMeter(max_forwards=5,max_reverse=10)
    r=run_hspi(Peaks(),image(),config(),identity='meter-seam',budget=MeterBudget(meter))
    assert r['status']=='PARTIAL_BUDGET' and meter.forwards==5 and meter.backward==4
    assert meter.optimizer_steps==4 and meter.forward_completed==5
    assert r['cost']['meter_receipt']['forward_entered']==5
    clock=[0.]
    class Slow(Peaks):
        def forward(self,x):clock[0]+=5;return super().forward(x)
    timed=ComputeMeter(max_seconds=8,clock=lambda:clock[0])
    r=run_hspi(Slow(),image(),config(),identity='timed-meter',budget=MeterBudget(timed))
    assert r['status']=='PARTIAL_BUDGET' and timed.backward==0 and timed.forwards==2
    assert r['stages'][0]['observed_iterations']==1
    with pytest.raises(ValueError,match='UNKNOWN'):refuse_execution(slot_status='UNKNOWN')
    with pytest.raises(ValueError,match='APPROVAL'):refuse_execution(slot_status='RECOVERED')
    with pytest.raises(ValueError,match='NOT_IMPLEMENTED'):refuse_execution(execution_lock={},slot_status='RECOVERED')


def test_independent_bilinear_numeric_oracle_and_finite_difference_mask_gradient():
    # Independent align_corners=False, border clamp. No interpolate/upsample in
    # the expected-value construction, for a non-divisible 3x3 -> 5x7 grid.
    import math
    c=config(image_size=(5,7),grids=(3,),reference_grid=3,epsilon=0)
    mask=torch.tensor([.2,.7,.4,.8,.3,.6,.5,.9,.1],dtype=torch.float64).reshape(1,1,3,3).requires_grad_()
    omega=torch.ones_like(mask);omega[0,0,0,0]=0
    x=torch.arange(35,dtype=torch.float64).reshape(1,1,5,7)/35+.1
    def scalar_soft(values,y,z):
        yy=max(0,min(2,(y+.5)*3/5-.5));zz=max(0,min(2,(z+.5)*3/7-.5))
        y0,z0=math.floor(yy),math.floor(zz);y1,z1=min(2,y0+1),min(2,z0+1)
        wy,wz=yy-y0,zz-z0
        return ((1-wy)*(1-wz)*values[y0][z0]+(1-wy)*wz*values[y0][z1]
                +wy*(1-wz)*values[y1][z0]+wy*wz*values[y1][z1])
    def scalar_loss(values):
        coarse=[[values[y][z]*float(omega[0,0,y,z]) for z in range(3)] for y in range(3)]
        masked=[]
        for y in range(5):
            for z in range(7):
                hard=float(omega[0,0,y*3//5,z*3//7])
                masked.append(scalar_soft(coarse,y,z)*hard*float(x[0,0,y,z]))
        # Analytic two-logit classifier [mean(x), -2*mean(x)].
        s=sum(masked)/35
        residual_mean=sum(float(x[0,0,y,z])*float(omega[0,0,y*3//5,z*3//7])
                          for y in range(5) for z in range(7))/35
        return 5*(residual_mean-s)**2+sum(abs(v) for row in values for v in row)/9
    values=mask.detach()[0,0].tolist()
    expected=torch.empty(5,7,dtype=torch.float64)
    coarse=[[values[y][z]*float(omega[0,0,y,z]) for z in range(3)] for y in range(3)]
    for y in range(5):
        for z in range(7):
            expected[y,z]=scalar_soft(coarse,y,z)*float(omega[0,0,y*3//5,z*3//7])*float(x[0,0,y,z])
    residual,masked=spi_inputs(x,omega,mask,c)
    assert torch.allclose(masked[0,0],expected,rtol=0,atol=1e-14)
    base=residual.mean();s=masked.mean()
    _,_,loss=losses(torch.stack([base,-2*base]),torch.stack([s,-2*s]),mask,c)
    loss.backward()
    assert float(loss)==pytest.approx(scalar_loss(values),abs=1e-14)
    h=1e-6
    for y in range(3):
        for z in range(3):
            plus,minus=copy.deepcopy(values),copy.deepcopy(values)
            plus[y][z]+=h;minus[y][z]-=h
            fd=(scalar_loss(plus)-scalar_loss(minus))/(2*h)
            assert float(mask.grad[0,0,y,z])==pytest.approx(fd,abs=2e-10)
