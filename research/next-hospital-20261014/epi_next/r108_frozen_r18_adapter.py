"""R108 independent K8 research seam. Injected synthetic arrays/functions only.

There is deliberately no medical reader, weight loader, real callback factory,
CLI executor, or import of the frozen Torch runtime in this module.
"""
from copy import deepcopy
import re

import numpy as np


K, SIZE = 8, 224
METHOD = 'R108_FROZEN_R18_SIGNED_MARGIN_INPUT_FILL_V1'
PREPROCESS = 'R18_HU_MINUS1350_150_RGB224_ANTIALIAS_4EPS_V1'
MEAN = np.array([.485, .456, .406], dtype=np.float32)
STD = np.array([.229, .224, .225], dtype=np.float32)
FILL = -MEAN / STD
for _constant in (MEAN, STD, FILL):
    _constant.setflags(write=False)
ATOL, RTOL = 1e-4, 1e-5  # Existing R92 future_spatial_logits policy, unchanged.
ROUNDING_ATOL = 4 * 2**-23
FROZEN_IDENTITY = dict(
    backbone_sha256='f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec',
    head_manifest_sha256='0000000000000000000000000000000000000000000000000000000000000000',
    preprocessing_config_sha256='0000000000000000000000000000000000000000000000000000000000000000',
    frozen_r18_source_sha256='ba7dd0f5e5cb42e4feb3571d056413aee611f9d418fc2bb7640298fe6e866fd0',
)


