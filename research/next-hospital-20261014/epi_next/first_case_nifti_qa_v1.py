"""Bounded native NIfTI qualification; no resampling, model or evaluation.

The caller owns extraction, authorization, source bindings and temporary files.
This module imports the separately pinned nibabel installation through PYTHONPATH.
"""
import itertools
import hashlib
import io
import json
import math
import mmap
import os
from pathlib import Path

import nibabel as nib
import numpy as np


SCHEMA = 'FIRST_CASE_NIFTI_NATIVE_QA_V1'
DEFAULT_LIMITS = dict(max_native_voxels_per_member=134217728,
    max_native_plane_voxels=4194304, working_numeric_buffer_cap_bytes=16777216,
    max_native_depth=4096, max_mask_values=64, tolerance_world_mm=1e-4, roundtrip_vox=1e-5)
RAS_TO_LPS = np.diag([-1., -1., 1., 1.])
ZYX_TO_XYZ = np.array([[0., 0., 1., 0.], [0., 1., 0., 0.],
                       [1., 0., 0., 0.], [0., 0., 0., 1.]])
HIST_EDGES = [-math.inf, -32768., -4096., -1024., 0., 1., 256., 1024., 4096., 32768., math.inf]


class Invalid(ValueError):
    pass


class BoundedHeaderIO(io.BytesIO):
    """Bound official extension parsing by bytes and read operations."""
    def __init__(self, value):
        super().__init__(value)
        self.read_calls = 0

    def read(self, size=-1):
        self.read_calls += 1
        require(self.read_calls <= 260, 'EXTENSION_PARSER_OPERATION_CAP')
        return super().read(size)


def require(condition, code):
    if not condition:
        raise Invalid(code)


def safe(value):
    if isinstance(value, np.ndarray):
        return safe(value.tolist())
    if isinstance(value, np.generic):
        return safe(value.item())
    if isinstance(value, bytes):
        return {'bytes_hex': value.hex()}
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [safe(v) for v in value]
    return value


def corners(shape):
    return np.array(list(itertools.product(*[(0., float(n - 1)) for n in shape])))


def apply(affine, points):
    return nib.affines.apply_affine(affine, points)


