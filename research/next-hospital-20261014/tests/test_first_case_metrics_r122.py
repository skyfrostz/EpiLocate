"""R122 contract tests: generated NumPy arrays only; no patient/model IO."""
import copy
import unittest
import numpy as np
from epi_next import first_case_metrics_r122 as bridge
from epi_next import medical_localization_r108 as core


def fixture(partial=False):
    shape = (8, 224, 224)
    scores = np.full(shape, -5., np.float64)
    support = np.ones(shape, bool)
    gt = np.zeros(shape, bool);gt.ravel()[:25] = True
    reference = support.copy();fov = support.copy()
    q = dict(qualification_status='PASS', qualification_receipt_sha256='a'*64,
             case_id=bridge.CASE_ID, source_namespace='GENERATED', source_version='v1',
             patient_group_id='synthetic-group', patient_group_provenance='generated fixture only',
             ct_archive_sha256=bridge.ARCHIVES['CT'], gt_archive_sha256=bridge.ARCHIVES['GT'],
             input_sha256='b'*64, gt_sha256='c'*64,
             input_hash_role='generated CT identity; no actual CT array',
             gt_hash_role='generated reference asset identity, distinct from stack digest',
             native_geometry_sha256='d'*64, native_shape_zyx=[16, 224, 224],
             original_shape_XYZ=[224, 224, 16],
             native_definition='ORIGINAL_NIFTI_XYZ_TRANSPOSED_ZYX_NO_FLIPS',
             fixed8_native_indices=list(range(1, 16, 2)),
             selected_original_nifti_Z=list(range(1, 16, 2)),
             selected_canonical_Z=list(range(14, -1, -2)),
             reference_kind='PARTIAL_INFECTION_REFERENCE' if partial else 'COMPLETE_INFECTION_MASK',
             annotation_completeness='KNOWN_POSITIVES_BACKGROUND_UNKNOWN' if partial else 'CONFIRMED_COMPLETE',
             reference_extent='generated known extent on fixed8 only',
             label_mapping_provenance='generated bool infection reference, not real Lesion qualification',
             geometry_qa='PASS', eval_grid_sha256='e'*64, transform_chain_sha256='f'*64,
             evidence_type='GENERATED_ONLY', fixed8_gt_bool_sha256=core._array_sha(gt),
             fixed8_reference_domain_sha256=core._array_sha(reference), fixed8_fov_sha256=core._array_sha(fov))
    cam = {k: copy.deepcopy(q[k]) for k in bridge.PLANE_IDENTITY}
    cam.update(evidence_type='GENERATED_ONLY', target_policy='DECLARED_FIXED', fixed_target_class=1,
               score_semantics=bridge.SCORE_SEMANTICS, negative_scores_clipped=False,
               model_sha256='1'*64, preprocess_sha256='2'*64, model_adapter_sha256='3'*64,
               runtime_sha256='4'*64, original_logits=[3., -2.], original_predicted_class=0,
               scores_sha256=core._array_sha(scores), model_support_sha256=core._array_sha(support))
    candidates = {}
    for p, alpha in zip(bridge.PERCENTS, core.AREAS):
        model = core.cam_toparea(scores, support, alpha)['mask']
        native = model.copy()  # Generated identity in-plane map; K8 has original native-Z labels.
        mapping = {k: copy.deepcopy(q[k]) for k in bridge.PLANE_IDENTITY}
        mapping.update(eval_grid_sha256=q['eval_grid_sha256'], transform_chain_sha256=q['transform_chain_sha256'],
                       model_mask_sha256=core._array_sha(model), native_prediction_sha256=core._array_sha(native),
                       prediction_domain_sha256=core._array_sha(support),
                       method='PER_NATIVE_PLANE_NEAREST_BINARY_NO_K8_INTERPOLATION')
        candidates[p] = dict(native_prediction=native, mapping=mapping)
    return [q, cam, scores, support, gt, reference, fov, candidates]


