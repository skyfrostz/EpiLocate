"""Consume ENC v4 saved F0 only; no torch, encoder, head call or dense mapping."""
from dataclasses import dataclass
import hashlib
import io
import itertools
import json
from pathlib import Path
import zipfile

import numpy as np

from .contracts import HandlerResult
from .runner import HandlerOutput


@dataclass(frozen=True)
class F0ReplayBinding:
    evaluation: dict
    head: dict
    cache: dict
    record_id: str
    data_manifest_sha256: str
    source_commit: str
    artifact_root: Path
    application_binding: dict


class BoundArtifacts:
    def __init__(self, root, limit):
        self.root = Path(root).resolve()
        self.remaining = limit

    def read(self, ref):
        path = Path(ref['path'])
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ValueError('F0_ARTIFACT_OUTSIDE_BOUND_ROOT')
        with path.open('rb') as stream:
            raw = stream.read(self.remaining + 1)
        if len(raw) > self.remaining:
            raise ValueError('F0_READ_BUDGET')
        self.remaining -= len(raw)
        if hashlib.sha256(raw).hexdigest() != ref['sha256']:
            raise ValueError('F0_ARTIFACT_SHA_MISMATCH')
        return raw

    def json(self, ref):
        return json.loads(self.read(ref))

    def array(self, ref, shape, dtype):
        value = np.load(io.BytesIO(self.read(ref)), allow_pickle=False)
        if value.shape != shape or value.dtype != dtype or not np.isfinite(value).all():
            raise ValueError('F0_ARRAY_SHAPE_DTYPE_FINITE')
        return value


def one_record(rows, record_id):
    matched = [row for row in rows if row['record_id'] == record_id]
    if len(matched) != 1:
        raise ValueError('F0_UNIQUE_RECORD_REQUIRED')
    return matched[0]


def validate_f0_consumption(req, prediction, f0, sources):
    """Repeat the persisted numerical/identity gate on the independent backend."""
    if f0['schema'] != 'EPI_NEXT_F0_CONSUMPTION_V1':
        raise ValueError('F0_CONSUMPTION_VERSION')
    if (f0['explanation_target'] != req.task.target_class
            or f0['predicted_class'] != prediction.predicted_class
            or f0['raw_logits'] != prediction.logits
            or f0['head_sha256'] != req.model.head_sha256
            or f0['geometry_sha256'] != req.input.geometry_ledger_sha256
            or sources['head'] != req.model.head_sha256):
        raise ValueError('F0_PERSISTED_BINDING_MISMATCH')
    values = np.asarray(f0['signed_values'], dtype=np.float64)
    bias = np.asarray(f0['effective_bias'], dtype=np.float64)
    if (values.shape != (2, 4, 4, 4) or bias.shape != (2,)
            or not np.isfinite(values).all() or not np.isfinite(bias).all()):
        raise ValueError('F0_SIGNED_COARSE_GRID_REQUIRED')
    if not np.allclose(values.mean(axis=(1, 2, 3)) + bias,
                       prediction.logits, atol=1e-10, rtol=1e-12):
        raise ValueError('F0_LOGIT_RECONSTRUCTION_MISMATCH')
    label = f0['source_label']
    if (set(label) != {'class_id', 'label', 'scope', 'provenance_sha256'}
            or type(label['class_id']) is not int or not 0 <= label['class_id'] < len(req.task.class_labels)
            or label['scope'] != 'SOURCE_GROUP' or not label['label']
            or label['provenance_sha256'] != sources['data_manifest']):
        raise ValueError('F0_SOURCE_LABEL_INVALID')
    return f0


