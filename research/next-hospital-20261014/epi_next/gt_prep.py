"""GT-vNext preparation primitives tested on synthetic data only.

No file access, DICOM decode, archive parsing, model access, or authorization
grant occurs here. Real annotation objects must be filtered by an independently
approved exact Study/Series/SOP allowlist BEFORE calling these functions.
"""
from __future__ import annotations

import hashlib
import json
import re

import numpy as np


def pending_authorization_template(proposal_sha256: str) -> dict:
    """A request template is not permission; it defaults to no permitted access."""
    if not isinstance(proposal_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", proposal_sha256):
        raise ValueError("exact proposal SHA-256 required")
    return {
        "schema": "EPI-NEXT-EXACT-DATA-APPROVAL-1", "status": "PENDING",
        "proposal_sha256": proposal_sha256, "approver": None, "approved_at": None,
        "approval_evidence_reference": None,
        "approved_scope": [], "permit_pixel_decode": False,
        "permit_annotation_bodies": False, "permit_remote_transfer": False,
        "permit_training": False, "permit_gpu": False,
        "sealed_test_permitted": False,
        "note": "Human approval must name exact proposal hash and access scope; this template grants nothing.",
    }


def _cross(a, b, c):
    delta, offset = b - a, c - a
    return float(delta[0] * offset[1] - delta[1] * offset[0])


def _on_segment(p, a, b, eps=1e-9):
    return abs(_cross(a, b, p)) <= eps and bool(np.all(p >= np.minimum(a, b) - eps) and
                                               np.all(p <= np.maximum(a, b) + eps))


def _intersects(a, b, c, d):
    ab_c, ab_d, cd_a, cd_b = _cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b)
    if ab_c * ab_d < 0 and cd_a * cd_b < 0:
        return True
    return any((_on_segment(c, a, b), _on_segment(d, a, b),
                _on_segment(a, c, d), _on_segment(b, c, d)))


def rasterize_native_polygon(vertices_xy, shape_rc) -> dict:
    """Rasterize a simple polygon using integer pixel-centre samples.

    Vertices use zero-based x=column/y=row coordinates; boundary pixel centres
    are included. Coordinates outside [0, columns-1] x [0, rows-1] are rejected,
    never clipped. Actual export conventions require an independent overlay QA.
    """
    if (len(shape_rc) != 2 or any(type(x) is not int or x < 1 for x in shape_rc)):
        raise ValueError("shape must be positive integer (rows, columns)")
    vertices = np.asarray(vertices_xy, dtype=float)
    if vertices.ndim != 2 or vertices.shape[1] != 2 or not np.isfinite(vertices).all():
        raise ValueError("vertices must be finite Nx2 coordinates")
    if len(vertices) > 1 and np.array_equal(vertices[0], vertices[-1]):
        vertices = vertices[:-1]
    if not 3 <= len(vertices) <= 1024:
        raise ValueError("polygon requires 3..1024 vertices")
    if len(np.unique(vertices, axis=0)) != len(vertices):
        raise ValueError("duplicate polygon vertices")
    rows, columns = shape_rc
    upper = np.array([columns - 1, rows - 1])
    if np.any(vertices < 0) or np.any(vertices > upper):
        raise ValueError("polygon outside native grid")
    n = len(vertices)
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            if _intersects(vertices[i], vertices[(i + 1) % n],
                           vertices[j], vertices[(j + 1) % n]):
                raise ValueError("self-intersecting or touching polygon")
    # Adjacent edges may meet, but cannot fold back over each other.
    for i in range(n):
        before, point, after = vertices[i - 1], vertices[i], vertices[(i + 1) % n]
        if abs(_cross(before, point, after)) <= 1e-9 and (before - point) @ (after - point) > 0:
            raise ValueError("overlapping adjacent edges")
    area2 = abs(float(np.sum(vertices[:, 0] * np.roll(vertices[:, 1], -1) -
                             vertices[:, 1] * np.roll(vertices[:, 0], -1))))
    if area2 <= 1e-9:
        raise ValueError("zero-area polygon")
    mask = np.zeros(shape_rc, dtype=bool)
    x0, y0 = np.ceil(vertices.min(axis=0)).astype(int)
    x1, y1 = np.floor(vertices.max(axis=0)).astype(int)
    yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
    inside, boundary = np.zeros(xx.shape, bool), np.zeros(xx.shape, bool)
    for a, b in zip(vertices, np.roll(vertices, -1, axis=0)):
        cross = (b[0] - a[0]) * (yy - a[1]) - (b[1] - a[1]) * (xx - a[0])
        boundary |= ((np.abs(cross) <= 1e-9) & (xx >= min(a[0], b[0])) &
                     (xx <= max(a[0], b[0])) & (yy >= min(a[1], b[1])) &
                     (yy <= max(a[1], b[1])))
        if b[1] != a[1]:
            inside ^= ((a[1] > yy) != (b[1] > yy)) & (
                xx < (b[0] - a[0]) * (yy - a[1]) / (b[1] - a[1]) + a[0])
    mask[y0:y1 + 1, x0:x1 + 1] = inside | boundary
    if not mask.any():
        raise ValueError("polygon has no covered native pixel centres")
    touches_edge = bool(np.any(vertices == 0) or np.any(vertices == upper))
    return {"mask": mask, "vertices_xy": vertices.tolist(),
            "coordinate_convention": "ZERO_BASED_NATIVE_PIXEL_CENTRES_XY_BOUNDARY_INCLUDED",
            "geometry_status": "EDGE_TOUCH_REVIEW_REQUIRED" if touches_edge else "SYNTHETIC_GEOMETRY_PASS"}


