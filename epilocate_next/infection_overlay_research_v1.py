"""Independent synthetic-only geometry and reference gates; no reader or renderer.

XYZ affine columns, ZYX NumPy arrays, mm LPS world coordinates. NIfTI header
support is intentionally limited to little-endian NIfTI-1 sform-only/mm metadata.
No nibabel is installed here: real-file interoperability remains NOT RUN.
"""
from dataclasses import dataclass
import hashlib
import json
import struct

import numpy as np

SCHEMA = 'EPI_NEXT_INFECTION_OVERLAY_RESEARCH_V1'
MAX_VOXELS = 1_048_576
RAS_TO_LPS = np.diag([-1., -1., 1., 1.])
ZYX_TO_XYZ = np.eye(4)[[2, 1, 0, 3]]


@dataclass(frozen=True)
class Grid:
    shape_zyx: tuple[int, int, int]
    affine_lps_xyz: np.ndarray

    def __post_init__(self):
        shape=self.shape_zyx
        a=np.array(self.affine_lps_xyz,dtype=np.float64,copy=True)
        if (len(shape)!=3 or any(type(v) is not int or v<=0 for v in shape)
                or np.prod(shape)>MAX_VOXELS or a.shape!=(4,4) or not np.isfinite(a).all()
                or not np.array_equal(a[3],[0,0,0,1]) or abs(np.linalg.det(a[:3,:3]))<1e-10):
            raise ValueError('VALID_BOUNDED_MM_AFFINE_GRID_REQUIRED')
        a.flags.writeable=False;object.__setattr__(self,'affine_lps_xyz',a)

    def to_lps(self,points_zyx):
        p=np.asarray(points_zyx,dtype=np.float64)
        if p.shape[-1]!=3 or not np.isfinite(p).all():raise ValueError('FINITE_ZYX_POINTS_REQUIRED')
        return p[...,::-1] @ self.affine_lps_xyz[:3,:3].T + self.affine_lps_xyz[:3,3]

    def from_lps(self,points_lps):
        p=np.asarray(points_lps,dtype=np.float64)
        if p.shape[-1]!=3 or not np.isfinite(p).all():raise ValueError('FINITE_LPS_POINTS_REQUIRED')
        return ((p-self.affine_lps_xyz[:3,3]) @ np.linalg.inv(self.affine_lps_xyz[:3,:3]).T)[...,::-1]

    def digest(self):
        raw=json.dumps(dict(shape_zyx=self.shape_zyx,affine_lps_xyz=self.affine_lps_xyz.tolist()),sort_keys=True,separators=(',',':')).encode()
        return hashlib.sha256(raw).hexdigest()


def native_zyx_grid(shape_zyx,native_to_lps_zyx):
    """Convert the original R18 ZYX ledger columns, never reorder its slices."""
    return Grid(tuple(shape_zyx),np.asarray(native_to_lps_zyx) @ ZYX_TO_XYZ)


def nifti_sform_metadata(header):
    """Bytes supplied by a caller; no file open, gzip or pixel decoding."""
    if (len(header)<348 or struct.unpack_from('<i',header,0)[0]!=348 or header[344:348]!=b'n+1\0'
            or struct.unpack_from('<h',header,40)[0]!=3):
        raise ValueError('SYNTHETIC_NIFTI1_3D_PROFILE_REQUIRED')
    q,s=struct.unpack_from('<2h',header,252)
    if q!=0 or s<=0:raise ValueError('EXPLICIT_SFORM_ONLY_QFORM_PROFILE_UNSUPPORTED')
    if header[123]&7!=2:raise ValueError('EXPLICIT_MM_UNITS_REQUIRED')
    xyz=struct.unpack_from('<3h',header,42)
    ras=np.eye(4);ras[:3]=np.array(struct.unpack_from('<12f',header,280)).reshape(3,4)
    return Grid(tuple(reversed(xyz)),RAS_TO_LPS @ ras)


def crop_grid(grid,origin_zyx,shape_zyx):
    if len(origin_zyx)!=3 or any(type(v) is not int or v<0 for v in origin_zyx):raise ValueError('INTEGER_CROP_ORIGIN_REQUIRED')
    if any(o+n>old for o,n,old in zip(origin_zyx,shape_zyx,grid.shape_zyx)):raise ValueError('CROP_OUTSIDE_NATIVE')
    shift=np.eye(4);shift[:3,3]=origin_zyx[::-1]
    return Grid(tuple(shape_zyx),grid.affine_lps_xyz @ shift)


