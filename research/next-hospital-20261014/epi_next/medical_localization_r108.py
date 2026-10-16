"""R108 pure-array localization and evaluation. No loader/model/optimizer/IO.

Input scores are signed (8,H,W) floats. Selection never consults GT. Geometry
proof is supplied by DATA/INT; equal array shapes alone never qualify a metric.
"""
from collections import deque
import hashlib
import heapq
import math
import numpy as np

AREAS = (.05, .10, .20)
SEEDS = 3
OFFSETS = ((0, 1), (1, 0), (0, -1), (-1, 0), (0, 2), (2, 0),
           (0, -2), (-2, 0), (1, 1), (1, -1), (-1, 1), (-1, -1))
METRICS = ('dice', 'iou', 'known_positive_coverage',
           'candidate_in_gt_valid_fraction', 'object_hit_fraction')


def _grid(a, kind):
    if not isinstance(a, np.ndarray) or a.ndim != 3 or a.shape[0] != 8 or min(a.shape[1:]) < 1:
        raise ValueError('K8_NONEMPTY_H_W_ARRAY_REQUIRED')
    if kind == 'bool' and a.dtype != np.bool_:
        raise ValueError('STRICT_BOOL_ARRAY_REQUIRED')
    if kind == 'float' and (not np.issubdtype(a.dtype, np.floating) or not np.isfinite(a).all()):
        raise ValueError('FINITE_SIGNED_FLOAT_SCORES_REQUIRED')
    return a


def _same(*arrays):
    if len({a.shape for a in arrays}) != 1:
        raise ValueError('SAME_K8_GRID_REQUIRED')


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _array_sha(a):
    h = hashlib.sha256(str((a.shape, str(a.dtype))).encode())
    h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def _domain(support, roi, provenance):
    _grid(support, 'bool')
    if roi is None:
        if provenance is not None:
            raise ValueError('ROI_PROVENANCE_WITHOUT_ROI')
        return support, dict(kind='NO_ROI', condition='BASELINE')
    _grid(roi, 'bool');_same(support, roi)
    kinds = {'MANUAL_LUNG_MASK', 'DATASET_REFERENCE_LUNG_MASK', 'AUTOMATIC_MODEL_LUNG_MASK'}
    if not isinstance(provenance, dict) or provenance.get('kind') not in kinds:
        raise ValueError('EXPLICIT_ROI_SOURCE_REQUIRED')
    if not provenance.get('source_id') or not _sha(provenance.get('roi_sha256')):
        raise ValueError('ROI_SOURCE_AND_SHA_REQUIRED')
    if provenance['kind'] == 'AUTOMATIC_MODEL_LUNG_MASK' and any(
            not _sha(provenance.get(k)) for k in ('model_sha256', 'preprocess_sha256')):
        raise ValueError('AUTOMATIC_ROI_MODEL_PREPROCESS_BINDING_REQUIRED')
    return support & roi, {**provenance,
        'condition': 'AUTOMATIC_PREDICTION' if provenance['kind'].startswith('AUTOMATIC') else 'REFERENCE_CONDITION_OR_UPPER_BOUND',
        'roi_pixels_outside_support': int(np.count_nonzero(roi & ~support))}


def _setup(scores, support, alpha, roi, provenance):
    _grid(scores, 'float');_grid(support, 'bool');_same(scores, support)
    if type(alpha) is not float or alpha not in AREAS:
        raise ValueError('PRELOCKED_ALPHA_05_10_20_REQUIRED')
    domain, origin = _domain(support, roi, provenance)
    n = int(support.sum());percent = {a: p for a, p in zip(AREAS, (5, 10, 20))}[alpha]
    quota = n * percent // 100
    ids = np.flatnonzero(domain)
    # flatnonzero is slice/row/column ordered; stable sort preserves ties.
    order = ids[np.argsort(-scores.ravel()[ids], kind='stable')]
    info = dict(alpha=alpha, quota=quota, full_support_pixels=n,
                candidate_domain_pixels=len(ids), roi=origin,
                area_denominator='ORIGINAL_FULL_BAG_SUPPORT', reliable=False,
                fixed_target_class=1, target_policy='DECLARED_FIXED',
                score_semantics='SIGNED_CLASS1_MINUS_CLASS0_SOURCE_MARGIN_CAM_NOT_INFECTION_PROBABILITY')
    return domain, order, info


