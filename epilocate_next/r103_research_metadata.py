"""Versioned R102 receipt projection. Embedded arrays are not inspected or copied.

Reuse the bounded JSON reader and strict references, not the GAP-only algebra
validator. No reference is resolved, hashed, loaded or medically rendered here.
"""
from __future__ import annotations

import math
from typing import Literal

from pydantic import Field, model_validator

from .r18_research_artifact import Reference, Strict, R91_HEAD_SHA, R91_ENCODER_SHA, reconstruct, close

SCHEMA = 'EPI_NEXT_RESEARCH_METADATA_V1'
CLASSES = ['Normal_SOURCE', 'COVID-19_OR_CAP_SOURCE']


class TargetMetadata(Strict):
    class_id: int = Field(ge=0, le=1)
    contrast_class: int = Field(ge=0, le=1)
    class_label: str
    policy: Literal['DECLARED_FIXED', 'ORIGINAL_ARGMAX_FIXED', 'NOT_EXPORTED_IN_THIS_JSON']

    @model_validator(mode='after')
    def binary_target(self):
        if self.contrast_class != 1-self.class_id or self.class_label not in (CLASSES[self.class_id], 'NOT_EXPORTED_IN_THIS_JSON'):
            raise ValueError('TARGET_CLASS_LABEL_OR_CONTRAST_MISMATCH')
        return self


class SpatialMetadata(Strict):
    status: Literal['REFERENCES_ONLY_NOT_READ', 'INLINE_ARRAYS_NOT_PROJECTED', 'NOT_AVAILABLE']
    feature_shape: list[int] | None = None
    signed_class: Reference | None = None
    signed_margin: Reference | None = None
    positive_margin_display: Reference | None = None
    margin_definition: Literal['CLASS1_MINUS_CLASS0'] | None = None
    positive_transform: Literal['MAX_SIGNED_MARGIN_WITH_ZERO_DISPLAY_ONLY'] | None = None
    positive_derived_from_sha256: str | None = None

    @model_validator(mode='after')
    def provenance(self):
        refs = [self.signed_class, self.signed_margin, self.positive_margin_display]
        if self.status == 'REFERENCES_ONLY_NOT_READ':
            if (self.feature_shape != [8, 512, 7, 7] or any(r is None for r in refs)
                    or self.margin_definition != 'CLASS1_MINUS_CLASS0'
                    or self.positive_transform != 'MAX_SIGNED_MARGIN_WITH_ZERO_DISPLAY_ONLY'
                    or self.positive_derived_from_sha256 != self.signed_margin.sha256
                    or len({r.sha256 for r in refs}) != 3):
                raise ValueError('SIGNED_AND_POSITIVE_SPATIAL_PROVENANCE_REQUIRED')
        elif any(r is not None for r in refs) or any(v is not None for v in (
                self.feature_shape, self.margin_definition, self.positive_transform,
                self.positive_derived_from_sha256)):
            raise ValueError('UNAVAILABLE_MAPS_CANNOT_CARRY_DECLARED_DERIVATION')
        return self


class ResponseMetadata(Strict):
    name: str
    method: Literal['CAM', 'E1', 'E2', 'OLD_FOURGRID']
    action: Literal['keep', 'remove', 'soft_keep', 'mechanism']
    area_percent: int | None = None
    logits: list[float] = Field(min_length=2, max_length=2)
    target_margin: float
    raw_bag_squared_loss: float | None = Field(default=None, ge=0)
    K2_component_squared_loss: float | None = Field(default=None, ge=0)


class SliceContributions(Strict):
    source: Reference
    units: Literal['UNWEIGHTED_BIAS_FREE_CLASS_DOT_PRODUCTS']
    class_dot_products: list[list[float]] = Field(min_length=8, max_length=8)
    effective_bias: list[float] = Field(min_length=2, max_length=2)

    @model_validator(mode='after')
    def dimensions(self):
        if any(len(v) != 2 for v in self.class_dot_products):
            raise ValueError('EIGHT_BINARY_SLICE_COMPONENTS_REQUIRED')
        return self