def load_native(path, limits, check):
    check()
    path = Path(path)
    require(path.suffix == '.nii' and path.is_file() and not path.is_symlink(), 'UNCOMPRESSED_REGULAR_NII_REQUIRED')
    initial_stat = path.stat()
    with path.open('rb') as stream:
        block = stream.read(540)
        klass = nib.Nifti2Header if nib.Nifti2Header.may_contain_header(block) else nib.Nifti1Header
        require(klass.may_contain_header(block), 'NIFTI1_OR_NIFTI2_HEADER_REQUIRED')
        binary = block[:klass.sizeof_hdr]
        diagnosis = klass.diagnose_binaryblock(binary)
        require(not diagnosis, 'INVALID_HEADER:' + diagnosis)
        original = klass(binary, check=False)
        require(bytes(original['magic']).rstrip(b'\x00') == klass.single_magic, 'SINGLE_FILE_MAGIC_REQUIRED')
        shape = tuple(int(v) for v in original.get_data_shape())
        require(len(shape) == 3 and all(n > 0 for n in shape), 'EXACT_THREE_DIMENSIONS_REQUIRED')
        require(shape[2] <= limits['max_native_depth'], 'NATIVE_DEPTH_CAP')
        voxels = math.prod(shape)
        require(voxels <= limits['max_native_voxels_per_member'], 'NATIVE_VOXEL_CAP')
        dtype = original.get_data_dtype()
        require(dtype.kind in 'iuf' and dtype.itemsize <= 8, 'REAL_SCALAR_DTYPE_REQUIRED')
        require(int(original['bitpix']) == dtype.itemsize * 8, 'BITPIX_DTYPE_MISMATCH')
        offset = float(original['vox_offset'])
        require(math.isfinite(offset) and offset == int(offset) and
                klass.sizeof_hdr + 4 <= offset <= min(1048576, limits['working_numeric_buffer_cap_bytes']), 'BOUNDED_VALID_OFFSET_REQUIRED')
        require(path.stat().st_size == int(offset) + voxels * dtype.itemsize, 'EXACT_UNCOMPRESSED_FILE_SIZE_REQUIRED')
        stream.seek(0)
        # nibabel's extension parser trusts declared esize for read(size).
        # Give it only the bounded header prefix, never the whole voxel file.
        prefix = stream.read(int(offset))
        require(len(prefix) == int(offset), 'TRUNCATED_HEADER_PREFIX')
        header = klass.from_fileobj(BoundedHeaderIO(prefix), check=False)
        require(len(header.extensions) <= 128, 'EXTENSION_COUNT_CAP')
    units = original.get_xyzt_units()
    require(units[0] in ('mm', 'meter', 'micron'), 'KNOWN_SPATIAL_UNITS_REQUIRED')
    unit_scale = {'mm': 1., 'meter': 1000., 'micron': .001}[units[0]]
    raw_slope, raw_inter = float(original['scl_slope']), float(original['scl_inter'])
    # Official nibabel semantics decide disabled/undefined scaling; do not use
    # the image's post-load header, where scaling is consumed and reset to NaN.
    original.get_slope_inter()
    qform, qcode = original.get_qform(coded=True)
    sform, scode = original.get_sform(coded=True)
    require(qcode or scode, 'CODED_NATIVE_AFFINE_REQUIRED')
    for affine in (qform, sform):
        if affine is not None:
            require(np.isfinite(affine).all(), 'NONFINITE_CODED_AFFINE')
    scale = np.diag([unit_scale, unit_scale, unit_scale, 1.])
    if qcode and scode:
        discrepancy = np.max(np.linalg.norm(apply(scale @ qform, corners(shape)) -
                                            apply(scale @ sform, corners(shape)), axis=1))
        require(discrepancy <= limits['tolerance_world_mm'], 'QFORM_SFORM_CONFLICT')
    else:
        discrepancy = None
    affine = scale @ (sform if scode else qform)
    require(np.isfinite(affine).all() and abs(np.linalg.det(affine[:3, :3])) > 0, 'FINITE_INVERTIBLE_AFFINE_REQUIRED')
    spacing = nib.affines.voxel_sizes(affine)
    require(np.isfinite(spacing).all() and np.all(spacing > 0), 'POSITIVE_SPACING_REQUIRED')
    direction = affine[:3, :3] / spacing
    require(np.allclose(direction.T @ direction, np.eye(3), atol=1e-6, rtol=0), 'SHEAR_REJECTED_NO_RESAMPLING')
    rounded = np.rint(direction)
    require(np.allclose(direction, rounded, atol=1e-6, rtol=0) and
            np.all(np.sum(np.abs(rounded), axis=0) == 1) and
            np.all(np.sum(np.abs(rounded), axis=1) == 1), 'OBLIQUE_REJECTED_NO_RESAMPLING')
    require(np.allclose(np.asarray(original.get_zooms()[:3]) * unit_scale, spacing,
                        atol=limits['tolerance_world_mm'], rtol=0), 'HEADER_SPACING_AFFINE_MISMATCH')
    orientation = nib.orientations.ornt_transform(nib.orientations.io_orientation(affine),
                                                 nib.orientations.axcodes2ornt(('L', 'P', 'S')))
    native_xyz_shape = np.array(shape)[np.argsort(orientation[:, 0].astype(int))]
    canonical_shape = tuple(int(v) for v in native_xyz_shape)
    # ENC V2: native axes preserve the original NIfTI array order and sign.
    # Canonical LPS orientation remains a separate reversible metadata map.
    native_shape = tuple(int(v) for v in shape[::-1])
    require(native_shape[0] >= 8, 'K8_REQUIRES_DEPTH_AT_LEAST_8')
    require(native_shape[1] * native_shape[2] <= limits['max_native_plane_voxels'], 'NATIVE_PLANE_VOXEL_CAP')
    original_from_canonical = nib.orientations.inv_ornt_aff(orientation, shape)
    canonical_from_original = np.linalg.inv(original_from_canonical)
    original_from_native = ZYX_TO_XYZ.copy()
    native_to_lps = RAS_TO_LPS @ affine @ original_from_native
    native_from_original = np.linalg.inv(original_from_native)
    roundtrip = float(np.max(np.abs(apply(native_from_original, apply(original_from_native, corners(native_shape))) - corners(native_shape))))
    require(roundtrip <= limits['roundtrip_vox'], 'INDEX_ROUNDTRIP_FAILURE')
    check()
    image_class = nib.Nifti2Image if klass is nib.Nifti2Header else nib.Nifti1Image
    image = image_class.from_filename(str(path), mmap='r', keep_file_open=False)
    proxy = image.dataobj
    raw = proxy.get_unscaled()
    try:
        require(isinstance(raw, np.memmap), 'READONLY_MEMMAP_REQUIRED')
        require(not raw.flags.writeable and tuple(raw.shape) == shape, 'RAW_PROXY_SHAPE_OR_MODE')
        slope, inter = float(proxy.slope), float(proxy.inter)
        require(math.isfinite(slope) and slope != 0 and math.isfinite(inter), 'FINITE_EFFECTIVE_SCALING_REQUIRED')
    except BaseException:
        if isinstance(raw, np.memmap):
            raw._mmap.close()
        raise
    metadata = dict(format=klass.__name__, header_checks='NIBABEL_CHECK_ONLY_NO_FIX',
        source_file_identity=dict(device=initial_stat.st_dev, inode=initial_stat.st_ino,
            bytes=initial_stat.st_size, mtime_ns=initial_stat.st_mtime_ns),
        raw_header={key: safe(original[key]) for key in original.keys()}, shape_original_XYZ=list(shape),
        dtype=str(dtype), bitpix=int(original['bitpix']), byte_order=original.endianness,
        vox_offset=int(offset), units=list(units), spatial_unit_to_mm=unit_scale,
        raw_scaling=dict(slope=safe(raw_slope), intercept=safe(raw_inter)),
        effective_proxy_scaling=dict(slope=slope, intercept=inter, applications=1),
        qform_code=int(qcode), sform_code=int(scode), qform=safe(qform) if qform is not None else None,
        sform=safe(sform) if sform is not None else None, q_s_max_corner_discrepancy_mm=discrepancy,
        original_XYZ_to_RAS_mm=affine.tolist(), axis_codes_original_RAS=list(nib.aff2axcodes(affine)),
        axis_codes_original_LPS=list(nib.aff2axcodes(RAS_TO_LPS @ affine,
            labels=(('-L', '+L'), ('-P', '+P'), ('-S', '+S')))),
        spacing_original_XYZ_mm=spacing.tolist(), native_shape_ZYX=list(native_shape),
        original_shape_XYZ=list(shape), spacing_ZYX_mm=spacing[::-1].tolist(),
        original_to_RAS=affine.tolist(), native_to_LPS=native_to_lps.tolist(),
        native_to_original_XYZ=original_from_native.tolist(), original_to_native_ZYX=native_from_original.tolist(),
        native_ZYX_to_original_XYZ=original_from_native.tolist(), original_XYZ_to_native_ZYX=native_from_original.tolist(),
        native_ZYX_to_LPS_mm=native_to_lps.tolist(), LPS_mm_to_native_ZYX=np.linalg.inv(native_to_lps).tolist(),
        index_roundtrip_max_vox=roundtrip, orientation_operation='INTEGER_AXIS_PERMUTATION_AND_FLIPS_ONLY',
        native_definition='original NIfTI XYZ transpose(2,1,0); no flips or permutation before K8',
        original_axis2_is_axial=bool(np.all(np.abs(affine[[0, 1], 2]) <= 1e-7) and
                                     np.all(np.abs(affine[2, [0, 1]]) <= 1e-7)),
        canonical_shape_XYZ=list(canonical_shape),
        canonical_to_original_XYZ=original_from_canonical.tolist(),
        original_to_canonical_XYZ=canonical_from_original.tolist(),
        canonical_to_LPS_mm=(RAS_TO_LPS @ affine @ original_from_canonical).tolist(),
        canonical_to_LPS=(RAS_TO_LPS @ affine @ original_from_canonical).tolist(),
        orientation_transform=orientation.tolist(),
        resampled=False)
    return dict(raw=raw, proxy=proxy, slope=slope, inter=inter, meta=metadata, orientation=orientation,
                native_shape=native_shape, original_from_native=original_from_native, native_to_lps=native_to_lps,
                original_from_canonical=original_from_canonical, canonical_shape=canonical_shape)


