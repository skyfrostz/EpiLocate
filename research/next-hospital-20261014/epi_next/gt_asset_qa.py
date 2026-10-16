"""Verify the saved three-case GT-vNext bytes and native geometry ledger.

Reads only the published private artifacts; does not revisit source DICOM/ZIP,
infer lesions, repair geometry, run models or qualify clinical truth.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
from PIL import Image

from .data_delivery import verify_delivery, read_bound
from .geometry import regular_stack_geometry, slice_affine_lps, transform_points, inverse_points
from .gt_vnext import sha256, union_key


def bound_path(root, relative):
    path = (root / relative).resolve(strict=True)
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError("artifact path escapes private asset root")
    return path


def checked_mask(root, record, shape):
    path = bound_path(root, record["mask_path"])
    if sha256(path) != record["mask_sha256"]:
        raise ValueError("mask SHA mismatch")
    with Image.open(path) as image:
        if image.mode != "1":
            raise ValueError("mask must be binary mode 1")
        mask = np.asarray(image, dtype=bool)
    if mask.shape != shape or not mask.any() or int(mask.sum()) != record["area_pixels"]:
        raise ValueError("mask shape/area mismatch")
    return mask


def verify_asset(manifest_path, manifest_sha, delivery_path, delivery_sha):
    delivery = verify_delivery(delivery_path, delivery_sha)
    allowlist = read_bound(delivery["allowlist_path"], delivery["allowlist_sha256"])
    expected = {c["patient_id"]: c for c in allowlist["records"]}
    root = manifest_path.parent.resolve(strict=True)
    manifest = read_bound(manifest_path, manifest_sha)
    if manifest["allowlist_sha256"] != delivery["allowlist_sha256"] or len(manifest["cases"]) != 3:
        raise ValueError("asset authority mismatch")
    if {c["patient_id"] for c in manifest["cases"]} != set(expected):
        raise ValueError("case membership mismatch")
    totals = Counter(); cases = []
    for summary in manifest["cases"]:
        path = bound_path(root, summary["manifest_path"])
        case = read_bound(path, summary["manifest_sha256"])
        rows = expected[case["patient_id"]]["rows"]
        sops = case["sops"]
        if {s["SOPInstanceUID"] for s in sops} != {r["sop_uid"] for r in rows} or len(sops) != len(rows):
            raise ValueError("SOP membership mismatch")
        if case["geometry"]["status"] != "PASS" or case["native_volume"]["status"] != "TECHNICAL_PASS":
            cases.append({"case_id": summary["case_id"], "status": "QUARANTINED"})
            continue
        geometry = case["geometry"]; volume_ref = case["native_volume"]
        headers = [s["native_header"] for s in sops]
        recalculated = regular_stack_geometry([h["ImagePositionPatient"] for h in headers],
                                             [h["ImageOrientationPatient"] for h in headers], [h["PixelSpacing"] for h in headers])
        if not np.allclose(recalculated["affine_lps"], geometry["affine_lps"], atol=1e-10, rtol=0):
            raise ValueError("saved affine differs from native headers")
        sorted_sops = [sops[i]["SOPInstanceUID"] for i in recalculated["order"]]
        if sorted_sops != volume_ref["ordered_sop_uids"]:
            raise ValueError("volume SOP ordering mismatch")
        if sorted(s["native_slice_index"] for s in sops) != list(range(len(rows))):
            raise ValueError("native slice index not bijective")
        for sop in sops:
            if sorted_sops[sop["native_slice_index"]] != sop["SOPInstanceUID"]:
                raise ValueError("SOP index differs from volume")
        volume_path = bound_path(path.parent, volume_ref["path"])
        if sha256(volume_path) != volume_ref["sha256"]:
            raise ValueError("native volume SHA mismatch")
        volume = np.load(volume_path, mmap_mode="r", allow_pickle=False)
        if list(volume.shape) != geometry["shape_krc"] or volume.dtype != np.float32 or any(not np.isfinite(sl).all() for sl in volume):
            raise ValueError("native HU volume invalid")
        by_sop = {s["SOPInstanceUID"]: s for s in sops}
        masks = {}; annotations = {}; max_world_error = 0.0
        shape = tuple(geometry["shape_krc"][1:])
        for obj in case["annotations"]:
            aid = obj["annotation_id"]
            if aid in annotations:
                raise ValueError("duplicate annotation ID")
            annotations[aid] = obj
            if obj["status"] != "PASS":
                totals["quarantined_objects"] += 1
                continue
            mask = checked_mask(root, obj, shape); masks[aid] = mask
            y, x = np.where(mask)
            if [int(x.min()), int(y.min()), int(x.max()) + 1, int(y.max()) + 1] != obj["box_xyxy_half_open"]:
                raise ValueError("mask/box mismatch")
            header = by_sop[obj["identity"]["SOPInstanceUID"]]["native_header"]
            vertices = np.asarray(obj["raw_annotation"]["data"]["vertices"])
            krc = np.c_[np.zeros(len(vertices)), vertices[:, 1], vertices[:, 0]]
            affine = slice_affine_lps(header["ImagePositionPatient"], header["ImageOrientationPatient"], header["PixelSpacing"])
            saved_world = np.asarray(obj["vertices_lps_mm"])
            error = max(float(np.max(np.abs(transform_points(krc, affine) - saved_world))),
                        float(np.max(np.abs(inverse_points(saved_world, affine) - krc))))
            if error > 1e-8:
                raise ValueError("polygon world/native roundtrip mismatch")
            max_world_error = max(max_world_error, error)
            totals["instance_masks_verified"] += 1
        for sop in sops:
            for union in sop["category_unions"]:
                mask = checked_mask(root, union, shape)
                expected_mask = np.zeros(shape, bool)
                target_key = (union["category"], union["createdById"], union["label_group_id"], union["labelId"])
                for aid in union["source_annotation_ids"]:
                    obj = annotations[aid]
                    if obj["identity"]["SOPInstanceUID"] != sop["SOPInstanceUID"] or union_key(obj["raw_annotation"], obj["raw_label"]) != target_key:
                        raise ValueError("union crosses SOP/category/creator/group/label")
                    expected_mask |= masks[aid]
                if not np.array_equal(mask, expected_mask):
                    raise ValueError("union differs from source instances")
                totals["category_unions_verified"] += 1
            if sop["annotation_complete"] is not False or sop["unannotated_region_status"] != "UNKNOWN":
                raise ValueError("incomplete annotation treated as normal")
        totals["native_volume_sops_verified"] += len(rows)
        for overlay in case["overlays"]:
            if sha256(bound_path(root, overlay["path"])) != overlay["sha256"]:
                raise ValueError("overlay SHA mismatch")
            totals["overlays_verified"] += 1
        cases.append({"case_id": summary["case_id"], "status": "TECHNICAL_PASS", "sop_count": len(rows),
                      "polygon_world_roundtrip_max_error": max_world_error, "spacing_krc_mm": geometry["spacing_krc_mm"],
                      "actual_spacing_min_max_mm": [min(geometry["actual_slice_spacings_mm"]), max(geometry["actual_slice_spacings_mm"])],
                      "resampling": "NONE_NATIVE_GRID", "acquisition_completeness": "UNKNOWN_BEYOND_FROZEN_INVENTORY"})
    return {"schema": "GT_VNEXT_SAVED_ASSET_QA_V1", "status": "TECHNICAL_PASS_WITH_QUARANTINE", "counts": dict(totals),
            "cases": cases, "source_manifest_sha256": manifest_sha, "delivery_sha256": delivery_sha,
            "annotation_completeness": "UNKNOWN", "clinical_adjudication": "NOT_ADJUDICATED",
            "full_reference_metrics_eligible": False, "independent_test_eligible": False,
            "quarantine_reason_mapping": {"'NoneType' object has no attribute 'get'": "DATA_NULL"},
            "source_DICOM_or_ZIP_reopened": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True); parser.add_argument("--sha256", required=True)
    parser.add_argument("--delivery", type=Path, required=True); parser.add_argument("--delivery-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify_asset(args.manifest, args.sha256, args.delivery, args.delivery_sha256)
    from .gt_vnext import save_json
    save_json(args.output, result)
    print(json.dumps({"status": result["status"], "counts": result["counts"], "sha256": sha256(args.output)}))