class F0PrecomputedAdapter:
    def __init__(self, binding_provider):
        self.binding_provider = binding_provider

    def __call__(self, req, input_path, output_dir, context):
        if req.algorithm_mode != 'CTFM' or req.execution_mode != 'PRECOMPUTED':
            raise ValueError('F0_EXPLICIT_PRECOMPUTED_REQUIRED')
        if any((req.budget.forward, req.budget.backward, req.budget.updates)):
            raise ValueError('F0_REPLAY_ZERO_COMPUTE_REQUIRED')
        binding = self.binding_provider(req)
        reader = BoundArtifacts(binding.artifact_root, req.budget.output_bytes)
        evaluation, head, cache = [reader.json(ref) for ref in
                                   (binding.evaluation, binding.head, binding.cache)]
        for value, schema in ((evaluation, 'CTFM_RESEARCH_EVALUATION_V4'),
                              (head, 'CTFM_RESEARCH_HEAD_CHECKPOINT_V4'),
                              (cache, 'CTFM_RESEARCH_CACHE_RECEIPT_V4')):
            if value['schema'] != schema or value['status'] != 'PASS':
                raise ValueError('F0_SOURCE_RECEIPT_REQUIRED')
        synthetic = req.input.source_identity_status == 'SYNTHETIC'
        if len({v['evidence_type'] for v in (evaluation, head, cache)}) != 1 or (
                (evaluation['evidence_type'] == 'SYNTHETIC') != synthetic):
            raise ValueError('F0_SOURCE_EVIDENCE_MISMATCH')
        row = one_record(cache['rows'], binding.record_id)
        result = one_record(evaluation['F0'], binding.record_id)
        version = result['model_version']
        expected = dict(backbone_sha256=req.model.encoder_sha256,
                        head_checkpoint_sha256=binding.head['sha256'],
                        feature_cache_receipt_sha256=binding.cache['sha256'],
                        data_manifest_sha256=binding.data_manifest_sha256,
                        source_commit=binding.source_commit, config_sha256=req.config_sha256,
                        seed=17, precision='FP32 feature/train, FP64 GAP/evaluation/contribution')
        identity = row['identity']
        if (version != expected or req.model.head_sha256 != binding.head['sha256']
                or cache['model_sha256'] != req.model.encoder_sha256
                or cache['config_sha256'] != req.config_sha256
                or cache['source_commit'] != binding.source_commit
                or cache['data_manifest_sha256'] != binding.data_manifest_sha256
                or head['data_manifest_sha256'] != binding.data_manifest_sha256
                or head['cache_receipt_sha256'] != binding.cache['sha256']
                or head['model_sha256'] != req.model.encoder_sha256
                or head['final_update'] != 100 or head['seed'] != 17
                or head['threshold'] != .5 or head['tie'] != 'Normal'
                or identity['input_sha'] != req.input.input_sha256
                or identity['geometry_sha'] != req.input.geometry_ledger_sha256
                or identity['preprocess_sha'] != req.model.preprocessing_sha256
                or identity['model_sha'] != req.model.encoder_sha256
                or identity['config_sha'] != req.config_sha256
                or identity['code_sha'] != binding.source_commit
                or identity['split_manifest_sha'] != binding.data_manifest_sha256
                or row['input']['sha256'] != req.input.input_sha256
                or row['geometry'] != result['geometry']):
            raise ValueError('F0_HEAD_CACHE_INPUT_VERSION_MISMATCH')
        # Bound head state is verified, but never loaded into a callable model.
        state = {}
        for name, shape in (('mean', (512,)), ('scale', (512,)),
                            ('linear.weight', (2, 512)), ('linear.bias', (2,))):
            state[name] = reader.array(head['state'][name], shape, np.dtype('float32')).astype(np.float64)
            if name == 'scale' and np.any(state[name] < 1e-6):
                raise ValueError('F0_TRAIN_SCALE_FLOOR')
        raw = reader.read(row['feature'])
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 256 * 1024:
                raise ValueError('F0_CACHE_DECOMPRESSION_BUDGET')
        with np.load(io.BytesIO(raw), allow_pickle=False) as loaded:
            features = loaded['features']
            metadata = json.loads(loaded['metadata'].tobytes())
        if (features.shape != (1, 512, 4, 4, 4) or features.dtype != np.float32
                or not np.isfinite(features).all() or metadata['identity'] != identity):
            raise ValueError('F0_SPATIAL_CACHE_MISMATCH')
        feature_header = json.dumps(dict(shape=list(features.shape), dtype=str(features.dtype)),
                                    sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        if metadata['feature_sha'] != hashlib.sha256(feature_header + features.tobytes()).hexdigest():
            raise ValueError('F0_FEATURE_CONTENT_SHA_MISMATCH')
        gap = reader.array(row['gap'], (1, 512), np.dtype('float64'))
        if not np.array_equal(gap, features.astype(np.float64).mean(axis=(2, 3, 4))):
            raise ValueError('F0_FP64_GAP_MISMATCH')
        values = reader.array(result['signed_contribution'], (1, 2, 4, 4, 4), np.dtype('float64'))
        weight, bias, mean, scale = (state['linear.weight'], state['linear.bias'],
                                     state['mean'], state['scale'])
        spatial64 = features.astype(np.float64)
        expected_signed = np.einsum('nfxyz,cf->ncxyz', spatial64, weight/scale)
        expected_bias = bias - np.sum(weight*mean/scale, axis=1)
        evaluated_logits = ((gap-mean)/scale) @ weight.T + bias
        if (not np.allclose(values, expected_signed, atol=1e-12, rtol=1e-12)
                or not np.allclose(result['effective_bias'], expected_bias, atol=1e-12, rtol=1e-12)
                or not np.allclose(result['raw_logits'], evaluated_logits[0], atol=1e-10, rtol=1e-12)):
            raise ValueError('F0_HEAD_FEATURE_CONTRIBUTION_MISMATCH')
        geometry = reader.json(row['geometry'])
        if (row['geometry']['sha256'] != req.input.geometry_ledger_sha256
                or geometry['native_shape_ZYX'] != list(req.input.native_shape_zyx)
                or geometry['native_to_lps'] != req.input.affine_lps
                or not result['geometry_valid'] or not req.input.mapping_verified
                or req.input.scope != 'VOLUME'
                or row['split'] not in {'train_weak','val_classification'}
                or req.task.definition_id != 'COVIDCTMD_SOURCE_CASE_WEAK_BINARY_V1'
                or req.task.class_labels != ['Normal_SOURCE','COVID-19_OR_CAP_SOURCE']
                or row['task_label'] not in (0,1)
                or (row['task_label']==0) != (row['source_diagnosis']=='Normal')):
            raise ValueError('F0_NATIVE_GEOMETRY_BINDING_MISMATCH')
        centers = np.array(list(itertools.product(range(4), repeat=3)), dtype=np.float64)
        homogeneous = np.column_stack((centers, np.ones(64)))
        transform = np.asarray(geometry['nominal_feature_to_native'], dtype=np.float64)
        affine = np.asarray(geometry['native_to_lps'], dtype=np.float64)
        native = homogeneous @ transform.T
        lps = native @ affine.T
        if (not np.isfinite(native).all() or not np.isfinite(lps).all()
                or not np.allclose(native @ np.linalg.inv(transform).T, homogeneous, atol=1e-8, rtol=0)
                or not np.allclose(lps @ np.linalg.inv(affine).T, native, atol=1e-8, rtol=0)
                or not np.allclose(native[:, :3], result['native_nominal_centers_ZYX'], atol=1e-8, rtol=0)
                or not np.allclose(lps[:, :3], result['LPS_centers_mm'], atol=1e-8, rtol=0)):
            raise ValueError('F0_COARSE_COORDINATE_MISMATCH')
        logits = result['raw_logits']
        pred = result['predicted_class']
        probability = result['positive_probability']
        stable = np.exp(np.asarray(logits) - np.max(logits)); stable /= stable.sum()
        if pred != int(probability > .5) or not np.isclose(probability, stable[1], atol=1e-12, rtol=1e-12):
            raise ValueError('F0_UNCALIBRATED_PREDICTION_MISMATCH')
        sources = dict(head=binding.head['sha256'], evaluation=binding.evaluation['sha256'],
                       cache_receipt=binding.cache['sha256'], spatial_features=row['feature']['sha256'],
                       gap512=row['gap']['sha256'], geometry=row['geometry']['sha256'],
                       signed_contribution=result['signed_contribution']['sha256'],
                       data_manifest=binding.data_manifest_sha256, input=req.input.input_sha256)
        app_expected = dict(case_id=req.input.case_id,study_id=req.input.study_id,
            series_id=req.input.series_id,slice_id=req.input.slice_id,
            input_sha256=req.input.input_sha256,display_sha256=req.input.display_sha256)
        if binding.application_binding != app_expected:
            raise ValueError('F0_CASE_SERIES_DISPLAY_BINDING_MISMATCH')
        consumption_binding = dict(record_id=binding.record_id,
            source_group_id=row['source_group_id'],data_manifest_sha256=binding.data_manifest_sha256,
            study_key=identity['study_key'],series_key=identity['series_key'],
            head_sha256=binding.head['sha256'],cache_receipt_sha256=binding.cache['sha256'],
            source_commit=binding.source_commit,application_binding=app_expected)
        f0 = dict(schema='EPI_NEXT_F0_CONSUMPTION_V1', record_id=binding.record_id,
                  consumption_binding=consumption_binding,
                  explanation_target=req.task.target_class, predicted_class=pred,
                  source_label=dict(class_id=row['task_label'], label=row['source_diagnosis'],
                                    scope='SOURCE_GROUP', provenance_sha256=binding.data_manifest_sha256),
                  raw_logits=logits, signed_values=values[0].tolist(), effective_bias=result['effective_bias'],
                  head_sha256=binding.head['sha256'], geometry_sha256=row['geometry']['sha256'],
                  nominal_native_centers_zyx=result['native_nominal_centers_ZYX'],
                  lps_centers_mm=result['LPS_centers_mm'], coarse_shape=[4, 4, 4],
                  semantics='signed coarse source-class contribution; no ReLU; not lesion probability',
                  calibration='UNCALIBRATED')
        output = HandlerResult(execution_status='SUCCESS', algorithm_status='F0_SAVED_V4', reason=None,
            prediction=dict(logits=logits, predicted_class=pred, class_label=req.task.class_labels[pred],
                            probabilities=[1-probability, probability]), candidates=[], layers=[],
            actual_forward=0, actual_backward=0, actual_updates=0, runtime_seconds=context.clock()-context.start,
            source_artifacts=sources, diagnostics=dict(precomputed_replay=True,
                source_evidence_type=evaluation['evidence_type'], spatial_features_shape=[1,512,4,4,4],
                gap_shape=[1,512], f0=f0, source_execution_cost=evaluation['calls']))
        validate_f0_consumption(req, output.prediction, f0, sources)
        return HandlerOutput(output, {})
