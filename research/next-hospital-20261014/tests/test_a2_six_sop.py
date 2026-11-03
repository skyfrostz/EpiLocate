"""Tiny programmatically encoded lossless JPEG and synthetic Part10/ZIP only."""
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import zipfile

import numpy as np
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.encaps import encapsulate
import pytest
from epi_next import a2_six_sop as a2
from test_a1_prepare import generated_request


def jpeg(values):
    values = np.asarray(values, dtype=np.uint16)
    h, w = values.shape
    bits = ''
    for y in range(h):
        for x in range(w):
            predictor = 32768 if y == x == 0 else int(values[y-1, x] if x == 0 else values[y, x-1])
            delta = int(values[y, x])-predictor
            n = abs(delta).bit_length()
            if n == 16:
                raise ValueError('fixture excludes JPEG category16 special case')
            bits += format(n, '05b')
            if n:
                bits += format(delta if delta >= 0 else (1 << n)-1+delta, f'0{n}b')
    bits += '1'*((-len(bits)) % 8)
    entropy = bytes(int(bits[i:i+8], 2) for i in range(0, len(bits), 8)).replace(b'\xff', b'\xff\0')
    def segment(marker, payload):
        return b'\xff'+bytes([marker])+struct.pack('>H', len(payload)+2)+payload
    return b'\xff\xd8'+segment(0xc4, b'\0'+bytes([0, 0, 0, 0, 17]+[0]*11)+bytes(range(17)))+segment(0xc3, struct.pack('>BHHB', 16, h, w, 1)+b'\1\x11\0')+segment(0xda, b'\1\1\0\1\0\0')+entropy+b'\xff\xd9'


def dicom(i, signed=False):
    values = np.array([[32767, 32768, 32769], [32770, 32771, 32772]], dtype=np.uint16) if signed else np.array([[4095, 0, 1], [10, 11, 12]], dtype=np.uint16)
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = a2.old.CT
    meta.MediaStorageSOPInstanceUID = f'1.2.3.{i}'
    meta.TransferSyntaxUID = a2.JPEG
    ds = FileDataset(None, {}, file_meta=meta, preamble=b'\0'*128)
    ds.SOPClassUID = a2.old.CT; ds.SOPInstanceUID = f'1.2.3.{i}'; ds.Modality = 'CT'
    ds.StudyInstanceUID = f'1.2.4.{i}'; ds.SeriesInstanceUID = f'1.2.5.{i}'; ds.FrameOfReferenceUID = f'1.2.6.{i}'
    ds.PatientName = 'GENERATED_FORBIDDEN_NAME'; ds.PatientID = 'GENERATED_FORBIDDEN_ID'
    ds.ImageType = ['ORIGINAL', 'PRIMARY']; ds.Rows = 2; ds.Columns = 3
    ds.SamplesPerPixel = 1; ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.BitsAllocated = 16; ds.BitsStored = 16; ds.HighBit = 15; ds.PixelRepresentation = int(signed)
    ds.PixelSpacing = [.7, .8]; ds.ImagePositionPatient = [0, 0, i]; ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.RescaleSlope = 2; ds.RescaleIntercept = -1000; ds.RescaleType = 'HU'
    ds.PixelData = encapsulate([jpeg(values)])
    buffer = io.BytesIO(); pydicom.dcmwrite(buffer, ds, enforce_file_format=True)
    return buffer.getvalue(), values.view(np.int16) if signed else values


