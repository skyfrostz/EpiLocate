"""R122 in-memory first-case bridge to frozen R108 B0 and metrics.

No loader, model, transform or permission check lives here. Qualification and
spatial proof are external declarations, not independently verified evidence.
Array digests use the frozen R108 shape/dtype/C-byte convention. GENERATED_ONLY
fixtures can exercise the contract but cannot establish real qualification.
"""
import numpy as np
from . import medical_localization_r108 as core

CASE_ID = 'coronacases_001'
ARCHIVES = dict(
    CT='0000000000000000000000000000000000000000000000000000000000000000',
    GT='0000000000000000000000000000000000000000000000000000000000000000')
IDENTITY = ('case_id', 'source_namespace', 'source_version', 'input_sha256',
            'native_geometry_sha256', 'fixed8_native_indices')
PLANE_IDENTITY = IDENTITY + ('native_definition', 'selected_original_nifti_Z', 'selected_canonical_Z')
SCORE_SEMANTICS = 'SIGNED_CLASS1_MINUS_CLASS0_SOURCE_MARGIN_CAM_NOT_INFECTION_PROBABILITY'
PERCENTS = ('5', '10', '20')


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _known(value):
    return isinstance(value, str) and value.strip() not in ('', 'UNKNOWN')


def _blocked(reason):
    rows = {p: core.failure_case(CASE_ID, reason, status='BLOCKED') for p in PERCENTS}
    return dict(case_id=CASE_ID, status='BLOCKED', reason=reason, areas=rows,
                case_macro_by_area={p: core.summarize_cases([r]) for p, r in rows.items()},
                full_scan_sampling_coverage=None, real_execution_authorized=False)


