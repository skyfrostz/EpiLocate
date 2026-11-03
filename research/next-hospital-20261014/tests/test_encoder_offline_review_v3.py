"""New directed generated-data tests only, no Torch/checkpoint/patient assets."""
import itertools
import numpy as np
import pytest

from epi_next.encoder_offline_review_v3 import (source_config, symbolic_profile, downsample_generated_control,
    compose_half_voxel, case_gap_oracle, linear_head_oracle, patient_manifest_guard)

CONFIG = dict(blocks_down=[1, 2, 2, 4, 4], in_channels=1, init_filters=32, spatial_dims=3)


def test_static_count_matches_previously_verified_state_and_lattice():
    config = source_config('CTFM_CONFIG = dict(blocks_down=[1,2,2,4,4], in_channels=1, init_filters=32, spatial_dims=3)')
    p = symbolic_profile(config, 128)
    assert p['parameter_elements'] == 77760992 and p['running_float_buffer_elements'] == 13952
    assert p['conv_count'] == 31 and p['lattice'] == dict(nominal_receptive_field_voxels=469, stride=16, center_offset=0)
    assert p['stages'][0]['fp32_bytes'] == 268435456
    assert p['retained_stage_outputs_fp32_bytes'] == 341*1024**2
    assert p['conditional_max_full_im2col_fp32_bytes'] == 7247757312
    assert p['measured_activation_peak_bytes'] is None and p['actual_cpu_backend'] is None
    with pytest.raises(ValueError): symbolic_profile(dict(CONFIG, init_filters=16), 128)


def test_only_volume_dependent_sizes_scale_eightfold_not_parameters():
    small, large = [symbolic_profile(CONFIG, n) for n in [64, 128]]
    for key in ['input_fp32_bytes', 'retained_stage_outputs_fp32_bytes',
                'conditional_max_full_im2col_fp32_bytes', 'total_convolution_multiply_accumulate_operations']:
        assert large[key] == 8*small[key]
    assert small['resident_state_fp32_bytes'] == large['resident_state_fp32_bytes']


def test_generated_2x_area_average_independent_loop_and_one_voxel_loss():
    x = np.linspace(0, 1, 8**3, dtype=np.float32).reshape(1, 1, 8, 8, 8)
    y = downsample_generated_control(x)
    expected = np.empty((4, 4, 4), np.float64)
    for i, j, k in itertools.product(range(4), repeat=3):
        expected[i, j, k] = sum(float(x[0, 0, 2*i+a, 2*j+b, 2*k+c])
                                for a, b, c in itertools.product(range(2), repeat=3))/8
    np.testing.assert_array_equal(y[0, 0], expected.astype(np.float32))
    impulse = np.zeros_like(x); impulse[0, 0, 3, 3, 3] = 1
    assert downsample_generated_control(impulse).max() == .125
    assert float(downsample_generated_control(impulse).sum())*8 == 1
    with pytest.raises(ValueError): downsample_generated_control(x.astype(np.float64))


def test_half_voxel_composition_keeps_full_edges_with_axis_flip():
    native_shape = np.array([223, 512, 512])
    parent = np.eye(4); parent[:3, :3] = np.diag(native_shape/128); parent[:3, 3] = .5*native_shape/128-.5
    flip = np.eye(4); flip[1, 1] = -1; flip[1, 3] = 511
    composed = compose_half_voxel(flip@parent, [2, 2, 2])
    direct = np.eye(4); direct[:3, :3] = np.diag(native_shape/64); direct[:3, 3] = .5*native_shape/64-.5
    np.testing.assert_allclose(composed, flip@direct, atol=1e-14)
    for corner in itertools.product([-.5, 63.5], repeat=3):
        point = [*corner, 1]
        np.testing.assert_allclose(composed@point, (flip@direct)@point, atol=1e-12)
    with pytest.raises(ValueError): compose_half_voxel(parent, [0, 2, 2])


def test_generated_whole_case_gap_and_signed_cam_match_independent_logits():
    x = np.linspace(-2, 3, 4*3*2*2, dtype=np.float32).reshape(1, 4, 3, 2, 2)
    mean = np.array([1, -1, 0, 2]); scale = np.array([2, .5, 3, 1])
    weight = np.array([[1, -2, 3, .25], [-1, 1, -.5, 2]]); bias = np.array([.3, -.1])
    result = linear_head_oracle(x, mean, scale, weight, bias)
    pooled = np.array([[sum(float(v) for v in x[0, c].ravel())/12 for c in range(4)]])
    expected = np.array([[sum(weight[k, c]*(pooled[0, c]-mean[c])/scale[c] for c in range(4))+bias[k] for k in range(2)]])
    np.testing.assert_allclose(result['logits'], expected, atol=1e-12)
    np.testing.assert_allclose(result['reconstructed_logits'], expected, atol=1e-12)
    with pytest.raises(ValueError): case_gap_oracle(x, field_of_view='CENTER_PATCH')
    with pytest.raises(ValueError): linear_head_oracle(x, mean, np.zeros(4), weight, bias)


def test_head_schema_rejects_masks_unknown_single_class_and_duplicate_patients():
    rows = [dict(patient_key='a', split='train', label_status='VERIFIED', label_source='EXPERT_STUDY', label=0),
            dict(patient_key='b', split='train', label_status='VERIFIED', label_source='EXPERT_STUDY', label=1)]
    assert patient_manifest_guard(rows)['patients'] == 2
    for changed in [dict(rows[1], patient_key='a'), dict(rows[1], label_source='MASK'),
                    dict(rows[1], label_status='UNKNOWN'), dict(rows[1], label=0), dict(rows[1], split='test')]:
        with pytest.raises(ValueError): patient_manifest_guard([rows[0], changed])
