"""Synthetic arithmetic witness for fixed-K8 MIL explanation scopes.

No file access, model imports, head fitting, or medical evaluation. These
numbers describe an affine margin function, never slice disease labels.
"""
import math


def scope_witness(raw_margin_terms, effective_bias, index):
    if (len(raw_margin_terms) != 8 or type(index) is not int or not 0 <= index < 8
            or any(type(v) not in (int, float) or not math.isfinite(v)
                   for v in [*raw_margin_terms, effective_bias])):
        raise ValueError('eight finite real terms, finite bias and K8 index required')
    terms = list(raw_margin_terms)
    bag = effective_bias + math.fsum(terms) / 8
    component = effective_bias + terms[index]
    # Zero means a synthetic zero feature vector, not a blank CT or absent lung.
    fixed_zero = effective_bias + math.fsum(terms[:index] + terms[index+1:]) / 8
    renormalized = effective_bias + math.fsum(terms[:index] + terms[index+1:]) / 7
    return dict(bag_margin=bag, component_margin=component,
                fixed_zero_drop=bag-fixed_zero,
                renormalized_removal_drop=bag-renormalized,
                component_is_slice_disease_truth=False,
                real_model_calls=0)


def probability_from_margin(margin):
    if type(margin) not in (int, float) or not math.isfinite(margin):
        raise ValueError('finite margin required')
    e = math.exp(-abs(margin))
    return 1 / (1 + e) if margin >= 0 else e / (1 + e)