class CaseMetadata(Strict):
    source_group: str
    lineage: Literal['FROZEN_R18', 'OLD_CASE3_NOT_R18']
    prediction_scope: Literal['BAG', 'OLD_SINGLE_SLICE']
    bag_logits: list[float] | None = Field(default=None, min_length=2, max_length=2)
    target: TargetMetadata
    native_indices: list[int] = Field(default_factory=list)
    head: Reference | None = None
    geometry: Reference | None = None
    model_binding: Literal['HEAD_AND_ENCODER_DECLARED', 'NOT_EXPORTED_IN_THIS_JSON']
    # Slice contributions require their own scalar JSON contract; no means of
    # referenced signed CAM arrays are silently calculated to fill this field.
    slice_signed_contribution_status: Literal['NOT_EXPORTED_IN_THIS_JSON', 'AVAILABLE_SAVED_GAP_SCALARS'] = 'NOT_EXPORTED_IN_THIS_JSON'
    slice_contributions: SliceContributions | None = None
    expert_slice_reference: Literal['UNKNOWN'] = 'UNKNOWN'
    expert_pixel_reference: Literal['UNKNOWN'] = 'UNKNOWN'
    spatial: SpatialMetadata
    candidate_status: Literal['NOT_ASSESSED', 'NO_CALIBRATED_RELIABILITY_RULE', 'NOT_APPLICABLE_OLD_MECHANISM']
    reliable_candidates: list[str] = Field(default_factory=list, max_length=0)
    absence_of_lesions: Literal['UNKNOWN'] = 'UNKNOWN'
    responses: list[ResponseMetadata] = Field(default_factory=list)

    @model_validator(mode='after')
    def semantics(self):
        if self.lineage == 'FROZEN_R18':
            if self.target.class_label != CLASSES[self.target.class_id]:
                raise ValueError('R18_TARGET_CLASS_LABEL_REQUIRED')
            if self.prediction_scope != 'BAG' or len(self.native_indices) != 8 or sorted(set(self.native_indices)) != self.native_indices or min(self.native_indices) < 0:
                raise ValueError('EXACT_FIXED_EIGHT_NATIVE_INDICES_REQUIRED')
        elif self.prediction_scope != 'OLD_SINGLE_SLICE' or self.native_indices or self.bag_logits is not None:
            raise ValueError('OLD_CASE3_CANNOT_BECOME_R18_BAG')
        if self.model_binding == 'HEAD_AND_ENCODER_DECLARED' and self.head is None:
            raise ValueError('DECLARED_HEAD_MISSING')
        if self.target.policy == 'ORIGINAL_ARGMAX_FIXED':
            if self.bag_logits is None or self.target.class_id != max(range(2), key=self.bag_logits.__getitem__):
                raise ValueError('ORIGINAL_BAG_ARGMAX_TARGET_DRIFT')
        if (self.slice_signed_contribution_status == 'AVAILABLE_SAVED_GAP_SCALARS') != (self.slice_contributions is not None):
            raise ValueError('CONTRIBUTION_STATUS_VALUES_MISMATCH')
        if self.slice_contributions is not None:
            sc=self.slice_contributions
            if self.lineage != 'FROZEN_R18' or self.bag_logits is None or any(not close(a,b) for a,b in zip(reconstruct(sc.effective_bias,sc.class_dot_products),self.bag_logits)):
                raise ValueError('SIGNED_SLICE_SCALARS_MUST_RECONSTRUCT_SAVED_BAG')
        for r in self.responses:
            if abs(r.target_margin-(r.logits[self.target.class_id]-r.logits[self.target.contrast_class])) > 1e-6:
                raise ValueError('RESPONSE_TARGET_MARGIN_MISMATCH')
            if r.K2_component_squared_loss is not None and (r.raw_bag_squared_loss is None or not math.isclose(r.K2_component_squared_loss, 64*r.raw_bag_squared_loss, abs_tol=1e-10, rel_tol=1e-10)):
                raise ValueError('K8_BAG_AND_COMPONENT_LOSS_UNITS_MISMATCH')
        return self


class LabelStructure(Strict):
    index_rows: int = Field(ge=0)
    array_shape: list[int] = Field(min_length=2, max_length=2)
    mapping_status: Literal['UNKNOWN'] = 'UNKNOWN'
    paired_source_groups: None = None
    evaluable_slices: None = None
    reason: str

    @model_validator(mode='after')
    def dimensions(self):
        if self.array_shape[0]!=self.index_rows or min(self.array_shape)<=0:
            raise ValueError('LABEL_STRUCTURE_DIMENSION_MISMATCH')
        return self


