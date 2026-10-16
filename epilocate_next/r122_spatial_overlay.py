"""Generated-only research overlay. No real input CLI, service or MVP import.

NIfTI storage XYZ -> scaled native XYZ -> closest-RAS canonical XYZ ->
display column/row. Canonicalization reorders/flips, never resamples voxels.
"""
import argparse
import hashlib
import json
from pathlib import Path

import nibabel as nib
import numpy as np

from .infection_overlay_research_v1 import RAS_TO_LPS
from .r108_research_geometry import (
    EVIDENCE, nifti1_header_geometry, maximum_world_difference,
    research_layer_bundle, valid_sha,
)

MAX_GENERATED_VOXELS = 65536
TEMPLATE = Path(__file__).with_name('r122_spatial_overlay.html')


def _source(source, case_id):
    if source.get('scope') != 'GENERATED_ONLY' or source.get('case_id') != case_id:
        raise ValueError('GENERATED_SAME_CASE_ONLY_NO_REAL_RENDERING')
    if not all(isinstance(source.get(k),str) and source[k].strip() for k in ('source_id','method','version','target')):
        raise ValueError('EXPLICIT_GENERATED_LAYER_PROVENANCE_REQUIRED')
    if not valid_sha(source.get('artifact_sha256')):
        raise ValueError('DECLARED_GENERATED_ARTIFACT_SHA_REQUIRED')
    image = source['image']
    geometry = nifti1_header_geometry(source['raw_header'])
    if (len(image.shape) != 3 or np.prod(image.shape) > MAX_GENERATED_VOXELS
            or tuple(image.shape[::-1]) != geometry.grid.shape_zyx
            or image.get_data_dtype() != np.dtype(geometry.stored_dtype)
            or not np.allclose(RAS_TO_LPS @ image.affine,geometry.grid.affine_lps_xyz,atol=1e-4,rtol=0)):
        raise ValueError('BOUNDED_NATIVE_HEADER_IMAGE_GEOMETRY_REQUIRED')
    return geometry


def display_point(payload, column, row, slice_index):
    nx,ny,nz = payload['coordinates']['canonical']['shape_xyz']
    if not (0 <= column < nx and 0 <= row < ny and 0 <= slice_index < nz):
        raise ValueError('DISPLAY_POINT_OUTSIDE_GENERATED_FOV')
    canonical = np.array([column,ny-1-row,slice_index,1.])
    c = payload['coordinates']
    native = np.asarray(c['native_from_canonical_xyz']) @ canonical
    ras = np.asarray(c['canonical']['affine_ras_mm']) @ canonical
    return dict(display_column_row=[column,row],canonical_xyz=canonical[:3].tolist(),
                native_xyz=native[:3].tolist(),raw_storage_xyz=native[:3].tolist(),
                world_RAS_mm=ras[:3].tolist(),world_LPS_mm=(RAS_TO_LPS @ ras)[:3].tolist())


