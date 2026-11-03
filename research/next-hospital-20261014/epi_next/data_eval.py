"""EPI-NEXT independent evaluation. No model, data, or GT files are loaded here.

Scores rank only algorithm-declared reliable candidates. The fixed common domain
defines every budget denominator; it must not depend on an algorithm's success.
Incomplete reference never licenses precision, Dice, or full-lesion recall.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from typing import Iterable, Mapping

import numpy as np

SUCCESS_STATUSES = frozenset({"OK", "PARTIAL_BUDGET", "NO_RELIABLE_RESPONSE"})


def _mask(value, shape=None, name="mask"):
    a = np.asarray(value)
    if a.dtype != np.bool_ or a.ndim == 0 or (shape is not None and a.shape != shape):
        raise ValueError(f"{name} must be a boolean array of matching shape")
    return a


def common_support(domains: Iterable[np.ndarray]) -> np.ndarray:
    """Intersect predeclared valid domains, before observing any predictions."""
    domains = list(domains)
    if not domains:
        raise ValueError("at least one domain is required")
    result = _mask(domains[0]).copy()
    for domain in domains[1:]:
        result &= _mask(domain, result.shape)
    return result


def budget_candidates(scores, reliable, support, fraction: float) -> np.ndarray:
    """Cap eligible voxels by floor(fraction * common-domain size), never pad.

    Ties use C-order flat index. Callers must establish reliability independently
    of GT; a positive CAM value alone is not an input-occlusion response.
    """
    if isinstance(fraction, bool) or not math.isfinite(fraction) or not 0 < fraction <= 1:
        raise ValueError("fraction must be finite and in (0, 1]")
    scores = np.asarray(scores, dtype=float)
    support = _mask(support, scores.shape, "support")
    reliable = _mask(reliable, scores.shape, "reliable")
    if not np.isfinite(scores[support]).all():
        raise ValueError("non-finite score in common support")
    indices = np.flatnonzero(reliable & support)
    order = np.lexsort((indices, -scores.ravel()[indices]))
    limit = math.floor(int(support.sum()) * fraction)
    result = np.zeros(scores.shape, dtype=bool)
    result.ravel()[indices[order[:limit]]] = True
    return result


def localization_metrics(candidate, reference, support, *, annotation_complete=False,
                         clinical_semantics_verified=False) -> dict:
    """Single patient's native-space reference comparison, restricted to support.

    Completeness and clinical semantic agreement are separately required for
    complete-reference metrics. Empty-reference coverage is undefined, not 1.
    GT outside the declared support is counted and never silently forgotten.
    """
    if type(annotation_complete) is not bool or type(clinical_semantics_verified) is not bool:
        raise ValueError("reference qualifications must be explicit booleans")
    support = _mask(support)
    candidate = _mask(candidate, support.shape, "candidate")
    reference = _mask(reference, support.shape, "reference")
    if np.any(candidate & ~support):
        raise ValueError("candidate lies outside common support")
    predicted = int(candidate.sum())
    positive = int((reference & support).sum())
    overlap = int((candidate & reference).sum())
    n = int(support.sum())
    complete = annotation_complete and clinical_semantics_verified
    result = {
        "support_voxels": n, "candidate_voxels": predicted,
        "reference_voxels_in_support": positive,
        "reference_voxels_outside_support": int((reference & ~support).sum()),
        "intersection_voxels": overlap,
        "actual_budget_fraction": predicted / n if n else None,
        "observed_reference_coverage": overlap / positive if positive else None,
        "observed_reference_hit": bool(overlap) if positive else None,
        "annotation_complete": annotation_complete,
        "clinical_semantics_verified": clinical_semantics_verified,
        "status": "EMPTY_SUPPORT" if not n else "OK" if positive else "NO_OBSERVED_REFERENCE",
        "complete_reference_metrics_status": "ELIGIBLE" if complete and n else "NOT_ELIGIBLE",
        "dice": None, "iou": None, "precision": None, "false_positive_voxels": None,
    }
    if complete and n:
        result.update(
            dice=2 * overlap / (predicted + positive) if predicted + positive else None,
            iou=overlap / (predicted + positive - overlap) if predicted + positive - overlap else None,
            precision=overlap / predicted if predicted else None,
            false_positive_voxels=predicted - overlap,
        )
    return result


def summarize_patients(records: Iterable[Mapping]) -> dict:
    """One record per expected patient, including failures and abstentions.

    Coverage mean is conditional on evaluable observed reference, explicitly
    separate from unavailable/abstaining proportions. Never count slices as n.
    """
    rows = list(records)
    ids = [r["patient_id"] for r in rows]
    if any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
        raise ValueError("patient IDs must be nonempty and unique; aggregate slices first")
    statuses = Counter(r["status"] for r in rows)
    values = []
    for row in rows:
        v = row.get("observed_reference_coverage")
        if v is not None:
            if not math.isfinite(v) or not 0 <= v <= 1:
                raise ValueError("coverage must be finite in [0, 1] or null")
            if row["status"] not in SUCCESS_STATUSES:
                raise ValueError("failed cases cannot carry successful coverage")
            values.append(v)
    n = len(rows)
    unavailable = sum(r["status"] not in SUCCESS_STATUSES for r in rows)
    abstentions = statuses["NO_RELIABLE_RESPONSE"]
    return {"patients_expected": n, "status_counts": dict(sorted(statuses.items())),
            "patients_evaluable_reference": len(values), "patients_unavailable": unavailable,
            "unavailable_rate": unavailable / n if n else None,
            "abstention_rate": abstentions / n if n else None,
            "partial_rate": statuses["PARTIAL_BUDGET"] / n if n else None,
            "conditional_patient_mean_observed_reference_coverage":
                math.fsum(values) / len(values) if values else None}


def patient_classification(records: Iterable[Mapping]) -> dict:
    """Binary patient AUROC and stepwise average precision with tied thresholds.

    Failed predictions use score=null and remain in the expected denominator.
    Unknown ground truth uses label=null. No calibration claim is made.
    """
    rows = list(records)
    ids = [r["patient_id"] for r in rows]
    if any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
        raise ValueError("classification requires unique nonempty patient IDs")
    valid = []
    for row in rows:
        label, score = row.get("label"), row.get("score")
        if label is not None and label not in (0, 1):
            raise ValueError("binary label must be 0, 1, or null")
        if score is not None and not math.isfinite(score):
            raise ValueError("score must be finite or null")
        if label is not None and score is not None:
            valid.append((int(label), float(score)))
    n = len(rows)
    result = {"patients_expected": n, "patients_evaluable": len(valid),
              "patients_unknown_label": sum(r.get("label") is None for r in rows),
              "patients_missing_score": sum(r.get("score") is None for r in rows),
              "evaluable_fraction": len(valid) / n if n else None,
              "auroc": None, "auprc_average_precision": None,
              "calibration_status": "NOT_ASSESSED", "status": "NO_EVALUABLE_PATIENTS"}
    if not valid:
        return result
    labels, scores = np.array(valid).T
    positives = int(labels.sum())
    negatives = len(labels) - positives
    if not positives or not negatives:
        result["status"] = "SINGLE_CLASS"
        return result
    # Threshold groups avoid arbitrary tie ordering in either metric.
    order = np.argsort(-scores, kind="stable")
    labels, scores = labels[order], scores[order]
    tp = fp = 0
    previous_tpr = previous_fpr = ap = auc = 0.0
    for end in np.r_[np.flatnonzero(np.diff(scores)) + 1, len(scores)]:
        start = tp + fp
        new_positive = int(labels[start:end].sum())
        tp += new_positive
        fp += int(end - start) - new_positive
        tpr, fpr = tp / positives, fp / negatives
        auc += (fpr - previous_fpr) * (tpr + previous_tpr) / 2
        ap += (tpr - previous_tpr) * tp / (tp + fp)
        previous_tpr, previous_fpr = tpr, fpr
    result.update(status="OK", auroc=auc, auprc_average_precision=ap)
    return result


def synthetic_smoke() -> dict:
    """Explicit synthetic numbers for protocol QA, never clinical evidence."""
    support = np.ones((10, 10), dtype=bool)
    scores = np.zeros((10, 10)); scores[2:4, 2:4] = 3
    scores[8:10, 8:10] = 2
    reference = np.zeros_like(support); reference[2:4, 2:4] = True
    budgets = {}
    for budget in (0.05, 0.1, 0.2):
        candidate = budget_candidates(scores, scores > 0, support, budget)
        budgets[str(budget)] = localization_metrics(candidate, reference, support)
    return {"experiment": "EPI-NEXT-DATA-EVAL-SYNTHETIC", "evidence_type": "SYNTHETIC",
            "clinical_validation": "NOT RUN", "budget_results": budgets,
            "classification": patient_classification([
                {"patient_id": "synthetic-a", "label": 1, "score": .8},
                {"patient_id": "synthetic-b", "label": 0, "score": .2},
                {"patient_id": "synthetic-c", "label": 1, "score": None}])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthetic", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps(synthetic_smoke(), indent=2, sort_keys=True, allow_nan=False))