def fixture(tmp_path, collision=False):
    archive = tmp_path/'generated-only.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for i in range(1, 7):
            raw = dicom(i, i == 6)[0]
            if collision and i == 2:raw = raw.replace(b'1.2.3.2', b'1.2.3.1')
            z.writestr(f'GENERATED/{i}.dcm', raw)
        z.writestr('FORBIDDEN.csv', b'GENERATED_NOT_ALLOWED')
    with zipfile.ZipFile(archive) as z:
        rows = [{'name': m.filename, 'compression_method': m.compress_type, 'compressed_bytes': m.compress_size,
                 'uncompressed_bytes': m.file_size, 'crc32': m.CRC, 'header_offset': m.header_offset} for m in z.infolist()[:6]]
    inventory = tmp_path/'generated-inventory.json'; inventory.write_text(json.dumps(rows))
    receipt = tmp_path/'generated-a0.json'; receipt.write_text('{}')
    st = archive.stat()
    fields = [f for f in generated_request()['requests'][0]['field_value_whitelist'] if f['keyword'] in a2.FIELDS]
    return {'field_value_whitelist': fields, 'source_archive': {'path': str(archive), 'bytes': st.st_size,
            'stat_binding': {'device': st.st_dev, 'inode': st.st_ino, 'mtime_ns': st.st_mtime_ns},
            'receipt_path': str(receipt), 'receipt_sha256': a2.old.sha(receipt)},
            'inventory_binding': {'path': str(inventory), 'sha256': a2.old.sha(inventory)},
            'selection': [{'candidate_id': f'GENERATED-{i}', 'member': r} for i, r in enumerate(rows, 1)]}


def test_header_stops_before_pixels_and_excludes_identity(tmp_path):
    r = fixture(tmp_path); out = tmp_path/'out'; out.mkdir()
    result = a2.discover(r, out)
    d = json.loads(Path(result['path']).read_text())
    assert len(result['eligible']) == 6
    assert 'GENERATED_FORBIDDEN_NAME' not in json.dumps(d) and 'GENERATED_FORBIDDEN_ID' not in json.dumps(d)
    for row in d['rows']:
        assert row['header']['consumed_prefix_bytes'] == row['header']['pixel_value_offset']
        assert row['geometry']['actual_inter_slice_spacing'] == 'UNKNOWN_SINGLE_SOP'


def test_same_pipeline_generated_lossless_decode_signed_and_rescale(tmp_path, monkeypatch):
    r = fixture(tmp_path)
    monkeypatch.setitem(a2.OVERALL, 'disk_free_floor_bytes', 0)
    out = tmp_path/'out'; receipt = a2.pipeline(r, out, True)
    assert receipt['status'] == 'COMPLETE_ELIGIBLE_SINGLE_SOP_SUBSET', receipt
    assert receipt['A2b']['decoded_SOP_count'] == 6
    for i in range(1, 7):
        p = out/f'GENERATED-{i}'
        _, expected = dicom(i, i == 6)
        np.testing.assert_array_equal(np.load(p/'native-stored.npy'), expected)
        np.testing.assert_array_equal(np.load(p/'native-rescaled.npy'), expected.astype(np.float32)*2-1000)
        case = json.loads((p/'case.json').read_text()); assert case['units'] == 'HU'
        assert case['training_eligible'] is False and case['patient_independence'] == 'UNKNOWN'
    assert receipt['A2a']['budget']['observed_process_peak_RSS_bytes'] > 0
    assert 'torch' not in sys.modules


def test_header_only_creates_no_arrays(tmp_path, monkeypatch):
    r = fixture(tmp_path); monkeypatch.setitem(a2.OVERALL, 'disk_free_floor_bytes', 0)
    out = tmp_path/'out'; receipt = a2.pipeline(r, out, False)
    assert receipt['status'] == 'A2A_COMPLETE_A2B_NOT_APPROVED'
    assert not list(out.rglob('*.npy'))


def test_geometry_uid_and_orientation_rejections(tmp_path):
    r = fixture(tmp_path); out = tmp_path/'out'; out.mkdir(); d = a2.discover(r, out)
    h = json.loads(Path(d['path']).read_text())['rows'][0]['header']
    for key, value in [('MediaStorageSOPInstanceUID', '1.9.9'), ('ImageOrientationPatient', [1, 0, 0, 1, 0, 0]), ('PixelSpacing', [0, .8]), ('NumberOfFrames', 2)]:
        invalid = copy.deepcopy(h); invalid['values'][key] = value
        with pytest.raises(a2.old.HeaderError):a2.geometry(invalid)


