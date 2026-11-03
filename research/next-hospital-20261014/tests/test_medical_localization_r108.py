"""R108 new synthetic-only suite. Chief executes once in serial CPU window."""
import copy
import unittest
import numpy as np
from epi_next.medical_localization_r108 import (
    cam_toparea, cam_connected, nested_random, shape_translations,
    evaluate_case, failure_case, summarize_cases, objects_2d8, b2_protocol,
)


def grid(h=8, w=8):
    return np.zeros((8, h, w), np.float32), np.ones((8, h, w), bool)


def roi_origin(kind='MANUAL_LUNG_MASK'):
    d = dict(kind=kind, source_id='synthetic-lung', roi_sha256='a'*64)
    if kind == 'AUTOMATIC_MODEL_LUNG_MASK':
        d.update(model_sha256='b'*64, preprocess_sha256='c'*64)
    return d


def binding(shape, case='toy', partial=False):
    identity = dict(case_id=case, source_namespace='GENERATED', source_version='v1',
                    input_sha256='a'*64, native_geometry_sha256='b'*64,
                    fixed8_native_indices=list(range(8)))
    ref = dict(identity, gt_sha256='c'*64,
               kind='PARTIAL_INFECTION_REFERENCE' if partial else 'COMPLETE_INFECTION_MASK',
               completeness='KNOWN_POSITIVES_BACKGROUND_UNKNOWN' if partial else 'CONFIRMED_COMPLETE')
    return dict(input=identity, reference=ref, evidence_type='GENERATED_ONLY',
                grid=dict(shape=list(shape), geometry_qa='PASS', space='NATIVE_FIXED8_GRID',
                          eval_grid_sha256='d'*64, transform_chain_sha256='e'*64))


def evaluate(pred, gt, *, partial=False, case='toy', **kw):
    full = np.ones_like(pred)
    return evaluate_case(pred, gt, kw.get('prediction_domain', full),
                         kw.get('reference_domain', full), kw.get('fov', full),
                         case_id=case, reference_kind='PARTIAL_INFECTION_REFERENCE' if partial else 'COMPLETE_INFECTION_MASK',
                         binding=kw.get('binding', binding(pred.shape, case, partial)))


