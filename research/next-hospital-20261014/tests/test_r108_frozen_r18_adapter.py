"""New R108 synthetic-only regression; no old suite/model/medical readers."""
import unittest

import numpy as np
from epi_next.r108_frozen_r18_adapter import (
    FILL, FROZEN_IDENTITY, METHOD, MEAN, STD, Blocked, case_eligibility,
    SyntheticFrozenR18Session, fixed8, model_centers_to_native,
    perturb_input, prepare_synthetic_native, real_callback, real_reader,
    stable_flat_order, validate_native_metadata,
)


def metadata():
    return dict(schema='R108_QUALIFIED_NATIVE_METADATA_V1', domain='SYNTHETIC_ONLY',
                qualification='QUALIFIED_NATIVE_HU_GEOMETRY', unit='HU', rescale_applied_once=True,
                axis_order='Z,Y,X', case_id='GENERATED_CASE', patient_id='GENERATED_PATIENT',
                source_version='GENERATED_VERSION', input_sha256='a'*64, geometry_sha256='b'*64,
                reference_sha256='c'*64, reference_status='COMPLETE', reference_extent_known=True,
                reference_identity_bound=True, native_shape_ZYX=[16, 6, 10], spacing_ZYX_mm=[2.5, 1.2, .8],
                native_to_LPS=[[0, 0, .8, 10], [0, 1.2, 0, 20], [2.5, 0, 0, -30], [0, 0, 0, 1]],
                model_identity=FROZEN_IDENTITY.copy(), source_label=1)


class ResizeSpy:
    def __init__(self, extra=0.):
        self.calls, self.extra = [], extra

    def __call__(self, x, **kwargs):
        self.calls.append((x.shape, x.dtype, kwargs))
        # Constant-per-slice fixture: all correct resizers preserve each value.
        return np.broadcast_to(x[:, :, :1, :1], (8, 1, 224, 224)).copy() + np.float32(self.extra)


class ToyCallback:
    def __init__(self, fail_on=None, corrupt=None):
        self.calls, self.fail_on, self.corrupt = [], fail_on, corrupt

    def __call__(self, bag, *, want_cam):
        self.calls.append((bag.shape, want_cam))
        if len(self.calls) == self.fail_on:
            raise RuntimeError('GENERATED_INFLIGHT_FAILURE')
        class_cam = np.zeros((8, 2, 7, 7), dtype=np.float64)
        class_cam[:, 1] = bag[:, 0].mean((1, 2), dtype=np.float64)[:, None, None] + np.linspace(-1, 1, 49).reshape(7, 7)
        bias = np.array([-.25, -2.], dtype=np.float64)
        out = dict(logits=bias+class_cam.mean((0, 2, 3)), model_identity=FROZEN_IDENTITY.copy(),
                   method_id=METHOD, target=1, evidence_status='SYNTHETIC_ONLY')
        if want_cam:
            out.update(class_cam=class_cam, effective_bias=bias)
        if self.corrupt:
            self.corrupt(out)
        return out


def session(callback=None, **kwargs):
    return SyntheticFrozenR18Session(np.zeros((8, 3, 224, 224), np.float32), metadata(),
                                     callback or ToyCallback(), mode='SYNTHETIC_ONLY', **kwargs)


def area_mask(percent, offset=0):
    mask = np.zeros((8, 224, 224), dtype=bool)
    count = mask.size*percent//100
    mask.ravel()[np.arange(offset, offset+count) % mask.size] = True
    return mask


