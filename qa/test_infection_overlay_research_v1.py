"""NEW synthetic tests only. Prepared; execution requires chief serial window."""
from dataclasses import replace
import struct

import numpy as np
import pytest

from epilocate_next.infection_overlay_research_v1 import (
    Grid, OverlayBinding, RAS_TO_LPS, native_zyx_grid, nifti_sform_metadata,
    crop_grid, cam7_centers_native, resample_nearest_mask, evaluate_synthetic_overlap,
)


def grid():
    # Asymmetric orientation and descending Z; a flipped cube cannot hide a bug.
    return Grid((5,6,7),np.array([[0,-2,0,50],[3,0,0,-30],[0,0,-4,100],[0,0,0,1]],dtype=float))


def bindings(g,extent='FULL'):
    p=OverlayBinding('GENERATED-GROUP','GENERATED-SERIES',g.digest(),1,'INFECTION_SEGMENTATION_MASK',extent,'NONE')
    return p,replace(p,evidence_type='EXPERT_INFECTION_MASK')


def nifti_fixture(g):
    h=bytearray(352);struct.pack_into('<i',h,0,348)
    struct.pack_into('<8h',h,40,3,*g.shape_zyx[::-1],1,1,1,1)
    struct.pack_into('<2h',h,70,2,8);struct.pack_into('<f',h,108,352.)
    h[123]=2;struct.pack_into('<2h',h,252,0,1)
    ras=RAS_TO_LPS @ g.affine_lps_xyz
    struct.pack_into('<8f',h,76,1.,*np.linalg.norm(ras[:3,:3],axis=0),1.,1.,1.,1.)
    struct.pack_into('<12f',h,280,*ras[:3].ravel());h[344:348]=b'n+1\0'
    return bytes(h)+np.zeros(g.shape_zyx,dtype=np.uint8).tobytes()


def test_actual_synthetic_nii_header_affine_and_world_roundtrip(tmp_path):
    g=grid();path=tmp_path/'GENERATED_ONLY.nii';path.write_bytes(nifti_fixture(g))
    header=path.read_bytes()[:348];parsed=nifti_sform_metadata(header)
    assert parsed.shape_zyx==g.shape_zyx
    assert np.array_equal(parsed.affine_lps_xyz,g.affine_lps_xyz)
    p=np.array([[0,0,0],[4,5,6],[1.25,2.5,3.75]])
    assert np.allclose(parsed.from_lps(g.to_lps(p)),p,atol=1e-12,rtol=0)


def test_ras_lps_left_right_and_native_zyx_columns():
    ras=np.diag([2.,3.,4.,1.]);g=Grid((4,5,6),RAS_TO_LPS @ ras)
    assert np.array_equal(g.to_lps([[0,0,1]])[0],[-2,0,0])
    native=np.array([[0,0,-2,0],[0,-3,0,0],[4,0,0,0],[0,0,0,1.]])
    assert np.array_equal(native_zyx_grid((4,5,6),native).affine_lps_xyz,g.affine_lps_xyz)
    assert g.to_lps([[1,0,0]])[0,2]==4


@pytest.mark.parametrize('kind',['qform','units','magic','singular'])
def test_unsupported_or_ambiguous_nifti_metadata_rejected(kind):
    h=bytearray(nifti_fixture(grid())[:348])
    if kind=='qform':struct.pack_into('<h',h,252,1)
    if kind=='units':h[123]=0
    if kind=='magic':h[344:348]=b'ni1\0'
    if kind=='singular':struct.pack_into('<4f',h,280,0,0,0,0)
    with pytest.raises(ValueError):nifti_sform_metadata(h)


def test_crop_resize_and_7x7_half_pixel_chain():
    g=grid();cropped=crop_grid(g,(1,2,3),(3,3,3))
    assert np.allclose(cropped.to_lps([[0,0,0]]),g.to_lps([[1,2,3]]))
    p=cam7_centers_native(2,(512,512));assert p.shape==(7,7,3)
    assert np.allclose(p[3,3],[2,255.5,255.5])
    q=cam7_centers_native(2,(512,512),(20,40),(224,224))
    assert np.allclose(q[3,3],[2,131.5,151.5])
    # Center convention is explicit; 7x7 does not become pixel-level truth.
    assert np.isclose(p[0,0,1],512/14-.5)


