#!/usr/bin/env python3
"""Build the immutable, PNG-only EpiLocate manual-review bundle."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterable

import numpy as np
from PIL import Image
import pydicom
from pydicom.pixels import get_decoder


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_ROOT = ROOT / "data/full_raw"
DEFAULT_REVIEW_ROOT = ROOT / "outputs/data/formal_series_rule_b_review_v1"
DEFAULT_PROTOCOL = ROOT / "configs/formal_series_selection_rule_b_v1.json"
DEFAULT_OUTPUT = ROOT / "outputs/data/formal_series_rule_b_review_bundle_v1"

BUNDLE_FORMAT = "epilocate-review-bundle"
BUNDLE_VERSION = 1
WINDOW_CENTER_HU = -600.0
WINDOW_WIDTH_HU = 1500.0
OUTPUT_ROWS = 512
OUTPUT_COLUMNS = 512

CASE_FIELDS = {
    "case_id",
    "case_type",
    "patient_id",
    "candidate_series_uids",
    "context_series_uids",
    "required_judgment",
    "allowed_decisions",
    "status",
}
CANDIDATE_FIELDS = {
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
}
SAFE_CASE_ID = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,63}$")
SAFE_KEY = re.compile(r"^[a-z0-9_-]+$")


class BundleBuildError(ValueError):
    """The source packet cannot safely produce a review bundle."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_key(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:24]}"


def _read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        missing = sorted(required - fields)
        if missing:
            raise BundleBuildError(f"{path.name} is missing columns: {missing}")
        return [{key: value or "" for key, value in row.items()} for row in reader]


def _json_string_list(value: str, field: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise BundleBuildError(f"{field} is not valid JSON") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) and item for item in parsed):
        raise BundleBuildError(f"{field} must be a JSON list of non-empty strings")
    if len(parsed) != len(set(parsed)):
        raise BundleBuildError(f"{field} contains duplicates")
    return parsed


