from __future__ import annotations

import hashlib
import importlib
import os
import time
from pathlib import Path
from typing import Callable

from .contracts import (
    CaseInput,
    ErrorInfo,
    InferenceOptions,
    InferenceResult,
    PredictionResult,
)
from .storage import Storage


MOCK_WARNING = "MOCK RESULT: interface-development data only; not for research metrics or clinical decisions."


class RealPipelineUnavailable(RuntimeError):
    pass


class InferenceAdapter:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        mode = os.getenv("APP_MODE", "mock").strip().lower()
        if mode not in {"mock", "real"}:
            raise ValueError("APP_MODE must be 'mock' or 'real'")
        self.mode = mode
        self.module_name = os.getenv("REAL_PIPELINE_MODULE", "algorithm.inference_pipeline")
        self.callable_name = os.getenv("REAL_PIPELINE_CALLABLE", "run_case")
        self._real_callable: Callable[..., object] | None = None
        self._real_error: str | None = None

    @property
    def real_ready(self) -> bool:
        try:
            self._load_real()
            return True
        except RealPipelineUnavailable:
            return False

    @property
    def real_error(self) -> str | None:
        if self._real_error is None and self.mode == "real":
            self.real_ready
        return self._real_error

    def _load_real(self) -> Callable[..., object]:
        if self._real_callable is not None:
            return self._real_callable
        try:
            module = importlib.import_module(self.module_name)
            candidate = getattr(module, self.callable_name)
            if not callable(candidate):
                raise TypeError(f"{self.callable_name} is not callable")
            self._real_callable = candidate
            return candidate
        except Exception as exc:
            self._real_error = f"{type(exc).__name__}: {exc}"
            raise RealPipelineUnavailable("Real inference pipeline is not available.") from exc

    def run_case(self, case_input: CaseInput, options: InferenceOptions | None = None) -> InferenceResult:
        options = options or InferenceOptions()
        if self.mode == "real":
            raw = self._load_real()(case_input, options)
            result = InferenceResult.model_validate(raw)
            if result.case_id != case_input.case_id or result.mode != "real":
                raise ValueError("real pipeline result does not match the requested case or mode")
            return result
        return self._run_mock(case_input)

    def _run_mock(self, case_input: CaseInput) -> InferenceResult:
        started = time.perf_counter()
        if case_input.input_kind != "image" or len(case_input.files) != 1:
            raise ValueError("P0 mock inference accepts exactly one image")
        image_path = self.storage.absolute_input_path(case_input.files[0])
        digest = hashlib.sha256(Path(image_path).read_bytes()).digest()
        positive_probability = round(0.60 + (digest[1] / 255) * 0.35, 4)
        probabilities = {
            "negative": round(1 - positive_probability, 4),
            "positive": positive_probability,
        }
        predicted_class = "positive" if positive_probability >= 0.5 else "negative"
        return InferenceResult(
            pipeline_version="mock-pipeline-v0.1",
            model_version="mock-v0",
            case_id=case_input.case_id,
            status="success",
            mode="mock",
            prediction=PredictionResult(
                available=True,
                predicted_class=predicted_class,
                probability=probabilities[predicted_class],
                probabilities=probabilities,
            ),
            runtime_ms=max(0, int((time.perf_counter() - started) * 1000)),
            warnings=[MOCK_WARNING],
        )

    def failed_result(self, case_id: str, code: str, message: str, stage: str) -> InferenceResult:
        return InferenceResult(
            pipeline_version="unavailable" if self.mode == "real" else "mock-pipeline-v0.1",
            model_version="unavailable" if self.mode == "real" else "mock-v0",
            case_id=case_id,
            status="failed",
            mode=self.mode,
            runtime_ms=0,
            warnings=[MOCK_WARNING] if self.mode == "mock" else [],
            error=ErrorInfo(code=code, message=message, stage=stage, retryable=False),
        )