def new_stats():
    return dict(voxels=0, nonfinite=0, minimum=None, maximum=None,
                histogram_edges=safe(HIST_EDGES), histogram_counts=[0] * (len(HIST_EDGES) - 1))


def update_stats(result, values):
    result['voxels'] += int(values.size)
    finite = np.isfinite(values)
    result['nonfinite'] += int(values.size - np.count_nonzero(finite))
    good = values[finite]
    if good.size:
        low, high = float(np.min(good)), float(np.max(good))
        result['minimum'] = low if result['minimum'] is None else min(low, result['minimum'])
        result['maximum'] = high if result['maximum'] is None else max(high, result['maximum'])
        counts = np.histogram(good, bins=HIST_EDGES)[0]
        result['histogram_counts'] = [a + int(b) for a, b in zip(result['histogram_counts'], counts)]


def scan(member, is_mask, infection_values, limits, check):
    raw_stats, scaled_stats = new_stats(), new_stats()
    raw_counts, scaled_counts, per_z = {}, {}, []
    # At most 128 bytes per source voxel are reserved for float buffers,
    # finite masks, histogram temporaries and unique-value/count work arrays.
    chunk_voxels = limits['working_numeric_buffer_cap_bytes'] // 128
    require(chunk_voxels >= 1, 'NUMERIC_BUFFER_CAP_TOO_SMALL')
    axis = 2
    noninteger = False
    fp32_unsafe = 0
    for z in range(member['native_shape'][0]):
        check()
        if member['raw'] is None:
            member['raw'] = member['proxy'].get_unscaled()
            require(isinstance(member['raw'], np.memmap) and not member['raw'].flags.writeable,
                    'READONLY_MEMMAP_REQUIRED')
        original_z = z
        slicing = [slice(None)] * 3
        slicing[axis] = original_z
        plane = member['raw'][tuple(slicing)]
        plane = plane.T  # Original XYZ plane -> original-order native YX.
        # Fortran NIfTI XYZ storage becomes a C-contiguous original-order YX
        # plane. Check before reshape so a hostile layout cannot cause a hidden
        # whole-plane copy; no canonical flips are applied here.
        require(plane.flags.c_contiguous, 'NATIVE_PLANE_CONTIGUOUS_VIEW_REQUIRED')
        flat = plane.reshape(-1, order='C')
        require(np.shares_memory(flat, plane), 'NATIVE_PLANE_RESHAPE_COPY_FORBIDDEN')
        plane_counts = {}
        infection_hash = hashlib.sha256() if is_mask and infection_values is not None else None
        for start in range(0, flat.size, chunk_voxels):
            check()
            raw_chunk = flat[start:start + chunk_voxels]
            if is_mask and raw_chunk.dtype.kind in 'iu':
                # Compare integer values before conversion: int64(2**53+1)
                # rounds down when cast to float64 and must not slip through.
                require(not np.any(raw_chunk > 2 ** 53), 'MASK_INTEGER_OUTSIDE_EXACT_FLOAT_DOMAIN')
                if raw_chunk.dtype.kind == 'i':
                    require(not np.any(raw_chunk < -(2 ** 53)), 'MASK_INTEGER_OUTSIDE_EXACT_FLOAT_DOMAIN')
            values = np.asarray(raw_chunk, dtype=np.float64)
            if is_mask:
                require(not np.any(np.abs(values[np.isfinite(values)]) > 2 ** 53),
                        'MASK_INTEGER_OUTSIDE_EXACT_FLOAT_DOMAIN')
            update_stats(raw_stats, values)
            scaled = values * member['slope'] + member['inter']
            update_stats(scaled_stats, scaled)
            finite_scaled = scaled[np.isfinite(scaled)]
            fp32_unsafe += int(np.count_nonzero(np.abs(finite_scaled) > np.finfo(np.float32).max))
            if is_mask:
                require(not np.any(np.abs(finite_scaled) > 2 ** 53), 'SCALED_MASK_OUTSIDE_EXACT_INTEGER_DOMAIN')
                for source, target in ((values, raw_counts), (scaled, scaled_counts)):
                    finite = source[np.isfinite(source)]
                    if np.any(finite != np.rint(finite)):
                        noninteger = True
                    unique, counts = np.unique(finite, return_counts=True)
                    require(unique.size <= limits['max_mask_values'], 'MASK_VALUE_CARDINALITY_CAP')
                    for value, count in zip(unique, counts):
                        key = str(int(value)) if float(value).is_integer() else repr(float(value))
                        target[key] = target.get(key, 0) + int(count)
                        require(len(target) <= limits['max_mask_values'], 'MASK_VALUE_CARDINALITY_CAP')
                unique, counts = np.unique(finite_scaled, return_counts=True)
                for value, count in zip(unique, counts):
                    key = str(int(value)) if float(value).is_integer() else repr(float(value))
                    plane_counts[key] = plane_counts.get(key, 0) + int(count)
                if infection_hash is not None:
                    infection_hash.update(np.isin(scaled, infection_values).astype(np.uint8).tobytes(order='C'))
        if is_mask:
            per_z.append(dict(native_Z=z, original_plane_axis=axis, original_plane_index=original_z,
                scaled_value_counts=plane_counts,
                infection_voxels=None if infection_values is None else sum(plane_counts.get(str(v), 0) for v in infection_values),
                infection_plane_sha256=None if infection_hash is None else infection_hash.hexdigest(),
                plane_hash_encoding='original-order nativeYX row-major uint8 explicit infection-class membership; no normal-region inference'))
        # macOS MADV_DONTNEED is advisory and did not bound resident pages in
        # the first generated capacity run. Drop every view and actually close
        # this plane's mapping; reopen the official proxy for the next plane.
        plane = flat = raw_chunk = values = scaled = finite_scaled = source = finite = None
        member['raw']._mmap.close()
        member['raw'] = None
        check()
    return dict(raw=raw_stats, scaled=scaled_stats, raw_value_counts=raw_counts if is_mask else None,
        scaled_value_counts=scaled_counts if is_mask else None, mask_noninteger=noninteger,
        fp32_unsafe_voxels=fp32_unsafe,
        per_native_Z=per_z if is_mask else None, full_float_volume_materialized=False,
        raw_mapping_policy='READONLY_PROXY_MAP_REOPENED_AND_CLOSED_EACH_NATIVE_Z',
        maximum_chunk_voxels=chunk_voxels, numeric_working_buffer_policy_bytes=limits['working_numeric_buffer_cap_bytes'])


