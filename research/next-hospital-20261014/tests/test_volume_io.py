import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, CTImageStorage

from epi_next.geometry import inverse_points, transform_points
from epi_next.volume_io import (load_approved_inventory, read_ct_volume,
                                resample_regular_hu, validate_approval)


def generated_approval(tmp_path):
    files = []
    for z in (2, 0, 1):
        path = tmp_path / f'synthetic-{z}.dcm'
        uid = f'1.2.826.0.1.3680043.10.543.1234.{z+1}'
        meta = FileMetaDataset()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        meta.MediaStorageSOPClassUID = CTImageStorage
        meta.MediaStorageSOPInstanceUID = uid
        ds = FileDataset(str(path), {}, file_meta=meta, preamble=b'\0' * 128)
        ds.SOPClassUID, ds.SOPInstanceUID = CTImageStorage, uid
        ds.PatientID, ds.StudyInstanceUID, ds.SeriesInstanceUID = 'GENERATED', '1.2.3', '1.2.3.4'
        ds.Modality, ds.PhotometricInterpretation, ds.SamplesPerPixel = 'CT', 'MONOCHROME2', 1
        ds.Rows, ds.Columns = 4, 5
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 1
        ds.ImagePositionPatient = [10, 20, 30 + 2 * z]
        ds.ImageOrientationPatient, ds.PixelSpacing = [1,0,0,0,1,0], [1.5, 1.]
        ds.RescaleSlope, ds.RescaleIntercept, ds.RescaleType = 2, -1000, 'HU'
        ds.PixelPaddingValue = -2000
        pixels = np.full((4,5), 100 + z, dtype=np.int16)
        pixels[0,0] = -2000
        ds.PixelData = pixels.tobytes()
        ds.save_as(path, enforce_file_format=True)
        files.append({'path':str(path), 'sop_uid':uid, 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return {'schema':'EPI-NEXT-CT-ACCESS-1', 'status':'APPROVED',
            'approval_reference':'TEST_ONLY_GENERATED_DICOM', 'scope':'local_ct_pixels_and_headers',
            'split_manifest_sha256':'a'*64, 'label_definition_sha256':'b'*64,
            'cases':[{'patient_id':'SYNTHETIC', 'dicom_patient_id':'GENERATED', 'study_uid':'1.2.3',
                      'series_uid':'1.2.3.4', 'split':'train', 'label_definition_id':'SYNTHETIC_ONLY',
                      'task_labels':{'status':'SYNTHETIC_ONLY'}, 'padding_policy':'require_dicom_tag',
                      'hu_policy':'ct_linear_rescale_hu', 'files':files}]}


def membership():
    return {'SYNTHETIC': {'split':'train', 'series_uids':['1.2.3.4']}}


def test_generated_dicom_hu_sorting_and_native_roundtrip(tmp_path):
    a = generated_approval(tmp_path)
    v = read_ct_volume(a, 'SYNTHETIC', '1.2.3.4')
    np.testing.assert_allclose(v.volume_hu[:,2,3], [-800,-798,-796])
    assert v.source_sops[0].endswith('.1')
    assert not v.valid_mask[:,0,0].any()
    np.testing.assert_allclose(transform_points([2,2,3],v.affine_lps), [13,23,34])
    assert v.transform_ledger[0]['source_order'] == [1,2,0]


def test_unauthorized_stops_before_patient_io(monkeypatch):
    monkeypatch.setattr(Path, 'stat', lambda *_: pytest.fail('clinical path accessed'))
    with pytest.raises(PermissionError):
        read_ct_volume({'status':'PENDING'}, 'unknown', 'unknown')


@pytest.mark.parametrize('change', ['sealed', 'missing_policy', 'duplicate_sop', 'missing_identity'])
def test_invalid_approval(tmp_path,change):
    a = generated_approval(tmp_path)
    c = a['cases'][0]
    if change == 'sealed': c['split'] = 'test'
    elif change == 'missing_policy': del c['padding_policy']
    elif change == 'duplicate_sop': c['files'][1]['sop_uid'] = c['files'][0]['sop_uid']
    else: c['study_uid'] = ''
    with pytest.raises((ValueError,PermissionError)):
        validate_approval(a)


def test_membership_and_hash_changes_rejected(tmp_path):
    a = generated_approval(tmp_path)
    with pytest.raises(PermissionError):
        read_ct_volume(a,'other','1.2.3.4')
    a['cases'][0]['files'][0]['sha256'] = '0'*64
    with pytest.raises(ValueError,match='hash mismatch'):
        read_ct_volume(a,'SYNTHETIC','1.2.3.4')


def test_inventory_external_hash_lock(tmp_path):
    a = generated_approval(tmp_path)
    p = tmp_path / 'approved.json'
    p.write_text(json.dumps(a))
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    assert load_approved_inventory(p,approved_sha256=digest) == a
    p.write_text(json.dumps(a) + '\n')
    with pytest.raises(ValueError,match='approved bytes'):
        load_approved_inventory(p,approved_sha256=digest)


def test_header_mismatch_before_decode(tmp_path,monkeypatch):
    a = generated_approval(tmp_path)
    a['cases'][0]['study_uid'] = '1.2.4'
    from pydicom.dataset import Dataset
    monkeypatch.setattr(Dataset,'pixel_array',property(lambda _:pytest.fail('decoded pixels')))
    with pytest.raises(ValueError,match='identity'):
        read_ct_volume(a,'SYNTHETIC','1.2.3.4')


def test_resource_budget_before_decode(tmp_path):
    a = generated_approval(tmp_path)
    with pytest.raises(ValueError,match='voxel budget'):
        read_ct_volume(a,'SYNTHETIC','1.2.3.4',max_voxels=5)


def test_resampling_preserves_world_and_support(tmp_path):
    a = generated_approval(tmp_path)
    v = read_ct_volume(a,'SYNTHETIC','1.2.3.4')
    r = resample_regular_hu(v,[1.,.75,.5], approved_membership=membership())
    assert r.volume_hu.shape == (5,7,9)
    np.testing.assert_allclose(r.volume_hu[2,4,6],v.volume_hu[1,2,3])
    world = transform_points([2,4,6],r.affine_lps)
    np.testing.assert_allclose(inverse_points(world,v.affine_lps),[1,2,3])
    assert not r.valid_mask[0,0,1]  # padding contaminates interpolated neighbour
    assert r.volume_hu[0,0,1] == -1024.
    assert r.source_sops == v.source_sops
    with pytest.raises(ValueError,match='membership'):
        resample_regular_hu(v,[2,2,2])


def test_identity_resample_and_ceil_edge(tmp_path):
    v = read_ct_volume(generated_approval(tmp_path),'SYNTHETIC','1.2.3.4')
    identity = resample_regular_hu(v,[2,1.5,1],approved_membership=membership())
    np.testing.assert_array_equal(identity.valid_mask,v.valid_mask)
    np.testing.assert_array_equal(identity.volume_hu[v.valid_mask],v.volume_hu[v.valid_mask])
    coarse = resample_regular_hu(v,[3,2,3],approved_membership=membership())
    assert not coarse.valid_mask[-1].any()
    assert coarse.transform_ledger[-1]['thin_lesion_loss_risk'] == 'NOT_EVALUATED'
    with pytest.raises(ValueError,match='voxel budget'):
        resample_regular_hu(v,[.01,.01,.01],approved_membership=membership(),max_voxels=60)


def test_asymmetric_oblique_reverse_stack_and_consumed_ledger(tmp_path):
    from epi_next.hospital_contract import spatial_from_volume, transform_chain
    import pydicom
    a = generated_approval(tmp_path)
    normal = np.array([0., 0., -1.])
    for entry in a['cases'][0]['files']:
        ds = pydicom.dcmread(entry['path'])
        z = int(str(ds.SOPInstanceUID).split('.')[-1]) - 1
        ds.ImageOrientationPatient = [0,1,0,1,0,0]  # column +Y, row +X
        ds.ImagePositionPatient = (np.array([10.,20.,30.]) + 2*z*normal).tolist()
        ds.PixelData = np.fromfunction(lambda y,x: 100*z+10*y+x,(4,5),dtype=int).astype(np.int16).tobytes()
        ds.save_as(entry['path'],enforce_file_format=True)
        entry['sha256'] = hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest()
    v = read_ct_volume(a,'SYNTHETIC','1.2.3.4')
    assert v.volume_hu[2,1,3] == -574.  # independent HU at z=2,y=1,x=3
    np.testing.assert_allclose(transform_points([2,1,3],v.affine_lps),[11.5,23.,26.])
    r = resample_regular_hu(v,[1.,.75,.5],approved_membership=membership())
    assert r.volume_hu[4,2,6] == -574.
    np.testing.assert_allclose(transform_points([4,2,6],r.affine_lps),[11.5,23.,26.])
    spatial = spatial_from_volume(r,approved_membership=membership())
    np.testing.assert_allclose(transform_chain(spatial),np.diag([.5,.5,.5,1.]))
    assert spatial['source_sops'] == v.source_sops
    r.transform_ledger[-1]['output_to_input_zyx'][0][0] = 1.
    with pytest.raises(ValueError,match='differs from ledger'):
        spatial_from_volume(r,approved_membership=membership())
