"""Offline source-group metrics and signed F0 algebra; no encoder calls."""
from __future__ import annotations
import numpy as np


def finite(value):
    value = np.asarray(value, dtype=np.float64)
    if not np.isfinite(value).all():
        raise ValueError('NONFINITE_RESEARCH_VALUE')
    return value


def signed_f0(features, weight, bias, mean, scale):
    f, w, b, m, s = map(finite, (features, weight, bias, mean, scale))
    if f.shape != (1, 512, 4, 4, 4) or w.shape != (2, 512) or b.shape != (2,) or m.shape != (512,) or s.shape != (512,) or np.any(s <= 0):
        raise ValueError('F0_SHAPE_OR_SCALE')
    contribution = np.einsum('nfxyz,cf->ncxyz', f, w / s)
    effective_bias = b - np.sum(w * m / s, axis=1)
    gap = f.mean(axis=(2, 3, 4))
    logits = ((gap - m) / s) @ w.T + b
    rebuilt = contribution.mean(axis=(2, 3, 4)) + effective_bias
    error = np.abs(logits - rebuilt)
    if not np.allclose(logits, rebuilt, atol=1e-10, rtol=1e-12):
        raise ValueError('F0_LOGIT_RECONSTRUCTION')
    return contribution, effective_bias, logits, float(error.max())


def probability(logits):
    z = finite(logits)
    if z.ndim != 2 or z.shape[1] != 2:
        raise ValueError('BINARY_LOGITS_REQUIRED')
    e = np.exp(z - z.max(axis=1, keepdims=True))
    return e[:, 1] / e.sum(axis=1)


def wilson(k, n):
    if not n:
        return None
    z = 1.959963984540054
    p = k/n
    center = (p+z*z/(2*n))/(1+z*z/n)
    width = z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return [float(center-width), float(center+width)]


def binary_metrics(labels, scores, predictions=None):
    y, p = np.asarray(labels), finite(scores)
    if y.ndim != 1 or p.shape != y.shape or not len(y) or not np.isin(y, [0, 1]).all() or np.any((p < 0) | (p > 1)):
        raise ValueError('INVALID_BINARY_METRIC_INPUT')
    predicted = p > .5 if predictions is None else np.asarray(predictions, dtype=bool)
    if predicted.shape != y.shape:
        raise ValueError('PREDICTION_SHAPE')
    pos, neg = y == 1, y == 0
    tp, tn = int(np.sum(predicted & pos)), int(np.sum(~predicted & neg))
    np_, nn_ = int(pos.sum()), int(neg.sum())
    sensitivity, specificity = (tp/np_ if np_ else None), (tn/nn_ if nn_ else None)
    auc = ap = None
    if np_ and nn_:
        delta = p[pos, None]-p[None, neg]
        auc = float(np.mean((delta > 0)+.5*(delta == 0)))
    if np_:
        # Group equal scores: average precision, not trapezoidal PR area.
        cumulative_tp = cumulative_total = 0
        ap = 0.
        for score in np.unique(p)[::-1]:
            group = p == score
            new_tp = int(pos[group].sum())
            cumulative_tp += new_tp
            cumulative_total += int(group.sum())
            ap += new_tp/np_ * cumulative_tp/cumulative_total
    return dict(n=len(y), positives=np_, negatives=nn_, tp=tp, tn=tn,
                fp=nn_-tn, fn=np_-tp, AUROC=auc, AUPRC_average_precision=ap,
                sensitivity=sensitivity, specificity=specificity,
                balanced_accuracy=(sensitivity+specificity)/2 if np_ and nn_ else None,
                accuracy=(tp+tn)/len(y), threshold=.5, tie='Normal',
                Wilson95=dict(accuracy=wilson(tp+tn, len(y)), sensitivity=wilson(tp, np_), specificity=wilson(tn, nn_)),
                interval_applicability='conditional source-group binomial description only; clinical patient independence UNKNOWN',
                AUROC_AUPRC_interval=None,
                AUROC_AUPRC_interval_reason='no independent clinical patient sampling established; small exploratory cohort',
                undefined_reason=None if np_ and nn_ else 'SINGLE_CLASS_DENOMINATOR')


def baselines(train_labels, labels):
    train = np.asarray(train_labels)
    majority = int(np.sum(train == 1) > np.sum(train == 0))
    return {name: binary_metrics(labels, np.full(len(labels), value), np.full(len(labels), value))
            for name, value in [('train_majority', majority), ('constant_Normal', 0), ('constant_positive', 1)]}
