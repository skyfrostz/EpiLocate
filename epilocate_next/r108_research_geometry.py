"""Research metadata and generated-array seams. No file reader, model or UI.

NIfTI-1 single-file, 3D, millimetres only. Caller supplies header bytes;
neither payload offsets nor paths are followed. XYZ affines / ZYX arrays / LPS.
"""
from dataclasses import dataclass
import hashlib
from itertools import product
from math import prod
import struct

import numpy as np

from epilocate_next.infection_overlay_research_v1 import (
    Grid, RAS_TO_LPS, crop_grid,
)

SCHEMA = 'EPI_NEXT_R108_GEOMETRY_V1'
WORLD_TOLERANCE_MM = 1e-4


class MetadataGrid(Grid):
    """Volume metadata only; inherited transforms allocate points, not voxels."""
    def __post_init__(self):
        shape = self.shape_zyx
        a = np.array(self.affine_lps_xyz,dtype=np.float64,copy=True)
        if (len(shape) != 3 or any(type(v) is not int or v <= 0 for v in shape)
                or prod(shape) > 2**31 or a.shape != (4,4) or not np.isfinite(a).all()
                or not np.array_equal(a[3],[0,0,0,1]) or abs(np.linalg.det(a[:3,:3])) < 1e-10):
            raise ValueError('FINITE_BOUNDED_VOLUME_METADATA_REQUIRED')
        a.flags.writeable = False
        object.__setattr__(self,'affine_lps_xyz',a)


@dataclass(frozen=True)
class HeaderGeometry:
    grid: Grid
    qform_code: int
    sform_code: int
    selected_form: str
    scaling_slope: float
    scaling_intercept: float
    stored_dtype: str

    def intensity_evidence(self, source_domain, source_sha256, verified):
        """Scaling is an encoding rule, not proof of Hounsfield units."""
        hu = source_domain == 'RAW_HU' and verified is True and valid_sha(source_sha256)
        return dict(status='HU_SOURCE_BOUND' if hu else 'BLOCKED_HU_UNVERIFIED',
                    domain=source_domain, source_sha256=source_sha256,
                    slope=self.scaling_slope, intercept=self.scaling_intercept,
                    hu_inferred_from_range=False)


def valid_sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def nifti1_header_geometry(header):
    """Resolve q/s explicitly; reject conflicts instead of library precedence."""
    if not isinstance(header, (bytes, bytearray)) or len(header) < 348:
        raise ValueError('NIFTI1_HEADER_BYTES_REQUIRED')
    endian = next((e for e in ('<', '>') if struct.unpack_from(e+'i', header, 0)[0] == 348), None)
    if endian is None or header[344:348] != b'n+1\0':
        raise ValueError('NIFTI1_SINGLE_FILE_ONLY')
    def unpack(fmt, offset):
        return struct.unpack_from(endian+fmt, header, offset)
    dims = unpack('8h', 40)
    if dims[0] != 3 or any(v <= 0 for v in dims[1:4]) or header[123] & 7 != 2:
        raise ValueError('THREE_DIMENSIONS_AND_MM_UNITS_REQUIRED')
    dtype, bits = unpack('2h', 70)
    supported = {2:(8,'u1'), 4:(16,'i2'), 8:(32,'i4'), 16:(32,'f4'), 64:(64,'f8'), 512:(16,'u2')}
    if dtype not in supported or bits != supported[dtype][0]:
        raise ValueError('UNSUPPORTED_STORED_DATATYPE')
    pixdim = np.asarray(unpack('8f', 76), dtype=float)
    if not np.isfinite(pixdim[:4]).all() or np.any(pixdim[1:4] <= 0):
        raise ValueError('FINITE_POSITIVE_SPACING_REQUIRED')
    qcode, scode = unpack('2h', 252)
    if qcode not in range(6) or scode not in range(6) or not (qcode or scode):
        raise ValueError('CODED_WORLD_GEOMETRY_REQUIRED')
    forms = {}
    if qcode:
        b, c, d = unpack('3f', 256)
        norm = b*b+c*c+d*d
        if not np.isfinite(norm) or norm > 1+1e-6 or pixdim[0] not in (-1, 0, 1):
            raise ValueError('INVALID_QFORM_QUATERNION_OR_QFAC')
        if norm > 1:  # Only float32 encoding roundoff near a 180 degree rotation.
            b, c, d = np.asarray([b,c,d])/np.sqrt(norm)
        a = np.sqrt(max(0., 1-b*b-c*c-d*d))
        rotation = np.array([
            [a*a+b*b-c*c-d*d, 2*(b*c-a*d), 2*(b*d+a*c)],
            [2*(b*c+a*d), a*a+c*c-b*b-d*d, 2*(c*d-a*b)],
            [2*(b*d-a*c), 2*(c*d+a*b), a*a+d*d-c*c-b*b],
        ])
        q = np.eye(4)
        q[:3,:3] = rotation @ np.diag(pixdim[1:4]*[1,1,-1 if pixdim[0] == -1 else 1])
        q[:3,3] = unpack('3f', 268)
        forms['qform'] = MetadataGrid(tuple(reversed(dims[1:4])), RAS_TO_LPS @ q)
    if scode:
        s = np.eye(4)
        s[:3] = np.asarray(unpack('12f', 280)).reshape(3,4)
        forms['sform'] = MetadataGrid(tuple(reversed(dims[1:4])), RAS_TO_LPS @ s)
    if len(forms) == 2:
        if qcode != scode or maximum_world_difference(forms['qform'], forms['sform']) > WORLD_TOLERANCE_MM:
            raise ValueError('QFORM_SFORM_COORDINATE_CONFLICT')
    slope, intercept = unpack('2f', 112)
    if slope == 0:
        slope, intercept = 1., 0.  # NIfTI disables both scaling fields.
    if not np.isfinite([slope, intercept]).all():
        raise ValueError('FINITE_SCALING_REQUIRED')
    selected = 'sform' if scode else 'qform'
    return HeaderGeometry(forms[selected], qcode, scode, selected, slope, intercept,
                          endian+supported[dtype][1])


