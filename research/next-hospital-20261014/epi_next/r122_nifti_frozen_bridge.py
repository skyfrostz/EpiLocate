"""R122 generated NIfTI bridge; no medical path reader or model callback.

Metadata layout is reusable by DATA. Voxel/preprocessing entrypoints require
explicit synthetic metadata. Real first-CAM execution remains separately gated.
"""
import json
from io import BytesIO
import re

import numpy as np

from . import r108_frozen_r18_adapter as frozen


PERMUTE_ZYX_TO_XYZ = np.eye(4)[[2, 1, 0, 3]]
RAS_TO_LPS = np.diag([-1., -1., 1., 1.])
LATE_BOUND_REFS = (
    'ct_member', 'mask_member', 'data_qualification_receipt', 'native_tensor',
    'geometry_ledger', 'gt_qualification_receipt', 'medical_registry',
    'real_backend_source', 'runtime_validation_receipt', 'owner_execution_approval',
    'task_admission', 'exclusive_dispatch',
)
FIRST_CAM_FIXED = dict(
    case='coronacases_001', member_name='coronacases_001.nii.gz',
    CT_archive_sha256='0000000000000000000000000000000000000000000000000000000000000000',
    Mask_archive_sha256='0000000000000000000000000000000000000000000000000000000000000000',
    model_identity=frozen.FROZEN_IDENTITY,
    native_order='ORIGINAL_NIFTI_XYZ_TRANSPOSED_ZYX_NO_FLIPS',
    target='FIXED_SIGNED_INFECTION_MARGIN_LOGIT1_MINUS_LOGIT0',
    head_policy='EXISTING_FROZEN_HEAD_NO_NEW_STANDARDIZATION_OR_TRAINING',
    cam_layer='TRUE_LAYER4_OUTPUT_AVGPOOL_INPUT_8_512_7_7',
    budget=dict(forward_batches=1, input_positions=8, backward=0, updates=0,
                warmup=0, retry=0, device='cpu', threads=1),
    mask_used_as_classification_label=False,
)


def validate_first_cam_binding(binding):
    """Pure metadata check. Even all-bound proposals are not executable here."""
    frozen.require(isinstance(binding, dict)
                   and set(binding) == {'schema', 'fixed', 'late_bound'}
                   and binding['schema'] == 'R122_FIRST_CAM_BINDING_SPEC_V1',
                   'EXACT_FIRST_CAM_BINDING_SCHEMA_REQUIRED')
    frozen.require(json.dumps(binding['fixed'], sort_keys=True) == json.dumps(FIRST_CAM_FIXED, sort_keys=True),
                   'FROZEN_FIRST_CAM_SCOPE_DRIFT')
    refs = binding['late_bound']
    frozen.require(isinstance(refs, dict) and set(refs) == set(LATE_BOUND_REFS),
                   'ONLY_DECLARED_LATE_BOUND_FIELDS_ALLOWED')
    for ref in refs.values():
        frozen.require(ref is None or (isinstance(ref, dict) and set(ref) == {'path', 'sha256'}
                       and isinstance(ref['path'], str) and ref['path'].startswith('/')
                       and isinstance(ref['sha256'], str) and re.fullmatch('[a-f0-9]{64}', ref['sha256'])),
                       'EXACT_ABSOLUTE_REFERENCE_AND_SHA_REQUIRED')
    return dict(status='BLOCKED', executable=False,
                missing=[name for name, ref in refs.items() if ref is None],
                reason='REAL_BACKEND_DISABLED_AND_SEPARATE_EXACT_EXECUTION_VALIDATION_REQUIRED',
                files_opened=0, model_calls=0)


