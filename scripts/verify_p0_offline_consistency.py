#!/usr/bin/env python3
"""Compare local HTTP P0 with frozen smoke train output; never read formal test."""
from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
import time
from pathlib import Path

import httpx
import pandas as pd
import pydicom
from pydicom.uid import generate_uid


def wait_result(client, base, job_id):
    for _ in range(300):
        job = client.get(f"{base}/api/v1/jobs/{job_id}").json()
        if job["status"] == "COMPLETED":
            return client.get(f"{base}/api/v1/jobs/{job_id}/result").json()
        if job["status"] == "FAILED":
            raise RuntimeError("API job failed")
        time.sleep(.2)
    raise TimeoutError("API job did not complete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8877")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.frozen_root.resolve()
    smoke = root / "outputs/experiments/FORMAL-BL-R18-V1/occlusion_stage1/smoke"
    fixture = pd.read_csv(smoke / "train_fixture.csv").iloc[0]
    if fixture["split"] != "train":
        raise RuntimeError("Only the frozen train fixture is permitted")
    source = (root / fixture["image_path"]).resolve()
    if not source.is_relative_to((root / "data/full_raw").resolve()):
        raise RuntimeError("Fixture path is outside controlled source")
    reference = pd.read_csv(smoke / "raw_responses.csv")
    reference = reference.loc[reference.fixture_id.eq("f0")]
    ds = pydicom.dcmread(source)
    original_pixels = bytes(ds.PixelData)
    ds.remove_private_tags()
    for element in ds.iterall():
        if element.VR == "PN":
            element.value = ""
    for key in ("PatientID", "PatientBirthDate", "PatientAddress", "InstitutionName",
                "ReferringPhysicianName", "AccessionNumber", "StudyDescription",
                "SeriesDescription", "ProtocolName", "ImageComments"):
        if key in ds:
            del ds[key]
    ds.PatientIdentityRemoved = "YES"
    ds.BurnedInAnnotation = "NO"
    for key in ("SOPInstanceUID", "StudyInstanceUID", "SeriesInstanceUID"):
        if key in ds:
            setattr(ds, key, generate_uid())
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    assert bytes(ds.PixelData) == original_pixels
    with tempfile.TemporaryDirectory(prefix="epilocate-p0-deid-") as directory:
        upload = Path(directory) / "deidentified.dcm"
        ds.save_as(upload, enforce_file_format=True)
        with httpx.Client(timeout=60) as client:
            with upload.open("rb") as stream:
                response = client.post(f"{args.url}/api/v1/cases", headers={"Idempotency-Key": "offline-check-" + os.urandom(8).hex()},
                                       data={"input_kind": "dicom_series"}, files={"files": ("deidentified.dcm", stream, "application/dicom")})
            response.raise_for_status()
            case_id = response.json()["case_id"]
            slice_id = client.get(f"{args.url}/api/v1/cases/{case_id}/slices").json()["slices"][0]["slice_id"]
            request = {"case_id": case_id, "slice_id": slice_id, "model_id": "baseline_resnet18"}
            response = client.post(f"{args.url}/api/v1/jobs/occlusion", headers={"Idempotency-Key": "offline-occlusion-" + os.urandom(8).hex()},
                                   json={**request, "scales": [16, 32, 64], "protocol_id": "stage1-occlusion-instability-v1"})
            response.raise_for_status()
            actual = wait_result(client, args.url, response.json()["job_id"])
            p0_reference = float(reference.p0.iloc[0])
            p0_actual = actual["prediction"]["positive_probability"]
            per_scale = {}
            for size in (16, 32, 64):
                expected = reference.loc[reference.block_size.eq(size) & reference.x.eq(0) & reference.y.eq(0)].iloc[0]
                positions = client.get(f"{args.url}/api/v1/occlusion-results/{actual['result_id']}/positions",
                                       params={"scale": size, "limit": 1}).json()["positions"]
                pg_actual = positions[0]["masked_positive_probability"]
                per_scale[str(size)] = {"masked_probability_absolute_error_at_0_0": abs(pg_actual - float(expected.pg))}
            report = {"source": "LIVE_CASE", "reference": "frozen smoke train fixture f0 (identity omitted)",
                      "checkpoint_sha256": actual["model_version"], "test_pixels_read": False,
                      "pixel_data_unchanged_during_deidentification": True,
                      "baseline_probability_absolute_error": abs(p0_actual - p0_reference),
                      "scales": per_scale,
                      "pass_tolerance": 1e-5}
            if report["baseline_probability_absolute_error"] > 1e-5 or any(v["masked_probability_absolute_error_at_0_0"] > 1e-5 for v in per_scale.values()):
                raise AssertionError(json.dumps(report))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