def maximum_world_difference(first, second):
    if first.shape_zyx != second.shape_zyx:
        return float('inf')
    # FOV edges also detect a conflicting slice basis in a one-slice image.
    corners = np.asarray(list(product(*[(-.5, n-.5) for n in first.shape_zyx])))
    return float(np.linalg.norm(first.to_lps(corners)-second.to_lps(corners), axis=1).max())


def resize_grid(grid, shape_zyx):
    """align_corners=False voxel centres; inverse is coordinate-only, not data."""
    if len(shape_zyx) != 3 or any(type(n) is not int or n <= 0 for n in shape_zyx):
        raise ValueError('POSITIVE_INTEGER_RESIZE_SHAPE_REQUIRED')
    scale = np.asarray(grid.shape_zyx[::-1])/np.asarray(shape_zyx[::-1])
    transform = np.eye(4)
    transform[:3,:3] = np.diag(scale)
    transform[:3,3] = (scale-1)/2
    return MetadataGrid(tuple(shape_zyx), grid.affine_lps_xyz @ transform)


def permute_flip_grid(grid, axes_zyx, flip_new_zyx=(False,False,False)):
    """Exact index reorientation metadata, matching transpose then flip arrays."""
    if (len(axes_zyx) != 3 or any(type(v) is not int for v in axes_zyx)
            or sorted(axes_zyx) != [0,1,2] or len(flip_new_zyx) != 3
            or any(type(v) is not bool for v in flip_new_zyx)):
        raise ValueError('EXPLICIT_AXIS_PERMUTATION_AND_FLIPS_REQUIRED')
    shape = tuple(grid.shape_zyx[k] for k in axes_zyx)
    index_map = np.zeros((4,4)); index_map[3,3] = 1
    for new_axis, old_axis in enumerate(axes_zyx):
        index_map[2-old_axis,2-new_axis] = -1 if flip_new_zyx[new_axis] else 1
        if flip_new_zyx[new_axis]:
            index_map[2-old_axis,3] = shape[new_axis]-1
    return MetadataGrid(shape, grid.affine_lps_xyz @ index_map)