def _selection(mask, info, method, reason=None):
    status = 'NOT_EVALUABLE' if mask is None else 'EMPTY_NO_PADDING' if info['quota'] == 0 else 'CANDIDATE_ONLY'
    return dict(method=method, status=status, reason=reason, mask=mask, **info,
                selected_pixels=None if mask is None else int(mask.sum()),
                per_slice_pixels=None if mask is None else mask.sum((1, 2)).astype(int).tolist(),
                full_support_fraction=None if mask is None or not info['full_support_pixels'] else float(mask.sum())/info['full_support_pixels'],
                roi_domain_fraction=None if mask is None or not info['candidate_domain_pixels'] else float(mask.sum())/info['candidate_domain_pixels'])


def cam_toparea(scores, support, alpha, *, roi=None, roi_provenance=None):
    """B0 global top-k. Negative scores remain eligible; no ReLU/GT threshold."""
    domain, order, info = _setup(scores, support, alpha, roi, roi_provenance)
    if len(order) < info['quota']:
        return _selection(None, info, 'B0_CAM_TOPAREA', 'ROI_OR_DOMAIN_SMALLER_THAN_FULL_BAG_QUOTA')
    mask = np.zeros(domain.shape, dtype=bool);mask.ravel()[order[:info['quota']]] = True
    return _selection(mask, info, 'B0_CAM_TOPAREA')


def _neighbors(flat, shape, eight=False):
    s, y, x = np.unravel_index(flat, shape)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if not (dy or dx) or (not eight and abs(dy)+abs(dx) != 1):
                continue
            yy, xx = y+dy, x+dx
            if 0 <= yy < shape[1] and 0 <= xx < shape[2]:
                yield int((s*shape[1]+yy)*shape[2]+xx)


def cam_connected(scores, support, alpha, *, roi=None, roi_provenance=None):
    """B1 <=3 nonadjacent seeds, score-priority four-neighbor growth.

    Seeds are the first three stable-ranked eligible pixels not four-adjacent
    to an earlier seed. Grow all frontiers jointly; touching regions merge.
    No cross-slice edge, crop, quota reduction, reseeding or GT inspection.
    Capacity failure returns no mask, never a smaller-area successful output.
    """
    domain, order, info = _setup(scores, support, alpha, roi, roi_provenance)
    info.update(adjacency='2D_4', max_seeds=SEEDS, cross_slice_edges=False,
                merge_rule='touching growth regions merge; no post-hoc removal')
    if len(order) < info['quota']:
        return _selection(None, info, 'B1_CAM_CONNECTED', 'ROI_OR_DOMAIN_SMALLER_THAN_FULL_BAG_QUOTA')
    mask = np.zeros(domain.shape, dtype=bool)
    if not info['quota']:
        info['seeds'] = []
        return _selection(mask, info, 'B1_CAM_CONNECTED')
    seeds = [];forbidden = set()
    for raw in order:
        i = int(raw)
        if i not in forbidden:
            seeds.append(i);forbidden.add(i);forbidden.update(_neighbors(i, domain.shape))
            if len(seeds) == min(SEEDS, info['quota']):
                break
    info['seeds'] = [list(map(int, np.unravel_index(i, domain.shape))) for i in seeds]
    chosen = mask.ravel();allowed = domain.ravel();values = scores.ravel()
    queued = np.zeros(mask.size, dtype=bool);frontier = []
    def push(i):
        if allowed[i] and not chosen[i] and not queued[i]:
            queued[i] = True;heapq.heappush(frontier, (-float(values[i]), i))
    for i in seeds:
        chosen[i] = True
    for i in seeds:
        for j in _neighbors(i, mask.shape):push(j)
    count = len(seeds)
    while count < info['quota'] and frontier:
        _, i = heapq.heappop(frontier)
        if chosen[i]:continue
        chosen[i] = True;count += 1
        for j in _neighbors(i, mask.shape):push(j)
    if count != info['quota']:
        info['reachable_selected_pixels'] = count
        return _selection(None, info, 'B1_CAM_CONNECTED', 'FIXED_SEED_COMPONENT_CAPACITY_BELOW_QUOTA')
    info['growth_steps'] = count-len(seeds)
    return _selection(mask, info, 'B1_CAM_CONNECTED')