def _finite_float(value: str, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise BundleBuildError(f"{field} must be numeric") from exc
    if not math.isfinite(result):
        raise BundleBuildError(f"{field} must be finite")
    return result


def _positive_int(value: str, field: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise BundleBuildError(f"{field} must be an integer") from exc
    if result <= 0:
        raise BundleBuildError(f"{field} must be positive")
    return result


def _safe_source_path(base: Path, relative: str, suffix: str) -> Path:
    if not relative or "\\" in relative:
        raise BundleBuildError("Resource paths must be non-empty POSIX paths")
    candidate = Path(relative)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise BundleBuildError(f"Unsafe resource path: {relative!r}")
    resolved_base = base.resolve()
    resolved = (resolved_base / candidate).resolve()
    try:
        resolved.relative_to(resolved_base)
    except ValueError as exc:
        raise BundleBuildError(f"Resource escapes its packet: {relative!r}") from exc
    if resolved.suffix.lower() != suffix or not resolved.is_file():
        raise BundleBuildError(f"Missing {suffix} resource: {relative!r}")
    return resolved


def _raw_inventory(raw_root: Path) -> str:
    rows = []
    for path in sorted(item for item in raw_root.rglob("*") if item.is_file()):
        stat = path.stat()
        rows.append((path.relative_to(raw_root).as_posix(), stat.st_size, stat.st_mtime_ns))
    return hashlib.sha256(
        json.dumps(rows, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _canonical_normal(orientation: Iterable[Any]) -> np.ndarray:
    values = np.asarray(list(orientation), dtype=np.float64)
    if values.shape != (6,) or not np.isfinite(values).all():
        raise BundleBuildError("ImageOrientationPatient must contain six finite values")
    normal = np.cross(values[:3], values[3:])
    length = float(np.linalg.norm(normal))
    if not math.isfinite(length) or length < 1e-8:
        raise BundleBuildError("ImageOrientationPatient has a degenerate normal")
    normal /= length
    dominant = int(np.argmax(np.abs(normal)))
    if normal[dominant] < 0:
        normal = -normal
    return normal


def _locate_series(raw_root: Path, target_uids: set[str]) -> dict[str, list[Path]]:
    located: dict[str, list[Path]] = {uid: [] for uid in target_uids}
    parents: dict[str, set[Path]] = {uid: set() for uid in target_uids}
    dicoms = sorted(
        path for path in raw_root.rglob("*") if path.is_file() and path.suffix.lower() == ".dcm"
    )
    if not dicoms:
        raise BundleBuildError(f"No DICOM files found under {raw_root}")
    for path in dicoms:
        try:
            path.resolve().relative_to(raw_root)
        except ValueError as exc:
            raise BundleBuildError("A DICOM symlink escapes the raw source tree") from exc
        try:
            ds = pydicom.dcmread(path, stop_before_pixels=True, specific_tags=["SeriesInstanceUID"])
        except Exception as exc:
            raise BundleBuildError(f"Cannot read DICOM header under raw root: {path.name}") from exc
        uid = str(getattr(ds, "SeriesInstanceUID", ""))
        if uid in target_uids:
            located[uid].append(path)
            parents[uid].add(path.parent.resolve())
    missing = sorted(uid for uid, paths in located.items() if not paths)
    if missing:
        raise BundleBuildError(f"Could not locate requested SeriesInstanceUID values: {missing}")
    split = sorted(uid for uid, directories in parents.items() if len(directories) != 1)
    if split:
        raise BundleBuildError(f"Series occur in multiple source directories: {split}")
    return located


def _ordered_slices(paths: list[Path], expected_uid: str) -> list[dict[str, Any]]:
    slices: list[dict[str, Any]] = []
    reference_normal: np.ndarray | None = None
    seen_sops: set[str] = set()
    for path in paths:
        try:
            ds = pydicom.dcmread(
                path,
                stop_before_pixels=True,
                specific_tags=[
                    "SeriesInstanceUID",
                    "SOPInstanceUID",
                    "ImageOrientationPatient",
                    "ImagePositionPatient",
                    "InstanceNumber",
                    "Rows",
                    "Columns",
                    "NumberOfFrames",
                ],
            )
        except Exception as exc:
            raise BundleBuildError(f"Cannot read candidate DICOM header: {path.name}") from exc
        if str(getattr(ds, "SeriesInstanceUID", "")) != expected_uid:
            raise BundleBuildError("A located DICOM changed SeriesInstanceUID during the build")
        if int(getattr(ds, "NumberOfFrames", 1) or 1) != 1:
            raise BundleBuildError("Multi-frame DICOM is not supported by review bundle v1")
        rows = int(getattr(ds, "Rows", 0) or 0)
        columns = int(getattr(ds, "Columns", 0) or 0)
        if (rows, columns) != (OUTPUT_ROWS, OUTPUT_COLUMNS):
            raise BundleBuildError(
                f"Review images must already be 512x512; got {rows}x{columns} without resampling"
            )
        normal = _canonical_normal(getattr(ds, "ImageOrientationPatient", ()))
        if reference_normal is None:
            reference_normal = normal
        elif float(np.dot(reference_normal, normal)) < 0.999:
            raise BundleBuildError("Series contains inconsistent ImageOrientationPatient values")
        position = np.asarray(getattr(ds, "ImagePositionPatient", ()), dtype=np.float64)
        if position.shape != (3,) or not np.isfinite(position).all():
            raise BundleBuildError("ImagePositionPatient must contain three finite values")
        sop_uid = str(getattr(ds, "SOPInstanceUID", ""))
        if not sop_uid or sop_uid in seen_sops:
            raise BundleBuildError("Series contains a missing or duplicate SOPInstanceUID")
        seen_sops.add(sop_uid)
        slices.append({
            "path": path,
            "projection": float(np.dot(position, reference_normal)),
            "instance": int(getattr(ds, "InstanceNumber", 0) or 0),
            "sop_uid": sop_uid,
        })
    return sorted(slices, key=lambda item: (item["projection"], item["instance"], item["sop_uid"]))


def _decode_pixel_array(ds: pydicom.Dataset) -> np.ndarray:
    transfer_syntax = getattr(getattr(ds, "file_meta", None), "TransferSyntaxUID", None)
    if transfer_syntax is not None and transfer_syntax.is_compressed:
        try:
            decoder = get_decoder(transfer_syntax)
        except NotImplementedError as exc:
            raise BundleBuildError(f"No DICOM decoder supports transfer syntax {transfer_syntax}") from exc
        if not decoder.is_available:
            raise BundleBuildError(
                f"DICOM decoder for {transfer_syntax} is unavailable; install pylibjpeg and pylibjpeg-libjpeg"
            )
    try:
        return np.asarray(ds.pixel_array)
    except Exception as exc:
        raise BundleBuildError(
            f"DICOM pixel decoding failed for transfer syntax {transfer_syntax or '<missing>'}"
        ) from exc


def window_to_uint8(
    stored_pixels: np.ndarray,
    slope: float,
    intercept: float,
    photometric_interpretation: str,
) -> np.ndarray:
    pixels = np.asarray(stored_pixels)
    if pixels.shape != (OUTPUT_ROWS, OUTPUT_COLUMNS):
        raise BundleBuildError(f"Expected one 512x512 frame, got {pixels.shape}")
    if not math.isfinite(slope) or slope == 0 or not math.isfinite(intercept):
        raise BundleBuildError("RescaleSlope and RescaleIntercept must be finite and slope non-zero")
    photometric = photometric_interpretation.upper()
    if photometric not in {"MONOCHROME1", "MONOCHROME2"}:
        raise BundleBuildError(f"Unsupported PhotometricInterpretation: {photometric!r}")
    hu = pixels.astype(np.float64) * slope + intercept
    low = WINDOW_CENTER_HU - WINDOW_WIDTH_HU / 2.0
    normalized = np.clip((hu - low) / WINDOW_WIDTH_HU, 0.0, 1.0)
    image = np.rint(normalized * 255.0).astype(np.uint8)
    if photometric == "MONOCHROME1":
        image = 255 - image
    return image


def _render_dicom(path: Path, expected_uid: str, output: Path) -> None:
    try:
        ds = pydicom.dcmread(path)
    except Exception as exc:
        raise BundleBuildError(f"Cannot read candidate DICOM pixels: {path.name}") from exc
    if str(getattr(ds, "SeriesInstanceUID", "")) != expected_uid:
        raise BundleBuildError("A candidate DICOM changed SeriesInstanceUID during pixel decoding")
    pixels = _decode_pixel_array(ds)
    image = window_to_uint8(
        pixels,
        float(getattr(ds, "RescaleSlope", 1.0)),
        float(getattr(ds, "RescaleIntercept", 0.0)),
        str(getattr(ds, "PhotometricInterpretation", "")),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image).save(output, format="PNG", compress_level=9, optimize=False)


def _copy_montage(source: Path, output: Path) -> tuple[int, int]:
    try:
        with Image.open(source) as opened:
            opened.load()
            image = opened.convert("RGB")
    except Exception as exc:
        raise BundleBuildError("Montage is not a decodable image") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", compress_level=9, optimize=False)
    return image.size


def _candidate_metadata(row: dict[str, str]) -> dict[str, Any]:
    return {
        "study_uid": row["study_uid"],
        "series_description": row["series_description"],
        "convolution_kernel": row["convolution_kernel"],
        "slice_thickness_mm": _finite_float(row["slice_thickness_mm"], "slice_thickness_mm"),
        "pixel_spacing_row_mm": _finite_float(row["pixel_spacing_row_mm"], "pixel_spacing_row_mm"),
        "pixel_spacing_column_mm": _finite_float(
            row["pixel_spacing_column_mm"], "pixel_spacing_column_mm"
        ),
        "coverage_mm": _finite_float(row["coverage_mm"], "coverage_mm"),
        "declared_slice_count": _positive_int(row["slice_count"], "slice_count"),
        "image_types": row["image_types"],
        "hard_status_before_review": row["hard_status_before_review"],
        "review_question": row["review_question"],
    }


def _asset_record(path: Path, staging: Path, kind: str, **fields: Any) -> dict[str, Any]:
    relative = path.relative_to(staging).as_posix()
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise AssertionError("Generated asset path is unsafe")
    with Image.open(path) as image:
        width, height = image.size
        image.verify()
    return {
        "kind": kind,
        "path": relative,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "width": width,
        "height": height,
        **fields,
    }


def _validate_packet(
    protocol: dict[str, Any],
    cases: list[dict[str, str]],
    candidates: list[dict[str, str]],
) -> tuple[dict[str, dict[str, str]], dict[str, list[dict[str, str]]]]:
    protocol_id = str(protocol.get("protocol_id", ""))
    if protocol.get("status") != "FROZEN" or not protocol_id:
        raise BundleBuildError("Review bundle requires a named FROZEN protocol")
    if protocol.get("phase_boundary", {}).get("formal_cohort_finalized") is True:
        raise BundleBuildError("Protocol unexpectedly claims a finalized cohort")
    case_map: dict[str, dict[str, str]] = {}
    for row in cases:
        case_id = row["case_id"]
        if not SAFE_CASE_ID.fullmatch(case_id) or case_id in case_map:
            raise BundleBuildError(f"Unsafe or duplicate case_id: {case_id!r}")
        case_map[case_id] = row
    grouped: dict[str, list[dict[str, str]]] = {case_id: [] for case_id in case_map}
    seen_uids: set[str] = set()
    for row in candidates:
        case_id = row["case_id"]
        if case_id not in case_map:
            raise BundleBuildError(f"Candidate references unknown case_id: {case_id!r}")
        case = case_map[case_id]
        if row["case_type"] != case["case_type"] or row["patient_id"] != case["patient_id"]:
            raise BundleBuildError(f"Candidate canonical fields disagree with case {case_id}")
        uid = row["series_uid"]
        if not uid or uid in seen_uids:
            raise BundleBuildError("SeriesInstanceUID values must be non-empty and globally unique")
        seen_uids.add(uid)
        grouped[case_id].append(row)
    for case_id, case in case_map.items():
        selectable = _json_string_list(case["candidate_series_uids"], f"{case_id}.candidate_series_uids")
        context = _json_string_list(case["context_series_uids"], f"{case_id}.context_series_uids")
        rows = grouped[case_id]
        row_selectable = [row["series_uid"] for row in rows if row["candidate_role"] != "excluded_bone_only_context"]
        row_context = [row["series_uid"] for row in rows if row["candidate_role"] == "excluded_bone_only_context"]
        if set(selectable) != set(row_selectable) or len(selectable) != len(row_selectable):
            raise BundleBuildError(f"Selectable candidates disagree for {case_id}")
        if set(context) != set(row_context) or len(context) != len(row_context):
            raise BundleBuildError(f"Context candidates disagree for {case_id}")
    return case_map, grouped


def _replace_output(staging: Path, output: Path) -> None:
    backup: Path | None = None
    if output.exists():
        backup = output.parent / f".{output.name}.previous-{os.getpid()}"
        if backup.exists():
            raise BundleBuildError(f"Refusing to overwrite stale backup directory: {backup}")
        os.replace(output, backup)
    try:
        os.replace(staging, output)
    except Exception:
        if backup is not None and backup.exists() and not output.exists():
            os.replace(backup, output)
        raise
    if backup is not None:
        shutil.rmtree(backup)


def build_review_bundle(
    *,
    raw_root: Path,
    cases_csv: Path,
    candidates_csv: Path,
    protocol_path: Path,
    output: Path,
    expected_cases: int | None = 13,
    expected_series: int | None = 26,
    expected_frames: int | None = 3479,
) -> dict[str, Any]:
    raw_root = raw_root.resolve()
    cases_csv = cases_csv.resolve()
    candidates_csv = candidates_csv.resolve()
    protocol_path = protocol_path.resolve()
    requested_output = output.expanduser()
    if requested_output.is_symlink():
        raise BundleBuildError("Output must not be a symbolic link")
    output = requested_output.parent.resolve() / requested_output.name
    if output.exists() and not output.is_dir():
        raise BundleBuildError("Existing output must be a directory")
    if not raw_root.is_dir():
        raise BundleBuildError(f"Raw DICOM root does not exist: {raw_root}")
    try:
        output.relative_to(raw_root)
    except ValueError:
        pass
    else:
        raise BundleBuildError("Output must not be inside the raw DICOM tree")
    for source in (cases_csv, candidates_csv, protocol_path):
        if not source.is_file():
            raise BundleBuildError(f"Required input does not exist: {source}")
        if source == output or output in source.parents:
            raise BundleBuildError("Output must not contain an input file")

    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    cases = _read_csv(cases_csv, CASE_FIELDS)
    candidates = _read_csv(candidates_csv, CANDIDATE_FIELDS)
    case_map, grouped = _validate_packet(protocol, cases, candidates)
    if expected_cases is not None and len(cases) != expected_cases:
        raise BundleBuildError(f"Expected {expected_cases} cases, found {len(cases)}")
    if expected_series is not None and len(candidates) != expected_series:
        raise BundleBuildError(f"Expected {expected_series} Series, found {len(candidates)}")

    raw_before = _raw_inventory(raw_root)
    locations = _locate_series(raw_root, {row["series_uid"] for row in candidates})
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.building-", dir=output.parent))
    assets: dict[str, dict[str, Any]] = {}
    manifest_cases: list[dict[str, Any]] = []
    total_frames = 0
    try:
        for case_id in sorted(case_map):
            case = case_map[case_id]
            manifest_case: dict[str, Any] = {
                "protocol_id": str(protocol["protocol_id"]),
                "case_id": case_id,
                "patient_id": case["patient_id"],
                "case_type": case["case_type"],
                "candidate_series_uids": _json_string_list(
                    case["candidate_series_uids"], f"{case_id}.candidate_series_uids"
                ),
                "context_series_uids": _json_string_list(
                    case["context_series_uids"], f"{case_id}.context_series_uids"
                ),
                "required_judgment": case["required_judgment"],
                "allowed_decisions": case["allowed_decisions"],
                "status": case["status"],
                "candidates": [],
                "context": [],
            }
            built_candidates: list[dict[str, Any]] = []
            for row in grouped[case_id]:
                uid = row["series_uid"]
                role = row["candidate_role"]
                candidate_key = _stable_key("candidate", str(protocol["protocol_id"]), case_id, role, uid)
                if not SAFE_KEY.fullmatch(candidate_key):
                    raise AssertionError("Generated candidate_key is unsafe")
                slices = _ordered_slices(locations[uid], uid)
                metadata = _candidate_metadata(row)
                if len(slices) != metadata["declared_slice_count"]:
                    raise BundleBuildError(
                        f"Declared slice_count for {case_id}/{role} is {metadata['declared_slice_count']}, "
                        f"but {len(slices)} DICOM frames were located"
                    )
                montage_source = _safe_source_path(candidates_csv.parent, row["montage_path"], ".png")
                montage_path = staging / "media" / candidate_key / "montage.png"
                _copy_montage(montage_source, montage_path)
                montage_asset_id = _stable_key("asset", candidate_key, "montage")
                assets[montage_asset_id] = _asset_record(
                    montage_path,
                    staging,
                    "montage",
                    case_id=case_id,
                    candidate_key=candidate_key,
                )
                frame_asset_ids: list[str] = []
                for index, descriptor in enumerate(slices):
                    frame_path = staging / "media" / candidate_key / "frames" / f"{index:06d}.png"
                    _render_dicom(descriptor["path"], uid, frame_path)
                    asset_id = _stable_key("asset", candidate_key, "frame", str(index))
                    assets[asset_id] = _asset_record(
                        frame_path,
                        staging,
                        "frame",
                        case_id=case_id,
                        candidate_key=candidate_key,
                        frame_index=index,
                        projection_mm=round(float(descriptor["projection"]), 6),
                    )
                    frame_asset_ids.append(asset_id)
                total_frames += len(frame_asset_ids)
                built_candidates.append({
                    "candidate_key": candidate_key,
                    "role": role,
                    "series_uid": uid,
                    "metadata": metadata,
                    "montage_asset_id": montage_asset_id,
                    "frame_count": len(frame_asset_ids),
                    "frame_asset_ids": frame_asset_ids,
                })
            # Preserve the frozen CSV row order. Candidate keys include the Series UID,
            # so sorting by key would make this order indirectly UID-dependent.
            for candidate in built_candidates:
                target = (
                    manifest_case["context"]
                    if candidate["role"] == "excluded_bone_only_context"
                    else manifest_case["candidates"]
                )
                target.append(candidate)
            manifest_cases.append(manifest_case)

        if expected_frames is not None and total_frames != expected_frames:
            raise BundleBuildError(f"Expected {expected_frames} frames, found {total_frames}")
        manifest = {
            "format": BUNDLE_FORMAT,
            "version": BUNDLE_VERSION,
            "protocol_id": str(protocol["protocol_id"]),
            "protocol_sha256": sha256_file(protocol_path),
            "window": {
                "center_hu": WINDOW_CENTER_HU,
                "width_hu": WINDOW_WIDTH_HU,
                "output_bits": 8,
                "rows": OUTPUT_ROWS,
                "columns": OUTPUT_COLUMNS,
                "resampled": False,
            },
            "cases": manifest_cases,
            "assets": {asset_id: assets[asset_id] for asset_id in sorted(assets)},
        }
        manifest_path = staging / "bundle.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        expected_files = {"bundle.json"} | {asset["path"] for asset in assets.values()}
        actual_files = {
            path.relative_to(staging).as_posix()
            for path in staging.rglob("*")
            if path.is_file()
        }
        if actual_files != expected_files:
            raise AssertionError("Bundle contains an unregistered or missing file")
        if any(path.suffix.lower() == ".dcm" for path in staging.rglob("*")):
            raise AssertionError("Bundle must not contain DICOM files")
        if _raw_inventory(raw_root) != raw_before:
            raise BundleBuildError("Raw DICOM inventory changed during bundle construction")
        _replace_output(staging, output)
        return manifest
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--cases-csv", type=Path, default=DEFAULT_REVIEW_ROOT / "manual_review_cases.csv")
    parser.add_argument(
        "--candidates-csv", type=Path, default=DEFAULT_REVIEW_ROOT / "manual_review_candidates.csv"
    )
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--expected-cases", type=int, default=13)
    parser.add_argument("--expected-series", type=int, default=26)
    parser.add_argument("--expected-frames", type=int, default=3479)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_review_bundle(
        raw_root=args.raw_root,
        cases_csv=args.cases_csv,
        candidates_csv=args.candidates_csv,
        protocol_path=args.protocol,
        output=args.output,
        expected_cases=args.expected_cases,
        expected_series=args.expected_series,
        expected_frames=args.expected_frames,
    )
    print(json.dumps({
        "bundle": str(args.output.resolve()),
        "manifest_sha256": sha256_file(args.output.resolve() / "bundle.json"),
        "cases": len(manifest["cases"]),
        "series": sum(len(case["candidates"]) + len(case["context"]) for case in manifest["cases"]),
        "frames": sum(
            candidate["frame_count"]
            for case in manifest["cases"]
            for candidate in case["candidates"] + case["context"]
        ),
        "assets": len(manifest["assets"]),
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
