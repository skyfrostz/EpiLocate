"""Contract tests for the PNG-only manual-review bundle."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.pixels import get_decoder
from pydicom.uid import (
    CTImageStorage,
    ExplicitVRLittleEndian,
    JPEGLosslessSV1,
    generate_uid,
)

from scripts.build_review_bundle import build_review_bundle, window_to_uint8


CASE_FIELDS = [
    "case_id",
    "case_type",
    "patient_id",
    "candidate_series_uids",
    "context_series_uids",
    "required_judgment",
    "allowed_decisions",
    "status",
]
CANDIDATE_FIELDS = [
    "case_id",
    "case_type",
    "patient_id",
    "candidate_role",
    "series_uid",
    "study_uid",
    "series_description",
    "convolution_kernel",
    "slice_thickness_mm",
    "pixel_spacing_row_mm",
    "pixel_spacing_column_mm",
    "coverage_mm",
    "slice_count",
    "image_types",
    "hard_status_before_review",
    "review_question",
    "montage_path",
]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_dicom(
    path: Path,
    *,
    series_uid: str,
    study_uid: str,
    sop_uid: str,
    z: float,
    instance: int,
    stored_value: int,
    photometric: str = "MONOCHROME2",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = sop_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = generate_uid()
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = CTImageStorage
    ds.SOPInstanceUID = sop_uid
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.Modality = "CT"
    ds.Rows = 512
    ds.Columns = 512
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = photometric
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.ImagePositionPatient = [0, 0, z]
    ds.InstanceNumber = instance
    ds.RescaleSlope = 1
    ds.RescaleIntercept = -1350
    pixels = np.full((512, 512), stored_value, dtype="<i2")
    ds.PixelData = pixels.tobytes()
    ds.save_as(path, enforce_file_format=True)


class ReviewBundleBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.raw = self.root / "raw"
        self.packet = self.root / "packet"
        self.packet.mkdir()
        self.output = self.root / "bundle"
        self.protocol = self.root / "protocol.json"
        self.protocol.write_text(json.dumps({
            "protocol_id": "formal-series-selection-rule-b-v1",
            "status": "FROZEN",
            "phase_boundary": {"formal_cohort_finalized": False},
        }), encoding="utf-8")

        self.tie_a = generate_uid()
        self.tie_b = generate_uid()
        protocol_id = "formal-series-selection-rule-b-v1"
        candidate_key = lambda uid: hashlib.sha256(
            "\x1f".join((protocol_id, "TIE-001", "eligible_top_tied", uid)).encode("utf-8")
        ).hexdigest()[:24]
        if candidate_key(self.tie_a) < candidate_key(self.tie_b):
            self.tie_a, self.tie_b = self.tie_b, self.tie_a
        self.diag = generate_uid()
        self.context = generate_uid()
        self.series = [self.tie_a, self.tie_b, self.diag, self.context]
        self.study = generate_uid()
        frame_specs = {
            self.tie_a: [(20, 3, 300), (0, 1, 100), (10, 2, 200)],
            self.tie_b: [(0, 1, 400)],
            self.diag: [(0, 1, 500)],
            self.context: [(0, 1, 600)],
        }
        for series_index, (uid, specs) in enumerate(frame_specs.items()):
            directory = self.raw / f"series-source-name-{series_index}"
            for file_index, (z, instance, value) in enumerate(specs):
                write_dicom(
                    directory / f"private-source-name-{file_index}.dcm",
                    series_uid=uid,
                    study_uid=self.study,
                    sop_uid=generate_uid(),
                    z=z,
                    instance=instance,
                    stored_value=value,
                    photometric="MONOCHROME1" if uid == self.diag else "MONOCHROME2",
                )

        for index, uid in enumerate(self.series):
            montage = self.packet / "montages" / f"source-montage-{index}.png"
            montage.parent.mkdir(exist_ok=True)
            Image.new("RGB", (40, 20), color=(index * 20, 50, 80)).save(montage)

        cases = [
            {
                "case_id": "TIE-001",
                "case_type": "technical_tie",
                "patient_id": "SYNTHETIC-P001",
                "candidate_series_uids": json.dumps([self.tie_a, self.tie_b]),
                "context_series_uids": "[]",
                "required_judgment": "Compare reconstruction and coverage.",
                "allowed_decisions": "SELECT_ONE_CANDIDATE | EXCLUDE_PATIENT | DEFER",
                "status": "PENDING_MANUAL_REVIEW",
            },
            {
                "case_id": "DIAG-001",
                "case_type": "diagnostic_type_uncertain",
                "patient_id": "SYNTHETIC-P002",
                "candidate_series_uids": json.dumps([self.diag]),
                "context_series_uids": json.dumps([self.context]),
                "required_judgment": "Confirm diagnostic suitability.",
                "allowed_decisions": "INCLUDE_REVIEW_SERIES | EXCLUDE_PATIENT | DEFER",
                "status": "PENDING_MANUAL_REVIEW",
            },
        ]
        write_csv(self.packet / "manual_review_cases.csv", CASE_FIELDS, cases)

        candidates = []
        specs = [
            ("TIE-001", "technical_tie", "SYNTHETIC-P001", "eligible_top_tied", self.tie_a, 3),
            ("TIE-001", "technical_tie", "SYNTHETIC-P001", "eligible_top_tied", self.tie_b, 1),
            ("DIAG-001", "diagnostic_type_uncertain", "SYNTHETIC-P002", "review_candidate", self.diag, 1),
            (
                "DIAG-001",
                "diagnostic_type_uncertain",
                "SYNTHETIC-P002",
                "excluded_bone_only_context",
                self.context,
                1,
            ),
        ]
        for index, (case_id, case_type, patient_id, role, uid, count) in enumerate(specs):
            candidates.append({
                "case_id": case_id,
                "case_type": case_type,
                "patient_id": patient_id,
                "candidate_role": role,
                "series_uid": uid,
                "study_uid": self.study,
                "series_description": "SYNTHETIC CHEST",
                "convolution_kernel": "B",
                "slice_thickness_mm": "1.25",
                "pixel_spacing_row_mm": "0.7",
                "pixel_spacing_column_mm": "0.7",
                "coverage_mm": "20",
                "slice_count": str(count),
                "image_types": "ORIGINAL | PRIMARY | AXIAL",
                "hard_status_before_review": "eligible" if role != "review_candidate" else "review",
                "review_question": "Synthetic evidence only.",
                "montage_path": f"montages/source-montage-{index}.png",
            })
        write_csv(self.packet / "manual_review_candidates.csv", CANDIDATE_FIELDS, candidates)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def build(self) -> dict[str, object]:
        return build_review_bundle(
            raw_root=self.raw,
            cases_csv=self.packet / "manual_review_cases.csv",
            candidates_csv=self.packet / "manual_review_candidates.csv",
            protocol_path=self.protocol,
            output=self.output,
            expected_cases=2,
            expected_series=4,
            expected_frames=6,
        )

    def test_bundle_is_deterministic_complete_and_contains_no_source_paths(self) -> None:
        raw_before = {
            path.relative_to(self.raw).as_posix(): (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
            for path in self.raw.rglob("*.dcm")
        }
        first = self.build()
        first_manifest_bytes = (self.output / "bundle.json").read_bytes()
        first_hashes = {
            path.relative_to(self.output).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.output.rglob("*")
            if path.is_file()
        }
        second = self.build()
        self.assertEqual(first, second)
        self.assertEqual(first_manifest_bytes, (self.output / "bundle.json").read_bytes())
        self.assertEqual(first_hashes, {
            path.relative_to(self.output).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.output.rglob("*")
            if path.is_file()
        })
        self.assertEqual(raw_before, {
            path.relative_to(self.raw).as_posix(): (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
            for path in self.raw.rglob("*.dcm")
        })

        self.assertEqual(set(second), {
            "format", "version", "protocol_id", "protocol_sha256", "window", "cases", "assets"
        })
        self.assertEqual(second["window"]["resampled"], False)
        manifest_text = (self.output / "bundle.json").read_text(encoding="utf-8")
        self.assertNotIn(str(self.raw), manifest_text)
        self.assertNotIn("private-source-name", manifest_text)
        self.assertNotIn("source-montage", manifest_text)
        self.assertNotIn(".dcm", manifest_text.lower())

        files = {
            path.relative_to(self.output).as_posix()
            for path in self.output.rglob("*")
            if path.is_file() and path.name != "bundle.json"
        }
        asset_paths = {asset["path"] for asset in second["assets"].values()}
        self.assertEqual(files, asset_paths)
        self.assertEqual(len(second["assets"]), 10)  # Six frames and four montages.
        for asset in second["assets"].values():
            path = self.output / asset["path"]
            self.assertEqual(path.suffix, ".png")
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), asset["sha256"])
            with Image.open(path) as image:
                image.verify()

    def test_projection_sort_windowing_and_context_are_preserved(self) -> None:
        manifest = self.build()
        tie_case = next(case for case in manifest["cases"] if case["case_id"] == "TIE-001")
        self.assertEqual(
            [item["series_uid"] for item in tie_case["candidates"]],
            [self.tie_a, self.tie_b],
            "Candidate order must preserve the frozen CSV rows",
        )
        self.assertGreater(
            tie_case["candidates"][0]["candidate_key"],
            tie_case["candidates"][1]["candidate_key"],
            "Fixture must remain opposite to candidate-key sort order",
        )
        candidate = next(item for item in tie_case["candidates"] if item["series_uid"] == self.tie_a)
        projections = [manifest["assets"][asset_id]["projection_mm"] for asset_id in candidate["frame_asset_ids"]]
        self.assertEqual(projections, [0.0, 10.0, 20.0])
        means = []
        for asset_id in candidate["frame_asset_ids"]:
            with Image.open(self.output / manifest["assets"][asset_id]["path"]) as image:
                self.assertEqual(image.size, (512, 512))
                self.assertEqual(image.mode, "L")
                means.append(int(np.asarray(image).mean()))
        self.assertEqual(means, sorted(means))

        diag_case = next(case for case in manifest["cases"] if case["case_id"] == "DIAG-001")
        self.assertEqual([item["series_uid"] for item in diag_case["candidates"]], [self.diag])
        self.assertEqual([item["series_uid"] for item in diag_case["context"]], [self.context])
        self.assertEqual(diag_case["candidate_series_uids"], [self.diag])
        self.assertEqual(diag_case["context_series_uids"], [self.context])

    def test_exact_hu_window_and_monochrome1_inversion(self) -> None:
        stored = np.zeros((512, 512), dtype=np.int16)
        stored[0, 0:3] = [0, 750, 1500]
        mono2 = window_to_uint8(stored, 1.0, -1350.0, "MONOCHROME2")
        mono1 = window_to_uint8(stored, 1.0, -1350.0, "MONOCHROME1")
        np.testing.assert_array_equal(mono2[0, 0:3], [0, 128, 255])
        np.testing.assert_array_equal(mono1[0, 0:3], [255, 127, 0])
        np.testing.assert_array_equal(mono1, 255 - mono2)

    def test_environment_has_jpeg_lossless_decoder_used_by_pixel_array(self) -> None:
        decoder = get_decoder(JPEGLosslessSV1)
        self.assertTrue(decoder.is_available, "pylibjpeg-libjpeg is required for JPEG Lossless input")

    def test_traversal_in_montage_path_is_rejected_without_partial_output(self) -> None:
        path = self.packet / "manual_review_candidates.csv"
        with path.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        rows[0]["montage_path"] = "../outside.png"
        write_csv(path, CANDIDATE_FIELDS, rows)
        with self.assertRaisesRegex(ValueError, "Unsafe resource path"):
            self.build()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
