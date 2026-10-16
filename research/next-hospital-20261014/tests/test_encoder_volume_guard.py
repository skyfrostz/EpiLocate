import numpy as np
import pytest

from epi_next.encoder_volume_guard import BudgetStop,ForwardBudget,sampled_peak,stream_area_input
from epi_next.encoder_volume_dry_run import area_resize_control


def test_per_case_deadline_stops_before_another_forward():
    now=[0.];b=ForwardBudget(lambda:now[0]);b.begin_case(1)
    now[0]=120
    with pytest.raises(BudgetStop,match='CASE120'):b.before_forward('cpu')
    assert b.total_calls==0


def test_global_deadline_blocks_next_case_independently():
    now=[0.];b=ForwardBudget(lambda:now[0]);b.begin_case(1)
    for device in ['cpu']*4+['mps']*4:b.before_forward(device)
    b.end_case(True);now[0]=1200
    with pytest.raises(BudgetStop,match='TOTAL1200'):b.begin_case(2)
    assert b.total_calls==8 and b.case_index==1


def test_all_warmups_repeats_fit_exact24_but_no_extra():
    b=ForwardBudget(lambda:0.)
    for index in [1,2,3]:
        b.begin_case(index)
        for device in ['cpu']*4+['mps']*4:b.before_forward(device)
        b.end_case(True)
    assert b.total_calls==24
    with pytest.raises(BudgetStop):b.begin_case(4)
    c=ForwardBudget(lambda:0.);c.begin_case(1)
    for _ in range(4):c.before_forward('cpu')
    with pytest.raises(BudgetStop,match='FORWARD_LIMIT'):c.before_forward('cpu')


def test_child_timeout_is_smaller_of_case_and_total():
    now=[1190.];b=ForwardBudget(lambda:0.);b.clock=lambda:now[0];b.begin_case(1)
    assert b.owned_child_timeout_seconds()==10


def test_failed_case_cannot_retry_or_launch_next():
    b=ForwardBudget(lambda:0.);b.begin_case(1)
    with pytest.raises(BudgetStop):b.end_case(False)
    with pytest.raises(BudgetStop,match='prior failure'):b.begin_case(2)


def test_streamed_HU_control_matches_independent_dense_area_average():
    a=np.linspace(-1400,2500,17*19*23,dtype=np.float32).reshape(17,19,23)
    output=stream_area_input(a,(7,8,9))
    dense=area_resize_control((np.clip(a.astype('float64'),-1024,2048)+1024)/3072,(7,8,9))
    np.testing.assert_allclose(output[0,0],dense,atol=3e-8,rtol=0)
    assert output.dtype==np.float32 and output.shape==(1,1,7,8,9)


def test_between_poll_overshoot_is_not_hard_cap_evidence():
    gi=1024**3;events=[(0,5*gi),(.010,7*gi),(.020,5*gi)]
    assert sampled_peak(events,[0,.020])<6*gi
    assert max(v for _,v in events)>6*gi
