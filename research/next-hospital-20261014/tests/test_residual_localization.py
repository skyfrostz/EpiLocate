import numpy as np
import pytest
from epi_next.localization import BudgetConfig
from epi_next.residual_localization import residual_input_occlusion_3d


A,B,C=(1,1,1),(3,3,3),(1,3,1)
def fixture():
    x=np.zeros((5,5,5),dtype=float)
    for p in (A,B,C):x[p]=1.
    return x,np.ones_like(x,bool)


class InteractionModel:
    def __init__(self):self.inputs=[]
    def __call__(self,x):
        self.inputs.append(x.copy())
        a,b,c=x[A],x[B],x[C]
        score=4*a+2*b+3*(1-a)*c
        coarse=np.zeros_like(x);coarse[A]=10*a;coarse[B]=8*b;coarse[C]=(1+19*(1-a))*c
        return [0.,score],coarse


def run(model=None,config=None,clock=None):
    x,v=fixture()
    kwargs={} if clock is None else dict(clock=clock)
    return residual_input_occlusion_3d(model or InteractionModel(),x,v,1,(1,1,1),config or BudgetConfig(seed=17,scales_mm=(1.,)),**kwargs)


def test_remaining_input_baseline_and_map_really_update():
    model=InteractionModel();result=run(model)
    assert result['model_calls']==8 and result['extra_evaluations']==7
    assert result['original_baseline_logits']==[0.,6.]
    assert [s['baseline_logits'] for s in result['stages']]==[[0.,6.],[0.,5.],[0.,2.]]
    assert [s['center_zyx'] for s in result['stages']]==[list(A),list(C),list(B)]
    assert len({s['coarse_sha256'] for s in result['stages']})==3
    assert len({s['baseline_input_sha256'] for s in result['stages']})==3
    assert [r['margin_delta'] for r in result['candidates']]==[1.,3.,2.]
    assert result['candidates'][1]['cumulative_margin_drop_from_original']==4.
    assert model.inputs[4][A]==0 and model.inputs[4][C]==1
    assert model.inputs[6][A]==0 and model.inputs[6][C]==0 and model.inputs[6][B]==1
    assert result['status']=='PARTIAL_BUDGET' and result['reason']=='STAGE_LIMIT'


def test_seeded_probes_diagnostic_only_without_reusing_cached_responses():
    result=run();repeat=run()
    assert result['probes']==repeat['probes'] and result['records']==repeat['records']
    assert result['random_probes_completed']==2 and result['probe_status']=='OK'
    probes=[set(p['mask_flat_indices']) for p in result['probes']]
    assert probes[0].isdisjoint(probes[1])
    assert all(not p['accepted'] and not p['candidate_eligible'] for p in result['probes'])
    assert all(c['call_index'] not in {p['call_index'] for p in result['probes']} for c in result['candidates'])
    assert len(result['candidates'])==3


def test_budget_counts_refresh_and_preserves_candidates():
    result=run(config=BudgetConfig(seed=17,scales_mm=(1.,),max_extra_evaluations=4))
    assert result['model_calls']==5 and result['extra_evaluations']==4
    assert result['calls'][-1]['kind']=='RESIDUAL_BASELINE_AND_COARSE_REFRESH'
    assert result['status']=='PARTIAL_BUDGET' and len(result['candidates'])==1
    assert result['stages'][-1]['status']=='PARTIAL_BUDGET'


@pytest.mark.parametrize('failure_call',[1,3,5,6])
def test_failed_calls_counted_including_baseline_refresh(failure_call):
    model=InteractionModel();n=[0]
    def predict(x):
        n[0]+=1
        if n[0]==failure_call:raise RuntimeError('synthetic model failure')
        return model(x)
    result=run(predict)
    assert result['status']=='FAILED' and result['reason']=='MODEL_FAILURE'
    assert result['model_calls']==failure_call and result['extra_evaluations']==failure_call-1
    assert result['calls'][-1]['status']=='FAILED'
    if failure_call>=5:assert len(result['candidates'])==1 and result['accepted_union_voxels']==1


def test_nonfinite_map_rejected_with_count():
    result=run(lambda x:([0,1],np.full_like(x,np.nan)))
    assert result['status']=='FAILED' and result['reason']=='NUMERICAL_FAILURE' and result['model_calls']==1


