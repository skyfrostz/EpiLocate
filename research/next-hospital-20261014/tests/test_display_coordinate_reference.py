"""Generated landmarks only; no clinical files or production mapping imports."""
import pytest
from epi_next.display_coordinate_reference import (
    native_to_model, model_to_native, expected)


def test_known_half_pixel_centres_and_edges():
    assert model_to_native(0, 223, 512, 512) == pytest.approx((9/14, 7145/14))
    assert model_to_native(-.5, 223.5, 512, 512) == (-.5, 511.5)
    assert native_to_model(255.5, 255.5, 512, 512) == (111.5, 111.5)


def test_generated_oblique_direction_and_asymmetric_size():
    g = {'crop': 'NONE', 'pad': 'NONE',
         'resize_convention': 'half_pixel_align_corners_false',
         'model_shape_yx': [224, 224], 'native_shape_rc': [448, 672],
         'native_slice_index_zero_based': 7,
         'native_affine_lps': [[0, 0, -2, 10], [0, 3, 0, 20],
                               [4, 0, 0, 30], [0, 0, 0, 1]]}
    r = expected(g)['landmarks'][0]
    assert r['native_yx'] == [.5, 1]
    assert r['lps_mm'] == [8, 21.5, 58]
    assert r['viewer_image_edge_xy'] == [1.5, 1]
    g['crop'] = 'UNKNOWN'
    with pytest.raises(ValueError, match='UNSUPPORTED'): expected(g)
