#!/usr/bin/env python3
"""Prepare the frozen Rule B manual-review packet without selecting a cohort."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys
import textwrap
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pydicom


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/full_raw"
ANALYSIS = ROOT / "outputs/data/fair_series_rule_analysis_v1"
PROTOCOL = ROOT / "configs/formal_series_selection_rule_b_v1.json"
OUT = ROOT / "outputs/data/formal_series_rule_b_review_v1"
MONTAGES = OUT / "montages"
WINDOW_CENTER = -600.0
WINDOW_WIDTH = 1500.0
FRACTIONS = (0.25, 0.50, 0.75)
FORMAL_SPLIT_NAMES = (
    "full_train.csv",
    "full_val.csv",
    "full_test.csv",
    "full_split_summary.json",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_hashes(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(ROOT).as_posix(): sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def raw_stat_inventory() -> tuple[list[tuple[str, int, int]], str]:
    rows = [
        (path.relative_to(RAW).as_posix(), path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(RAW.rglob("*.dcm"))
    ]
    digest = hashlib.sha256(
        json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    return rows, digest


def json_list(value: str) -> list[str]:
    result = json.loads(value)
    if not isinstance(result, list):
        raise ValueError(f"Expected JSON list: {value}")
    return [str(item) for item in result]


def display_value(value: str) -> str:
    values = [item for item in json_list(value) if item != "<MISSING>"]
    return " | ".join(values) if values else "<MISSING>"


def verify_frozen_inputs(protocol: dict[str, Any]) -> None:
    if protocol["status"] != "FROZEN" or protocol["protocol_id"] != "formal-series-selection-rule-b-v1":
        raise ValueError("Formal Rule B protocol is not frozen as expected")
    if protocol["phase_boundary"]["formal_cohort_finalized"]:
        raise ValueError("Protocol unexpectedly claims a finalized cohort")
    for name, value in protocol["source_analysis"].items():
        if not name.endswith("_sha256"):
            continue
        source_key = name.removesuffix("_sha256")
        path = ROOT / protocol["source_analysis"][source_key]
        if not path.is_file() or sha256(path) != value:
            raise ValueError(f"Frozen source analysis changed: {path}")


def review_question(case_type: str, kernels: set[str]) -> str:
    if case_type == "diagnostic_type_uncertain":
        return (
            "确认这个 ORIGINAL/SECONDARY/AXIAL 的 chest Series 是否属于诊断性胸部 CT，胸部覆盖是否充分，"
            "伪影是否可接受。不能仅凭 SECONDARY 纳入或排除；必须记录可见影像和 metadata 证据。"
        )
    if len(kernels) > 1:
        return (
            "比较技术排名相同的重建（包括 B 与 L）在诊断性胸部 CT 用途、解剖覆盖、噪声、锐度和伪影方面的表现。"
            "如需选择，理由必须引用一个可统一应用于所有患者的影像标准。"
        )
    return (
        "判断两个技术排名相同的 Series 是否重复，或在诊断解剖范围、期相、覆盖、运动或其他伪影方面存在差异。"
        "若现有证据不能支持选择，记录 DEFER 或 EXCLUDE_PATIENT，不能按列表顺序或 UID 选择。"
    )


def build_cases(series: pd.DataFrame, patients: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    patient_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    ties = patients[(patients.rule == "B") & (patients.status == "ranking_tie_review")].sort_values("patient_id")
    if len(ties) != 12:
        raise ValueError(f"Expected 12 Rule B technical ties, found {len(ties)}")
    for index, patient in enumerate(ties.itertuples(), start=1):
        case_id = f"TIE-{index:03d}"
        candidate_uids = json_list(patient.top_tied_series_uids)
        candidates = series[series.series_uid.isin(candidate_uids)].copy()
        if len(candidates) != 2 or set(candidates.series_uid) != set(candidate_uids):
            raise ValueError(f"Tie candidate mismatch: {patient.patient_id}")
        kernels = {display_value(value) for value in candidates.kernels}
        question = review_question("technical_tie", kernels)
        patient_rows.append({
            "case_id": case_id,
            "case_type": "technical_tie",
            "patient_id": patient.patient_id,
            "candidate_series_uids": json.dumps(sorted(candidate_uids)),
            "context_series_uids": "[]",
            "required_judgment": question,
            "allowed_decisions": "SELECT_ONE_CANDIDATE | EXCLUDE_PATIENT | DEFER",
            "status": "PENDING_MANUAL_REVIEW",
        })
        for row in candidates.sort_values("series_uid").to_dict("records"):
            candidate_rows.append(candidate_record(case_id, "technical_tie", "eligible_top_tied", row, question))

    uncertain = series[
        series.review_reasons.map(lambda value: "diagnostic_type_uncertain" in json_list(value))
        & series.hard_status.eq("review")
    ]
    if len(uncertain) != 1:
        raise ValueError(f"Expected one diagnostic_type_uncertain Series, found {len(uncertain)}")
    review_row = uncertain.iloc[0].to_dict()
    patient_id = review_row["patient_id"]
    patient_series = series[series.patient_id.eq(patient_id)]
    bone_context = patient_series[
        patient_series.exclusion_reasons.map(lambda value: "explicit_bone_only" in json_list(value))
    ]
    if len(bone_context) != 1:
        raise ValueError(f"Expected one bone-only context Series for {patient_id}")
    case_id = "DIAG-001"
    question = review_question("diagnostic_type_uncertain", set())
    patient_rows.append({
        "case_id": case_id,
        "case_type": "diagnostic_type_uncertain",
        "patient_id": patient_id,
        "candidate_series_uids": json.dumps([review_row["series_uid"]]),
        "context_series_uids": json.dumps([bone_context.iloc[0].series_uid]),
        "required_judgment": question,
        "allowed_decisions": "INCLUDE_REVIEW_SERIES | EXCLUDE_PATIENT | DEFER",
        "status": "PENDING_MANUAL_REVIEW",
    })
    candidate_rows.append(candidate_record(case_id, "diagnostic_type_uncertain", "review_candidate", review_row, question))
    candidate_rows.append(candidate_record(
        case_id,
        "diagnostic_type_uncertain",
        "excluded_bone_only_context",
        bone_context.iloc[0].to_dict(),
        "仅作对照：该明确 bone-only 重建继续由冻结的硬规则排除，不能成为候选。",
    ))
    return patient_rows, candidate_rows


def candidate_record(
    case_id: str,
    case_type: str,
    candidate_role: str,
    row: dict[str, Any],
    question: str,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "case_type": case_type,
        "patient_id": row["patient_id"],
        "candidate_role": candidate_role,
        "series_uid": row["series_uid"],
        "study_uid": row["study_uid"],
        "series_description": display_value(row["descriptions"]),
        "convolution_kernel": display_value(row["kernels"]),
        "slice_thickness_mm": float(row["thickness_max"]),
        "pixel_spacing_row_mm": float(row["spacing_row"]),
        "pixel_spacing_column_mm": float(row["spacing_column"]),
        "coverage_mm": float(row["coverage_mm"]),
        "slice_count": int(row["slice_count"]),
        "image_types": " | ".join(json_list(row["image_types"])),
        "hard_status_before_review": row["hard_status"],
        "review_question": question,
        "montage_path": "",
    }


def locate_series(target_uids: set[str]) -> dict[str, list[Path]]:
    located: dict[str, list[Path]] = {}
    for directory in sorted({path.parent for path in RAW.rglob("*.dcm")}):
        files = sorted(directory.glob("*.dcm"))
        ds = pydicom.dcmread(files[0], stop_before_pixels=True, specific_tags=["SeriesInstanceUID"])
        uid = str(ds.SeriesInstanceUID)
        if uid in target_uids:
            if uid in located:
                raise ValueError(f"Series UID occurs in multiple directories: {uid}")
            located[uid] = files
    if set(located) != target_uids:
        raise ValueError(f"Could not locate Series: {sorted(target_uids - set(located))}")
    return located


def sorted_slice_headers(paths: list[Path]) -> list[tuple[float, int, str, Path]]:
    result = []
    for path in paths:
        ds = pydicom.dcmread(
            path,
            stop_before_pixels=True,
            specific_tags=[
                "ImageOrientationPatient",
                "ImagePositionPatient",
                "InstanceNumber",
                "SOPInstanceUID",
            ],
        )
        orientation = np.asarray(ds.ImageOrientationPatient, dtype=float)
        position = np.asarray(ds.ImagePositionPatient, dtype=float)
        if orientation.shape != (6,) or position.shape != (3,):
            raise ValueError(f"Invalid geometry in review candidate: {path}")
        normal = np.cross(orientation[:3], orientation[3:])
        normal /= np.linalg.norm(normal)
        projection = float(np.dot(position, normal))
        instance = int(getattr(ds, "InstanceNumber", 0) or 0)
        result.append((projection, instance, str(ds.SOPInstanceUID), path))
    return sorted(result, key=lambda item: (item[0], item[1], item[2]))


def representative_slices(paths: list[Path]) -> list[tuple[float, int, str, Path]]:
    ordered = sorted_slice_headers(paths)
    by_position: dict[float, tuple[float, int, str, Path]] = {}
    for item in ordered:
        by_position.setdefault(round(item[0], 3), item)
    unique = [by_position[key] for key in sorted(by_position)]
    if len(unique) < 3:
        raise ValueError("Review montage requires at least three unique spatial positions")
    indices = [round(fraction * (len(unique) - 1)) for fraction in FRACTIONS]
    return [unique[index] for index in indices]


def lung_window(ds: pydicom.Dataset) -> np.ndarray:
    pixels = ds.pixel_array.astype(np.float32)
    if pixels.ndim != 2:
        raise ValueError(f"Expected a single-frame 2D image, got {pixels.shape}")
    slope = float(ds.RescaleSlope)
    intercept = float(ds.RescaleIntercept)
    hu = pixels * slope + intercept
    low = WINDOW_CENTER - WINDOW_WIDTH / 2
    high = WINDOW_CENTER + WINDOW_WIDTH / 2
    image = np.clip((hu - low) / (high - low), 0.0, 1.0)
    if str(ds.PhotometricInterpretation).upper() == "MONOCHROME1":
        image = 1.0 - image
    return image


def montage_filename(case_id: str, series_uid: str, role: str) -> str:
    short = hashlib.sha256(series_uid.encode("ascii")).hexdigest()[:10]
    return f"{case_id.lower()}__{role}__{short}.png"


def render_montage(row: dict[str, Any], paths: list[Path]) -> tuple[str, list[dict[str, Any]]]:
    selected = representative_slices(paths)
    figure, axes = plt.subplots(1, 3, figsize=(12, 4.7), facecolor="#f2f2ef")
    source_rows = []
    for axis, fraction, item in zip(axes, FRACTIONS, selected):
        projection, instance, sop_uid, path = item
        ds = pydicom.dcmread(path)
        axis.imshow(lung_window(ds), cmap="gray", vmin=0, vmax=1)
        axis.set_title(
            f"{int(fraction * 100)}% position\nInstance {instance} | z-proj {projection:.1f} mm",
            fontsize=9,
        )
        axis.axis("off")
        source_rows.append({
            "case_id": row["case_id"],
            "patient_id": row["patient_id"],
            "candidate_role": row["candidate_role"],
            "series_uid": row["series_uid"],
            "fraction": fraction,
            "projection_mm": round(projection, 6),
            "instance_number": instance,
            "sop_uid": sop_uid,
            "source_dicom": path.relative_to(ROOT).as_posix(),
        })
    figure.suptitle(
        f"{row['case_id']} | {row['patient_id']} | REVIEW ONLY - NOT SELECTED",
        fontsize=12,
        fontweight="bold",
        y=0.98,
    )
    uid_text = "\n".join(textwrap.wrap(f"Series UID: {row['series_uid']}", width=105))
    metadata = (
        f"Role: {row['candidate_role']} | Description: {row['series_description']} | "
        f"Kernel: {row['convolution_kernel']} | Thickness: {row['slice_thickness_mm']:g} mm | "
        f"Spacing: {row['pixel_spacing_row_mm']:g} x {row['pixel_spacing_column_mm']:g} mm | "
        f"Coverage: {row['coverage_mm']:g} mm\n{uid_text}\n"
        f"Lung window C={WINDOW_CENTER:g}/W={WINDOW_WIDTH:g}; stored pixel orientation; "
        "three samples do not replace full-series review."
    )
    figure.text(0.02, 0.015, metadata, ha="left", va="bottom", fontsize=7.5)
    figure.tight_layout(rect=(0.0, 0.16, 1.0, 0.92), w_pad=0.4)
    filename = montage_filename(row["case_id"], row["series_uid"], row["candidate_role"])
    path = MONTAGES / filename
    figure.savefig(path, dpi=160, bbox_inches="tight", facecolor=figure.get_facecolor())
    plt.close(figure)
    return path.relative_to(OUT).as_posix(), source_rows


def decision_template(patient_rows: list[dict[str, Any]], protocol_id: str) -> list[dict[str, Any]]:
    decisions = []
    for row in patient_rows:
        decisions.append({
            "protocol_id": protocol_id,
            "case_id": row["case_id"],
            "patient_id": row["patient_id"],
            "case_type": row["case_type"],
            "candidate_series_uids": row["candidate_series_uids"],
            "allowed_decisions": row["allowed_decisions"],
            "decision": "PENDING",
            "selected_series_uid": "",
            "reason": "",
            "reviewer": "",
            "reviewed_at_utc": "",
            "image_evidence_reviewed": "",
            "metadata_evidence_reviewed": "",
            "validation_status": "INCOMPLETE_REASON_REQUIRED",
        })
    return decisions


def markdown_packet(
    protocol: dict[str, Any],
    patient_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> str:
    lines = [
        "# Rule B Series 人工复核包 v1",
        "",
        f"Protocol：`{protocol['protocol_id']}`（FROZEN）。当前状态：未形成最终 cohort；未生成 split；未训练。",
        "",
        "复核者必须查看每个候选的 metadata 和 montage，并在 `manual_review_decisions.csv` 中记录决定、具体理由、复核人和 UTC 时间。Montage 只显示固定肺窗下的 25%/50%/75% 三张切片，应在条件允许时滚动检查完整 Series。",
        "",
        "有效理由应描述诊断用途、胸部解剖覆盖、重建表现、噪声/锐度、运动或其他伪影、重复序列或期相。UID 大小、列表位置、collection、label、随机选择和模型结果都不是有效理由。无法判断时填写 `DEFER`。",
        "",
        "Montage 按 DICOM 中保存的像素方向显示，并非认证诊断工作站。它用于人工筛查 Series 是否适合本研究，不用于临床诊断。",
        "",
    ]
    candidate_frame = pd.DataFrame(candidate_rows)
    for patient in patient_rows:
        lines.extend([
            f"## {patient['case_id']} · {patient['patient_id']}",
            "",
            f"类型：`{patient['case_type']}`  ",
            f"需要判断：{patient['required_judgment']}  ",
            f"允许决定：`{patient['allowed_decisions']}`",
            "",
            "|角色|SeriesDescription|Kernel|Thickness|PixelSpacing|Coverage|Study UID|Series UID|",
            "|---|---|---|---:|---:|---:|---|---|",
        ])
        group = candidate_frame[candidate_frame.case_id.eq(patient["case_id"])]
        for row in group.itertuples():
            lines.append(
                f"|{row.candidate_role}|{row.series_description}|{row.convolution_kernel}|"
                f"{row.slice_thickness_mm:g} mm|{row.pixel_spacing_row_mm:g} × "
                f"{row.pixel_spacing_column_mm:g} mm|{row.coverage_mm:g} mm|"
                f"`{row.study_uid}`|`{row.series_uid}`|"
            )
        lines.append("")
        for row in group.itertuples():
            lines.extend([
                f"### {row.candidate_role} · `{row.series_uid}`",
                "",
                f"![{patient['case_id']} {row.candidate_role}]({row.montage_path})",
                "",
            ])
    lines.extend([
        "## 决策记录约束",
        "",
        "`manual_review_decisions.csv` 初始全部为 `PENDING`。后续校验脚本只接受候选清单中的 UID；选择或排除必须有具体理由并确认已查看图像与 metadata。`DEFER` 会保持 cohort 未决。人工复核结果通过校验后仍需用户显式确认最终 cohort，不能直接进入 split 或训练。",
        "",
    ])
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    frame = pd.DataFrame(rows)
    path.write_text(frame.to_csv(index=False, lineterminator="\n"), encoding="utf-8")


def main() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    verify_frozen_inputs(protocol)
    protocol_digest = sha256(PROTOCOL)
    raw_before, raw_digest_before = raw_stat_inventory()
    splits_before = file_hashes(ROOT / "data/splits")
    experiments_before = file_hashes(ROOT / "outputs/experiments")
    analysis_before = file_hashes(ANALYSIS)

    series = pd.read_csv(ANALYSIS / "series_analysis.csv", dtype=str, keep_default_na=False)
    patients = pd.read_csv(ANALYSIS / "patient_rule_analysis.csv", dtype=str, keep_default_na=False)
    patient_rows, candidate_rows = build_cases(series, patients)
    if len(patient_rows) != 13 or len(candidate_rows) != 26:
        raise ValueError("Unexpected review packet size")

    OUT.mkdir(parents=True, exist_ok=True)
    MONTAGES.mkdir(parents=True, exist_ok=True)
    target_uids = {row["series_uid"] for row in candidate_rows}
    locations = locate_series(target_uids)
    source_rows: list[dict[str, Any]] = []
    for row in candidate_rows:
        montage_path, selected_sources = render_montage(row, locations[row["series_uid"]])
        row["montage_path"] = montage_path
        source_rows.extend(selected_sources)

    expected_montages = {Path(row["montage_path"]).name for row in candidate_rows}
    actual_montages = {path.name for path in MONTAGES.glob("*.png")}
    if actual_montages != expected_montages:
        raise ValueError("Montage directory contains stale or missing files")

    decisions = decision_template(patient_rows, protocol["protocol_id"])
    write_csv(OUT / "manual_review_cases.csv", patient_rows)
    write_csv(OUT / "manual_review_candidates.csv", candidate_rows)
    write_csv(OUT / "manual_review_decisions.csv", decisions)
    write_csv(OUT / "montage_source_manifest.csv", source_rows)
    (OUT / "MANUAL_REVIEW.md").write_text(
        markdown_packet(protocol, patient_rows, candidate_rows), encoding="utf-8"
    )
    (OUT / "formal_protocol.sha256").write_text(
        f"{protocol_digest}  {PROTOCOL.relative_to(ROOT).as_posix()}\n", encoding="ascii"
    )

    raw_after, raw_digest_after = raw_stat_inventory()
    verification = {
        "protocol_id": protocol["protocol_id"],
        "formal_protocol_sha256": protocol_digest,
        "source_analysis_hashes_verified": True,
        "review_patients": len(patient_rows),
        "technical_tie_patients": sum(row["case_type"] == "technical_tie" for row in patient_rows),
        "diagnostic_type_uncertain_patients": sum(
            row["case_type"] == "diagnostic_type_uncertain" for row in patient_rows
        ),
        "eligible_top_tied_series": sum(row["candidate_role"] == "eligible_top_tied" for row in candidate_rows),
        "diagnostic_review_candidates": sum(row["candidate_role"] == "review_candidate" for row in candidate_rows),
        "excluded_context_series": sum(
            row["candidate_role"] == "excluded_bone_only_context" for row in candidate_rows
        ),
        "montages": len(actual_montages),
        "representative_pixel_images_read": len(source_rows),
        "representative_fractions": list(FRACTIONS),
        "window_center_hu": WINDOW_CENTER,
        "window_width_hu": WINDOW_WIDTH,
        "raw_dicom_files": len(raw_after),
        "raw_inventory_stat_sha256_before": raw_digest_before,
        "raw_inventory_stat_sha256_after": raw_digest_after,
        "raw_inventory_unchanged": raw_before == raw_after,
        "existing_split_files_unchanged": splits_before == file_hashes(ROOT / "data/splits"),
        "existing_experiment_files_unchanged": experiments_before == file_hashes(ROOT / "outputs/experiments"),
        "source_analysis_files_unchanged": analysis_before == file_hashes(ANALYSIS),
        "formal_full_split_files_absent": all(
            not (ROOT / "data/splits" / name).exists() for name in FORMAL_SPLIT_NAMES
        ),
        "all_decisions_pending": all(row["decision"] == "PENDING" for row in decisions),
        "formal_cohort_finalized": False,
        "split_created": False,
        "training_started": False,
        "pixel_data_use": "Only 3 representative slices per review Series for local montage generation.",
    }
    if not all(
        verification[key]
        for key in (
            "raw_inventory_unchanged",
            "existing_split_files_unchanged",
            "existing_experiment_files_unchanged",
            "source_analysis_files_unchanged",
            "formal_full_split_files_absent",
            "all_decisions_pending",
        )
    ):
        raise AssertionError("Review packet safety verification failed")
    (OUT / "verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(verification, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
