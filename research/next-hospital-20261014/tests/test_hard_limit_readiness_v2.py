"""Counterexamples, with simulated time/RSS; no large allocation or sleeping."""
from types import SimpleNamespace
from unittest.mock import patch
import json
import sys
import pytest
import torch
from epi_next.spi_recovery_v2 import ComputeMeter,StopBudget,verify_execution_lock

COUNTS=dict(synthetic_forwards=0,loss_backward=0,autograd_grad=0,real_forwards=0)


@pytest.fixture(scope='module',autouse=True)
def report_cost():
    yield
    print('HARD_LIMIT_TEST_COST='+json.dumps(COUNTS))


def test_deadline_can_be_crossed_inside_one_forward():
    elapsed=[0.];meter=ComputeMeter(clock=lambda:elapsed[0],max_seconds=900.)
    def inflight(x):
        COUNTS['synthetic_forwards']+=1;elapsed[0]=901.;return x*2
    value=meter.forward(inflight,torch.tensor(1.,requires_grad=True))
    assert value.item()==2 and meter.forward_completed==1 and meter.receipt()['elapsed_seconds']==901.
    with pytest.raises(StopBudget,match='TIME_LIMIT'):meter.check()


def test_rss_threshold_is_detected_after_simulated_overshoot():
    peak=[0];unit=1 if sys.platform=='darwin' else 1024
    with patch('epi_next.spi_recovery_v2.resource.getrusage',new=lambda _:SimpleNamespace(ru_maxrss=peak[0]/unit)):
        meter=ComputeMeter(max_rss=6*1024**3)
        def inflight(x):
            COUNTS['synthetic_forwards']+=1;peak[0]=7*1024**3;return x*2
        value=meter.forward(inflight,torch.tensor(1.,requires_grad=True))
        assert value.item()==2 and peak[0]>meter.max_rss and meter.forward_completed==1
        with pytest.raises(StopBudget,match='RSS_LIMIT'):meter.check()


def test_counts_reject_next_call_before_actual_invocation():
    meter=ComputeMeter(max_forwards=1,max_reverse=1)
    def predict(x):COUNTS['synthetic_forwards']+=1;return x*2
    value=meter.forward(predict,torch.tensor(1.,requires_grad=True))
    with pytest.raises(StopBudget,match='FORWARD_LIMIT'):meter.forward(predict,torch.tensor(1.))
    def reverse():COUNTS['loss_backward']+=1;value.backward()
    meter.reverse('backward',reverse)
    with pytest.raises(StopBudget,match='REVERSE_LIMIT'):meter.reverse('autograd',lambda:None)
    assert meter.forwards==meter.forward_completed==1 and meter.backward==meter.reverse_completed==1 and meter.autograd==0


def test_scope_approval_alone_requires_revised_resource_supervision_binding():
    lock=dict(status='LOCKED_FOR_E2_R1_R2_CPU_EXECUTION',proposal_sha256='a'*64,real_model_execution_authorized=True)
    with pytest.raises(ValueError,match='resource revision and shared supervision binding required'):
        verify_execution_lock(lock,'a'*64)
