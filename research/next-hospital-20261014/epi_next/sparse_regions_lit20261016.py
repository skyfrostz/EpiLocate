"""Independent metadata/synthetic helpers; no IO, model, optimizer or runner.

Global exact area across a fixed K8 bag permits disconnected support. This is
engineering preparation, not a new HSPI/CPF implementation or medical result.
"""
import math

AREAS = (5, 10, 20)


def exact_bag_region(scores, valid, percent):
    """Rank K8 flattened grids jointly, stable member/row-major tie order.

    Cardinality is floor(percent * total valid / 100), not one quota per slice.
    Zero quota stays empty; no forced peak, connectivity or positive-score gate.
    """
    if percent not in AREAS or type(percent) is not int:
        raise ValueError('FIXED_5_10_20_AREA_REQUIRED')
    if len(scores) != 8 or len(valid) != 8:
        raise ValueError('ORIGINAL_K8_REQUIRED')
    if not scores[0] or any(len(x) != len(scores[0]) for x in scores + valid):
        raise ValueError('COMMON_NONEMPTY_FLAT_GRID_REQUIRED')
    ranked = []
    for member, (values, support) in enumerate(zip(scores, valid)):
        for pixel, (value, allowed) in enumerate(zip(values, support)):
            if type(allowed) is not bool or type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('FINITE_SCORES_BOOL_SUPPORT_REQUIRED')
            if allowed:
                ranked.append((-value, member, pixel))
    ranked.sort()
    quota = len(ranked) * percent // 100
    selected = [[False] * len(scores[0]) for _ in range(8)]
    for _, member, pixel in ranked[:quota]:
        selected[member][pixel] = True
    return selected, dict(valid_pixels=len(ranked), selected_pixels=quota,
                          percent=percent, reliable=False,
                          status='NONEMPTY_DIAGNOSTIC' if quota else 'EMPTY_NO_PADDING')


def fixed_target(original_logits, policy, declared_class=None):
    if len(original_logits) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in original_logits):
        raise ValueError('FINITE_ORIGINAL_BINARY_LOGITS_REQUIRED')
    if policy not in ('ORIGINAL_ARGMAX_FIXED', 'DECLARED_FIXED'):
        raise ValueError('FIXED_TARGET_REQUIRED')
    resolved = (0 if original_logits[0] >= original_logits[1] else 1) if policy == 'ORIGINAL_ARGMAX_FIXED' else declared_class
    if type(resolved) is not int or resolved not in (0, 1) or (declared_class is not None and declared_class != resolved):
        raise ValueError('DECLARED_RESOLVED_TARGET_MISMATCH')
    return resolved


def fidelity(original, perturbed, target):
    fixed_target(original, 'DECLARED_FIXED', target)
    fixed_target(perturbed, 'DECLARED_FIXED', target)
    delta = [b - a for a, b in zip(original, perturbed)]
    return dict(raw_bag_all_logits_ls=sum(x*x for x in delta),
                fixed_target=target, margin_drop=delta[1-target]-delta[target],
                common_shift=sum(delta)/2,
                reliable=False)


def mean_components(components):
    """Synthetic affine-component algebra only; never edits cached features."""
    if len(components) != 8:
        raise ValueError('ORIGINAL_K8_REQUIRED')
    for row in components:
        fixed_target(row, 'DECLARED_FIXED', 1)
    return [math.fsum(row[c] for row in components)/8 for c in range(2)]


def proposal_budget(candidate, translations_per_area=2, cam_readouts_reused=False):
    """Upper bounds for proposed full-K8 batches; no execution permission.

    C1: two baseline checks + 3 areas x (CAM/random/2 translations) x 2 actions.
    C2: two baselines + 48 updates + 18 final reads + 6 random + 24 translations
    + 6 CAM reads unless exact same-target C1 inputs/regions can be reused.
    """
    if type(translations_per_area) is not int or not 0 <= translations_per_area <= 2 or type(cam_readouts_reused) is not bool:
        raise ValueError('BOUNDED_EXPLICIT_TRANSLATION_REUSE_POLICY_REQUIRED')
    if candidate == 'C1_CAM_JOINT_READOUT':
        if cam_readouts_reused:
            raise ValueError('C1_HAS_NO_IMPLICIT_REUSE')
        forward, backward, updates = 2 + 6*(2+translations_per_area), 0, 0
    elif candidate == 'C2_HARD_JOINT_ADAPTATION':
        forward = 2 + 48 + 18 + 6 + 12*translations_per_area + (0 if cam_readouts_reused else 6)
        backward = updates = 48
    else:
        raise ValueError('UNKNOWN_CANDIDATE')
    return dict(status='SPEC_NOT_EXECUTABLE_NOT_APPROVED', encoder_batch_forward=forward,
                encoded_samples=8*forward, backward=backward, mask_updates=updates,
                model_updates=0, real_calls_actual=None)