class NativeContractTests(unittest.TestCase):
    def test_floor_sampling_resize_spy_normalization_and_native_centers(self):
        m = metadata()
        native = np.broadcast_to((np.arange(16, dtype=np.float32)*100-1350)[:, None, None], (16, 6, 10)).copy()
        spy = ResizeSpy()
        bag, valid, geo = prepare_synthetic_native(native, m, resize=spy)
        self.assertEqual(fixed8(16), [1, 3, 5, 7, 9, 11, 13, 15])
        self.assertEqual(fixed8(17), [1, 3, 5, 7, 9, 11, 13, 15])
        self.assertEqual(spy.calls, [((8, 1, 6, 10), np.dtype('float32'),
                                     dict(size=(224, 224), interpolation='bilinear', antialias=True))])
        expected = (np.clip((native[geo['indices_Z'], 0, 0]+1350)/1500, 0, 1)[:, None]-MEAN)/STD
        np.testing.assert_allclose(bag[:, :, 0, 0], expected, atol=0, rtol=0)
        self.assertEqual(bag.shape, (8, 3, 224, 224))
        self.assertEqual(bag.dtype, np.float32)
        self.assertTrue(valid.all())
        points, world = model_centers_to_native(geo, [[0, 111.5, 111.5]])
        np.testing.assert_allclose(points, [[1, 2.5, 4.5]])
        np.testing.assert_allclose(world, [[13.6, 23., -27.5]])
        self.assertIn('REAL_NUMERICAL_PARITY_NOT_RUN', geo['verification'])

    def test_unknown_identity_reference_and_non_HU_reject_before_callback(self):
        changes = [dict(patient_id=None), dict(patient_id='UNKNOWN'), dict(reference_status='UNKNOWN'),
                   dict(reference_extent_known=False), dict(reference_identity_bound=False),
                   dict(unit='WINDOWED_UINT8'), dict(domain='REAL'),
                   dict(input_sha256='unknown'), dict(fixed8_indices=list(range(8))),
                   dict(model_identity={}), dict(native_shape_ZYX=[7, 6, 10])]
        for change in changes:
            m = metadata(); m.update(change)
            spy = ToyCallback()
            with self.subTest(change=change), self.assertRaises((Blocked, ValueError)):
                SyntheticFrozenR18Session(np.zeros((8, 3, 224, 224), np.float32), m,
                                           spy, mode='SYNTHETIC_ONLY')
            self.assertEqual(spy.calls, [])
        m = metadata(); m['native_to_LPS'][0][0] = .1
        with self.assertRaises(Blocked):
            validate_native_metadata(m)

    def test_frozen_resize_roundoff_envelope_is_strict(self):
        native = np.full((16, 6, 10), 150, np.float32)
        bag, _, geo = prepare_synthetic_native(native, metadata(), resize=ResizeSpy(2**-22))
        self.assertGreater(geo['resize_roundoff_max'], 0)
        np.testing.assert_allclose(bag[0, :, 0, 0], (1-MEAN)/STD)
        with self.assertRaises(Blocked):
            prepare_synthetic_native(native, metadata(), resize=ResizeSpy(2**-20))
        with self.assertRaises(Blocked):
            prepare_synthetic_native(native.astype(np.float64), metadata(), resize=ResizeSpy())

    def test_real_entrypoints_disabled_without_open_or_invocation(self):
        for function in (real_reader, real_callback):
            with self.assertRaises(Blocked):
                function('/not/a/path/to/open')
        spy = ToyCallback()
        with self.assertRaises(Blocked):
            SyntheticFrozenR18Session(np.zeros((8, 3, 224, 224), np.float32), metadata(), spy)
        self.assertEqual(spy.calls, [])

    def test_case_failure_rows_preserve_unknown_reference_denominator(self):
        rows = []
        for case, status in [('generated1', 'UNKNOWN'), ('generated2', 'COMPLETE')]:
            m = metadata(); m.update(case_id=case, reference_status=status)
            rows.append(case_eligibility(m))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['status'], 'BLOCKED')
        self.assertEqual(rows[0]['reference_status'], 'UNKNOWN')
        self.assertIsNone(rows[0]['indices_Z'])
        self.assertEqual(rows[1]['status'], 'QUALIFIED_SYNTHETIC_METADATA_ONLY')
        self.assertTrue(all(r['medical_reference_verified'] is False and r['model_calls'] == 0 for r in rows))


class ScoreAndInputTests(unittest.TestCase):
    def test_signed_margin_with_separate_bias_and_stable_flat_ties(self):
        s = session(); original = s.start()
        self.assertLess(original['scores'].min(), 0)
        self.assertGreater(original['scores'].max(), 0)
        self.assertEqual(original['effective_margin_bias'], -1.75)
        self.assertAlmostEqual(original['signed_margin_7x7'].mean()+original['effective_margin_bias'], original['margin'])
        self.assertEqual(original['predicted_class'], 0)
        self.assertEqual(original['fixed_target'], 1)
        order = stable_flat_order(np.full((8, 224, 224), -4., np.float64), s.valid)
        np.testing.assert_array_equal(order[:10], np.arange(10))
        self.assertFalse(original['negative_values_clipped'])
        self.assertEqual(s.report()['actual_forward'], 2)

    def test_keep_remove_fill_vector_preserves_bag_and_complement(self):
        bag = np.full((8, 3, 224, 224), .4, np.float32)
        original = bag.copy(); mask = area_mask(5)
        valid = np.ones_like(mask)
        keep = perturb_input(bag, mask, valid, action='keep')
        remove = perturb_input(bag, mask, valid, action='remove')
        self.assertEqual(keep.shape[0], 8)
        self.assertEqual(remove.shape, bag.shape)
        self.assertTrue(np.all(keep.transpose(0, 2, 3, 1)[mask] == .4))
        self.assertTrue(np.all(remove.transpose(0, 2, 3, 1)[mask] == FILL))
        self.assertTrue(np.all(keep.transpose(0, 2, 3, 1)[~mask] == FILL))
        np.testing.assert_array_equal(bag, original)
        np.testing.assert_allclose(FILL, -MEAN/STD, atol=0, rtol=0)
        with self.assertRaises(Blocked):
            perturb_input(bag, mask.astype(np.uint8), valid, action='keep')
        valid[0, 0, 0] = False
        with self.assertRaises(Blocked):
            perturb_input(bag, mask, valid, action='keep')

    def test_wrong_bias_target_identity_or_nonfinite_logit_stop(self):
        corruptions = [lambda x: x.update(target=0), lambda x: x.update(model_identity={}),
                       lambda x: x.update(logits=np.array([0., np.nan])),
                       lambda x: x.update(effective_bias=np.array([100., 200.]))]
        for corrupt in corruptions:
            spy = ToyCallback(corrupt=corrupt); s = session(spy)
            with self.subTest(corrupt=corrupt), self.assertRaises(Blocked): s.start()
            self.assertEqual(s.report()['actual_forward'], 1)
            with self.assertRaises(Blocked): s.start()
            self.assertEqual(len(spy.calls), 1)