class MetadataArtifact(Strict):
    schema_version: Literal['EPI_NEXT_RESEARCH_METADATA_V1']
    evidence: Literal['GENERATED', 'REAL_PRECOMPUTED_JSON']
    source: Reference
    producer_schema: str
    supplemental_sources: list[Reference] = Field(default_factory=list)
    kind: Literal['LABEL_STRUCTURE', 'R18_SPATIAL', 'CONDITIONAL_BAG', 'OLD_FOURGRID']
    execution_status: Literal['SUCCESS']
    labels: LabelStructure | None = None
    cases: list[CaseMetadata] = Field(default_factory=list, max_length=20)
    method_limits: list[str] = Field(min_length=1)
    clinical_validity: Literal['NOT_ESTABLISHED'] = 'NOT_ESTABLISHED'
    referenced_assets_read: Literal[0] = 0
    metadata_arithmetic_only: Literal[True] = True

    @model_validator(mode='after')
    def separation(self):
        if (self.kind == 'LABEL_STRUCTURE') != (self.labels is not None) or (self.kind == 'LABEL_STRUCTURE') == bool(self.cases):
            raise ValueError('LABEL_STRUCTURE_IS_NOT_A_CASE_REFERENCE')
        if len({c.source_group for c in self.cases}) != len(self.cases):
            raise ValueError('DUPLICATE_SOURCE_GROUP')
        if any((c.lineage == 'OLD_CASE3_NOT_R18') != (self.kind == 'OLD_FOURGRID') for c in self.cases):
            raise ValueError('OLD_AND_R18_LINEAGES_CANNOT_MIX')
        if self.evidence == 'GENERATED' and any(not c.source_group.startswith('GENERATED-') for c in self.cases):
            raise ValueError('GENERATED_CASE_NAMESPACE_REQUIRED')
        return self


def validate_metadata(value):
    return MetadataArtifact.model_validate(value)


def _ref(value):
    return Reference.model_validate({k: value[k] for k in ('path', 'sha256')})


def _target(class_id, policy='DECLARED_FIXED'):
    return dict(class_id=class_id, contrast_class=1-class_id, class_label=CLASSES[class_id], policy=policy)


