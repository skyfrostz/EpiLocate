import importlib.util
import os
from pathlib import Path
import sys
import numpy as np
import pytest
import torch
from epi_next.encoder_localization_bridge import EncoderResidualPredictor,HeadEvidence,head_state_sha256
from epi_next.localization import BudgetConfig


def encoder_module():
    # Integrated trees have epi_next.encoder. Isolated localization checkout can
    # test the exact sibling source without copying or editing the owning tree.
    try:
        from epi_next import encoder
        return encoder
    except ImportError:
        source=os.environ.get('EPI_NEXT_ENCODER_SOURCE')
        if not source:pytest.fail('set EPI_NEXT_ENCODER_SOURCE to audited encoder.py in isolated checkout')
        spec=importlib.util.spec_from_file_location('epi_next_encoder_test_source',source)
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module);return module


def setup():
    torch.set_num_threads(1);m=encoder_module()
    adapter=m.FrozenEncoderAdapter(torch.nn.AvgPool3d(2))
    head=m.CaseLinearHead(1)
    with torch.no_grad():head.linear.weight[:]=torch.tensor([[0.],[1.]]);head.linear.bias.zero_()
    return m,adapter,head


def test_actual_encoder_classes_full_reencoding_and_cam_geometry():
    m,a,h=setup();bridge=EncoderResidualPredictor(a,h,1,contribution_map=m.class_contribution_map)
    x=np.ones((4,4,4),np.float32)
    logits,c=bridge(x);logits2,c2=bridge(x)
    assert a.actual_queries==2 and bridge.calls==2 and np.array_equal(logits,logits2)
    assert c.shape==x.shape and c.min()==1 and np.array_equal(c,c2)
    meta=bridge.call_metadata[0]
    assert meta['feature_shape_zyx']==[2,2,2] and meta['coordinate_space']=='MODEL_INPUT_GRID_ZYX' and not meta['align_corners']
    assert meta['target_logit']==meta['cam_mean_plus_target_bias']
    r=bridge.localize(x,np.ones_like(x,bool),(1,1,1),BudgetConfig(scales_mm=(1.,),max_extra_evaluations=4))
    assert r['model_calls']==r['encoder_bridge']['actual_full_encoder_calls']==5
    assert a.actual_queries==7 and r['encoder_bridge']['head_evidence']=='SYNTHETIC'


def test_untrained_head_cannot_claim_real_f0_f1():
    m,a,h=setup()
    with pytest.raises(ValueError,match='untrained/synthetic'):EncoderResidualPredictor(a,h,1,scope='APPROVED_PREPROCESSED',input_approval_sha256='a'*64,contribution_map=m.class_contribution_map)
    bad=HeadEvidence(status='TRAINED_VERIFIED',head_state_sha256='a'*64,training_manifest_sha256='b'*64,label_audit_sha256='c'*64,task_definition_id='external-task',target_class_names=('c0','c1'))
    with pytest.raises(ValueError,match='head state'):EncoderResidualPredictor(a,h,1,evidence=bad,contribution_map=m.class_contribution_map)


def test_head_mutation_and_bool_target_rejected():
    m,a,h=setup()
    with pytest.raises(ValueError):EncoderResidualPredictor(a,h,True,contribution_map=m.class_contribution_map)
    bridge=EncoderResidualPredictor(a,h,1,contribution_map=m.class_contribution_map)
    with torch.no_grad():h.linear.bias[1]=1
    with pytest.raises(ValueError,match='head changed'):bridge(np.ones((4,4,4),np.float32))
    assert a.actual_queries==0


def test_verified_receipt_requires_task_semantics():
    m,a,h=setup();e=HeadEvidence(status='TRAINED_VERIFIED',head_state_sha256=head_state_sha256(h),training_manifest_sha256='a'*64,label_audit_sha256='b'*64)
    with pytest.raises(ValueError,match='task labels'):EncoderResidualPredictor(a,h,1,evidence=e,contribution_map=m.class_contribution_map)
