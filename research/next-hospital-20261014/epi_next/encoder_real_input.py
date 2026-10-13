"""Exact DATA-v3 consumption and deterministic center-patch geometry. No GT use."""
from __future__ import annotations
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
from .encoder_ctfm_mps_smoke import file_sha, write_new

DATA_V3_SHA = '0000000000000000000000000000000000000000000000000000000000000000'


def read_bound_json(path, expected):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('SHA mismatch for required DATA metadata')
    return json.loads(raw)


def center_ledger(shape, affine, patch_shape=(64,64,64)):
    """SPL in LPS means axes +Z,+Y,+X. Reject oblique/ambiguous inputs."""
    shape = np.asarray(shape, dtype=int)
    affine = np.asarray(affine, dtype=np.float64)
    if shape.shape != (3,) or affine.shape != (4,4) or not np.isfinite(affine).all():
        raise ValueError('finite 3D shape/affine required')
    if not np.allclose(affine[3], [0,0,0,1]):
        raise ValueError('homogeneous affine required')
    basis = affine[:3,:3]
    spacing = np.linalg.norm(basis, axis=0)
    if np.any(spacing <= 0):
        raise ValueError('positive native spacing required')
    axes = np.argmax(np.abs(basis),axis=0)
    if len(set(axes)) != 3 or not np.allclose(np.abs(basis / spacing), np.eye(3)[:,axes],atol=1e-7):
        raise ValueError('only unambiguous axis-aligned signed permutations supported')
    target = [2,1,0]
    permutation = [int(np.flatnonzero(axes==world)[0]) for world in target]
    orient_to_native = np.eye(4)
    orient_to_native[:3,:3] = 0
    flips = []
    for dst,src in enumerate(permutation):
        sign = 1 if basis[target[dst],src] > 0 else -1
        orient_to_native[src,dst] = sign
        orient_to_native[src,3] = 0 if sign > 0 else shape[src]-1
        flips.append(sign < 0)
    oriented_shape = shape[permutation]
    patch_shape = np.asarray(patch_shape,dtype=int)
    if patch_shape.shape != (3,) or np.any(patch_shape < 1) or np.any(oriented_shape < patch_shape):
        raise ValueError('patch must fit native volume; new padding forbidden')
    start = (oriented_shape-patch_shape)//2
    patch_to_orient = np.eye(4); patch_to_orient[:3,3] = start
    patch_to_native = orient_to_native @ patch_to_orient
    patch_to_lps = affine @ patch_to_native
    points = np.array([*itertools.product(*[(0,int(n-1)) for n in patch_shape]),
                       tuple((patch_shape-1)/2)],dtype=np.float64)
    h = np.column_stack([points,np.ones(len(points))]).T
    native = patch_to_native @ h
    restored = np.linalg.inv(patch_to_native) @ native
    max_error = float(np.max(np.abs(restored-h)))
    lps=patch_to_lps@h
    lps_restored=np.linalg.inv(patch_to_lps)@lps
    lps_error=float(np.max(np.abs(lps_restored-h)))
    mm_error=float(np.max(np.abs(patch_to_lps@lps_restored-lps)))
    if max(max_error,lps_error)>1e-8: raise ValueError('native/LPS roundtrip exceeds declared geometry tolerance')
    expected_basis = np.zeros((3,3))
    for a,w in enumerate(target): expected_basis[w,a] = spacing[permutation[a]]
    if not np.allclose(patch_to_lps[:3,:3], expected_basis, atol=1e-7):
        raise ValueError('SPL laterality/orientation mismatch')
    return dict(native_shape_krc=shape.tolist(), orientation='SPL',
        permutation=permutation, flips=flips, oriented_shape=oriented_shape.tolist(),
        crop_start_spl=start.tolist(), patch_shape_spl=patch_shape.tolist(),
        spacing_spl_mm=spacing[permutation].tolist(),
        orient_to_native=orient_to_native.tolist(), patch_to_native=patch_to_native.tolist(),
        native_to_patch=np.linalg.inv(patch_to_native).tolist(), patch_to_lps=patch_to_lps.tolist(),
        lps_to_patch=np.linalg.inv(patch_to_lps).tolist(),
        corner_native_indices=native[:3,:8].T.tolist(),
        center_offset_voxels_spl=(start+(patch_shape-1)/2-(oriented_shape-1)/2).tolist(),
        roundtrip_max_voxel_error=max_error,lps_roundtrip_max_voxel_error=lps_error,
        lps_roundtrip_max_mm_error=mm_error,roundtrip_tolerance_voxels=1e-8,resampling='NONE_NATIVE_SPACING',
        voxel_edge_extent_mm=(patch_shape*spacing[permutation]).tolist(),
        feature_lattice=dict(stride_spl=[16,16,16],nominal_center_offset=[0,0,0],
            receptive_field_voxels=[469,469,469],verification='derived k3/p1 conv graph; not clinical localization',
            feature_to_native=(patch_to_native @ np.diag([16,16,16,1])).tolist()),
        patch_full_volume_equivalence='NOT ASSERTED')