def prepare_generated_overlay(inputs, case_id):
    """In-memory generated inputs with raw header/provenance; no path loader."""
    if not isinstance(case_id,str) or not case_id.startswith('GENERATED_'):
        raise ValueError('GENERATED_CASE_REQUIRED')
    if set(inputs)-{'CT','GT','CAM'} or 'CT' not in inputs:
        raise ValueError('CT_AND_OPTIONAL_GT_CAM_ONLY')
    ct = inputs['CT'];native = _source(ct,case_id)
    canonical_ct = nib.as_closest_canonical(ct['image'])
    canonical_affine = np.asarray(canonical_ct.affine,dtype=float)
    transform = np.linalg.inv(ct['image'].affine) @ canonical_affine
    data = np.asarray(canonical_ct.get_fdata(dtype=np.float64))
    if not np.isfinite(data).all():
        raise ValueError('FINITE_GENERATED_CT_REQUIRED')
    inverse = np.linalg.inv(transform)
    if not np.allclose(transform @ inverse,np.eye(4),atol=1e-12,rtol=0):
        raise ValueError('CANONICAL_NATIVE_INVERSE_UNVERIFIED')
    statuses = {};layers = [];arrays = {};coverage = None
    for kind in ('CT','GT','CAM'):
        source = inputs.get(kind)
        if source is None:
            statuses[kind] = dict(status='UNKNOWN',reason='MISSING_'+kind,source=None)
            arrays[kind] = None
            continue
        geometry = _source(source,case_id)
        meta = {k:source[k] for k in ('source_id','method','version','target','artifact_sha256')}
        if maximum_world_difference(native.grid,geometry.grid) > 1e-4:
            statuses[kind] = dict(status='UNKNOWN',reason='NATIVE_GEOMETRY_MISMATCH_OVERLAY_BLOCKED',source=meta)
            arrays[kind] = None
            continue
        canonical = nib.as_closest_canonical(source['image'])
        if canonical.shape != canonical_ct.shape or not np.allclose(canonical.affine,canonical_affine,atol=1e-4,rtol=0):
            raise ValueError('CANONICAL_LAYER_GEOMETRY_CONFLICT')
        values = canonical.get_fdata(dtype=np.float64)
        if not np.isfinite(values).all() or kind == 'GT' and not np.isin(values,[0,1]).all():
            raise ValueError('FINITE_LAYER_AND_BINARY_REFERENCE_REQUIRED')
        status = 'PASS';reason = 'GENERATED_SAME_SPACE_ONLY'
        if kind == 'GT':
            extent = source.get('reference_extent')
            cov = source.get('coverage_xyz')
            if extent not in ('FULL','PARTIAL','UNKNOWN','CONFLICT'):
                raise ValueError('REFERENCE_EXTENT_REQUIRED')
            if extent == 'FULL' and cov is None:
                cov = np.ones(source['image'].shape,dtype=bool)
            if cov is None or np.asarray(cov).dtype != np.bool_ or np.asarray(cov).shape != source['image'].shape:
                raise ValueError('EXPLICIT_PARTIAL_REFERENCE_COVERAGE_REQUIRED')
            if extent in ('UNKNOWN','CONFLICT'):
                cov = np.zeros(source['image'].shape,dtype=bool)
            oriented = nib.as_closest_canonical(nib.Nifti1Image(np.asarray(cov,dtype=np.uint8),source['image'].affine))
            coverage = oriented.get_fdata().transpose(2,1,0).ravel().astype(bool).tolist()
            if extent != 'FULL' or not all(coverage):status,reason = 'UNKNOWN','PARTIAL_OR_UNKNOWN_REFERENCE'
        arrays[kind] = np.asarray(values).transpose(2,1,0).ravel().tolist()
        statuses[kind] = dict(status=status,reason=reason,source=meta,evidence_type=EVIDENCE[kind])
        layers.append(dict(kind=kind,method=source['method'],version=source['version'],target=source['target'],
                           artifact_sha256=source['artifact_sha256'],grid_sha256=native.grid.digest(),
                           evidence_type=EVIDENCE[kind],value_semantics=EVIDENCE[kind],evidence_status='GENERATED_ONLY'))
    bundle = research_layer_bundle(case_id,'GENERATED_STUDY','GENERATED_SERIES',native.grid,layers)
    return dict(schema='EPI_NEXT_R122_GENERATED_OVERLAY_V1',scope='GENERATED_ONLY',case_id=case_id,
                qualification='UNKNOWN_REAL_MEDICAL_REFERENCE_NOT_ACCESSED',identity_verified=False,
                bundle=bundle,layers=statuses,arrays=arrays,reference_coverage=coverage,
                coordinates=dict(raw=dict(axes='NIfTI stored XYZ',shape_xyz=list(ct['image'].shape),
                                          dtype=native.stored_dtype,slope=native.scaling_slope,intercept=native.scaling_intercept,
                                          source=ct['source_id'],note='raw/native indices coincide in this NIfTI profile; values need scaling'),
                                 native=dict(axes='native XYZ / world RAS and LPS mm',affine_ras_mm=ct['image'].affine.tolist(),
                                             grid_sha256=native.grid.digest(),qform_code=native.qform_code,sform_code=native.sform_code),
                                 canonical=dict(axes='closest RAS XYZ; reorder/flip only, no resampling',shape_xyz=list(data.shape),
                                                affine_ras_mm=canonical_affine.tolist()),
                                 display=dict(axes='column=x; row=canonicalY-1-y; slice=canonicalZ',
                                              convention='left L / right R / top A / bottom P; voxel-centre indices',
                                              intensity_window=[-1100,0],window_scope='GENERATED_DISPLAY_ONLY_NOT_R18_PREPROCESS'),
                                 native_from_canonical_xyz=transform.tolist(),canonical_from_native_xyz=inverse.tolist()),
                medical_payload_reads=0,model_calls=0,mvp_auto_import=False)