class FirstCaseTests(unittest.TestCase):
    def check_blocked(self, args, reason):
        result = bridge.evaluate_first_case(*args)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn(reason, result['reason'])
        for p in bridge.PERCENTS:
            self.assertTrue(all(v is None for v in result['areas'][p]['metrics'].values()))
            self.assertIsNone(result['case_macro_by_area'][p]['macro']['dice']['value'])
        self.assertFalse(result['real_execution_authorized'])

    def test_complete_exact_areas_case_plane_object_denominators(self):
        result = bridge.evaluate_first_case(*fixture())
        self.assertEqual(result['status'], 'EVALUATED_FIXED_AREAS')
        self.assertEqual([result['areas'][p]['model_selected_pixels'] for p in bridge.PERCENTS], [20070, 40140, 80281])
        self.assertEqual(result['areas']['5']['evaluation']['metrics']['dice'], 50/20095)
        self.assertEqual(result['areas']['5']['evaluation']['counts']['prediction_domain_pixels'], 401408)
        self.assertEqual(result['areas']['5']['evaluation']['objects']['count'], 1)
        self.assertEqual(result['denominators']['cases'], 1)
        self.assertEqual(result['denominators']['sampled_native_planes'], 8)
        self.assertFalse(result['areas_averaged'])
        self.assertIsNone(result['full_scan_sampling_coverage'])
        self.assertEqual(result['geometry_proof'], 'EXTERNAL_METADATA_GATE_ONLY')

    def test_partial_unknown_never_complete_dice_or_false_positive(self):
        args = fixture(partial=True)
        args[5].fill(False);args[5].ravel()[:25] = True
        args[0]['fixed8_reference_domain_sha256'] = core._array_sha(args[5])
        result = bridge.evaluate_first_case(*args)
        for p in bridge.PERCENTS:
            r = result['areas'][p]['evaluation']
            self.assertEqual(r['status'], 'EVALUATED_PARTIAL_COVERAGE_ONLY')
            self.assertIsNone(r['metrics']['dice']);self.assertIsNone(r['metrics']['iou'])
            self.assertIsNone(r['counts']['false_positive_known_pixels'])
            self.assertEqual(r['metrics']['known_positive_coverage'], 1.)
        self.assertEqual(result['areas']['20']['evaluation']['counts']['candidate_outside_gt_valid_fov'], 80256)

    def test_missing_qualification_and_unknown_completeness_block(self):
        for key, value, reason in [('qualification_status', 'NOT_RUN', 'QUALIFICATION_NOT_PASS'),
                                   ('annotation_completeness', 'UNKNOWN', 'REFERENCE_COMPLETENESS'),
                                   ('qualification_receipt_sha256', None, 'RECEIPT_SHA')]:
            args = fixture();args[0][key] = value;self.check_blocked(args, reason)

    def test_case_archive_and_cam_identity_conflicts(self):
        args = fixture();args[0]['case_id'] = 'other';self.check_blocked(args, 'FIXED_CASE')
        args = fixture();args[0]['ct_archive_sha256'] = 'f'*64;self.check_blocked(args, 'ARCHIVE_IDENTITY')
        args = fixture();args[1]['input_sha256'] = '0'*64;self.check_blocked(args, 'CAM_INPUT_IDENTITY')

    def test_original_z_preserved_canonical_metadata_never_sampling(self):
        result = bridge.evaluate_first_case(*fixture())
        self.assertEqual(result['denominators']['native_z'], list(range(1, 16, 2)))
        self.assertEqual(result['denominators']['selected_canonical_Z'], list(range(14, -1, -2)))
        args = fixture();args[0]['fixed8_native_indices'] = args[0]['selected_canonical_Z']
        self.check_blocked(args, 'ORIGINAL_FIXED8_CENTER_ORDER')
        args = fixture();args[0]['native_definition'] = 'CANONICAL_LPS_REORDERED'
        self.check_blocked(args, 'ORIGINAL_NIFTI_PLANE')

    def test_reference_stack_digests_reject_corruption(self):
        for i in (4, 5, 6):
            args = fixture();args[i][0, 0, 0] = not args[i][0, 0, 0]
            self.check_blocked(args, 'QUALIFIED_ARRAY_DIGEST')

    def test_model_mask_native_mask_and_full_domain_binding(self):
        for key in ('model_mask_sha256', 'native_prediction_sha256', 'prediction_domain_sha256'):
            args = fixture();args[7]['5']['mapping'][key] = '0'*64
            self.check_blocked(args, 'NATIVE_MAPPING_MASK_OR_DOMAIN_DIGEST')
        args = fixture();args[7]['5']['native_prediction'][7, 223, 223] = True
        self.check_blocked(args, 'NATIVE_MAPPING_MASK_OR_DOMAIN_DIGEST')

    def test_mapping_wrong_plane_grid_or_pseudovolume_rejected(self):
        args = fixture();args[7]['10']['mapping']['selected_original_nifti_Z'].reverse()
        self.check_blocked(args, 'NATIVE_MAPPING_IDENTITY')
        args = fixture();args[7]['10']['mapping']['eval_grid_sha256'] = '0'*64
        self.check_blocked(args, 'NATIVE_MAPPING_GRID')
        args = fixture();args[7]['10']['mapping']['method'] = 'TRILINEAR_K8_VOLUME'
        self.check_blocked(args, 'PER_NATIVE_PLANE_MAPPING')

    def test_fixed_target_one_retains_original_prediction_zero_and_signed_ties(self):
        result = bridge.evaluate_first_case(*fixture())
        self.assertEqual(result['original_predicted_class'], 0)
        self.assertEqual(result['original_logits'], [3., -2.])
        self.assertEqual(result['fixed_target_class'], 1)
        self.assertEqual(result['areas']['5']['selection']['per_slice_pixels'], [20070, 0, 0, 0, 0, 0, 0, 0])
        args = fixture();args[1]['negative_scores_clipped'] = True
        self.check_blocked(args, 'FIXED_SIGNED_TARGET')

    def test_no_roi_or_missing_area_substitution(self):
        args = fixture();args[3][0, 0, 0] = False
        args[1]['model_support_sha256'] = core._array_sha(args[3])
        self.check_blocked(args, 'ORIGINAL_FULL_MODEL_SUPPORT')
        args = fixture();del args[7]['20'];self.check_blocked(args, 'EXACT_THREE_PRELOCKED')

    def test_bad_dtype_empty_domain_and_asset_hash_role(self):
        args = fixture();args[4] = args[4].astype(np.uint8)
        self.check_blocked(args, 'STRICT_BOOL')
        args = fixture();args[0]['input_hash_role'] = 'UNKNOWN'
        self.check_blocked(args, 'INPUT_HASH_ROLE')
        args = fixture();args[6].fill(False)
        args[0]['fixed8_fov_sha256'] = core._array_sha(args[6])
        result = bridge.evaluate_first_case(*args)
        self.assertEqual(result['status'], 'NOT_EVALUABLE')
        for p in bridge.PERCENTS:
            self.assertIsNone(result['areas'][p]['evaluation']['metrics']['dice'])
            self.assertEqual(result['areas'][p]['evaluation']['reason'], 'EMPTY_COMMON_KNOWN_FOV_DOMAIN')

    def test_wrong_model_grid_or_precision_rejected(self):
        for precision in (np.float32, np.float16):
            args = fixture();args[2] = args[2].astype(precision)
            args[1]['scores_sha256'] = core._array_sha(args[2])
            self.check_blocked(args, 'FROZEN_R18_MODEL_GRID')
        args = fixture();args[2] = args[2][:, :8, :8];args[3] = args[3][:, :8, :8]
        args[1]['scores_sha256'] = core._array_sha(args[2])
        args[1]['model_support_sha256'] = core._array_sha(args[3])
        self.check_blocked(args, 'FROZEN_R18_MODEL_GRID')
        args = fixture();args[2].ravel()[20070] += 2**-30
        args[1]['scores_sha256'] = core._array_sha(args[2])
        for p, alpha in zip(bridge.PERCENTS, core.AREAS):
            native = core.cam_toparea(args[2], args[3], alpha)['mask']
            args[7][p]['native_prediction'] = native.copy()
            args[7][p]['mapping'].update(model_mask_sha256=core._array_sha(native),
                                        native_prediction_sha256=core._array_sha(native))
        result = bridge.evaluate_first_case(*args)
        self.assertEqual(result['status'], 'EVALUATED_FIXED_AREAS')
        self.assertEqual(result['score_dtype'], 'float64')
        exact = args[7]['5']['native_prediction']
        self.assertTrue(exact.ravel()[20070]);self.assertFalse(exact.ravel()[20069])
        rounded = core.cam_toparea(args[2].astype(np.float32), args[3], .05)['mask']
        self.assertNotEqual(core._array_sha(exact), core._array_sha(rounded))
        self.assertEqual(result['areas']['5']['model_mask_sha256'], core._array_sha(exact))


if __name__ == '__main__':
    unittest.main()