def test_timeout_after_inflight_keeps_completed_response():
    t=[0.];model=InteractionModel()
    def predict(x):t[0]+=1.;return model(x)
    result=run(predict,BudgetConfig(seed=17,scales_mm=(1.,),timeout_seconds=4.),clock=lambda:t[0])
    assert result['status']=='PARTIAL_BUDGET' and result['reason']=='TIME_LIMIT'
    assert result['model_calls']==4 and result['extra_evaluations']==3 and len(result['candidates'])==1
    assert result['elapsed_seconds']==4. and result['accepted_union_voxels']==1


def test_tiny_support_reports_incomplete_probes():
    x=np.ones((1,1,1));result=residual_input_occlusion_3d(lambda a:([0,a.sum()],a),x,np.ones_like(x,bool),1,(1,1,1))
    assert result['status']=='INPUT_UNSUPPORTED' and result['reason']=='INSUFFICIENT_PROBE_SUPPORT'
    assert result['model_calls']==2 and result['random_probes_completed']==1


def test_no_positive_response_can_finish_empty_without_topk():
    x=np.ones((1,1,3));v=np.ones_like(x,bool)
    result=residual_input_occlusion_3d(lambda a:([0,1],a),x,v,1,(1,1,1),BudgetConfig(scales_mm=(1.,),seed=17))
    assert result['status']=='NO_RELIABLE_RESPONSE' and result['reason']=='SEARCH_SUPPORT_EXHAUSTED'
    assert not result['candidates'] and result['accepted_union_voxels']==0


def test_each_scale_compared_to_same_current_baseline():
    result=run(config=BudgetConfig(seed=17,scales_mm=(1.,2.),stages=2))
    for stage in result['stages']:
        records=[result['records'][i] for i in stage['candidate_record_indices']]
        assert all(r['baseline_logits']==stage['baseline_logits'] for r in records)
        assert all(r['stage_baseline_call_index']==stage['baseline_call_index'] for r in records)


def test_bad_target_or_unknown_support_never_runs():
    x,v=fixture()
    with pytest.raises(ValueError):residual_input_occlusion_3d(None,x,v,True,(1,1,1))
    result=residual_input_occlusion_3d(None,x,None,1,(1,1,1))
    assert result['status']=='INPUT_UNSUPPORTED' and result['model_calls']==0


def test_budget_reserved_for_two_probes_before_any_candidate():
    result=run(config=BudgetConfig(seed=17,scales_mm=(1.,),max_extra_evaluations=2))
    assert result['status']=='PARTIAL_BUDGET' and result['reason']=='EXTRA_EVALUATION_LIMIT'
    assert result['random_probes_completed']==2 and result['model_calls']==3
    assert result['extra_evaluations']==2 and result['records']==[] and result['candidates']==[]


def test_unique_signal_seen_by_probe_is_formally_rediscovered():
    shape=(5,5,5)
    center=tuple(np.unravel_index(np.random.default_rng(17).integers(np.prod(shape)),shape))
    x=np.zeros(shape);x[center]=1.;valid=np.ones(shape,bool)
    def predict(a):
        coarse=np.zeros_like(a);coarse[center]=10*a[center]
        return [0.,a[center]],coarse
    result=residual_input_occlusion_3d(predict,x,valid,1,(1,1,1),BudgetConfig(seed=17,scales_mm=(1.,)))
    assert result['probes'][0]['center_zyx']==list(center)
    assert result['probes'][0]['supporting_response'] and not result['probes'][0]['candidate_eligible']
    assert result['candidates'][0]['center_zyx']==list(center)
    assert result['candidates'][0]['call_index']!=result['probes'][0]['call_index']
    assert result['candidates'][0]['margin_delta']==1.
    assert result['status']=='OK' and result['reason']=='TARGET_SUPPORT_LOST'
    assert result['calls'][-1]['kind']=='RESIDUAL_BASELINE_AND_COARSE_REFRESH'


def test_initial_target_support_loss_stops_without_normal_ct_claim():
    x,v=fixture();result=residual_input_occlusion_3d(lambda a:([2.,1.],a),x,v,1,(1,1,1))
    assert result['status']=='NO_RELIABLE_RESPONSE' and result['reason']=='TARGET_SUPPORT_LOST'
    assert result['model_calls']==1 and result['extra_evaluations']==0
    assert result['candidates']==[] and result['probe_status']=='INCOMPLETE'


def test_smoke_output_is_exclusive_and_preserves_existing_bytes(tmp_path,monkeypatch):
    import sys
    from epi_next.residual_localization import main
    path=tmp_path/'existing.json';path.write_text('previous evidence')
    monkeypatch.setattr(sys,'argv',['residual_localization','--output',str(path)])
    with pytest.raises(SystemExit) as exc:main()
    assert exc.value.code==2 and path.read_text()=='previous evidence'
