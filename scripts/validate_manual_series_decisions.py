#!/usr/bin/env python3
"""Validate Rule B manual decisions; never create a cohort or split."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "configs/formal_series_selection_rule_b_v1.json"
DEFAULT_DECISIONS = ROOT / "outputs/data/formal_series_rule_b_review_v1/manual_review_decisions.csv"
FORBIDDEN_REASON_PATTERNS = (
    r"\brandom\b",
    r"随机",
    r"\bcollection\b",
    r"\blabel\b",
    r"标签",
    r"(?:UID|uid).*(?:small|large|first|last|最小|最大|第一|最后)",
    r"(?:first|last|第一|最后).*(?:UID|uid)",
    r"列表.*(?:第一|最后)",
    r"模型|accuracy|AUC|loss|prediction|预测",
)
EVIDENCE_TERMS = (
    "diagnostic", "anatom", "coverage", "reconstruction", "kernel", "noise",
    "sharp", "artifact", "motion", "duplicate", "phase", "诊断", "解剖", "覆盖",
    "重建", "核", "噪声", "锐度", "伪影", "运动", "重复", "期相",
)


def json_list(value: str) -> list[str]:
    result = json.loads(value)
    if not isinstance(result, list):
        raise ValueError("candidate_series_uids must be a JSON list")
    return [str(item) for item in result]


def validate(path: Path) -> tuple[list[str], list[str]]:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = set(protocol["manual_decision_requirements"]["required_fields"]) | {
        "protocol_id",
        "case_id",
        "patient_id",
        "case_type",
        "candidate_series_uids",
        "allowed_decisions",
    }
    errors = []
    pending = []
    if missing := required - set(frame.columns):
        return [f"Missing columns: {sorted(missing)}"], []
    if len(frame) != 13 or frame.case_id.duplicated().any() or frame.patient_id.duplicated().any():
        errors.append("Decision file must contain exactly 13 unique cases and patients")
    for row in frame.itertuples(index=False):
        prefix = f"{row.case_id}/{row.patient_id}"
        if row.protocol_id != protocol["protocol_id"]:
            errors.append(f"{prefix}: protocol_id mismatch")
            continue
        candidates = json_list(row.candidate_series_uids)
        if row.decision in ("", "PENDING", "DEFER"):
            pending.append(prefix)
            continue
        allowed = (
            {"SELECT_ONE_CANDIDATE", "EXCLUDE_PATIENT"}
            if row.case_type == "technical_tie"
            else {"INCLUDE_REVIEW_SERIES", "EXCLUDE_PATIENT"}
        )
        if row.decision not in allowed:
            errors.append(f"{prefix}: invalid decision {row.decision}")
        needs_uid = row.decision in ("SELECT_ONE_CANDIDATE", "INCLUDE_REVIEW_SERIES")
        if needs_uid and row.selected_series_uid not in candidates:
            errors.append(f"{prefix}: selected_series_uid is not an allowed candidate")
        if not needs_uid and row.selected_series_uid:
            errors.append(f"{prefix}: exclusion must not contain selected_series_uid")
        reason = row.reason.strip()
        if len(reason) < 20:
            errors.append(f"{prefix}: reason must contain at least 20 characters of reviewable evidence")
        if not any(term.lower() in reason.lower() for term in EVIDENCE_TERMS):
            errors.append(f"{prefix}: reason must cite diagnostic, coverage, reconstruction, or artifact evidence")
        if any(re.search(pattern, reason, flags=re.IGNORECASE) for pattern in FORBIDDEN_REASON_PATTERNS):
            errors.append(f"{prefix}: reason uses a forbidden tie-break input")
        if not row.reviewer.strip() or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", row.reviewed_at_utc.strip()
        ):
            errors.append(f"{prefix}: reviewer and UTC timestamp are required")
        if row.image_evidence_reviewed.strip().upper() != "YES":
            errors.append(f"{prefix}: image_evidence_reviewed must be YES")
        if row.metadata_evidence_reviewed.strip().upper() != "YES":
            errors.append(f"{prefix}: metadata_evidence_reviewed must be YES")
    return errors, pending


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decisions", nargs="?", type=Path, default=DEFAULT_DECISIONS)
    args = parser.parse_args()
    path = args.decisions if args.decisions.is_absolute() else ROOT / args.decisions
    errors, pending = validate(path)
    result = {
        "decision_file": path.relative_to(ROOT).as_posix(),
        "errors": errors,
        "pending_cases": pending,
        "valid_complete_manual_review": not errors and not pending,
        "cohort_created": False,
        "split_created": False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 2 if pending else 0


if __name__ == "__main__":
    raise SystemExit(main())