def native_layout(shape_XYZ, affine_RAS):
    """Metadata only: original XYZ -> ZYX, preserving every original Z.

    Canonical LPS coordinates are separate display metadata, never used for K8.
    No interpolation, header/file/voxel access or claim of HU qualification.
    """
    import nibabel as nib
    frozen.require(len(shape_XYZ) == 3 and all(type(n) is int and n > 0 for n in shape_XYZ),
                   'SCALAR_3D_SHAPE_REQUIRED')
    affine = np.asarray(affine_RAS, dtype=np.float64)
    frozen.require(affine.shape == (4, 4) and np.isfinite(affine).all()
                   and np.allclose(affine[3], [0, 0, 0, 1], atol=1e-7, rtol=0)
                   and abs(np.linalg.det(affine[:3, :3])) >= 1e-8,
                   'FINITE_INVERTIBLE_AFFINE_REQUIRED')
    orientation = nib.orientations.ornt_transform(
        nib.orientations.io_orientation(affine), nib.orientations.axcodes2ornt(('L', 'P', 'S')))
    canonical_to_original = nib.orientations.inv_ornt_aff(orientation, shape_XYZ)
    native_to_original = PERMUTE_ZYX_TO_XYZ
    native_to_LPS = RAS_TO_LPS @ affine @ native_to_original
    frozen.require(np.allclose(native_to_LPS[:2, 0], 0, atol=1e-7, rtol=0)
                   and np.allclose(native_to_LPS[2, 1:3], 0, atol=1e-7, rtol=0),
                   'FROZEN_NATIVE_AXIAL_GEOMETRY_REQUIRED_NO_RESAMPLING')
    shape = list(shape_XYZ[::-1])
    frozen.fixed8(shape[0])
    return dict(original_shape_XYZ=list(shape_XYZ), original_to_RAS=affine.tolist(),
                orientation_transform=orientation.tolist(), native_shape_ZYX=shape,
                native_to_original_XYZ=native_to_original.tolist(),
                original_to_native_ZYX=np.linalg.inv(native_to_original).tolist(),
                native_to_LPS=native_to_LPS.tolist(),
                spacing_ZYX_mm=np.linalg.norm(native_to_LPS[:3, :3], axis=0).tolist(),
                canonical_shape_XYZ=np.asarray(shape_XYZ)[np.argsort(orientation[:, 0].astype(int))].tolist(),
                canonical_to_original_XYZ=canonical_to_original.tolist(),
                original_to_canonical_XYZ=np.linalg.inv(canonical_to_original).tolist(),
                canonical_to_LPS=(RAS_TO_LPS @ affine @ canonical_to_original).tolist(),
                axis_order='Z,Y,X', native_definition='ORIGINAL_NIFTI_XYZ_TRANSPOSED_ZYX_NO_FLIPS',
                reorientation='NO_NATIVE_FLIPS_OR_REORDERING_CANONICAL_MAPPING_METADATA_ONLY')


def synthetic_nifti_to_native(image, metadata):
    """Decode only an injected serialized synthetic NIfTI proxy, scale once.

    No nib.load/path interface. DATA must independently establish HU provenance;
    slope/intercept and plausible numeric range alone do not establish HU.
    """
    frozen.validate_native_metadata(metadata)  # Reject real domain before proxy access.
    import nibabel as nib
    frozen.require(isinstance(image, nib.Nifti1Image)
                   and isinstance(image.dataobj, nib.arrayproxy.ArrayProxy)
                   and isinstance(image.dataobj.file_like, BytesIO),
                   'SERIALIZED_IN_MEMORY_SYNTHETIC_NIFTI1_PROXY_REQUIRED')
    frozen.require(image.dataobj.dtype.kind in 'iuf'
                   and image.dataobj.dtype == image.header.get_data_dtype(),
                   'REAL_SCALAR_STORAGE_DTYPE_REQUIRED')
    frozen.require(np.prod(image.shape, dtype=object)*4 <= 64*1024**2,
                   'GENERATED_FP32_VOLUME_LIMIT_64_MIB')
    frozen.require(image.header.get_xyzt_units()[0] == 'mm', 'EXPLICIT_MILLIMETRE_UNITS_REQUIRED')
    qform, qcode = image.get_qform(coded=True)
    sform, scode = image.get_sform(coded=True)
    frozen.require(bool(qcode or scode), 'CODED_AFFINE_REQUIRED')
    if qcode and scode:
        frozen.require(np.allclose(qform, sform, atol=1e-5, rtol=0), 'QFORM_SFORM_CONFLICT')
    affine = sform if scode else qform
    frozen.require(np.allclose(image.affine, affine, atol=1e-7, rtol=0), 'IMAGE_CODED_AFFINE_MISMATCH')
    layout = native_layout(list(image.shape), affine)
    frozen.require(layout['native_shape_ZYX'] == metadata['native_shape_ZYX']
                   and np.allclose(layout['native_to_LPS'], metadata['native_to_LPS'], atol=1e-7, rtol=0)
                   and np.allclose(layout['spacing_ZYX_mm'], metadata['spacing_ZYX_mm'], atol=1e-7, rtol=1e-7),
                   'BOUND_NATIVE_LAYOUT_MISMATCH')
    slope, intercept = float(image.dataobj.slope), float(image.dataobj.inter)
    frozen.require(np.isfinite([slope, intercept]).all() and slope != 0, 'FINITE_PROXY_SCALING_REQUIRED')
    # ArrayProxy performs encoded scaling here. Never multiply/add it again.
    scaled_xyz = np.asanyarray(image.dataobj, dtype=np.float32)
    frozen.require(scaled_xyz.dtype == np.float32 and np.isfinite(scaled_xyz).all(), 'FINITE_FP32_HU_REQUIRED')
    native = np.ascontiguousarray(scaled_xyz.transpose(2, 1, 0), dtype=np.float32)
    layout['scaling'] = dict(encoded_slope=slope, encoded_intercept=intercept,
                             applications=1, backend='nibabel.ArrayProxy.__array__',
                             unit='HU_BY_SYNTHETIC_PROVENANCE_NOT_RANGE_INFERENCE')
    return native, layout


