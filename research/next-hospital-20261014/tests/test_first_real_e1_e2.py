import numpy as np
import pytest
import torch
from epi_next.first_real_e1_e2 import native_lookup, locked_json, DifferentiablePreparedModel


def test_consumed_half_pixel_ledger_preserves_native_cell_membership():
    # Model 2x2 -> native 4x4; native centres belong to 2x2 constant regions.
    forward=np.diag([1.,2.,2.,1.]);forward[:3,3]=[111.,.5,.5]
    g=dict(native_shape_rc=[4,4],model_shape_yx=[2,2],native_slice_index_zero_based=111,
           model_to_native_zyx=forward.tolist(),native_to_model_zyx=np.linalg.inv(forward).tolist())
    y,x=native_lookup(g)
    model=np.array([[True,False],[False,False]])
    assert np.array_equal(model[y,x],np.array([[1,1,0,0],[1,1,0,0],[0,0,0,0],[0,0,0,0]],bool))
    g['native_slice_index_zero_based']=112
    with pytest.raises(ValueError,match='leaves selected'):native_lookup(g)


def test_changed_delivery_bytes_rejected_before_any_model_load(tmp_path):
    p=tmp_path/'receipt.json';p.write_text('{}')
    with pytest.raises(ValueError,match='SHA mismatch'):locked_json(p,'0'*64)


def test_real_resize_ulp_overshoot_preserved_as_exact_frozen_tensor():
    class Classifier(torch.nn.Module):
        def forward(self,x):
            self.seen=x.detach().clone();s=x.mean((1,2,3));return torch.stack((s*0,s),1)
    c=Classifier();spec=dict(normalization_mean=[.485,.456,.406],normalization_std=[.229,.224,.225])
    m=DifferentiablePreparedModel(c,spec);image=np.full((224,224),np.float32(1.000000238418579))
    m.predict_numpy(image)
    expected=(torch.from_numpy(image)[None,None].repeat(1,3,1,1)-m.mean)/m.std
    assert torch.equal(c.seen,expected) and m.classifier_calls==1
    assert image.max()>1
