import numpy as np
import pytest

from epi_next.ref_support_qa import patch_support, native_support, verify_full_base_support

SAMPLING = "NEAREST_FLOOR_GRID;HALF_PIXEL_NATIVE_CELL"


def test_nondivisible_grid_boundaries_partition_without_gaps():
    counts = np.zeros((23, 29), int)
    for y in range(7):
        for x in range(9):
            mask = patch_support((23, 29), (7, 9), (y, x))
            # Independent integer boundary ceil(cell*size/grid), not floor edges.
            expected = np.zeros((23, 29), bool)
            expected[(y * 23 + 6)//7:((y+1)*23+6)//7,
                     (x * 29 + 8)//9:((x+1)*29+8)//9] = True
            assert np.array_equal(mask, expected)
            counts += mask
    assert (counts == 1).all()


def test_entire_base_patch_not_overlap_pixels():
    base = patch_support((23, 29), (7, 7), (0, 0))
    vote = patch_support((23, 29), (9, 9), (0, 0))
    assert (base & vote).sum() < base.sum()
    native = native_support(base, (51, 67))
    assert verify_full_base_support((23, 29), (7, 7), [(0, 0)], base, native, (51, 67), sampling=SAMPLING)['status'] == 'PASS'
    with pytest.raises(ValueError, match='mismatch'):
        verify_full_base_support((23, 29), (7, 7), [(0, 0)], base & vote,
                                 native_support(base & vote, (51, 67)), (51, 67), sampling=SAMPLING)


def test_native_halfpixel_border_oracle():
    model = patch_support((23, 29), (7, 9), (6, 8))
    expected = np.zeros((51, 67), bool)
    for y in range(51):
        for x in range(67):
            my = ((2*y+1)*23)//(2*51)
            mx = ((2*x+1)*29)//(2*67)
            expected[y,x] = model[my,mx]
    assert np.array_equal(native_support(model, (51, 67)), expected)
    assert expected[-1,-1]


def test_empty_export_and_explicit_convention():
    result = verify_full_base_support((23,29),(7,7),[],np.zeros((23,29),bool),
                                     np.zeros((51,67),bool),(51,67),sampling=SAMPLING)
    assert result['native_pixels'] == 0
    with pytest.raises(ValueError, match='convention'):
        verify_full_base_support((23,29),(7,7),[],np.zeros((23,29),bool),
                                 np.zeros((51,67),bool),(51,67),sampling='nearest-exact')
