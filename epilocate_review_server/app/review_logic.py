from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence


TIE_KEYS = ("texture", "noise", "artifact", "coverage")
DIAG_KEYS = ("diag_coverage", "diag_artifact", "diag_use")
TIE_VALUES = frozenset({"A", "B", "SAME", "UNSURE"})
DIAG_VALUES = frozenset({"YES", "NO", "UNSURE"})
FINAL_DECISIONS = frozenset(
    {"SELECT_ONE_CANDIDATE", "INCLUDE_REVIEW_SERIES", "EXCLUDE_PATIENT", "DEFER"}
)
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
    "重建", "核", "噪声", "锐度", "伪影", "运动", "重复", "期相", "肺实质", "纹理",
)


@dataclass(frozen=True)
class Recommendation:
    decision: str
    selected_position: str | None
    reason: str
    complete: bool = True

    def as_dict(self, ordered_uids: Sequence[str] = ()) -> dict[str, Any]:
        selected_uid = ""
        if self.selected_position and len(ordered_uids) >= 2:
            selected_uid = ordered_uids[0 if self.selected_position == "A" else 1]
        elif self.selected_position == "A" and ordered_uids:
            selected_uid = ordered_uids[0]
        return {
            "decision": self.decision,
            "selected_position": self.selected_position,
            "selected_series_uid": selected_uid,
            "reason": self.reason,
            "complete": self.complete,
        }


def recommend_tie(observations: Mapping[str, str], *, duplicate_warning: bool = False) -> Recommendation:
    values = {key: str(observations.get(key, "")).upper() for key in TIE_KEYS}
    if any(values[key] not in TIE_VALUES for key in TIE_KEYS):
        return Recommendation("PENDING", None, "请完成四项观察。", complete=False)
    a_count = sum(value == "A" for value in values.values())
    b_count = sum(value == "B" for value in values.values())
    if a_count >= 2 and b_count == 0:
        return Recommendation("SELECT_ONE_CANDIDATE", "A", _tie_reason("A", values))
    if b_count >= 2 and a_count == 0:
        return Recommendation("SELECT_ONE_CANDIDATE", "B", _tie_reason("B", values))
    if all(value in {"SAME", "UNSURE"} for value in values.values()):
        reason = (
            "两套候选在胸部解剖覆盖、肺实质纹理、图像噪声和伪影方面未观察到稳定且可重复的差异，"
            "现有图像与 metadata 证据不足以支持可靠选择，因此暂缓决定。"
        )
        if duplicate_warning:
            reason += " 两套候选的技术参数相同，需进一步检查是否为重复 Series。"
    else:
        reason = (
            "不同观察维度对候选 Series 的支持方向不一致，现有图像与 metadata 证据存在冲突，"
            "不足以形成稳定、可重复的人工选择依据，因此暂缓决定。"
        )
    return Recommendation("DEFER", None, reason)


def _tie_reason(winner: str, observations: Mapping[str, str]) -> str:
    name = f"候选 {winner}"
    facts = []
    if observations["texture"] == winner:
        facts.append(f"{name}的肺实质纹理和细小解剖结构显示更清楚")
    if observations["noise"] == winner:
        facts.append(f"{name}的图像噪声更少，对肺实质观察干扰更小")
    if observations["artifact"] == winner:
        facts.append(f"{name}的运动、条纹或其他明显伪影更少")
    if observations["coverage"] == winner:
        facts.append(f"{name}的胸部解剖覆盖更完整")
    return "；".join(facts) + "。以上为可复核图像与 metadata 证据，因此选择该候选作为研究输入。"


