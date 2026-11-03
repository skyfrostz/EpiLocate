"""Independent CPU verification of the three fixed prepared inputs; no model."""
import argparse
import json
from pathlib import Path

import numpy as np

from .data_delivery import read_bound
from .evaluation_protocol import fixed_slice_binding
from .gt_vnext import sha256


def require_close(actual, expected, reason, tolerance=1e-8):
    actual, expected = np.asarray(actual), np.asarray(expected)
    if actual.shape != expected.shape or not np.isfinite(actual).all() or not np.isfinite(expected).all():
        raise ValueError(reason)
    error = float(np.max(np.abs(actual - expected)))
    if error > tolerance:
        raise ValueError(reason)
    return error


def verify_prepared(path, expected_sha, slice_lock_path, slice_lock_sha):
    # torch is used solely for CPU preprocessing arithmetic, never inference.
    import torch
    import torch.nn.functional as functional
    torch.set_num_threads(1)
    path = Path(path)
    prepared = read_bound(path, expected_sha)
    lock = read_bound(slice_lock_path, slice_lock_sha)
    if (prepared["data_delivery_sha256"] != lock["data_delivery_sha256"]
            or prepared["slice_lock_sha256"] != slice_lock_sha
            or len(prepared["records"]) != 3
            or len({r["case_id"] for r in prepared["records"]}) != 3):
        raise ValueError("prepared delivery scope mismatch")
    source = read_bound(lock["data_delivery_path"], lock["data_delivery_sha256"])
    if source["allowlist_sha256"] != lock["allowlist_sha256"]:
        raise ValueError("allowlist mismatch")
    for relative, digest in prepared["artifacts_sha256"].items():
        if sha256(path.parent / relative) != digest:
            raise ValueError("prepared artifact hash mismatch")
    preprocess = read_bound(path.parent / "preprocessing.json", prepared["preprocess_sha256"])
    if (preprocess["resize"] != [224, 224] or preprocess["crop"] != "NONE" or preprocess["pad"] != "NONE"
            or preprocess["window_center"] != -600 or preprocess["window_width"] != 1500
            or preprocess["normalization_mean"] != [.485, .456, .406]
            or preprocess["normalization_std"] != [.229, .224, .225]
            or preprocess["channel_policy"] != "repeat_one_channel_rgb"
            or preprocess["interpolation"] != "bilinear_antialias"):
        raise ValueError("unexpected preprocessing policy")
    results = []
    for record in prepared["records"]:
        rows = [r for r in lock["slices"] if r["case_id"] == record["case_id"]]
        if len(rows) != 1:
            raise ValueError("unexpected prepared case")
        selected = rows[0]
        case = read_bound(selected["native_manifest_path"], selected["native_manifest_sha256"])
        index, sop = fixed_slice_binding(lock, selected["patient_id"], case, selected["native_manifest_sha256"])
        if (record["source_sop_uid"] != sop or record["native_slice_index_zero_based"] != index
                or record["native_manifest_sha256"] != selected["native_manifest_sha256"]
                or record["native_volume_sha256"] != selected["native_volume_sha256"]):
            raise ValueError("prepared source identity mismatch")
        ledger = next(s for s in case["sops"] if s["native_slice_index"] == index)
        pixel = next(s for s in case["native_volume"]["pixel_ledger"] if s["native_slice_index"] == index)
        if record["source_ct_sha256"] != pixel["ct_sha256"]:
            raise ValueError("prepared CT digest differs from DATA ledger")
        if sha256(selected["native_volume_path"]) != selected["native_volume_sha256"]:
            raise ValueError("native HU digest mismatch")
        hu = np.load(selected["native_volume_path"], mmap_mode="r", allow_pickle=False)[index]
        normalized = (np.clip(hu, -1350., 150.) + 1350.) / 1500.
        independently_resized = functional.interpolate(torch.from_numpy(normalized.copy())[None, None],
            size=(224, 224), mode="bilinear", align_corners=False, antialias=True)[0, 0].numpy()
        mean = np.array(preprocess["normalization_mean"], dtype=np.float32)[:, None, None]
        std = np.array(preprocess["normalization_std"], dtype=np.float32)[:, None, None]
        reconstructed_tensor = (np.repeat(independently_resized[None], 3, axis=0) - mean) / std
        arrays = {}
        for name, spec in record["arrays"].items():
            if sha256(spec["path"]) != spec["sha256"]:
                raise ValueError("prepared array digest mismatch")
            arrays[name] = np.load(spec["path"], allow_pickle=False)
        image_error = require_close(arrays["image"], independently_resized, "resized image mismatch", 0)
        tensor_error = require_close(arrays["model_tensor"], reconstructed_tensor, "normalized tensor mismatch", 0)
        if arrays["valid_mask"].dtype != np.bool_ or arrays["valid_mask"].shape != (224, 224) or not arrays["valid_mask"].all():
            raise ValueError("unexpected model support")
        geometry = read_bound(record["geometry"]["path"], record["geometry"]["sha256"])
        if (geometry["crop"] != "NONE" or geometry["pad"] != "NONE"
                or geometry["resize_convention"] != "half_pixel_align_corners_false"
                or geometry["native_slice_index_zero_based"] != index or geometry["source_sop_uid"] != sop):
            raise ValueError("geometry policy/identity mismatch")
        transform = np.diag([1., 512 / 224, 512 / 224, 1.])
        transform[:3, 3] = [index, (512 / 224 - 1) / 2, (512 / 224 - 1) / 2]
        affine = np.array(case["geometry"]["affine_lps"])
        require_close(geometry["native_affine_lps"], affine, "native affine mismatch")
        require_close(geometry["model_to_native_zyx"], transform, "half-pixel mapping mismatch")
        require_close(geometry["native_to_model_zyx"], np.linalg.inv(transform), "inverse mapping mismatch")
        require_close(geometry["model_to_lps"], affine @ transform, "world mapping mismatch")
        require_close(geometry["lps_to_model"], np.linalg.inv(affine @ transform), "world inverse mismatch")
        points = np.array([[0., r, c, 1.] for r, c in [(0, 0), (0, 223), (223, 0), (223, 223),
                                                       (70.25, 119.75), (111.5, 111.5)]])
        native = (transform @ points.T).T
        world = (affine @ native.T).T[:, :3]
        header = ledger["native_header"]
        orientation = np.array(header["ImageOrientationPatient"])
        spacing = header["PixelSpacing"]
        direct_world = (np.array(header["ImagePositionPatient"]) + native[:, 1, None] * spacing[0] * orientation[3:]
                        + native[:, 2, None] * spacing[1] * orientation[:3])
        world_error = require_close(world, direct_world, "DICOM world correspondence mismatch")
        roundtrip_error = require_close((np.linalg.inv(affine @ transform) @ np.c_[world, np.ones(len(world))].T).T,
                                        points, "world roundtrip mismatch")
        results.append({"case_id": record["case_id"], "native_slice_index": index, "SOPInstanceUID": sop,
                        "geometry_sha256": record["geometry"]["sha256"], "status": "PASS",
                        "reconstructed_image_max_abs_error": image_error, "reconstructed_tensor_max_abs_error": tensor_error,
                        "independent_header_world_max_error_mm": world_error, "roundtrip_max_error_model_voxels": roundtrip_error})
    return {"schema": "DATA_PREPARED_MAPPING_QA_V1", "status": "TECHNICAL_PASS",
            "prepared_delivery_path": str(path), "prepared_delivery_sha256": expected_sha,
            "fixed_slice_lock_sha256": slice_lock_sha, "data_delivery_sha256": lock["data_delivery_sha256"],
            "records": results, "candidate_inverse_raster_mapping": "NOT_YET_RECEIVED_SEPARATE_QA_REQUIRED",
            "resampling_scope": "native CT unchanged; model image resized512-to224 with antialias",
            "clinical_validity": "NOT_ESTABLISHED", "model_forwards": 0, "source_CT_reopened": False,
            "device": "CPU_ONLY", "GT_used_for_preprocessing_or_selection": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--prepared-sha", required=True)
    parser.add_argument("--slice-lock", type=Path, required=True)
    parser.add_argument("--slice-lock-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify_prepared(args.prepared, args.prepared_sha, args.slice_lock, args.slice_lock_sha)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False); stream.write("\n")