def test_malformed_fragment_rejected_before_payload_and_missing_delimiter():
    class Memory:
        def __init__(self, raw):self.raw = raw; self.offset = 0
        def read(self, n):
            if self.offset+n > len(self.raw):raise a2.old.GuardError('SHORT')
            result = self.raw[self.offset:self.offset+n]; self.offset += n; return result
    raw = struct.pack('<HHI', 0xfffe, 0xe000, 0)+struct.pack('<HHI', 0xfffe, 0xe000, 0xffffffff)+b'SHOULD_NOT_READ'
    m = Memory(raw)
    with pytest.raises(a2.old.HeaderError, match='BAD_PIXEL_FRAGMENT'):a2.encapsulated(m)
    assert m.offset == 16
    with pytest.raises(a2.old.GuardError):a2.encapsulated(Memory(struct.pack('<HHI', 0xfffe, 0xe000, 0)))


def test_corrupt_jpeg_refuses_decode():
    values = {'Rows': 2, 'Columns': 3, 'SamplesPerPixel': 1, 'PhotometricInterpretation': 'MONOCHROME2',
              'BitsAllocated': 16, 'BitsStored': 16, 'HighBit': 15, 'PixelRepresentation': 0}
    with pytest.raises(Exception):a2.decode_pixels(values, encapsulate([b'GENERATED_INVALID_JPEG']))


def test_source_drift_and_output_cap_fail_no_canonical(tmp_path, monkeypatch):
    r = fixture(tmp_path); bad = copy.deepcopy(r); bad['source_archive']['stat_binding']['inode'] += 1
    with pytest.raises(a2.old.GuardError):a2.discover(bad, tmp_path)
    monkeypatch.setitem(a2.OVERALL, 'disk_free_floor_bytes', 0)
    monkeypatch.setitem(a2.B, 'output_bytes_total', 128*1024+50)
    out = tmp_path/'out'; result = a2.pipeline(r, out, True)
    assert result['status'] == 'FAILED' and not (out/'canonical.json').exists()


def test_cli_no_approval_cannot_open_pipeline(monkeypatch, capsys):
    binding = {'request_sha256': '1'*64, 'source_bindings': [{'path': m.__file__} for m in (a2, a2.meta)],
               'decoder_distributions': {}, 'decoder_module_bindings': [], 'decoder_binary_bindings': []}
    monkeypatch.setattr(a2, 'bound_json', lambda path, digest: {} if path == 'r' else binding)
    monkeypatch.setattr(a2.old, 'verify_readiness', lambda b: None)
    monkeypatch.setattr(a2, 'validate', lambda r: None)
    monkeypatch.setattr(a2, 'pipeline', lambda *args: pytest.fail('real pipeline invoked'))
    argv = ['generated', '--request', 'r', '--request-sha256', '1'*64, '--readiness', 'b', '--readiness-sha256', '2'*64]
    monkeypatch.setattr(sys, 'argv', argv); a2.main()
    assert json.loads(capsys.readouterr().out)['status'] == 'CHECK_ONLY_NO_ARCHIVE_MEMBER_ACCESS'
    monkeypatch.setattr(sys, 'argv', argv+['--execute'])
    with pytest.raises(a2.old.GuardError, match='NEW_EXACT_A2_APPROVAL_REQUIRED'):a2.main()


