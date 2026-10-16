"""Independent saved-asset QA of three native-spacing CT-FM center blocks."""
import argparse
import hashlib
from itertools import product
import json
from pathlib import Path

import numpy as np

from .data_delivery import read_bound
from .gt_vnext import sha256
from .prepared_mapping_qa import require_close


def nominal_encoder_lattice():
    """Longest residual conv path: init3/1, 1/2/2/4/4 two-conv blocks.

    Four inter-level conv3/stride2/pad1 downsamplers. Shortcuts share the
    same centers and cannot enlarge the receptive field of the longest path.
    """
    field, stride, offset, count = 3, 1, 0, 1
    for level, blocks in enumerate([1, 2, 2, 4, 4]):
        field += blocks * 4 * stride; count += blocks * 2
        if level < 4:
            field += 2 * stride; stride *= 2; count += 1
    return {"stride": stride, "nominal_center_offset": offset, "receptive_field": field, "conv_count": count}


def verify_encoder_mapping(manifest_path, manifest_sha, data_path, data_sha):
    manifest_path = Path(manifest_path)
    manifest = read_bound(manifest_path, manifest_sha)
    data = read_bound(data_path, data_sha)
    if data["case_count"] != 3 or data["sop_count"] != 715 or manifest["real_case_count"] != 3:
        raise ValueError("three-case scope required")
    base = manifest_path.parent
    config = read_bound(base / "config.json", manifest["config_sha256"])
    if (config["data_delivery_sha256"] != data_sha or config["real_patch_shape_spl"] != [64, 64, 64]
            or config["hu_clip"] != [-1024, 2048] or config["resampling"] != "NONE_NATIVE_SPACING"):
        raise ValueError("unexpected block config")
    expected_lattice = nominal_encoder_lattice()
    records = []
    for i, mapping in enumerate(data["spatial_mapping"]["cases"], 1):
        key = f"case_{i}"
        ledger = read_bound(base / f"{key}_ledger.json", manifest["prepared_ledger_hashes"][key])
        case = read_bound(mapping["manifest_path"], mapping["manifest_sha256"])
        if (ledger["case_index"] != i or ledger["case_manifest_sha256"] != mapping["manifest_sha256"]
                or ledger["data_delivery_sha256"] != data_sha
                or ledger["native_volume_sha256"] != mapping["native_hu_volume_sha256"]
                or ledger["native_slice_sop_mapping"] != mapping["ordered_sop_uids"]):
            raise ValueError("encoder source ledger binding mismatch")
        shape = np.array(case["geometry"]["shape_krc"])
        if (list(shape) != ledger["native_shape_krc"] or ledger["orientation"] != "SPL"
                or ledger["permutation"] != [0, 1, 2] or ledger["flips"] != [False, False, False]
                or ledger["resampling"] != "NONE_NATIVE_SPACING" or ledger["patch_shape_spl"] != [64, 64, 64]):
            raise ValueError("unsupported or mismatched orientation/crop policy")
        affine = np.array(case["geometry"]["affine_lps"])
        spacing = np.array(case["geometry"]["spacing_krc_mm"])
        expected_basis = np.array([[0, 0, spacing[2]], [0, spacing[1], 0], [spacing[0], 0, 0]])
        require_close(affine[:3, :3], expected_basis, "native axes are not positive SPL")
        start = (shape - 64) // 2
        if np.any(start < 0) or list(start) != ledger["crop_start_spl"]:
            raise ValueError("block is not geometry-only floor center")
        transform = np.eye(4); transform[:3, 3] = start
        for field, expected in [("orient_to_native", np.eye(4)), ("patch_to_native", transform),
                                ("native_to_patch", np.linalg.inv(transform)), ("patch_to_lps", affine @ transform),
                                ("lps_to_patch", np.linalg.inv(affine @ transform))]:
            require_close(ledger[field], expected, field + " mismatch")
        require_close(ledger["spacing_spl_mm"], spacing, "spacing mismatch")
        require_close(ledger["voxel_edge_extent_mm"], 64 * spacing, "physical extent mismatch")
        require_close(ledger["center_offset_voxels_spl"], start + 31.5 - (shape - 1) / 2, "center offset mismatch")
        feature_transform = transform @ np.diag([16., 16., 16., 1.])
        lattice = ledger["feature_lattice"]
        require_close(lattice["feature_to_native"], feature_transform, "feature center mapping mismatch")
        if (lattice["stride_spl"] != [16] * 3 or lattice["nominal_center_offset"] != [0] * 3
                or lattice["receptive_field_voxels"] != [expected_lattice["receptive_field"]] * 3):
            raise ValueError("feature lattice does not match longest conv path")
        input_path = base / f"{key}_input.npy"
        if sha256(input_path) != manifest["prepared_input_hashes"][key]:
            raise ValueError("block input hash mismatch")
        if sha256(mapping["native_hu_volume_path"]) != mapping["native_hu_volume_sha256"]:
            raise ValueError("native source hash mismatch")
        native = np.load(mapping["native_hu_volume_path"], mmap_mode="r", allow_pickle=False)
        patch = np.array(native[tuple(slice(int(s), int(s + 64)) for s in start)], dtype=np.float32)
        reconstructed = ((np.clip(patch, -1024, 2048) + np.float32(1024)) / np.float32(3072))[None, None]
        saved = np.load(input_path, allow_pickle=False)
        input_error = require_close(saved, reconstructed, "block HU preprocessing mismatch", 0)
        if saved.shape != (1, 1, 64, 64, 64) or saved.dtype != np.float32:
            raise ValueError("block input grid mismatch")
        if hashlib.sha256(saved.tobytes()).hexdigest() != ledger["input_content_sha256"]:
            raise ValueError("ledger input content mismatch")
        headers = {s["native_slice_index"]: s["native_header"] for s in case["sops"]}
        feature_points = np.array([(*point, 1.) for point in product(range(4), repeat=3)])
        native_points = (feature_transform @ feature_points.T).T
        world = (affine @ native_points.T).T[:, :3]
        header_world = []
        for point in native_points:
            header = headers[int(point[0])]
            orientation = np.array(header["ImageOrientationPatient"])
            row_mm, col_mm = header["PixelSpacing"]
            header_world.append(np.array(header["ImagePositionPatient"]) + point[1] * row_mm * orientation[3:]
                                + point[2] * col_mm * orientation[:3])
        world_error = require_close(world, header_world, "feature centers disagree with DICOM headers")
        roundtrip = require_close((np.linalg.inv(affine @ feature_transform) @ np.c_[world, np.ones(64)].T).T,
                                  feature_points, "feature world roundtrip mismatch")
        real = manifest["real"][i - 1]
        if real["ledger_sha256"] != manifest["prepared_ledger_hashes"][key] or real["result"]["feature_lattice"] != expected_lattice:
            raise ValueError("actual execution feature lattice binding mismatch")
        for name, digest in real["result"]["output_hashes"].items():
            output = base / f"real_{key}" / name
            if sha256(output) != digest:
                raise ValueError("saved feature output hash mismatch")
            features = np.load(output, allow_pickle=False)
            if features.shape != (1, 512, 4, 4, 4) or features.dtype != np.float32 or not np.isfinite(features).all():
                raise ValueError("saved feature lattice shape/nonfinite failure")
        records.append({"case_index": i, "status": "PASS", "crop_start_native_krc": start.tolist(),
                        "ledger_sha256": manifest["prepared_ledger_hashes"][key], "normalized_input_max_abs_error": input_error,
                        "feature_centers_checked": 64, "header_world_max_error_mm": world_error,
                        "feature_roundtrip_max_error_voxels": roundtrip, "physical_block_extent_mm": (64 * spacing).tolist()})
    return {"schema": "DATA_CTFM_BLOCK_MAPPING_QA_V1", "status": "TECHNICAL_PASS_WITH_SCOPE_LIMITATIONS",
            "encoder_manifest_path": str(manifest_path), "encoder_manifest_sha256": manifest_sha,
            "data_delivery_sha256": data_sha, "records": records, "nominal_encoder_lattice": expected_lattice,
            "model_forwards": 0, "whole_volume_equivalence": "NOT_ESTABLISHED",
            "feature_center_semantics": "nominal conv sampling lattice; not lesion centers or disjoint16-cube cells",
            "boundary_context": "469-voxel nominal receptive field exceeds64 block; zero-padded block context differs from whole volume",
            "clinical_localization": "NOT_ESTABLISHED", "GT_used": False, "source_CT_reopened": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha", required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--data-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify_encoder_mapping(args.manifest, args.manifest_sha, args.data, args.data_sha)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False); stream.write("\n")
