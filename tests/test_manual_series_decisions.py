"""Validation boundaries for the frozen Rule B manual-review record."""
import json
import tempfile
from pathlib import Path
import unittest

import pandas as pd

from scripts.validate_manual_series_decisions import validate


class ManualDecisionValidationTests(unittest.TestCase):
    def setUp(self):
        rows = []
        for index in range(1, 14):
            case_type = "technical_tie" if index <= 12 else "diagnostic_type_uncertain"
            candidates = (
                [f"1.2.840.10008.5.1.4.{index}.1", f"1.2.840.10008.5.1.4.{index}.2"]
                if case_type == "technical_tie"
                else [f"1.2.840.10008.5.1.4.{index}.1"]
            )
            rows.append({
                "protocol_id": "formal-series-selection-rule-b-v1",
                "case_id": f"TEST-{index:03d}",
                "patient_id": f"SYNTHETIC-P{index:03d}",
                "case_type": case_type,
                "candidate_series_uids": json.dumps(candidates),
                "allowed_decisions": (
                    "SELECT_ONE_CANDIDATE | EXCLUDE_PATIENT | DEFER"
                    if case_type == "technical_tie"
                    else "INCLUDE_REVIEW_SERIES | EXCLUDE_PATIENT | DEFER"
                ),
                "decision": "PENDING",
                "selected_series_uid": "",
                "reason": "",
                "reviewer": "",
                "reviewed_at_utc": "",
                "image_evidence_reviewed": "",
                "metadata_evidence_reviewed": "",
                "validation_status": "INCOMPLETE_REASON_REQUIRED",
            })
        self.frame = pd.DataFrame(rows)

    def validate_frame(self, frame):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.csv"
            frame.to_csv(path, index=False)
            return validate(path)

    def test_synthetic_template_is_pending_without_validation_errors(self):
        errors, pending = self.validate_frame(self.frame)
        self.assertEqual(errors, [])
        self.assertEqual(len(pending), 13)

    def test_reviewable_reason_and_allowed_candidate_pass(self):
        frame = self.frame.copy()
        candidates = json.loads(frame.loc[0, "candidate_series_uids"])
        frame.loc[0, [
            "decision", "selected_series_uid", "reason", "reviewer", "reviewed_at_utc",
            "image_evidence_reviewed", "metadata_evidence_reviewed",
        ]] = [
            "SELECT_ONE_CANDIDATE",
            candidates[0],
            "该序列胸部解剖覆盖完整，肺窗重建噪声较低且未见明显运动伪影。",
            "reviewer",
            "2026-09-22T12:00:00Z",
            "YES",
            "YES",
        ]
        errors, pending = self.validate_frame(frame)
        self.assertEqual(errors, [])
        self.assertEqual(len(pending), 12)

    def test_uid_order_or_random_reason_is_rejected(self):
        frame = self.frame.copy()
        candidates = json.loads(frame.loc[0, "candidate_series_uids"])
        frame.loc[0, [
            "decision", "selected_series_uid", "reason", "reviewer", "reviewed_at_utc",
            "image_evidence_reviewed", "metadata_evidence_reviewed",
        ]] = [
            "SELECT_ONE_CANDIDATE",
            candidates[0],
            "按 UID 最小值随机选择，没有影像覆盖或重建方面的依据。",
            "reviewer",
            "2026-09-22T12:00:00Z",
            "YES",
            "YES",
        ]
        errors, _ = self.validate_frame(frame)
        self.assertTrue(any("forbidden tie-break" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