class SelectionTests(unittest.TestCase):
    def test_noncontiguous_and_fortran_inputs(self):
        scores, valid = grid()
        layouts = [(np.asfortranarray(scores), np.asfortranarray(valid)),
                   (scores[:, ::-1, :], valid[:, ::-1, :])]
        for values, support in layouts:
            self.assertFalse(support.flags.c_contiguous)
            for selector in (cam_toparea, cam_connected):
                result = selector(values, support, .05)
                self.assertEqual(result['selected_pixels'], 25)
                self.assertEqual(int(result['mask'].sum()), 25)
                self.assertTrue(result['mask'].flags.c_contiguous)
            rows = nested_random(support)
            self.assertEqual([int(r['mask'].sum()) for r in rows], [25, 51, 102])

    def test_b0_global_quota_signed_and_ties(self):
        scores, valid = grid()
        scores.fill(-5.)
        for alpha, count in [(.05, 25), (.10, 51), (.20, 102)]:
            r = cam_toparea(scores, valid, alpha)
            self.assertEqual(r['selected_pixels'], count)
            self.assertEqual(r['per_slice_pixels'][0], min(count, 64))
            self.assertTrue(r['mask'].ravel()[:count].all())
            self.assertFalse(r['mask'].ravel()[count:].any())
            self.assertEqual(r['fixed_target_class'], 1)
            self.assertEqual(r['target_policy'], 'DECLARED_FIXED')

    def test_negative_order_not_clipped(self):
        scores, valid = grid(2, 5)
        scores.fill(-100.)
        scores[7, 1, 4] = -1.
        result = cam_toparea(scores, valid, .05)
        self.assertTrue(result['mask'][7, 1, 4])
        self.assertEqual(result['selected_pixels'], 4)

    def test_discrete_floor_empty_and_support(self):
        scores, valid = grid(1, 1)
        r = cam_toparea(scores, valid, .05)
        self.assertEqual(r['status'], 'EMPTY_NO_PADDING')
        self.assertEqual(r['selected_pixels'], 0)
        scores, valid = grid(2, 5);valid[0, 0, 0] = False
        scores[0, 0, 0] = 100.
        r = cam_toparea(scores, valid, .20)
        self.assertEqual(r['selected_pixels'], 15)
        self.assertFalse(r['mask'][0, 0, 0])

    def test_invalid_array_contract(self):
        scores, valid = grid()
        for a, v, alpha in [(scores.astype(int), valid, .05), (scores, valid.astype(int), .05),
                            (scores[:7], valid[:7], .05), (scores, valid, .15)]:
            with self.assertRaises(ValueError):cam_toparea(a, v, alpha)
        scores[0, 0, 0] = np.nan
        with self.assertRaises(ValueError):cam_toparea(scores, valid, .05)

    def test_b1_differs_from_b0_without_stealing_area(self):
        scores, valid = grid();scores.fill(-100.)
        for s in range(8):
            for y, x in [(0, 0), (0, 7), (7, 0), (7, 7)]:scores[s, y, x] = 100.-s
        a = cam_toparea(scores, valid, .05);b = cam_connected(scores, valid, .05)
        self.assertEqual(a['selected_pixels'], b['selected_pixels'])
        self.assertEqual(b['selected_pixels'], 25)
        self.assertFalse(np.array_equal(a['mask'], b['mask']))
        self.assertLessEqual(len(b['seeds']), 3)
        self.assertFalse(b['mask'][1:].any())

    def test_b1_no_reseeding_or_quota_reduction(self):
        scores, valid = grid();scores[0].fill(10.)
        r = cam_connected(scores, valid, .20)
        self.assertEqual(r['status'], 'NOT_EVALUABLE')
        self.assertIsNone(r['mask'])
        self.assertEqual(r['quota'], 102)
        self.assertEqual(r['reason'], 'FIXED_SEED_COMPONENT_CAPACITY_BELOW_QUOTA')

    def test_b1_single_seed_tiny_empty(self):
        scores, valid = grid(1, 1)
        r = cam_connected(scores, valid, .05)
        self.assertEqual(r['seeds'], [])
        self.assertEqual(r['selected_pixels'], 0)
        scores, valid = grid(1, 5)
        r = cam_connected(scores, valid, .05)
        self.assertEqual(r['selected_pixels'], 2)
        self.assertFalse(r['cross_slice_edges'])

    def test_roi_same_full_bag_quota_and_source(self):
        scores, valid = grid();roi = np.zeros_like(valid);roi[:2] = True
        r = cam_toparea(scores, valid, .10, roi=roi, roi_provenance=roi_origin())
        self.assertEqual(r['quota'], 51)
        self.assertEqual(r['selected_pixels'], 51)
        self.assertAlmostEqual(r['roi_domain_fraction'], 51/128)
        self.assertEqual(r['roi']['condition'], 'REFERENCE_CONDITION_OR_UPPER_BOUND')
        auto = cam_toparea(scores, valid, .10, roi=roi, roi_provenance=roi_origin('AUTOMATIC_MODEL_LUNG_MASK'))
        self.assertEqual(auto['roi']['condition'], 'AUTOMATIC_PREDICTION')

    def test_roi_insufficient_rejects_both_algorithms(self):
        scores, valid = grid();roi = np.zeros_like(valid);roi.ravel()[:20] = True
        for f in [cam_toparea, cam_connected]:
            r = f(scores, valid, .05, roi=roi, roi_provenance=roi_origin())
            self.assertEqual(r['quota'], 25)
            self.assertIsNone(r['mask'])
            self.assertEqual(r['status'], 'NOT_EVALUABLE')
        with self.assertRaises(ValueError):cam_toparea(scores, valid, .05, roi=roi)
        origin = roi_origin('AUTOMATIC_MODEL_LUNG_MASK');origin.pop('model_sha256')
        with self.assertRaises(ValueError):cam_toparea(scores, valid, .05, roi=roi, roi_provenance=origin)

    def test_random_seed_nested_equal_full_area(self):
        _, valid = grid();rows = nested_random(valid);again = nested_random(valid)
        for a, b, expected in zip(rows, again, (25, 51, 102)):
            self.assertEqual(a['selected_pixels'], expected)
            self.assertTrue(np.array_equal(a['mask'], b['mask']))
        self.assertFalse((rows[0]['mask'] & ~rows[1]['mask']).any())
        self.assertFalse((rows[1]['mask'] & ~rows[2]['mask']).any())

    def test_random_roi_insufficiency_not_smaller_quota(self):
        _, valid = grid();roi = np.zeros_like(valid);roi.ravel()[:30] = True
        rows = nested_random(valid, roi=roi, roi_provenance=roi_origin())
        self.assertEqual(rows[0]['selected_pixels'], 25)
        self.assertIsNone(rows[1]['mask']);self.assertEqual(rows[1]['quota'], 51)

    def test_shape_translations_preserve_all_planes(self):
        _, valid = grid();mask = np.zeros_like(valid)
        mask[0, 3:5, 3:5] = True;mask[7, 3, 3] = True
        r = shape_translations(mask, valid)
        self.assertEqual(r['status'], 'COMPLETE')
        self.assertEqual(len(r['controls']), 2)
        for c in r['controls']:
            self.assertEqual(c['pixels'], 5)
            self.assertTrue(np.array_equal(c['mask'].sum((1, 2)), mask.sum((1, 2))))
            self.assertNotEqual((c['dy'], c['dx']), (0, 0))

    def test_no_shape_control_never_wraps(self):
        _, valid = grid(2, 2);r = shape_translations(valid.copy(), valid)
        self.assertEqual(r['status'], 'MISSING_CONTROL')
        self.assertEqual(r['missing'], 2)
        self.assertEqual(r['controls'], [])


