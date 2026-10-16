"""Consume DATA v3 and coordinator slice lock; prepare exactly three 2D inputs.

No GT selection, allowlist creation, training or localization/model forwards.
The original frozen preprocessing entry point is called on verified DICOM bytes.
"""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pydicom
import torch
import yaml
from torchvision.models import ResNet18_Weights
from torchvision.transforms import functional as TF

from .artifacts import canonical_json, sha256
from .contracts import require_hash
from .geometry import transform_points, inverse_points
from .hospital_runtime import device_lease


ROOT = Path(__file__).resolve().parents[3]
PREPROCESS_SOURCE_SHA = "b4630fd86e0628ab49683368fbaddfcfa2a80717feadf5c8e967ff2d6fa7d41c"
FROZEN_CONFIG_SHA = "7c456065fbff126d25417ad4580c8f8ac58a2b80f5e8fde1356bd6d92a021e17"
CHECKPOINT_SHA = "548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734"
CONTRACT_COMMIT = "8ac99308a123bee468374fff68df4c4f1ec08414"
CONTRACT_PATH = "research/next-hospital-20261014/epi_next/preprocessed_localization.py"


def file_sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_locked_json(path, expected):
    require_hash(expected, "externally fixed file hash")
    raw = Path(path).read_bytes()
    if sha256(raw) != expected:
        raise ValueError("LOCKED_JSON_HASH_MISMATCH")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("LOCKED_JSON_OBJECT_REQUIRED")
    return value


def read_sources(delivery_path, delivery_sha, selection_path, selection_sha):
    """Verify authority references before opening any CT or native HU asset."""
    delivery = read_locked_json(delivery_path, delivery_sha)
    selection = read_locked_json(selection_path, selection_sha)
    if (delivery["schema"] != "EPI_NEXT_DATA_DELIVERY_V3"
            or selection["schema"] != "EPI-NEXT-FIRST-REAL-SLICES-1"
            or delivery["case_count"] != 3 or delivery["sop_count"] != 715
            or selection["data_delivery_sha256"] != delivery_sha
            or selection["allowlist_sha256"] != delivery["allowlist_sha256"]
            or selection["model_outputs_used"] is not False or selection["gt_used_for_selection"] is not False
            or selection["hospital_display_authorized"] is not False):
        raise ValueError("DATA_OR_SELECTION_SCOPE_MISMATCH")
    allowlist = read_locked_json(delivery["allowlist_path"], delivery["allowlist_sha256"])
    authorization = delivery["authorization_reference"]
    approval = read_locked_json(authorization["receipt_path"], authorization["receipt_sha256"])
    # Authorization semantics are DATA's. Record its exact receipt, do not
    # reinterpret a proxy label or mint another approved manifest here.
    if not approval or delivery["consumer_contract"]["local_cpu"] != "ALLOWED":
        raise ValueError("LOCAL_CPU_SCOPE_MISSING")
    if len(selection["slices"]) != 3 or len({s["case_index"] for s in selection["slices"]}) != 3:
        raise ValueError("EXACTLY_THREE_LOCKED_SLICES_REQUIRED")
    label = read_locked_json(delivery["label_definition"]["path"], delivery["label_definition"]["sha256"])
    cases = []
    for selected in selection["slices"]:
        records = [r for r in allowlist["records"] if r["case_index"] == selected["case_index"]]
        mappings = [r for r in delivery["spatial_mapping"]["cases"] if r["patient_id"] == selected["patient_id"]]
        if len(records) != 1 or len(mappings) != 1:
            raise ValueError("SELECTED_CASE_NOT_UNIQUE_IN_DATA_HANDOFF")
        record, mapping = records[0], mappings[0]
        index = selected["native_slice_index_zero_based"]
        if (record["split"] != "train" or selected["split"] != "train"
                or record["patient_id"] != selected["patient_id"] or record["series_uid"] != selected["series_uid"]
                or selected["study_uid"] not in record["study_uids"]
                or index != (selected["native_shape_krc"][0] - 1) // 2
                or selected["sop_uid"] != mapping["ordered_sop_uids"][index]
                or selected["native_manifest_sha256"] != mapping["manifest_sha256"]
                or selected["native_volume_sha256"] != mapping["native_hu_volume_sha256"]):
            raise ValueError("LOCKED_SLICE_MEMBERSHIP_OR_MEDIAN_MISMATCH")
        manifest = read_locked_json(mapping["manifest_path"], mapping["manifest_sha256"])
        if (manifest["native_volume"]["ordered_sop_uids"] != mapping["ordered_sop_uids"]
                or manifest["geometry"]["affine_lps"] != mapping["affine_lps"]
                or manifest["geometry"]["inverse_affine_lps"] != mapping["inverse_affine_lps"]
                or (Path(mapping["manifest_path"]).parent / manifest["native_volume"]["path"]).resolve() != Path(mapping["native_hu_volume_path"]).resolve()
                or selected["affine_lps"] != mapping["affine_lps"]
                or selected["inverse_affine_lps"] != mapping["inverse_affine_lps"]):
            raise ValueError("NATIVE_MAPPING_REFERENCE_MISMATCH")
        rows = [r for r in record["rows"] if r["sop_uid"] == selected["sop_uid"]]
        pixels = [r for r in manifest["native_volume"]["pixel_ledger"] if r["SOPInstanceUID"] == selected["sop_uid"]]
        if len(rows) != 1 or len(pixels) != 1:
            raise ValueError("SOURCE_SOP_LEDGER_MISSING")
        row, pixel = rows[0], pixels[0]
        if (row["study_uid"] != selected["study_uid"] or row["series_uid"] != selected["series_uid"]
                or pixel["native_slice_index"] != index or pixel["ct_reference_relative"] != row["image_path"]):
            raise ValueError("SOURCE_HEADER_MEMBERSHIP_MISMATCH")
        source_root = Path(allowlist["source_root"]).resolve()
        source = (source_root / row["image_path"]).resolve()
        if source_root not in source.parents:
            raise ValueError("SOURCE_PATH_ESCAPES_UPSTREAM_ROOT")
        cases.append((selected, mapping, pixel, source))
    return delivery, selection, label, cases