def from_r102_receipt(value, source, *, evidence='REAL_PRECOMPUTED_JSON'):
    """Explicit schema adapters. No embedded map/mask array field is accessed."""
    schema = value.get('schema')
    result = dict(schema_version=SCHEMA, evidence=evidence, source=_ref(source), producer_schema=schema)
    if schema == 'ARCHIVE_BOUND_AB_RESULT_V2':
        if value['status'] != 'AB_EVIDENCE_SAVED_MAPPING_UNKNOWN' or value['registry'] != 'NOT_RUN':
            raise ValueError('UNSUPPORTED_LABEL_MAPPING_STATE')
        return validate_metadata(dict(**result, kind='LABEL_STRUCTURE', execution_status='SUCCESS',
            labels=dict(index_rows=value['index_rows_observed'], array_shape=value['label_shape'],
                        reason='Version, valid extent, padding and native-Z pairing unresolved.'),
            method_limits=['Array dimensions are not paired patients or valid-slice denominators.',
                           'Reference UNKNOWN; no label array or Index payload read.']))
    if schema == 'R92_TRUE_SPATIAL_RECEIPT_V1':
        if value['status'] != 'PASS' or value['expert_labels'] != 'UNKNOWN':
            raise ValueError('SPATIAL_RECEIPT_STATUS_OR_REFERENCE_CHANGED')
        cases = []
        for row in value['rows']:
            if evidence == 'REAL_PRECOMPUTED_JSON' and (row['head_reference']['sha256'] != R91_HEAD_SHA or row['model_context']['backbone_sha256'] != R91_ENCODER_SHA):
                raise ValueError('FROZEN_R18_MODEL_BINDING_DRIFT')
            if row['hook']['shape'] != [8,512,7,7] or row['hook']['hook'] != 'avgpool.forward_pre_hook' or row['residual_correction'] is not False:
                raise ValueError('ACTUAL_PRE_GAP_METADATA_REQUIRED')
            assets = row['assets']
            cases.append(dict(source_group=row['source_group_id'], lineage='FROZEN_R18', prediction_scope='BAG',
                bag_logits=row['saved_logits'], target=_target(1), native_indices=row['geometry']['indices_Z'],
                head=_ref(row['head_reference']), geometry=_ref(row['geometry_reference']),
                model_binding='HEAD_AND_ENCODER_DECLARED', candidate_status='NOT_ASSESSED',
                spatial=dict(status='REFERENCES_ONLY_NOT_READ', feature_shape=row['hook']['shape'],
                    signed_class=_ref(assets['signed_class']), signed_margin=_ref(assets['signed_margin']),
                    positive_margin_display=_ref(assets['positive_margin_display']), margin_definition='CLASS1_MINUS_CLASS0',
                    positive_transform='MAX_SIGNED_MARGIN_WITH_ZERO_DISPLAY_ONLY',
                    positive_derived_from_sha256=assets['signed_margin']['sha256'])))
        if value['actual_slice_positions'] != 8*len(cases) or not cases:
            raise ValueError('GROUP_AND_SLICE_POSITION_DENOMINATOR_MISMATCH')
        return validate_metadata(dict(**result, kind='R18_SPATIAL', execution_status='SUCCESS', cases=cases,
            method_limits=['Only receipt declarations; spatial arrays and geometry references unverified here.',
                           'Signed class maps retain both classes; margin = class1-class0; positive clip is display only.',
                           'Slice signed scalars not exported: do not reconstruct them by loading CAM arrays.',
                           'Model fidelity does not establish medical correspondence.']))
    if schema == 'R92_SAME_BAG_COMPARISON_V1':
        a = value['adapter']
        if (value['status'] != 'SUCCESS' or a['K'] != 8 or a['prediction_scope'] != 'BAG'
                or a['fixed_target'] != 0 or a['class_labels'] != CLASSES or a['target_policy'] != 'ORIGINAL_ARGMAX_FIXED'
                or a['cpf'] != 'NOT_CALIBRATED_NOT_APPLIED' or value['expert_reference_status'] != 'UNKNOWN'
                or value['candidate_status'] != 'NO_CALIBRATED_RELIABILITY_RULE' or value['reliable_candidates']):
            raise ValueError('UNCALIBRATED_CONDITIONAL_BAG_PROFILE_REQUIRED')
        expected={f'{m}_{pct}_{action}' for m in ('CAM','E1','E2') for pct in (5,10,20) for action in ('keep','remove')} | {'E2_final_soft_keep'}
        if set(value['responses']) != expected:
            raise ValueError('EXACT_FIXED_AREA_AND_SOFT_RESPONSES_REQUIRED')
        target = a['fixed_target']; responses = []
        for name, row in value['responses'].items():
            if row['fixed_target'] != target:
                raise ValueError('RESPONSE_FIXED_TARGET_DRIFT')
            method, rest = name.split('_', 1)
            if name == 'E2_final_soft_keep': area, action = None, 'soft_keep'
            else:
                pct, action = rest.split('_'); area = int(pct)
                if area not in (5,10,20): raise ValueError('PRELOCKED_AREA_REQUIRED')
            loss = row['all_logits_squared_difference']
            responses.append(dict(name=name, method=method, action=action, area_percent=area,
                logits=row['logits'][0], target_margin=row['target_logit_margin'],
                raw_bag_squared_loss=loss, K2_component_squared_loss=64*loss))
        case = dict(source_group=value['source_group_id'], lineage='FROZEN_R18', prediction_scope='BAG',
            bag_logits=a['original_logits'][0], target=_target(target,a['target_policy']),
            native_indices=value['source_geometry']['indices_Z'], model_binding='NOT_EXPORTED_IN_THIS_JSON',
            spatial=dict(status='INLINE_ARRAYS_NOT_PROJECTED'), candidate_status=value['candidate_status'], responses=responses)
        return validate_metadata(dict(**result, kind='CONDITIONAL_BAG', execution_status='SUCCESS', cases=[case],
            method_limits=[value['limitation'], 'Target Normal_SOURCE explains normal-source prediction, not infectious lesions.',
                           'Conditional member0 with other7 preserved; K²=64 is a unit conversion, not algorithm improvement.',
                           'Empty reliable_candidates means no calibrated rule, never absence of lesions.',
                           'K2 component squared loss is consumer-derived 64 * exported raw BAG squared loss.',
                           'Embedded CAM/mask arrays are excluded from projection; this JSON lacks exact head reference.']))
    if schema == 'R92_FOURGRID_RESULT_V1':
        if value['status'] != 'SUCCESS': raise ValueError('FOURGRID_NOT_SUCCESS')
        target=value['fixed_target'];responses=[]
        for name, row in value['responses'].items():
            if row['fixed_target'] != target:raise ValueError('OLD_FIXED_TARGET_DRIFT')
            responses.append(dict(name=name,method='OLD_FOURGRID',action='mechanism',logits=row['logits'][0],target_margin=row['target_logit_margin']))
        return validate_metadata(dict(**result,kind='OLD_FOURGRID',execution_status='SUCCESS',cases=[dict(
            source_group='GENERATED-OLD-CASE3' if evidence=='GENERATED' else 'OLD-CASE3',lineage='OLD_CASE3_NOT_R18',
            prediction_scope='OLD_SINGLE_SLICE',target=dict(class_id=target, contrast_class=1-target, class_label='NOT_EXPORTED_IN_THIS_JSON', policy='NOT_EXPORTED_IN_THIS_JSON'),model_binding='NOT_EXPORTED_IN_THIS_JSON',
            spatial=dict(status='NOT_AVAILABLE'),candidate_status='NOT_APPLICABLE_OLD_MECHANISM',responses=responses)],
            method_limits=[value['limitation'],'Do not transfer old classifier mechanism to R18 medical localization.']))
    raise ValueError('UNSUPPORTED_METADATA_SCHEMA_NO_IMPLICIT_CONVERSION')


