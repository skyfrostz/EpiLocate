"""New generated-only cases. Chief runs serially after exact-source admission."""
import importlib.util
import struct

import numpy as np
import pytest

from epilocate_next.infection_overlay_research_v1 import Grid, RAS_TO_LPS, crop_grid, resample_nearest_mask
from epilocate_next.r108_research_geometry import (
    EVIDENCE, nifti1_header_geometry, resize_grid, permute_flip_grid,
    geometry_coverage_report, research_layer_bundle, infnet_real_preflight,
    adapt_generated_infnet_logits,
)


def header(endian='<', qcode=1, scode=1):
    h = bytearray(352)
    struct.pack_into(endian+'i',h,0,348)
    struct.pack_into(endian+'8h',h,40,3,5,4,3,1,1,1,1)
    struct.pack_into(endian+'2h',h,70,4,16)
    struct.pack_into(endian+'8f',h,76,-1,2,3,4,1,1,1,1)
    struct.pack_into(endian+'3f',h,108,352,2,-1024)
    h[123] = 2
    struct.pack_into(endian+'2h',h,252,qcode,scode)
    struct.pack_into(endian+'3f',h,268,10,-20,30)
    struct.pack_into(endian+'12f',h,280,2,0,0,10,0,3,0,-20,0,0,-4,30)
    h[344:348] = b'n+1\0'
    return h


@pytest.mark.parametrize('endian',['<','>'])
def test_qform_sform_world_left_right_descending_z_and_inverse(endian):
    g = nifti1_header_geometry(header(endian)).grid
    assert g.shape_zyx == (3,4,5)
    assert np.array_equal(g.to_lps([[0,0,0],[1,1,1]]),[[-10,20,30],[-12,17,26]])
    points = np.array([[.2,1.5,3.1],[2,3,4]])
    assert np.allclose(g.from_lps(g.to_lps(points)),points,atol=1e-12,rtol=0)


def test_rotated_qform_matches_independently_written_sform():
    h = header()
    struct.pack_into('<3f',h,256,0,0,np.sqrt(.5))
    struct.pack_into('<12f',h,280,0,-3,0,10,2,0,0,-20,0,0,-4,30)
    g = nifti1_header_geometry(h).grid
    assert np.allclose(g.to_lps([[0,0,1]]),[[-10,18,30]],atol=1e-5,rtol=0)


def test_large_volume_header_is_metadata_only_no_voxel_allocation():
    h = header()
    struct.pack_into('<3h',h,42,512,512,300)
    parsed = nifti1_header_geometry(h)
    assert parsed.grid.shape_zyx == (300,512,512)
    assert np.array_equal(parsed.grid.to_lps([[299,511,511]]),[[-1032,-1513,-1166]])


@pytest.mark.parametrize('kind',['translation','frame','slice_basis'])
def test_conflicting_forms_fail_even_single_slice(kind):
    h = header()
    if kind == 'translation': struct.pack_into('<f',h,292,11)
    if kind == 'frame': struct.pack_into('<h',h,254,2)
    if kind == 'slice_basis':
        struct.pack_into('<h',h,46,1)
        struct.pack_into('<f',h,320,-5)
    with pytest.raises(ValueError,match='QFORM_SFORM_COORDINATE_CONFLICT'):
        nifti1_header_geometry(h)


@pytest.mark.parametrize('kind',['no_form','unknown_units','quaternion','spacing','datatype','magic','nan_scaling'])
def test_header_rejects_unsupported_or_unverifiable_metadata(kind):
    h = header()
    if kind == 'no_form': struct.pack_into('<2h',h,252,0,0)
    if kind == 'unknown_units': h[123] = 0
    if kind == 'quaternion': struct.pack_into('<f',h,256,2)
    if kind == 'spacing': struct.pack_into('<f',h,80,0)
    if kind == 'datatype': struct.pack_into('<h',h,72,8)
    if kind == 'magic': h[344:348] = b'ni1\0'
    if kind == 'nan_scaling': struct.pack_into('<f',h,112,float('nan'))
    with pytest.raises(ValueError): nifti1_header_geometry(h)