def load_prepared_contract(upstream):
    """Use the upstream committed class without reimplementing localization."""
    upstream = Path(upstream)
    committed = subprocess.check_output(["git", "show", f"{CONTRACT_COMMIT}:{CONTRACT_PATH}"], cwd=upstream)
    path = upstream / CONTRACT_PATH
    if path.read_bytes() != committed:
        raise ValueError("PREPARED_CONTRACT_WORKTREE_DIFFERS_FROM_FIXED_COMMIT")
    name = "epi_next._upstream_prepared_contract"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module.Prepared2DInput, {"source_commit": CONTRACT_COMMIT, "path": str(path), "sha256": sha256(committed),
                                    "usage": "Prepared2DInput.validate only; no localization executed"}


def prepare_slice(source, expected_sha, selected, native_affine, native_inverse, native_hu, config):
    raw = Path(source).read_bytes()
    if sha256(raw) != expected_sha:
        raise ValueError("SOURCE_CT_HASH_MISMATCH")
    header = pydicom.dcmread(io.BytesIO(raw), stop_before_pixels=True)
    for key, expected in (("SOPInstanceUID", selected["sop_uid"]), ("StudyInstanceUID", selected["study_uid"]),
                          ("SeriesInstanceUID", selected["series_uid"])):
        if str(header.get(key, "")) != expected:
            raise ValueError("SOURCE_CT_IDENTITY_MISMATCH")
    from src.preprocessing import preprocess_dicom
    stages = preprocess_dicom(io.BytesIO(raw), config, return_stages=True)
    if not np.array_equal(stages.hu, native_hu):
        raise ValueError("NATIVE_HU_DIFFERS_FROM_ORIGINAL_FROZEN_CONVERSION")
    image = np.ascontiguousarray(stages.resized[0].numpy(), dtype=np.float32)
    preset = ResNet18_Weights.DEFAULT.transforms()
    tensor = TF.normalize(torch.from_numpy(image)[None].repeat(3, 1, 1), mean=preset.mean, std=preset.std)
    if not torch.equal(tensor, stages.tensor):
        raise ValueError("PREPARED_NORMALIZATION_DIFFERS_FROM_FROZEN_TENSOR")
    rows, columns = stages.raw.shape
    if image.shape != (224, 224) or native_hu.shape != (rows, columns):
        raise ValueError("FROZEN_INPUT_SHAPE_MISMATCH")
    index = selected["native_slice_index_zero_based"]
    mapping = np.diag([1., rows / 224., columns / 224., 1.])
    mapping[:3, 3] = [index, (rows / 224. - 1) / 2, (columns / 224. - 1) / 2]
    native_affine, native_inverse = np.asarray(native_affine), np.asarray(native_inverse)
    if not np.allclose(native_affine @ native_inverse, np.eye(4), rtol=0, atol=1e-8):
        raise ValueError("DATA_AFFINE_INVERSE_MISMATCH")
    points = np.array([[0,0,0], [0,0,223], [0,223,0], [0,223,223], [0,70.25,119.75]])
    world = transform_points(points, native_affine @ mapping)
    native_points = transform_points(points, mapping)
    orientation, spacing, position = np.asarray(header.ImageOrientationPatient,float), np.asarray(header.PixelSpacing,float), np.asarray(header.ImagePositionPatient,float)
    # Independent DICOM formula: IOP first triplet follows column; spacing
    # first component follows row. Do not validate only inverse(self(affine)).
    expected_world = position + native_points[:,1,None]*spacing[0]*orientation[3:] + native_points[:,2,None]*spacing[1]*orientation[:3]
    world_error = float(abs(world-expected_world).max())
    roundtrip = float(abs(inverse_points(world, native_affine @ mapping)-points).max())
    if world_error > 1e-7 or roundtrip > 1e-7:
        raise ValueError("REAL_SOURCE_DICOM_MODEL_NATIVE_GEOMETRY_MISMATCH")
    geometry = {"status":"TECHNICAL_PASS", "source_sop_uid":selected["sop_uid"],
                "native_slice_index_zero_based":index, "native_shape_rc":[rows,columns],
                "model_shape_yx":[224,224], "coordinate_convention":"ZYX_CENTERS_TO_LPS_MM",
                "native_affine_lps":native_affine.tolist(), "native_inverse_affine_lps":native_inverse.tolist(),
                "model_to_native_zyx":mapping.tolist(), "native_to_model_zyx":np.linalg.inv(mapping).tolist(),
                "model_to_lps":(native_affine @ mapping).tolist(), "lps_to_model":np.linalg.inv(native_affine @ mapping).tolist(),
                "resize_convention":"half_pixel_align_corners_false", "resize_interpolation":"bilinear_antialias",
                "crop":"NONE", "pad":"NONE", "resampling":"NONE_NATIVE_GRID",
                "world_header_max_error_mm":world_error, "roundtrip_max_error_model_voxels":roundtrip,
                "checked_model_points_zyx":points.tolist(), "checked_world_points_lps_mm":world.tolist(),
                "native_hu_exact_match":True, "complete_frozen_tensor_exact_match":True,
                "source_rescale_slope":float(header.RescaleSlope), "source_rescale_intercept":float(header.RescaleIntercept),
                "pixel_padding_value":int(header.PixelPaddingValue) if "PixelPaddingValue" in header else None,
                "pixel_padding_range_limit":int(header.PixelPaddingRangeLimit) if "PixelPaddingRangeLimit" in header else None,
                "pixel_padding_status":"TAG_PRESENT_NOT_MASKED_BY_FROZEN_PIPELINE" if "PixelPaddingValue" in header else "UNKNOWN",
                "valid_support_semantics":"FULL_FROZEN_MODEL_IMAGE_DOMAIN_NOT_PADDING_OR_LUNG_MASK",
                "antialias_footprint":"resized pixel centres retained; not a pointwise lesion sampling claim",
                "native_overlay_browser_validation":"NOT RUN", "clinical_validation":"NOT RUN"}
    return image, np.ones(image.shape,dtype=bool), stages.tensor.numpy().copy(), geometry


