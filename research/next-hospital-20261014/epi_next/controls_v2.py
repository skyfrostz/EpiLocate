"""Bounded deterministic CPU controls. No real checkpoint or data loader."""
from unittest.mock import patch
import torch
import torch.nn.functional as F
from .hspi import HSPIConfig,hspi_reference


def graph_contains_leaf(tensor,leaf):
    pending=[tensor.grad_fn];seen=set()
    while pending:
        node=pending.pop()
        if node is None or node in seen:continue
        seen.add(node)
        if getattr(node,'variable',None) is leaf:return True
        pending.extend(n for n,_ in node.next_functions)
    return False


def run_controls():
    torch.set_num_threads(1)
    cost=dict(synthetic_forwards=0,direct_backward_calls=0,autograd_grad_calls=0,
              real_forwards=0,optimizer_steps=0)
    original_grad=torch.autograd.grad;original_backward=torch.Tensor.backward
    def grad(*args,**kwargs):
        cost['autograd_grad_calls']+=1;return original_grad(*args,**kwargs)
    def backward(value,*args,**kwargs):
        cost['direct_backward_calls']+=1;return original_backward(value,*args,**kwargs)
    class Toy(torch.nn.Module):
        def __init__(self):
            super().__init__();self.bn=torch.nn.BatchNorm2d(3).double()
            self.weight=torch.nn.Parameter(torch.tensor([.02,.04],dtype=torch.float64))
            self.expected_leaf=None;self.graph_checks=[]
        def forward(self,raw):
            cost['synthetic_forwards']+=1
            mean=raw.new_tensor([.485,.456,.406])[None,:,None,None]
            std=raw.new_tensor([.229,.224,.225])[None,:,None,None]
            x=self.bn((raw.repeat(1,3,1,1)-mean)/std)
            if self.expected_leaf is not None and raw.requires_grad:
                self.graph_checks.append(graph_contains_leaf(raw,self.expected_leaf))
            a=x[:,:,:6,:7].mean((1,2,3));b=(x*x).mean((1,2,3))
            return torch.stack((a*.04+b*.005,a*.09-b*.002),1)+self.weight
    model=Toy().eval().requires_grad_(False)
    before={k:v.clone() for k,v in model.state_dict().items()}
    x=torch.linspace(.15,.85,144,dtype=torch.float64).reshape(1,1,12,12)
    valid=torch.ones((12,12),dtype=torch.bool);valid[0,:]=False
    def masked(mask):
        retention=F.interpolate(mask,size=(12,12),mode='bilinear',align_corners=False)
        return x*torch.where(valid[None,None],retention,torch.ones_like(retention))
    with patch('torch.autograd.grad',new=grad),patch.object(torch.Tensor,'backward',new=backward):
        with torch.no_grad():
            baseline=model(x)
            identity=model(masked(torch.ones((1,1,3,3),dtype=x.dtype)))
            zero=model(masked(torch.zeros((1,1,3,3),dtype=x.dtype)))
            replacement=model(torch.where(valid[None,None],torch.zeros_like(x),x))
        mask=torch.full((1,1,3,3),.5,dtype=x.dtype,requires_grad=True)
        logits=model(masked(mask));ls=((baseline-logits)**2).sum()
        derivative=torch.autograd.grad(ls,mask)[0]
        finite=[];epsilon=1e-5
        for index in (0,4,8):
            plus=mask.detach().clone();minus=mask.detach().clone()
            plus.flatten()[index]+=epsilon;minus.flatten()[index]-=epsilon
            with torch.no_grad():
                high=((baseline-model(masked(plus)))**2).sum()
                low=((baseline-model(masked(minus)))**2).sum()
            fd=float((high-low)/(2*epsilon));ad=float(derivative.flatten()[index])
            finite.append(dict(cell=index,autograd=ad,finite_difference=fd,absolute_error=abs(ad-fd),
                relative_error=abs(ad-fd)/max(abs(ad),abs(fd),1e-12)))
        lm_mask=torch.nn.Parameter(torch.full_like(mask,.5));optimizer=torch.optim.Adam([lm_mask],lr=.01)
        lm_start=float(lm_mask.detach().mean())
        for _ in range(10):
            optimizer.zero_grad(set_to_none=True);lm_mask.abs().mean().backward()
            optimizer.step();cost['optimizer_steps']+=1
            with torch.no_grad():lm_mask.clamp_(0,1)
        ls_mask=torch.nn.Parameter(torch.full_like(mask,.5));optimizer=torch.optim.Adam([ls_mask],lr=.01)
        ls_losses=[]
        for _ in range(8):
            optimizer.zero_grad(set_to_none=True);loss=((baseline-model(masked(ls_mask)))**2).sum()
            ls_losses.append(float(loss.detach()));loss.backward();optimizer.step();cost['optimizer_steps']+=1
            with torch.no_grad():ls_mask.clamp_(0,1)
        optimizers=[];optimizer_events=[];base_adam=torch.optim.Adam
        class InspectAdam(base_adam):
            def __init__(self,parameters,*args,**kwargs):
                super().__init__(parameters,*args,**kwargs);optimizers.append(self)
                # An audit reference must not register the mask as a classifier
                # parameter through Module.__setattr__.
                object.__setattr__(model,'expected_leaf',self.param_groups[0]['params'][0]);self.zero_calls=0
            def zero_grad(self,*args,**kwargs):
                self.zero_calls+=1;return super().zero_grad(*args,**kwargs)
            def step(self,*args,**kwargs):
                param=self.param_groups[0]['params'][0];old=param.detach().clone()
                result=super().step(*args,**kwargs);cost['optimizer_steps']+=1
                optimizer_events.append(dict(optimizer_identity=id(self),leaf_identity=id(param),
                    leaf_is_forward_parameter=param is model.expected_leaf,is_leaf=param.is_leaf,
                    requires_grad=param.requires_grad,device=str(param.device),step=int(self.state[param]['step']),
                    update_max=float((param.detach()-old).abs().max()),zero_grad_calls=self.zero_calls))
                return result
        events=[]
        with patch('torch.optim.Adam',new=InspectAdam):
            hspi=hspi_reference(model,x,HSPIConfig(grids=((3,3),),stages=1,epochs=5,
                min_other_scale_support=0),valid,telemetry_sink=events.append)
    parameters_and_buffers_unchanged=all(torch.equal(before[k],v) for k,v in model.state_dict().items())
    checks=dict(identity_exact=torch.equal(identity,baseline),zero_matches_explicit_raw_zero_exact=torch.equal(zero,replacement),
        finite_difference_pass=all(e['relative_error']<1e-6 for e in finite),
        lm_only_reduces_mask=float(lm_mask.detach().mean())<lm_start,
        ls_only_loss_decreases=ls_losses[-1]<ls_losses[0],
        optimizer_created_once=len(optimizers)==1,
        optimizer_steps_monotone=[e['step'] for e in optimizer_events]==list(range(1,6)),
        optimizer_is_forward_leaf=all(e['leaf_is_forward_parameter'] and e['is_leaf'] and e['requires_grad'] for e in optimizer_events),
        masked_forward_graph_reaches_leaf=len(model.graph_checks)==5 and all(model.graph_checks),
        zero_grad_each_step=all(e['zero_grad_calls']==e['step'] for e in optimizer_events),
        parameters_and_bn_buffers_unchanged=parameters_and_buffers_unchanged,
        eval_and_frozen=model.training is False and all(not p.requires_grad for p in model.parameters()),
        sum_not_mean=all(abs(e['similarity']-sum((a-b)**2 for a,b in zip(hspi['stages'][0]['baseline_logits'],e['logits'])))<1e-12 for e in hspi['stages'][0]['trace']))
    cost['total_reverse_calls']=cost['direct_backward_calls']+cost['autograd_grad_calls']
    return dict(schema='E2_SYNTHETIC_CONTROL_V2',status='PASS' if all(checks.values()) else 'FAIL',
        checks=checks,cost=cost,finite_differences=finite,optimizer_events=optimizer_events,
        synthetic_mask_start=lm_start,lm_only_final_mean=float(lm_mask.detach().mean()),ls_only_losses=ls_losses,
        hspi_status=hspi['status'],telemetry_epochs=len(events),
        scope='tiny deterministic float64 CPU control; no real model, GT or input',
        conclusion='rules out these implementation failures in this synthetic path, not global real-model convergence')
