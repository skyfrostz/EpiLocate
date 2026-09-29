"""Frontend contract checks independent of frozen model execution."""
from __future__ import annotations

import io

import httpx
import pytest
from PIL import Image

from gradio_service.gradio_debug.api_client import APIError, P0Client
from gradio_service.gradio_debug.real_ct_ui import RealCTController, _source
from gradio_service.gradio_debug.spatial import aligned_overlay


def png(size, value=100):
    stream = io.BytesIO()
    Image.new("L", size, value).save(stream, "PNG")
    return stream.getvalue()


GEOMETRY = {"raw_width": 112, "raw_height": 80, "algorithm_width": 224,
            "algorithm_height": 224, "coordinate_origin": "TOP_LEFT_PIXEL_EDGE",
            "raw_to_algorithm_edge_affine": [2, 0, 0, 0, 2.8, 0, 0, 0, 1]}
LAYER = {"width": 224, "height": 224, "coordinate_space": "ALGORITHM_224",
         "origin": "TOP_LEFT_PIXEL_EDGE"}


def test_overlay_uses_nonuniform_backend_affine_and_rejects_mismatch():
    overlay = aligned_overlay(png((112, 80)), png((224, 224)), GEOMETRY, LAYER)
    assert overlay.size == (224, 224)
    with pytest.raises(ValueError, match="尺寸"):
        aligned_overlay(png((112, 80)), png((80, 112)), GEOMETRY, LAYER)
    with pytest.raises(ValueError, match="不可逆"):
        aligned_overlay(png((112, 80)), png((224, 224)),
                        {**GEOMETRY, "raw_to_algorithm_edge_affine": [0, 0, 0, 0, 0, 0, 0, 0, 1]}, LAYER)


def test_mock_or_wrong_slice_cannot_be_presented_as_real():
    with pytest.raises(APIError, match="来源或切片"):
        _source({"source": "MOCK", "case_id": "CASE-1", "slice_id": "SLICE-1"}, "CASE-1", "SLICE-1")
    with pytest.raises(APIError, match="来源或切片"):
        _source({"source": "LIVE_CASE", "case_id": "CASE-1", "slice_id": "SLICE-2"}, "CASE-1", "SLICE-1")


def test_network_error_has_no_mock_fallback():
    def disconnect(_request):
        raise httpx.ConnectError("offline")

    client = P0Client("http://127.0.0.1:9", transport=httpx.MockTransport(disconnect))
    with pytest.raises(APIError) as error:
        client.capabilities()
    assert error.value.code == "NETWORK_UNAVAILABLE"
    assert "MOCK" not in str(error.value)


class FakeClient:
    def __init__(self, status, result=None):
        self.status = status
        self.payload = result
        self.result_reads = 0

    def job(self, _job_id):
        return {"job_type": "OCCLUSION", "case_id": "CASE-1", "status": self.status,
                "progress": .5, "processed_slices": 0, "total_slices": 1,
                "error_code": "INFERENCE_FAILED", "error_message": "Analysis failed."}

    def result(self, _job_id):
        self.result_reads += 1
        return self.payload


@pytest.mark.parametrize("status", ["PENDING", "RUNNING", "FAILED", "CANCELLED"])
def test_job_states_do_not_fetch_unfinished_result(status):
    client = FakeClient(status)
    message, result = RealCTController(client).inspect_job("job-1", "CASE-1", "SLICE-1")
    assert status in message and result is None and client.result_reads == 0


def test_completed_job_reads_matching_real_result():
    client = FakeClient("COMPLETED", {"source": "LIVE_CASE", "case_id": "CASE-1", "slice_id": "SLICE-1",
                                      "prediction": {"source": "LIVE_CASE", "unit": "slice", "slice_id": "SLICE-1"}})
    message, result = RealCTController(client).inspect_job("job-1", "CASE-1", "SLICE-1")
    assert "COMPLETED" in message and result["source"] == "LIVE_CASE" and client.result_reads == 1


def test_failed_http_response_surfaces_code_without_fallback():
    def failure(_request):
        return httpx.Response(503, json={"code": "MODEL_UNAVAILABLE", "message": "Frozen baseline unavailable."})

    client = P0Client("http://127.0.0.1:9", transport=httpx.MockTransport(failure))
    with pytest.raises(APIError) as error:
        client.capabilities()
    assert error.value.code == "MODEL_UNAVAILABLE"


def test_invalid_candidate_response_has_no_candidate_image():
    class Assets:
        def slices(self, _case_id):
            return {"slices": [{"slice_id": "SLICE-1", "geometry": GEOMETRY}]}

        def preview(self, _slice_id):
            return png((112, 80))

        def asset(self, _result_id, asset_id):
            assert asset_id == "response.png"
            return png((224, 224))

        def positions(self, _result_id, _scale, _cursor):
            return {"positions": [], "next_cursor": None}

    result = {"source": "LIVE_CASE", "case_id": "CASE-1", "slice_id": "SLICE-1",
              "result_id": "RESULT-1", "prediction": {"source": "LIVE_CASE", "unit": "slice", "slice_id": "SLICE-1"},
              "scale_summaries": [{"block_size": 16, "stride": 8,
                                   "baseline_positive_probability": .3,
                                   "median_absolute_probability_change": 0,
                                   "flip_rate": 0, "candidate_status": "insufficient_positive_response",
                                   "candidate_area_fraction": None,
                                   "response_layer": {**LAYER, "asset_id": "response.png", "value_min": 0, "value_max": 1},
                                   "candidate_layer": None}]}
    response, overlay, candidate, note = RealCTController(Assets()).scale_view(result, "CASE-1", "SLICE-1", 16)
    assert response.size == overlay.size == (224, 224)
    assert candidate is None and "insufficient_positive_response" in note


def test_optional_server_bearer_token_is_sent_only_as_header(monkeypatch):
    seen = []

    def capture(request):
        seen.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"capabilities": {}})

    monkeypatch.delenv("EPILOCATE_API_BEARER_TOKEN", raising=False)
    transport = httpx.MockTransport(capture)
    P0Client("http://127.0.0.1:9", transport=transport).capabilities()
    monkeypatch.setenv("EPILOCATE_API_BEARER_TOKEN", "server-only-secret")
    client = P0Client("http://127.0.0.1:9", transport=transport)
    client.capabilities()
    assert seen == [None, "Bearer server-only-secret"]


def test_401_and_403_are_sanitized_without_token_echo():
    for status, expected in [(401, "AUTH_REQUIRED"), (403, "ACCESS_DENIED")]:
        transport = httpx.MockTransport(lambda _request: httpx.Response(
            status, json={"code": "DENIED", "message": "secret should not be shown"}))
        client = P0Client("http://127.0.0.1:9", transport=transport, token="server-only-secret")
        with pytest.raises(APIError) as error:
            client.capabilities()
        assert error.value.code == expected
        assert "secret" not in str(error.value)
