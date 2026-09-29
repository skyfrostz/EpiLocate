"""Versioned future integration types. These are contracts, not active features."""

from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class CapabilityState(str, Enum):
    available = "AVAILABLE"
    not_connected = "NOT_CONNECTED"


class CapabilityReport(BaseModel):
    api_version: Literal["v1"] = "v1"
    site_mode: Literal["PROJECT_PRESENTATION"] = "PROJECT_PRESENTATION"
    capabilities: dict[str, CapabilityState]
    accepts_real_images: Literal[False] = False
    stores_business_payloads: Literal[False] = False
    csrf_token: str


class AnalysisStage(str, Enum):
    preprocessing = "PREPROCESSING"
    classification_occlusion = "CLASSIFICATION_OCCLUSION"
    coarse_localization = "COARSE_LOCALIZATION"
    lime_refinement = "LIME_REFINEMENT"
    clinical_review = "CLINICAL_REVIEW"


class AnalysisStatus(str, Enum):
    queued = "QUEUED"
    running = "RUNNING"
    completed = "COMPLETED"
    failed = "FAILED"
    not_connected = "NOT_CONNECTED"


class ImageMetadata(BaseModel):
    image_id: str = Field(description="Future pseudonymous image identifier; no patient identifiers")
    modality: Literal["CT", "XRAY", "OTHER"]
    format: Literal["DICOM", "NIFTI", "PNG", "JPEG"]
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    slices: int | None = Field(default=None, ge=1)
    deidentified: bool = Field(description="Must be true before any future integration")


class ImageSubmission(BaseModel):
    metadata: ImageMetadata


class AnalysisTaskCreate(BaseModel):
    image_id: str
    requested_stages: list[AnalysisStage] = Field(default_factory=lambda: list(AnalysisStage))


class AnalysisTask(BaseModel):
    task_id: str
    image_id: str
    stage: AnalysisStage
    status: AnalysisStatus
    created_at: str = Field(description="ISO 8601 UTC")
    updated_at: str = Field(description="ISO 8601 UTC")


class Point(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class LocalizationRegion(BaseModel):
    region_id: str
    stage: Literal["COARSE_LOCALIZATION", "LIME_REFINEMENT"]
    geometry: Literal["POLYGON", "BOX"]
    points: list[Point] = Field(description="Normalized image coordinates")
    slice_index: int | None = Field(default=None, ge=0)
    stability_score: float | None = Field(default=None, ge=0, le=1)


class Explanation(BaseModel):
    method: Literal["BLOCK_MASK", "LIME", "GRAD_CAM_PLUS_PLUS"]
    summary: str
    region_ids: list[str]
    contribution: float | None = Field(default=None, description="Method-specific signed contribution")
    comparison_only: bool = Field(default=False, description="True for baseline or degraded route")


class AnalysisResult(BaseModel):
    result_id: str
    task_id: str
    status: AnalysisStatus
    regions: list[LocalizationRegion]
    explanations: list[Explanation]
    model_version: str | None = None


class DoctorCorrection(BaseModel):
    region_id: str | None = None
    action: Literal["CONFIRM", "ADD", "REMOVE", "ADJUST"]
    corrected_region: LocalizationRegion | None = None
    note: str | None = Field(default=None, max_length=2000)


class DoctorFeedback(BaseModel):
    result_id: str
    corrections: list[DoctorCorrection]
    clinical_alignment_score: int | None = Field(default=None, ge=1, le=5)


class NotConnectedError(BaseModel):
    code: Literal["NOT_CONNECTED"] = "NOT_CONNECTED"
    status: Literal["NOT_CONNECTED"] = "NOT_CONNECTED"
    message: str = "该能力尚未接入；当前不接收或保存影像及业务数据。"
    capability: str
