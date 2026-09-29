from __future__ import annotations

import csv
from io import StringIO
import json
from typing import Any, Mapping

from .bundle import ReviewBundle


DECISION_FIELDS = (
    "protocol_id",
    "case_id",
    "patient_id",
    "case_type",
    "candidate_series_uids",
    "allowed_decisions",
    "decision",
    "selected_series_uid",
    "reason",
    "reviewer",
    "reviewed_at_utc",
    "image_evidence_reviewed",
    "metadata_evidence_reviewed",
    "validation_status",
)


class FinalExportNotReady(ValueError):
    pass


def allowed_decisions(case_type: str) -> str:
    if case_type == "technical_tie":
        return "SELECT_ONE_CANDIDATE | EXCLUDE_PATIENT | DEFER"
    return "INCLUDE_REVIEW_SERIES | EXCLUDE_PATIENT | DEFER"


def build_export_rows(
    bundle: ReviewBundle,
    final_decisions: Mapping[str, Mapping[str, Any]],
    *,
    kind: str = "snapshot",
) -> list[dict[str, str]]:
    if kind not in {"snapshot", "final"}:
        raise ValueError("export kind must be snapshot or final")
    complete_non_defer = (
        len(final_decisions) == len(bundle.cases)
        and all(
            case.case_id in final_decisions
            and final_decisions[case.case_id].get("decision") != "DEFER"
            for case in bundle.cases
        )
    )
    if kind == "final" and not complete_non_defer:
        raise FinalExportNotReady("final export requires a non-DEFER final decision for all 13 cases")

    rows: list[dict[str, str]] = []
    for case in bundle.cases:
        final = final_decisions.get(case.case_id)
        canonical_candidate_uids = case.declared_candidate_uids or case.selectable_uids
        if final:
            decision = str(final["decision"])
            selected_uid = str(final.get("selected_series_uid") or "")
            row = {
                "protocol_id": bundle.protocol_id,
                "case_id": case.case_id,
                "patient_id": case.patient_id,
                "case_type": case.case_type,
                "candidate_series_uids": json.dumps(
                    list(canonical_candidate_uids), ensure_ascii=False
                ),
                "allowed_decisions": allowed_decisions(case.case_type),
                "decision": decision,
                "selected_series_uid": selected_uid,
                "reason": str(final.get("reason") or ""),
                "reviewer": "admin",
                "reviewed_at_utc": str(final.get("reviewed_at_utc") or ""),
                "image_evidence_reviewed": "YES" if final.get("image_evidence_reviewed") else "",
                "metadata_evidence_reviewed": "YES" if final.get("metadata_evidence_reviewed") else "",
                "validation_status": (
                    "READY_FOR_VALIDATION" if decision != "DEFER" else "INCOMPLETE_DEFERRED"
                ),
            }
        else:
            row = {
                "protocol_id": bundle.protocol_id,
                "case_id": case.case_id,
                "patient_id": case.patient_id,
                "case_type": case.case_type,
                "candidate_series_uids": json.dumps(
                    list(canonical_candidate_uids), ensure_ascii=False
                ),
                "allowed_decisions": allowed_decisions(case.case_type),
                "decision": "PENDING",
                "selected_series_uid": "",
                "reason": "",
                "reviewer": "",
                "reviewed_at_utc": "",
                "image_evidence_reviewed": "",
                "metadata_evidence_reviewed": "",
                "validation_status": "INCOMPLETE_REASON_REQUIRED",
            }
        rows.append(row)
    return rows


def render_csv(rows: list[Mapping[str, str]]) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=DECISION_FIELDS, extrasaction="raise", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in DECISION_FIELDS})
    return buffer.getvalue().encode("utf-8")
