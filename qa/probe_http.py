"""Independent P0 HTTP probe against a fixed, loopback-only service.

Uses only the committed synthetic DICOM. Never opens formal test pixels.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import numpy as np
import pydicom
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "docs/interfaces/fixtures/p0_synthetic_ct.dcm"
VECTOR = json.loads((ROOT / "docs/interfaces/fixtures/p0_http_vector.json").read_text())


def wait(client: httpx.Client, job_id: str) -> dict:
    history = []
    for _ in range(300):
        response = client.get(f"/api/v1/jobs/{job_id}")
        response.raise_for_status()
        job = response.json()
        history.append(job["status"])
        if job["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
            return {"job": job, "history": list(dict.fromkeys(history))}
        time.sleep(0.2)
    raise TimeoutError("job did not reach a terminal state within 60 seconds")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = FIXTURE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == VECTOR["dicom_sha256"]
    token = os.getenv("EPILOCATE_API_BEARER_TOKEN")
    current_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    evidence: dict = {"tested_worktree_head": current_head,
                      "token_mode": bool(token),
                      "fixture_sha256": VECTOR["dicom_sha256"], "checks": {}}

    def record(name: str, observed, expected) -> None:
        evidence["checks"][name] = {"observed": observed, "expected": expected,
                                     "status": "PASS" if observed == expected else "FAIL"}

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with httpx.Client(base_url=args.url, timeout=60, trust_env=False, headers=headers) as client:
        health = client.get("/api/health").json()
        record("real_health", [health["mode"], health["real_ready"]], ["real", True])
        capabilities = client.get("/api/v1/capabilities").json()["capabilities"]
        record("real_capabilities", [capabilities["baseline_slice_prediction"]["state"],
                                      capabilities["single_slice_occlusion"]["state"]],
               ["available", "available"])
        record("planned_capabilities", [capabilities[name]["state"] for name in
                                        ("nifti", "robust", "coarse_localization", "lime", "doctor_feedback")],
               ["planned"] * 5)
        files = {"files": ("synthetic.dcm", data, "application/dicom")}
        key = uuid.uuid4().hex
        upload = client.post("/api/v1/cases", headers={"Idempotency-Key": key},
                             data={"input_kind": "dicom_series"}, files=files)
        record("upload_http", upload.status_code, 202)
        accepted = upload.json()
        case_id = accepted["case_id"]
        duplicate = client.post("/api/v1/cases", headers={"Idempotency-Key": key},
                                data={"input_kind": "dicom_series"}, files=files)
        record("upload_idempotency", duplicate.json() == accepted, True)
        parsed = wait(client, accepted["job_id"])
        record("case_parse_job", parsed["job"]["status"], "COMPLETED")
        case = client.get(f"/api/v1/cases/{case_id}").json()
        record("case_source", case["source"], "LIVE_CASE")
        slices = client.get(f"/api/v1/cases/{case_id}/slices").json()["slices"]
        record("single_slice", len(slices), 1)
        slice_id = slices[0]["slice_id"]
        geometry = slices[0]["geometry"]
        record("geometry", {key: geometry[key] for key in VECTOR["expected"]["geometry"]},
               VECTOR["expected"]["geometry"])
        preview = client.get(f"/api/v1/slices/{slice_id}/preview")
        record("preview_size", list(Image.open(io.BytesIO(preview.content)).size), [112, 80])

        pred_body = {"case_id": case_id, "slice_id": slice_id, "unit": "slice",
                     "model_id": "baseline_resnet18"}
        pred_key = uuid.uuid4().hex
        prediction_job = client.post("/api/v1/predictions", json=pred_body,
                                     headers={"Idempotency-Key": pred_key})
        record("prediction_submit", prediction_job.status_code, 202)
        pred_accept = prediction_job.json()
        record("prediction_idempotency",
               client.post("/api/v1/predictions", json=pred_body,
                           headers={"Idempotency-Key": pred_key}).json() == pred_accept, True)
        conflict = client.post("/api/v1/predictions", json={**pred_body, "slice_id": "OTHER"},
                               headers={"Idempotency-Key": pred_key})
        record("idempotency_conflict", [conflict.status_code, conflict.json().get("code")],
               [409, "IDEMPOTENCY_CONFLICT"])
        pred_state = wait(client, pred_accept["job_id"])
        record("prediction_job", pred_state["job"]["status"], "COMPLETED")
        pred_result = client.get(f"/api/v1/jobs/{pred_accept['job_id']}/result").json()
        probability = pred_result["prediction"]["positive_probability"]
        record("prediction_source_unit", [pred_result["source"], pred_result["prediction"]["unit"],
                                                pred_result["prediction"]["source"]],
               ["LIVE_CASE", "slice", "LIVE_CASE"])
        record("golden_probability_within_declared_tolerance",
               abs(probability - VECTOR["expected"]["positive_probability"]) <=
               VECTOR["expected"]["probability_absolute_tolerance"], True)
        record("model_identity", pred_result["model_version"], VECTOR["expected"]["model_version"])

        occ_body = {"case_id": case_id, "slice_id": slice_id, "model_id": "baseline_resnet18",
                    "scales": [16, 32, 64], "protocol_id": "stage1-occlusion-instability-v1"}
        occ = client.post("/api/v1/jobs/occlusion", json=occ_body,
                          headers={"Idempotency-Key": uuid.uuid4().hex})
        record("occlusion_submit", occ.status_code, 202)
        occ_state = wait(client, occ.json()["job_id"])
        record("occlusion_job", occ_state["job"]["status"], "COMPLETED")
        result = client.get(f"/api/v1/jobs/{occ.json()['job_id']}/result").json()
        record("occlusion_source_slice", [result["source"], result["slice_id"]], ["LIVE_CASE", slice_id])
        record("future_modules", [result["coarse_localization"]["status"], result["lime"]["status"]],
               ["NOT_IMPLEMENTED", "NOT_IMPLEMENTED"])
        count_map = {}
        formula_ok = True
        heatmap_ok = True
        grid_ok = True
        for summary in result["scale_summaries"]:
            size = summary["block_size"]
            cursor = 0
            positions = []
            while True:
                page = client.get(f"/api/v1/occlusion-results/{result['result_id']}/positions",
                                  params={"scale": size, "cursor": cursor, "limit": 97})
                page.raise_for_status()
                payload = page.json()
                positions.extend(payload["positions"])
                if payload["next_cursor"] is None:
                    break
                cursor = payload["next_cursor"]
            count_map[str(size)] = len(positions)
            value = np.zeros((224, 224), dtype=np.float64)
            coverage = np.zeros((224, 224), dtype=np.float64)
            for item in positions:
                p0 = item["baseline_positive_probability"]
                pg = item["masked_positive_probability"]
                original_class = int(p0 >= 0.5)
                q0 = p0 if original_class else 1 - p0
                qg = pg if original_class else 1 - pg
                drop = q0 - qg
                formula_ok &= (abs(drop - item["decision_confidence_drop"]) < 1e-12 and
                               abs(max(drop, 0) - item["candidate_response"]) < 1e-12 and
                               item["prediction_flip"] == (original_class != int(pg >= 0.5)))
                x, y = item["x"], item["y"]
                value[y:y + size, x:x + size] += item["candidate_response"]
                coverage[y:y + size, x:x + size] += 1
            if np.any(coverage == 0):
                heatmap_ok = False
                continue
            response = value / coverage
            layer = summary["response_layer"]
            if summary["candidate_status"] == "valid":
                response_png = client.get(f"/api/v1/assets/{layer['asset_id']}",
                                          params={"result_id": result["result_id"]})
                pixels = np.asarray(Image.open(io.BytesIO(response_png.content)))
                expected_pixels = np.rint(response / max(float(response.max()), 1e-6) * 255).astype(np.uint8)
                heatmap_ok &= (pixels.shape == (224, 224) and np.array_equal(pixels, expected_pixels))
                grid_layer = summary["comparison_grid_layer"]
                grid = client.get(f"/api/v1/assets/{grid_layer['asset_id']}",
                                  params={"result_id": result["result_id"]}).json()
                expected_grid = response.reshape(14, 16, 14, 16).mean(axis=(1, 3))
                grid_ok &= (np.asarray(grid).shape == (14, 14) and np.allclose(grid, expected_grid, atol=1e-12))
            else:
                heatmap_ok &= layer is None and summary["candidate_layer"] is None
        record("mask_position_counts", count_map, VECTOR["expected"]["mask_positions"])
        record("fixed_decision_class_q0_qg_formula", bool(formula_ok), True)
        record("independent_heatmap_pixels_all_scales", bool(heatmap_ok), True)
        record("independent_14x14_grid_all_scales", bool(grid_ok), True)
        evidence["job_status_histories"] = {"parse": parsed["history"], "prediction": pred_state["history"],
                                            "occlusion": occ_state["history"]}

        malformed = client.post("/api/v1/cases", headers={"Idempotency-Key": uuid.uuid4().hex},
                                data={"input_kind": "dicom_series"},
                                files={"files": ("bad.dcm", b"not a DICOM", "application/dicom")})
        record("invalid_dicom", [malformed.status_code, malformed.json().get("code")],
               [422, "IMAGE_PARSE_FAILED"])
        unsupported = client.post("/api/v1/cases", headers={"Idempotency-Key": uuid.uuid4().hex},
                                  data={"input_kind": "nifti"}, files=files)
        record("unsupported_format", [unsupported.status_code, unsupported.json().get("code")],
               [415, "UNSUPPORTED_FORMAT"])
        missing_key = client.post("/api/v1/cases", data={"input_kind": "dicom_series"}, files=files)
        record("missing_idempotency_key", [missing_key.status_code, missing_key.json().get("code")],
               [422, "INVALID_REQUEST"])
        ds = pydicom.dcmread(io.BytesIO(data))
        ds.PatientID = "SYNTHETIC-NOT-ALLOWED"
        stream = io.BytesIO()
        ds.save_as(stream, enforce_file_format=True)
        identifiable = client.post("/api/v1/cases", headers={"Idempotency-Key": uuid.uuid4().hex},
                                   data={"input_kind": "dicom_series"},
                                   files={"files": ("identifiable.dcm", stream.getvalue(), "application/dicom")})
        record("identity_field_rejected", [identifiable.status_code, identifiable.json().get("code")],
               [422, "IMAGE_PARSE_FAILED"])
        unknown = client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000/result")
        record("missing_result", [unknown.status_code, unknown.json().get("code")],
               [404, "RESULT_NOT_FOUND"])
        traversal = client.get("/api/v1/assets/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
                               params={"result_id": result["result_id"]})
        record("asset_traversal_rejected", traversal.status_code, 404)
        with httpx.Client(base_url=args.url, timeout=60, trust_env=False) as anonymous:
            no_auth_asset = anonymous.get(
                f"/api/v1/assets/{result['scale_summaries'][0]['response_layer']['asset_id']}",
                params={"result_id": result["result_id"]})
        record("asset_access_boundary", no_auth_asset.status_code, 401 if token else 200)
        evidence["asset_without_auth_status"] = no_auth_asset.status_code
        evidence["observed_probability"] = probability
    evidence["summary"] = {status: sum(item["status"] == status for item in evidence["checks"].values())
                           for status in ("PASS", "FAIL")}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(evidence["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