def cam7_centers_native(native_z,native_yx,crop_origin_yx=(0,0),crop_shape_yx=None):
    """Nominal align_corners=False centers: 7->224->native; no map data."""
    size=np.asarray(crop_shape_yx if crop_shape_yx is not None else native_yx,dtype=float)
    origin=np.asarray(crop_origin_yx,dtype=float)
    if (size.shape!=(2,) or origin.shape!=(2,) or min(size)<=0 or min(origin)<0
            or np.any(size+origin>np.asarray(native_yx)) or type(native_z) is not int or native_z<0):
        raise ValueError('EXPLICIT_NATIVE_AND_CROP_GEOMETRY_REQUIRED')
    model_centers=(np.arange(7)+.5)*224/7-.5
    y=origin[0]+(model_centers+.5)*size[0]/224-.5
    x=origin[1]+(model_centers+.5)*size[1]/224-.5
    yy,xx=np.meshgrid(y,x,indexing='ij')
    return np.stack([np.full_like(yy,native_z),yy,xx],axis=-1)


def resample_nearest_mask(mask,source,target):
    """Returns data AND coverage. Zero fill never implies known negative truth."""
    m=np.asarray(mask)
    if m.shape!=source.shape_zyx or not np.isin(m,[0,1]).all():raise ValueError('BINARY_MASK_GRID_REQUIRED')
    points=np.moveaxis(np.indices(target.shape_zyx,dtype=np.float64),0,-1)
    source_points=source.from_lps(target.to_lps(points))
    indices=np.floor(source_points+.5).astype(np.int64)
    covered=np.all((indices>=0)&(indices<np.asarray(source.shape_zyx)),axis=-1)
    out=np.zeros(target.shape_zyx,dtype=np.uint8)
    ix=indices[covered];out[covered]=m[tuple(ix.T)]
    return out,covered


@dataclass(frozen=True)
class OverlayBinding:
    source_group: str
    volume_or_series: str
    native_grid_sha256: str
    target_class: int
    evidence_type: str
    reference_extent: str
    prompt_origin: str


def evaluate_synthetic_overlap(prediction,reference,grid,binding,reference_binding,coverage):
    """Complete-reference Dice/IoU only. This function cannot open a real file."""
    if (binding.source_group,binding.volume_or_series,binding.native_grid_sha256)!=(reference_binding.source_group,reference_binding.volume_or_series,reference_binding.native_grid_sha256):
        raise ValueError('CROSS_CASE_SERIES_OR_GRID_REFERENCE_REJECTED')
    if binding.native_grid_sha256!=grid.digest():raise ValueError('UNVERIFIED_NATIVE_GRID')
    if binding.evidence_type!='INFECTION_SEGMENTATION_MASK' or reference_binding.evidence_type!='EXPERT_INFECTION_MASK':
        raise ValueError('ANATOMY_OR_CAM_IS_NOT_INFECTION_MASK_TRUTH')
    if binding.target_class!=1:raise ValueError('NORMAL_TARGET_IS_NOT_INFECTION_LOCALIZATION')
    if binding.prompt_origin=='TEST_REFERENCE':
        return dict(status='BLOCKED_GT_ASSISTED_INTERACTIVE_NOT_AUTOMATIC',dice=None,iou=None)
    if binding.prompt_origin not in ('MODEL_CAM_PRELOCKED','NONE'):
        raise ValueError('EXPLICIT_PROMPT_PROVENANCE_REQUIRED')
    if reference_binding.reference_extent not in ('FULL','PARTIAL','UNKNOWN','CONFLICT'):
        raise ValueError('REFERENCE_EXTENT_REQUIRED')
    p,g,c=np.asarray(prediction),np.asarray(reference),np.asarray(coverage)
    if (p.shape!=grid.shape_zyx or g.shape!=grid.shape_zyx or c.shape!=grid.shape_zyx
            or c.dtype!=np.bool_ or not np.isin(p,[0,1]).all() or not np.isin(g,[0,1]).all()):
        raise ValueError('BINARY_REFERENCE_AND_EXPLICIT_COVERAGE_REQUIRED')
    if reference_binding.reference_extent!='FULL' or not c.all():
        return dict(status='BLOCKED_INCOMPLETE_REFERENCE_OR_FOV',dice=None,iou=None,
                    global_negative_truth='UNKNOWN',covered_voxels=int(c.sum()))
    pp,gg=p.astype(bool),g.astype(bool);inter=int((pp&gg).sum());union=int((pp|gg).sum());denom=int(pp.sum()+gg.sum())
    return dict(status='GENERATED_ENGINEERING_ONLY',dice=2*inter/denom if denom else None,
                iou=inter/union if union else None,empty_empty=denom==0,
                false_positive_voxels=int((pp&~gg).sum()),clinical_validity='NOT_ESTABLISHED')
