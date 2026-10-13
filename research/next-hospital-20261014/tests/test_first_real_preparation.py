import io
from pathlib import Path

import numpy as np
import pydicom
import pytest

from epi_next.first_real_preparation import (prepare_slice, file_sha, read_frozen_config,
                                            read_locked_json, load_prepared_contract)
from epi_next.artifacts import canonical_json, sha256
from epi_next.geometry import transform_points
from test_volume_io import generated_approval


def test_original_dicom_pipeline_and_frozen_tensor_exact_equivalence(tmp_path):
    a=generated_approval(tmp_path)
    entry=a['cases'][0]['files'][0]  # z=2 from generated unsorted inventory
    ds=pydicom.dcmread(entry['path'])
    ds.ImageOrientationPatient=[0,1,0,1,0,0]
    ds.ImagePositionPatient=[10,20,26]
    ds.PixelData=np.fromfunction(lambda y,x:100+10*y+x,(4,5),dtype=int).astype(np.int16).tobytes()
    ds.save_as(entry['path'],enforce_file_format=True)
    selected={'sop_uid':str(ds.SOPInstanceUID),'study_uid':str(ds.StudyInstanceUID),
              'series_uid':str(ds.SeriesInstanceUID),'native_slice_index_zero_based':2}
    native=np.array([[0,1.5,0,10],[0,0,1,20],[-2,0,0,30],[0,0,0,1.]])
    hu=np.fromfunction(lambda y,x:-800+20*y+2*x,(4,5),dtype=float).astype(np.float32)
    image,support,tensor,geometry=prepare_slice(entry['path'],file_sha(entry['path']),selected,
                                               native,np.linalg.inv(native),hu,read_frozen_config())
    assert image.shape==(224,224) and tensor.shape==(3,224,224) and image.dtype==np.float32
    assert geometry['native_hu_exact_match'] and geometry['complete_frozen_tensor_exact_match']
    assert geometry['world_header_max_error_mm']<1e-10
    assert geometry['pixel_padding_status']=='TAG_PRESENT_NOT_MASKED_BY_FROZEN_PIPELINE'
    assert support.all() and 'NOT_PADDING_OR_LUNG_MASK' in geometry['valid_support_semantics']
    mapping=np.asarray(geometry['model_to_native_zyx'])
    # Model edge (0,0) -> native edge (0,0); model centre follows half-pixel convention.
    np.testing.assert_allclose(transform_points([0,-.5,-.5],mapping),[2,-.5,-.5],atol=1e-14)
    np.testing.assert_allclose(transform_points([0,223.5,223.5],mapping),[2,3.5,4.5],atol=1e-14)
    np.testing.assert_allclose(transform_points([0,50,100],np.asarray(geometry['model_to_lps'])),
        [10+1.5*((50+.5)*4/224-.5),20+((100+.5)*5/224-.5),26],atol=1e-12)


def test_hash_and_header_mismatch_stop_before_decode(tmp_path,monkeypatch):
    a=generated_approval(tmp_path);entry=a['cases'][0]['files'][0]
    selected={'sop_uid':entry['sop_uid'],'study_uid':'1.2.3','series_uid':'1.2.3.4','native_slice_index_zero_based':2}
    monkeypatch.setattr(pydicom.dataset.Dataset,'pixel_array',property(lambda _:pytest.fail('decoded unexpected CT')))
    with pytest.raises(ValueError,match='SOURCE_CT_HASH_MISMATCH'):
        prepare_slice(entry['path'],'0'*64,selected,np.eye(4),np.eye(4),np.zeros((4,5)),read_frozen_config())
    selected['study_uid']='UNKNOWN-STUDY'
    with pytest.raises(ValueError,match='IDENTITY_MISMATCH'):
        prepare_slice(entry['path'],entry['sha256'],selected,np.eye(4),np.eye(4),np.zeros((4,5)),read_frozen_config())


def test_native_hu_and_affine_cannot_be_self_declared(tmp_path):
    a=generated_approval(tmp_path);entry=a['cases'][0]['files'][0]
    selected={'sop_uid':entry['sop_uid'],'study_uid':'1.2.3','series_uid':'1.2.3.4','native_slice_index_zero_based':2}
    with pytest.raises(ValueError,match='HU_DIFFERS'):
        prepare_slice(entry['path'],entry['sha256'],selected,np.eye(4),np.eye(4),np.zeros((4,5)),read_frozen_config())
    ds=pydicom.dcmread(entry['path']);hu=ds.pixel_array.astype(np.float32)*2-1000
    with pytest.raises(ValueError,match='GEOMETRY_MISMATCH'):
        prepare_slice(entry['path'],entry['sha256'],selected,np.eye(4),np.eye(4),hu,read_frozen_config())


def test_locked_json_bytes_preserved(tmp_path):
    p=tmp_path/'locked.json';raw=canonical_json({'schema':'SYNTHETIC'});p.write_bytes(raw)
    assert read_locked_json(p,sha256(raw))['schema']=='SYNTHETIC'
    p.write_bytes(raw+b'\n')
    with pytest.raises(ValueError,match='HASH_MISMATCH'):read_locked_json(p,sha256(raw))
