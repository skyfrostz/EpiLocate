from copy import deepcopy

import pytest

from epi_next.artifacts import sha256, reconcile_run
from epi_next.e2_result_handoff import AXES, save_handoff, validate_handoff


def fixture(tmp_path):
    source=tmp_path/'generated-result.json';source.write_bytes(b'{"logits":[1,2],"candidates":[]}\n')
    trace=b'{"iteration":1,"Ls":0.01,"Lm":0.4}\n'
    envelope={'schema':'EPI-NEXT-E2-RESULT-HANDOFF-3','method_mode':'E2-REF',
              'algorithm_version':'generated-reference-v1','run_profile':{'profile_id':'generated-component',
              'profile_kind':'COMPONENT','config_sha256':'1'*64},'model_sha256':'2'*64,
              'input_sha256':'3'*64,'preprocessing_sha256':'4'*64,
              'source_result':{'path':str(source),'sha256':sha256(source.read_bytes())},
              'execution_status':'NO_RELIABLE_RESPONSE','algorithm_status':'NO_FEASIBLE_MASK',
              'planned_branches':[{'scale_index':0,'grid_yx':[7,7],'stage':1,'max_iterations':1}],
              'branches':[{'scale_index':0,'grid_yx':[7,7],'stage':1,'completed_iterations':1,
               'status':'NO_FEASIBLE_MASK','selected_iteration':None,'selection_scope':'NONE',
               'reason':'CPF_EMPTY','trace_asset':{'path':'trace-0-1.jsonl','sha256':sha256(trace)}}],
              'psmi_status':'NOT_APPLICABLE','acceptance_axes':{axis:'NOT RUN' for axis in AXES}}
    return source,envelope,{'trace-0-1.jsonl':trace}


def test_mode_identity_and_immutable_trace_save_replay(tmp_path):
    source,envelope,assets=fixture(tmp_path)
    root=tmp_path/'saved';run='EPI-NEXT-generated-E2-REF'
    first=save_handoff(root,run,envelope,assets)
    assert first==save_handoff(root,run,envelope,assets)
    assert first['state']=='COMMITTED' and (root/run/'trace-0-1.jsonl').read_bytes()==assets['trace-0-1.jsonl']
    other=deepcopy(envelope);other['method_mode']='E2-CT';other['run_profile']['profile_kind']='CT_ADAPTATION'
    with pytest.raises(RuntimeError,match='RESULT_CONFLICT'):save_handoff(root,run,other,assets)
    source.write_bytes(b'changed')
    with pytest.raises(ValueError,match='SOURCE_RESULT'):save_handoff(root,'EPI-NEXT-new',envelope,assets)
    assert reconcile_run(root,run)['state']=='COMMITTED'


def test_partial_prefix_and_unrun_branch_not_silent_zero(tmp_path):
    _,e,assets=fixture(tmp_path);e['execution_status']='PARTIAL_BUDGET'
    e['algorithm_status']='PARTIAL_BUDGET';e['psmi_status']='NOT_FINALIZED_INCOMPLETE_OPTIMIZATION'
    e['planned_branches'][0]['max_iterations']=10
    b=e['branches'][0];b.update(status='OPTIMIZATION_PARTIAL',reason='BUDGET',selected_iteration=1,selection_scope='BEST_SO_FAR')
    plan={'scale_index':1,'grid_yx':[9,9],'stage':1,'max_iterations':10};e['planned_branches'].append(plan)
    with pytest.raises(ValueError,match='MISSING_BRANCH'):validate_handoff(e,assets)
    e['branches'].append(dict(scale_index=1,grid_yx=[9,9],stage=1,status='NOT RUN',completed_iterations=0,
                              selected_iteration=None,selection_scope='NONE',reason='PREVIOUS_BUDGET_STOP',trace_asset=None))
    validate_handoff(e,assets)
    b['selection_scope']='FULL_PLANNED_BUDGET'
    with pytest.raises(ValueError,match='PARTIAL_CANNOT'):validate_handoff(e,assets)
    b['selection_scope']='BEST_SO_FAR';e['execution_status']='SUCCESS'
    with pytest.raises(ValueError,match='UNFINISHED'):validate_handoff(e,assets)


def test_trace_and_selection_identity_rejected(tmp_path):
    _,e,assets=fixture(tmp_path)
    with pytest.raises(ValueError,match='TRACE_ASSET'):validate_handoff(e,dict.fromkeys(assets,b'tamper'))
    e['branches'][0].update(selected_iteration=2,selection_scope='FULL_PLANNED_BUDGET')
    with pytest.raises(ValueError,match='SELECTED_ITERATION'):validate_handoff(e,assets)


def test_modes_and_complete_no_feasible_have_separate_scopes(tmp_path):
    _,e,assets=fixture(tmp_path)
    e['method_mode']='E2-W1'
    with pytest.raises(ValueError,match='MODE_PROFILE'):validate_handoff(e,assets)
    e['run_profile']['profile_kind']='HISTORICAL_COMPONENT';validate_handoff(e,assets)
    e['execution_status']='SUCCESS'
    with pytest.raises(ValueError,match='SUCCESS_WITHOUT'):validate_handoff(e,assets)
    e['execution_status']='NO_RELIABLE_RESPONSE';e['acceptance_axes']['REAL_CT_FULL_CHAIN']='PASS'
    with pytest.raises(ValueError,match='SCOPED_ACCEPTANCE'):validate_handoff(e,assets)
