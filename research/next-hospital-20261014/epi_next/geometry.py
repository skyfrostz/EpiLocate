"""DICOM geometry in millimetres and LPS; arrays use (slice, row, column).

This module handles regular parallel stacks only and fails closed on nonuniform
spacing, gantry tilt, orientation changes, or missing/duplicate positions.
SliceThickness and InstanceNumber are deliberately not used for geometry.
"""
from __future__ import annotations

import numpy as np


def _finite(value, shape, name):
    a = np.asarray(value, dtype=float)
    if a.shape != shape or not np.isfinite(a).all():
        raise ValueError(f"invalid {name}")
    return a


def _directions(orientation, tolerance=1e-5):
    a = _finite(orientation, (6,), "ImageOrientationPatient")
    col, row = a[:3], a[3:]
    if (abs(np.linalg.norm(col) - 1) > tolerance or
            abs(np.linalg.norm(row) - 1) > tolerance or abs(col @ row) > tolerance):
        raise ValueError("orientation must contain orthonormal direction cosines")
    return col, row, np.cross(col, row)


def slice_affine_lps(position, orientation, pixel_spacing) -> np.ndarray:
    """Map (normal_mm, row, column, 1) to LPS millimetres.

    DICOM IOP first triplet follows increasing column; PixelSpacing first value
    follows increasing row. Pixel centres use zero-based indices, no half shift.
    """
    col, row, normal = _directions(orientation)
    spacing = _finite(pixel_spacing, (2,), "PixelSpacing")
    if np.any(spacing <= 0):
        raise ValueError("PixelSpacing must be positive")
    affine = np.eye(4)
    affine[:3, :3] = np.column_stack((normal, row * spacing[0], col * spacing[1]))
    affine[:3, 3] = _finite(position, (3,), "ImagePositionPatient")
    return affine


def transform_points(points, affine) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    affine = _finite(affine, (4, 4), "affine")
    if points.ndim < 1 or points.shape[-1] != 3 or not np.isfinite(points).all():
        raise ValueError("points must end in three finite coordinates")
    if not np.allclose(affine[3], [0, 0, 0, 1], rtol=0, atol=1e-12):
        raise ValueError("only affine transforms are supported")
    return points @ affine[:3, :3].T + affine[:3, 3]


def inverse_points(points, affine) -> np.ndarray:
    affine = _finite(affine, (4, 4), "affine")
    try:
        inverse = np.linalg.inv(affine)
    except np.linalg.LinAlgError as exc:
        raise ValueError("singular affine") from exc
    return transform_points(points, inverse)


def regular_stack_geometry(positions, orientations, pixel_spacings, *,
                           tolerance_mm=1e-3) -> dict:
    """Validate a stack and return its sort order, affine, and measured spacing.

    Single-slice stacks cannot establish slice spacing and are rejected. Larger
    regular gaps cannot be detected without an independent expected inventory.
    """
    positions = np.asarray(positions, dtype=float)
    if positions.ndim != 2 or positions.shape[1] != 3 or len(positions) < 2:
        raise ValueError("at least two slice positions are required")
    n = len(positions)
    positions = _finite(positions, (n, 3), "positions")
    orientations = _finite(orientations, (n, 6), "orientations")
    pixel_spacings = _finite(pixel_spacings, (n, 2), "pixel spacings")
    if not np.isfinite(tolerance_mm) or tolerance_mm <= 0:
        raise ValueError("positive finite tolerance is required")
    for orientation in orientations:
        _directions(orientation)
    if not np.allclose(orientations, orientations[0], atol=1e-5, rtol=0):
        raise ValueError("inconsistent slice orientation")
    if np.any(pixel_spacings <= 0) or not np.allclose(pixel_spacings, pixel_spacings[0], atol=1e-6, rtol=0):
        raise ValueError("inconsistent or nonpositive pixel spacing")
    _, _, normal = _directions(orientations[0])
    projection = positions @ normal
    order = np.argsort(projection, kind="stable")
    differences = np.diff(projection[order])
    if np.any(differences <= tolerance_mm):
        raise ValueError("duplicate or unresolved slice position")
    spacing = float(np.median(differences))
    if not np.allclose(differences, spacing, atol=tolerance_mm, rtol=0):
        raise ValueError("nonuniform slice spacing or possible missing slices")
    deltas = np.diff(positions[order], axis=0)
    if np.max(np.linalg.norm(deltas - differences[:, None] * normal, axis=1)) > tolerance_mm:
        raise ValueError("gantry tilt or in-plane slice drift is unsupported")
    affine = slice_affine_lps(positions[order[0]], orientations[0], pixel_spacings[0])
    affine[:3, 0] *= spacing
    return {"axis_convention": "slice,row,column", "world_convention": "LPS_mm",
            "order": order, "affine_lps": affine,
            "spacing_krc_mm": np.r_[spacing, pixel_spacings[0]],
            "actual_slice_spacings_mm": differences,
            "completeness_status": "REQUIRES_EXPECTED_SOP_INVENTORY"}
