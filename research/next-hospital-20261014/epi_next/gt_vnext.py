"""Nonsealed, native-grid RICORD development reference builder.

Shared official ZIP containers are streamed. Only allowlisted annotation
objects are JSON-decoded; other bodies are skipped lexically. No sealed GT,
test manifest, model, GPU, or network path is accepted by this module.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
from zipfile import ZipFile

import numpy as np
import pydicom
from PIL import Image, ImageDraw, __version__ as pillow_version

from .geometry import regular_stack_geometry, slice_affine_lps, transform_points, inverse_points

INFECTION_CLASSES = frozenset({"Infectious opacity", "Infectious TIB/micronodules", "Infectious cavity"})
NONINFECTION_CLASSES = frozenset({"Noninfectious nodule/mass", "Atelectasis", "Other noninfectious opacity"})
OFFICIAL_SHA = "0000000000000000000000000000000000000000000000000000000000000000"
CLINICAL_SHA = "0000000000000000000000000000000000000000000000000000000000000000"
SPLIT_SHA = {"train": "0000000000000000000000000000000000000000000000000000000000000000",
             "val": "0000000000000000000000000000000000000000000000000000000000000000"}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def save_json(path, value):
    path = Path(path)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    path.chmod(0o600)


def array_objects(stream, key):
    """Frame a named array's objects without decoding unselected JSON bodies.

    This deliberately supports the hash-bound MD.ai export layout, not arbitrary
    JSON queries. Strings and escapes are honoured; records can span chunks.
    """
    text_stream = io.TextIOWrapper(stream, encoding="utf-8")
    marker = re.compile(r'"' + re.escape(key) + r'"\s*:\s*\[')
    prefix = ""
    while True:
        chunk = text_stream.read(65536)
        if not chunk:
            raise ValueError(f"missing array {key}")
        prefix += chunk
        found = marker.search(prefix)
        if found:
            chunk = prefix[found.end():]
            break
        prefix = prefix[-256:]
    depth = 0
    quoted = escaped = False
    parts = []
    while True:
        start = 0 if depth else None
        for index, character in enumerate(chunk):
            if depth == 0:
                if character in " \r\n\t,":
                    continue
                if character == "]":
                    return
                if character != "{":
                    raise ValueError("array must contain objects")
                start = index
                depth = 1
                continue
            if quoted:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    quoted = False
            elif character == '"':
                quoted = True
            elif character in "{[":
                depth += 1
            elif character in "}]":
                depth -= 1
                if depth == 0:
                    parts.append(chunk[start:index + 1])
                    yield "".join(parts)
                    parts = []
                    start = None
        if start is not None:
            parts.append(chunk[start:])
        chunk = text_stream.read(65536)
        if not chunk:
            raise ValueError("truncated array")


def authorized_cases(delivery_path, delivery_sha):
    """The sole access entrance is the formally released exact delivery."""
    from .data_delivery import verify_delivery, read_bound
    delivery = verify_delivery(delivery_path, delivery_sha)
    if delivery["schema"] != "EPI_NEXT_DATA_DELIVERY_V2":
        raise ValueError("current v2 delivery required")
    allowlist = read_bound(delivery["allowlist_path"], delivery["allowlist_sha256"])
    cases = allowlist["records"]
    if len(cases) != 3 or any(c["split"] != "train" for c in cases) or sum(c["sop_count"] for c in cases) != 715:
        raise ValueError("exact three train / 715 SOP scope required")
    source_root = Path(allowlist["source_root"]).resolve(strict=True)
    raw_root = (source_root / "data/full_raw").resolve(strict=True)
    for case in cases:
        for row in case["rows"]:
            relative = Path(row["image_path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("invalid CT relative path")
            path = (source_root / relative).resolve(strict=True)
            if not path.is_relative_to(raw_root) or not path.is_file():
                raise ValueError("CT outside approved raw root")
    return cases, source_root, delivery


def top_level_metadata(raw, wanted):
    """Read only requested top-level scalar fields; never decode data objects.

    Framing still scans shared-container bytes. Nested UID lookalikes and string
    contents cannot authorize an object. Duplicate top-level keys fail closed.
    """
    fields = {}
    depth = 0
    i = 0
    while i < len(raw):
        char = raw[i]
        if char == '"':
            start = i; i += 1
            escaped = False
            while i < len(raw):
                if escaped:
                    escaped = False
                elif raw[i] == "\\":
                    escaped = True
                elif raw[i] == '"':
                    break
                i += 1
            if i == len(raw):
                raise ValueError("unterminated string")
            end = i + 1
            if depth == 1:
                j = end
                while j < len(raw) and raw[j].isspace():
                    j += 1
                if j < len(raw) and raw[j] == ':':
                    key = json.loads(raw[start:end])
                    if key in wanted:
                        if key in fields:
                            raise ValueError("duplicate identity key")
                        j += 1
                        while j < len(raw) and raw[j].isspace():
                            j += 1
                        if raw[j] not in '"n':
                            raise ValueError("identity must be string or null")
                        value, consumed = json.JSONDecoder().raw_decode(raw[j:])
                        if value is not None and not isinstance(value, str):
                            raise ValueError("identity must be string or null")
                        fields[key] = value
            i = end
            continue
        if char in '{[':
            depth += 1
        elif char in '}]':
            depth -= 1
        i += 1
    if depth != 0:
        raise ValueError("unbalanced object")
    return fields


def selected_annotations(zip_path, cases):
    by_sop = {r["sop_uid"]: r for c in cases for r in c["rows"]}
    studies = {r["study_uid"] for r in by_sop.values()}
    if sha256(zip_path) != OFFICIAL_SHA:
        raise ValueError("official annotation SHA mismatch")
    selected, labels = [], {}
    with ZipFile(zip_path) as archive:
        names = [n for n in archive.namelist() if n.endswith(".json") and not n.startswith("__MACOSX/")]
        if len(names) != 1:
            raise ValueError("expected one annotation JSON")
        with archive.open(names[0]) as stream:
            for raw in array_objects(stream, "labelGroups"):
                group = json.loads(raw)
                for label in group["labels"]:
                    if label["id"] in labels:
                        raise ValueError("duplicate label ID")
                    labels[label["id"]] = {**label, "label_group_id": group["id"], "label_group_name": group["name"]}
        with archive.open(names[0]) as stream:
            for raw in array_objects(stream, "annotations"):
                identity = top_level_metadata(raw, {"StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID", "labelId"})
                sop = identity.get("SOPInstanceUID")
                if sop not in by_sop:
                    continue
                row = by_sop[sop]
                if (identity.get("StudyInstanceUID") != row["study_uid"] or
                        identity.get("SeriesInstanceUID") != row["series_uid"]):
                    raise ValueError("annotation UID parent mismatch")
                label = labels.get(identity.get("labelId"))
                if not label or label["scope"] != "INSTANCE":
                    raise ValueError("only exact approved INSTANCE annotations permitted")
                selected.append(json.loads(raw))
    ids = [a["id"] for a in selected]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate annotation ID")
    return labels, selected



def native_geometry(headers, rows):
    if len(headers) != len(rows) or len({r["sop_uid"] for r in rows}) != len(rows):
        raise ValueError("SOP inventory mismatch")
    for ds, row in zip(headers, rows):
        for tag, field in [("StudyInstanceUID", "study_uid"), ("SeriesInstanceUID", "series_uid"), ("SOPInstanceUID", "sop_uid"), ("PatientID", "patient_id")]:
            if str(ds.get(tag, "")) != row[field]:
                raise ValueError(f"DICOM {tag} mismatch")
        if str(ds.get("Modality", "")) != "CT" or int(ds.get("NumberOfFrames", 1)) != 1:
            raise ValueError("unsupported DICOM modality/frames")
        if not np.isfinite([float(ds.RescaleSlope), float(ds.RescaleIntercept)]).all() or float(ds.RescaleSlope) == 0:
            raise ValueError("invalid HU rescale")
    for tag in ["StudyInstanceUID", "SeriesInstanceUID", "FrameOfReferenceUID"]:
        values = {str(ds.get(tag, "")) for ds in headers}
        if len(values) != 1 or "" in values:
            raise ValueError(f"mixed or missing {tag}")
    if len({(int(ds.Rows), int(ds.Columns)) for ds in headers}) != 1:
        raise ValueError("mixed image sizes")
    result = regular_stack_geometry([ds.ImagePositionPatient for ds in headers],
                                    [ds.ImageOrientationPatient for ds in headers],
                                    [ds.PixelSpacing for ds in headers])
    affine = result["affine_lps"]
    size = [len(headers), int(headers[0].Rows), int(headers[0].Columns)]
    corners = np.array([[0, 0, 0], np.array(size) - 1, (np.array(size) - 1) / 2])
    error = float(np.max(np.abs(inverse_points(transform_points(corners, affine), affine) - corners)))
    if error > 1e-8:
        raise ValueError("native affine roundtrip failure")
    return {"status": "PASS", "shape_krc": size, "order": result["order"].tolist(),
            "affine_lps": affine.tolist(), "inverse_affine_lps": np.linalg.inv(affine).tolist(),
            "spacing_krc_mm": result["spacing_krc_mm"].tolist(),
            "actual_slice_spacings_mm": result["actual_slice_spacings_mm"].tolist(),
            "roundtrip_max_voxel_error": error, "inventory_status": "EXACT_FROZEN_SERIES_SOP_SET",
            "absolute_acquisition_completeness": "UNKNOWN_BEYOND_FROZEN_INVENTORY",
            "resampling": "NONE_NATIVE_GRID", "model_to_native_transform": "NOT_APPLICABLE_NO_MODEL_INPUT"}


def polygon_mask(vertices, shape):
    points = np.asarray(vertices, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3 or not np.isfinite(points).all():
        raise ValueError("INVALID_POLYGON")
    # Remove only exact closure/consecutive duplicates. Require bitmap identity.
    original = points.copy()
    points = points[np.r_[True, np.any(np.diff(points, axis=0) != 0, axis=1)]]
    if len(points) > 1 and np.array_equal(points[0], points[-1]):
        points = points[:-1]
    if len(points) < 3:
        raise ValueError("DEGENERATE_POLYGON")
    rows, columns = shape
    if np.any(points < 0) or np.any(points[:, 0] > columns - 1) or np.any(points[:, 1] > rows - 1):
        raise ValueError("POLYGON_OUT_OF_BOUNDS")
    if np.any(points == 0) or np.any(points[:, 0] == columns - 1) or np.any(points[:, 1] == rows - 1):
        raise ValueError("EDGE_TOUCH_REVIEW_REQUIRED")
    a, b = points, np.roll(points, -1, axis=0)
    if abs(np.sum(a[:, 0] * b[:, 1] - b[:, 0] * a[:, 1])) <= 1e-6:
        raise ValueError("ZERO_AREA_POLYGON")
    # Vectorized all nonadjacent edge relations: crosses, touches, overlaps.
    def cross(u, v):
        return u[..., 0] * v[..., 1] - u[..., 1] * v[..., 0]
    aa, bb, cc, dd = a[:, None], b[:, None], a[None, :], b[None, :]
    t1, t2 = cross(bb - aa, cc - aa), cross(bb - aa, dd - aa)
    t3, t4 = cross(dd - cc, aa - cc), cross(dd - cc, bb - cc)
    eps = 1e-8
    bbox = np.all(np.maximum(np.minimum(aa, bb), np.minimum(cc, dd)) <=
                  np.minimum(np.maximum(aa, bb), np.maximum(cc, dd)) + eps, axis=-1)
    def on_segment(point, start, end):
        return np.all((point >= np.minimum(start, end) - eps) &
                      (point <= np.maximum(start, end) + eps), axis=-1)
    intersects = bbox & (((t1 > eps) & (t2 < -eps) | (t1 < -eps) & (t2 > eps)) &
                         ((t3 > eps) & (t4 < -eps) | (t3 < -eps) & (t4 > eps)) |
                         ((np.abs(t1) <= eps) & on_segment(cc, aa, bb)) |
                         ((np.abs(t2) <= eps) & on_segment(dd, aa, bb)) |
                         ((np.abs(t3) <= eps) & on_segment(aa, cc, dd)) |
                         ((np.abs(t4) <= eps) & on_segment(bb, cc, dd)))
    i, j = np.indices(intersects.shape)
    nonadjacent = (j > i + 1) & ~((i == 0) & (j == len(points) - 1))
    if np.any(intersects & nonadjacent):
        raise ValueError("SELF_INTERSECTION_TOUCH_OR_OVERLAP")
    # Reject adjacent folds; no geometric repair or smoothing is allowed.
    before, after = np.roll(points, 1, axis=0) - points, np.roll(points, -1, axis=0) - points
    if np.any((np.abs(cross(before, after)) <= eps) & (np.sum(before * after, axis=1) > 0)):
        raise ValueError("OVERLAPPING_ADJACENT_EDGES")
    def raster(vertices):
        mask = np.zeros(shape, dtype=bool)
        x0, y0 = np.ceil(vertices.min(axis=0)).astype(int)
        x1, y1 = np.floor(vertices.max(axis=0)).astype(int)
        yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
        inside, boundary = np.zeros(xx.shape, bool), np.zeros(xx.shape, bool)
        for a, b in zip(vertices, np.roll(vertices, -1, axis=0)):
            edge_cross = (b[0] - a[0]) * (yy - a[1]) - (b[1] - a[1]) * (xx - a[0])
            boundary |= ((np.abs(edge_cross) <= 1e-9) & (xx >= min(a[0], b[0])) &
                         (xx <= max(a[0], b[0])) & (yy >= min(a[1], b[1])) & (yy <= max(a[1], b[1])))
            if b[1] != a[1]:
                inside ^= ((a[1] > yy) != (b[1] > yy)) & (xx < (b[0] - a[0]) * (yy - a[1]) / (b[1] - a[1]) + a[0])
        mask[y0:y1 + 1, x0:x1 + 1] = inside | boundary
        return mask
    mask = raster(points)
    if not mask.any() or not np.array_equal(mask, raster(original)):
        raise ValueError("EMPTY_OR_CHANGED_RASTER")
    return mask


def union_key(annotation, label):
    reader = annotation.get("createdById") or "UNKNOWN:" + annotation["id"]
    group = label.get("label_group_id") or "UNKNOWN:" + annotation["id"]
    return label["name"], reader, group, annotation["labelId"]


def category_unions(items):
    """Do not cross category, creator, or label-group boundaries."""
    grouped = {}
    for annotation, label, mask in items:
        key = union_key(annotation, label)
        if label["name"] not in INFECTION_CLASSES | NONINFECTION_CLASSES:
            raise ValueError("UNKNOWN_MEDICAL_CATEGORY")
        grouped[key] = mask.copy() if key not in grouped else grouped[key] | mask
    return grouped


def render_overlay(ds, items, path, caption):
    pixels = np.asarray(ds.pixel_array)
    if pixels.shape != (int(ds.Rows), int(ds.Columns)):
        raise ValueError("DECODED_GRID_MISMATCH")
    hu = pixels.astype(float) * float(ds.RescaleSlope) + float(ds.RescaleIntercept)
    if not np.isfinite(hu).all():
        raise ValueError("NONFINITE_HU")
    gray = np.uint8(np.clip((hu + 1350) / 1500, 0, 1) * 255)
    base = Image.fromarray(gray).convert("RGB")
    rgb = np.repeat(gray[..., None], 3, axis=2).astype(float)
    palette = [(255, 112, 64), (64, 220, 255), (255, 220, 64), (200, 128, 255), (64, 240, 130)]
    for index, (_, _, mask) in enumerate(items):
        rgb[mask] = 0.65 * rgb[mask] + 0.35 * np.array(palette[index % len(palette)])
    overlay = Image.fromarray(np.uint8(rgb))
    draw = ImageDraw.Draw(overlay)
    for index, (annotation, _, _) in enumerate(items):
        points = [tuple(p) for p in annotation["data"]["vertices"]]
        draw.line(points + points[:1], fill=palette[index % len(palette)], width=1)
    canvas = Image.new("RGB", (int(ds.Columns) * 2, int(ds.Rows) + 44), (20, 24, 30))
    canvas.paste(base, (0, 44)); canvas.paste(overlay, (int(ds.Columns), 44))
    ImageDraw.Draw(canvas).text((8, 7), caption, fill="white")
    canvas.save(path)
    return {"status": "GENERATED_NOT_CLINICALLY_ADJUDICATED", "stored_min_max": [int(pixels.min()), int(pixels.max())],
            "hu_min_max": [float(hu.min()), float(hu.max())], "window_center_width": [-600, 1500],
            "sha256": sha256(path)}


def native_volume(headers, rows, geometry, source_root, folder):
    """Decode only the approved series; save native HU, ordered SOP and ledger."""
    if geometry["status"] != "PASS":
        return {"status": "QUARANTINED", "reason": "HEADER_GEOMETRY_FAILED", "path": None}
    volume_path = folder / "native-hu.npy"
    volume = np.lib.format.open_memmap(volume_path, mode="w+", dtype=np.float32, shape=tuple(geometry["shape_krc"]))
    pixel_ledger = []
    try:
        for native_index, original_index in enumerate(geometry["order"]):
            row = rows[original_index]; header = headers[original_index]
            path = source_root / row["image_path"]
            before_hash = sha256(path)
            ds = pydicom.dcmread(path)
            for tag in ["StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID", "PatientID", "Rows", "Columns",
                        "FrameOfReferenceUID", "ImagePositionPatient", "ImageOrientationPatient", "PixelSpacing",
                        "RescaleSlope", "RescaleIntercept"]:
                if ds.get(tag) != header.get(tag):
                    raise ValueError("DICOM_CHANGED_SINCE_HEADER_QA:" + tag)
            stored = np.asarray(ds.pixel_array)
            if stored.shape != tuple(geometry["shape_krc"][1:]) or not np.isfinite(stored).all():
                raise ValueError("DECODED_NATIVE_GRID_INVALID")
            hu = stored.astype(np.float32) * float(ds.RescaleSlope) + float(ds.RescaleIntercept)
            if not np.isfinite(hu).all() or before_hash != sha256(path):
                raise ValueError("NONFINITE_HU_OR_CHANGED_DICOM_BYTES")
            volume[native_index] = hu
            padding = int(ds.PixelPaddingValue) if "PixelPaddingValue" in ds else None
            pixel_ledger.append({"native_slice_index": native_index, "SOPInstanceUID": row["sop_uid"],
                                 "ct_sha256": before_hash, "ct_reference_relative": row["image_path"],
                                 "RescaleSlope": float(ds.RescaleSlope), "RescaleIntercept": float(ds.RescaleIntercept),
                                 "stored_min_max": [int(stored.min()), int(stored.max())],
                                 "hu_min_max": [float(hu.min()), float(hu.max())],
                                 "PixelPaddingValue": padding, "PixelPaddingRangeLimit": int(ds.PixelPaddingRangeLimit) if "PixelPaddingRangeLimit" in ds else None,
                                 "padding_status": "DECLARED_VALUE_PRESERVED_NO_MASK_DERIVED" if padding is not None else "PADDING_METADATA_UNKNOWN"})
        volume.flush(); del volume
        return {"status": "TECHNICAL_PASS", "path": volume_path.name, "sha256": sha256(volume_path),
                "shape_krc": geometry["shape_krc"], "dtype": "float32", "units": "DICOM_RESCALED_HU",
                "windowing": "NONE", "resampling": "NONE_NATIVE_GRID", "ordered_sop_uids": [r["SOPInstanceUID"] for r in pixel_ledger],
                "pixel_ledger": pixel_ledger, "model_input_mapping": None, "inverse_resampling_transform": None,
                "missing_padding_policy": "UNKNOWN_NO_INFERRED_PADDING_MASK"}
    except Exception as error:
        volume.flush(); del volume
        quarantine_path = folder / "quarantined-partial-native-hu.npy"
        volume_path.rename(quarantine_path)
        return {"status": "QUARANTINED", "reason": f"{type(error).__name__}: {error}", "path": None,
                "quarantined_partial_path": quarantine_path.name, "completed_sops": len(pixel_ledger)}


def build(args):
    os.umask(0o077)
    cases, source_root, delivery = authorized_cases(args.delivery, args.delivery_sha256)
    output = args.output.resolve()
    # Private ignored DATA-EVAL location only; refuse any existing output tree.
    worktree = Path(__file__).resolve().parents[3]
    if not output.is_relative_to(worktree / ".local") or output.exists():
        raise ValueError("output must be a fresh private DATA-EVAL .local directory")
    base = args.annotation_base.resolve(strict=True)
    labels, annotations = selected_annotations(base / "original/annotations.zip", cases)
    # Clinical XLSX/Study-scoped bodies are outside this exact SOP access
    # contract. Preserve UNKNOWN; do not decode the full table to select rows.
    preview_ids = {c["patient_id"] for c in cases}
    output.mkdir(parents=True)
    (output / "cases").mkdir(); (output / "overlays").mkdir()
    by_sop = defaultdict(list)
    for annotation in annotations:
        label = labels[annotation["labelId"]]
        if label["scope"] == "INSTANCE":
            by_sop[annotation["SOPInstanceUID"]].append(annotation)
    summaries, overlay_entries = [], []
    for number, case in enumerate(cases, 1):
        pid = case["patient_id"]
        case_id = hashlib.sha256(pid.encode()).hexdigest()[:20]
        folder = output / "cases" / case_id; folder.mkdir()
        headers = []
        geometry = None
        try:
            headers = [pydicom.dcmread(source_root / row["image_path"], stop_before_pixels=True) for row in case["rows"]]
            geometry = native_geometry(headers, case["rows"])
        except Exception as error:
            geometry = {"status": "QUARANTINED", "reason": f"{type(error).__name__}: {error}"}
        volume = native_volume(headers, case["rows"], geometry, source_root, folder)
        counts = Counter(); reasons = Counter(); records = []; sop_records = []; overlay_options = []
        order = geometry.get("order", list(range(len(case["rows"]))))
        index_by_sop = {case["rows"][index]["sop_uid"]: k for k, index in enumerate(order)}
        for index, row in enumerate(case["rows"]):
            sop = row["sop_uid"]; raw = by_sop[sop]; accepted = []
            counts["raw_instances"] += len(raw)
            counts["raw_polygons"] += sum(labels[a["labelId"]].get("annotationMode") == "freeform" and isinstance(a.get("data"), dict) and "vertices" in a["data"] for a in raw)
            counts["annotated_sops"] += bool(raw)
            counts["single_polygon_sops"] += len(raw) == 1; counts["multi_polygon_sops"] += len(raw) > 1
            ds = headers[index] if len(headers) == len(case["rows"]) else None
            identity = {"StudyInstanceUID": row["study_uid"], "SeriesInstanceUID": row["series_uid"], "SOPInstanceUID": sop}
            header = ({"ImagePositionPatient": list(map(float, ds.ImagePositionPatient)),
                       "ImageOrientationPatient": list(map(float, ds.ImageOrientationPatient)),
                       "PixelSpacing": list(map(float, ds.PixelSpacing)), "Rows": int(ds.Rows), "Columns": int(ds.Columns),
                       "RescaleSlope": float(ds.RescaleSlope), "RescaleIntercept": float(ds.RescaleIntercept),
                       "SliceThickness": float(ds.SliceThickness) if "SliceThickness" in ds else None,
                       "FrameOfReferenceUID": str(ds.get("FrameOfReferenceUID", "")),
                       "TransferSyntaxUID": str(ds.file_meta.TransferSyntaxUID)} if ds is not None and geometry["status"] == "PASS" else None)
            for annotation in raw:
                label = labels[annotation["labelId"]]
                record = {"annotation_id": annotation["id"], "raw_annotation": annotation, "raw_label": label,
                          "identity": identity, "lesion_identity": "UNKNOWN", "annotation_completeness": "UNKNOWN",
                          "coordinate_convention": "original MD.ai x=column,y=row zero-based pixel coordinates",
                          "world_coordinate_source": "DERIVED_FROM_EXACT_DICOM; official JSON has no independent LPS vertices"}
                try:
                    if geometry["status"] != "PASS":
                        raise ValueError("SERIES_GEOMETRY_QUARANTINED")
                    if label["name"] not in INFECTION_CLASSES | NONINFECTION_CLASSES or label.get("annotationMode") != "freeform":
                        raise ValueError("UNKNOWN_CATEGORY_OR_MODE")
                    if (annotation["height"], annotation["width"]) != (int(ds.Rows), int(ds.Columns)):
                        raise ValueError("ANNOTATION_GRID_MISMATCH")
                    vertices = annotation.get("data", {}).get("vertices")
                    mask = polygon_mask(vertices, (int(ds.Rows), int(ds.Columns)))
                    native_points = np.c_[np.zeros(len(vertices)), np.asarray(vertices)[:, 1], np.asarray(vertices)[:, 0]]
                    record["vertices_lps_mm"] = transform_points(native_points, slice_affine_lps(ds.ImagePositionPatient, ds.ImageOrientationPatient, ds.PixelSpacing)).tolist()
                    filename = hashlib.sha256(annotation["id"].encode()).hexdigest()[:24] + ".png"
                    Image.fromarray(mask).save(folder / filename)
                    y, x = np.where(mask)
                    record.update(status="PASS", mask_path=str((folder / filename).relative_to(output)),
                                  mask_sha256=sha256(folder / filename), area_pixels=int(mask.sum()),
                                  box_xyxy_half_open=[int(x.min()), int(y.min()), int(x.max()) + 1, int(y.max()) + 1])
                    accepted.append((annotation, label, mask)); counts["accepted_polygons"] += 1
                    counts["category:" + label["name"]] += 1
                except Exception as error:
                    reason = str(error)
                    record.update(status="QUARANTINED", reason=reason); reasons[reason] += 1
                records.append(record)
            unions = []
            for union_number, (key, mask) in enumerate(category_unions(accepted).items()):
                filename = f"union-{index:04d}-{union_number}.png"; Image.fromarray(mask).save(folder / filename)
                unions.append({"category": key[0], "createdById": key[1], "label_group_id": key[2], "labelId": key[3],
                               "mask_path": str((folder / filename).relative_to(output)), "mask_sha256": sha256(folder / filename),
                               "area_pixels": int(mask.sum()), "source_annotation_ids": [a["id"] for a, l, _ in accepted if union_key(a, l) == key],
                               "semantics": "same creator/category/group annotated region union; no consensus or lesion ID"})
            sop_records.append({**identity, "native_slice_index": index_by_sop[sop], "native_header": header,
                                "ct_reference_relative": row["image_path"], "raw_polygon_count": len(raw),
                                "accepted_polygon_count": len(accepted), "category_unions": unions,
                                "coverage_status": "ANNOTATED_PARTIAL_REFERENCE" if raw else "NO_POLYGON_ANNOTATION_UNKNOWN",
                                "unannotated_region_status": "UNKNOWN", "annotation_complete": False})
            infectious = [(a, l, m) for a, l, m in accepted if l["name"] in INFECTION_CLASSES]
            if infectious:
                overlay_options.append((index, accepted, len(infectious), len({l["name"] for _, l, _ in accepted})))
        selected_previews = []
        if pid in preview_ids and geometry["status"] == "PASS" and volume["status"] == "TECHNICAL_PASS":
            # Structural choices only, independent of algorithm output or area.
            options = sorted(overlay_options, key=lambda x: x[0]); used = set()
            selectors = [lambda x: (x[2] != 1, x[0]), lambda x: (-x[2], x[0]), lambda x: (-x[3], x[0])]
            for ordinal, selector in enumerate(selectors):
                available = [x for x in options if x[0] not in used]
                if not available:
                    continue
                index, items, _, _ = min(available, key=selector); used.add(index)
                row = case["rows"][index]; overlay_path = output / "overlays" / f"{case_id}-{ordinal}.png"
                entry = {"patient_id": pid, "SOPInstanceUID": row["sop_uid"], "path": str(overlay_path.relative_to(output)),
                         "annotation_ids": [a["id"] for a, _, _ in items]}
                try:
                    ds = pydicom.dcmread(source_root / row["image_path"])
                    native_geometry([ds, headers[(index + 1) % len(headers)]], [row, case["rows"][(index + 1) % len(headers)]])
                    entry["ct_file_sha256"] = sha256(source_root / row["image_path"])
                    entry.update(render_overlay(ds, items, overlay_path, f"{case_id} | native CT / official polygons | n={len(items)}"))
                except Exception as error:
                    entry.update(status="QUARANTINED", reason=f"{type(error).__name__}: {error}")
                selected_previews.append(entry); overlay_entries.append(entry)
        study_uids = {r["study_uid"] for r in case["rows"]}
        patient_doc = {"schema": "RICORD_GT_VNEXT_DEVELOPMENT_CASE_V1", "patient_id": pid, "split": case["split"],
                       "development_used": True, "independent_test_eligible": False,
                       "authorization": case["authorization"], "geometry": geometry, "native_volume": volume, "annotation_completeness": "UNKNOWN",
                       "clinical_validity": "CLINICAL_VALIDITY_NOT_ADJUDICATED", "lesion_count": None,
                       "label_evidence": {"collection_proxy": 1, "clinical_result": None, "clinical_source_recheck": "NOT RUN_OUTSIDE_EXACT_SOP_SCOPE", "clinical_adjudication": "NOT_ADJUDICATED"},
                       "sops": sop_records, "annotations": records, "statistics": dict(counts),
                       "quarantine_reasons": dict(reasons), "overlays": selected_previews}
        save_json(folder / "manifest.json", patient_doc)
        summaries.append({"case_id": case_id, "patient_id": pid, "split": case["split"], "sop_count": len(case["rows"]),
                          "geometry_status": geometry["status"], "geometry_reason": geometry.get("reason"),
                          "native_volume_status": volume["status"], "native_volume_reason": volume.get("reason"),
                          "manifest_path": str((folder / "manifest.json").relative_to(output)), "manifest_sha256": sha256(folder / "manifest.json"),
                          "statistics": dict(counts), "quarantine_reasons": dict(reasons)})
        print(json.dumps({"processed": number, "total": len(cases), "geometry": geometry["status"], "polygons": counts["raw_polygons"], "accepted": counts["accepted_polygons"]}), flush=True)
    aggregate = Counter(); quarantine = Counter()
    for case in summaries:
        aggregate.update(case["statistics"]); quarantine.update(case["quarantine_reasons"])
    manifest = {"schema": "RICORD_GT_VNEXT_DEVELOPMENT_MANIFEST_V1", "status": "DEVELOPMENT_REFERENCE_WITH_QUARANTINE",
                "source_annotation_sha256": OFFICIAL_SHA, "clinical_source_recheck": "NOT RUN_OUTSIDE_EXACT_SOP_SCOPE",
                "allowlist_sha256": delivery["allowlist_sha256"], "delivery_path": str(args.delivery.resolve()), "delivery_sha256": args.delivery_sha256,
                "frozen_split_sha256": {s: SPLIT_SHA[s] for s in sorted({c["split"] for c in cases})},
                "script_sha256": sha256(Path(__file__)), "pillow_version": pillow_version,
                "rasterization": "integer native pixel-centre even-odd interior; exact boundary included; continuous raw vertices preserved; no coordinate rounding",
                "annotation_access": "shared ZIP container scanned; only allowlisted bodies JSON-decoded; no sealed GT or test manifest opened",
                "unannotated_region_status": "UNKNOWN", "complete_metrics_eligible": False,
                "clinical_validity": "CLINICAL_VALIDITY_NOT_ADJUDICATED", "independent_test_eligible": False,
                "counts": {"patients": len(cases), "sops": sum(c["sop_count"] for c in summaries), **aggregate},
                "geometry_status_counts": dict(Counter(c["geometry_status"] for c in summaries)),
                "native_volume_status_counts": dict(Counter(c["native_volume_status"] for c in summaries)),
                "quarantine_reasons": dict(quarantine), "cases": summaries, "overlays": overlay_entries}
    save_json(output / "manifest.json", manifest)
    cards = []
    for entry in overlay_entries:
        if entry.get("sha256"):
            cards.append(f'<figure><img src="{html.escape(entry["path"])}"><figcaption>{html.escape(entry["patient_id"])} · {len(entry["annotation_ids"])} polygon objects · native CT left / overlay right</figcaption></figure>')
    (output / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>GT-vNext native overlay QA</title><style>body{background:#14181e;color:#eef;font:16px system-ui;max-width:1150px;margin:30px auto}img{width:100%}figure{margin:20px 0}figcaption{padding:12px}</style><h1>GT-vNext · real development CT</h1><p>Official partial annotations. Blank regions UNKNOWN. Local visual QA, no clinical adjudication. C=-600/W=1500, no resampling.</p>' + "".join(cards), encoding="utf-8")
    print(json.dumps({"manifest": str(output / "manifest.json"), "sha256": sha256(output / "manifest.json"), "counts": manifest["counts"], "geometry": manifest["geometry_status_counts"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery", type=Path, required=True)
    parser.add_argument("--delivery-sha256", required=True)
    parser.add_argument("--annotation-base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args())
