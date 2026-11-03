import math

import numpy as np
import pytest

from epi_next.data_eval import (budget_candidates, common_support,
    localization_metrics, patient_classification, summarize_patients, synthetic_smoke)


def test_budget_is_cap_and_ties_are_stable():
    scores = np.ones(100)
    support = np.ones(100, dtype=bool)
    reliable = np.arange(100) < 7
    for fraction, expected in [(0.05, 5), (0.1, 7), (0.2, 7)]:
        mask = budget_candidates(scores, reliable, support, fraction)
        assert np.flatnonzero(mask).tolist() == list(range(expected))
    assert not budget_candidates(scores, np.zeros(100, bool), support, .2).any()


def test_common_domain_is_shared_not_algorithm_success():
    a = np.arange(20) < 15
    b = np.arange(20) >= 5
    domain = common_support([a, b])
    assert domain.sum() == 10
    assert budget_candidates(np.ones(20), a, domain, .2).sum() == 2
    assert budget_candidates(np.ones(20), b, domain, .2).sum() == 2


@pytest.mark.parametrize("fraction", [0, -1, 1.1, math.nan, math.inf, True])
def test_bad_budget(fraction):
    with pytest.raises(ValueError):
        budget_candidates(np.ones(10), np.ones(10, bool), np.ones(10, bool), fraction)


def test_nonfinite_and_nonboolean_rejected():
    with pytest.raises(ValueError):
        budget_candidates([math.nan], [True], [True], .1)
    with pytest.raises(ValueError):
        budget_candidates([1], [1], [True], .1)
    with pytest.raises(ValueError):
        common_support([])


def test_incomplete_annotation_never_produces_complete_metrics():
    candidate = np.array([True, True, False, False])
    reference = np.array([True, False, True, False])
    result = localization_metrics(candidate, reference, np.ones(4, bool))
    assert result["observed_reference_coverage"] == .5
    assert result["dice"] is result["iou"] is result["precision"] is None
    assert result["false_positive_voxels"] is None
    result = localization_metrics(candidate, reference, np.ones(4, bool),
                                  annotation_complete=True)
    assert result["dice"] is None  # Clinical semantics is a separate gate.
    result = localization_metrics(candidate, reference, np.ones(4, bool),
                                  annotation_complete=True, clinical_semantics_verified=True)
    assert result["dice"] == .5 and result["iou"] == pytest.approx(1 / 3)
    assert result["false_positive_voxels"] == 1


def test_unknown_reference_and_empty_domain_are_not_perfect_results():
    empty = np.zeros(4, bool)
    for support, status in [(empty, "EMPTY_SUPPORT"), (~empty, "NO_OBSERVED_REFERENCE")]:
        result = localization_metrics(empty, empty, support,
            annotation_complete=True, clinical_semantics_verified=True)
        assert result["status"] == status
        assert result["observed_reference_coverage"] is None
        assert result["dice"] is None


def test_gt_outside_support_is_reported_and_candidate_rejected():
    support = np.array([True, False])
    gt = np.ones(2, bool)
    result = localization_metrics(support, gt, support)
    assert result["reference_voxels_outside_support"] == 1
    with pytest.raises(ValueError):
        localization_metrics(gt, gt, support)
    with pytest.raises(ValueError):
        localization_metrics(support, gt, support, annotation_complete="false")


def test_patient_failures_and_abstentions_remain_in_denominator():
    rows = [{"patient_id": "a", "status": "OK", "observed_reference_coverage": .5},
            {"patient_id": "b", "status": "FAILED", "observed_reference_coverage": None},
            {"patient_id": "c", "status": "NO_RELIABLE_RESPONSE", "observed_reference_coverage": 0}]
    result = summarize_patients(rows)
    assert result["patients_expected"] == 3
    assert result["patients_evaluable_reference"] == 2
    assert result["unavailable_rate"] == result["abstention_rate"] == 1 / 3
    assert result["conditional_patient_mean_observed_reference_coverage"] == .25
    with pytest.raises(ValueError):
        summarize_patients(rows + [rows[0]])
    rows[1]["observed_reference_coverage"] = 0
    with pytest.raises(ValueError):
        summarize_patients(rows)


def test_classification_ties_known_metrics_and_failed_denominator():
    rows = [{"patient_id": str(i), "label": y, "score": s}
            for i, (y, s) in enumerate([(0, .1), (0, .4), (1, .35), (1, .8), (1, None)])]
    result = patient_classification(rows)
    assert result["auroc"] == .75
    assert result["auprc_average_precision"] == pytest.approx(5 / 6)
    assert result["patients_expected"] == 5 and result["evaluable_fraction"] == .8
    for row in rows:
        row["score"] = 1
    result = patient_classification(rows[:4])
    assert result["auroc"] == result["auprc_average_precision"] == .5


def test_classification_single_class_duplicates_and_nan():
    assert patient_classification([])["status"] == "NO_EVALUABLE_PATIENTS"
    row = {"patient_id": "a", "label": 1, "score": .5}
    assert patient_classification([row])["status"] == "SINGLE_CLASS"
    with pytest.raises(ValueError):
        patient_classification([row, row])
    with pytest.raises(ValueError):
        patient_classification([{**row, "score": math.nan}])


def test_synthetic_coverage_no_budget_padding():
    smoke = synthetic_smoke()
    assert smoke["budget_results"]["0.1"]["candidate_voxels"] == 8
    assert smoke["budget_results"]["0.2"]["candidate_voxels"] == 8
    assert smoke["budget_results"]["0.05"]["observed_reference_coverage"] == 1
