#!/usr/bin/env python3
"""Build the full RICORD metadata audit and stop safely at fairness gates.

This script never reads PixelData, moves DICOM files, or changes the development
dataset. It writes the Step 13/14 reports first, then creates formal patient
splits only when the predeclared series rule is fair and every patient has an
objective series selection.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import pydicom

from src.data_checks import PROJECT_ROOT


COLLECTIONS = {
    "midrc_ricord_1a": ("MIDRC-RICORD-1A", "1"),
    "midrc_ricord_1b": ("MIDRC-RICORD-1B", "0"),
}
MISSING = "<MISSING>"
AXIAL_TOLERANCE = 0.01

# A rule that removes at least half of either collection is unambiguously a
# large systematic exclusion. A 10 percentage-point class retention gap is
# separately reported as an imbalance.
MASS_EXCLUSION_THRESHOLD = 0.50
RETENTION_GAP_THRESHOLD = 0.10

AUDIT_FIELDS = (
    "slice_thickness",
    "convolution_kernel",
    "manufacturer",
    "manufacturer_model_name",
    "rows",
    "columns",
    "pixel_spacing",
    "series_description",
    "image_orientation_patient",
    "photometric_interpretation",
    "rescale_slope",
    "rescale_intercept",
)
CONTRAST_FIELDS = (
    "ContrastBolusAgent",
    "ContrastBolusRoute",
    "ContrastBolusVolume",
    "ContrastBolusStartTime",
    "ContrastBolusStopTime",
    "ContrastBolusTotalDose",
    "ContrastBolusIngredient",
    "ContrastBolusIngredientConcentration",
    "AcquisitionContrast",
)


def scalar_text(value: Any) -> str:
    if value is None or str(value).strip() == "":
        return MISSING
    if isinstance(value, (list, tuple)) or value.__class__.__name__ == "MultiValue":
        return "|".join(scalar_text(item) for item in value)
    return str(value).strip()


def number_text(value: Any) -> str:
    text = scalar_text(value)
    if text == MISSING:
        return text
    try:
        number = float(text)
    except (TypeError, ValueError):
        return text
    if not math.isfinite(number):
        return text
    return f"{number:.12g}"


def vector_text(value: Any) -> str:
    if value is None or str(value).strip() == "":
        return MISSING
    try:
        values = list(value)
    except TypeError:
        return scalar_text(value)
    return ",".join(number_text(item) for item in values)


def collection_for_path(path: Path, root: Path) -> tuple[str, str]:
    key = path.relative_to(root).parts[0]
    if key not in COLLECTIONS:
        raise ValueError(f"Unexpected collection directory: {key}")
    return COLLECTIONS[key]


def header_value(ds: pydicom.Dataset, keyword: str) -> Any:
    return getattr(ds, keyword, None)


def image_types(ds: pydicom.Dataset) -> tuple[str, ...]:
    value = header_value(ds, "ImageType")
    if value is None:
        return ()
    if isinstance(value, str):
        values = value.split("\\")
    else:
        try:
            values = list(value)
        except TypeError:
            values = [value]
    return tuple(str(item).strip().upper() for item in values if str(item).strip())


def is_axial(ds: pydicom.Dataset) -> bool:
    try:
        orientation = np.asarray(header_value(ds, "ImageOrientationPatient"), dtype=float)
    except (TypeError, ValueError):
        return False
    if orientation.shape != (6,) or not np.isfinite(orientation).all():
        return False
    normal = np.cross(orientation[:3], orientation[3:])
    return bool(
        np.isfinite(normal).all()
        and np.allclose(np.abs(normal), [0.0, 0.0, 1.0], atol=AXIAL_TOLERANCE, rtol=0)
    )


def is_localizer(types: Iterable[str], description: str) -> bool:
    joined = "|".join(types)
    description = description.upper()
    terms = ("LOCALIZER", "SCOUT", "TOPOGRAM", "SURVIEW")
    return any(term in joined or term in description for term in terms)


def series_value(values: set[str]) -> str:
    return " || ".join(sorted(values))


@dataclass
class SeriesAggregate:
    collection: str
    label: str
    patient_id: str
    study_uid: str
    series_uid: str
    slice_count: int = 0
    sop_uids: set[str] = field(default_factory=set)
    values: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    all_ct: bool = True
    all_axial: bool = True
    any_localizer: bool = False
    all_original_primary: bool = True
    all_axial_image_type: bool = True
    any_derived_or_reformatted: bool = False
    header_warnings: int = 0

    def add(self, ds: pydicom.Dataset, row: dict[str, str]) -> None:
        self.slice_count += 1
        self.sop_uids.add(row["sop_uid"])
        for name in AUDIT_FIELDS:
            self.values[name].add(row[name])
        self.values["image_type"].add(row["image_type"])
        for keyword in CONTRAST_FIELDS:
            self.values[keyword].add(row[keyword])
        types = image_types(ds)
        description = row["series_description"] if row["series_description"] != MISSING else ""
        type_set = set(types)
        self.all_ct = self.all_ct and row["modality"].upper() == "CT"
        self.all_axial = self.all_axial and is_axial(ds)
        self.any_localizer = self.any_localizer or is_localizer(types, description)
        self.all_original_primary = self.all_original_primary and {"ORIGINAL", "PRIMARY"}.issubset(type_set)
        self.all_axial_image_type = self.all_axial_image_type and "AXIAL" in type_set
        self.any_derived_or_reformatted = self.any_derived_or_reformatted or bool(
            {"DERIVED", "REFORMATTED"} & type_set
        )

    def summary(self) -> dict[str, Any]:
        reasons = []
        if not self.all_ct:
            reasons.append("not_CT")
        if self.any_localizer:
            reasons.append("scout_or_localizer")
        if not self.all_axial:
            reasons.append("non_axial_or_missing_orientation")
        if not self.all_original_primary or self.any_derived_or_reformatted:
            reasons.append("not_original_primary_diagnostic")
        core_eligible = not reasons

        kernels = self.values["convolution_kernel"]
        thicknesses = self.values["slice_thickness"]
        if core_eligible and not self.all_axial_image_type:
            reasons_for_development = ["image_type_missing_AXIAL"]
        else:
            reasons_for_development = list(reasons)
        if kernels != {"STANDARD"}:
            reasons_for_development.append("kernel_not_STANDARD")
        if thicknesses != {"1.25"}:
            reasons_for_development.append("thickness_not_1.25mm")
        development_rule_eligible = not reasons_for_development

        result: dict[str, Any] = {
            "collection": self.collection,
            "label": self.label,
            "patient_id": self.patient_id,
            "study_uid": self.study_uid,
            "series_uid": self.series_uid,
            "slice_count": self.slice_count,
            "unique_sop_uid_count": len(self.sop_uids),
            "duplicate_sop_uid_count": self.slice_count - len(self.sop_uids),
            "modality_all_CT": self.all_ct,
            "axial_geometry_all_slices": self.all_axial,
            "scout_or_localizer": self.any_localizer,
            "original_primary_all_slices": self.all_original_primary,
            "axial_image_type_all_slices": self.all_axial_image_type,
            "derived_or_reformatted": self.any_derived_or_reformatted,
            "core_axial_diagnostic_eligible": core_eligible,
            "core_exclusion_reasons": ";".join(reasons) or "eligible",
            "development_STANDARD_1.25_eligible": development_rule_eligible,
            "development_rule_exclusion_reasons": ";".join(reasons_for_development) or "eligible",
        }
        for name in (*AUDIT_FIELDS, "image_type", *CONTRAST_FIELDS):
            result[name] = series_value(self.values[name])
        return result


def slice_record(ds: pydicom.Dataset, path: Path, root: Path) -> dict[str, str]:
    collection, label = collection_for_path(path, root)
    patient_id = scalar_text(header_value(ds, "PatientID"))
    study_uid = scalar_text(header_value(ds, "StudyInstanceUID"))
    series_uid = scalar_text(header_value(ds, "SeriesInstanceUID"))
    sop_uid = scalar_text(header_value(ds, "SOPInstanceUID"))
    for keyword, value in (
        ("PatientID", patient_id),
        ("StudyInstanceUID", study_uid),
        ("SeriesInstanceUID", series_uid),
        ("SOPInstanceUID", sop_uid),
    ):
        if value == MISSING:
            raise ValueError(f"Missing required {keyword}")
    types = image_types(ds)
    record = {
        "collection": collection,
        "label": label,
        "patient_id": patient_id,
        "study_uid": study_uid,
        "series_uid": series_uid,
        "sop_uid": sop_uid,
        "modality": scalar_text(header_value(ds, "Modality")),
        "slice_thickness": number_text(header_value(ds, "SliceThickness")),
        "convolution_kernel": scalar_text(header_value(ds, "ConvolutionKernel")),
        "manufacturer": scalar_text(header_value(ds, "Manufacturer")),
        "manufacturer_model_name": scalar_text(header_value(ds, "ManufacturerModelName")),
        "rows": number_text(header_value(ds, "Rows")),
        "columns": number_text(header_value(ds, "Columns")),
        "pixel_spacing": vector_text(header_value(ds, "PixelSpacing")),
        "series_description": scalar_text(header_value(ds, "SeriesDescription")),
        "image_orientation_patient": vector_text(header_value(ds, "ImageOrientationPatient")),
        "photometric_interpretation": scalar_text(header_value(ds, "PhotometricInterpretation")),
        "rescale_slope": number_text(header_value(ds, "RescaleSlope")),
        "rescale_intercept": number_text(header_value(ds, "RescaleIntercept")),
        "image_type": "|".join(types) if types else MISSING,
    }
    for keyword in CONTRAST_FIELDS:
        record[keyword] = scalar_text(header_value(ds, keyword))
    return record


def total_variation(left: Counter[str], right: Counter[str]) -> float:
    left_total = sum(left.values())
    right_total = sum(right.values())
    if not left_total or not right_total:
        return 0.0
    values = set(left) | set(right)
    return 0.5 * sum(abs(left[value] / left_total - right[value] / right_total) for value in values)


def comparison_rows(
    slice_distributions: dict[str, dict[str, Counter[str]]],
    series_frame: pd.DataFrame,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    collections = ("MIDRC-RICORD-1A", "MIDRC-RICORD-1B")
    rows: list[dict[str, Any]] = []
    field_metrics: dict[str, Any] = {}
    for level in ("slice", "series"):
        for field_name in AUDIT_FIELDS:
            if level == "slice":
                counters = {
                    collection: slice_distributions[collection][field_name]
                    for collection in collections
                }
            else:
                counters = {
                    collection: Counter(
                        series_frame.loc[series_frame.collection.eq(collection), field_name]
                    )
                    for collection in collections
                }
            tvd = total_variation(counters[collections[0]], counters[collections[1]])
            metric_key = f"{level}:{field_name}"
            field_metrics[metric_key] = {
                "total_variation_distance": round(tvd, 6),
                "obvious_distribution_difference": tvd >= 0.25,
            }
            values = sorted(set(counters[collections[0]]) | set(counters[collections[1]]))
            totals = {collection: sum(counters[collection].values()) for collection in collections}
            for value in values:
                count_a = counters[collections[0]][value]
                count_b = counters[collections[1]][value]
                rate_a = count_a / totals[collections[0]] if totals[collections[0]] else 0.0
                rate_b = count_b / totals[collections[1]] if totals[collections[1]] else 0.0
                rows.append({
                    "level": level,
                    "field": field_name,
                    "value": value,
                    "collection_1a_count": count_a,
                    "collection_1a_fraction": round(rate_a, 8),
                    "collection_1b_count": count_b,
                    "collection_1b_fraction": round(rate_b, 8),
                    "absolute_fraction_difference": round(abs(rate_a - rate_b), 8),
                    "field_total_variation_distance": round(tvd, 6),
                    "obvious_field_difference": tvd >= 0.25,
                })
    return rows, field_metrics


def distribution_json(counter: Counter[str]) -> dict[str, Any]:
    total = sum(counter.values())
    return {
        "total": total,
        "missing": counter[MISSING],
        "value_counts": dict(sorted(counter.items(), key=lambda item: (-item[1], item[0]))),
    }


def count_entities(series_frame: pd.DataFrame, collection: str) -> dict[str, int]:
    group = series_frame[series_frame.collection.eq(collection)]
    return {
        "patients": int(group.patient_id.nunique()),
        "studies": int(group.study_uid.nunique()),
        "series": int(group.series_uid.nunique()),
        "slices": int(group.slice_count.sum()),
    }


def contrast_audit(
    slice_contrast: dict[str, dict[str, Counter[str]]],
    series_frame: pd.DataFrame,
) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for collection in ("MIDRC-RICORD-1A", "MIDRC-RICORD-1B"):
        collection_report: dict[str, Any] = {}
        subset = series_frame[series_frame.collection.eq(collection)]
        for keyword in CONTRAST_FIELDS:
            slice_counter = slice_contrast[collection][keyword]
            present_slices = sum(count for value, count in slice_counter.items() if value != MISSING)
            present_series = int(subset[keyword].ne(MISSING).sum())
            collection_report[keyword] = {
                "present_slices": present_slices,
                "slice_fraction": round(present_slices / sum(slice_counter.values()), 8),
                "present_series": present_series,
                "series_fraction": round(present_series / len(subset), 8),
                "value_counts": dict(sorted(slice_counter.items(), key=lambda item: (-item[1], item[0]))),
            }
        report[collection] = collection_report

    agent_present = any(
        report[collection]["ContrastBolusAgent"]["present_series"]
        for collection in report
    )
    acquisition_present = any(
        report[collection]["AcquisitionContrast"]["present_series"]
        for collection in report
    )
    report["reliability_assessment"] = {
        "reliable_for_automatic_contrast_classification": False,
        "reason": (
            "Contrast-related tags are incomplete across the collections; absence cannot be "
            "interpreted as a non-contrast acquisition. SeriesDescription may be used only for "
            "manual review, not as a reliable ground-truth contrast label."
        ),
        "ContrastBolusAgent_present_anywhere": agent_present,
        "AcquisitionContrast_present_anywhere": acquisition_present,
    }
    return report


def scan_headers(root: Path) -> tuple[pd.DataFrame, dict[str, Any], list[dict[str, str]]]:
    files = sorted(path for path in root.rglob("*.dcm") if path.is_file())
    if not files:
        raise ValueError(f"No DICOM files found under {root}")
    series: dict[str, SeriesAggregate] = {}
    errors: list[dict[str, str]] = []
    slice_distributions = {
        collection: {field_name: Counter() for field_name in AUDIT_FIELDS}
        for collection, _ in COLLECTIONS.values()
    }
    slice_contrast = {
        collection: {keyword: Counter() for keyword in CONTRAST_FIELDS}
        for collection, _ in COLLECTIONS.values()
    }
    patient_collections: dict[str, set[str]] = defaultdict(set)

    for index, path in enumerate(files, start=1):
        try:
            ds = pydicom.dcmread(path, stop_before_pixels=True, force=False)
            row = slice_record(ds, path, root)
            patient_collections[row["patient_id"]].add(row["collection"])
            key = row["series_uid"]
            if key not in series:
                series[key] = SeriesAggregate(
                    collection=row["collection"],
                    label=row["label"],
                    patient_id=row["patient_id"],
                    study_uid=row["study_uid"],
                    series_uid=row["series_uid"],
                )
            aggregate = series[key]
            identity = (aggregate.collection, aggregate.patient_id, aggregate.study_uid)
            if identity != (row["collection"], row["patient_id"], row["study_uid"]):
                raise ValueError("SeriesInstanceUID maps to conflicting collection/patient/study")
            aggregate.add(ds, row)
            for field_name in AUDIT_FIELDS:
                slice_distributions[row["collection"]][field_name][row[field_name]] += 1
            for keyword in CONTRAST_FIELDS:
                slice_contrast[row["collection"]][keyword][row[keyword]] += 1
        except Exception as exc:
            errors.append({
                "image_path": path.relative_to(PROJECT_ROOT).as_posix(),
                "error": f"{type(exc).__name__}: {exc}",
            })
        if index % 10000 == 0:
            print(f"Read {index}/{len(files)} DICOM headers", flush=True)

    series_frame = pd.DataFrame([aggregate.summary() for aggregate in series.values()])
    if not series_frame.empty:
        series_frame = series_frame.sort_values(
            ["collection", "patient_id", "study_uid", "series_uid"]
        ).reset_index(drop=True)
    conflicts = {
        patient: sorted(collections)
        for patient, collections in patient_collections.items()
        if len(collections) > 1
    }
    scan_state = {
        "files_found": len(files),
        "errors": errors,
        "patient_id_conflicts": conflicts,
        "slice_distributions": slice_distributions,
        "slice_contrast": slice_contrast,
    }
    return series_frame, scan_state, errors


def fairness_report(series_frame: pd.DataFrame) -> dict[str, Any]:
    by_collection: dict[str, Any] = {}
    retention_rates = []
    for collection in ("MIDRC-RICORD-1A", "MIDRC-RICORD-1B"):
        subset = series_frame[series_frame.collection.eq(collection)]
        patients = set(subset.patient_id)
        core_patients = set(subset.loc[subset.core_axial_diagnostic_eligible, "patient_id"])
        strict_patients = set(subset.loc[subset["development_STANDARD_1.25_eligible"], "patient_id"])
        retention = len(strict_patients) / len(patients)
        exclusion = 1.0 - retention
        retention_rates.append(retention)
        by_collection[collection] = {
            "all_patients": len(patients),
            "core_axial_diagnostic_patients": len(core_patients),
            "development_STANDARD_1.25_patients": len(strict_patients),
            "development_rule_excluded_patients": len(patients - strict_patients),
            "development_rule_retention_fraction": round(retention, 8),
            "development_rule_exclusion_fraction": round(exclusion, 8),
            "mass_exclusion": exclusion >= MASS_EXCLUSION_THRESHOLD,
        }
    gap = abs(retention_rates[0] - retention_rates[1])
    stop = any(item["mass_exclusion"] for item in by_collection.values()) or gap >= RETENTION_GAP_THRESHOLD
    return {
        "rule_under_review": {
            "core": "CT + all-slice axial geometry + not Scout/Localizer + ORIGINAL/PRIMARY + not DERIVED/REFORMATTED",
            "development_constraints": "ImageType includes AXIAL + ConvolutionKernel exactly STANDARD + SliceThickness exactly 1.25 mm",
        },
        "thresholds": {
            "mass_exclusion_fraction": MASS_EXCLUSION_THRESHOLD,
            "retention_gap_fraction": RETENTION_GAP_THRESHOLD,
        },
        "by_collection": by_collection,
        "absolute_retention_gap": round(gap, 8),
        "retention_imbalance": gap >= RETENTION_GAP_THRESHOLD,
        "stop_required": stop,
        "decision": (
            "STOP: the development STANDARD/1.25 mm rule is not acceptable for formal full-data selection"
            if stop
            else "PASS: development rule may proceed to objective series selection"
        ),
        "policy": "Report only; do not relax, replace, or tune the predeclared rule automatically.",
    }


def patient_selection_report(series_frame: pd.DataFrame, fairness: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for patient_id, group in series_frame.groupby("patient_id", sort=True):
        core = group[group.core_axial_diagnostic_eligible]
        strict = group[group["development_STANDARD_1.25_eligible"]]
        if core.empty:
            status = "NO_CORE_AXIAL_DIAGNOSTIC_SERIES"
        elif fairness["stop_required"]:
            status = "STOPPED_BY_STANDARD_1.25_FAIRNESS_GATE"
        elif len(core) > 1:
            status = "MANUAL_CONFIRMATION_REQUIRED"
        else:
            status = "OBJECTIVE_SINGLE_CANDIDATE"
        rows.append({
            "collection": group.collection.iloc[0],
            "label": group.label.iloc[0],
            "patient_id": patient_id,
            "study_count": int(group.study_uid.nunique()),
            "all_series_count": len(group),
            "core_axial_diagnostic_candidate_count": len(core),
            "core_candidate_series_uids": "|".join(core.series_uid),
            "development_STANDARD_1.25_candidate_count": len(strict),
            "development_STANDARD_1.25_candidate_series_uids": "|".join(strict.series_uid),
            "selected_series_uid": "",
            "selection_status": status,
            "requires_manual_series_confirmation": bool(len(core) > 1),
            "selection_finalized": False,
        })
    return pd.DataFrame(rows).sort_values(["collection", "patient_id"]).reset_index(drop=True)


def write_reports(root: Path, output_dir: Path) -> dict[str, Any]:
    series_frame, scan_state, errors = scan_headers(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    series_frame.to_csv(output_dir / "full_series_summary.csv", index=False, lineterminator="\n")

    comparison, field_metrics = comparison_rows(scan_state["slice_distributions"], series_frame)
    pd.DataFrame(comparison).to_csv(
        output_dir / "collection_metadata_comparison.csv", index=False, lineterminator="\n"
    )
    fairness = fairness_report(series_frame)
    selections = patient_selection_report(series_frame, fairness)
    selections.to_csv(output_dir / "full_series_selection.csv", index=False, lineterminator="\n")

    metadata_differences = {
        key: value for key, value in field_metrics.items() if value["obvious_distribution_difference"]
    }
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "step": "Step 13 Full Metadata Audit and Step 14 fairness gate",
        "source": root.relative_to(PROJECT_ROOT).as_posix(),
        "read_method": "pydicom.dcmread(stop_before_pixels=True, force=False)",
        "counts": {
            collection: count_entities(series_frame, collection)
            for collection in ("MIDRC-RICORD-1A", "MIDRC-RICORD-1B")
        },
        "header_read_errors": errors,
        "header_read_error_count": len(errors),
        "patient_id_conflicts": scan_state["patient_id_conflicts"],
        "patient_id_conflict_count": len(scan_state["patient_id_conflicts"]),
        "slice_level_distributions": {
            collection: {
                field_name: distribution_json(counter)
                for field_name, counter in fields.items()
            }
            for collection, fields in scan_state["slice_distributions"].items()
        },
        "distribution_comparison": {
            "method": "Total variation distance on empirical categorical distributions; >=0.25 is reported as obvious.",
            "field_metrics": field_metrics,
            "obvious_differences": metadata_differences,
            "obvious_metadata_distribution_difference_present": bool(metadata_differences),
        },
        "contrast_metadata": contrast_audit(scan_state["slice_contrast"], series_frame),
        "series_eligibility_fairness": fairness,
        "outputs": {
            "series_summary": "outputs/data/full_series_summary.csv",
            "series_selection": "outputs/data/full_series_selection.csv",
            "metadata_comparison": "outputs/data/collection_metadata_comparison.csv",
        },
        "safety": {
            "pixel_data_read": False,
            "dicom_deleted_or_moved": False,
            "automatic_rule_change": False,
            "formal_split_created": False,
        },
    }
    (output_dir / "full_metadata_audit.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report


def print_summary(report: dict[str, Any], selection_path: Path) -> None:
    fairness = report["series_eligibility_fairness"]
    selections = pd.read_csv(selection_path, dtype=str, keep_default_na=False)
    print(json.dumps({
        "counts": report["counts"],
        "header_read_error_count": report["header_read_error_count"],
        "patient_id_conflict_count": report["patient_id_conflict_count"],
        "obvious_metadata_distribution_difference_present": report[
            "distribution_comparison"
        ]["obvious_metadata_distribution_difference_present"],
        "fairness": fairness,
        "patients_requiring_manual_series_confirmation": int(
            selections.requires_manual_series_confirmation.eq("True").sum()
        ),
        "formal_split_created": False,
    }, indent=2, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-dir", default="data/full_raw")
    parser.add_argument("--output-dir", default="outputs/data")
    args = parser.parse_args()
    root = PROJECT_ROOT / args.download_dir
    output_dir = PROJECT_ROOT / args.output_dir
    if not root.is_dir():
        raise SystemExit(f"Missing download directory: {root}")
    report = write_reports(root, output_dir)
    print_summary(report, output_dir / "full_series_selection.csv")
    if report["header_read_error_count"] or report["patient_id_conflict_count"]:
        print("STOP: full metadata audit found integrity errors", file=sys.stderr)
        return 2
    if report["series_eligibility_fairness"]["stop_required"]:
        print(
            "STOP: STANDARD/1.25 mm development rule failed the predeclared fairness gate; "
            "formal full-data split files were not created.",
            file=sys.stderr,
        )
        return 3
    print(
        "STOP: fairness passed, but automatic multi-series selection is intentionally not "
        "implemented without a separately approved objective rule.",
        file=sys.stderr,
    )
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