def geometry_coverage_report(ct, reference, reference_extent, coverage):
    """No identity join or medical metric; DATA owns identity, LOC owns metrics."""
    c = np.asarray(coverage)
    if c.shape != ct.shape_zyx or c.dtype != np.bool_:
        raise ValueError('EXPLICIT_CT_GRID_BOOLEAN_COVERAGE_REQUIRED')
    if reference_extent not in ('FULL','PARTIAL','UNKNOWN','CONFLICT'):
        raise ValueError('EXPLICIT_REFERENCE_EXTENT_REQUIRED')
    error = maximum_world_difference(ct, reference)
    status = ('BLOCKED_GEOMETRY_MISMATCH' if error > WORLD_TOLERANCE_MM else
              'BLOCKED_REFERENCE_UNKNOWN' if reference_extent in ('UNKNOWN','CONFLICT') else
              'PARTIAL_REFERENCE_OR_FOV' if reference_extent != 'FULL' or not c.all() else 'MATCH_FULL_COVERAGE')
    return dict(schema=SCHEMA, status=status,
                max_world_difference_mm=error if np.isfinite(error) else None,
                shape_match=ct.shape_zyx == reference.shape_zyx,
                covered_voxels=int(c.sum()), total_voxels=c.size,
                coverage_fraction=float(c.mean()), reference_extent=reference_extent,
                outside_coverage_truth='UNKNOWN', identity_verified=False,
                medical_evaluability='REQUIRES_DATA_IDENTITY_AND_LOC_METRIC_GATES')


EVIDENCE = {
    'CT':'SOURCE_CT', 'GT':'REFERENCE_INFECTION_MASK', 'CAM':'SIGNED_CLASS_MARGIN_CONTRIBUTION',
    'E1':'OCCLUSION_RESPONSE', 'E2':'MODEL_DECISION_SUPPORT',
    'B0':'FIXED_AREA_CAM_SELECTION', 'B1':'CONNECTED_CAM_SELECTION',
    'InfNet':'INDEPENDENT_SEGMENTATION_CANDIDATE',
}


def research_layer_bundle(case_id, study_id, series_id, grid, layers):
    if not all(isinstance(x,str) and x.strip() for x in (case_id,study_id,series_id)):
        raise ValueError('EXPLICIT_CASE_STUDY_SERIES_BINDING_REQUIRED')
    seen = set(); outputs = []
    for layer in layers:
        x = dict(layer); name = x.get('kind')
        if name not in EVIDENCE or name in seen or x.get('evidence_type') != EVIDENCE[name]:
            raise ValueError('DISTINCT_TYPED_RESEARCH_LAYER_REQUIRED')
        if not all(isinstance(x.get(k),str) and x[k].strip() for k in ('method','version','target')):
            raise ValueError('METHOD_VERSION_TARGET_REQUIRED')
        if x.get('grid_sha256') != grid.digest() or not valid_sha(x.get('artifact_sha256')):
            raise ValueError('BOUND_NATIVE_GRID_AND_ARTIFACT_REQUIRED')
        for key, expected in [('case_id',case_id),('study_id',study_id),('series_id',series_id)]:
            if key in x and x[key] != expected:
                raise ValueError('CROSS_CASE_LAYER_REJECTED')
        if x.get('evidence_status') not in ('GENERATED_ONLY','NOT_RUN','UNVERIFIED','SOURCE_DECLARED'):
            raise ValueError('INTEGRATION_CANNOT_SELF_CERTIFY_MEDICAL_EVIDENCE')
        if x.get('value_semantics') != EVIDENCE[name] or x.get('clinical_validated',False):
            raise ValueError('NO_GENERIC_LESION_PROBABILITY_OR_CLINICAL_CLAIM')
        seen.add(name); outputs.append(x)
    if not outputs:
        raise ValueError('RESEARCH_LAYERS_REQUIRED')
    return dict(schema='EPI_NEXT_R108_RESEARCH_LAYERS_V1', case_id=case_id,
                study_id=study_id, series_id=series_id, native_grid_sha256=grid.digest(),
                layers=outputs, hospital_eligible=False, mvp_auto_import=False)


