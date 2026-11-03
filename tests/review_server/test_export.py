from __future__ import annotations

from pathlib import Path

import pytest

from epilocate_review_server.app.bundle import Candidate, ReviewBundle, ReviewCase
from epilocate_review_server.app.config import EXPECTED_PROTOCOL_ID, EXPECTED_PROTOCOL_SHA256
from epilocate_review_server.app.export import DECISION_FIELDS, FinalExportNotReady, build_export_rows, render_csv
from scripts.validate_manual_series_decisions import validate


def synthetic_bundle(tmp_path: Path) -> ReviewBundle:
    cases = []
    for index in range(1, 14):
        case_type = "technical_tie" if index <= 12 else "diagnostic_type_uncertain"
        count = 2 if index <= 12 else 1
        candidates = tuple(
            Candidate(
                candidate_key=f"key-{index}-{candidate_index}",
                series_uid=f"1.2.840.synthetic.{index}.{candidate_index}",
                role="eligible_top_tied" if index <= 12 else "review_candidate",
                metadata={},
                montage_asset_id=None,
                frame_asset_ids=(f"asset-{index}-{candidate_index}",),
            )
            for candidate_index in range(count)
        )
        cases.append(
            ReviewCase(
                case_id=f"TIE-{index:03d}" if index <= 12 else "DIAG-001",
                case_type=case_type,
                patient_id=f"SYNTHETIC-P{index:03d}",
                candidates=candidates,
            )
        )
    return ReviewBundle(
        tmp_path / "bundle.json",
        EXPECTED_PROTOCOL_ID,
        EXPECTED_PROTOCOL_SHA256,
        cases,
        {},
        {},
    )


def final_records(bundle: ReviewBundle, defer_case: str | None = None):
    records = {}
    for case in bundle.cases:
        include = case.case_id != defer_case
        records[case.case_id] = {
            "decision": (
                "SELECT_ONE_CANDIDATE"
                if include and case.case_type == "technical_tie"
                else "INCLUDE_REVIEW_SERIES"
                if include
                else "DEFER"
            ),
            "selected_series_uid": case.selectable_uids[0] if include else "",
            "reason": "该 Series 胸部解剖覆盖完整，肺窗重建噪声低且未见明显运动伪影。",
            "reviewed_at_utc": "2026-09-24T12:00:00Z",
            "image_evidence_reviewed": True,
            "metadata_evidence_reviewed": True,
        }
    return records


def test_export_has_exact_14_column_contract_and_validator_accepts_complete(tmp_path):
    bundle = synthetic_bundle(tmp_path)
    rows = build_export_rows(bundle, final_records(bundle), kind="final")
    assert tuple(rows[0]) == DECISION_FIELDS
    assert all(row["reviewer"] == "admin" for row in rows)
    output = tmp_path / "manual_review_decisions.csv"
    output.write_bytes(render_csv(rows))
    errors, pending = validate(output)
    assert errors == []
    assert pending == []


def test_snapshot_with_defer_is_auditable_but_final_export_is_closed(tmp_path):
    bundle = synthetic_bundle(tmp_path)
    records = final_records(bundle, defer_case=bundle.cases[0].case_id)
    rows = build_export_rows(bundle, records, kind="snapshot")
    assert rows[0]["decision"] == "DEFER"
    assert rows[0]["validation_status"] == "INCOMPLETE_DEFERRED"
    output = tmp_path / "snapshot.csv"
    output.write_bytes(render_csv(rows))
    errors, pending = validate(output)
    assert errors == []
    assert len(pending) == 1
    with pytest.raises(FinalExportNotReady):
        build_export_rows(bundle, records, kind="final")
