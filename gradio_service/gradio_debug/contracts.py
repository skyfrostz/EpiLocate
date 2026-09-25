from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CaseInput(StrictModel):
    case_id: str
    input_kind: Literal["image", "dicom_series", "dicom_zip", "nifti"]
    files: list[str]


class InferenceOptions(StrictModel):
    requested_modules: list[str] = Field(default_factory=list)


class ErrorInfo(StrictModel):
    code: str
    message: str
    stage: str
    retryable: bool = False


class PredictionResult(StrictModel):
    available: bool = False
    predicted_class: str | None = Field(default=None, alias="class")
    probability: float | None = Field(default=None, ge=0, le=1)
    probabilities: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_availability(self) -> "PredictionResult":
        if self.available:
            if self.predicted_class is None or self.probability is None or not self.probabilities:
                raise ValueError("available prediction requires class, probability, and probabilities")
            if self.predicted_class not in self.probabilities:
                raise ValueError("predicted class must be present in probabilities")
            if any(value < 0 or value > 1 for value in self.probabilities.values()):
                raise ValueError("all probabilities must be between 0 and 1")
            if abs(sum(self.probabilities.values()) - 1.0) > 0.001:
                raise ValueError("probabilities must sum to 1")
        elif self.predicted_class is not None or self.probability is not None or self.probabilities:
            raise ValueError("unavailable prediction must not contain values")
        return self


class OcclusionStage(StrictModel):
    level: int = Field(ge=1)
    image_path: str | None = None
    score: float | None = None


class OcclusionResult(StrictModel):
    available: bool = False
    stability_score: float | None = Field(default=None, ge=0, le=1)
    stages: list[OcclusionStage] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_availability(self) -> "OcclusionResult":
        if not self.available and (self.stability_score is not None or self.stages):
            raise ValueError("unavailable occlusion result must not contain values")
        return self


class LocalizationResult(StrictModel):
    available: bool = False
    mask_path: str | None = None
    overlay_path: str | None = None

    @model_validator(mode="after")
    def validate_availability(self) -> "LocalizationResult":
        if not self.available and (self.mask_path is not None or self.overlay_path is not None):
            raise ValueError("unavailable localization must not contain artifacts")
        return self


class LimeResult(LocalizationResult):
    explanation: str | None = None

    @model_validator(mode="after")
    def validate_explanation(self) -> "LimeResult":
        if not self.available and self.explanation is not None:
            raise ValueError("unavailable LIME result must not contain an explanation")
        return self


class InferenceResult(StrictModel):
    contract_version: Literal["0.1"] = "0.1"
    pipeline_version: str
    model_version: str
    case_id: str
    status: Literal["success", "failed"]
    mode: Literal["mock", "real"]
    source: Literal["MOCK", "LIVE_CASE"] = "MOCK"
    prediction: PredictionResult = Field(default_factory=PredictionResult)
    occlusion: OcclusionResult = Field(default_factory=OcclusionResult)
    coarse_localization: LocalizationResult = Field(default_factory=LocalizationResult)
    lime: LimeResult = Field(default_factory=LimeResult)
    runtime_ms: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    error: ErrorInfo | None = None

    @model_validator(mode="after")
    def validate_status(self) -> "InferenceResult":
        if self.status == "success" and self.error is not None:
            raise ValueError("successful result cannot contain an error")
        if self.status == "failed" and self.error is None:
            raise ValueError("failed result requires an error")
        return self


class JobStatus(StrictModel):
    job_id: str
    case_id: str
    status: Literal["queued", "running", "success", "failed"]
    stage: str
    progress: int = Field(ge=0, le=100)
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None