def infnet_real_preflight(binding):
    """No inference runner exists here, even when prospective gates are filled."""
    failures = [key for key in ('weight_license_confirmed','training_overlap_resolved',
                                'preprocess_352_confirmed','HU_source_verified') if binding.get(key) is not True]
    failures += [key for key in ('weights_sha256','model_sha256','preprocess_sha256') if not valid_sha(binding.get(key))]
    return dict(status='BLOCKED', reasons=failures+['REAL_INFERENCE_NOT_IMPLEMENTED_OR_AUTHORIZED'],
                model_calls=0, weight_reads=0)


def adapt_generated_infnet_logits(request, native, crop_origin_zyx, crop_shape_zyx, logits):
    """Adapt caller-generated 352 logits only. Does not call a dummy or real model."""
    if request.get('mode') != 'GENERATED_ONLY' or request.get('generated_input') is not True:
        raise ValueError('GENERATED_ONLY_NO_REAL_INFERENCE')
    if not all(isinstance(request.get(k),str) and request[k].strip() for k in ('case_id','study_id','series_id','model_version','preprocess_version','runtime_identity')):
        raise ValueError('INFNET_INPUT_PROVENANCE_REQUIRED')
    for k in ('input_sha256','model_sha256','preprocess_sha256'):
        if not valid_sha(request.get(k)):
            raise ValueError('INFNET_BOUND_INPUT_MODEL_PREPROCESS_REQUIRED')
    if (request.get('native_grid_sha256') != native.digest() or native.shape_zyx[0] != 1
            or prod(native.shape_zyx) > 1_048_576):
        raise ValueError('BOUND_SINGLE_SLICE_NATIVE_GEOMETRY_REQUIRED')
    score = np.asarray(logits)
    if score.shape != (352,352) or not np.issubdtype(score.dtype,np.floating) or not np.isfinite(score).all():
        raise ValueError('FINITE_GENERATED_352_LOGITS_REQUIRED')
    cropped = crop_grid(native, crop_origin_zyx, crop_shape_zyx)
    if cropped.shape_zyx[0] != 1:
        raise ValueError('SINGLE_SLICE_CROP_REQUIRED')
    output_grid = resize_grid(cropped, (1,352,352))
    points = np.moveaxis(np.indices(native.shape_zyx,dtype=float),0,-1)
    coordinates = output_grid.from_lps(native.to_lps(points))
    covered = np.all((coordinates >= [-.5,-.5,-.5]) & (coordinates < [.5,351.5,351.5]),axis=-1)
    y = np.clip(coordinates[...,1],0,351); x = np.clip(coordinates[...,2],0,351)
    y0 = np.floor(y).astype(int); x0 = np.floor(x).astype(int)
    y1 = np.minimum(y0+1,351); x1 = np.minimum(x0+1,351)
    wy = y-y0; wx = x-x0
    interpolated = (score[y0,x0]*(1-wy)*(1-wx)+score[y1,x0]*wy*(1-wx)
                    +score[y0,x1]*(1-wy)*wx+score[y1,x1]*wy*wx)
    native_logits = np.where(covered,interpolated,np.nan).astype(np.float32)
    candidate = (covered & (native_logits >= 0)).astype(np.uint8)  # sigmoid >= .5; no min-max.
    return dict(schema='EPI_NEXT_R108_INFNET_ADAPTER_V1', status='GENERATED_ONLY',
                provenance=dict(request), method='Inf-Net existing supervised segmentation adaptation',
                evidence_type=EVIDENCE['InfNet'], target='INFECTION_SEGMENTATION',
                value_semantics='UNCALIBRATED_LOGITS_AND_THRESHOLD_CANDIDATE',
                native_grid_sha256=native.digest(), native_logits=native_logits,
                infection_mask_candidate=candidate, coverage=covered,
                original_generated_logits=score.copy(), model_calls=0, weight_reads=0,
                candidate_sha256=hashlib.sha256(candidate.tobytes()).hexdigest(),
                candidate_encoding='uint8_C_order_ZYX_bound_to_native_grid',
                runtime_identity=request['runtime_identity'], runtime_seconds=None,
                runtime_status='ADAPTATION_ONLY_NO_MODEL_RUNTIME',
                output_paths=None, output_storage_status='IN_MEMORY_NOT_PERSISTED',
                hospital_eligible=False)
