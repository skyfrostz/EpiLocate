import hashlib
import numpy as np
import pytest
import torch
from epi_next.preprocessed_localization import Prepared2DInput,run_prepared_e1_e2
from epi_next.hspi import HSPIConfig


class Model(torch.nn.Module):
    def forward(self,x):
        s=x[:,:,0,0].sum(1);return torch.stack((s*0,s),1)


def record(**kwargs):
    x=np.ones((4,4),np.float32)
    return Prepared2DInput(x,np.ones_like(x,bool),hashlib.sha256(x.tobytes()).hexdigest(),'test-preprocess','externally-defined-synthetic-task',**kwargs)


def test_in_memory_adapter_counts_and_no_labels_created():
    torch.set_num_threads(1);m=Model()
    def predict(a):return m(torch.from_numpy(a)[None,None]).detach().numpy()[0]
    cfg=HSPIConfig(grids=((2,2),),stages=1,epochs=2,min_other_scale_support=0)
    result=run_prepared_e1_e2(record(),predict,m,target=1,e1_options=dict(patch_sizes=(2,),fill=0.),e2_config=cfg)
    assert result['status']=='OK' and not result['label_creation']
    assert result['actual_model_calls']==2+result['E1']['model_calls']+result['E2']['model_calls']
    assert result['E2_target_semantics']=='FULL_LOGITS_CONSISTENCY_NOT_FIXED_TARGET_MARGIN'


def test_mismatched_preprocessing_stops_before_algorithms():
    result=run_prepared_e1_e2(record(),lambda x:[0,2],Model(),target=1,e1_options={},e2_config=HSPIConfig())
    assert result['reason']=='PREPROCESS_ADAPTER_MISMATCH' and result['actual_model_calls']==2 and 'E1' not in result


def test_sealed_or_unapproved_prepared_input_rejected():
    with pytest.raises(ValueError):record(scope='APPROVED_PREPROCESSED',split='sealed',approval_receipt_sha256='a'*64).validate()
    with pytest.raises(ValueError):record(scope='APPROVED_PREPROCESSED',split='train').validate()


def test_adapter_eval_modes_restored_and_config_hash_reproducible():
    m=Model();m.train()
    def predict(a):
        assert not m.training
        return m(torch.from_numpy(a)[None,None]).detach().numpy()[0]
    cfg=HSPIConfig(grids=((2,2),),stages=1,epochs=2,min_other_scale_support=0)
    a=run_prepared_e1_e2(record(),predict,m,target=1,e1_options=dict(patch_sizes=(2,),fill=np.zeros((4,4),np.float32)),e2_config=cfg)
    b=run_prepared_e1_e2(record(),predict,m,target=1,e1_options=dict(patch_sizes=(2,),fill=np.zeros((4,4),np.float32)),e2_config=cfg)
    assert a['status']=='OK' and m.training and a['config_sha256']==b['config_sha256']
    assert a['E1_numerical_diagnosis']['status']=='PASS' and a['elapsed_seconds']>=0


def test_e1_failure_stops_before_e2_and_counts_attempt():
    m=Model();calls=[0]
    def predict(a):
        calls[0]+=1
        if calls[0]==3:raise RuntimeError('controlled occlusion failure')
        return [0.,1.]
    r=run_prepared_e1_e2(record(),predict,m,target=1,e1_options=dict(patch_sizes=(2,),fill=0.),e2_config=HSPIConfig())
    assert r['status']=='FAILED' and r['reason']=='E1_FAILED' and 'E2' not in r
    assert r['actual_model_calls']==4


def test_algorithm_failure_precedence_over_other_algorithm_budget(monkeypatch):
    import epi_next.preprocessed_localization as module
    monkeypatch.setattr(module,'hspi_reference',lambda *args:dict(status='FAILED',reason='MODEL_FAILURE',model_calls=1))
    r=run_prepared_e1_e2(record(),lambda a:[0.,1.],Model(),target=1,e1_options=dict(max_model_calls=1),e2_config=HSPIConfig())
    assert r['E1']['status']=='PARTIAL_BUDGET' and r['status']=='FAILED'
    assert r['actual_model_calls']==4