class Blocked(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise Blocked(reason)


def real_reader(*args, **kwargs):
    raise Blocked('REAL_MEDICAL_READER_DISABLED_NO_PATH_OPENED')


def real_callback(*args, **kwargs):
    raise Blocked('REAL_MODEL_CALLBACK_DISABLED_NO_MODEL_LOADED')


def fixed8(depth):
    require(type(depth) is int and depth >= 8, 'EIGHT_DISTINCT_SLICES_REQUIRED')
    return [(2*j + 1)*depth//16 for j in range(8)]


def validate_native_metadata(meta):
    require(isinstance(meta, dict), 'NATIVE_METADATA_DICTIONARY_REQUIRED')
    require(meta.get('schema') == 'R108_QUALIFIED_NATIVE_METADATA_V1'
            and meta.get('domain') == 'SYNTHETIC_ONLY', 'SYNTHETIC_METADATA_ONLY')
    require(meta.get('qualification') == 'QUALIFIED_NATIVE_HU_GEOMETRY'
            and meta.get('unit') == 'HU' and meta.get('rescale_applied_once') is True
            and meta.get('axis_order') == 'Z,Y,X', 'QUALIFIED_ORIGINAL_HU_REQUIRED')
    for key in ('case_id', 'patient_id', 'source_version'):
        require(isinstance(meta.get(key), str) and bool(meta[key].strip())
                and meta[key] not in ('UNKNOWN', 'NOT_EVALUATED'), 'BOUND_CASE_PATIENT_SOURCE_REQUIRED')
    label = meta.get('source_label')
    require(label is None or (type(label) is int and label in (0, 1)), 'OPTIONAL_WEAK_SOURCE_LABEL_ONLY')
    for key in ('input_sha256', 'geometry_sha256', 'reference_sha256'):
        require(isinstance(meta.get(key), str) and re.fullmatch('[a-f0-9]{64}', meta[key]),
                'BOUND_INPUT_GEOMETRY_REFERENCE_SHA_REQUIRED')
    require(meta.get('reference_status') in ('COMPLETE', 'PARTIAL')
            and meta.get('reference_extent_known') is True
            and meta.get('reference_identity_bound') is True, 'UNKNOWN_REFERENCE_NOT_EVALUABLE')
    shape = meta.get('native_shape_ZYX')
    require(isinstance(shape, list) and len(shape) == 3
            and all(type(v) is int and v > 0 for v in shape), 'POSITIVE_NATIVE_ZYX_REQUIRED')
    indices = fixed8(shape[0])
    if 'fixed8_indices' in meta:
        require(meta['fixed8_indices'] == indices, 'FIXED8_RESELECTION_FORBIDDEN')
    affine = np.asarray(meta.get('native_to_LPS'), dtype=np.float64)
    spacing = np.asarray(meta.get('spacing_ZYX_mm'), dtype=np.float64)
    require(affine.shape == (4, 4) and spacing.shape == (3,)
            and np.isfinite(affine).all() and np.isfinite(spacing).all()
            and (spacing > 0).all(), 'BOUND_FINITE_LPS_GEOMETRY_REQUIRED')
    require(np.allclose(affine[3], [0, 0, 0, 1], atol=1e-7, rtol=0)
            and np.allclose(affine[:2, 0], 0, atol=1e-7, rtol=0)
            and np.allclose(affine[2, 1:3], 0, atol=1e-7, rtol=0)
            and np.allclose(np.linalg.norm(affine[:3, :3], axis=0), spacing, atol=1e-7, rtol=1e-7)
            and abs(np.linalg.det(affine[:3, :3])) >= 1e-8,
            'FROZEN_NATIVE_AXIAL_GEOMETRY_REQUIRED')
    require(meta.get('model_identity') == FROZEN_IDENTITY, 'FROZEN_CLASSIFIER_IDENTITY_REQUIRED')
    return indices


def case_eligibility(meta):
    """Keep a rejected case in the denominator without a callback or payload."""
    if not isinstance(meta, dict):
        return dict(case_id=None, reference_status=None, status='BLOCKED', indices_Z=None,
                    reason='NATIVE_METADATA_DICTIONARY_REQUIRED', medical_reference_verified=False, model_calls=0)
    row = dict(case_id=meta.get('case_id'), reference_status=meta.get('reference_status'),
               medical_reference_verified=False, model_calls=0)
    try:
        row.update(status='QUALIFIED_SYNTHETIC_METADATA_ONLY', indices_Z=validate_native_metadata(meta))
    except (ValueError, TypeError) as exc:
        row.update(status='BLOCKED', reason=str(exc), indices_Z=None)
    return row


def prepare_synthetic_native(native_hu, meta, *, resize):
    """Window/sample/RGB normalization with an explicitly injected resize spy.

    The callback must implement the frozen bilinear-antialias resize semantics
    when a separately authorized real adapter is built. A synthetic spy does
    not establish numerical parity of that backend on real images.
    """
    indices = validate_native_metadata(meta)
    native = np.asarray(native_hu)
    require(native.dtype == np.float32 and list(native.shape) == meta['native_shape_ZYX']
            and np.isfinite(native).all(), 'FINITE_FP32_BOUND_NATIVE_REQUIRED')
    require(callable(resize), 'INJECTED_SYNTHETIC_RESIZE_REQUIRED')
    scalar = np.clip((native[indices] + np.float32(1350)) / np.float32(1500), 0, 1)[:, None]
    resized = np.asarray(resize(scalar.copy(), size=(SIZE, SIZE), interpolation='bilinear', antialias=True))
    require(resized.shape == (K, 1, SIZE, SIZE) and resized.dtype == np.float32
            and np.isfinite(resized).all(), 'FP32_RESIZE_CONTRACT_REQUIRED')
    lo, hi = float(resized.min()), float(resized.max())
    require(lo >= -ROUNDING_ATOL and hi <= 1+ROUNDING_ATOL, 'RESIZE_EXCURSION_OUTSIDE_FROZEN_4EPS')
    recovered = np.clip(resized, 0, 1)
    bag = (np.repeat(recovered, 3, axis=1) - MEAN[None, :, None, None]) / STD[None, :, None, None]
    geometry = dict(native_shape_ZYX=meta['native_shape_ZYX'], indices_Z=indices,
                    native_to_LPS=meta['native_to_LPS'], model_shape=[K, 3, SIZE, SIZE],
                    crop='NONE', model_to_native_YX='(index+.5)*native_size/224-.5',
                    coverage='fixed eight centers, not full-Series lesion coverage',
                    input_sha256=meta['input_sha256'], geometry_sha256=meta['geometry_sha256'],
                    reference_sha256=meta['reference_sha256'], preprocessing_id=PREPROCESS,
                    resize_roundoff_max=max(0., -lo, hi-1),
                    verification='SYNTHETIC_CONTRACT_ONLY_REAL_NUMERICAL_PARITY_NOT_RUN')
    return bag, np.ones((K, SIZE, SIZE), dtype=bool), geometry


def signed_margin_scores(class_cam, effective_bias, logits):
    maps = np.asarray(class_cam)
    bias, raw = np.asarray(effective_bias), np.asarray(logits)
    require(maps.shape == (K, 2, 7, 7) and bias.shape == raw.shape == (2,)
            and maps.dtype.kind == bias.dtype.kind == raw.dtype.kind == 'f'
            and all(np.isfinite(v).all() for v in (maps, bias, raw)), 'FINITE_SIGNED_CAM_BIAS_LOGITS_REQUIRED')
    reconstructed = bias.astype(np.float64) + maps.astype(np.float64).mean((0, 2, 3))
    require(np.all(np.abs(reconstructed-raw) <= ATOL+RTOL*np.abs(raw)), 'SIGNED_CAM_LOGITS_MISMATCH')
    low = maps[:, 1].astype(np.float64) - maps[:, 0].astype(np.float64)
    # Same geometric convention as align_corners=False bilinear interpolation.
    q = (np.arange(SIZE)+.5)*7/SIZE-.5
    lo = np.floor(q).astype(int)
    t = q-lo
    a, b = np.clip(lo, 0, 6), np.clip(lo+1, 0, 6)
    rows = low[:, a, :]*(1-t)[None, :, None] + low[:, b, :]*t[None, :, None]
    scores = rows[:, :, a]*(1-t)[None, None, :] + rows[:, :, b]*t[None, None, :]
    return dict(scores=scores, signed_margin_7x7=low, effective_bias=bias.copy(),
                effective_margin_bias=float(bias[1]-bias[0]),
                reconstructed_logits=reconstructed, raw_logits=raw.copy(),
                maximum_reconstruction_error=float(np.max(np.abs(reconstructed-raw))),
                negative_values_clipped=False, target=1)


def model_centers_to_native(geometry, points_KYX):
    """Nominal resize centers, not a lesion-mask registration proof."""
    points = np.asarray(points_KYX, dtype=np.float64)
    require(points.ndim == 2 and points.shape[1] == 3 and np.isfinite(points).all()
            and np.equal(points[:, 0], np.floor(points[:, 0])).all()
            and ((points[:, 0] >= 0) & (points[:, 0] < K)).all()
            and ((points[:, 1:] >= 0) & (points[:, 1:] < SIZE)).all(), 'MODEL_KYX_CENTERS_REQUIRED')
    native = points.copy()
    native[:, 0] = np.asarray(geometry['indices_Z'])[points[:, 0].astype(int)]
    native[:, 1:] = (points[:, 1:]+.5)*np.asarray(geometry['native_shape_ZYX'][1:])/SIZE-.5
    world = np.concatenate([native, np.ones((len(native), 1))], axis=1) @ np.asarray(geometry['native_to_LPS']).T
    return native, world[:, :3]


def stable_flat_order(scores, valid):
    score, support = np.asarray(scores), np.asarray(valid)
    require(score.shape == support.shape == (K, SIZE, SIZE) and support.dtype == np.bool_
            and score.dtype.kind == 'f' and np.isfinite(score).all() and support.any(),
            'FINITE_FULL_BAG_SCORES_AND_BOOL_SUPPORT_REQUIRED')
    positions = np.flatnonzero(support)
    return positions[np.argsort(-score.ravel()[positions], kind='stable')]


def perturb_input(bag, mask, valid, *, action):
    image, selected, support = np.asarray(bag), np.asarray(mask), np.asarray(valid)
    require(image.shape == (K, 3, SIZE, SIZE) and image.dtype == np.float32
            and np.isfinite(image).all(), 'NORMALIZED_FP32_K8_RGB224_REQUIRED')
    require(selected.shape == support.shape == (K, SIZE, SIZE)
            and selected.dtype == support.dtype == np.bool_
            and not (selected & ~support).any(), 'BOOL_MASK_WITHIN_MODEL_SUPPORT_REQUIRED')
    require(support.all(), 'FULL_BAG_MODEL_SUPPORT_CANNOT_SHRINK_TO_ROI')
    require(action in ('keep', 'remove'), 'KEEP_REMOVE_ACTION_REQUIRED')
    replace = (support & ~selected) if action == 'keep' else selected
    return np.where(replace[:, None], FILL[None, :, None, None], image).astype(np.float32)


class SyntheticFrozenR18Session:
    """Explicit original/empty calls, full-bag input perturbations, no warmup.

    Real readers/callbacks stay disabled, even if a caller requests real mode.
    A returned callback is counted before validating its result. An exception
    in flight makes actual calls unknown and closes this session permanently.
    """
    def __init__(self, bag, metadata, callback=None, *, mode='DISABLED', b1_forward_cap=0):
        require(mode == 'SYNTHETIC_ONLY', 'REAL_EXECUTION_DISABLED_EXPLICIT_SYNTHETIC_MODE_REQUIRED')
        validate_native_metadata(metadata)
        require(callable(callback) and callback is not real_callback, 'SYNTHETIC_SPY_CALLBACK_REQUIRED')
        require(type(b1_forward_cap) is int and 0 <= b1_forward_cap <= 24, 'EXPLICIT_SEPARATE_B1_CAP_REQUIRED')
        self.bag = np.asarray(bag).copy()
        self.valid = np.ones((K, SIZE, SIZE), dtype=bool)
        perturb_input(self.bag, self.valid, self.valid, action='keep')
        self.bag.setflags(write=False)
        self.valid.setflags(write=False)
        self.meta, self.callback = deepcopy(metadata), callback
        self.caps = dict(B0=26, B1=b1_forward_cap)
        self.reserved, self.returned = dict(B0=0, B1=0), dict(B0=0, B1=0)
        self.failed, self.inflight, self.started = None, None, False
        self.completed_B0 = False
        self.trace, self.original, self.empty = [], None, None
        self.evaluated = set()

    def report(self):
        known = self.inflight is None
        return dict(status='FAILED' if self.failed else 'SYNTHETIC_ONLY', failure=self.failed,
                    phase_reserved=self.reserved.copy(), phase_returned=self.returned.copy(),
                    reserved_forward=sum(self.reserved.values()), returned_forward=sum(self.returned.values()),
                    actual_forward=sum(self.returned.values()) if known else None,
                    encoded_input_positions=8*sum(self.returned.values()) if known else None,
                    reserved_input_positions=8*sum(self.reserved.values()), inflight=self.inflight,
                    backward=0, updates=0, warmup=0, retry=False, real_model_calls=0,
                    real_medical_payload_reads=0, trace=deepcopy(self.trace))

    def _call(self, image, phase, label, *, want_cam=False):
        require(self.failed is None, 'SESSION_CLOSED_AFTER_FIRST_FAILURE')
        if self.reserved[phase] >= self.caps[phase]:
            self.failed = 'FORWARD_BUDGET_EXCEEDED_'+phase
            raise Blocked(self.failed)
        self.reserved[phase] += 1
        self.inflight = dict(phase=phase, label=label, samples=K)
        try:
            value = self.callback(image.copy(), want_cam=want_cam)
            self.returned[phase] += 1
            self.inflight = None
            require(isinstance(value, dict) and value.get('model_identity') == FROZEN_IDENTITY
                    and value.get('method_id') == METHOD and type(value.get('target')) is int
                    and value['target'] == 1 and value.get('evidence_status') == 'SYNTHETIC_ONLY',
                    'CALLBACK_MODEL_METHOD_FIXED_TARGET_MISMATCH')
            logits = np.asarray(value['logits'])
            require(logits.shape == (2,) and logits.dtype.kind == 'f'
                    and np.isfinite(logits).all(), 'RAW_TWO_CLASS_LOGITS_REQUIRED')
            result = dict(logits=logits.copy(), margin=float(logits[1]-logits[0]),
                          fixed_target=1, predicted_class=int(logits[1] > logits[0]),
                          original_error_status_not_filtered=True, method_id=METHOD,
                          model_identity=FROZEN_IDENTITY.copy(), phase=phase, label=label)
            if want_cam:
                result.update(signed_margin_scores(value['class_cam'], value['effective_bias'], logits))
            self.trace.append(dict(phase=phase, label=label, samples=K,
                                   raw_logits=logits.tolist(), fixed_margin=result['margin']))
            return result
        except Exception as exc:
            if self.failed is None:
                self.failed = type(exc).__name__+': '+str(exc)
            raise

    def start(self):
        try:
            require(not self.started and self.failed is None, 'ONCE_ONLY_NO_WARMUP_OR_RETRY')
            self.started = True
            self.original = self._call(self.bag, 'B0', 'original_and_CAM', want_cam=True)
            empty = np.zeros_like(self.valid)
            self.empty = self._call(perturb_input(self.bag, empty, self.valid, action='keep'), 'B0', 'empty_fill_baseline')
            return self.original
        except Exception as exc:
            if self.failed is None:
                self.failed = type(exc).__name__+': '+str(exc)
            raise

    def evaluate_candidate(self, mask, *, percent, method, phase='B0'):
        try:
            return self._evaluate_candidate(mask, percent=percent, method=method, phase=phase)
        except Exception as exc:
            if self.failed is None:
                self.failed = type(exc).__name__+': '+str(exc)
            raise

    def _evaluate_candidate(self, mask, *, percent, method, phase):
        require(self.started and self.original is not None and self.empty is not None
                and self.failed is None, 'START_SUCCESS_REQUIRED')
        require(phase in self.caps and type(percent) is int and percent in (5, 10, 20), 'LOCKED_PHASE_AREA_REQUIRED')
        require(phase != 'B0' or not self.completed_B0, 'B0_ALREADY_CLOSED')
        methods = ('CAM', 'RANDOM', 'SHAPE1', 'SHAPE2') if phase == 'B0' else ('CAM_CONNECTED',)
        require(method in methods, 'DECLARED_CANDIDATE_METHOD_REQUIRED')
        key = (phase, percent, method)
        require(key not in self.evaluated, 'NO_REPEATED_CANDIDATE_QUERY')
        selected = np.asarray(mask)
        # Validate and construct both inputs before any callback.
        keep = perturb_input(self.bag, selected, self.valid, action='keep')
        remove = perturb_input(self.bag, selected, self.valid, action='remove')
        count = int(self.valid.sum())*percent//100
        require(int(selected.sum()) == count, 'FLOOR_FULL_BAG_AREA_MISMATCH')
        if self.reserved[phase]+2 > self.caps[phase]:
            self.failed = 'FORWARD_BUDGET_EXCEEDED_'+phase
            raise Blocked(self.failed)
        self.evaluated.add(key)
        rows = {}
        for action, image in (('keep', keep), ('remove', remove)):
            rows[action] = self._call(image, phase, str(key)+':'+action)
        return dict(method_id=METHOD, candidate_method=method, phase=phase, percent=percent,
                    selected_pixels=count, model_support_pixels=int(self.valid.sum()),
                    area_fraction=count/int(self.valid.sum()), fixed_target=1,
                    original_logits=self.original['logits'].tolist(), original_margin=self.original['margin'],
                    original_predicted_class=self.original['predicted_class'],
                    source_label=self.meta.get('source_label'),
                    reference_status=self.meta['reference_status'],
                    keep_logits=rows['keep']['logits'].tolist(), remove_logits=rows['remove']['logits'].tolist(),
                    keep_margin=rows['keep']['margin'], remove_margin=rows['remove']['margin'],
                    keep_margin_drop=self.original['margin']-rows['keep']['margin'],
                    remove_margin_drop=self.original['margin']-rows['remove']['margin'],
                    evidence_status='SYNTHETIC_ONLY_NO_MEDICAL_RESULT')

    def finish_B0(self):
        try:
            require(self.failed is None and self.original is not None and self.empty is not None,
                    'SUCCESSFUL_BASELINES_REQUIRED')
            require(all(('B0', p, m) in self.evaluated for p in (5, 10, 20) for m in ('CAM', 'RANDOM')),
                    'REQUIRED_CAM_RANDOM_ALL_THREE_AREAS_NOT_COMPLETE')
        except Exception as exc:
            if self.failed is None:
                self.failed = type(exc).__name__+': '+str(exc)
            raise
        self.completed_B0 = True
        result = self.report()
        result.update(status='COMPLETE_SYNTHETIC_ONLY_NOT_MEDICAL_RESULT',
                      optional_shape_controls=[list(key) for key in sorted(self.evaluated) if key[2].startswith('SHAPE')],
                      clinical_validity='NOT_EVALUATED')
        return result