def evaluate_first_case(qualification, cam, scores, model_support, gt,
                        reference_domain, fov, native_candidates):
    """Check supplied identities/digests, then evaluate each fixed B0 area.

    native_candidates['5'/'10'/'20'] contains a bool native_prediction and a
    mapping dict. Mapping is supplied by the spatial owner, never inferred
    from equal shapes. Native prediction_domain is the original full plane,
    not the selected region or an ROI. Native area need not equal model area.
    No area averaging and no inference about the remainder of the CT scan.
    """
    try:
        q = qualification
        _require(isinstance(q, dict) and isinstance(cam, dict), 'METADATA_DICT_REQUIRED')
        _require(q.get('qualification_status') == 'PASS', 'QUALIFICATION_NOT_PASS')
        _require(core._sha(q.get('qualification_receipt_sha256')), 'QUALIFICATION_RECEIPT_SHA_REQUIRED')
        _require(q.get('case_id') == CASE_ID, 'FIXED_CASE_CONFLICT')
        _require(q.get('ct_archive_sha256') == ARCHIVES['CT'] and
                 q.get('gt_archive_sha256') == ARCHIVES['GT'], 'FIXED_ARCHIVE_IDENTITY_CONFLICT')
        for key in ('source_namespace', 'source_version', 'patient_group_id',
                    'patient_group_provenance', 'input_hash_role', 'gt_hash_role',
                    'reference_extent', 'label_mapping_provenance'):
            _require(_known(q.get(key)), 'MISSING_QUALIFIED_' + key.upper())
        shape = q.get('native_shape_zyx')
        _require(isinstance(shape, list) and len(shape) == 3 and
                 all(type(n) is int and n > 0 for n in shape) and shape[0] >= 8,
                 'ORIGINAL_NATIVE_SHAPE_REQUIRED')
        zs = [(2*j+1)*shape[0]//16 for j in range(8)]
        supplied_zs = q.get('fixed8_native_indices')
        _require(isinstance(supplied_zs, list) and len(supplied_zs) == 8 and
                 all(type(z) is int for z in supplied_zs) and supplied_zs == zs,
                 'ORIGINAL_FIXED8_CENTER_ORDER_REQUIRED')
        _require(q.get('native_definition') == 'ORIGINAL_NIFTI_XYZ_TRANSPOSED_ZYX_NO_FLIPS' and
                 q.get('original_shape_XYZ') == shape[::-1] and
                 q.get('selected_original_nifti_Z') == zs, 'ORIGINAL_NIFTI_PLANE_BINDING_REQUIRED')
        canonical = q.get('selected_canonical_Z')
        _require(isinstance(canonical, list) and len(canonical) == 8 and
                 all(type(z) in (int, float) and np.isfinite(z) for z in canonical),
                 'CANONICAL_PLANE_MAPPING_METADATA_REQUIRED')
        for a in (gt, reference_domain, fov):
            core._grid(a, 'bool')
            _require(a.shape == (8, shape[1], shape[2]), 'NATIVE_FIXED8_SHAPE_CONFLICT')
        for a, key in ((gt, 'fixed8_gt_bool_sha256'),
                       (reference_domain, 'fixed8_reference_domain_sha256'),
                       (fov, 'fixed8_fov_sha256')):
            _require(q.get(key) == core._array_sha(a), 'QUALIFIED_ARRAY_DIGEST_CONFLICT:' + key)
        pairs = {'COMPLETE_INFECTION_MASK': 'CONFIRMED_COMPLETE',
                 'PARTIAL_INFECTION_REFERENCE': 'KNOWN_POSITIVES_BACKGROUND_UNKNOWN'}
        kind = q.get('reference_kind')
        _require(kind in pairs and q.get('annotation_completeness') == pairs[kind],
                 'REFERENCE_COMPLETENESS_NOT_QUALIFIED')
        binding = dict(input={k: q[k] for k in IDENTITY},
                       reference={k: q[k] for k in IDENTITY}, evidence_type=q.get('evidence_type'),
                       grid=dict(shape=list(gt.shape), geometry_qa=q.get('geometry_qa'),
                                 space='NATIVE_FIXED8_GRID', eval_grid_sha256=q.get('eval_grid_sha256'),
                                 transform_chain_sha256=q.get('transform_chain_sha256')))
        binding['reference'].update(gt_sha256=q.get('gt_sha256'), kind=kind,
                                    completeness=q['annotation_completeness'])
        reason = core.binding_gate(binding, gt.shape)
        _require(reason is None, reason)
        _require(all(cam.get(k) == q[k] for k in PLANE_IDENTITY), 'CAM_INPUT_IDENTITY_CONFLICT')
        _require(cam.get('evidence_type') == q['evidence_type'], 'CAM_REFERENCE_EVIDENCE_CONFLICT')
        _require(cam.get('target_policy') == 'DECLARED_FIXED' and
                 type(cam.get('fixed_target_class')) is int and cam['fixed_target_class'] == 1 and
                 cam.get('score_semantics') == SCORE_SEMANTICS and
                 cam.get('negative_scores_clipped') is False, 'FIXED_SIGNED_TARGET_CONFLICT')
        for key in ('model_sha256', 'preprocess_sha256', 'model_adapter_sha256', 'runtime_sha256'):
            _require(core._sha(cam.get(key)), 'CAM_RUNTIME_BINDING_MISSING:' + key)
        logits = cam.get('original_logits')
        _require(isinstance(logits, list) and len(logits) == 2 and
                 all(type(x) in (int, float) and np.isfinite(x) for x in logits),
                 'ORIGINAL_BINARY_LOGITS_REQUIRED')
        predicted = int(np.argmax(logits))
        _require(type(cam.get('original_predicted_class')) is int and
                 cam['original_predicted_class'] == predicted, 'ORIGINAL_PREDICTION_CONFLICT')
        core._grid(scores, 'float');core._grid(model_support, 'bool')
        core._same(scores, model_support)
        # Frozen ENC signed_margin_scores emits FP64; casting can change ties.
        _require(scores.shape == (8, 224, 224) and scores.dtype == np.float64,
                 'FROZEN_R18_MODEL_GRID_8_224_224_FLOAT64_SCORES_REQUIRED')
        _require(model_support.all(), 'FIRST_B0_REQUIRES_ORIGINAL_FULL_MODEL_SUPPORT_NO_ROI')
        _require(cam.get('scores_sha256') == core._array_sha(scores) and
                 cam.get('model_support_sha256') == core._array_sha(model_support),
                 'CAM_ARRAY_DIGEST_CONFLICT')
        _require(isinstance(native_candidates, dict) and set(native_candidates) == set(PERCENTS),
                 'EXACT_THREE_PRELOCKED_AREAS_REQUIRED')
        prediction_domain = np.ones(gt.shape, dtype=bool)
        domain_sha = core._array_sha(prediction_domain)
        prepared = {}
        for p, alpha in zip(PERCENTS, core.AREAS):
            selection = core.cam_toparea(scores, model_support, alpha)
            model_sha = core._array_sha(selection['mask'])
            candidate = native_candidates[p]
            native = candidate['native_prediction'];mapping = candidate['mapping']
            core._grid(native, 'bool');core._same(native, gt)
            _require(all(mapping.get(k) == q[k] for k in PLANE_IDENTITY), 'NATIVE_MAPPING_IDENTITY_CONFLICT')
            _require(all(mapping.get(k) == q[k] for k in ('eval_grid_sha256', 'transform_chain_sha256')),
                     'NATIVE_MAPPING_GRID_CONFLICT')
            _require(mapping.get('model_mask_sha256') == model_sha and
                     mapping.get('native_prediction_sha256') == core._array_sha(native) and
                     mapping.get('prediction_domain_sha256') == domain_sha,
                     'NATIVE_MAPPING_MASK_OR_DOMAIN_DIGEST_CONFLICT')
            _require(mapping.get('method') == 'PER_NATIVE_PLANE_NEAREST_BINARY_NO_K8_INTERPOLATION',
                     'PER_NATIVE_PLANE_MAPPING_REQUIRED')
            prepared[p] = (selection, model_sha, native, mapping)
        areas = {}
        for p, (selection, model_sha, native, mapping) in prepared.items():
            result = core.evaluate_case(native, gt, prediction_domain, reference_domain, fov,
                                        case_id=CASE_ID, reference_kind=kind, binding=binding)
            areas[p] = dict(selection={k: v for k, v in selection.items() if k != 'mask'},
                            model_mask_sha256=model_sha, mapping=mapping.copy(), evaluation=result,
                            model_selected_pixels=selection['selected_pixels'],
                            native_selected_pixels=int(native.sum()),
                            native_full_plane_fraction=float(native.sum())/native.size,
                            native_fraction_is_not_model_quota=True)
        return dict(case_id=CASE_ID, status='EVALUATED_FIXED_AREAS' if all(
                        r['evaluation']['status'].startswith('EVALUATED_') for r in areas.values()) else 'NOT_EVALUABLE',
                    evidence_type=q['evidence_type'], areas=areas,
                    qualification_receipt_sha256=q['qualification_receipt_sha256'],
                    original_logits=list(logits), original_predicted_class=predicted,
                    score_dtype=str(scores.dtype), scores_sha256=core._array_sha(scores),
                    fixed_target_class=1, target_policy='DECLARED_FIXED',
                    denominators=dict(cases=1, sampled_native_planes=8, native_z=zs,
                        selected_canonical_Z=list(canonical),
                        known_reference_planes=int(reference_domain.any((1, 2)).sum()),
                        object_unit='PER_PLANE_2D8CC_REFERENCE_OBJECT_NOT_3D_LESION',
                        aggregation='SUM_COUNTS_OVER_FIXED8_THEN_ONE_CASE_PER_AREA',
                        independent_patient_claim=False),
                    case_macro_by_area={p: core.summarize_cases([r['evaluation']]) for p, r in areas.items()},
                    areas_averaged=False, scan_outside_fixed8='NOT_EVALUATED',
                    full_scan_sampling_coverage=None, geometry_proof='EXTERNAL_METADATA_GATE_ONLY',
                    real_execution_authorized=False)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        return _blocked(str(exc))
