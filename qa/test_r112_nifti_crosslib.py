"""One generated lossless-encoding regression; chief serial window required.

The original R108 integer auto-scaling failure is retained unchanged. This
test fixes the storage contract, not a medical tolerance or preprocessing rule.
"""
import nibabel as nib
import numpy as np

from epilocate_next.infection_overlay_research_v1 import RAS_TO_LPS
from epilocate_next.r108_research_geometry import nifti1_header_geometry
from qa.test_r108_research_geometry import header


def test_generated_explicit_float64_cross_library_roundtrip(tmp_path):
    h = header()
    stored = np.arange(60,dtype='<i2').reshape((3,4,5))
    source = tmp_path/'GENERATED_INT16_SOURCE.nii'
    source.write_bytes(bytes(h)+stored.tobytes())
    geometry = nifti1_header_geometry(h)
    image = nib.load(source)
    expected_xyz = (stored*2-1024).transpose(2,1,0).astype(np.float64)
    assert np.array_equal(image.get_fdata(dtype=np.float64),expected_xyz)
    assert np.array_equal(RAS_TO_LPS @ image.affine,geometry.grid.affine_lps_xyz)

    # Integer default re-encoding can quantize. Require explicitly lossless
    # float64 storage with identity scaling for this generated roundtrip.
    lossless = nib.Nifti1Image(image.get_fdata(dtype=np.float64),image.affine,
                             header=image.header.copy())
    lossless.set_data_dtype(np.float64)
    lossless.header.set_slope_inter(1.,0.)
    saved = tmp_path/'GENERATED_FLOAT64_LOSSLESS.nii'
    nib.save(lossless,saved)
    reread = nib.load(saved)
    raw_header = saved.read_bytes()[:348]
    reparsed = nifti1_header_geometry(raw_header)

    assert reread.get_data_dtype() == np.dtype('float64')
    assert np.array_equal(reread.get_fdata(dtype=np.float64),expected_xyz)
    assert np.array_equal(reread.affine,image.affine)
    assert reparsed.grid.shape_zyx == geometry.grid.shape_zyx
    assert np.array_equal(reparsed.grid.affine_lps_xyz,geometry.grid.affine_lps_xyz)
    assert (reparsed.qform_code,reparsed.sform_code) == (geometry.qform_code,geometry.sform_code)
    assert (reparsed.scaling_slope,reparsed.scaling_intercept) == (1.,0.)