def nested_random(support, *, roi=None, roi_provenance=None):
    """One PCG64 seed17 permutation shared by all three fixed area controls."""
    domain, origin = _domain(support, roi, roi_provenance)
    ids = np.random.Generator(np.random.PCG64(17)).permutation(np.flatnonzero(domain))
    n = int(support.sum());rows = []
    for alpha, percent in zip(AREAS, (5, 10, 20)):
        info = dict(alpha=alpha, quota=n*percent//100, full_support_pixels=n,
                    candidate_domain_pixels=len(ids), roi=origin,
                    area_denominator='ORIGINAL_FULL_BAG_SUPPORT', reliable=False, seed=17)
        mask = None
        if len(ids) >= info['quota']:
            mask = np.zeros(support.shape, dtype=bool);mask.ravel()[ids[:info['quota']]] = True
        rows.append(_selection(mask, info, 'RANDOM_NESTED', None if mask is not None else 'ROI_OR_DOMAIN_SMALLER_THAN_FULL_BAG_QUOTA'))
    return rows


def shape_translations(mask, support, *, roi=None, roi_provenance=None):
    """At most2 rigid whole-bag in-plane shifts from 12 prelocked offsets.

    Identical dy/dx for all8. No wrap/crop/rescale or alternative shape. A
    missing control means no feasible shift in this finite neighborhood only.
    """
    _grid(mask, 'bool');_grid(support, 'bool');_same(mask, support)
    domain, _ = _domain(support, roi, roi_provenance)
    if np.any(mask & ~domain):raise ValueError('REGION_OUTSIDE_CANDIDATE_DOMAIN')
    shifts = [];attempted = []
    if not mask.any():
        return dict(status='NOT_EVALUABLE', reason='EMPTY_REGION', controls=[], requested=2, missing=2)
    s, y, x = np.nonzero(mask)
    permutation = np.random.Generator(np.random.PCG64(17)).permutation(len(OFFSETS))
    for i in permutation:
        dy, dx = OFFSETS[int(i)];yy, xx = y+dy, x+dx
        inside = bool((yy >= 0).all() and (yy < mask.shape[1]).all() and (xx >= 0).all() and (xx < mask.shape[2]).all())
        legal = inside and bool(domain[s, yy, xx].all())
        attempted.append(dict(dy=dy, dx=dx, legal=legal))
        if legal:
            moved = np.zeros_like(mask);moved[s, yy, xx] = True
            shifts.append(dict(dy=dy, dx=dx, mask=moved, pixels=int(moved.sum())))
            if len(shifts) == 2:break
    return dict(status='COMPLETE' if len(shifts) == 2 else 'MISSING_CONTROL',
                reason=None if len(shifts) == 2 else 'NO_MORE_FEASIBLE_PRELOCKED_TRANSLATIONS',
                seed=17, requested=2, missing=2-len(shifts), controls=shifts,
                attempted=attempted, offset_neighborhood=[list(x) for x in OFFSETS])


def binding_gate(binding, shape):
    """Check declared provenance only. Does not verify geometry from pixels."""
    if not isinstance(binding, dict):return 'MISSING_BINDING'
    a, b, grid = (binding.get(k, {}) for k in ('input', 'reference', 'grid'))
    keys = ('case_id', 'source_namespace', 'source_version', 'input_sha256',
            'native_geometry_sha256', 'fixed8_native_indices')
    if not all(isinstance(x, dict) for x in (a, b, grid)):return 'INVALID_BINDING'
    for key in keys:
        if key not in a or key not in b or a[key] is None or b[key] is None:return 'UNKNOWN_IDENTITY'
        if a[key] != b[key]:return 'INPUT_REFERENCE_IDENTITY_CONFLICT'
    if any(not isinstance(a[k], str) or a[k] in ('', 'UNKNOWN') for k in keys[:3]):return 'UNKNOWN_IDENTITY'
    if any(not _sha(a[k]) for k in ('input_sha256', 'native_geometry_sha256')) or not _sha(b.get('gt_sha256')):
        return 'INVALID_ASSET_SHA'
    zs = a['fixed8_native_indices']
    if not isinstance(zs, list) or len(zs) != 8 or any(type(z) is not int or z < 0 for z in zs) or len(set(zs)) != 8:return 'INVALID_FIXED8_IDENTITY'
    if grid.get('shape') != list(shape) or grid.get('geometry_qa') != 'PASS':return 'GEOMETRY_NOT_VERIFIED'
    if grid.get('space') not in ('NATIVE_FIXED8_GRID', 'MODEL_GRID') or any(
            not _sha(grid.get(k)) for k in ('eval_grid_sha256', 'transform_chain_sha256')):
        return 'GRID_TRANSFORM_PROOF_MISSING'
    if binding.get('evidence_type') not in ('GENERATED_ONLY', 'EXTERNALLY_VERIFIED_REFERENCE'):
        return 'REFERENCE_EVIDENCE_NOT_DECLARED'
    return None


