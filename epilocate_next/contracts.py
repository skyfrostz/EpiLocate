"""Application-only contracts shared with LOC/ENC; no model or DICOM imports."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Hash = str
Terminal = Literal['SUCCESS', 'NO_RELIABLE_RESPONSE', 'PARTIAL_BUDGET', 'FAILED', 'BLOCKED', 'NOT RUN']

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Budget(Strict):
    forward: int = Field(ge=0)
    backward: int = Field(ge=0)
    updates: int = Field(ge=0)
    seconds: float = Field(gt=0)
    output_bytes: int = Field(gt=0, le=64*1024*1024)

class Input(Strict):
    case_id: str = Field(min_length=1)
    study_id: str = Field(min_length=1)
    series_id: str = Field(min_length=1)
    slice_id: str = Field(min_length=1)
    input_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    display_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    scope: Literal['SINGLE_SLICE', 'VOLUME']
    display_kind: Literal['DICOM', 'RESEARCH_ARRAY']
    source_identity_status: Literal['DICOM_CONFORMANT', 'DICOM_ID_NONCONFORMANT', 'SYNTHETIC']
    native_shape_zyx: tuple[int, int, int]
    model_shape: tuple[int, ...]
    native_slice_index: int = Field(ge=0)
    affine_lps: list[list[float]]
    coordinate_convention: Literal['array_zyx_to_LPS_mm'] = 'array_zyx_to_LPS_mm'
    geometry_ledger_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    mapping_qa_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    mapping_verified: bool
    @model_validator(mode='after')
    def geometry(self):
        if any(v<=0 for v in self.native_shape_zyx+self.model_shape) or self.native_slice_index>=self.native_shape_zyx[0]:
            raise ValueError('INVALID_INPUT_SHAPE')
        a=self.affine_lps
        if len(a)!=4 or any(len(row)!=4 for row in a) or a[3]!=[0,0,0,1]:raise ValueError('INVALID_LPS_AFFINE')
        det=a[0][0]*(a[1][1]*a[2][2]-a[1][2]*a[2][1])-a[0][1]*(a[1][0]*a[2][2]-a[1][2]*a[2][0])+a[0][2]*(a[1][0]*a[2][1]-a[1][1]*a[2][0])
        if abs(det)<1e-12:raise ValueError('SINGULAR_LPS_AFFINE')
        if self.source_identity_status=='DICOM_ID_NONCONFORMANT' and self.display_kind!='RESEARCH_ARRAY':
            raise ValueError('NONCONFORMANT_SOURCE_REQUIRES_RESEARCH_ARRAY')
        return self

class Model(Strict):
    model_id: str = Field(min_length=1)
    checkpoint_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    encoder_sha256: str | None = Field(default=None, pattern='^[a-f0-9]{64}$')
    head_sha256: str | None = Field(default=None, pattern='^[a-f0-9]{64}$')
    preprocessing_version: str = Field(min_length=1)
    preprocessing_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    protocol_id: str = Field(min_length=1)

class Task(Strict):
    definition_id: str = Field(min_length=1)
    unit: Literal['SLICE', 'SOURCE_CASE_SELECTED_SERIES']
    class_labels: list[str] = Field(min_length=2)
    target_class: int = Field(ge=0)

class ApplicationRequest(Strict):
    schema_version: Literal['EPI_NEXT_APPLICATION_REQUEST_V1']
    algorithm_mode: Literal['E2', 'CTFM']
    method_mode: Literal['E2-CT', 'CTFM-VOLUME-HEAD']
    algorithm_version: str = Field(min_length=1)
    config_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    execution_mode: Literal['LIVE', 'PRECOMPUTED', 'SYNTHETIC']
    input: Input
    model: Model
    task: Task
    budget: Budget
    @model_validator(mode='after')
    def semantics(self):
        if self.task.target_class>=len(self.task.class_labels) or len(set(self.task.class_labels))!=len(self.task.class_labels):raise ValueError('INVALID_CLASS_LABELS')
        if self.algorithm_mode=='E2':
            if (self.method_mode!='E2-CT' or self.input.scope!='SINGLE_SLICE' or len(self.input.model_shape)!=2
                    or self.task.unit!='SLICE' or self.input.input_sha256!=self.input.display_sha256):raise ValueError('E2_REQUIRES_EXPLICIT_2D_FUNCTION')
        elif (self.method_mode!='CTFM-VOLUME-HEAD' or self.input.scope!='VOLUME' or self.input.model_shape!=(1,1,64,64,64)
                or self.task.unit!='SOURCE_CASE_SELECTED_SERIES' or not self.model.encoder_sha256 or not self.model.head_sha256):
            raise ValueError('CTFM_REQUIRES_COMPLETE_SERIES64_AND_HEAD')
        return self

class Prediction(Strict):
    logits: list[float] = Field(min_length=2)
    predicted_class: int = Field(ge=0)
    class_label: str
    probabilities: list[float] | None = None

class Layer(Strict):
    asset_id: str = Field(pattern='^[A-Za-z0-9_-]+\\.png$')
    layer_kind: Literal['OPTIMIZED_INPUT_MASK', 'SIGNED_FEATURE_CONTRIBUTION', 'HSPI_CPF_GAP', 'HSPI_CPF_PSMI_PATCH_SUPPORT', 'HSPI_PSMI_WHOLE_PATCH_SUPPORT', 'BASE_IMAGE']
    evidence_type: Literal['OPTIMIZED_INPUT_MASK', 'SIGNED_FEATURE_CONTRIBUTION', 'HSPI_CPF_GAP', 'HSPI_CPF_PSMI_PATCH_SUPPORT', 'HSPI_PSMI_WHOLE_PATCH_SUPPORT', 'SOURCE_ARRAY_PREVIEW']
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    coordinate_space: Literal['RAW_PIXEL_EDGE']
    origin: Literal['TOP_LEFT_PIXEL_EDGE']
    x_axis: Literal['RIGHT']
    y_axis: Literal['DOWN']
    display_interpolation_only: Literal[True]
    value_min: float
    value_max: float
    # Exact native-grid numeric evidence; not PNG intensities/probabilities.
    raw_values: list[list[float]] | None = None
    display_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    geometry_ledger_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    mapping_qa_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    native_slice_index: int = Field(ge=0)

class Candidate(Strict):
    response: float
    evidence_type: Literal['HSPI_CPF_PSMI_PATCH_SUPPORT', 'SIGNED_FEATURE_CONTRIBUTION']
    bbox_lps_mm: tuple[tuple[float,float,float],tuple[float,float,float]]
    stage: int = Field(ge=1)

class StopEvent(Strict):
    kind: Literal['TIME_BUDGET', 'FORWARD_BUDGET', 'BACKWARD_BUDGET', 'UPDATE_BUDGET']
    elapsed_seconds: float = Field(ge=0)
    deadline_elapsed_seconds: float = Field(ge=0)
    new_work_after_stop: Literal[False]

class HandlerResult(Strict):
    execution_status: Terminal
    algorithm_status: str = Field(min_length=1)
    reason: str | None
    prediction: Prediction | None
    candidates: list[Candidate]
    layers: list[Layer]
    actual_forward: int = Field(ge=0)
    actual_backward: int = Field(ge=0)
    actual_updates: int = Field(ge=0)
    runtime_seconds: float = Field(ge=0)
    stop_events: list[StopEvent] = Field(default_factory=list)
    source_artifacts: dict[str,str]  # named SHA references; private paths stay in local runner receipt
    diagnostics: dict


def validate_output(request: ApplicationRequest, result: HandlerResult):
    b=request.budget
    if (result.actual_forward>b.forward or result.actual_backward>b.backward or result.actual_updates>b.updates):raise ValueError('ALGORITHM_BUDGET_EXCEEDED')
    if result.execution_status=='NOT RUN' and (result.actual_forward or result.actual_backward or result.actual_updates or result.prediction or result.layers):raise ValueError('NOT_RUN_HAS_NO_COMPUTE_OR_OUTPUT')
    if result.runtime_seconds>b.seconds:
        if result.execution_status not in {'PARTIAL_BUDGET','FAILED'} or not any(e.kind=='TIME_BUDGET' and e.deadline_elapsed_seconds<=b.seconds and e.elapsed_seconds>=e.deadline_elapsed_seconds for e in result.stop_events):
            raise ValueError('OVERTIME_REQUIRES_PRESERVED_STOP_EVENT')
    if result.execution_status!='SUCCESS' and result.candidates:raise ValueError('ABSTENTION_CANNOT_FABRICATE_CANDIDATES')
    if result.execution_status in {'FAILED','BLOCKED','PARTIAL_BUDGET','NO_RELIABLE_RESPONSE','NOT RUN'} and not result.reason:raise ValueError('TERMINAL_REASON_REQUIRED')
    if result.prediction:
        p=result.prediction
        if len(p.logits)!=len(request.task.class_labels) or p.predicted_class>=len(p.logits) or p.class_label!=request.task.class_labels[p.predicted_class] or p.logits[p.predicted_class]!=max(p.logits):raise ValueError('PREDICTION_TASK_MISMATCH')
        if p.probabilities is not None and (len(p.probabilities)!=len(p.logits) or any(v<0 or v>1 for v in p.probabilities) or abs(sum(p.probabilities)-1)>1e-5):raise ValueError('INVALID_PROBABILITIES')
    expected={'OPTIMIZED_INPUT_MASK','HSPI_CPF_GAP','HSPI_CPF_PSMI_PATCH_SUPPORT','HSPI_PSMI_WHOLE_PATCH_SUPPORT'} if request.algorithm_mode=='E2' else {'SIGNED_FEATURE_CONTRIBUTION'}
    if request.algorithm_mode=='CTFM' and result.prediction is not None:
        if not {'spatial_features','gap512','head'}.issubset(result.source_artifacts) or result.diagnostics.get('spatial_features_shape') != [1,512,4,4,4] or result.diagnostics.get('gap_shape') != [1,512]:
            raise ValueError('CTFM_FEATURE_HEAD_PROVENANCE_REQUIRED')
        if result.source_artifacts['head']!=request.model.head_sha256:raise ValueError('CTFM_HEAD_BINDING_MISMATCH')
    for value in result.source_artifacts.values():
        import re
        if not re.fullmatch('[a-f0-9]{64}',value):raise ValueError('SOURCE_ARTIFACT_SHA_REQUIRED')
    i=request.input
    names=set()
    for layer in result.layers:
        if layer.asset_id in names:raise ValueError('DUPLICATE_LAYER')
        names.add(layer.asset_id)
        if (layer.layer_kind!='BASE_IMAGE' and (layer.layer_kind not in expected or layer.evidence_type!=layer.layer_kind)
                or layer.layer_kind=='BASE_IMAGE' and layer.evidence_type!='SOURCE_ARRAY_PREVIEW'):raise ValueError('EVIDENCE_TYPE_MISMATCH')
        if layer.value_min>layer.value_max:raise ValueError('INVALID_LAYER_RANGE')
        if (layer.width,layer.height)!=(i.native_shape_zyx[2],i.native_shape_zyx[1]) or layer.native_slice_index!=i.native_slice_index or layer.display_sha256!=i.display_sha256 or layer.geometry_ledger_sha256!=i.geometry_ledger_sha256 or layer.mapping_qa_sha256!=i.mapping_qa_sha256:raise ValueError('NATIVE_LAYER_BINDING_MISMATCH')
        if layer.layer_kind=='SIGNED_FEATURE_CONTRIBUTION':
            if layer.raw_values is None:raise ValueError('SIGNED_VALUES_REQUIRED')
        if layer.raw_values is not None and (len(layer.raw_values)!=layer.height or any(len(row)!=layer.width for row in layer.raw_values)):raise ValueError('INVALID_RAW_GRID')
    if any(c.evidence_type!=('HSPI_CPF_PSMI_PATCH_SUPPORT' if request.algorithm_mode=='E2' else 'SIGNED_FEATURE_CONTRIBUTION') or any(a>=b for a,b in zip(*c.bbox_lps_mm)) for c in result.candidates):raise ValueError('INVALID_CANDIDATE_COORDINATES')
    return result
