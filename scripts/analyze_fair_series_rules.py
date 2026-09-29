#!/usr/bin/env python3
"""Compare frozen, label-blind series proposals. Never build a cohort or split."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pydicom

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/full_raw"
OUT = ROOT / "outputs/data/fair_series_rule_analysis_v1"
COLLECTIONS = ("MIDRC-RICORD-1A", "MIDRC-RICORD-1B")
MISSING = "<MISSING>"
TAGS = (
    "PatientID", "StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID",
    "Modality", "ImageType", "SeriesDescription", "SliceThickness",
    "PixelSpacing", "ConvolutionKernel", "ImageOrientationPatient",
    "ImagePositionPatient", "Manufacturer", "ManufacturerModelName",
    "Rows", "Columns", "NumberOfFrames", "PhotometricInterpretation",
    "RescaleSlope", "RescaleIntercept", "BodyPartExamined",
)
PROTOCOL = {
    "version": "fair-series-analysis-v1",
    "purpose": "ANALYSIS ONLY; no approved cohort, split, or model execution",
    "fixed_before_scenario_evaluation": True,
    "axial_normal_tolerance": 0.01,
    "numeric_comparison_rounding_decimals": 6,
    "position_rounding_mm": 0.001,
    "ranking_rounding_mm": 0.001,
    "hard_exclusions": [
        "non_CT", "scout_localizer", "explicit_sagittal_coronal_reformatted",
        "non_axial_geometry", "explicit_bone_only", "non_diagnostic_monitoring",
    ],
    "uncertainty_policy": "Missing/ambiguous diagnostic or geometry evidence -> review; never silently eligible or excluded.",
    "no_kernel_whitelist": True,
    "no_exact_thickness_requirement": True,
    "A": "All hard-pass series; rank by decreasing position span, increasing thickness, increasing maximum PixelSpacing.",
    "B": "All hard-pass series; keep within-patient span >=95% of maximum; rank by increasing thickness, increasing maximum PixelSpacing, decreasing span.",
    "C": "Hard-pass plus thickness <=3 mm and each PixelSpacing <=1 mm; then use B.",
    "B_C_coverage_fraction": 0.95,
    "C_max_thickness_mm": 3.0,
    "C_max_spacing_mm": 1.0,
    "ties": "Equal rounded ranking keys require manual confirmation; no UID, label, collection, random or outcome tie-break.",
    "multiple_studies": "Compare all qualifying series of each patient using the same ranking; no date or phase preference. Report multiple studies for review of index-exam intent.",
    "coverage_limit": "ImagePositionPatient projection span measures extent, not verified anatomical/full-lung coverage.",
    "imbalance_flag": "TVD>=0.25 for categorical fields; two-sample empirical KS distance>=0.25 for numeric fields. Descriptive only, not a significance/fairness test or selection gate.",
    "retention_denominators": {COLLECTIONS[0]: 110, COLLECTIONS[1]: 117},
    "kernel_warning": "B, L, DETAIL and vendor-specific kernels are not automatically bone-only; no cross-vendor equivalence is inferred.",
}


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)


def json_cell(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def normalized(value):
    if value is None or str(value).strip() == "":
        return MISSING
    if isinstance(value, (list, tuple, pydicom.multival.MultiValue)):
        return "|".join(normalized(v) for v in value)
    return str(value).strip()


def vector(value, size):
    try:
        array = np.asarray(value, dtype=float)
        return array if array.shape == (size,) and np.isfinite(array).all() else None
    except (TypeError, ValueError):
        return None


def finite_number(value):
    try:
        number = float(value)
        return round(number, 6) if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def hard_decision(row):
    """Only imaging evidence is used; labels/collection are never inspected."""
    excluded, review = [], []
    types = set(row["image_types"])
    description = " | ".join(row["descriptions"]).upper()
    kernel = " | ".join(row["kernels"]).upper()
    if row["modalities"] != ["CT"]:
        (review if MISSING in row["modalities"] else excluded).append("non_CT_or_missing_modality")
    if re.search(r"SCOUT|LOCALIZER|TOPOGRAM|SURVIEW", description + " | " + "|".join(types)):
        excluded.append("scout_localizer")
    if (types & {"REFORMATTED", "MIP", "MPR"}
            or any("MPR" in t or "MIP" == t for t in types)
            or re.search(r"\b(?:SAG(?:ITTAL)?|COR(?:ONAL)?|REFORMAT\w*|MPR|MIP)\b", description)):
        excluded.append("explicit_sagittal_coronal_reformatted")
    if row["orientation_missing"]:
        review.append("missing_or_invalid_orientation")
    if row["non_axial_slices"]:
        excluded.append("non_axial_geometry")
    if re.search(r"\bBONE\w*\b", kernel) or re.search(r"\bBONE\b", description):
        excluded.append("explicit_bone_only")
    if row["unique_positions"] <= 1 and not row["position_missing"]:
        excluded.append("non_diagnostic_monitoring")
    elif re.search(r"SMART\s*PREP|BOLUS\s*TRACK|MONITOR", description) and row["unique_positions"] <= 3 and row["duplicate_positions"]:
        excluded.append("non_diagnostic_monitoring")
    if "GSI MD" in types or "IODINE(WATER)" in description:
        review.append("material_map_diagnostic_use_uncertain")
    if not row["all_original_primary"]:
        review.append("diagnostic_type_uncertain")
    if row["position_missing"]:
        review.append("missing_or_invalid_position")
    if row["duplicate_positions"]:
        review.append("duplicate_spatial_positions")
    if row["variable_orientation"]:
        review.append("variable_axial_orientation")
    if row["invalid_thickness"] or row["invalid_spacing"]:
        review.append("missing_or_invalid_resolution")
    if row["variable_resolution"]:
        review.append("within_series_resolution_variation")
    if row["multiframe"]:
        review.append("enhanced_multiframe_requires_frame_audit")
    if row["dimensions_invalid_or_variable"]:
        review.append("dimensions_invalid_or_variable")
    if row["photometric"] != ["MONOCHROME2"] or row["invalid_rescale"]:
        review.append("pixel_interpretation_requires_review")
    return ("excluded" if excluded else "review" if review else "eligible",
            sorted(set(excluded)), sorted(set(review)))


def scan():
    grouped = defaultdict(list)
    inventory = []
    for path in sorted(RAW.rglob("*")):
        if path.is_file():
            stat = path.stat()
            inventory.append((str(path.relative_to(RAW)), stat.st_size, stat.st_mtime_ns))
            if path.suffix.lower() == ".dcm":
                grouped[path.parent].append(path)
    rows, details, seen_sop, seen_series, identities = [], {}, set(), set(), defaultdict(set)
    processed = 0
    for directory, paths in sorted(grouped.items()):
        values = defaultdict(Counter)
        positions, orientations, thicknesses, spacings = [], [], [], []
        flags = Counter()
        all_original_primary = True
        dimensions = set()
        for path in paths:
            ds = pydicom.dcmread(path, stop_before_pixels=True, force=False)
            for tag in TAGS:
                values[tag][normalized(getattr(ds, tag, None))] += 1
            sop = normalized(getattr(ds, "SOPInstanceUID", None))
            if sop == MISSING or sop in seen_sop:
                raise ValueError(f"Missing/duplicate SOP UID in {path}")
            seen_sop.add(sop)
            types = set(normalized(getattr(ds, "ImageType", None)).upper().split("|"))
            all_original_primary &= {"ORIGINAL", "PRIMARY"}.issubset(types)
            orientation = vector(getattr(ds, "ImageOrientationPatient", None), 6)
            if orientation is None:
                flags["orientation_missing"] += 1
            else:
                normal = np.cross(orientation[:3], orientation[3:])
                valid_basis = (np.isclose(np.linalg.norm(orientation[:3]), 1, atol=.01)
                               and np.isclose(np.linalg.norm(orientation[3:]), 1, atol=.01)
                               and abs(np.dot(orientation[:3], orientation[3:])) <= .01)
                if not valid_basis:
                    flags["orientation_missing"] += 1
                elif not np.allclose(abs(normal), [0, 0, 1], atol=.01, rtol=0):
                    flags["non_axial_slices"] += 1
                orientations.append(orientation)
            position = vector(getattr(ds, "ImagePositionPatient", None), 3)
            if position is None:
                flags["position_missing"] += 1
            else:
                positions.append(position)
            thickness = finite_number(getattr(ds, "SliceThickness", None))
            if thickness is None or thickness <= 0:
                flags["invalid_thickness"] += 1
            else:
                thicknesses.append(thickness)
            spacing = vector(getattr(ds, "PixelSpacing", None), 2)
            if spacing is None or (spacing <= 0).any():
                flags["invalid_spacing"] += 1
            else:
                spacings.append(tuple(round(float(v), 6) for v in spacing))
            dims = (finite_number(getattr(ds, "Rows", None)), finite_number(getattr(ds, "Columns", None)))
            dimensions.add(dims)
            flags["bad_dimensions"] += any(v is None or v <= 1 for v in dims)
            frames = finite_number(getattr(ds, "NumberOfFrames", 1))
            flags["multiframe"] += frames is None or frames != 1
            slope = finite_number(getattr(ds, "RescaleSlope", None))
            intercept = finite_number(getattr(ds, "RescaleIntercept", None))
            flags["invalid_rescale"] += slope is None or slope <= 0 or intercept is None
        processed += len(paths)
        if not rows or processed // 10000 != (processed - len(paths)) // 10000:
            print(f"Header audit: {processed}/53076", flush=True)
        identity = {}
        for key in ("PatientID", "StudyInstanceUID", "SeriesInstanceUID"):
            if len(values[key]) != 1 or MISSING in values[key]:
                raise ValueError(f"Conflicting or absent {key}: {directory}")
            identity[key] = next(iter(values[key]))
        collection_dir = directory.relative_to(RAW).parts[0]
        if collection_dir not in ("midrc_ricord_1a", "midrc_ricord_1b"):
            raise ValueError("Unexpected collection directory")
        collection = COLLECTIONS[0] if collection_dir.endswith("1a") else COLLECTIONS[1]
        if not identity["PatientID"].startswith(collection + "-"):
            raise ValueError("Path/header collection disagreement")
        uid = identity["SeriesInstanceUID"]
        if uid in seen_series:
            raise ValueError("Series spans multiple directories")
        seen_series.add(uid)
        identities[identity["PatientID"]].add(collection)
        normal = np.cross(orientations[0][:3], orientations[0][3:]) if orientations else np.array([0., 0., 1.])
        norm = np.linalg.norm(normal)
        if norm:
            normal /= norm
        projection = [round(float(np.dot(p, normal)), 3) for p in positions]
        unique = sorted(set(projection))
        span = round(max(unique) - min(unique), 3) if unique else None
        row = {
            "collection": collection, "patient_id": identity["PatientID"],
            "study_uid": identity["StudyInstanceUID"], "series_uid": uid,
            "slice_count": len(paths),
            "modalities": sorted(values["Modality"]),
            "image_types": sorted({t.upper() for v in values["ImageType"] for t in v.split("|")}),
            "descriptions": sorted(values["SeriesDescription"]),
            "kernels": sorted(values["ConvolutionKernel"]),
            "manufacturer": sorted(values["Manufacturer"]),
            "manufacturer_model": sorted(values["ManufacturerModelName"]),
            "photometric": sorted(values["PhotometricInterpretation"]),
            "all_original_primary": bool(all_original_primary),
            "thickness_min": min(thicknesses) if thicknesses else None,
            "thickness_max": max(thicknesses) if thicknesses else None,
            "spacing_row": max(s[0] for s in spacings) if spacings else None,
            "spacing_column": max(s[1] for s in spacings) if spacings else None,
            "spacing_max": max(max(s) for s in spacings) if spacings else None,
            "coverage_mm": span,
            "unique_positions": len(unique), "duplicate_positions": len(projection) - len(unique),
            "variable_orientation": bool(any(not np.allclose(o, orientations[0], atol=1e-4, rtol=0) for o in orientations)),
            "variable_resolution": len(set(thicknesses)) > 1 or len(set(spacings)) > 1,
            "dimensions_invalid_or_variable": bool(flags["bad_dimensions"] or len(dimensions) != 1),
        }
        for flag in ("orientation_missing", "non_axial_slices", "position_missing", "invalid_thickness", "invalid_spacing", "multiframe", "invalid_rescale"):
            row[flag] = flags[flag]
        status, exclusion, review = hard_decision(row)
        row.update(hard_status=status, exclusion_reasons=exclusion, review_reasons=review)
        row["extent_review_note"] = "extent_does_not_confirm_anatomy" if span is not None and (span < 150 or span > 450) else ""
        rows.append(row)
        details[uid] = {tag: dict(counter) for tag, counter in sorted(values.items())}
    if processed != 53076 or len(rows) != 349 or len(identities) != 227 or any(len(v) != 1 for v in identities.values()):
        raise ValueError("Full-download inventory/identity counts differ")
    return rows, details, inventory


def rule_pool(rows, rule):
    eligible = [r for r in rows if r["hard_status"] == "eligible"]
    if rule == "C":
        eligible = [r for r in eligible if r["thickness_max"] <= 3 and r["spacing_max"] <= 1]
    return eligible


def rank_candidates(pool, rule):
    """No collection, patient ID, UID or label values affect ranking."""
    if not pool:
        return [], []
    contenders = pool
    if rule in ("B", "C"):
        largest = max(r["coverage_mm"] for r in pool)
        contenders = [r for r in pool if r["coverage_mm"] + 1e-6 >= .95 * largest]
    def key(row):
        extent = round(row["coverage_mm"], 3)
        thickness = round(row["thickness_max"], 3)
        spacing = round(row["spacing_max"], 3)
        return (-extent, thickness, spacing) if rule == "A" else (thickness, spacing, -extent)
    best = min(key(r) for r in contenders)
    return [r for r in contenders if key(r) == best], contenders


def describe(values):
    present = [float(v) for v in values if v is not None]
    if not present:
        return {"n": 0, "missing": len(values)}
    q = np.percentile(present, [0, 25, 50, 75, 100])
    return {"n": len(present), "missing": len(values) - len(present),
            **{k: round(float(v), 6) for k, v in zip(("min", "q25", "median", "q75", "max"), q)}}


NUMERIC = ("thickness_max", "spacing_row", "spacing_column", "slice_count", "coverage_mm")
CATEGORICAL = ("kernels", "descriptions", "manufacturer", "manufacturer_model")


def tvd(a, b):
    if not a or not b:
        return None
    ca, cb = Counter(a), Counter(b)
    return .5 * sum(abs(ca[k] / len(a) - cb[k] / len(b)) for k in ca.keys() | cb.keys())


def ks(a, b):
    a, b = sorted(v for v in a if v is not None), sorted(v for v in b if v is not None)
    if not a or not b:
        return None
    values = sorted(set(a + b))
    return float(np.max(abs(np.searchsorted(a, values, side="right") / len(a)
                            - np.searchsorted(b, values, side="right") / len(b))))


def compare(rows):
    groups = [[r for r in rows if r["collection"] == c] for c in COLLECTIONS]
    metrics = {}
    for field in NUMERIC + CATEGORICAL:
        values = [[json_cell(r[field]) if field in CATEGORICAL else r[field] for r in g] for g in groups]
        distance = tvd(*values) if field in CATEGORICAL else ks(*values)
        metrics[field] = {"method": "TVD" if field in CATEGORICAL else "KS_distance",
                          "distance": round(distance, 6) if distance is not None else None,
                          "flag_ge_0.25": bool(distance is not None and distance >= .25)}
    return metrics


def overlap(rows):
    groups = [[r for r in rows if r["collection"] == c] for c in COLLECTIONS]
    result = {}
    for field in NUMERIC:
        sets = [set(r[field] for r in g if r[field] is not None) for g in groups]
        if not all(sets):
            result[field] = {"shared_values": [], "range_intersection": None}
            continue
        lo, hi = max(min(s) for s in sets), min(max(s) for s in sets)
        result[field] = {
            "range_by_collection": {c: [min(s), max(s)] for c, s in zip(COLLECTIONS, sets)},
            "range_intersection": [lo, hi] if lo <= hi else None,
            "shared_values": sorted(sets[0] & sets[1]),
            "KS_distance": ks(*[list(r[field] for r in g) for g in groups]),
            "note": "Envelope overlap does not imply similar density or joint parameter support.",
        }
    for field in CATEGORICAL:
        sets = [{v for r in g for v in r[field] if v != MISSING} for g in groups]
        result[field] = {"shared_values": sorted(sets[0] & sets[1]),
                         "only_1a": sorted(sets[0] - sets[1]), "only_1b": sorted(sets[1] - sets[0])}
    # Joint support reports observed thickness + spacing pairs, not Cartesian products.
    joint = [Counter((r["thickness_max"], r["spacing_row"], r["spacing_column"]) for r in g) for g in groups]
    result["joint_thickness_spacing_support"] = [
        {"thickness_mm": k[0], "row_mm": k[1], "column_mm": k[2], "series_1a": joint[0][k], "series_1b": joint[1][k]}
        for k in sorted(joint[0].keys() & joint[1].keys(), key=str)
    ]
    return result


def distributions(rows, population):
    records, summary = [], {}
    for collection in COLLECTIONS:
        group = [r for r in rows if r["collection"] == collection]
        summary[collection] = {field: describe([r[field] for r in group]) for field in NUMERIC}
        for field in NUMERIC + CATEGORICAL:
            counts = Counter(json_cell(r[field]) if isinstance(r[field], list) else str(r[field]) for r in group)
            for value, count in sorted(counts.items()):
                records.append({"population": population, "weighting": "one_series_one_vote", "collection": collection,
                                "field": field, "value": value, "count": count,
                                "denominator": len(group), "fraction": count / len(group)})
    return records, summary


def patient_scenarios(rows):
    patients = defaultdict(list)
    for row in rows:
        patients[row["patient_id"]].append(row)
    records, memberships, summaries, chosen_by_rule = [], [], {}, {}
    for rule in ("A", "B", "C"):
        chosen, rule_records = [], []
        for patient_id, group in sorted(patients.items()):
            pool = rule_pool(group, rule)
            best, contenders = rank_candidates(pool, rule)
            chosen.extend(best if len(best) == 1 else [])
            row = {
                "rule": rule, "collection": group[0]["collection"], "patient_id": patient_id,
                "all_series_count": len(group),
                "hard_eligible_count": sum(r["hard_status"] == "eligible" for r in group),
                "hard_review_count": sum(r["hard_status"] == "review" for r in group),
                "rule_eligible_count": len(pool), "contender_count": len(contenders),
                "rule_eligible_study_count": len({r["study_uid"] for r in pool}),
                "candidate_series_uids": [r["series_uid"] for r in pool],
                "top_tied_series_uids": [r["series_uid"] for r in best] if len(best) > 1 else [],
                "proposed_series_uid": best[0]["series_uid"] if len(best) == 1 else "",
                "status": "proposed_only" if len(best) == 1 else "ranking_tie_review" if best else "no_auto_eligible_series",
                "no_selection_reasons": [],
            }
            if not pool:
                row["no_selection_reasons"] = sorted({
                    reason for r in group for reason in (r["exclusion_reasons"] if r["hard_status"] == "excluded" else r["review_reasons"])
                } | ({"C_resolution_upper_bound"} if rule == "C" and row["hard_eligible_count"] else set()))
            elif len(best) > 1:
                row["no_selection_reasons"] = ["equal_technical_ranking_requires_confirmation"]
            rule_records.append(row)
            pool_uids, contender_uids, best_uids = [{r["series_uid"] for r in g} for g in (pool, contenders, best)]
            for r in group:
                reasons = list(r["exclusion_reasons"] + r["review_reasons"])
                if rule == "C" and r["hard_status"] == "eligible":
                    if r["thickness_max"] > 3: reasons.append("C_thickness_gt_3mm")
                    if r["spacing_max"] > 1: reasons.append("C_pixel_spacing_gt_1mm")
                if r["series_uid"] in pool_uids and r["series_uid"] not in contender_uids:
                    reasons.append("coverage_below_95pct_of_patient_maximum")
                elif r["series_uid"] in contender_uids and r["series_uid"] not in best_uids:
                    reasons.append("lower_technical_priority")
                memberships.append({"rule": rule, "collection": r["collection"], "patient_id": patient_id,
                                    "series_uid": r["series_uid"], "hard_status": r["hard_status"],
                                    "rule_eligible": r["series_uid"] in pool_uids,
                                    "proposed_only": len(best) == 1 and r["series_uid"] in best_uids,
                                    "reasons": reasons})
        records.extend(rule_records)
        by_collection = {}
        for collection in COLLECTIONS:
            pr = [r for r in rule_records if r["collection"] == collection]
            sr = [r for r in chosen if r["collection"] == collection]
            by_collection[collection] = {
                "all_patients": len(pr), "rule_eligible_patients": sum(r["rule_eligible_count"] > 0 for r in pr),
                "eligible_patient_retention_rate": sum(r["rule_eligible_count"] > 0 for r in pr) / len(pr),
                "proposed_retained_patients": len(sr), "retention_rate": len(sr) / len(pr),
                "multi_series_patients_before_ranking": sum(r["rule_eligible_count"] > 1 for r in pr),
                "multi_study_patients": sum(r["rule_eligible_study_count"] > 1 for r in pr),
                "ranking_tie_review_patients": sum(r["status"] == "ranking_tie_review" for r in pr),
                "no_auto_eligible_patients": sum(r["rule_eligible_count"] == 0 for r in pr),
                "review_only_patients": sum(r["rule_eligible_count"] == 0 and r["hard_review_count"] > 0 for r in pr),
                "proposed_series": len(sr), "proposed_slices": sum(r["slice_count"] for r in sr),
                "unselected_patient_reasons_nonexclusive": dict(Counter(reason for r in pr for reason in r["no_selection_reasons"])),
            }
        summaries[rule] = {"by_collection": by_collection,
                           "rule_eligible_total_patients": sum(d["rule_eligible_patients"] for d in by_collection.values()),
                           "eligible_retention_rate_gap": abs(by_collection[COLLECTIONS[0]]["eligible_patient_retention_rate"] - by_collection[COLLECTIONS[1]]["eligible_patient_retention_rate"]),
                           "proposed_total_patients": len(chosen),
                           "retention_rate_gap": abs(by_collection[COLLECTIONS[0]]["retention_rate"] - by_collection[COLLECTIONS[1]]["retention_rate"]),
                           "selected_metadata_comparison_patient_weighted": compare(chosen)}
        chosen_by_rule[rule] = chosen
    return records, memberships, summaries, chosen_by_rule


def tied_completion_sensitivity(rows, patient_records, chosen):
    """Enumerate metadata possibilities without selecting any tied series.

    Deduplicate equal field values at each tie to avoid enumerating redundant
    combinations. This does not score or adopt a completion.
    """
    by_uid = {r["series_uid"]: r for r in rows}
    report = {}
    for rule in ("A", "B", "C"):
        ties = [p for p in patient_records if p["rule"] == rule and p["status"] == "ranking_tie_review"]
        metrics = {}
        for field in NUMERIC + CATEGORICAL:
            value = lambda r: json_cell(r[field]) if field in CATEGORICAL else r[field]
            fixed = {c: [value(r) for r in chosen[rule] if r["collection"] == c] for c in COLLECTIONS}
            options = [sorted({value(by_uid[uid]) for uid in p["top_tied_series_uids"]}) for p in ties]
            permutations = math.prod(len(o) for o in options)
            if permutations > 65536:
                metrics[field] = {"status": "not_enumerated_too_many_combinations"}
                continue
            distances = []
            for combination in itertools.product(*options):
                groups = {c: list(v) for c, v in fixed.items()}
                for p, item in zip(ties, combination):
                    groups[p["collection"]].append(item)
                distances.append((tvd if field in CATEGORICAL else ks)(groups[COLLECTIONS[0]], groups[COLLECTIONS[1]]))
            metrics[field] = {"min_distance": round(min(distances), 6), "max_distance": round(max(distances), 6),
                              "distinct_field_completions": permutations, "all_completions_flag_ge_0.25": min(distances) >= .25}
        report[rule] = {"tied_patients": len(ties), "completion_patient_count": len(chosen[rule]) + len(ties),
                        "assumption": "One currently eligible top-ranked series per tied patient; no choice adopted.", "metrics": metrics}
    return report


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected_files():
    return {str(p.relative_to(ROOT)): sha(p)
            for base in (ROOT / "data/splits", ROOT / "outputs/experiments", ROOT / "configs")
            for p in base.rglob("*") if p.is_file()} | {
        str(p.relative_to(ROOT)): sha(p) for p in (ROOT / "outputs/data").glob("*") if p.is_file()
    }


def write_csv(name, rows):
    serial = [{k: json_cell(v) if isinstance(v, (dict, list)) else v for k, v in r.items()} for r in rows]
    (OUT / name).write_text(pd.DataFrame(serial).to_csv(index=False, lineterminator="\n"), encoding="utf-8")


def markdown_report(summary, rows, scenarios):
    lines = ["# 公平 Series 选择规则分析 v1", "",
             "状态：仅方案分析，未批准最终 cohort；未生成 split、未启动训练。", "",
             "本报告重新扫描全部 53,076 个 Header（stop_before_pixels=True），以所有 110 位 1A、117 位 1B 患者为保留率分母。旧 STANDARD/1.25 mm 条件不参与本轮规则。",
             "", "## 硬条件与不确定性", "",
             "CT、有效轴位几何、诊断序列；排除明确 Scout/Localizer、sagittal/coronal/reformatted/MPR/MIP、明确 BONE/bone-only，以及空间位置不变的监测序列。",
             "缺失几何、诊断类型不明确、碘材料图、重复位置等列入人工复核，不冒充已通过，也不直接当作不合格。ORIGINAL/PRIMARY 在这里是自动确认诊断类型的证据；不满足时只进入复核，除非另有明确硬排除证据。B、L、DETAIL 等厂商核不凭名字猜测骨算法；核名称相同不证明跨厂商重建效果等价。",
             "只读 Header 不能证明全肺覆盖、临床图像质量或正确增强期相；当前 eligible 是技术候选状态。", "",
             "|集合|全部患者|硬条件自动候选患者|候选 Series|明确排除 Series|待核实 Series|零候选患者|多候选患者|",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for c, d in summary["hard_pool"].items():
        lines.append(f"|{c}|{d['all_patients']}|{d['eligible_patients']}|{d['eligible_series']}|{d['excluded_series']}|{d['review_series']}|{d['zero_eligible_patients']}|{d['multi_eligible_patients']}|")
    lines += ["", "上一轮 189/233 没有作为固定分母沿用；本轮新增明确 bone-only 排除，并核对诊断/监测用途。逐 Series 状态、全部原因和与旧结果的对应见 series_analysis.csv；每位患者（包含零候选）的候选列表见 patient_rule_analysis.csv。", "", "## 三套待确认方案", "",
              "A：所有硬条件通过者中，纵向覆盖最大优先；再依次比较层厚较小、最大 PixelSpacing 较小。",
              "B：所有硬条件通过者中，先取覆盖 ≥该患者最大覆盖 95% 的候选，再依次比较层厚较小、最大 PixelSpacing 较小、覆盖较大。",
              "C：增加层厚 ≤3 mm、行列 PixelSpacing 均 ≤1 mm 的统一上限，再执行 B。95%、3 mm、1 mm 均在计算方案结果前固定，仅为本轮待评估的工程参数，未按保留人数或模型效果调参。",
              "覆盖使用 ImagePositionPatient 在序列法向上的最大投影差；不使用切片数量代替覆盖。排序数值统一到 0.001 mm；技术键完全相同则人工确认，不按 UID、标签、collection 或随机数选择。多个 Study 也按同一规则比较，需明确这代表患者内最大覆盖/分辨率偏好，而非首次检查或特定期相；如研究要求 index exam，应在正式选择前另行确认。",
              "", "|方案|可唯一定序患者|1A|1B|1A 唯一定序比例|1B 唯一定序比例|差值 pp|多 Series 患者（排名前）|排名后待确认|可唯一定序 Series/Slices|",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for rule, s in scenarios.items():
        a, b = [s["by_collection"][c] for c in COLLECTIONS]
        lines.append(f"|{rule}|{s['proposed_total_patients']}|{a['proposed_retained_patients']}|{b['proposed_retained_patients']}|{a['retention_rate']:.2%}|{b['retention_rate']:.2%}|{100*s['retention_rate_gap']:.2f}|{a['multi_series_patients_before_ranking']+b['multi_series_patients_before_ranking']}|{a['ranking_tie_review_patients']+b['ranking_tie_review_patients']}|{s['proposed_total_patients']}/{a['proposed_slices']+b['proposed_slices']}|")
    lines += ["", "表内人数仅指可唯一定序者，不是最终保留人数。排名平局患者仍然 eligible，不能因为未确认 Series 就当作被排除。多 Series 数量在确定性排序前统计；待核实但无自动候选的患者另计，不与平局混用。",
              "", "|方案|有合格候选的患者总数|1A|1B|1A 保留率|1B 保留率|保留率差 pp|", "|---|---:|---:|---:|---:|---:|---:|"]
    for rule, s in scenarios.items():
        a, b = [s["by_collection"][c] for c in COLLECTIONS]
        lines.append(f"|{rule}|{s['rule_eligible_total_patients']}|{a['rule_eligible_patients']}|{b['rule_eligible_patients']}|{a['eligible_patient_retention_rate']:.2%}|{b['eligible_patient_retention_rate']:.2%}|{100*s['eligible_retention_rate_gap']:.2f}|")
    lines += ["", "若完成所有当前 eligible 平局的确认，每套方案可覆盖上述患者；实际最终名单仍待用户确认。不能把仅看可唯一定序者的较小差值当作公平性改善。三套方案当前唯一定序 Series 完全相同，C 只减少一个未被选中的 5 mm 候选，没有因此额外排除患者；没有为了产生不同结果调整阈值。",
              "", "## 各方案排除与待确认", ""]
    for rule, s in scenarios.items():
        lines += [f"### 方案 {rule}", ""]
        for c, d in s["by_collection"].items():
            lines += [f"- {c}：无自动候选 {d['no_auto_eligible_patients']}，其中仍有待核实 Series 的患者 {d['review_only_patients']}；排名平局 {d['ranking_tie_review_patients']}；跨多个合格 Study {d['multi_study_patients']}。未选患者原因（非互斥）：`{json_cell(d['unselected_patient_reasons_nonexclusive'])}`。"]
        lines.append("")
    lines += ["共 38 位患者（1A 13、1B 25）的所有 Series 都触发明确硬排除；另 1 位 1A 患者没有自动候选、仍有诊断类型待核实的 Series。该患者原先被纳入的 bone-only Series 本轮被排除，解释了旧核心 189 到当前 188 的变化。其余 3 个待核实 Series 有其他合格候选可供分析。",
              "12 位平局患者全部在 1A：11 位为同等覆盖/层厚/间距的 Philips B 与 L，另 1 位为两个同等指标的 B Series。平局不能按 collection 偏好选 B 或 L；须确认一种统一的核语义偏好或逐例诊断用途。patient_rule_analysis.csv 列出了完整 UID。", ""]
    lines += ["", "## 两组分布与重叠", "",
              "descriptive_statistics.csv 给出全部 Series、硬条件候选和各方案一患者一 Series 的 min/Q1/median/Q3/max；metadata_distributions.csv 保存完整取值频数。患者候选数量分布包含全部 227 位患者及零值，见 patient_candidate_counts.csv。",
              "", "|硬条件候选字段|1A 范围|1B 范围|范围交集|", "|---|---|---|---|"]
    for field in NUMERIC:
        o = summary["overlap_hard_eligible"][field]
        ranges = o.get("range_by_collection", {})
        lines.append(f"|{field}|{ranges.get(COLLECTIONS[0])}|{ranges.get(COLLECTIONS[1])}|{o['range_intersection']}|")
    lines += ["", f"共同核名称：`{json_cell(summary['overlap_hard_eligible']['kernels']['shared_values'])}`。",
              f"共同 SeriesDescription（排除缺失值）：`{json_cell(summary['overlap_hard_eligible']['descriptions']['shared_values'])}`。",
              f"共同层厚观测值：`{json_cell(summary['overlap_hard_eligible']['thickness_max']['shared_values'])}`。",
              "共同 PixelSpacing 精确值及层厚×行距×列距的联合重叠见 analysis.json。数值统一六位小数以消除浮点表示噪声；最小—最大交集仅是外包范围，不等于范围内都有两组样本，更不证明联合分布相同。", "", "## 选择后仍有的分布不平衡", "",
              "各方案选中一位患者的一个 Series，因此下表为患者等权比较。数值字段用两样本经验 CDF 的最大差（KS 距离）；分类字段用 TVD。距离 ≥0.25 仅为本轮描述性提醒，未做显著性推断，也不作为自动拒绝/接受 cohort 的公平性闸门。SeriesDescription 高基数和缺失、厂家字段缺失会限制解释。",
              "", "|字段/距离|A|B|C|", "|---|---:|---:|---:|"]
    for field in NUMERIC + CATEGORICAL:
        cells = []
        for rule in ("A", "B", "C"):
            metric = scenarios[rule]["selected_metadata_comparison_patient_weighted"][field]
            cells.append("无法比较" if metric["distance"] is None else f"{metric['distance']:.3f}" + ("（明显）" if metric['flag_ge_0.25'] else ""))
        lines.append(f"|{field}|{'|'.join(cells)}|")
    lines += ["", "上述距离只覆盖 176 位可唯一定序者，遗漏的 12 位全部来自 1A，因此不是完整 eligible cohort 的最终差异。为避免把排除平局造成的表面平衡当成结论，下面枚举这些技术平局在各字段上的所有不同补全值，仅给距离范围，不采用任何补全方案。",
              "", "|字段|补齐 188 位后的距离范围（A/B/C 均相同）|", "|---|---:|"]
    for field, values in summary["tied_completion_sensitivity"]["A"]["metrics"].items():
        lines.append(f"|{field}|{values['min_distance']:.3f}–{values['max_distance']:.3f}|")
    lines += ["", "较接近的患者保留率不等于扫描协议、来源站点或期相已平衡；无法从缺失 Manufacturer 推断设备相同，也不能把缺失 ContrastBolusAgent 当成非增强。没有以 metadata 分数或保留人数自动选赢家。",
              "", "## 复现与停止状态", "",
              "运行 `.venv/bin/python scripts/analyze_fair_series_rules.py`。protocol.json 保存冻结参数；analysis.json 保存完整统计、重叠和校验；scenario_series_analysis.csv 保存每套规则逐 Series 的排除或低优先级原因。所有带 proposed 的结果仅用于方案比较，未写正式 selected_manifest 或 full split。",
              "源 DICOM 只读；全量路径/大小/mtime 清单前后匹配，未执行像素读取；旧审计、DEV split、配置和实验文件 SHA-256 前后一致（详见 verification）。原始文件未做逐字节重新哈希，不把 stat 一致冒充内容哈希验证。",
              "本轮到此停止，等待用户确认最终规则；确认一套 Series 方案并不自动授权 split 或训练。", ""]
    return "\n".join(lines)


def main():
    protected_before = protected_files()
    OUT.mkdir(parents=True, exist_ok=True)
    frozen = dumps(PROTOCOL)
    protocol_path = OUT / "protocol.json"
    if protocol_path.exists() and protocol_path.read_text(encoding="utf-8") != frozen:
        raise ValueError("Existing protocol differs; use a new analysis version")
    protocol_path.write_text(frozen, encoding="utf-8")
    rows, details, inventory = scan()
    old = pd.read_csv(ROOT / "outputs/data/full_series_summary.csv", keep_default_na=False).set_index("series_uid")
    for row in rows:
        row["previous_core_eligible"] = bool(old.loc[row["series_uid"], "core_axial_diagnostic_eligible"])
    patient_records, memberships, scenarios, chosen = patient_scenarios(rows)
    hard = [r for r in rows if r["hard_status"] == "eligible"]
    hard_summary, candidate_counts = {}, []
    for c in COLLECTIONS:
        group = [r for r in rows if r["collection"] == c]
        counts = Counter(r["patient_id"] for r in group if r["hard_status"] == "eligible")
        all_patients = {r["patient_id"] for r in group}
        histogram = Counter(counts[p] for p in all_patients)
        for number, count in sorted(histogram.items()):
            candidate_counts.append({"population": "hard_eligible", "collection": c, "eligible_series_per_patient": number,
                                     "patients": count, "denominator": len(all_patients), "fraction": count / len(all_patients)})
        hard_summary[c] = {
            "all_patients": len(all_patients), "eligible_patients": len(counts),
            "eligible_series": sum(r["hard_status"] == "eligible" for r in group),
            "excluded_series": sum(r["hard_status"] == "excluded" for r in group),
            "review_series": sum(r["hard_status"] == "review" for r in group),
            "zero_eligible_patients": histogram[0], "multi_eligible_patients": sum(v for k, v in histogram.items() if k > 1),
            "exclusion_reasons_nonexclusive": dict(Counter(reason for r in group for reason in r["exclusion_reasons"])),
            "review_reasons_on_nonexcluded_series": dict(Counter(reason for r in group if r["hard_status"] == "review" for reason in r["review_reasons"])),
        }
    distribution_rows, descriptives = [], []
    for population, population_rows in [("all_series", rows), ("hard_eligible", hard), *[(f"proposal_{k}", v) for k, v in chosen.items()]]:
        dist, stats = distributions(population_rows, population)
        distribution_rows.extend(dist)
        for c, fields in stats.items():
            for f, values in fields.items():
                descriptives.append({"population": population, "collection": c, "field": f, **values})
    for rule in ("A", "B", "C"):
        for c in COLLECTIONS:
            group = [r for r in patient_records if r["rule"] == rule and r["collection"] == c]
            for number, count in sorted(Counter(r["rule_eligible_count"] for r in group).items()):
                candidate_counts.append({"population": rule, "collection": c, "eligible_series_per_patient": number,
                                         "patients": count, "denominator": len(group), "fraction": count / len(group)})
    # Differential checks on real data: reversing traversal and swapping collection labels
    # must not change any proposal, candidate list or eligibility status.
    altered = [{**r, "collection": COLLECTIONS[1] if r["collection"] == COLLECTIONS[0] else COLLECTIONS[0]} for r in reversed(rows)]
    altered_records, _, _, _ = patient_scenarios(altered)
    def signature(records):
        return sorted((r["rule"], r["patient_id"], r["proposed_series_uid"], r["status"], tuple(sorted(r["candidate_series_uids"]))) for r in records)
    if signature(patient_records) != signature(altered_records):
        raise AssertionError("Rule depends on collection label or input order")
    inventory_after = [(str(p.relative_to(RAW)), p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(RAW.rglob("*")) if p.is_file()]
    if inventory != inventory_after or protected_before != protected_files():
        raise AssertionError("Raw inventory or protected artifacts changed")
    summary = {
        "protocol": PROTOCOL, "hard_pool": hard_summary, "scenarios": scenarios,
        "tied_completion_sensitivity": tied_completion_sensitivity(rows, patient_records, chosen),
        "overlap_all_series": overlap(rows), "overlap_hard_eligible": overlap(hard),
        "all_series_metadata_comparison": compare(rows), "hard_eligible_metadata_comparison": compare(hard),
        "verification": {"dicom_headers_read": 53076, "header_errors": 0, "series": len(rows),
                         "patient_id_conflicts": 0, "unique_sop_uids": 53076,
                         "input_order_and_collection_swap_invariance": True,
                         "raw_inventory_stat_unchanged": True, "protected_sha256_unchanged": True,
                         "protected_files": protected_before,
                         "raw_inventory_stat_sha256": hashlib.sha256(json_cell(inventory).encode()).hexdigest(),
                         "source_script_sha256": sha(Path(__file__)),
                         "pixel_read": False, "formal_cohort_selected": False, "split_created": False, "training_started": False},
    }
    write_csv("series_analysis.csv", rows)
    write_csv("patient_rule_analysis.csv", patient_records)
    write_csv("scenario_series_analysis.csv", memberships)
    write_csv("metadata_distributions.csv", distribution_rows)
    write_csv("descriptive_statistics.csv", descriptives)
    write_csv("patient_candidate_counts.csv", candidate_counts)
    write_csv("manual_review_series.csv", [r for r in rows if r["hard_status"] == "review"])
    write_csv("scenario_summary.csv", [{"rule": k, "collection": c, **d} for k, s in scenarios.items() for c, d in s["by_collection"].items()])
    (OUT / "header_distributions_by_series.json").write_text(dumps(details), encoding="utf-8")
    (OUT / "analysis.json").write_text(dumps(summary), encoding="utf-8")
    (OUT / "REPORT.md").write_text(markdown_report(summary, rows, scenarios), encoding="utf-8")
    print(dumps({"hard_pool": hard_summary, "scenarios": scenarios, "output": str(OUT)}))


if __name__ == "__main__":
    main()