@pytest.mark.parametrize('qcode,scode,selected',[(1,0,'qform'),(0,1,'sform')])
def test_single_coded_form_and_scaling_do_not_infer_hu(qcode,scode,selected):
    h = header(qcode=qcode,scode=scode)
    parsed = nifti1_header_geometry(h)
    assert parsed.selected_form == selected
    assert parsed.scaling_slope == 2 and parsed.scaling_intercept == -1024
    assert parsed.intensity_evidence('WINDOWED_0_255','a'*64,True)['status'] == 'BLOCKED_HU_UNVERIFIED'
    assert parsed.intensity_evidence('RAW_HU','a'*64,True)['status'] == 'HU_SOURCE_BOUND'
    assert parsed.intensity_evidence('RAW_HU',None,True)['status'] == 'BLOCKED_HU_UNVERIFIED'
    struct.pack_into('<2f',h,112,0,float('nan'))
    disabled = nifti1_header_geometry(h)
    assert (disabled.scaling_slope,disabled.scaling_intercept) == (1,0)


def test_permutation_flip_and_nearest_mask_return_to_native_without_loss():
    g = nifti1_header_geometry(header()).grid
    mask = np.zeros(g.shape_zyx,dtype=np.uint8);mask[1,2,4] = 1;mask[2,0,1] = 1
    target = permute_flip_grid(g,(2,0,1),(True,False,True))
    expected = np.flip(np.transpose(mask,(2,0,1)),axis=(0,2))
    changed,cov = resample_nearest_mask(mask,g,target)
    back,back_cov = resample_nearest_mask(changed,target,g)
    assert cov.all() and back_cov.all()
    assert np.array_equal(changed,expected) and np.array_equal(back,mask)


def test_crop_resize_half_pixel_inverse_and_coverage_never_negative_truth():
    native = Grid((3,8,10),np.diag([2.,3.,4.,1.]))
    cropped = crop_grid(native,(1,2,3),(1,4,5))
    resized = resize_grid(cropped,(1,8,10))
    assert np.allclose(native.from_lps(resized.to_lps([[0,0,0]])),[[1,1.75,2.75]])
    pts = np.array([[0,0,0],[0,7,9],[0,2.5,4.25]])
    assert np.allclose(resized.from_lps(native.to_lps(native.from_lps(resized.to_lps(pts)))) ,pts)
    restored,coverage = resample_nearest_mask(np.ones(cropped.shape_zyx,dtype=np.uint8),cropped,native)
    assert coverage.sum() == 20 and restored.sum() == 20
    report = geometry_coverage_report(native,native,'FULL',coverage)
    assert report['status'] == 'PARTIAL_REFERENCE_OR_FOV' and report['outside_coverage_truth'] == 'UNKNOWN'


@pytest.mark.parametrize('extent,status',[('FULL','MATCH_FULL_COVERAGE'),('PARTIAL','PARTIAL_REFERENCE_OR_FOV'),('UNKNOWN','BLOCKED_REFERENCE_UNKNOWN'),('CONFLICT','BLOCKED_REFERENCE_UNKNOWN')])
def test_geometry_reference_extent_returns_gates_without_metrics(extent,status):
    g = Grid((1,2,3),np.eye(4));coverage = np.ones(g.shape_zyx,dtype=bool)
    result = geometry_coverage_report(g,g,extent,coverage)
    assert result['status'] == status and result['identity_verified'] is False and 'dice' not in result
    shifted = Grid(g.shape_zyx,np.array([[1,0,0,1],[0,1,0,0],[0,0,1,0],[0,0,0,1.]]))
    assert geometry_coverage_report(g,shifted,extent,coverage)['status'] == 'BLOCKED_GEOMETRY_MISMATCH'


def test_bundle_preserves_each_method_target_and_evidence_without_mvp_entry():
    g = Grid((1,2,3),np.eye(4))
    layers = [dict(kind=k,method=k+'-method',version='generated-v1',target='FIXED_INFECTION_MARGIN' if k=='CAM' else 'EXPLICIT_SOURCE_TARGET',evidence_type=v,value_semantics=v,grid_sha256=g.digest(),artifact_sha256='a'*64,evidence_status='GENERATED_ONLY') for k,v in EVIDENCE.items()]
    bundle = research_layer_bundle('generated-case','generated-study','generated-series',g,layers)
    assert len(bundle['layers']) == 8 and bundle['mvp_auto_import'] is False
    for kind in ('probability','cross_case','clinical','mixed_evidence'):
        changed = dict(layers[2])
        if kind=='probability': changed['value_semantics'] = 'LESION_PROBABILITY'
        if kind=='cross_case': changed['case_id'] = 'other-case'
        if kind=='clinical': changed['clinical_validated'] = True
        if kind=='mixed_evidence': changed['evidence_type'] = EVIDENCE['GT']
        with pytest.raises(ValueError):research_layer_bundle('generated-case','generated-study','generated-series',g,[changed])


