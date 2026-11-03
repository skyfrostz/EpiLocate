import time
import pytest
import torch
from epi_next.hspi import HSPIConfig,hspi_reference
from epi_next.e2_mechanism_telemetry import ForwardGuard,ResourceStop


class Toy(torch.nn.Module):
    def __init__(self):
        super().__init__();self.weight=torch.nn.Parameter(torch.tensor(1.));self.classifier_calls=0
    def forward(self,x):
        self.classifier_calls+=1
        y=(x[:,:,:2,:3].sum((1,2,3))+.2*x[:,:,5:,5:].sum((1,2,3)))*self.weight
        return torch.stack((y,y*.3),1)


def test_telemetry_preserves_exact_optimization_and_model_parameters():
    cfg=HSPIConfig(grids=((2,2),(3,3)),epochs=8,stages=1)
    x=torch.ones((1,1,8,8));valid=torch.ones((8,8),dtype=torch.bool)
    a=Toy();b=Toy();events=[]
    plain=hspi_reference(a,x,cfg,valid)
    traced=hspi_reference(b,x,cfg,valid,telemetry_sink=events.append)
    assert traced['status']==plain['status'] and traced['model_calls']==plain['model_calls']==18
    assert traced['candidates']==plain['candidates']
    assert [(s['baseline_logits'],s['trace']) for s in plain['stages']]==[(s['baseline_logits'],s['trace']) for s in traced['stages']]
    assert len(events)==16
    assert all(e['gradient_decomposition_max_error']<1e-5 for e in events)
    assert torch.equal(a.weight,b.weight) and b.weight.grad is None and b.weight.requires_grad
    for event in events:
        assert torch.allclose(torch.tensor(event['mask_after_projection']),torch.tensor(event['mask_before_projection']).clamp(0,1),rtol=0,atol=0)
    assert events[0]['mask_before']==[[.5,.5],[.5,.5]]


def test_forward_cap_blocks_next_actual_forward():
    model=Toy();model.classifier_calls=2
    guard=ForwardGuard(model,time.monotonic(),2,360,6*1024**3)
    guard.check() # gradients and saving remain allowed after last valid forward
    with pytest.raises(ResourceStop,match='MODEL_CALL_LIMIT'):guard.check(before_forward=True)
    assert model.classifier_calls==2


def test_global_time_and_rss_guards():
    with pytest.raises(ResourceStop,match='TIME_LIMIT'):
        ForwardGuard(Toy(),time.monotonic()-2,606,1,6*1024**3).check()
    with pytest.raises(ResourceStop,match='RSS_LIMIT'):
        ForwardGuard(Toy(),time.monotonic(),606,360,1).check()