def recommend_diag(observations: Mapping[str, str]) -> Recommendation:
    values = {key: str(observations.get(key, "")).upper() for key in DIAG_KEYS}
    if any(values[key] not in DIAG_VALUES for key in DIAG_KEYS):
        return Recommendation("PENDING", None, "请完成三项观察。", complete=False)
    if all(value == "YES" for value in values.values()):
        return Recommendation(
            "INCLUDE_REVIEW_SERIES",
            "A",
            "完整 Series 的胸部解剖覆盖基本完整，图像运动、条纹及其他伪影处于可接受范围；"
            "结合 metadata，可确认其具备作为研究用诊断性胸部 CT 输入的基本条件，因此纳入该 Series。",
        )
    if "NO" in values.values():
        facts = []
        if values["diag_coverage"] == "NO":
            facts.append("胸部解剖覆盖明显不足")
        if values["diag_artifact"] == "NO":
            facts.append("运动、条纹或其他伪影已经影响观察")
        if values["diag_use"] == "NO":
            facts.append("结合图像与 metadata 无法支持其作为研究输入")
        return Recommendation(
            "EXCLUDE_PATIENT", None,
            "；".join(facts) + "。该 Series 不适合作为研究用诊断性胸部 CT 输入，因此排除该患者。",
        )
    return Recommendation(
        "DEFER", None,
        "当前复核中仍存在无法确认的图像或 metadata 证据，尚不能可靠判断该 Series 是否适合作为"
        "诊断性胸部 CT 研究输入，因此暂缓决定。",
    )


def recommendation(case_type: str, observations: Mapping[str, str], *, case_id: str = "") -> Recommendation:
    if case_type == "technical_tie":
        return recommend_tie(observations, duplicate_warning=case_id == "TIE-012")
    if case_type == "diagnostic_type_uncertain":
        return recommend_diag(observations)
    raise ValueError("unknown case type")


def validate_decision(
    case_type: str,
    decision: str,
    selected_series_uid: str,
    reason: str,
    selectable_uids: Sequence[str],
    image_evidence_reviewed: bool,
    metadata_evidence_reviewed: bool,
    *,
    allow_pending: bool = False,
) -> list[str]:
    errors: list[str] = []
    decision = decision.strip().upper()
    selected_series_uid = selected_series_uid.strip()
    reason = reason.strip()
    allowed = (
        {"SELECT_ONE_CANDIDATE", "EXCLUDE_PATIENT", "DEFER"}
        if case_type == "technical_tie"
        else {"INCLUDE_REVIEW_SERIES", "EXCLUDE_PATIENT", "DEFER"}
    )
    if allow_pending:
        allowed.add("PENDING")
    if decision not in allowed:
        errors.append("invalid decision for case type")
    needs_uid = decision in {"SELECT_ONE_CANDIDATE", "INCLUDE_REVIEW_SERIES"}
    if needs_uid and selected_series_uid not in set(selectable_uids):
        errors.append("selected_series_uid is not an allowed candidate")
    if not needs_uid and selected_series_uid:
        errors.append("this decision must not contain selected_series_uid")
    if decision != "PENDING":
        if len(reason) < 20:
            errors.append("reason must contain at least 20 characters of reviewable evidence")
        if reason and not any(term.lower() in reason.lower() for term in EVIDENCE_TERMS):
            errors.append("reason must cite diagnostic, coverage, reconstruction, or artifact evidence")
        if any(re.search(pattern, reason, re.IGNORECASE) for pattern in FORBIDDEN_REASON_PATTERNS):
            errors.append("reason uses a forbidden tie-break input")
        if not image_evidence_reviewed:
            errors.append("image evidence must be reviewed")
        if not metadata_evidence_reviewed:
            errors.append("metadata evidence must be reviewed")
    return errors


def consensus_status(reviews: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    submitted = [review for review in reviews if review.get("status") == "SUBMITTED"]
    has_defer = any(review.get("decision") == "DEFER" for review in submitted)
    if len(submitted) < 2:
        return {"status": "WAITING", "has_defer": has_defer, "decision": None, "selected_series_uid": None}
    first, second = submitted[:2]
    same = (
        first.get("decision") == second.get("decision")
        and (first.get("selected_series_uid") or "") == (second.get("selected_series_uid") or "")
    )
    return {
        "status": "CONSENSUS" if same else "CONFLICT",
        "has_defer": has_defer,
        "decision": first.get("decision") if same else None,
        "selected_series_uid": (first.get("selected_series_uid") or "") if same else None,
    }