class BudgetAndFlowTests(unittest.TestCase):
    def test_26_full_bag_calls_original_cam_reuse_no_warmup_and_normal_kept(self):
        spy = ToyCallback(); s = session(spy); s.start()
        rows = []
        for percent in (5, 10, 20):
            for i, method in enumerate(('CAM', 'RANDOM', 'SHAPE1', 'SHAPE2')):
                rows.append(s.evaluate_candidate(area_mask(percent, 100*i), percent=percent, method=method))
        report = s.finish_B0()
        self.assertEqual(report['actual_forward'], 26)
        self.assertEqual(report['encoded_input_positions'], 208)
        self.assertEqual(report['phase_returned'], dict(B0=26, B1=0))
        self.assertEqual(sum(cam for shape, cam in spy.calls), 1)
        self.assertTrue(all(shape == (8, 3, 224, 224) for shape, cam in spy.calls))
        self.assertTrue(all(row['original_predicted_class'] == 0 and row['fixed_target'] == 1 for row in rows))
        self.assertEqual(rows[0]['source_label'], 1)
        self.assertEqual(report['warmup'], 0)
        self.assertFalse(report['retry'])
        self.assertEqual(report['real_model_calls'], 0)

    def test_partial_reference_kept_without_inventing_medical_metrics(self):
        m = metadata(); m['reference_status'] = 'PARTIAL'
        s = SyntheticFrozenR18Session(np.zeros((8, 3, 224, 224), np.float32), m,
                                      ToyCallback(), mode='SYNTHETIC_ONLY')
        s.start(); row = s.evaluate_candidate(area_mask(5), percent=5, method='CAM')
        self.assertEqual(row['reference_status'], 'PARTIAL')
        self.assertNotIn('Dice', row)
        self.assertNotIn('IoU', row)

    def test_B1_cap_separate_no_implicit_extra_calls(self):
        spy = ToyCallback(); s = session(spy); s.start()
        with self.assertRaises(Blocked):
            s.evaluate_candidate(area_mask(5), percent=5, method='CAM_CONNECTED', phase='B1')
        self.assertEqual(len(spy.calls), 2)
        s = session(b1_forward_cap=2); s.start()
        s.evaluate_candidate(area_mask(5), percent=5, method='CAM_CONNECTED', phase='B1')
        self.assertEqual(s.report()['phase_returned'], dict(B0=2, B1=2))
        with self.assertRaises(Blocked):
            s.evaluate_candidate(area_mask(10), percent=10, method='CAM_CONNECTED', phase='B1')
        self.assertEqual(s.report()['actual_forward'], 4)

    def test_inflight_failure_has_unknown_actual_and_no_retry(self):
        spy = ToyCallback(fail_on=4); s = session(spy); s.start()
        with self.assertRaisesRegex(RuntimeError, 'GENERATED_INFLIGHT_FAILURE'):
            s.evaluate_candidate(area_mask(5), percent=5, method='CAM')
        report = s.report()
        self.assertEqual(report['reserved_forward'], 4)
        self.assertEqual(report['returned_forward'], 3)
        self.assertIsNone(report['actual_forward'])
        self.assertIsNone(report['encoded_input_positions'])
        self.assertEqual(report['inflight']['samples'], 8)
        self.assertEqual(len(report['trace']), 3)
        with self.assertRaises(Blocked):
            s.evaluate_candidate(area_mask(10), percent=10, method='CAM')
        self.assertEqual(len(spy.calls), 4)
        self.assertIn('GENERATED_INFLIGHT_FAILURE', s.report()['failure'])

    def test_wrong_area_or_duplicate_is_fail_closed_before_extra_query(self):
        for mask, percent in [(area_mask(10), 5), (area_mask(5), 7)]:
            s = session(); s.start()
            with self.assertRaises(Blocked):
                s.evaluate_candidate(mask, percent=percent, method='CAM')
            self.assertEqual(s.report()['actual_forward'], 2)
            with self.assertRaises(Blocked):
                s.evaluate_candidate(area_mask(5), percent=5, method='CAM')
        s = session(); s.start(); s.evaluate_candidate(area_mask(5), percent=5, method='CAM')
        with self.assertRaises(Blocked):
            s.evaluate_candidate(area_mask(5), percent=5, method='CAM')
        self.assertEqual(s.report()['actual_forward'], 4)


if __name__ == '__main__':
    unittest.main()