def render_generated_overlay(payload):
    if payload.get('scope') != 'GENERATED_ONLY' or payload.get('mvp_auto_import') is not False:
        raise ValueError('GENERATED_RESEARCH_VIEW_ONLY')
    data = json.dumps(payload,ensure_ascii=True,allow_nan=False).replace('<','\\u003c')
    return TEMPLATE.read_text().replace('__GENERATED_PAYLOAD__',data)


def generate_demo(output, without_cam=False):
    """Exclusive new directory, creates every input locally; accepts no data path."""
    output = Path(output);output.mkdir(mode=0o700,parents=True,exist_ok=False)
    shape = (5,6,4);x,y,z = np.indices(shape)
    ct = (100*x+10*y+z).astype(np.int16)
    mask = np.zeros(shape,dtype=np.uint8);mask[1,3,1] = 1
    cam = np.zeros(shape,dtype=np.float64);cam[1,3,1] = 4;cam[3,1,1] = -2
    affine = np.array([[0,-2,0,20],[3,0,0,-30],[0,0,-4,50],[0,0,0,1.]],dtype=float)
    inputs = {}
    for kind,values in [('CT',ct),('GT',mask)]+([] if without_cam else [('CAM',cam)]):
        image = nib.Nifti1Image(values,affine)
        image.set_qform(affine,1);image.set_sform(affine,1);image.header.set_xyzt_units('mm')
        image.header.set_slope_inter(2.,-1024.) if kind == 'CT' else image.header.set_slope_inter(1.,0.)
        path = output/('GENERATED_'+kind+'.nii');nib.save(image,path)
        raw = path.read_bytes()
        inputs[kind] = dict(scope='GENERATED_ONLY',case_id='GENERATED_ASYMMETRIC',image=nib.load(path),
                            raw_header=raw[:348],source_id=path.name,artifact_sha256=hashlib.sha256(raw).hexdigest(),
                            method={'CT':'GENERATED_CT_ENCODING','GT':'GENERATED_DOCTOR_MASK_INTERFACE_FIXTURE','CAM':'GENERATED_SIGNED_MARGIN_CAM'}[kind],
                            version='r122-generated-v1',target='CLASS1_MINUS_CLASS0' if kind == 'CAM' else 'GENERATED_SOURCE',
                            reference_extent='FULL')
    payload = prepare_generated_overlay(inputs,'GENERATED_ASYMMETRIC')
    with (output/'overlay.json').open('x') as f:json.dump(payload,f,indent=2,allow_nan=False);f.write('\n')
    with (output/'overlay.html').open('x') as f:f.write(render_generated_overlay(payload))
    return payload,inputs


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--generated-output',type=Path,required=True)
    p.add_argument('--without-cam',action='store_true')
    args = p.parse_args();payload,_ = generate_demo(args.generated_output,args.without_cam)
    print(json.dumps(dict(status='GENERATED_ARTIFACTS_WRITTEN',output=str(args.generated_output),
                          layers=payload['layers'],real_medical_reads=0,models=0)))


if __name__ == '__main__':main()