class EvaluationTests(unittest.TestCase):
    def test_complete_dice_iou_coverage(self):
        _, valid = grid();gt = np.zeros_like(valid);pred = gt.copy()
        gt[0, 1, 1] = gt[0, 4, 4] = True
        pred[0, 1, 1] = pred[0, 6, 6] = True
        r = evaluate(pred, gt)
        self.assertAlmostEqual(r['metrics']['dice'], .5)
        self.assertAlmostEqual(r['metrics']['iou'], 1/3)
        self.assertAlmostEqual(r['metrics']['known_positive_coverage'], .5)
        self.assertEqual(r['counts']['false_positive_known_pixels'], 1)
        self.assertEqual(r['evidence_type'], 'GENERATED_ONLY')

    def test_partial_unknown_is_not_background(self):
        _, valid = grid();gt = np.zeros_like(valid);gt[0, 1, 1] = True
        pred = gt.copy();pred[7, 7, 7] = True
        r = evaluate(pred, gt, partial=True, reference_domain=gt.copy())
        self.assertIsNone(r['metrics']['dice']);self.assertIsNone(r['metrics']['iou'])
        self.assertIsNone(r['counts']['false_positive_known_pixels'])
        self.assertEqual(r['metrics']['known_positive_coverage'], 1.)
        self.assertEqual(r['metrics']['candidate_in_gt_valid_fraction'], .5)

    def test_empty_gt_conventions(self):
        _, valid = grid();empty = np.zeros_like(valid)
        r = evaluate(empty, empty)
        self.assertIsNone(r['metrics']['dice']);self.assertIsNone(r['metrics']['known_positive_coverage'])
        self.assertEqual(r['empty_gt_state'], 'EMPTY_GT_EMPTY_PRED')
        pred = empty.copy();pred[0, 0, 0] = True
        r = evaluate(pred, empty)
        self.assertEqual(r['metrics']['dice'], 0.)
        self.assertEqual(r['counts']['false_positive_known_pixels'], 1)
        r = evaluate(pred, empty, partial=True)
        self.assertIsNone(r['metrics']['dice']);self.assertIsNone(r['counts']['false_positive_known_pixels'])

    def test_fov_and_prediction_domain_are_reported(self):
        _, valid = grid();gt = np.zeros_like(valid);gt[0, 1, 1] = gt[1, 1, 1] = True
        pred = gt.copy();pred[7, 7, 7] = True
        domain = valid.copy();domain[1] = False
        r = evaluate(pred, gt, prediction_domain=domain)
        self.assertEqual(r['status'], 'NOT_EVALUABLE')
        pred[1, 1, 1] = False
        fov = valid.copy();fov[7] = False
        r = evaluate(pred, gt, prediction_domain=domain, fov=fov)
        self.assertEqual(r['counts']['gt_positive_unpredicted_in_fov'], 1)
        self.assertEqual(r['metrics']['known_positive_coverage'], .5)
        self.assertEqual(r['metrics']['candidate_in_gt_valid_fraction'], .5)
        self.assertEqual(len(r['domains']['fov_sha256']), 64)

    def test_binding_and_completeness_reject_equal_shape(self):
        _, valid = grid();empty = np.zeros_like(valid)
        for field, value in [('input_sha256', 'f'*64), ('native_geometry_sha256', 'f'*64)]:
            b = binding(valid.shape);b['reference'][field] = value
            self.assertEqual(evaluate(empty, empty, binding=b)['status'], 'NOT_EVALUABLE')
        b = binding(valid.shape);b['grid']['geometry_qa'] = 'UNKNOWN'
        self.assertIsNone(evaluate(empty, empty, binding=b)['metrics']['dice'])
        b = binding(valid.shape);b['reference']['completeness'] = 'UNKNOWN'
        self.assertEqual(evaluate(empty, empty, binding=b)['reason'], 'REFERENCE_COMPLETENESS_BINDING_CONFLICT')

    def test_unknown_reference_and_no_common_domain(self):
        _, valid = grid();empty = np.zeros_like(valid)
        r = evaluate(empty, empty, reference_domain=empty)
        self.assertEqual(r['reason'], 'EMPTY_COMMON_KNOWN_FOV_DOMAIN')
        r = evaluate_case(empty, empty, valid, valid, valid, case_id='toy',
                          reference_kind='UNKNOWN', binding=binding(valid.shape))
        self.assertEqual(r['status'], 'NOT_EVALUABLE')
        gt = empty.copy();gt[0, 0, 0] = True
        r = evaluate(empty, gt, reference_domain=empty)
        self.assertEqual(r['reason'], 'GT_POSITIVES_OUTSIDE_DECLARED_REFERENCE_DOMAIN')

    def test_objects_are_2d8cc_and_not_pseudo3d(self):
        _, valid = grid();gt = np.zeros_like(valid)
        gt[0, 1, 1] = gt[0, 2, 2] = gt[1, 1, 1] = True
        pred = np.zeros_like(gt);pred[0, 1, 1] = True
        r = objects_2d8(gt, pred)
        self.assertEqual(r['count'], 2)
        self.assertEqual(r['hit_count'], 1)
        self.assertEqual(r['objects'][0]['pixels'], 2)

    def test_case_aggregation_precedes_macro(self):
        _, valid = grid();gt = np.zeros_like(valid);pred = gt.copy()
        gt[0, 0, 0] = True;gt[1, :3, :3] = True;pred[0, 0, 0] = True
        r = evaluate(pred, gt)
        self.assertAlmostEqual(r['metrics']['dice'], 2/11)
        partial = evaluate(pred, gt, partial=True, case='partial')
        failed = failure_case('failed', 'GEOMETRY_REJECTED', status='FAILED')
        summary = summarize_cases([r, partial, failed])
        self.assertAlmostEqual(summary['macro']['dice']['value'], 2/11)
        self.assertEqual(summary['macro']['dice']['defined_cases'], 1)
        self.assertEqual(summary['case_count'], 3)
        self.assertEqual(summary['status_counts']['FAILED'], 1)
        with self.assertRaises(ValueError):summarize_cases([r, copy.deepcopy(r)])

    def test_failure_never_becomes_numeric_zero(self):
        bad = failure_case('x', 'UNKNOWN_REFERENCE');bad['metrics']['dice'] = 0.
        with self.assertRaises(ValueError):summarize_cases([bad])
        s = summarize_cases([failure_case('x', 'UNKNOWN_REFERENCE')])
        self.assertIsNone(s['macro']['dice']['value'])

    def test_b2_is_finite_spec_not_search(self):
        p = b2_protocol()
        self.assertEqual(p['total_proposal_evaluations'], 12)
        self.assertFalse(p['gt_used_in_search'])
        self.assertIsNone(p['real_model_calls_actual'])
        self.assertEqual(p['status'], 'SPEC_NOT_EXECUTABLE')


if __name__ == '__main__':unittest.main()