def prepare_synthetic_nifti(image, metadata):
    """Generated NIfTI -> unchanged R108 HU/K8 + actual frozen resize backend."""
    native, layout = synthetic_nifti_to_native(image, metadata)

    def resize(array, *, size, interpolation, antialias):
        import torch
        from torchvision.transforms import InterpolationMode, functional as tf
        frozen.require(size == (224, 224) and interpolation == 'bilinear' and antialias is True,
                       'FROZEN_RESIZE_ARGUMENT_DRIFT')
        return tf.resize(torch.from_numpy(array), [224, 224],
                         interpolation=InterpolationMode.BILINEAR, antialias=True).numpy()

    bag, valid, geometry = frozen.prepare_synthetic_native(native, metadata, resize=resize)
    geometry.update(layout)
    geometry['selected_original_nifti_Z'] = geometry['indices_Z'].copy()
    original_planes = np.array([[0, 0, z, 1] for z in geometry['indices_Z']], dtype=np.float64)
    geometry['selected_canonical_Z'] = (original_planes @ np.asarray(layout['original_to_canonical_XYZ']).T)[:, 2].tolist()
    geometry['verification'] = 'GENERATED_NIFTI_BRIDGE_ONLY'
    return bag, valid, geometry


def native_centers_to_model(geometry, points_ZYX):
    """Invert nominal centers only on the eight selected native planes."""
    points = np.asarray(points_ZYX, dtype=np.float64)
    frozen.require(points.ndim == 2 and points.shape[1] == 3 and np.isfinite(points).all(),
                   'FINITE_NATIVE_POINTS_REQUIRED')
    delta = np.abs(points[:, :1] - np.asarray(geometry['indices_Z'])[None, :])
    frozen.require((delta.min(axis=1) <= 1e-7).all(), 'UNSAMPLED_NATIVE_Z_HAS_NO_MODEL_PLANE')
    result = points.copy()
    result[:, 0] = delta.argmin(axis=1)
    result[:, 1:] = (points[:, 1:] + .5)*224/np.asarray(geometry['native_shape_ZYX'][1:]) - .5
    frozen.require(((result[:, 1:] >= -1e-7) & (result[:, 1:] <= 223+1e-7)).all(),
                   'POINT_OUTSIDE_MODEL_CENTER_DOMAIN')
    return result


def real_reader(*args, **kwargs):
    raise frozen.Blocked('R122_REAL_MEDICAL_READER_DISABLED')


def first_cam_callback(*args, **kwargs):
    raise frozen.Blocked('R122_FIRST_CAM_MODEL_CALLBACK_NOT_IMPLEMENTED_NOT_AUTHORIZED')