def metadata_summary(artifact):
    return dict(status='METADATA_CONSUMED_NOT_PRODUCT_ACCEPTANCE', schema=SCHEMA, kind=artifact.kind,
        evidence=artifact.evidence, source_groups=len(artifact.cases), source_group_count_semantics='PROJECTED_RECORDS_NOT_MEDICALLY_PAIRED_DENOMINATOR',
        slice_positions=sum(len(c.native_indices) for c in artifact.cases),
        slice_contributions=sum(c.slice_contributions is not None for c in artifact.cases), medical_reference='UNKNOWN',
        referenced_assets_read=0, model_calls=0, medical_pages_opened=0, clinical_validity='NOT_ESTABLISHED')


def join_saved_contributions(spatial, contributions, control, control_ref):
    """Join already validated scalar JSON on exact group/head/geometry/indices.

    Never reads a path. A split/source label is not a medical reference.
    """
    if (spatial.kind != 'R18_SPATIAL' or spatial.evidence != ('GENERATED' if contributions.evidence == 'GENERATED' else 'REAL_PRECOMPUTED_JSON')
            or control.get('schema') != 'R103_R18_FIXED8_DATA_CONTROL_V1'
            or control['status'] != 'EXISTING_JSON_METADATA_ONLY' or control['medical_pairing'] != 'NOT RUN'
            or any(control[k] != 0 for k in ('new_feature_arithmetic','new_model_calls','new_native_weight_array_reads'))
            or _ref(control['source_artifact']) != contributions.contributions_ref):
        raise ValueError('EXACT_CONTROL_AND_SCALAR_SOURCE_BINDING_REQUIRED')
    rows=control['rows'];by_group={r['source_group_id']:r for r in rows}
    old={c.source_group:c for c in contributions.cases}
    if (len(by_group)!=len(rows) or set(by_group)!=set(old)
            or len({r['record_id'] for r in rows})!=len(rows)):
        raise ValueError('EXACT_UNIQUE_CONTROL_SOURCE_GROUP_JOIN_REQUIRED')
    dev=set(control['development_record_ids'])
    if dev!={r['record_id'] for r in rows if r['split']=='val_classification'} or len(dev)!=len(control['development_record_ids']) or {c.source_group for c in spatial.cases}!={r['source_group_id'] for r in rows if r['record_id'] in dev}:
        raise ValueError('EXACT_SPATIAL_DEVELOPMENT_SET_REQUIRED')
    value=spatial.model_dump(mode='json')
    for case in value['cases']:
        r=by_group[case['source_group']];c=old[case['source_group']]
        if (r['split']!='val_classification' or c.split!='DEVELOPMENT_VALIDATION' or r['fixed8_native_indices']!=case['native_indices'] or c.native_slice_indices!=case['native_indices']
                or any(z>=r['native_depth'] for z in r['fixed8_native_indices'])
                or _ref(r['sample_geometry_reference']) != c.geometry or c.geometry != Reference.model_validate(case['geometry'])
                or contributions.model.head != Reference.model_validate(case['head'])
                or c.slice_class_dot_products is None or c.expert_slice_labels!='UNKNOWN'
                or any(not close(a,b) for a,b in zip(c.bag_logits,case['bag_logits']))):
            raise ValueError('SCALAR_HEAD_GEOMETRY_INPUT_OR_LOGIT_JOIN_MISMATCH')
        case['slice_signed_contribution_status']='AVAILABLE_SAVED_GAP_SCALARS'
        case['slice_contributions']=dict(source=contributions.contributions_ref.model_dump(),
            units='UNWEIGHTED_BIAS_FREE_CLASS_DOT_PRODUCTS',class_dot_products=c.slice_class_dot_products,
            effective_bias=contributions.model.effective_bias)
    value['supplemental_sources']=[contributions.contributions_ref.model_dump(),_ref(control_ref).model_dump()]
    value['method_limits']=[m for m in value['method_limits'] if not m.startswith('Slice signed scalars not exported:')]
    value['method_limits'].append('No per-slice input SHA was exported; geometry/index/logit equality is not independent pixel identity verification.')
    value['method_limits'].append('Slice scalars joined from saved GAP JSON; raw/8 is BAG addend, raw+bias is slice component. No CAM arrays read, no medical pairing inferred.')
    return validate_metadata(value)
