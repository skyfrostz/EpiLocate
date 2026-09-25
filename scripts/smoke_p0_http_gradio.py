#!/usr/bin/env python3
"""Exercise live HTTP and Gradio P0 using only the bundled synthetic CT DICOM."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
import uuid
from pathlib import Path

import httpx
from gradio_client import Client, handle_file
from PIL import Image

FIXTURE = Path(__file__).resolve().parents[1] / "docs/interfaces/fixtures/p0_synthetic_ct.dcm"


def wait(client, base, job_id):
    for _ in range(300):
        status = client.get(f"{base}/api/v1/jobs/{job_id}").json()
        if status["status"] == "COMPLETED":
            result = client.get(f"{base}/api/v1/jobs/{job_id}/result")
            result.raise_for_status()
            return result.json()
        if status["status"] == "FAILED":
            raise RuntimeError("Live job failed")
        time.sleep(.2)
    raise TimeoutError("Live job timed out")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8877")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = args.url.rstrip("/")
    with httpx.Client(timeout=60) as client:
        health = client.get(f"{base}/api/health").json()
        capabilities = client.get(f"{base}/api/v1/capabilities").json()
        assert health["real_ready"] is True
        assert capabilities["capabilities"]["single_slice_occlusion"]["state"] == "available"
        with FIXTURE.open("rb") as stream:
            uploaded = client.post(f"{base}/api/v1/cases", headers={"Idempotency-Key": uuid.uuid4().hex},
                                   data={"input_kind": "dicom_series"},
                                   files={"files": ("synthetic.dcm", stream, "application/dicom")})
        uploaded.raise_for_status()
        case_id = uploaded.json()["case_id"]
        slice_record = client.get(f"{base}/api/v1/cases/{case_id}/slices").json()["slices"][0]
        slice_id = slice_record["slice_id"]
        geometry = slice_record["geometry"]
        assert geometry["raw_to_algorithm_edge_affine"] == [2, 0, 0, 0, 2.8, 0, 0, 0, 1]
        preview = client.get(f"{base}/api/v1/slices/{slice_id}/preview")
        assert preview.status_code == 200 and Image.open(io.BytesIO(preview.content)).size == (112, 80)
        pred = client.post(f"{base}/api/v1/predictions", headers={"Idempotency-Key": uuid.uuid4().hex},
                           json={"case_id": case_id, "slice_id": slice_id, "unit": "slice", "model_id": "baseline_resnet18"})
        pred.raise_for_status()
        prediction = wait(client, base, pred.json()["job_id"])["prediction"]
        occ = client.post(f"{base}/api/v1/jobs/occlusion", headers={"Idempotency-Key": uuid.uuid4().hex},
                          json={"case_id": case_id, "slice_id": slice_id, "model_id": "baseline_resnet18",
                                "scales": [16, 32, 64], "protocol_id": "stage1-occlusion-instability-v1"})
        occ.raise_for_status()
        result = wait(client, base, occ.json()["job_id"])
        counts = {}
        for size in (16, 32, 64):
            page = client.get(f"{base}/api/v1/occlusion-results/{result['result_id']}/positions",
                              params={"scale": size, "limit": 1000})
            page.raise_for_status()
            counts[str(size)] = len(page.json()["positions"])
        assert counts == {"16": 729, "32": 169, "64": 36}
        asset = client.get(f"{base}/api/v1/assets/response-16.png", params={"result_id": result["result_id"]})
        assert asset.status_code == 200 and Image.open(io.BytesIO(asset.content)).size == (224, 224)
    gradio_result = Client(f"{base}/gradio").predict(handle_file(str(FIXTURE)), True, api_name="/run_dicom")
    assert gradio_result[2] == "LIVE_CASE"
    assert [item["block_size"] for item in gradio_result[1]["scale_summaries"]] == [16, 32, 64]
    difference = abs(prediction["positive_probability"] - gradio_result[1]["prediction"]["positive_probability"])
    assert difference < 1e-6
    report = {"status": "PASS", "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
              "http_health": health, "http_source": result["source"], "gradio_source": gradio_result[2],
              "positive_probability": prediction["positive_probability"],
              "http_gradio_probability_absolute_error": difference,
              "mask_positions": counts, "preview_size": [112, 80], "response_asset_size": [224, 224],
              "test_pixels_read": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
