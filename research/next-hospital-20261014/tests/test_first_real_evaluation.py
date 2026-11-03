import numpy as np
import pytest

from epi_next.first_real_evaluation import native_cell_lookup, reconstruct_e1
from epi_next.encoder_mapping_qa import nominal_encoder_lattice


def test_independent_inverse_cells_cover_native_fov_with_correct_boundaries():
    indices = native_cell_lookup()
    assert indices[0] == 0 and indices[-1] == 223
    assert len(indices) == 512 and np.array_equal(np.unique(indices), np.arange(224))
    # Native cell boundary crosses model16 at native37; no rounding-to-even.
    assert indices[35] == 15 and indices[36] == 15 and indices[37] == 16


def records():
    return [{"scale_pixels": 16, "bounds_yx": [[0, 224], [0, 224]], "baseline_logits": [0., 2.],
             "perturbed_logits": [0., 1.], "margin_delta": 1., "target": 1, "accepted": True}]


def test_margin_mismatch_rejected_without_model_execution():
    rows = records(); rows[0]["margin_delta"] = .7
    with pytest.raises(ValueError, match="margin"):
        reconstruct_e1(rows, 16)


def test_reliability_cannot_override_numerical_response():
    rows = records(); rows[0]["accepted"] = False
    with pytest.raises(ValueError, match="reliability"):
        reconstruct_e1(rows, 16)


def test_missing_spatial_grid_is_rejected():
    rows = records(); rows[0]["bounds_yx"][0][1] = 223
    with pytest.raises(ValueError, match="incomplete"):
        reconstruct_e1(rows, 16)


def test_longest_residual_path_lattice_retains_boundary_limitation():
    lattice = nominal_encoder_lattice()
    assert lattice == {"stride": 16, "nominal_center_offset": 0, "receptive_field": 469, "conv_count": 31}
    assert lattice["receptive_field"] > 64
