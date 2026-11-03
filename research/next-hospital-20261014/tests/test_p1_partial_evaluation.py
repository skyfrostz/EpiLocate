"""Small mathematical checks for separate continuous display / CPF support."""
import numpy as np

from epi_next.p1_partial_evaluation import bilinear_half_pixel
from epi_next.ref_support_qa import native_support, patch_support


def test_half_pixel_bilinear_known_oracle_and_border_clamp():
    coarse = np.array([[0., 1.], [2., 3.]])
    expected = np.array([[0., .25, .75, 1.], [.5, .75, 1.25, 1.5],
                         [1.5, 1.75, 2.25, 2.5], [2., 2.25, 2.75, 3.]])
    np.testing.assert_array_equal(bilinear_half_pixel(coarse, 4), expected)
    np.testing.assert_array_equal(bilinear_half_pixel(np.ones((7, 7))), np.ones((224, 224)))


def test_continuous_display_is_not_peak_region_or_binary_candidate():
    coarse = np.zeros((7, 7))
    coarse[6, 1] = 1
    peak = native_support(patch_support((224, 224), (7, 7), (6, 1)), (512, 512))
    assert peak.sum() == 5329
    ys, xs = np.where(peak)
    assert (ys.min(), ys.max() + 1, xs.min(), xs.max() + 1) == (439, 512, 73, 146)
    continuous = bilinear_half_pixel(coarse)
    assert continuous.dtype.kind == 'f' and np.any((continuous > 0) & (continuous < 1))
    assert np.sum(continuous > 0) > 32 * 32