def request(g):
    return dict(mode='GENERATED_ONLY',generated_input=True,case_id='generated-case',study_id='generated-study',series_id='generated-series',model_version='InfNet-GENERATED-v1',preprocess_version='generated-352-v1',runtime_identity='generated-numpy-no-model',input_sha256='a'*64,model_sha256='b'*64,preprocess_sha256='c'*64,native_grid_sha256=g.digest())


def test_infnet_native_inverse_crop_coverage_preserves_logits_and_not_minmax():
    g = Grid((1,8,10),np.eye(4));x = np.full((352,352),2.,dtype=np.float32)
    out = adapt_generated_infnet_logits(request(g),g,(0,2,3),(1,4,5),x)
    assert out['model_calls'] == out['weight_reads'] == 0
    assert out['coverage'].sum() == out['infection_mask_candidate'].sum() == 20
    assert np.all(out['native_logits'][out['coverage']] == 2)
    assert np.isnan(out['native_logits'][~out['coverage']]).all()
    assert np.array_equal(out['original_generated_logits'],x)
    assert out['hospital_eligible'] is False and out['runtime_seconds'] is None
    negative = adapt_generated_infnet_logits(request(g),g,(0,0,0),g.shape_zyx,-x)
    assert negative['coverage'].all() and not negative['infection_mask_candidate'].any()


def test_infnet_half_pixel_bilinear_matches_known_generated_plane():
    g = Grid((1,176,176),np.eye(4))
    # At native (y,x), generated logits sample (2y+.5,2x+.5).
    yy,xx = np.indices((352,352),dtype=np.float32)
    out = adapt_generated_infnet_logits(request(g),g,(0,0,0),g.shape_zyx,yy+2*xx)
    assert np.isclose(out['native_logits'][0,10,20],20.5+2*40.5)


def test_infnet_real_branch_and_missing_provenance_are_closed_without_runner():
    p = infnet_real_preflight({})
    assert p['status'] == 'BLOCKED' and 'weight_license_confirmed' in p['reasons']
    assert 'training_overlap_resolved' in p['reasons'] and 'preprocess_352_confirmed' in p['reasons']
    g = Grid((1,2,3),np.eye(4));r = request(g);r['mode'] = 'REAL'
    with pytest.raises(ValueError,match='GENERATED_ONLY'):adapt_generated_infnet_logits(r,g,(0,0,0),g.shape_zyx,np.zeros((352,352),dtype=np.float32))
    r = request(g);r['model_sha256'] = None
    with pytest.raises(ValueError,match='BOUND_INPUT_MODEL'):adapt_generated_infnet_logits(r,g,(0,0,0),g.shape_zyx,np.zeros((352,352),dtype=np.float32))


@pytest.mark.skipif(importlib.util.find_spec('nibabel') is None,reason='NIBABEL_NOT_INSTALLED_CROSS_LIBRARY_NOT_RUN')
def test_generated_nifti_cross_library_save_load_world_and_scaling(tmp_path):
    import nibabel as nib
    h = header();data = np.arange(60,dtype='<i2').reshape((3,4,5))
    path = tmp_path/'GENERATED_R108.nii';path.write_bytes(bytes(h)+data.tobytes())
    parsed = nifti1_header_geometry(h);image = nib.load(path)
    assert np.allclose(RAS_TO_LPS @ image.affine,parsed.grid.affine_lps_xyz)
    assert np.array_equal(image.get_fdata().transpose(2,1,0),data*2-1024)
    saved = tmp_path/'GENERATED_R108_ROUNDTRIP.nii';nib.save(image,saved)
    reread = nib.load(saved)
    assert np.allclose(reread.affine,image.affine) and np.array_equal(reread.get_fdata(),image.get_fdata())
    reparsed = nifti1_header_geometry(saved.read_bytes()[:348])
    assert np.allclose(reparsed.grid.affine_lps_xyz,parsed.grid.affine_lps_xyz)