def objects_2d8(mask, prediction):
    """Known-positive 2D8CC objects in each sampled plane; never K8 3D lesions."""
    _grid(mask, 'bool');_grid(prediction, 'bool');_same(mask, prediction)
    visited = np.zeros(mask.size, dtype=bool);positive = mask.ravel();pred = prediction.ravel();objects = []
    for raw in np.flatnonzero(positive):
        start = int(raw)
        if visited[start]:continue
        visited[start] = True;queue = deque([start]);area = hit = 0
        while queue:
            i = queue.popleft();area += 1;hit += int(pred[i])
            for j in _neighbors(i, mask.shape, eight=True):
                if positive[j] and not visited[j]:visited[j] = True;queue.append(j)
        objects.append(dict(slice_index=int(np.unravel_index(start, mask.shape)[0]),
                            object_index=len(objects), pixels=area, covered_pixels=hit,
                            coverage=hit/area, hit=hit > 0))
    return dict(kind='FIXED8_PLANE_2D8CC_REFERENCE_OBJECTS_NOT_3D_LESIONS',
                count=len(objects), hit_count=sum(x['hit'] for x in objects), objects=objects)


def failure_case(case_id, reason, *, status='NOT_EVALUABLE'):
    return dict(case_id=case_id, status=status, reason=reason,
                metrics={k: None for k in METRICS}, counts=None, objects=None)


def evaluate_case(prediction, gt, prediction_domain, reference_domain, fov, *,
                  case_id, reference_kind, binding):
    """Aggregate all8 planes first. Unknown/reference/FOV domains explicit.

    COMPLETE means complete only within reference_domain, not whole scan.
    Partial references define positive coverage only, never FP/Dice/IoU.
    Empty GT+empty prediction has undefined Dice/IoU, not a rewarded1.
    """
    try:
        for a in (prediction, gt, prediction_domain, reference_domain, fov):_grid(a, 'bool')
        _same(prediction, gt, prediction_domain, reference_domain, fov)
    except (ValueError, TypeError) as exc:return failure_case(case_id, str(exc))
    reason = binding_gate(binding, prediction.shape)
    if reason:return failure_case(case_id, reason)
    if case_id != binding['input']['case_id']:return failure_case(case_id, 'CASE_ID_CONFLICT')
    if reference_kind not in ('COMPLETE_INFECTION_MASK', 'PARTIAL_INFECTION_REFERENCE'):
        return failure_case(case_id, 'UNKNOWN_REFERENCE_COMPLETENESS')
    ref = binding['reference']
    expected = 'CONFIRMED_COMPLETE' if reference_kind == 'COMPLETE_INFECTION_MASK' else 'KNOWN_POSITIVES_BACKGROUND_UNKNOWN'
    if ref.get('kind') != reference_kind or ref.get('completeness') != expected:
        return failure_case(case_id, 'REFERENCE_COMPLETENESS_BINDING_CONFLICT')
    if np.any(prediction & ~prediction_domain):return failure_case(case_id, 'CANDIDATE_OUTSIDE_DECLARED_PREDICTION_DOMAIN')
    if np.any(gt & ~reference_domain):return failure_case(case_id, 'GT_POSITIVES_OUTSIDE_DECLARED_REFERENCE_DOMAIN')
    valid_reference = reference_domain & fov
    evaluation = prediction_domain & valid_reference
    if not evaluation.any():return failure_case(case_id, 'EMPTY_COMMON_KNOWN_FOV_DOMAIN')
    known_gt = gt & valid_reference
    true = int(np.count_nonzero(prediction & gt & evaluation))
    positives = int(np.count_nonzero(known_gt));observed_positives = int(np.count_nonzero(gt & evaluation))
    selected = int(prediction.sum());pred_e = int(np.count_nonzero(prediction & evaluation))
    complete = reference_kind == 'COMPLETE_INFECTION_MASK'
    fp = pred_e-true if complete else None
    fn = observed_positives-true if complete else None
    denom = pred_e+observed_positives
    dice = 2*true/denom if complete and denom else None
    union = pred_e+observed_positives-true
    iou = true/union if complete and union else None
    objects = objects_2d8(known_gt, prediction)
    metrics = dict(dice=dice, iou=iou, known_positive_coverage=true/positives if positives else None,
                   candidate_in_gt_valid_fraction=pred_e/selected if selected else None,
                   object_hit_fraction=objects['hit_count']/objects['count'] if objects['count'] else None)
    counts = dict(selected_pixels=selected, true_positive_known_pixels=true,
                  gt_positive_in_fov=positives, gt_positive_in_common_domain=observed_positives,
                  false_positive_known_pixels=fp, false_negative_known_pixels=fn,
                  prediction_domain_pixels=int(prediction_domain.sum()),
                  gt_valid_domain_pixels=int(reference_domain.sum()), fov_pixels=int(fov.sum()),
                  common_evaluation_pixels=int(evaluation.sum()),
                  candidate_outside_gt_valid_fov=selected-pred_e,
                  gt_positive_outside_fov=int(np.count_nonzero(gt & ~fov)),
                  gt_positive_unpredicted_in_fov=positives-observed_positives)
    return dict(case_id=case_id, status='EVALUATED_COMPLETE_DOMAIN' if complete else 'EVALUATED_PARTIAL_COVERAGE_ONLY',
                reason=None, reference_kind=reference_kind, metrics=metrics, counts=counts, objects=objects,
                evidence_type=binding['evidence_type'],
                provenance=dict(input_identity={k: binding['input'][k] for k in (
                    'case_id', 'source_namespace', 'source_version', 'input_sha256',
                    'native_geometry_sha256', 'fixed8_native_indices')},
                    gt_sha256=ref['gt_sha256'], grid=binding['grid'].copy()),
                domains=dict(prediction_domain_sha256=_array_sha(prediction_domain),
                             reference_domain_sha256=_array_sha(reference_domain), fov_sha256=_array_sha(fov),
                             candidate_array_sha256=_array_sha(prediction), gt_array_sha256=_array_sha(gt)),
                metric_scope='COMMON_PREDICTED_REFERENCE_FOV_DOMAIN',
                coverage_scope='ALL_KNOWN_GT_POSITIVES_IN_FOV_OF_FIXED8',
                empty_gt_state='NONEMPTY' if observed_positives else 'EMPTY_GT_NONEMPTY_PRED' if pred_e else 'EMPTY_GT_EMPTY_PRED',
                unknown_is_background=False, scan_outside_fixed8='NOT_EVALUATED',
                full_scan_sampling_coverage=None, geometry_proof='EXTERNAL_METADATA_GATE_ONLY')