def test_unsupported_syntax_and_sequence_stop_before_values(tmp_path):
    from test_a1_file_meta_v2 import Memory
    fields = [f for f in generated_request()['requests'][0]['field_value_whitelist'] if f['keyword'] in a2.FIELDS]
    allowed = {tuple(int(x, 16) for x in f['tag'].split(',')): f['keyword'] for f in fields}
    raw, _ = dicom(1)
    bad = raw.replace(a2.JPEG.encode(), b'1.2.840.10008.1.2.4.71')
    m = Memory(bad)
    with pytest.raises(a2.meta.HeaderError, match='UNSUPPORTED_TRANSFER_SYNTAX') as caught:
        a2.header(m, {}, allowed)
    assert caught.value.metadata['values']['TransferSyntaxUID'] == '1.2.840.10008.1.2.4.71'
    end = 144 + struct.unpack_from('<I', raw, 140)[0]
    sequence = struct.pack('<HH', 0x0008, 0x1115)+b'SQ\0\0'+struct.pack('<I', 14)
    m = Memory(raw[:end]+sequence+b'PIXELS_NOTREAD!'+raw[end:])
    with pytest.raises(a2.meta.HeaderError, match='CONTAINER'):
        a2.header(m, {}, allowed)
    assert m.emitted == end+len(sequence)


def test_complete_member_crc_rejects_changed_uninterpreted_tail(tmp_path):
    r = fixture(tmp_path)
    archive = tmp_path/'generated-crc.zip';raw, _ = dicom(1)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_STORED) as z:z.writestr('GENERATED/1.dcm', raw+b'TAIL')
    with zipfile.ZipFile(archive) as z:
        m = z.infolist()[0];member = {'name':m.filename,'compression_method':m.compress_type,'compressed_bytes':m.compress_size,'uncompressed_bytes':m.file_size,'crc32':m.CRC,'header_offset':m.header_offset}
    corrupt = bytearray(archive.read_bytes());corrupt[30+len(member['name'])+len(raw)+3] ^= 1;archive.write_bytes(corrupt)
    st=archive.stat();r['source_archive'].update(path=str(archive),bytes=st.st_size,stat_binding={'device':st.st_dev,'inode':st.st_ino,'mtime_ns':st.st_mtime_ns})
    r['selection']=[{'candidate_id':'GENERATED-1','member':member}]
    out=tmp_path/'header';out.mkdir();d=a2.discover(r,out);row=json.loads(Path(d['path']).read_text())['rows'][0]
    with pytest.raises(a2.old.GuardError,match='CRC'):
        a2.decode_case(r,row,out,{})


def test_precision_mismatch_not_silently_fixed():
    values={'Rows':2,'Columns':3,'SamplesPerPixel':1,'PhotometricInterpretation':'MONOCHROME2','BitsAllocated':16,'BitsStored':8,'HighBit':7,'PixelRepresentation':0}
    with pytest.raises(a2.old.HeaderError,match='PRECISION_MISMATCH'):
        a2.decode_pixels(values,encapsulate([jpeg([[4095,0,1],[10,11,12]])]))


def test_duplicate_dataset_SOP_blocks_all_decoding(tmp_path,monkeypatch):
    r=fixture(tmp_path,collision=True);monkeypatch.setitem(a2.OVERALL,'disk_free_floor_bytes',0)
    out=tmp_path/'out';receipt=a2.pipeline(r,out,True)
    assert receipt['status']=='A2B_BLOCKED_DUPLICATE_SOP'
    assert not list(out.rglob('*.npy'))


def test_wrong_predictor_and_trailing_frame_are_refused():
    values={'Rows':2,'Columns':3,'SamplesPerPixel':1,'PhotometricInterpretation':'MONOCHROME2','BitsAllocated':16,'BitsStored':16,'HighBit':15,'PixelRepresentation':0}
    frame=jpeg([[4095,0,1],[10,11,12]])
    invalid=bytearray(frame);pos=invalid.index(b'\xff\xda');invalid[pos+7]=2
    with pytest.raises(a2.old.HeaderError,match='PREDICTOR'):a2.validate_jpeg_frame(bytes(invalid),values)
    with pytest.raises(a2.old.HeaderError,match='TRAILING'):a2.validate_jpeg_frame(frame+frame,values)