def prepare_sop_reference(objects: list[dict], *, shape_rc: tuple[int, int],
                          study_uid: str, series_uid: str, sop_uid: str,
                          approved_categories: set[str]) -> dict:
    """Keep every source object; union only unambiguous reader/category/group.

    Missing reader or group keeps an object separate. Group unions are technical
    sensitivity representations, never lesion identity or reader consensus.
    Edge-touch polygons retain a mask for review but are excluded from unions.
    Invalid polygons and non-target categories remain explicit rejected entries.
    """
    expected = (study_uid, series_uid, sop_uid)
    if any(not isinstance(x, str) or not x for x in expected):
        raise ValueError("explicit Study/Series/SOP identity required")
    if not approved_categories or any(not isinstance(x, str) or not x for x in approved_categories):
        raise ValueError("explicit nonempty approved categories required")
    ids = [o.get("annotation_id") for o in objects]
    if any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
        raise ValueError("source annotation IDs must be nonempty and unique")
    output, groups = [], {}
    for obj in objects:
        if tuple(obj.get(k) for k in ("study_uid", "series_uid", "sop_uid")) != expected:
            raise ValueError("annotation identity does not match approved SOP")
        # JSON source snapshot is retained verbatim semantically, not a fabricated GT.
        source = json.loads(json.dumps(obj, allow_nan=False))
        source_hash = hashlib.sha256(json.dumps(source, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        entry = {"source": source, "source_object_sha256": source_hash,
                 "annotation_id": obj["annotation_id"], "mask": None,
                 "status": "NOT_EVALUATED", "reason": None}
        if obj.get("category") not in approved_categories:
            entry.update(status="CATEGORY_OUT_OF_SCOPE", reason="not a preapproved target category")
        else:
            try:
                raster = rasterize_native_polygon(obj.get("vertices_xy"), shape_rc)
                entry.update(mask=raster["mask"], status=raster["geometry_status"],
                             coordinate_convention=raster["coordinate_convention"])
            except (ValueError, TypeError) as exc:
                entry.update(status="INVALID_POLYGON", reason=str(exc))
        output.append(entry)
        if entry["status"] != "SYNTHETIC_GEOMETRY_PASS":
            continue
        reader, category, group = obj.get("reader_id"), obj["category"], obj.get("group_id")
        if isinstance(reader, str) and reader and isinstance(group, str) and group:
            key = (reader, category, group, None)
        else:
            key = (None, category, None, obj["annotation_id"])
        if key not in groups:
            groups[key] = {"reader_id": reader, "category": category, "group_id": group,
                           "annotation_ids": [], "mask": np.zeros(shape_rc, bool),
                           "meaning": "WITHIN_READER_CATEGORY_GROUP_SENSITIVITY" if key[3] is None else "SINGLE_OBJECT_UNKNOWN_RELATIONSHIP"}
        groups[key]["mask"] |= entry["mask"]
        groups[key]["annotation_ids"].append(obj["annotation_id"])
    return {"schema": "EPI-NEXT-GT-vNext-PREP-1", "status": "NO_POLYGON_ANNOTATION" if not objects else "PREPARED_REQUIRES_NATIVE_OVERLAY_QA",
            "annotation_completeness": "UNKNOWN", "clinical_validity": "NOT_ADJUDICATED",
            "objects": output, "sensitivity_groups": list(groups.values()),
            "whole_sop_union": None, "consensus_mask": None,
            "full_reference_metrics_eligible": False}
