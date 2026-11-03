"""Explicitly authorized, hash-locked CT loading and regular-grid resampling.

An approval is a trusted coordinator input, not a signature or access sandbox.
This module never discovers patients, selects cases, or infers clinical labels.
Only the exact files in a reviewed inventory may be opened. No production use
or real-data validation is implied by the generated-DICOM tests.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np

from .contracts import VolumeRecord, require_hash
from .geometry import regular_stack_geometry


def load_approved_inventory(path, *, approved_sha256: str) -> dict:
    """Coordinator must supply the hash explicitly approved by the human.

    The expected hash must not be copied automatically from the same input file.
    Approval status alone is deliberately insufficient.
    """
    require_hash(approved_sha256, "externally approved inventory hash")
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != approved_sha256:
        raise ValueError("inventory differs from externally approved bytes")
    approval = json.loads(raw)
    validate_approval(approval)
    return approval


def validate_approval(approval):
    if (approval.get("schema") != "EPI-NEXT-CT-ACCESS-1"
            or approval.get("status") != "APPROVED"
            or not approval.get("approval_reference")
            or approval.get("scope") != "local_ct_pixels_and_headers"):
        raise PermissionError("explicit local CT authorization is required")
    require_hash(approval.get("split_manifest_sha256"), "split manifest hash")
    require_hash(approval.get("label_definition_sha256"), "label definition hash")
    if not isinstance(approval.get("cases"), list) or not approval["cases"]:
        raise ValueError("approval requires explicit cases")
    seen = set()
    for case in approval["cases"]:
        key = (case.get("patient_id"), case.get("series_uid"))
        if key in seen or not all(key):
            raise ValueError("missing or duplicate case identity")
        seen.add(key)
        if case.get("split") not in {"train", "observed_validation"}:
            raise PermissionError("sealed or unknown split is forbidden")
        if (not case.get("study_uid") or not case.get("dicom_patient_id")
                or not case.get("label_definition_id") or not case.get("task_labels")):
            raise ValueError("header identity and explicit label provenance required")
        if case.get("padding_policy") not in {"require_dicom_tag", "allow_absent_tag"}:
            raise ValueError("padding policy must be explicitly approved")
        if case.get("hu_policy") != "ct_linear_rescale_hu":
            raise ValueError("explicit HU conversion policy required")
        files = case.get("files", [])
        if len(files) < 2 or len({f.get("sop_uid") for f in files}) != len(files):
            raise ValueError("complete unique SOP inventory required")
        for f in files:
            if not f.get("sop_uid") or not Path(f.get("path", "")).is_absolute():
                raise ValueError("exact absolute file paths and SOPs required")
            require_hash(f.get("sha256"), "DICOM file hash")


def read_ct_volume(approval, patient_id, series_uid, *, max_voxels=64_000_000,
                   max_file_bytes=32_000_000) -> VolumeRecord:
    """Read one approved conventional CT stack; reject enhanced/tilted CT.

    Before pixel decode, every header and geometry is checked. Valid support
    excludes explicit padding only; it is NOT a lung mask. Unavailable padding
    metadata is recorded, never interpreted as proof that padding is absent.
    """
    validate_approval(approval)  # Must precede any clinical file access.
    matches = [c for c in approval["cases"] if c["patient_id"] == patient_id
               and c["series_uid"] == series_uid]
    if len(matches) != 1:
        raise PermissionError("case is absent from approved inventory")
    if type(max_voxels) is not int or max_voxels <= 0 or type(max_file_bytes) is not int or max_file_bytes <= 0:
        raise ValueError("positive integer resource limits required")
    import pydicom
    case = matches[0]
    headers, paths, hashes = [], [], []
    shape = None
    for entry in case["files"]:
        path = Path(entry["path"])
        if path.stat().st_size > max_file_bytes:
            raise ValueError("DICOM file exceeds memory budget")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != entry["sha256"]:
            raise ValueError("DICOM file hash mismatch")
        # Header parsing from exact verified bytes prevents a path replacement
        # between the hash check and header read.
        import io
        ds = pydicom.dcmread(io.BytesIO(raw), stop_before_pixels=True)
        if (str(ds.get("PatientID", "")) != case["dicom_patient_id"]
                or str(ds.get("StudyInstanceUID", "")) != case["study_uid"]
                or str(ds.get("SeriesInstanceUID", "")) != series_uid
                or str(ds.get("SOPInstanceUID", "")) != entry["sop_uid"]):
            raise ValueError("DICOM header differs from approved identity")
        if (ds.get("Modality") != "CT" or int(ds.get("NumberOfFrames", 1)) != 1
                or ds.get("PhotometricInterpretation") != "MONOCHROME2"
                or int(ds.get("SamplesPerPixel", 0)) != 1
                or "LOCALIZER" in ds.get("ImageType", [])):
            raise ValueError("unsupported CT encoding or localizer")
        current = (int(ds.Rows), int(ds.Columns))
        if min(current) <= 0 or (shape is not None and shape != current):
            raise ValueError("inconsistent pixel matrix")
        shape = current
        if len(case["files"]) * shape[0] * shape[1] > max_voxels:
            raise ValueError("CT volume exceeds voxel budget")
        slope, intercept = float(ds.RescaleSlope), float(ds.RescaleIntercept)
        if not np.isfinite([slope, intercept]).all() or slope == 0:
            raise ValueError("invalid HU rescale")
        if str(ds.get("RescaleType", "HU")).upper() != "HU":
            raise ValueError("non-HU rescale type")
        if "PixelPaddingRangeLimit" in ds and "PixelPaddingValue" not in ds:
            raise ValueError("padding range has no base value")
        if "PixelPaddingValue" not in ds and case["padding_policy"] == "require_dicom_tag":
            raise ValueError("required padding metadata missing")
        headers.append(ds)
        paths.append(path)
        hashes.append(digest)
    geometry = regular_stack_geometry([d.ImagePositionPatient for d in headers],
        [d.ImageOrientationPatient for d in headers], [d.PixelSpacing for d in headers])
    volume = np.empty((len(headers), *shape), dtype=np.float32)
    valid = np.empty(volume.shape, dtype=bool)
    ordered_sops, ordered_hashes = [], []
    unknown_padding = 0
    for out_z, source_index in enumerate(geometry["order"]):
        ds = headers[source_index]
        # Reverify exact bytes on the second pass before any pixel decoding.
        raw = paths[source_index].read_bytes()
        if hashlib.sha256(raw).hexdigest() != hashes[source_index]:
            raise ValueError("DICOM changed between header and pixel pass")
        import io
        pixels = pydicom.dcmread(io.BytesIO(raw)).pixel_array
        if pixels.shape != shape:
            raise ValueError("decoded matrix mismatch")
        support = np.ones(shape, dtype=bool)
        if "PixelPaddingValue" in ds:
            lower, upper = sorted((float(ds.PixelPaddingValue), float(ds.get("PixelPaddingRangeLimit", ds.PixelPaddingValue))))
            support &= ~((pixels >= lower) & (pixels <= upper))
        else:
            unknown_padding += 1
        volume[out_z] = pixels.astype(np.float32) * float(ds.RescaleSlope) + float(ds.RescaleIntercept)
        valid[out_z] = support
        ordered_sops.append(str(ds.SOPInstanceUID))
        ordered_hashes.append(hashes[source_index])
    raw_hash = hashlib.sha256(json.dumps(ordered_hashes, separators=(",", ":")).encode()).hexdigest()
    ledger = [{"operation": "dicom_to_hu_regular_stack", "version": "EPI-NEXT-CT-1",
               "native_affine_lps": geometry["affine_lps"].tolist(),
               "source_file_sha256": ordered_hashes, "source_order": geometry["order"].tolist(),
               "missing_padding_tag_slices": unknown_padding,
               "padding_policy": case["padding_policy"],
               "completeness": "EXACT_APPROVED_INVENTORY_ONLY", "support_is_lung_mask": False}]
    record = VolumeRecord(patient_id, case["split"], series_uid, ordered_sops, raw_hash,
        volume, valid, geometry["affine_lps"], ledger, case["label_definition_id"],
        case["task_labels"], "PIXEL_PADDING_UNKNOWN" if unknown_padding else "PADDING_EXCLUDED_NOT_LUNG_MASK",
        volume.shape)
    record.validate({patient_id: {"split": case["split"], "series_uids": [series_uid]}})
    return record


def resample_regular_hu(record, spacing_mm, *, approved_membership=None,
                        max_voxels=64_000_000, outside_hu=-1024.) -> VolumeRecord:
    """Resample pixel centres to a parallel grid; return explicit model->LPS.

    Linear interpolation, no antialiasing; thin lesions may be lost. This is a
    provisional resource-test transform, not validated CT-FM preprocessing.
    Output support requires all interpolated native neighbours to be supported.
    """
    record.validate(approved_membership)
    spacing = np.asarray(spacing_mm, dtype=float)
    if spacing.shape != (3,) or not np.isfinite(spacing).all() or np.any(spacing <= 0):
        raise ValueError("three positive finite ZYX spacings required")
    if type(max_voxels) is not int or max_voxels <= 0 or not np.isfinite(outside_hu):
        raise ValueError("invalid resampling budget or fill")
    old = np.linalg.norm(record.affine_lps[:3, :3], axis=0)
    directions = record.affine_lps[:3, :3] / old
    if not np.allclose(directions.T @ directions, np.eye(3), atol=1e-5):
        raise ValueError("resampling only supports orthogonal regular stacks")
    shape = np.ceil((np.array(record.volume_hu.shape) - 1) * old / spacing).astype(int) + 1
    if np.prod(shape, dtype=object) > max_voxels:
        raise ValueError("resampled volume exceeds voxel budget")
    from scipy.ndimage import affine_transform
    mapping = np.diag(spacing / old)
    affine = record.affine_lps.copy()
    affine[:3, :3] = directions * spacing
    hu = affine_transform(record.volume_hu.astype(np.float32), mapping,
        output_shape=tuple(shape), order=1, mode="constant", cval=outside_hu, prefilter=False)
    support_weights = affine_transform(record.valid_mask.astype(np.float32), mapping,
        output_shape=tuple(shape), order=1, mode="constant", cval=0, prefilter=False)
    valid = support_weights >= 1.0 - 1e-6
    hu[~valid] = outside_hu
    ledger = record.transform_ledger + [{"operation": "resample_regular_hu", "version": "EPI-NEXT-CT-1",
        "spacing_zyx_mm": spacing.tolist(), "input_shape": list(record.volume_hu.shape),
        "output_shape": shape.tolist(), "output_to_input_zyx": np.diag([*spacing / old, 1.]).tolist(),
        "interpolation": "linear", "support_interpolation": "all_contributors_valid",
        "outside_hu": outside_hu, "antialiasing": False, "thin_lesion_loss_risk": "NOT_EVALUATED",
        "ctfm_preprocessing_validated": False}]
    result = replace(record, volume_hu=hu, valid_mask=valid, affine_lps=affine, transform_ledger=ledger)
    result.validate(approved_membership)
    return result
