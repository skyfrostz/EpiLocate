"""New synthetic scope counterexamples only; no prior R92/R103 suite rerun."""
import unittest
from epi_next.r106_mil_scope_audit import scope_witness, probability_from_margin


class ScopeWitnessTests(unittest.TestCase):
    def test_removal_changes_denominator_and_even_effect_sign(self):
        r = scope_witness([1.0] + [2.0]*7, 0.0, 0)
        self.assertEqual(r['fixed_zero_drop'], 0.125)
        self.assertEqual(r['renormalized_removal_drop'], -0.125)
        self.assertFalse(r['component_is_slice_disease_truth'])

    def test_bias_inclusive_positive_is_not_positive_replacement_support(self):
        r = scope_witness([-1.0]*8, 2.0, 0)
        self.assertEqual(r['component_margin'], 1.0)
        self.assertEqual(r['fixed_zero_drop'], -0.125)
        self.assertEqual(r['real_model_calls'], 0)

    def test_probability_of_mean_is_not_mean_of_probabilities(self):
        components = [8.0] + [-1.0]*7
        bag_p = probability_from_margin(sum(components)/8)
        avg_p = sum(map(probability_from_margin, components))/8
        self.assertGreater(bag_p, 0.5)
        self.assertLess(avg_p, 0.5)
        for terms, bias, index in [([0.0]*7, 0.0, 0),
                                   ([0.0]*7+[float('nan')], 0.0, 0),
                                   ([0.0]*8, 0.0, True)]:
            with self.assertRaises(ValueError):
                scope_witness(terms, bias, index)


if __name__ == '__main__':
    unittest.main()
