import numpy as np

from epi_next.data_eval import budget_candidates
from epi_next.evaluation_diagnostic import coverage, distribution, tie_diagnostic


def test_positive_gt_response_can_be_removed_by_budget_ranking():
    scores = np.array([[10., 9.], [1., 2.]])
    reliable = np.ones((2, 2), bool)
    reference = np.array([[False, False], [True, True]])
    selected = budget_candidates(scores, reliable, reliable, .5)
    assert coverage(reliable, reference) == 1
    assert coverage(selected, reference) == 0


def test_cutoff_plateau_records_exact_c_order_loss():
    scores = np.ones((2, 2)); reliable = np.ones((2, 2), bool)
    reference = np.array([[False, False], [True, True]])
    selected = budget_candidates(scores, reliable, reliable, .5)
    diagnosis = tie_diagnostic(scores, reliable, selected, reference)
    assert diagnosis["cutoff_splits_plateau"] is True
    assert diagnosis["eligible_at_cutoff"] == 4 and diagnosis["selected_at_cutoff"] == 2
    assert diagnosis["reference_pixels_at_cutoff"] == 2 and diagnosis["selected_reference_pixels_at_cutoff"] == 0


def test_absent_reference_remains_null_in_descriptive_aggregation():
    empty = np.zeros((2, 2), bool)
    assert coverage(empty, empty) is None
    assert distribution([None, None])["mean"] is None
    assert distribution([None, .3, .5])["mean"] == .4


def test_zero_candidate_is_not_randomly_padded_to_nominal_budget():
    support = np.ones((2, 2), bool)
    selected = budget_candidates(np.zeros((2, 2)), ~support, support, .5)
    assert not selected.any()
    assert tie_diagnostic(np.zeros((2, 2)), ~support, selected, support)["cutoff_score"] is None