def prepare_center_patch(volume, affine, patch_shape=(64,64,64)):
    if volume.ndim != 3 or volume.dtype != np.float32:
        raise ValueError('DATA native float32 HU volume required')
    ledger = center_ledger(volume.shape, affine, patch_shape)
    oriented = volume.transpose(ledger['permutation'])
    for axis,flip in enumerate(ledger['flips']):
        if flip: oriented = np.flip(oriented,axis=axis)
    start = ledger['crop_start_spl']
    patch = np.array(oriented[tuple(slice(s,s+n) for s,n in zip(start,patch_shape))], dtype=np.float32,copy=True)
    if patch.shape != tuple(patch_shape) or not np.isfinite(patch).all():
        raise ValueError('finite exact patch required')
    # Independent voxel equality check, not merely an invertible affine identity.
    matrix = np.array(ledger['patch_to_native'])
    probes = [*itertools.product(*[(0,n-1) for n in patch_shape]), tuple(n//2 for n in patch_shape)]
    for point in probes:
        mapped = matrix @ [*point,1]
        index = tuple(np.rint(mapped[:3]).astype(int))
        if patch[point] != volume[index]:
            raise ValueError('patch/native corner or center sample mismatch')
    normalized = (np.clip(patch,-1024,2048)+np.float32(1024))/np.float32(3072)
    normalized = np.ascontiguousarray(normalized[None,None],dtype=np.float32)
    ledger.update(raw_patch_hu_range=[float(patch.min()),float(patch.max())],
        normalized_range=[float(normalized.min()),float(normalized.max())],
        input_shape=list(normalized.shape), input_content_sha256=hashlib.sha256(normalized.tobytes()).hexdigest(),
        independent_sample_checks=len(probes), foreground_crop='not used: geometric center variant',
        official_conformance='SPL and HU clip/scale match card; crop and native spacing are bounded engineering variant')
    return normalized,ledger


def consume_v3(path, directory):
    """Validate only metadata + native volumes needed here; no mask/polygon reads."""
    data=read_bound_json(path,DATA_V3_SHA)
    if data['schema']!='EPI_NEXT_DATA_DELIVERY_V3' or data['case_count']!=3 or data['sop_count']!=715:
        raise ValueError('exact v3 three-case scope required')
    contract=data['consumer_contract']
    if (contract['local_cpu']!='ALLOWED' or not contract['local_mps'].startswith('ALLOWED')
            or contract['mps_current_owner']!='ENCODER' or not contract['local_use_only']):
        raise ValueError('consumer permissions do not match dispatch')
    allow=read_bound_json(data['allowlist_path'],data['allowlist_sha256'])
    auth=data['authorization_reference']
    read_bound_json(auth['receipt_path'],auth['receipt_sha256'])
    read_bound_json(auth['proposal_path'],auth['proposal_sha256'])
    if (allow['case_count']!=3 or allow['sop_count']!=715 or len(allow['records'])!=3
            or len({r['patient_id'] for r in allow['records']})!=3
            or sum(r['sop_count'] for r in allow['records'])!=715):
        raise ValueError('formal allowlist scope changed')
    mappings=data['spatial_mapping']['cases']
    if len(mappings)!=3: raise ValueError('three spatial mappings required')
    consumed=[]
    for ordinal,(record,mapping) in enumerate(zip(allow['records'],mappings),1):
        # Hash the producer manifest without parsing its annotation/vertex fields.
        # Native mapping and SOP inventory are consumed from the v3 projection.
        if file_sha(mapping['manifest_path'])!=mapping['manifest_sha256']:
            raise ValueError('case manifest SHA mismatch')
        if record['split']!='train' or mapping['patient_id']!=record['patient_id']:
            raise ValueError('case/order/split mismatch')
        permitted={(r['study_uid'],r['series_uid'],r['sop_uid']) for r in record['rows']}
        if (len(permitted)!=record['sop_count'] or len(record['rows'])!=record['sop_count']
                or any(r['series_uid']!=record['series_uid'] or r['study_uid'] not in record['study_uids']
                    or r['patient_id']!=record['patient_id'] or r['split']!='train' for r in record['rows'])):
            raise ValueError('exact Study/Series/SOP membership mismatch')
        ordered=mapping['ordered_sop_uids']
        if (mapping['status']!='NATIVE_GEOMETRY_AND_HU_TECHNICAL_PASS' or mapping['resampling']!='NONE_NATIVE_GRID'
                or len(ordered)!=mapping['shape_krc'][0] or len(set(ordered))!=len(ordered)
                or set(ordered)!={r[2] for r in permitted}):
            raise ValueError('native geometry/volume/SOP order not verified')
        if file_sha(mapping['native_hu_volume_path'])!=mapping['native_hu_volume_sha256']:
            raise ValueError('native volume SHA mismatch')
        affine=np.asarray(mapping['affine_lps'],dtype=np.float64)
        inverse=np.asarray(mapping['inverse_affine_lps'],dtype=np.float64)
        if np.max(np.abs(affine@inverse-np.eye(4)))>1e-8 or not np.allclose(np.linalg.norm(affine[:3,:3],axis=0),mapping['spacing_krc_mm']):
            raise ValueError('native affine/inverse mismatch')
        native=np.load(mapping['native_hu_volume_path'],mmap_mode='r',allow_pickle=False)
        if list(native.shape)!=mapping['shape_krc'] or native.dtype!=np.float32:
            raise ValueError('native volume shape/dtype mismatch')
        # Pixel array is consumed as a memmap only after metadata+asset hashes pass.
        del native
        consumed.append(dict(case_index=ordinal, mapping=mapping,
            case_manifest_sha256=mapping['manifest_sha256'], authorized_sop_count=record['sop_count'],
            header_audit_scope='DATA v3 producer ledger + coordinator acceptance; no redundant raw DICOM header re-audit'))
    receipt=dict(status='PASS',schema='ENCODER_DATA_V3_CONSUMER_RECEIPT_V1', data_delivery_sha256=DATA_V3_SHA,
        allowlist_sha256=data['allowlist_sha256'],approval_receipt_sha256=auth['receipt_sha256'],
        case_count=3,sop_count=715,case_manifest_hashes=[c['case_manifest_sha256'] for c in consumed],
        native_volume_hashes=[c['mapping']['native_hu_volume_sha256'] for c in consumed],
        exact_membership_status='PASS',native_affine_inverse_status='PASS',
        GT_masks_or_polygons_read=False,GT_manifest_bytes_hashed_only=True,GT_annotation_fields_parsed=False,
        new_allowlist_created=False,training_executed=False)
    write_new(directory/'consumer_receipt.json',receipt)
    return consumed,receipt