def test_nearest_reorientation_roundtrip_preserves_asymmetric_binary_mask():
    g=grid();m=np.zeros(g.shape_zyx,dtype=np.uint8);m[1,2,5]=1;m[3,4,1]=1
    flip=np.eye(4);flip[0,0]=-1;flip[0,3]=6
    target=Grid(g.shape_zyx,g.affine_lps_xyz @ flip)
    transformed,valid=resample_nearest_mask(m,g,target)
    back,valid_back=resample_nearest_mask(transformed,target,g)
    assert valid.all() and valid_back.all() and np.array_equal(back,m)
    assert transformed[1,2,1]==1 and np.unique(transformed).tolist()==[0,1]


def test_lossy_downsample_not_claimed_invertible_and_fov_not_background():
    g=Grid((3,3,3),np.eye(4));m=np.zeros(g.shape_zyx,dtype=np.uint8);m[1,1,1]=1
    coarse=Grid((2,2,2),np.diag([2.,2.,2.,1.]));r,_=resample_nearest_mask(m,g,coarse)
    back,coverage=resample_nearest_mask(r,coarse,g)
    assert not np.array_equal(back,m)  # Small lesions can vanish.
    outside=Grid((3,3,3),np.array([[1,0,0,20],[0,1,0,0],[0,0,1,0],[0,0,0,1.]]))
    _,coverage=resample_nearest_mask(m,g,outside);assert not coverage.any()
    p,ref=bindings(g);result=evaluate_synthetic_overlap(m,m,g,p,ref,coverage)
    assert result['dice'] is None and result['global_negative_truth']=='UNKNOWN'


@pytest.mark.parametrize('extent',['PARTIAL','UNKNOWN','CONFLICT'])
def test_incomplete_reference_never_global_dice(extent):
    g=grid();m=np.zeros(g.shape_zyx,dtype=np.uint8);p,r=bindings(g,extent)
    result=evaluate_synthetic_overlap(m,m,g,p,r,np.ones(g.shape_zyx,dtype=bool))
    assert result['status']=='BLOCKED_INCOMPLETE_REFERENCE_OR_FOV' and result['dice'] is None


def test_complete_reference_positive_and_empty_cases():
    g=grid();p,r=bindings(g);m=np.zeros(g.shape_zyx,dtype=np.uint8);m[1,2,3]=1;c=np.ones(g.shape_zyx,dtype=bool)
    result=evaluate_synthetic_overlap(m,m,g,p,r,c);assert result['dice']==result['iou']==1
    m[:]=0;result=evaluate_synthetic_overlap(m,m,g,p,r,c);assert result['dice'] is None and result['empty_empty']


@pytest.mark.parametrize('kind',['cross_group','cross_series','grid','anatomy','normal','gt_prompt'])
def test_semantic_and_reference_gates(kind):
    g=grid();p,r=bindings(g);m=np.zeros(g.shape_zyx,dtype=np.uint8);c=np.ones(g.shape_zyx,dtype=bool)
    if kind=='cross_group':r=replace(r,source_group='GENERATED-OTHER')
    if kind=='cross_series':r=replace(r,volume_or_series='GENERATED-OTHER')
    if kind=='grid':r=replace(r,native_grid_sha256='0'*64)
    if kind=='anatomy':r=replace(r,evidence_type='LUNG_ANATOMY_MASK')
    if kind=='normal':p=replace(p,target_class=0)
    if kind=='gt_prompt':
        p=replace(p,prompt_origin='TEST_REFERENCE')
        assert evaluate_synthetic_overlap(m,m,g,p,r,c)['status']=='BLOCKED_GT_ASSISTED_INTERACTIVE_NOT_AUTOMATIC';return
    with pytest.raises(ValueError):evaluate_synthetic_overlap(m,m,g,p,r,c)
