"""Generated NIfTI members only; no existing patient arrays or archives."""

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[3]
import json
import hashlib
import resource
import struct
import sys
import time
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from epi_next import first_case_nifti_qa_v1 as qa


def write_pair(tmp_path, *, klass=nib.Nifti1Image, affine=None, mask=None,
               ct=None, slope=None, intercept=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    affine = np.diag([-1.5, -2., 3., 1.]) if affine is None else affine
    ct = np.arange(8 * 9 * 10, dtype=np.int16).reshape((8, 9, 10)) if ct is None else ct
    if mask is None:
        mask = np.zeros(ct.shape, dtype=np.uint8)
        mask[1:4, 2:5, 4:7] = 1
        mask[5:7, 6:8, 1:3] = 2
    paths = []
    for name, array in (('ct', ct), ('mask', mask)):
        image = klass(array, affine, dtype=array.dtype)
        image.header.set_xyzt_units('mm')
        image.set_qform(affine, code=1)
        image.set_sform(affine, code=1)
        if name == 'ct' and slope is not None:
            image.header.set_slope_inter(slope, intercept)
        path = tmp_path / (name + '.nii')
        nib.save(image, path)
        paths.append(path)
    return paths


def evidence():
    binding = {'path': 'GENERATED_METADATA_ONLY', 'sha256': 'a' * 64}
    return dict(hu_status='NATIVE_HU_VERIFIED', hu_binding=binding,
        case_domain=dict(modality='CT', value_domain='HU', case_bound=True),
        class_map=[dict(value=0, raw_class='SOURCE_ZERO', medical_category='unknown_background'),
                   dict(value=1, raw_class='SOURCE_INFECTION', medical_category='infection'),
                   dict(value=2, raw_class='SOURCE_OTHER_CLASS', medical_category='other')],
        expert_status='SOURCE_EXPERT_CONFIRMED', extent='PARTIAL_ANNOTATION',
        patient_status='SOURCE_DEIDENTIFIED_VERIFIED', license_status='LICENSE_VERIFIED',
        expert_binding=binding, extent_binding=binding, patient_binding=binding,
        license_binding=binding, class_map_binding=binding)


@pytest.mark.parametrize('klass', [nib.Nifti1Image, nib.Nifti2Image])
def test_generated_formats_scaling_once_k8_and_no_full_float_volume(tmp_path, monkeypatch, klass):
    ct, mask = write_pair(tmp_path, klass=klass, slope=2., intercept=-100.)
    def forbidden(*args, **kwargs):
        raise AssertionError('Full float volume is forbidden')
    monkeypatch.setattr(klass, 'get_fdata', forbidden)
    result = qa.analyze_pair(ct, mask, evidence(), None, {})
    assert result['status'] == 'UNKNOWN' and result['geometry']['status'] == 'PASS'
    ct_meta = result['members']['CT']
    assert ct_meta['raw_scaling'] == dict(slope=2., intercept=-100.)
    assert ct_meta['effective_proxy_scaling'] == dict(slope=2., intercept=-100., applications=1)
    assert ct_meta['statistics']['raw']['minimum'] == 0.
    assert ct_meta['statistics']['scaled']['minimum'] == -100.
    assert ct_meta['statistics']['scaled']['maximum'] == 1338.
    assert ct_meta['statistics']['full_float_volume_materialized'] is False
    assert result['medical_denominator'] is None and result['full_region_metrics_enabled'] is False
    selections = result['K8']['selections']
    assert [row['native_Z'] for row in selections] == [int((j + .5) * 10 / 8) for j in range(8)]
    assert len(result['geometry']['shape_and_transform_sha256']) == 64
    assert all(row['world_roundtrip_max_vox'] < 1e-5 for row in selections)
    counts = result['members']['Mask']['statistics']['scaled_value_counts']
    assert counts['1'] == 27 and counts['2'] == 8
    assert sum(row['infection_voxels'] for row in result['members']['Mask']['statistics']['per_native_Z']) == 27
    json.dumps(result, allow_nan=False)


def test_integer_axis_permutation_and_flips_are_reversible(tmp_path):
    # Original signed Z is preserved; canonical superior Z is metadata only.
    affine = np.array([[0., -2., 0., 50.], [3., 0., 0., -10.], [0., 0., -4., 40.], [0., 0., 0., 1.]])
    ct, mask = write_pair(tmp_path, affine=affine)
    result = qa.analyze_pair(ct, mask, evidence(), None, {})
    assert result['geometry']['status'] == 'PASS'
    meta = result['members']['CT']
    assert meta['native_shape_ZYX'] == [10, 9, 8]
    assert meta['resampled'] is False and meta['index_roundtrip_max_vox'] < 1e-5
    forward = np.asarray(meta['native_ZYX_to_original_XYZ'])
    inverse = np.asarray(meta['original_XYZ_to_native_ZYX'])
    assert np.allclose(inverse @ forward, np.eye(4))
    first = result['K8']['selections'][0]
    assert first['original_plane_corners_XYZ'][0][2] == 0.
    assert first['canonical_plane_corners_XYZ'][0][2] == 9.
    assert first['original_nifti_Z'] == first['native_Z'] == 0
    assert first['mask_counts']['original_plane_axis'] == 2
    assert result['canonical_reference_K8']['used_for_frozen_K8'] is False


def test_missing_evidence_preserves_all_unknown_domains_and_no_normal_inference(tmp_path):
    ct, mask = write_pair(tmp_path, ct=np.full((8, 9, 10), -500, dtype=np.int16))
    result = qa.analyze_pair(ct, mask, {}, {}, {})
    assert result['status'] == 'UNKNOWN' and result['HU']['status'] == 'UNKNOWN'
    assert result['geometry']['status'] == 'PASS'
    assert {'HU', 'labels', 'preprocess', 'evidence'} <= {row['domain'] for row in result['reasons']}
    assert result['labels']['zero_is_normal'] is False
    assert result['labels']['unannotated_is_normal'] is False
    assert result['labels']['full_shape_establishes_complete_GT'] is False
    assert all(row['infection_voxels'] is None and row['infection_plane_sha256'] is None
               for row in result['members']['Mask']['statistics']['per_native_Z'])
    assert result['medical_denominator'] is None


@pytest.mark.parametrize('fault', ['fractional_mask', 'nonfinite_CT', 'depth_below_8'])
def test_numeric_or_fixed_sampling_failure_is_isolated(tmp_path, fault):
    data = np.ones((8, 9, 10), dtype=np.float32)
    mask = np.zeros(data.shape, dtype=np.float32)
    if fault == 'fractional_mask':
        mask[0, 0, 0] = .25
    elif fault == 'nonfinite_CT':
        data[0, 0, 0] = np.nan
    else:
        data = data[:, :, :7]
        mask = mask[:, :, :7]
    ct_path, mask_path = write_pair(tmp_path, ct=data, mask=mask)
    result = qa.analyze_pair(ct_path, mask_path, {}, None, {})
    assert result['status'] == 'REJECT'
    assert result['medical_denominator'] is None and result['resampling'] is False


@pytest.mark.parametrize('fault', ['q_s_conflict', 'oblique', 'pair_mismatch', 'nonaxial_original_Z'])
def test_geometry_problem_rejects_without_resampling(tmp_path, fault):
    ct_path, mask_path = write_pair(tmp_path)
    image = nib.load(ct_path if fault != 'pair_mismatch' else mask_path)
    affine = image.affine.copy()
    if fault == 'oblique':
        angle = np.deg2rad(15.)
        rotation = np.array([[np.cos(angle), -np.sin(angle), 0.],
                             [np.sin(angle), np.cos(angle), 0.], [0., 0., 1.]])
        affine[:3, :3] = rotation @ affine[:3, :3]
        image.set_qform(affine, code=1)
        image.set_sform(affine, code=1)
    elif fault == 'nonaxial_original_Z':
        affine = np.array([[0., -2., 0., 50.], [0., 0., 3., -10.], [-4., 0., 0., 40.], [0., 0., 0., 1.]])
        image.set_qform(affine, code=1)
        image.set_sform(affine, code=1)
    elif fault == 'q_s_conflict':
        affine[0, 3] += 10.
        image.set_sform(affine, code=1)
    else:
        affine[1, 3] += 10.
        image.set_qform(affine, code=1)
        image.set_sform(affine, code=1)
    # Save to a fresh generated file; do not overwrite a live memmap source.
    changed = tmp_path / 'changed.nii'
    nib.save(image, changed)
    result = qa.analyze_pair(changed if fault != 'pair_mismatch' else ct_path,
                             changed if fault == 'pair_mismatch' else mask_path, {}, None, {})
    assert result['status'] == 'REJECT' and result['resampling'] is False


def test_budget_check_failure_propagates_instead_of_becoming_case_rejection(tmp_path):
    ct, mask = write_pair(tmp_path)
    def stop():
        raise ValueError('GENERATED_BUDGET_STOP')
    with pytest.raises(ValueError, match='GENERATED_BUDGET_STOP'):
        qa.analyze_pair(ct, mask, {}, None, {}, check=stop)


def test_voxel_cap_is_checked_before_raw_proxy_scan(tmp_path):
    ct, mask = write_pair(tmp_path)
    result = qa.analyze_pair(ct, mask, {}, None, {'max_native_voxels_per_member': 100})
    assert result['status'] == 'REJECT'
    assert not result['members']
    assert any('NATIVE_VOXEL_CAP' in row['code'] for row in result['reasons'])


def test_arbitrary_or_conflicting_evidence_cannot_create_pass(tmp_path):
    ct, mask = write_pair(tmp_path)
    supplied = evidence()
    supplied.update(expert_status='ARBITRARY', extent='PARTIAL', license_status='CONFLICT', hu_status='WINDOWED_0_255')
    result = qa.analyze_pair(ct, mask, supplied, {'status': 'BOUND', 'binding': supplied['hu_binding'], 'fields': {'arbitrary': True}}, {})
    assert result['status'] == 'REJECT'  # Bound but conflicting preprocessing.
    assert result['qualification']['license_status']['effective_status'] == 'UNKNOWN'
    assert result['HU']['status'] == 'WINDOWED_0_255'
    assert any(row['domain'] == 'evidence' for row in result['reasons'])


def test_fixed8_export_hashes_native_order_and_explicit_infection_only(tmp_path):
    import importlib.util
    from pathlib import Path
    loc_source = Path(str(_PUBLIC_ROOT / 'research/next-hospital-20261014/epi_next/medical_localization_r108.py'))
    assert hashlib.sha256(loc_source.read_bytes()).hexdigest() == '107e443223bcadf9ccf252ebc1a634932998b355dc9bdfb12c46c3fc0a6a22ef'
    spec = importlib.util.spec_from_file_location('generated_frozen_LOC_hash', loc_source)
    frozen_loc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(frozen_loc)
    ct, mask = write_pair(tmp_path / 'sources', slope=2., intercept=-100.)
    supplied = evidence()
    supplied['member_bindings'] = {name: dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                                   for name, path in (('CT', ct), ('Mask', mask))}
    result = qa.analyze_pair(ct, mask, supplied, None, {})
    exported = qa.export_fixed8(ct, mask, result, supplied, tmp_path / 'exports', {}, check=lambda: None)
    assert exported['infection_GT_status'] == 'EXPORTED_EXPLICIT_CLASSES_ONLY'
    assert exported['resize_performed'] is False and exported['model_ready'] is False
    by_kind = {row['kind']: row for row in exported['arrays']}
    assert set(by_kind) == {'CT', 'FOV_SUPPORT', 'INFECTION_GT', 'REFERENCE_DOMAIN'}
    for record in by_kind.values():
        path = record['path']
        with open(path, 'rb') as stream:
            assert hashlib.sha256(stream.read()).hexdigest() == record['npy_stream_sha256']
        array = np.load(path, mmap_mode='r')
        digest = frozen_loc._array_sha(array)
        assert digest == record['shape_dtype_C_bytes_sha256']
        assert len(record['planes']) == 8 and array.shape == (8, 9, 8)
        if record['kind'] == 'FOV_SUPPORT':
            assert np.all(array)
        if record['kind'] == 'INFECTION_GT':
            assert int(array.sum()) == sum(row['mask_counts']['infection_voxels'] for row in result['K8']['selections'])
        array._mmap.close()


def test_representative_generated_shape_stays_bounded(tmp_path, record_property):
    data = np.arange(128 * 128 * 64, dtype=np.int16).reshape((128, 128, 64))
    mask = np.zeros(data.shape, dtype=np.uint8)
    mask[30:40, 50:70, 15:25] = 1
    ct, mask_path = write_pair(tmp_path, ct=data, mask=mask)
    started = time.monotonic()
    result = qa.analyze_pair(ct, mask_path, {}, None, {})
    record_property('generated_128x128x64_elapsed_seconds', time.monotonic() - started)
    assert result['status'] == 'UNKNOWN' and result['geometry']['status'] == 'PASS'
    assert result['members']['CT']['statistics']['raw']['voxels'] == 128 * 128 * 64
    assert result['members']['CT']['statistics']['numeric_working_buffer_policy_bytes'] == 16777216


@pytest.mark.parametrize('fault', ['depth', 'mask_value_count'])
def test_metadata_growth_caps_before_unbounded_receipt_growth(tmp_path, fault):
    mask = np.arange(8 * 9 * 10, dtype=np.int16).reshape((8, 9, 10)) if fault == 'mask_value_count' else None
    ct, mask_path = write_pair(tmp_path, mask=mask)
    result = qa.analyze_pair(ct, mask_path, {}, None, {'max_native_depth': 2} if fault == 'depth' else {})
    assert result['status'] == 'REJECT'
    expected = 'NATIVE_DEPTH_CAP' if fault == 'depth' else 'MASK_VALUE_CARDINALITY_CAP'
    assert any(expected in row['code'] for row in result['reasons'])


def test_fp32_unsafe_CT_outside_selected8_is_rejected(tmp_path):
    data = np.zeros((8, 9, 10), dtype=np.float64)
    # For depth10 the frozen8 skip original Z2 and Z7.
    data[0, 0, 2] = 1e100
    ct, mask = write_pair(tmp_path, ct=data)
    result = qa.analyze_pair(ct, mask, {}, None, {})
    assert result['status'] == 'REJECT'
    assert result['members']['CT']['statistics']['fp32_unsafe_voxels'] == 1
    assert any(row['code'] == 'FULL_VOLUME_FP32_UNSAFE' for row in result['reasons'])


def test_mask_int64_precision_loss_is_rejected_before_float_conversion(tmp_path):
    mask = np.zeros((8, 9, 10), dtype=np.int64)
    mask[0, 0, 0] = 2 ** 53 + 1
    ct, mask_path = write_pair(tmp_path, mask=mask)
    result = qa.analyze_pair(ct, mask_path, {}, None, {})
    assert result['status'] == 'REJECT'
    assert any(row['code'] == 'MASK_INTEGER_OUTSIDE_EXACT_FLOAT_DOMAIN' for row in result['reasons'])


def test_malformed_extension_length_is_bounded_before_voxel_mapping(tmp_path, monkeypatch):
    ct, mask = write_pair(tmp_path)
    image = nib.load(ct)
    image.header.extensions.append(nib.nifti1.Nifti1Extension(6, b'GENERATED_EXTENSION'))
    corrupt = tmp_path / 'corrupt-extension.nii'
    nib.save(image, corrupt)
    with corrupt.open('r+b') as stream:
        stream.seek(nib.Nifti1Header.sizeof_hdr + 4)
        stream.write(struct.pack('<i', 2 ** 30))
    original = nib.arrayproxy.ArrayProxy.get_unscaled
    mapped = []
    def tracked(proxy):
        mapped.append(str(proxy.file_like))
        return original(proxy)
    monkeypatch.setattr(nib.arrayproxy.ArrayProxy, 'get_unscaled', tracked)
    result = qa.analyze_pair(corrupt, mask, {}, None, {})
    assert result['status'] == 'REJECT'
    assert all('corrupt-extension' not in path for path in mapped)
    assert any('extension' in row['code'].lower() for row in result['reasons'])


def test_generated_near_capacity_100m_voxels_is_streamed_within_RSS(tmp_path, record_property):
    shape = (512, 512, 384)
    affine = np.diag([-1., -1., 2., 1.])
    paths = []
    fixture_started = time.monotonic()
    # Sparse generated files exercise the full logical300MiB native pair
    # without a giant ndarray or fixture-construction resident mapping.
    for name, dtype in (('ct', np.dtype('<i2')), ('mask', np.dtype('u1'))):
        header = nib.Nifti1Header()
        header.set_data_shape(shape)
        header.set_data_dtype(dtype)
        header.set_data_offset(352)
        header.set_xyzt_units('mm')
        header.set_qform(affine, code=1)
        header.set_sform(affine, code=1)
        path = tmp_path / ('capacity-' + name + '.nii')
        with path.open('wb') as stream:
            header.write_to(stream)
            assert stream.tell() == 352
            stream.truncate(352 + 100663296 * dtype.itemsize)
            for z in range(0, shape[2], 7):
                offset = 352 + (200 + shape[0] * 200 + shape[0] * shape[1] * z) * dtype.itemsize
                stream.seek(offset)
                stream.write(np.asarray([z - 512 if name == 'ct' else 1], dtype=dtype).tobytes())
        paths.append(path)
    fixture_elapsed = time.monotonic() - fixture_started
    # The capacity phase uses a fresh child running the complete same reader,
    # not pytest's accumulated SELF RSS or a relaxed production budget.
    import gzip
    import os
    import shutil
    import subprocess
    import zipfile
    from epi_next import first_case_qualification_v1 as entry
    targets = []
    for role, source in zip(('CT', 'INFECTION_MASK'), paths):
        gz_path = tmp_path / (role+'.nii.gz')
        with source.open('rb') as src, gzip.open(gz_path, 'wb') as dst:
            shutil.copyfileobj(src, dst, length=65536)
        archive_path = tmp_path/(role+'.zip')
        with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(gz_path, 'coronacases_001.nii.gz')
            info = archive.getinfo('coronacases_001.nii.gz')
        stat = archive_path.stat()
        targets.append(dict(role=role, archive=dict(path=str(archive_path), bytes=stat.st_size,
            device=stat.st_dev, inode=stat.st_ino, mtime_ns=stat.st_mtime_ns,
            stream_sha256=hashlib.sha256(archive_path.read_bytes()).hexdigest()),
            member=dict(name=info.filename, header_offset=info.header_offset,
            compression=info.compress_type, compressed_bytes=info.compress_size,
            uncompressed_bytes=info.file_size, declared_crc32=info.CRC)))
    request = dict(output_root=str(tmp_path/'capacity-output'), targets=targets,
        limits=dict(entry.LIMITS), evidence=evidence(), preprocess={})
    request_path = tmp_path/'capacity-generated-request.json'
    request_path.write_text(json.dumps(request))
    script = ("import json,resource,sys; from pathlib import Path; "
        "from epi_next.first_case_qualification_v1 import run; "
        "r=run(json.loads(Path(sys.argv[1]).read_text())); "
        "peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024); "
        "print(json.dumps(dict(status=r['status'],technical_status=r['technical_status'],"
        "SELF_peak_RSS_bytes=peak,metrics=r['metrics']))); "
        "sys.exit(0 if r['status']=='UNKNOWN' and r['technical_status']=='PASS' and peak<=268435456 else 1)")
    started = time.monotonic()
    completed = subprocess.run([sys.executable, '-c', script, str(request_path)],
        env=os.environ.copy(), capture_output=True, text=True, timeout=45)
    elapsed = time.monotonic()-started
    print(completed.stdout)
    assert completed.returncode == 0, completed.stderr+completed.stdout
    child = json.loads(completed.stdout)
    record_property('generated_512x512x384_fixture_seconds', fixture_elapsed)
    record_property('generated_512x512x384_full_entry_seconds', elapsed)
    record_property('generated_512x512x384_child_SELF_peak_RSS_bytes', child['SELF_peak_RSS_bytes'])
    print(json.dumps(dict(generated_shape_XYZ=list(shape), voxels_per_member=100663296,
        sparse_generated_fixture=True, fixture_seconds=fixture_elapsed,
        full_entry_seconds=elapsed, child=child)))
    result = json.loads((Path(request['output_root'])/'RECEIPT.json').read_text())
    assert result['qualification']['members']['CT']['statistics']['raw']['voxels'] == 100663296
    assert result['qualification']['members']['Mask']['statistics']['raw']['voxels'] == 100663296
    assert all(row['zip_CRC_EOF_verified'] and row['gzip_CRC_EOF_verified'] for row in result['integrity'])


@pytest.mark.parametrize('complete', [False, True])
@pytest.mark.skip(reason="Requires excluded private execution binding; public generated unit checks remain enabled")
def test_generated_handoff_passes_actual_LOC_data_gates_for_both_extents(tmp_path, complete):
    import importlib.util
    import types
    from epi_next import first_case_qualification_v1 as entry
    from test_first_case_qualification_v1 import inputs
    coordinator = Path(str(_PUBLIC_ROOT / '.local/private-bindings/manifests/epi-next-phase2-coordinator'))
    enc = coordinator/'r122-first-case-qualification-preparation-20261016/ENCODER/ENCODER_DATA_FROZEN_CONTRACT_V2.json'
    q = inputs(tmp_path)
    declared = evidence()
    declared.update(extent='COMPLETE_REFERENCE_VERIFIED' if complete else 'PARTIAL_REFERENCE_VERIFIED',
        patient_status='DEIDENTIFIED_VERIFIED', license_status='PERMITTED_VERIFIED',
        patient_group_id='GENERATED_DISTINCT_GROUP_ONLY', source_namespace='GENERATED_ONLY', source_version='GENERATED_V1')
    q['evidence'] = declared
    q['preprocess'] = dict(status='BOUND', binding=dict(path=str(enc), sha256=hashlib.sha256(enc.read_bytes()).hexdigest()),
                           fields=json.loads(enc.read_text()))
    # Deliberate fixture substitution, never real source identity evidence.
    for record, sha in zip(q['targets'], ['0000000000000000000000000000000000000000000000000000000000000000',
            '0000000000000000000000000000000000000000000000000000000000000000']):
        record['archive']['stream_sha256'] = sha
    result = entry.run(q)
    assert result['status'] == 'PASS'
    root = Path(q['output_root'])
    handoff = json.loads((root/'LOCALIZATION_HANDOFF.json').read_text())
    assert handoff['evidence_type'] == 'GENERATED_ONLY'
    assert isinstance(handoff['patient_group_provenance'], str)
    assert isinstance(handoff['label_mapping_provenance'], str)
    assert handoff['patient_group_provenance_binding'] == declared['patient_binding']
    gt = np.load(root/'fixed8/INFECTION_GT.npy')
    domain = np.load(root/'fixed8/REFERENCE_DOMAIN.npy')
    fov = np.load(root/'fixed8/FOV_SUPPORT.npy')
    if complete:
        assert domain.all() and handoff['reference_kind'] == 'COMPLETE_INFECTION_MASK'
    else:
        assert np.array_equal(domain, gt) and not domain.all()
        assert handoff['reference_kind'] == 'PARTIAL_INFECTION_REFERENCE'
    source = Path(str(_PUBLIC_ROOT / 'research/next-hospital-20261014/epi_next'))
    package = types.ModuleType('_generated_LOC_contract')
    package.__path__ = [str(source)]
    sys.modules[package.__name__] = package
    for name in ('medical_localization_r108', 'first_case_metrics_r122'):
        full = package.__name__+'.'+name
        spec = importlib.util.spec_from_file_location(full, source/(name+'.py'))
        module = importlib.util.module_from_spec(spec); sys.modules[full] = module; spec.loader.exec_module(module)
    adapter = sys.modules[package.__name__+'.first_case_metrics_r122']
    gate = adapter.evaluate_first_case(handoff, {}, None, None, gt, domain, fov, {})
    # All actual DATA identity/extent/array/provenance gates passed. There is
    # deliberately no model/CAM: stop exactly at its first separate gate.
    assert gate['reason'] == 'CAM_INPUT_IDENTITY_CONFLICT', gate