def binding_present(value):
    return (isinstance(value, dict) and isinstance(value.get('path'), str) and bool(value['path']) and
        isinstance(value.get('sha256'), str) and len(value['sha256']) == 64 and
        all(c in '0123456789abcdef' for c in value['sha256'].lower()))


def analyze_pair(ct_path, mask_path, evidence, preprocess, limits, check=lambda: None):
    caller_check = check
    check_failures = []
    def check():
        try:
            caller_check()
        except BaseException as exc:
            check_failures.append(exc)
            raise
    limits = {**DEFAULT_LIMITS, **(limits or {})}
    evidence = evidence or {}
    result = dict(schema=SCHEMA, status='UNKNOWN', reasons=[], members={}, geometry=None,
                  K8=None, evidence=evidence, preprocess=dict(status='UNKNOWN', supplied=preprocess),
                  medical_denominator=None, models=0, resampling=False, full_region_metrics_enabled=False,
                  scope='NATIVE_PAIR_QUALIFICATION_ONLY')
    def issue(domain, code, reject=False):
        result['reasons'].append(dict(domain=domain, code=code, severity='REJECT' if reject else 'UNKNOWN'))
    accepted = dict(expert_status={'EXPERT_VERIFIED', 'SOURCE_EXPERT_CONFIRMED'},
        extent={'COMPLETE_REFERENCE_VERIFIED', 'PARTIAL_REFERENCE_VERIFIED'}, patient_status={'DEIDENTIFIED_VERIFIED', 'SOURCE_DEIDENTIFIED_VERIFIED'},
        license_status={'PERMITTED_VERIFIED', 'OPEN_LICENSE_VERIFIED', 'LICENSE_VERIFIED'})
    binding_keys = dict(expert_status='expert_binding', extent='extent_binding',
        patient_status='patient_binding', license_status='license_binding')
    qualification = {}
    for name, allowed in accepted.items():
        supplied = evidence.get(name)
        bound = binding_present(evidence.get(binding_keys[name]))
        verified = isinstance(supplied, str) and supplied in allowed and bound
        qualification[name] = dict(input_status=supplied, binding_present=bound,
            effective_status='VERIFIED' if verified else 'UNKNOWN')
        if not verified:
            issue('evidence', name.upper() + '_UNVERIFIED_OR_INCOMPLETE',
                  reject=supplied == 'REJECT' and name != 'license_status')
    result['qualification'] = qualification
    result['annotation_coverage'] = dict(status='UNKNOWN' if not qualification['extent']['effective_status'] == 'VERIFIED' else 'BOUND_EXTENT_CLAIM',
        source_extent=evidence.get('extent'), full_region_metrics_enabled=False,
        unknown_or_partial_background='UNKNOWN_NOT_NORMAL')
    domain = evidence.get('case_domain')
    verified_hu = (evidence.get('hu_status') == 'NATIVE_HU_VERIFIED' and binding_present(evidence.get('hu_binding')) and
                   isinstance(domain, dict) and domain.get('modality') == 'CT' and domain.get('value_domain') == 'HU' and domain.get('case_bound') is True)
    if not verified_hu:
        issue('HU', 'NATIVE_HU_NOT_VERIFIED')
    result['HU'] = dict(status='NATIVE_HU_VERIFIED' if verified_hu else ('WINDOWED_0_255' if evidence.get('hu_status') == 'WINDOWED_0_255' else 'UNKNOWN'),
                        negative_values_do_not_establish_HU=True)
    class_map = evidence.get('class_map')
    infection_values = None
    if binding_present(evidence.get('class_map_binding')) and isinstance(class_map, list) and class_map and all(isinstance(row, dict) and {'value', 'raw_class', 'medical_category'} <= row.keys() and
            isinstance(row['value'], int) and not isinstance(row['value'], bool) and
            isinstance(row['raw_class'], str) and bool(row['raw_class']) and
            isinstance(row['medical_category'], str) and bool(row['medical_category']) for row in class_map):
        values = [row['value'] for row in class_map]
        if len(set(values)) != len(values):
            issue('labels', 'CONFLICTING_CLASS_MAP', True)
        else:
            infection_values = [row['value'] for row in class_map if row['medical_category'] in ('infection', 'infectious_lesion')]
    else:
        issue('labels', 'CLASS_MAP_UNKNOWN')
    result['labels'] = dict(class_map=class_map, infection_values=infection_values,
        zero_is_normal=False, full_shape_establishes_complete_GT=False, unannotated_is_normal=False,
        reference_domain='POSITIVE_ANNOTATED_ONLY' if evidence.get('extent') != 'COMPLETE_REFERENCE_VERIFIED' else 'COMPLETE_EXTENT_CLAIM_REQUIRES_SEPARATE_METRIC_APPROVAL')
    if isinstance(preprocess, dict) and preprocess.get('status') == 'BOUND' and binding_present(preprocess.get('binding')) and isinstance(preprocess.get('fields'), dict) and preprocess['fields']:
        contract = preprocess['fields']
        fields = contract.get('frozen_preprocess', {})
        expected = dict(K=8, window='clip((HU+1350)/1500,0,1), FP32',
            resize='torchvision.transforms.functional.resize(...,[224,224],InterpolationMode.BILINEAR,antialias=True)',
            rgb='repeat scalar channels 3', mean=[.485, .456, .406], std=[.229, .224, .225],
            crop='NONE', output_axes='K,C,Y,X', output_shape=[8, 3, 224, 224], dtype='float32', device='cpu')
        if contract.get('schema') == 'R122_ENCODER_DATA_FROZEN_INTERFACE_V2' and all(fields.get(k) == v for k, v in expected.items()):
            result['preprocess']['status'] = 'BOUND_V2_CONTRACT_VALIDATED_NOT_EXECUTED'
        else:
            issue('preprocess', 'BOUND_CONTRACT_MISSING_OR_CONFLICTING_FIELDS', True)
    else:
        issue('preprocess', 'FROZEN_CONTRACT_UNKNOWN')
    loaded = {}
    for name, path in (('CT', ct_path), ('Mask', mask_path)):
        member = None
        try:
            member = load_native(path, limits, check)
            result['members'][name] = member['meta']
            member['stats'] = scan(member, name == 'Mask', infection_values, limits, check)
            result['members'][name]['statistics'] = member['stats']
            if member['stats']['raw']['nonfinite'] or member['stats']['scaled']['nonfinite']:
                issue(name, 'NONFINITE_VOXELS', True)
            if member['stats']['mask_noninteger']:
                issue(name, 'NONINTEGER_MASK', True)
            if name == 'CT' and member['stats']['fp32_unsafe_voxels']:
                issue(name, 'FULL_VOLUME_FP32_UNSAFE', True)
            if not member['meta']['original_axis2_is_axial']:
                issue(name, 'ORIGINAL_AXIS2_NONAXIAL_FROZEN_NATIVE_BLOCKED', True)
            if name == 'Mask' and infection_values is not None:
                unknown = set(member['stats']['scaled_value_counts']) - {str(row['value']) for row in class_map}
                if unknown:
                    issue('labels', 'OBSERVED_VALUES_WITHOUT_CLASS_MAP')
            current = Path(path).stat()
            require(member['meta']['source_file_identity'] == dict(device=current.st_dev, inode=current.st_ino,
                bytes=current.st_size, mtime_ns=current.st_mtime_ns), 'SOURCE_CHANGED_DURING_SCAN')
            loaded[name] = member
        except (Invalid, ValueError, OSError, nib.filebasedimages.ImageFileError, nib.spatialimages.HeaderDataError) as exc:
            if check_failures:
                raise
            issue(name, str(exc)[:500], True)
        finally:
            if member is not None and member.get('raw') is not None:
                member['raw']._mmap.close()
                member['raw'] = None
    if len(loaded) == 2:
        ct, mask = loaded['CT'], loaded['Mask']
        same_shape = ct['native_shape'] == mask['native_shape']
        delta = None
        if same_shape:
            delta = float(np.max(np.linalg.norm(apply(ct['native_to_lps'], corners(ct['native_shape'])) -
                                               apply(mask['native_to_lps'], corners(mask['native_shape'])), axis=1)))
        aligned = same_shape and delta <= limits['tolerance_world_mm']
        axial = ct['meta']['original_axis2_is_axial'] and mask['meta']['original_axis2_is_axial']
        result['geometry'] = dict(status='PASS' if aligned else 'REJECT',
            same_native_shape=same_shape, max_corner_mismatch_mm=delta,
            tolerance_world_mm=limits['tolerance_world_mm'], resampled=False)
        if not axial:
            result['geometry']['status'] = 'REJECT'
        if not aligned:
            issue('geometry', 'CT_MASK_NATIVE_GEOMETRY_MISMATCH', True)
        depth, height, width = ct['native_shape']
        selections = []
        for j in range(8):
            check()
            z = int((j + .5) * depth / 8)
            points = np.array([[z, 0, 0], [z, height - 1, 0], [z, 0, width - 1], [z, height - 1, width - 1]], dtype=float)
            world = apply(ct['native_to_lps'], points)
            roundtrip = apply(np.linalg.inv(ct['native_to_lps']), world)
            error = float(np.max(np.abs(roundtrip - points)))
            if error > limits['roundtrip_vox']:
                issue('geometry', 'K8_WORLD_ROUNDTRIP_FAILURE', True)
            canonical_points = apply(np.linalg.inv(ct['original_from_canonical']), apply(ct['original_from_native'], points))
            canonical_z = float(canonical_points[0, 2]) if np.allclose(canonical_points[:, 2], canonical_points[0, 2], atol=limits['roundtrip_vox'], rtol=0) else None
            selections.append(dict(slot=j, native_Z=z, native_plane_corners_ZYX=points.tolist(),
                original_nifti_Z=z,
                corresponding_canonical_Z=canonical_z,
                original_plane_corners_XYZ=apply(ct['original_from_native'], points).tolist(),
                canonical_plane_corners_XYZ=canonical_points.tolist(),
                physical_plane_corners_LPS_mm=world.tolist(), world_roundtrip_max_vox=error,
                mask_counts=mask['stats']['per_native_Z'][z] if aligned else None))
        result['K8'] = dict(rule='floor((2*j+1)*original_NIfTI_Z/16), j=0..7; NO flips before sampling',
            reference='ENCODER_DATA_FROZEN_CONTRACT_V2 native=originalXYZ.transpose(2,1,0)',
            depth=depth, selections=selections)
        ct['meta']['selected_original_nifti_Z'] = [row['original_nifti_Z'] for row in selections]
        ct['meta']['selected_canonical_Z'] = [row['corresponding_canonical_Z'] for row in selections]
        canonical_rows = []
        cx, cy, cz = ct['canonical_shape']
        if cz >= 8:
            for j in range(8):
                z = int((j + .5) * cz / 8)
                points = np.array([[0, 0, z], [cx - 1, 0, z], [0, cy - 1, z], [cx - 1, cy - 1, z]], dtype=float)
                originals = apply(ct['original_from_canonical'], points)
                canonical_rows.append(dict(slot=j, canonical_Z=z, canonical_plane_corners_XYZ=points.tolist(),
                    original_plane_corners_XYZ=originals.tolist(),
                    physical_plane_corners_LPS_mm=apply(RAS_TO_LPS @ np.asarray(ct['meta']['original_XYZ_to_RAS_mm']), originals).tolist()))
        result['canonical_reference_K8'] = dict(status='METADATA_REFERENCE_ONLY_NOT_FROZEN_INPUT',
            selections=canonical_rows, used_for_frozen_K8=False)
        transform_fields = {key: ct['meta'][key] for key in ('shape_original_XYZ', 'native_shape_ZYX',
            'native_ZYX_to_original_XYZ', 'native_ZYX_to_LPS_mm', 'original_XYZ_to_native_ZYX', 'LPS_mm_to_native_ZYX',
            'canonical_shape_XYZ', 'canonical_to_original_XYZ', 'original_to_canonical_XYZ', 'canonical_to_LPS_mm',
            'native_definition', 'orientation_transform')}
        result['geometry']['shape_and_transform_sha256'] = hashlib.sha256(
            json.dumps(transform_fields, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        result['geometry']['shape_and_transform_hash_algorithm'] = 'SHA256 canonical JSON sort_keys compact separators UTF8'
    if any(item['severity'] == 'REJECT' for item in result['reasons']):
        result['status'] = 'REJECT'
    elif result['reasons']:
        result['status'] = 'UNKNOWN'
    else:
        result['status'] = 'PASS'
    return result


def export_fixed8(ct_path, mask_path, qa, evidence, outdir, limits, check=lambda: None):
    """Future authorized one-batch native planes; never resize or run a model.

    Source bindings are supplied by the controlling extractor in
    evidence.member_bindings.{CT,Mask}, each with path and uncompressed SHA256.
    Array hash reuses the frozen LOC encoding: str((shape, str(dtype))) then
    C-order bytes, incrementally. NPY file SHA is a separate stream hash.
    """
    limits = {**DEFAULT_LIMITS, **(limits or {})}
    require(qa.get('status') != 'REJECT' and qa.get('geometry', {}).get('status') == 'PASS', 'EXPORT_GEOMETRY_NOT_QUALIFIED')
    selected = qa['K8']['selections']
    require(len(selected) == 8 and all(row['original_nifti_Z'] == row['native_Z'] for row in selected), 'ORIGINAL_NATIVE_K8_REQUIRED')
    bindings = evidence.get('member_bindings', {})
    require(all(binding_present(bindings.get(name)) for name in ('CT', 'Mask')), 'EXPORT_SOURCE_BINDINGS_REQUIRED')
    root = Path(outdir)
    require(not root.exists() and not root.is_symlink(), 'EXPORT_NO_OVERWRITE')
    shape = [8, *qa['members']['CT']['native_shape_ZYX'][1:]]
    plane_voxels = math.prod(shape[1:])
    require(plane_voxels <= limits['max_native_plane_voxels'], 'EXPORT_PLANE_CAP')
    mapping = qa['labels'].get('infection_values')
    observed = qa['members']['Mask']['statistics']['scaled_value_counts']
    supplied_map = evidence.get('class_map') or []
    gt_known = (isinstance(mapping, list) and bool(mapping) and
        not qa['members']['Mask']['statistics']['mask_noninteger'] and
        set(observed) <= {str(row['value']) for row in supplied_map})
    planned = math.prod(shape) * (4 + 1 + 2 * int(gt_known))
    require(planned + 4096 <= limits.get('max_export_bytes', 134217728), 'EXPORT_OUTPUT_CAP')
    check()
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    arrays = []
    chunk_voxels = max(1, limits['working_numeric_buffer_cap_bytes'] // 128)
    hu_verified = qa['HU']['status'] == 'NATIVE_HU_VERIFIED'
    complete_reference = (qa.get('qualification', {}).get('extent', {}).get('effective_status') == 'VERIFIED' and
                          evidence.get('extent') == 'COMPLETE_REFERENCE_VERIFIED')
    for kind, source_name, source_path, dtype in [('CT', 'CT', ct_path, '<f4'),
            ('FOV_SUPPORT', 'CT', ct_path, '|b1')] + ([('INFECTION_GT', 'Mask', mask_path, '|b1'),
            ('REFERENCE_DOMAIN', 'Mask', mask_path, '|b1')] if gt_known else []):
        check()
        member = None
        output = None
        path = root/(kind + '.npy')
        plane_records = []
        try:
            member = load_native(source_path, limits, check)
            require(member['meta']['source_file_identity'] == qa['members'][source_name]['source_file_identity'], 'EXPORT_SOURCE_FILE_IDENTITY_DRIFT')
            require(member['meta']['native_shape_ZYX'] == qa['members'][source_name]['native_shape_ZYX'], 'EXPORT_SOURCE_SHAPE_DRIFT')
            require(member['meta']['native_ZYX_to_LPS_mm'] == qa['members'][source_name]['native_ZYX_to_LPS_mm'], 'EXPORT_SOURCE_AFFINE_DRIFT')
            with path.open('xb'):
                pass
            output = np.lib.format.open_memmap(path, mode='w+', dtype=np.dtype(dtype), shape=tuple(shape), fortran_order=False)
            array_hash = hashlib.sha256(str((tuple(shape), str(output.dtype))).encode())
            with path.open('rb') as stream:
                file_hash = hashlib.sha256(stream.read(output.offset))
            for slot, row in enumerate(selected):
                if member['raw'] is None:
                    member['raw'] = member['proxy'].get_unscaled()
                    require(isinstance(member['raw'], np.memmap) and not member['raw'].flags.writeable,
                            'READONLY_MEMMAP_REQUIRED')
                z = row['native_Z']
                source = member['raw'][:, :, z].T
                plane_hash = hashlib.sha256(str((tuple(shape[1:]), str(output.dtype))).encode())
                for y in range(shape[1]):
                    for x in range(0, shape[2], chunk_voxels):
                        check()
                        stop = min(shape[2], x+chunk_voxels)
                        if kind == 'FOV_SUPPORT' or (kind == 'REFERENCE_DOMAIN' and complete_reference):
                            values = np.ones(stop-x, dtype=np.bool_)
                        else:
                            scaled = np.asarray(source[y, x:stop], dtype=np.float64) * member['slope'] + member['inter']
                            require(np.isfinite(scaled).all(), 'EXPORT_NONFINITE_SOURCE')
                            values = scaled.astype('<f4') if kind == 'CT' else np.isin(scaled, mapping)
                            require(np.isfinite(values).all(), 'EXPORT_FP32_OVERFLOW')
                        output[slot, y, x:stop] = values
                        raw_bytes = values.tobytes(order='C')
                        array_hash.update(raw_bytes); plane_hash.update(raw_bytes); file_hash.update(raw_bytes)
                output.flush()
                source = None
                member['raw']._mmap.close()
                member['raw'] = None
                if hasattr(output._mmap, 'madvise') and hasattr(mmap, 'MADV_DONTNEED'):
                    output._mmap.madvise(mmap.MADV_DONTNEED)
                plane_records.append(dict(slot=slot, original_nifti_Z=z, native_Z=z,
                    shape=shape[1:], dtype=output.dtype.str, shape_dtype_C_bytes_sha256=plane_hash.hexdigest(),
                    source_binding=bindings[source_name], physical_plane_corners_LPS_mm=row['physical_plane_corners_LPS_mm']))
            output.flush()
            with path.open('r+b') as stream:
                os.fsync(stream.fileno())
            arrays.append(dict(kind=kind, path=str(path), shape=shape, dtype=output.dtype.str,
                bytes=path.stat().st_size, npy_stream_sha256=file_hash.hexdigest(),
                shape_dtype_C_bytes_sha256=array_hash.hexdigest(), planes=plane_records,
                status=('NATIVE_HU_VERIFIED_NOT_MODEL_EXECUTED' if hu_verified else 'NOT_MODEL_READY_HU_UNPROVEN') if kind == 'CT' else
                    ('GEOMETRIC_FOV_SUPPORT_NOT_NORMAL_GT' if kind == 'FOV_SUPPORT' else
                     ('COMPLETE_BOUND_REFERENCE_DOMAIN' if complete_reference else 'KNOWN_INFECTION_POSITIVES_ONLY_BACKGROUND_UNKNOWN') if kind == 'REFERENCE_DOMAIN' else 'EXPLICIT_INFECTION_CLASSES_ONLY'),
                reference_domain='COMPLETE_BOUND_REFERENCE' if complete_reference else 'POSITIVE_ANNOTATED_ONLY', source_binding=bindings[source_name]))
        finally:
            if output is not None:
                output._mmap.close()
            if member is not None and member.get('raw') is not None:
                member['raw']._mmap.close()
    return dict(schema='FIRST_CASE_FIXED8_NATIVE_EXPORT_V1', arrays=arrays,
        infection_GT_status='EXPORTED_EXPLICIT_CLASSES_ONLY' if gt_known else 'UNKNOWN_NOT_EXPORTED',
        array_hash_encoding='Frozen LOC SHA256 str((array.shape,str(array.dtype))).encode then C-order bytes',
        LOC_hash_schema_acceptance='FROZEN_ENCODING_REUSED_GENERATED_PARITY_REQUIRED', planned_payload_bytes=planned, medical_denominator=None,
        resize_performed=False, model_ready=False, full_region_metrics_enabled=False)