def save_array(path, value):
    with path.open("xb") as stream:
        np.save(stream, value, allow_pickle=False)
    return {"path":str(path.resolve()), "sha256":file_sha(path), "array_sha256":sha256(np.ascontiguousarray(value).tobytes()),
            "shape":list(value.shape), "dtype":str(value.dtype)}


def prepare_delivery(args):
    output = Path(args.output).resolve()
    if output.exists():
        raise RuntimeError("EXISTING_PREPARATION_RECONCILE_FIRST_NO_AUTOMATIC_RETRY")
    if file_sha(ROOT / "src/preprocessing.py") != PREPROCESS_SOURCE_SHA:
        raise ValueError("FROZEN_PREPROCESS_SOURCE_MISMATCH")
    config = read_frozen_config()
    if args.checkpoint_sha != CHECKPOINT_SHA or file_sha(args.checkpoint) != CHECKPOINT_SHA:
        raise ValueError("FROZEN_CHECKPOINT_HASH_MISMATCH")
    delivery, selection, label, cases = read_sources(args.delivery,args.delivery_sha,args.slice_lock,args.slice_lock_sha)
    coordinator_config = read_locked_json(args.algorithm_config,args.algorithm_config_sha)
    if coordinator_config["slice_lock_sha256"] != args.slice_lock_sha or coordinator_config["device"] != "cpu":
        raise ValueError("COORDINATOR_CONFIG_BINDING_MISMATCH")
    Prepared2DInput, contract = load_prepared_contract(args.localization_worktree)
    preset = ResNet18_Weights.DEFAULT.transforms()
    spec = {"id":"formal-resnet18-baseline-rule-b-v1", "original_source_path":"src/preprocessing.py",
            "original_source_sha256":PREPROCESS_SOURCE_SHA,"config_sha256":FROZEN_CONFIG_SHA,
            "window_center":-600.,"window_width":1500.,"window_lower":-1350.,"window_upper":150.,
            "resize":[224,224],"interpolation":"bilinear_antialias","crop":"NONE","pad":"NONE",
            "channel_policy":"repeat_one_channel_rgb","normalization_mean":preset.mean,"normalization_std":preset.std,
            "input_fill_normalized_scalar":0.,"constant_fill_equivalent_hu":-1350.,
            "fill_semantics":"post_resize_before_RGB_ImageNet_normalization; not clinical counterfactual",
            "torch":torch.__version__,"torchvision":__import__('torchvision').__version__}
    spec_bytes=canonical_json(spec); preprocess_sha=sha256(spec_bytes)
    with device_lease("cpu"):
        output.mkdir(parents=True,exist_ok=False)
        (output/'submission.json').write_bytes(canonical_json({'state':'STARTED','data_delivery_sha256':args.delivery_sha,
                                                               'slice_lock_sha256':args.slice_lock_sha,'command':sys.argv}))
        records=[]; received=[]
        for selected,mapping,pixel,source in cases:
            if file_sha(mapping['native_hu_volume_path']) != mapping['native_hu_volume_sha256']:
                raise ValueError('DATA_NATIVE_VOLUME_HASH_MISMATCH')
            native=np.load(mapping['native_hu_volume_path'],mmap_mode='r',allow_pickle=False)
            if list(native.shape)!=selected['native_shape_krc'] or native.dtype!=np.float32:
                raise ValueError('DATA_NATIVE_VOLUME_SHAPE_DTYPE_MISMATCH')
            z=selected['native_slice_index_zero_based']
            image,support,tensor,geometry=prepare_slice(source,pixel['ct_sha256'],selected,mapping['affine_lps'],mapping['inverse_affine_lps'],native[z],config)
            prepared=Prepared2DInput(image,support,sha256(image.tobytes()),spec['id'],
                label['schema']+':sha256:'+delivery['label_definition']['sha256'],split='train',scope='APPROVED_PREPROCESSED',
                approval_receipt_sha256=delivery['authorization_reference']['receipt_sha256'])
            prepared.validate()
            case_output=output/f"case-{selected['case_index']}";case_output.mkdir()
            arrays={name:save_array(case_output/(name+'.npy'),value) for name,value in
                    [('image',image),('valid_mask',support),('model_tensor',tensor)]}
            geo_path=case_output/'geometry.json';geo_path.write_bytes(canonical_json(geometry))
            record={"case_id":selected['case_id'],"case_index":selected['case_index'],"study_uid":selected['study_uid'],
                    "series_uid":selected['series_uid'],"source_sop_uid":selected['sop_uid'],"native_slice_index_zero_based":z,
                    "source_ct_sha256":pixel['ct_sha256'],"source_ct_path":str(source),"native_manifest_sha256":mapping['manifest_sha256'],
                    "native_volume_sha256":mapping['native_hu_volume_sha256'],"arrays":arrays,
                    "geometry":{"path":str(geo_path),"sha256":file_sha(geo_path),"status":"TECHNICAL_PASS"},
                    "prepared_contract":{"input_sha256":prepared.input_sha256,"preprocess_id":prepared.preprocess_id,
                        "task_definition_id":prepared.task_definition_id,"split":prepared.split,"scope":prepared.scope,
                        "approval_receipt_sha256":prepared.approval_receipt_sha256},"preprocess_sha256":preprocess_sha,
                    "valid_support_semantics":geometry['valid_support_semantics'],"padding_status":geometry['pixel_padding_status']}
            (case_output/'prepared_input.json').write_bytes(canonical_json(record));records.append(record)
            received.append({'case_index':selected['case_index'],'native_manifest_sha256':mapping['manifest_sha256'],
                             'native_volume_sha256':mapping['native_hu_volume_sha256'],'source_ct_sha256':pixel['ct_sha256'],'hash_verified':True})
        (output/'preprocessing.json').write_bytes(spec_bytes)
        (output/'data_v3_receive_receipt.json').write_bytes(canonical_json({'schema':'EPI-NEXT-DATA-CONSUMER-RECEIVE-1',
            'consumer':'INTEGRATION','data_delivery_path':str(Path(args.delivery).resolve()),'data_delivery_sha256':args.delivery_sha,
            'allowlist_sha256':delivery['allowlist_sha256'],'approval_receipt_sha256':delivery['authorization_reference']['receipt_sha256'],
            'slice_lock_sha256':args.slice_lock_sha,'accepted_case_count':3,'selected_slice_count':3,'upstream_sop_count':715,
            'selected_assets':received,'allowlist_created':False,'gt_created':False,'gt_used_for_selection':False,'model_forwards':0}))
        result={'schema':'EPI-NEXT-PREPARED-DELIVERY-1','status':'READY_FOR_LOCALIZATION_CPU','source_git_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'source_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)),
            'command':sys.argv,'data_delivery_sha256':args.delivery_sha,'slice_lock_sha256':args.slice_lock_sha,
            'algorithm_config_sha256':args.algorithm_config_sha,'algorithm_config_path':str(Path(args.algorithm_config).resolve()),
            'checkpoint_path':str(Path(args.checkpoint).resolve()),'checkpoint_sha256':CHECKPOINT_SHA,
            'prepared_contract_source':contract,'preprocess_sha256':preprocess_sha,'records':records,
            'model_forwards':0,'gt_reference_files_opened':False,'gt_geometry_used_for_preparation':False,
            'native_manifest_contains_gt_metadata':True,'hospital_display_authorized':False,'clinical_validation':'NOT RUN',
            'artifacts_sha256':{str(p.relative_to(output)):file_sha(p) for p in sorted(output.rglob('*')) if p.is_file()}}
        with (output/'prepared_delivery.json').open('xb') as stream:stream.write(canonical_json(result))
    return {'status':result['status'],'path':str(output/'prepared_delivery.json'),'sha256':file_sha(output/'prepared_delivery.json'),
            'case_count':3,'native_slice_indices':[s['native_slice_index_zero_based'] for s in selection['slices']], 'model_forwards':0}


def read_frozen_config():
    path=ROOT/'configs/formal_baseline_rule_b_v1.yaml'
    if file_sha(path)!=FROZEN_CONFIG_SHA:raise ValueError('FROZEN_CONFIG_MISMATCH')
    return yaml.safe_load(path.read_bytes())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('delivery','slice-lock','algorithm-config','checkpoint','localization-worktree','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    for name in ('delivery-sha','slice-lock-sha','algorithm-config-sha','checkpoint-sha'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args();torch.set_num_threads(1)
    print(json.dumps(prepare_delivery(args),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
