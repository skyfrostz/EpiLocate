import pytest
from pydantic import ValidationError

from gradio_debug.contracts import InferenceResult, PredictionResult


def test_prediction_contract_and_alias():
    prediction = PredictionResult(
        available=True,
        predicted_class="positive",
        probability=0.8,
        probabilities={"negative": 0.2, "positive": 0.8},
    )
    result = InferenceResult(
        pipeline_version="test",
        model_version="test",
        case_id="CASE-1",
        status="success",
        mode="mock",
        prediction=prediction,
        runtime_ms=1,
    )
    assert result.model_dump(by_alias=True)["prediction"]["class"] == "positive"


def test_invalid_probability_sum_is_rejected():
    with pytest.raises(ValidationError):
        PredictionResult(
            available=True,
            predicted_class="positive",
            probability=0.7,
            probabilities={"negative": 0.7, "positive": 0.7},
        )


def test_unavailable_prediction_cannot_contain_values():
    with pytest.raises(ValidationError):
        PredictionResult(available=False, predicted_class="positive")
