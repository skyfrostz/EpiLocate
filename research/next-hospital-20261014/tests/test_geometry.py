import numpy as np
import pytest

from epi_next.geometry import (inverse_points, regular_stack_geometry,
    slice_affine_lps, transform_points)


def stack(positions, orientation=(1, 0, 0, 0, 1, 0)):
    n = len(positions)
    return regular_stack_geometry(positions, [orientation] * n, [[2, 3]] * n)


def test_row_column_spacing_and_pixel_center_convention():
    affine = slice_affine_lps([10, 20, 30], [1, 0, 0, 0, 1, 0], [2, 3])
    np.testing.assert_allclose(transform_points([0, 4, 5], affine), [25, 28, 30])
    np.testing.assert_allclose(transform_points([0, 0, 0], affine), [10, 20, 30])


@pytest.mark.parametrize("orientation", [(1,0,0,0,1,0), (0,1,0,0,0,1), (0,0,1,1,0,0),
    (2 ** -.5,2 ** -.5,0,0,0,1)])
def test_oblique_sagittal_coronal_and_axial_round_trip(orientation):
    origin = np.array([23, -17, 40])
    normal = np.cross(orientation[:3], orientation[3:])
    positions = [origin + k * 1.25 * normal for k in (2, 0, 1)]
    result = stack(positions, orientation)
    assert result["order"].tolist() == [1, 2, 0]
    points = np.array([[0,0,0], [2,511,127], [.5,80.5,12.25]])
    affine = result["affine_lps"]
    np.testing.assert_allclose(inverse_points(transform_points(points, affine), affine), points, atol=1e-10)
    np.testing.assert_allclose(result["spacing_krc_mm"], [1.25,2,3])


@pytest.mark.parametrize("positions", [
    [[0,0,0]], [[0,0,0], [0,0,0]], [[0,0,0],[0,0,1],[0,0,3]],
    [[0,0,0],[.1,0,1]], [[0,0,0],[0,0,float("nan")]]])
def test_invalid_or_unsupported_stacks_fail_closed(positions):
    with pytest.raises(ValueError):
        stack(positions)


def test_bad_orientation_spacing_and_singular_inverse():
    with pytest.raises(ValueError):
        slice_affine_lps([0,0,0], [1,0,0,1,0,0], [1,1])
    with pytest.raises(ValueError):
        slice_affine_lps([0,0,0], [1,0,0,0,1,0], [-1,1])
    with pytest.raises(ValueError):
        inverse_points([0,0,0], np.zeros((4,4)))
    with pytest.raises(ValueError):
        regular_stack_geometry([[0,0,0],[0,0,1]],
            [[1,0,0,0,1,0],[0,1,0,1,0,0]], [[1,1],[1,1]])


def test_crop_and_resample_ledger_composition():
    native = stack([[10,20,30],[10,20,31]])["affine_lps"]
    # Model index = cropped index / 2; model->native adds crop after scale.
    model_to_native = np.diag([2.,2.,2.,1.])
    model_to_native[:3,3] = [0,4,7]
    model_to_lps = native @ model_to_native
    model_point = np.array([.25,10,12])
    world = transform_points(model_point, model_to_lps)
    np.testing.assert_allclose(inverse_points(world, native), [.5,24,31])
    np.testing.assert_allclose(inverse_points(world, model_to_lps), model_point)
