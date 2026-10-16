"""Only new generated research geometry/display contracts; no real data paths."""
import hashlib

import nibabel as nib
import numpy as np
import pytest

from epilocate_next.r122_spatial_overlay import (
    generate_demo, prepare_generated_overlay, display_point, render_generated_overlay,
)


def test_asymmetric_nifti_scaling_canonical_marker_and_world_inverse(tmp_path):
    p,inputs = generate_demo(tmp_path/'generated')
    assert p['coordinates']['raw']['slope'] == 2 and p['coordinates']['raw']['intercept'] == -1024
    assert p['coordinates']['canonical']['shape_xyz'] == [6,5,4]
    point = display_point(p,2,3,2)
    assert np.allclose(point['native_xyz'],[1,3,1],atol=1e-12,rtol=0)
    assert np.allclose(point['world_RAS_mm'],[14,-27,46],atol=1e-12,rtol=0)
    assert np.allclose(point['world_LPS_mm'],[-14,27,46],atol=1e-12,rtol=0)
    ix = (2*5+1)*6+2
    assert p['arrays']['CT'][ix] == -762
    assert p['arrays']['GT'][ix] == 1 and p['arrays']['CAM'][ix] == 4
    # Every native centre must survive canonical/display roundtrip.
    a = np.asarray(p['coordinates']['canonical_from_native_xyz'])
    for native in np.ndindex(inputs['CT']['image'].shape):
        c = a @ [*native,1]
        returned = display_point(p,float(c[0]),float(4-c[1]),float(c[2]))
        assert np.allclose(returned['native_xyz'],native,atol=1e-12,rtol=0)


def test_missing_cam_is_unknown_null_and_has_no_fabricated_layer(tmp_path):
    p,_ = generate_demo(tmp_path/'generated',without_cam=True)
    assert p['arrays']['CAM'] is None and p['layers']['CAM']['status'] == 'UNKNOWN'
    assert p['layers']['CAM']['reason'] == 'MISSING_CAM'
    assert {x['kind'] for x in p['bundle']['layers']} == {'CT','GT'}
    assert p['mvp_auto_import'] is False and p['identity_verified'] is False


def test_partial_reference_keeps_unknown_and_explicit_coverage(tmp_path):
    _,inputs = generate_demo(tmp_path/'generated')
    gt = dict(inputs['GT']);cov = np.zeros(gt['image'].shape,dtype=bool);cov[1,3,1] = True
    gt.update(reference_extent='PARTIAL',coverage_xyz=cov)
    p = prepare_generated_overlay({**inputs,'GT':gt},'GENERATED_ASYMMETRIC')
    assert p['layers']['GT']['status'] == 'UNKNOWN'
    assert sum(p['reference_coverage']) == 1 and p['arrays']['GT'] is not None
    assert p['qualification'] == 'UNKNOWN_REAL_MEDICAL_REFERENCE_NOT_ACCESSED'


def test_mismatched_native_geometry_blocks_layer_without_resampling(tmp_path):
    _,inputs = generate_demo(tmp_path/'generated')
    gt = inputs['GT'];affine = gt['image'].affine.copy();affine[0,3] += 10
    image = nib.Nifti1Image(np.asanyarray(gt['image'].dataobj).astype(np.uint8),affine)
    image.set_qform(affine,1);image.set_sform(affine,1);image.header.set_xyzt_units('mm');image.header.set_slope_inter(1,0)
    path = tmp_path/'GENERATED_MISMATCH.nii';nib.save(image,path);raw = path.read_bytes()
    altered = dict(gt,image=nib.load(path),raw_header=raw[:348],artifact_sha256=hashlib.sha256(raw).hexdigest(),source_id=path.name)
    p = prepare_generated_overlay({**inputs,'GT':altered},'GENERATED_ASYMMETRIC')
    assert p['layers']['GT']['status'] == 'UNKNOWN' and p['arrays']['GT'] is None
    assert p['layers']['GT']['reason'] == 'NATIVE_GEOMETRY_MISMATCH_OVERLAY_BLOCKED'


@pytest.mark.parametrize('kind',['real_scope','other_case','invalid_sha'])
def test_unbound_or_non_generated_source_rejected_before_render(tmp_path,kind):
    _,inputs = generate_demo(tmp_path/'generated')
    bad = dict(inputs['CT'])
    if kind == 'real_scope':bad['scope'] = 'REAL'
    if kind == 'other_case':bad['case_id'] = 'OTHER'
    if kind == 'invalid_sha':bad['artifact_sha256'] = None
    with pytest.raises(ValueError):prepare_generated_overlay({**inputs,'CT':bad},'GENERATED_ASYMMETRIC')


def test_only_bounded_display_points_and_generated_html_escape(tmp_path):
    _,inputs = generate_demo(tmp_path/'generated')
    inputs['CT']['source_id'] = '</script><img src="https://invalid.example/">'
    p = prepare_generated_overlay(inputs,'GENERATED_ASYMMETRIC');html = render_generated_overlay(p)
    assert '</script><img' not in html and '\\u003c/script' in html
    assert all(word in html for word in ['raw','native','canonical','display','UNKNOWN','PASS'])
    with pytest.raises(ValueError):display_point(p,-1,0,0)
    with pytest.raises(ValueError):render_generated_overlay({**p,'scope':'REAL'})


def test_demo_is_exclusive_and_never_overwrites_generated_or_history(tmp_path):
    output = tmp_path/'generated';generate_demo(output)
    before = (output/'overlay.html').read_bytes()
    with pytest.raises(FileExistsError):generate_demo(output)
    assert (output/'overlay.html').read_bytes() == before