def summarize_cases(results):
    """Macro over defined case-level values; keep every failure and denominator."""
    ids = [x['case_id'] for x in results]
    if len(set(ids)) != len(ids):raise ValueError('DUPLICATE_CASE_ID')
    if any(not x['status'].startswith('EVALUATED_') and any(v is not None for v in x['metrics'].values()) for x in results):
        raise ValueError('FAILED_OR_UNKNOWN_METRIC_MUST_STAY_NULL')
    macro = {}
    for key in METRICS:
        values = [x['metrics'][key] for x in results if x['metrics'][key] is not None]
        if any(not math.isfinite(v) for v in values):raise ValueError('NONFINITE_METRIC')
        macro[key] = dict(value=math.fsum(values)/len(values) if values else None,
                          defined_cases=len(values), undefined_cases=len(results)-len(values))
    states = {}
    for x in results:states[x['status']] = states.get(x['status'], 0)+1
    return dict(case_count=len(results), status_counts=states, macro=macro,
                cases=results, unit='CASE_NOT_SLICE_OR_PATIENT_INDEPENDENCE_CLAIM')


def b2_protocol():
    """Finite proposed neighbor protocol only; deliberately no model search."""
    return dict(status='SPEC_NOT_EXECUTABLE', initialization='B0_OR_B1_PRELOCKED_BEFORE_GT',
                areas=list(AREAS), neighborhood='one selected boundary pixel swapped with one unselected 2D4 neighbor; same slice/support/quota',
                candidates_per_area=4, total_proposal_evaluations=12, seed=17,
                fixed_target='DECLARED_FIXED_INFECTION_MARGIN1_MINUS0',
                score='actual full fixed8 input keep margin; no cached-feature deletion',
                gt_used_in_search=False, stop='12 proposals or admitted time/call cap; no automatic extension',
                real_model_calls_actual=None, budget_owner='ENC explicit full-BAG accounting required before authorization')
