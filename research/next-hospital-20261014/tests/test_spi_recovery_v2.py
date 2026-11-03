import json
from unittest.mock import patch
import numpy as np
import pytest
import torch
from epi_next.hspi import HSPIConfig,hspi_reference
from epi_next.spi_recovery_v2 import ComputeMeter,run_spi,verify_execution_lock
from epi_next.e1_fill_v2 import gaussian_replacement

torch.set_num_threads(1)
COST=dict(synthetic_forwards=0,direct_backward=0,autograd_grad=0,real_forwards=0)


@pytest.fixture(scope='module',autouse=True)
def count_all_calls():
    original_backward=torch.Tensor.backward;original_grad=torch.autograd.grad
    def backward(value,*args,**kwargs):
        COST['direct_backward']+=1;return original_backward(value,*args,**kwargs)
    def grad(*args,**kwargs):
        COST['autograd_grad']+=1;return original_grad(*args,**kwargs)
    with patch.object(torch.Tensor,'backward',new=backward),patch('torch.autograd.grad',new=grad):yield
    print('V2_SYNTHETIC_TEST_COST='+json.dumps(COST))


class Tiny(torch.nn.Module):
    def __init__(self):super().__init__();self.weight=torch.nn.Parameter(torch.tensor(.2,dtype=torch.float64))
    def forward(self,x):
        COST['synthetic_forwards']+=1
        y=(x[:,:,:4,:5].mean((1,2,3))+x.pow(2).mean((1,2,3)))*self.weight
        return torch.stack((y,y*.3),1)


def inputs():return torch.linspace(.1,.9,144,dtype=torch.float64).reshape(1,1,12,12),torch.ones((12,12),dtype=torch.bool)


def test_recovery_exact_frozen_prefix_and_resumable_snapshot():
    x,v=inputs();base=Tiny();next_model=Tiny();meter=ComputeMeter()
    old=hspi_reference(base,x,HSPIConfig(grids=((7,7),),epochs=3,stages=1,min_other_scale_support=0),v)
    snapshots={}
    result=run_spi(next_model,x,v,weight=.1,steps=3,meter=meter,gradient_steps=(1,3),
        checkpoints=(1,3),checkpoint_sink=lambda step,s:snapshots.update({step:s}),expected_prefix=old['stages'][0]['trace'],
        expected_baseline=old['stages'][0]['baseline_logits'])
    assert result['trace']==old['stages'][0]['trace'] and result['prefix_exact_match'] is True
    assert result['status']==old['status'] and result['model_unchanged']
    assert meter.forwards==4 and meter.backward==3 and meter.autograd==4 and meter.optimizer_steps==3
    assert int(snapshots[1]['optimizer']['state'][0]['step'])==1
    assert int(snapshots[3]['optimizer']['state'][0]['step'])==3
    assert not torch.equal(snapshots[1]['mask'],snapshots[3]['mask'])
    assert next_model.training and next_model.weight.requires_grad and next_model.weight.grad is None


def test_reverse_budget_stops_before_backward_and_preserves_partial():
    x,v=inputs();meter=ComputeMeter(max_reverse=0)
    result=run_spi(Tiny(),x,v,weight=.1,steps=2,meter=meter)
    assert result['status']=='PARTIAL_BUDGET' and result['reason']=='REVERSE_LIMIT'
    assert len(result['trace'])==1 and result['candidates']==[]
    assert meter.forwards==2 and meter.backward==meter.autograd==meter.optimizer_steps==0


def test_forward_budget_and_expired_clock_start_no_next_query():
    x,v=inputs();meter=ComputeMeter(max_forwards=1)
    result=run_spi(Tiny(),x,v,weight=1.,steps=2,meter=meter)
    assert result['status']=='PARTIAL_BUDGET' and result['reason']=='FORWARD_LIMIT' and meter.forwards==1
    elapsed=[0.];expired=ComputeMeter(clock=lambda:elapsed[0]);elapsed[0]=901
    result=run_spi(Tiny(),x,v,weight=.1,steps=2,meter=expired)
    assert result['status']=='PARTIAL_BUDGET' and result['reason']=='TIME_LIMIT' and expired.forwards==0


def test_preparation_lock_cannot_authorize_real_execution():
    with pytest.raises(ValueError,match='not execution authorization'):
        verify_execution_lock({'status':'LOCKED_PREPARATION_ONLY','proposal_sha256':'a'*64},'a'*64)


def test_wrong_frozen_baseline_stops_after_one_measured_forward():
    x,v=inputs();meter=ComputeMeter()
    result=run_spi(Tiny(),x,v,weight=.1,steps=3,meter=meter,expected_baseline=[999.,999.])
    assert result['status']=='FAILED' and result['reason']=='frozen baseline mismatch'
    assert meter.forwards==1 and meter.backward==meter.autograd==0 and result['trace']==[]


def test_fixed_blur_replacement_preserves_shape_and_constant_without_GT():
    x=np.full((12,12),.4,dtype=np.float32);blur=gaussian_replacement(x)
    assert blur.shape==x.shape and blur.dtype==x.dtype and np.allclose(blur,x,atol=1e-6,rtol=0)
    x=np.zeros((12,12),dtype=np.float32);x[6,6]=1;blur=gaussian_replacement(x)
    assert 0<float(blur[6,6])<1 and np.isfinite(blur).all()
