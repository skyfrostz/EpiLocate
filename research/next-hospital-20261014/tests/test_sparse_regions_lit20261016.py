"""Prepared only: stdlib toy values; no patient/model/array/file IO.

Chief owns serial CPU test window. Do not invoke old generated suites here.
"""
import unittest
from epi_next.sparse_regions_lit20261016 import (
    exact_bag_region, fixed_target, fidelity, mean_components, proposal_budget,
)


class SyntheticSparseRegionTests(unittest.TestCase):
    def test_exact_global_area_ties_support_and_empty(self):
        scores = [[0.] * 10 for _ in range(8)]
        valid = [[True] * 10 for _ in range(8)]
        valid[0][0] = False
        for area, expected in [(5, 3), (10, 7), (20, 15)]:
            mask, meta = exact_bag_region(scores, valid, area)
            self.assertEqual(sum(sum(row) for row in mask), expected)
            self.assertEqual(meta['valid_pixels'], 79)
            self.assertFalse(mask[0][0])
            self.assertTrue(mask[0][1])
            self.assertFalse(meta['reliable'])
        mask, meta = exact_bag_region([[0.] for _ in range(8)], [[False] for _ in range(8)], 5)
        self.assertEqual(meta['status'], 'EMPTY_NO_PADDING')
        self.assertFalse(any(any(row) for row in mask))

    def test_multiple_regions_are_not_reduced_to_peak(self):
        scores = [[0.] * 10 for _ in range(8)]
        for member, pixel in [(0, 0), (0, 9), (7, 0), (7, 9)]:
            scores[member][pixel] = 3.
        mask, meta = exact_bag_region(scores, [[True]*10 for _ in range(8)], 5)
        self.assertEqual(meta['selected_pixels'], 4)
        self.assertEqual(sum(mask[0]), 2)
        self.assertEqual(sum(mask[7]), 2)
        self.assertFalse(any(any(row) for row in mask[1:7]))

    def test_fixed_target_flip_and_full_logits_translation(self):
        target = fixed_target([2., 0.], 'ORIGINAL_ARGMAX_FIXED')
        self.assertEqual(target, 0)
        row = fidelity([2., 0.], [-1., 3.], target)
        self.assertEqual(row['fixed_target'], 0)
        self.assertEqual(row['margin_drop'], 6.)
        translated = fidelity([2., 0.], [3., 1.], target)
        self.assertEqual(translated['margin_drop'], 0.)
        self.assertEqual(translated['raw_bag_all_logits_ls'], 2.)
        self.assertEqual(fixed_target([2., 0.], 'DECLARED_FIXED', 1), 1)
        with self.assertRaises(ValueError):
            fixed_target([2., 0.], 'ORIGINAL_ARGMAX_FIXED', 1)

    def test_joint_mean_has_cross_terms(self):
        original = [[0., 0.] for _ in range(8)]
        one = [row[:] for row in original];one[0][1] = 8.
        two = [row[:] for row in one];two[1][1] = 8.
        baseline = mean_components(original)
        self.assertEqual(fidelity(baseline, mean_components(one), 1)['raw_bag_all_logits_ls'], 1.)
        self.assertEqual(fidelity(baseline, mean_components(two), 1)['raw_bag_all_logits_ls'], 4.)
        # 4 != 1+1: do not transplant single-member K² loss to multiple members.
        other = [row[:] for row in original];other[1][1] = 8.
        a = fidelity(baseline, mean_components(one), 1)['margin_drop']
        b = fidelity(baseline, mean_components(other), 1)['margin_drop']
        joint = fidelity(baseline, mean_components(two), 1)['margin_drop']
        self.assertEqual(joint-a-b, 0.)
        # Independent slices have zero margin interaction; squared loss differs.

    def test_budgets_and_invalid_inputs(self):
        c1 = proposal_budget('C1_CAM_JOINT_READOUT')
        self.assertEqual((c1['encoder_batch_forward'], c1['encoded_samples']), (26, 208))
        c2 = proposal_budget('C2_HARD_JOINT_ADAPTATION')
        self.assertEqual((c2['encoder_batch_forward'], c2['encoded_samples'], c2['backward']), (104, 832, 48))
        self.assertIsNone(c2['real_calls_actual'])
        scores = [[0.] for _ in range(8)];valid = [[True] for _ in range(8)]
        for area in [True, 0, 30]:
            with self.assertRaises(ValueError):exact_bag_region(scores, valid, area)
        scores[0][0] = float('nan')
        with self.assertRaises(ValueError):exact_bag_region(scores, valid, 5)
        with self.assertRaises(ValueError):proposal_budget('C1_CAM_JOINT_READOUT', 3)


if __name__ == '__main__':
    unittest.main()
