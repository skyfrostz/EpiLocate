"""Additive metadata consumer. Never resolves asset paths or imports a model."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA = 'EPI_NEXT_R18_RESEARCH_REVIEW_V1'
R91_HEAD_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
ENC_POLICY_SHA = 'c72df9804d0efc340c30d17e495ec0e1df918689c9c9271439dcfbd7c6e8e30c'
R91_ENCODER_SHA = 'f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec'
ATOL, RTOL = 1e-8, 1e-10  # ENC prelocked saved-FP64-logit policy, not a new clinical gate.
MAX_JSON_BYTES = 4 * 1024 * 1024


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class Reference(Strict):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern='^[a-f0-9]{64}$')


class ModelBinding(Strict):
    model_id: Literal['R18_MIL_V1']
    version: str = Field(min_length=1)
    head: Reference
    encoder: Reference
    preprocessing: Reference | None
    config_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    standardization: Reference
    standardization_binding: Literal['HEAD_RECEIPT_STATE_MEAN_SCALE']
    effective_bias: list[float] = Field(min_length=2, max_length=2)
    aggregation: Literal['MEAN_8_STANDARDIZED_AFFINE']
    cache_kind: Literal['GAP_ONLY']
    cache_shape: list[int]
    class_labels: list[str] = Field(min_length=2, max_length=2)

    @model_validator(mode='after')
    def dimensions(self):
        if self.cache_shape != [8, 512, 1, 1, 1] or len(set(self.class_labels)) != 2:
            raise ValueError('EXPLICIT_GAP_CACHE_AND_BINARY_CLASS_MAP_REQUIRED')
        return self


class Target(Strict):
    scope: Literal['BAG']
    policy: Literal['DECLARED_FIXED', 'ORIGINAL_ARGMAX_FIXED']
    class_id: int = Field(ge=0, le=1)
    contrast_class: int = Field(ge=0, le=1)
    version: str = Field(min_length=1)


class Spatial(Strict):
    status: Literal['NOT_RUN', 'BLOCKED', 'AVAILABLE']
    reason: str = Field(min_length=1)
    source_kind: Literal['NONE', 'ACTUAL_PRE_GAP_HOOK']
    hook: str | None = None
    feature_shape: list[int] | None = None
    feature_ref: Reference | None = None
    signed_maps: list[Reference] = Field(default_factory=list)
    positive_maps: list[Reference] = Field(default_factory=list)
    positive_derived_from: list[str] = Field(default_factory=list)
    positive_transform: Literal['MAX_SIGNED_WITH_ZERO'] | None = None
    # Metadata declarations only: no pixel/map arrays enter this consumer.
    @model_validator(mode='after')
    def spatial_origin(self):
        if self.status == 'AVAILABLE':
            shape = self.feature_shape
            if (self.source_kind != 'ACTUAL_PRE_GAP_HOOK' or not self.hook or self.feature_ref is None
                    or shape is None or len(shape) != 4 or shape[:2] != [8, 512]
                    or min(shape[2:]) <= 1 or len(self.signed_maps) != 8):
                raise ValueError('GAP_PLACEHOLDERS_ARE_NOT_SPATIAL_FEATURES')
            if self.positive_maps and (len(self.positive_maps) != 8
                    or self.positive_derived_from != [r.sha256 for r in self.signed_maps]
                    or self.positive_transform != 'MAX_SIGNED_WITH_ZERO'
                    or any(a.sha256 == b.sha256 for a, b in zip(self.signed_maps, self.positive_maps))):
                raise ValueError('POSITIVE_MAPS_REQUIRE_SEPARATE_DERIVATION')
            if not self.positive_maps and (self.positive_derived_from or self.positive_transform is not None):
                raise ValueError('MISSING_POSITIVE_ARTIFACTS_CANNOT_HAVE_DERIVATION')
        elif (self.source_kind != 'NONE' or self.hook is not None or self.feature_shape is not None
                or self.feature_ref is not None or self.signed_maps or self.positive_maps
                or self.positive_derived_from or self.positive_transform is not None):
            raise ValueError('UNAVAILABLE_SPATIAL_EVIDENCE_CANNOT_CONTAIN_MAPS')
        return self


class Case(Strict):
    source_group: str = Field(min_length=1)
    split: Literal['TRAIN', 'DEVELOPMENT_VALIDATION']
    source_category: Literal['COVID', 'CAP', 'Normal', 'UNKNOWN']
    source_label: int | None = Field(ge=0, le=1)
    source_label_provenance: str | None = None
    identity_status: Literal['SYNTHETIC', 'DICOM_ID_NONCONFORMANT', 'NOT_EVALUATED', 'NOT_EXPORTED_IN_PRODUCER_JSON']
    input: Reference | None
    input_binding_status: Literal['DECLARED', 'BAG_HASH_AND_NATIVE_INDICES', 'NOT_EXPORTED_IN_PRODUCER_JSON']
    bag_input_sha256: str | None = Field(default=None, pattern='^[a-f0-9]{64}$')
    cache_metadata: Reference | None = None
    feature: Reference
    geometry: Reference
    native_slice_indices: list[int] = Field(min_length=8, max_length=8)
    slice_input_sha256: list[str] | None
    bag_logits: list[float] = Field(min_length=2, max_length=2)
    predicted_class: int = Field(ge=0, le=1)
    saved_positive_probability: float = Field(ge=0, le=1)
    expert_slice_labels: Literal['UNKNOWN']
    target: Target
    contribution_status: Literal['SUCCESS', 'NOT_RUN', 'BLOCKED', 'FAILED']
    # Unweighted, bias-free dot(a_c, f_i), not standalone slice predictions.
    slice_class_dot_products: list[list[float]] | None
    spatial: Spatial

    @model_validator(mode='after')
    def case_semantics(self):
        if (any(x < 0 for x in self.native_slice_indices) or len(set(self.native_slice_indices)) != 8
                or sorted(self.native_slice_indices) != self.native_slice_indices):
            raise ValueError('EIGHT_DISTINCT_NONNEGATIVE_NATIVE_SLICES_REQUIRED')
        if self.slice_input_sha256 is not None and (len(self.slice_input_sha256) != 8 or any(len(x) != 64 or any(c not in '0123456789abcdef' for c in x) for x in self.slice_input_sha256)):
            raise ValueError('EACH_SLICE_REQUIRES_INPUT_SHA')
        if (self.input_binding_status == 'DECLARED') != (self.input is not None and self.slice_input_sha256 is not None):
            raise ValueError('INPUT_BINDING_MISSING_OR_FABRICATED')
        if self.input_binding_status == 'NOT_EXPORTED_IN_PRODUCER_JSON' and (self.input is not None or self.slice_input_sha256 is not None):
            raise ValueError('MISSING_INPUT_HASH_MUST_REMAIN_EXPLICITLY_MISSING')
        if self.input_binding_status == 'BAG_HASH_AND_NATIVE_INDICES':
            if self.bag_input_sha256 is None or self.cache_metadata is None or self.input is not None or self.slice_input_sha256 is not None:
                raise ValueError('BAG_INPUT_HASH_IS_NOT_A_PER_SLICE_HASH')
        elif self.bag_input_sha256 is not None or self.cache_metadata is not None:
            raise ValueError('BAG_HASH_REQUIRES_EXPLICIT_CACHE_METADATA_BINDING')
        if (self.source_label is None) != (self.source_label_provenance is None):
            raise ValueError('SOURCE_LABEL_MUST_HAVE_PROVENANCE_OR_REMAIN_UNKNOWN')
        if self.target.contrast_class != 1 - self.target.class_id:
            raise ValueError('BINARY_TARGET_CONTRAST_MISMATCH')
        if self.target.policy == 'ORIGINAL_ARGMAX_FIXED' and self.target.class_id != max(range(2), key=self.bag_logits.__getitem__):
            raise ValueError('ORIGINAL_BAG_TARGET_MUST_STAY_FIXED')
        if self.predicted_class != int(self.bag_logits[1] > self.bag_logits[0]):
            raise ValueError('FIXED_CLASS1_THRESHOLD_0_5_MISMATCH')
        top = max(self.bag_logits)
        exps = [math.exp(x - top) for x in self.bag_logits]
        if abs(exps[1] / sum(exps) - self.saved_positive_probability) > 1e-12:
            raise ValueError('SAVED_PROBABILITY_MUST_MATCH_SAVED_LOGITS')
        values = self.slice_class_dot_products
        if self.contribution_status == 'SUCCESS':
            if values is None or len(values) != 8 or any(len(v) != 2 for v in values):
                raise ValueError('EXACT_EIGHT_BINARY_SLICE_COMPONENTS_REQUIRED')
        elif values is not None:
            raise ValueError('MISSING_CONTRIBUTIONS_MUST_NOT_BE_FABRICATED')
        return self


class ReviewArtifact(Strict):
    schema_version: Literal['EPI_NEXT_R18_RESEARCH_REVIEW_V1']
    producer_version: str = Field(min_length=1)
    producer_reference: Reference
    producer_compute_counts: dict[str, int]
    upstream_frozen_ref: Reference | None
    evidence: Literal['GENERATED', 'REAL_PRECOMPUTED']
    mode: Literal['PRECOMPUTED']
    prediction_scope: Literal['BAG']
    model: ModelBinding
    predictions_ref: Reference
    contributions_ref: Reference | None
    policy_ref: Reference
    declared_reconstruction_atol: float = Field(ge=0)
    declared_reconstruction_rtol: float = Field(ge=0)
    patient_independence: Literal['UNKNOWN']
    pretraining_overlap: Literal['UNKNOWN']
    cases: list[Case] = Field(min_length=1, max_length=60)

    @model_validator(mode='after')
    def artifact_semantics(self):
        if len({c.source_group for c in self.cases}) != len(self.cases):
            raise ValueError('DUPLICATE_SOURCE_GROUP')
        if (self.evidence == 'REAL_PRECOMPUTED') != (self.model.head.sha256 == R91_HEAD_SHA):
            raise ValueError('R91_R18_HEAD_AND_GENERATED_LINEAGES_MUST_BE_SEPARATE')
        if self.evidence == 'REAL_PRECOMPUTED' and self.model.encoder.sha256 != R91_ENCODER_SHA:
            raise ValueError('FROZEN_R91_ENCODER_REQUIRED')
        if any(v < 0 for v in self.producer_compute_counts.values()):
            raise ValueError('NEGATIVE_PRODUCER_COMPUTE_COUNT')
        if (self.declared_reconstruction_atol, self.declared_reconstruction_rtol) != (ATOL, RTOL):
            raise ValueError('ENC_PRELOCKED_FP64_TOLERANCE_REQUIRED')
        if self.evidence == 'REAL_PRECOMPUTED' and self.policy_ref.sha256 != ENC_POLICY_SHA:
            raise ValueError('ENC_PRELOCKED_POLICY_REFERENCE_REQUIRED')
        for c in self.cases:
            if not math.isfinite(c.bag_logits[c.target.class_id] - c.bag_logits[c.target.contrast_class]):
                raise ValueError('NONFINITE_BAG_MARGIN')
            if (self.evidence == 'GENERATED') != (c.identity_status == 'SYNTHETIC'):
                raise ValueError('REAL_AND_GENERATED_CASES_CANNOT_BE_MIXED')
            if c.slice_class_dot_products is not None:
                if self.contributions_ref is None:
                    raise ValueError('CONTRIBUTION_SOURCE_REFERENCE_REQUIRED')
                reconstructed = reconstruct(self.model.effective_bias, c.slice_class_dot_products)
                if any(not math.isfinite(v[c.target.class_id] - v[c.target.contrast_class]) for v in c.slice_class_dot_products):
                    raise ValueError('NONFINITE_COMPONENT_MARGIN')
                if any(not close(a, b) for a, b in zip(reconstructed, c.bag_logits)):
                    raise ValueError('BAG_LOGITS_NOT_RECONSTRUCTED_WITH_DECLARED_POLICY')
        return self


def reconstruct(bias, components):
    try:
        values = [bias[c] + math.fsum(v[c] for v in components) / 8 for c in range(2)]
    except OverflowError as exc:
        raise ValueError('NONFINITE_RECONSTRUCTION') from exc
    if not all(math.isfinite(x) for x in values):
        raise ValueError('NONFINITE_RECONSTRUCTION')
    return values


def close(actual, expected):
    return math.isfinite(actual) and math.isfinite(expected) and abs(actual - expected) <= ATOL + RTOL * abs(expected)


def validate_artifact(value):
    return ReviewArtifact.model_validate(value)


def load_json_metadata(path, expected_sha256):
    """Read exactly this JSON only; do not follow any embedded reference."""
    p = Path(path)
    if p.suffix != '.json' or p.is_symlink() or p.stat().st_size > MAX_JSON_BYTES:
        raise ValueError('BOUNDED_JSON_METADATA_REQUIRED')
    with p.open('rb') as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('JSON_METADATA_SHA_OR_SIZE_MISMATCH')
    def pairs(items):
        result = {}
        for key, val in items:
            if key in result:
                raise ValueError('DUPLICATE_JSON_KEY')
            result[key] = val
        return result
    def nonfinite(_):
        raise ValueError('NONFINITE_JSON_NUMBER')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def metadata_summary(artifact):
    # This is metadata arithmetic, not model execution or clinical validation.
    errors = [c for c in artifact.cases if c.source_label is not None and c.source_label != c.predicted_class]
    return dict(status='METADATA_VALID', evidence=artifact.evidence, prediction_scope='BAG',
        source_groups=len(artifact.cases), source_label_error_count=len(errors),
        error_source_counts={k: sum(c.source_category == k for c in errors) for k in ['COVID', 'CAP', 'Normal', 'UNKNOWN']},
        contribution_cases=sum(c.contribution_status == 'SUCCESS' for c in artifact.cases),
        spatial_metadata_cases=sum(c.spatial.status == 'AVAILABLE' for c in artifact.cases),
        referenced_assets_read=0, pixels_read=0, model_calls=0, metadata_arithmetic=True,
        reference_verification='DECLARED_REFERENCES_NOT_READ_OR_HASH_VERIFIED',
        numeric_policy='ENC prelocked FP64 atol=1e-8, rtol=1e-10; metadata arithmetic only, no independent model/asset/clinical acceptance',
        clinical_validity='NOT_ESTABLISHED')


def from_encoder_contributions(value, source_ref, *, evidence='REAL_PRECOMPUTED', cache=None, cache_ref=None):
    """Explicit adapter for ENC's actual JSON; no NPZ/head/CT/reference reads."""
    if (value.get('schema') != 'R92_R18_SLICE_CONTRIBUTIONS_V1' or value.get('status') != 'PASS'
            or value.get('prediction_scope') != 'BAG' or value.get('K') != 8
            or value.get('contribution_scope') != 'SAVED_SLICE_GAP_AFFINE_COMPONENT'
            or value.get('threshold') != .5 or value.get('threshold_tuning') is not False
            or not value['spatial_maps'].startswith('NOT AVAILABLE')):
        raise ValueError('SUPPORTED_ENC_SAVED_GAP_CONTRIBUTION_PROFILE_REQUIRED')
    if any(value['counts'].get(k) != 0 for k in ['backbone_forward', 'torch_head_forward', 'backward', 'updates', 'native_CT_reads', 'weight_file_reads']):
        raise ValueError('SAVED_FEATURE_ALGEBRA_PROFILE_CANNOT_DECLARE_NEW_MODEL_OR_CT_WORK')
    rows = value['cases']
    if not rows:
        raise ValueError('EMPTY_ENCODER_DELIVERY')
    if len({c['record_id'] for c in rows}) != len(rows) or len({c['source_group_id'] for c in rows}) != len(rows):
        raise ValueError('ENC_UNIQUE_RECORD_AND_SOURCE_GROUP_REQUIRED')
    first = rows[0]
    context, head, bias = first['model_version'], first['head_reference'], first['effective_bias']
    if (cache is None) != (cache_ref is None):
        raise ValueError('CACHE_JSON_AND_REFERENCE_PAIR_REQUIRED')
    cache_rows = None
    if cache is not None:
        cache_rows = {(c['record_id'], c['source_group_id']): c for c in cache['rows']}
        keys = {(c['record_id'], c['source_group_id']) for c in rows}
        if (cache['status'] != 'PASS' or cache['context'] != context or len(cache_rows) != len(cache['rows'])
                or len({c['record_id'] for c in cache['rows']}) != len(cache['rows'])
                or len(keys) != len(rows) or set(cache_rows) != keys):
            raise ValueError('EXACT_SOURCE_GROUP_RECORD_CACHE_JOIN_REQUIRED')
    def reference_only(ref):
        return dict(path=ref['path'], sha256=ref['sha256'])
    cases = []
    for row in rows:
        bag_sha, cache_metadata = None, None
        if cache_rows is not None:
            saved = cache_rows[(row['record_id'], row['source_group_id'])]
            if (saved['feature'] != row['feature_reference'] or saved['geometry'] != row['geometry_reference']
                    or saved['identity']['geometry_sha'] != row['geometry_reference']['sha256']
                    or saved['split'] != row['split'] or saved['source_diagnosis'] != row['source_diagnosis']
                    or saved['task_label'] != row['source_label']['class_id']):
                raise ValueError('CACHE_INPUT_FEATURE_GEOMETRY_OR_LABEL_JOIN_MISMATCH')
            bag_sha, cache_metadata = saved['identity']['input_sha'], reference_only(cache_ref)
        if (row['model_version'] != context or row['head_reference'] != head
                or row['effective_bias'] != bias or row['reconstruction_status'] != 'PASS'
                or row['expert_slice_label_availability'] != 'UNKNOWN'):
            raise ValueError('ENC_CASE_HEAD_OR_RECONSTRUCTION_IDENTITY_MISMATCH')
        raw, weighted, component = row['raw_class_terms'], row['weighted_class_terms'], row['slice_component_logits']
        if any(len(a) != 8 or any(len(v) != 2 for v in a) for a in [raw, weighted, component]):
            raise ValueError('ENC_EIGHT_BINARY_COMPONENTS_REQUIRED')
        for i in range(8):
            if (any(not close(weighted[i][c], raw[i][c] / 8) or not close(component[i][c], raw[i][c] + bias[c]) for c in range(2))
                    or not close(row['weighted_margin_terms'][i], weighted[i][1] - weighted[i][0])
                    or not close(row['slice_component_margin'][i], component[i][1] - component[i][0])):
                raise ValueError('WEIGHTED_AND_BIAS_INCLUDED_COMPONENT_UNITS_MISMATCH')
        if not close(row['effective_margin_bias'], bias[1] - bias[0]):
            raise ValueError('EFFECTIVE_MARGIN_BIAS_MISMATCH')
        if row['correct'] != (row['saved_predicted_class'] == row['source_label']['class_id']):
            raise ValueError('SOURCE_LABEL_ERROR_JOIN_MISMATCH')
        cases.append(dict(source_group=row['source_group_id'],
            split={'train_weak': 'TRAIN', 'val_classification': 'DEVELOPMENT_VALIDATION'}[row['split']],
            source_category={'COVID-19': 'COVID', 'CAP': 'CAP', 'Normal': 'Normal'}[row['source_diagnosis']],
            source_label=row['source_label']['class_id'], source_label_provenance=json.dumps(row['source_label'], sort_keys=True),
            identity_status='SYNTHETIC' if evidence == 'GENERATED' else 'NOT_EXPORTED_IN_PRODUCER_JSON',
            input=None, input_binding_status='BAG_HASH_AND_NATIVE_INDICES' if cache_rows is not None else 'NOT_EXPORTED_IN_PRODUCER_JSON',
            bag_input_sha256=bag_sha, cache_metadata=cache_metadata, feature=reference_only(row['feature_reference']),
            geometry=reference_only(row['geometry_reference']), native_slice_indices=row['geometry']['indices_Z'],
            slice_input_sha256=None, bag_logits=row['saved_raw_logits'], predicted_class=row['saved_predicted_class'],
            saved_positive_probability=row['saved_positive_probability'], expert_slice_labels='UNKNOWN',
            target=dict(scope='BAG', policy='DECLARED_FIXED', class_id=1, contrast_class=0, version='R18_BAG_CLASS1_MARGIN_V1'),
            contribution_status='SUCCESS', slice_class_dot_products=raw,
            spatial=dict(status='NOT_RUN', reason=value['spatial_maps'], source_kind='NONE')))
    return validate_artifact(dict(schema_version=SCHEMA, producer_version=value['schema'], evidence=evidence,
        producer_reference=reference_only(value['implementation']), producer_compute_counts=value['counts'],
        upstream_frozen_ref=reference_only(value['frozen_reference']),
        mode='PRECOMPUTED', prediction_scope='BAG',
        model=dict(model_id='R18_MIL_V1', version=context['source_commit'], head=reference_only(head),
            encoder=reference_only(context['checkpoint_reference']), preprocessing=None, config_sha256=context['config_sha256'],
            standardization=reference_only(head), standardization_binding='HEAD_RECEIPT_STATE_MEAN_SCALE',
            effective_bias=bias, aggregation='MEAN_8_STANDARDIZED_AFFINE',
            cache_kind='GAP_ONLY', cache_shape=[8, 512, 1, 1, 1], class_labels=['Normal proxy', 'COVID+CAP proxy']),
        predictions_ref=reference_only(source_ref), contributions_ref=reference_only(source_ref),
        policy_ref=reference_only(value['numerical_policy']), declared_reconstruction_atol=ATOL,
        declared_reconstruction_rtol=RTOL, patient_independence='UNKNOWN', pretraining_overlap='UNKNOWN', cases=cases))
