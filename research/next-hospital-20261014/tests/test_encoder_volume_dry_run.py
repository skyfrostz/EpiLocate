import numpy as np
import pytest

from epi_next.encoder_volume_dry_run import axis_starts,area_matrix,area_resize_control,full_fov_ledger,window_plan,synthetic_controls


def test_aligned_tail_covers_odd_native_shape():
    assert axis_starts(223,128,128)==(224,[0,96])
    p=window_plan((223,512,512),128,128)
    assert p['window_count']==32 and p['geometric_uncovered_native_voxels']==0
    assert p['normalized_patient_weight_sum']==pytest.approx(1,abs=1e-12)
    assert p['feature_center_multiplicity_max']==2
    assert p['windows'][-1]['new_air_padding_after']==[1,0,0]


def test_overlap_weights_do_not_duplicate_constant_patient_contribution():
    p=window_plan((244,512,512),96,48)
    assert p['window_count']==500
    assert p['normalized_patient_weight_sum']*7==pytest.approx(7)
    with pytest.raises(ValueError):axis_starts(223,128,140)
    with pytest.raises(ValueError):axis_starts(223,128,100)


def test_full_fov_half_voxel_mapping_preserves_both_edges_independently():
    old=dict(oriented_shape=[223,512,512],orient_to_native=np.eye(4).tolist(),
             patch_to_native=[[1,0,0,79],[0,1,0,224],[0,0,1,224],[0,0,0,1]],
             patch_to_lps=[[0,0,.78125,175],[0,.78125,0,175],[1.25,0,0,98.75],[0,0,0,1]],
             spacing_spl_mm=[1.25,.78125,.78125])
    p=full_fov_ledger(old);matrix=np.asarray(p['model_to_native'])
    np.testing.assert_allclose(matrix@[-.5,-.5,-.5,1],[-.5,-.5,-.5,1])
    np.testing.assert_allclose(matrix@[127.5,127.5,127.5,1],[222.5,511.5,511.5,1])
    assert p['proposed_spacing_spl_mm']==[2.177734375,3.125,3.125]


def test_area_average_preserves_constant_and_volume_mass():
    m=area_matrix(17,7)
    np.testing.assert_allclose(m.sum(axis=1),1,atol=1e-14)
    a=np.arange(17*19*23).reshape(17,19,23)
    out=area_resize_control(a,(7,8,9))
    assert out.mean()==pytest.approx(a.mean(),abs=1e-10)


def test_toy_overlap_and_small_impulse_are_not_false_equivalence():
    c=synthetic_controls()
    assert c['actual_ctfm_encoder_forwards']==0
    assert c['toy_whole_vs_overlap_average_max_abs_error']>0
    assert c['one_voxel_impulse_after_peak']==1/64
    assert c['impulse_volume_integral_absolute_error']<1e-12
