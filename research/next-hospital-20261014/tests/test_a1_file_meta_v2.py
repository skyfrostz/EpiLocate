"""Generated Part10 prefixes/ZIPs only, never any patient archive body."""
import copy
import hashlib
import json
import struct
import sys
import zipfile

import pytest
from epi_next import a1_file_meta_v2 as probe


def ui(tag, value):
    raw = value.encode('ascii')
    if len(raw) % 2:
        raw += b'\0'
    return struct.pack('<HH', 2, tag) + b'UI' + struct.pack('<H', len(raw)) + raw


def generated(syntax='1.2.840.10008.1.2.1', instance='1.2.3.4'):
    meta = ui(2, probe.legacy.CT) + ui(3, instance)
    if syntax is not None:
        meta += ui(16, syntax)
    prefix = b'\0' * 128 + b'DICM' + struct.pack('<HH', 2, 0) + b'UL\x04\0' + struct.pack('<I', len(meta)) + meta
    dataset = struct.pack('<HH', 0x0010, 0x0010) + b'PN\x04\0DATA'
    return prefix + dataset + b'GENERATED_PIXEL_VALUE_MUST_NOT_EMIT', len(prefix)


class Memory:
    def __init__(self, raw):
        self.raw = raw
        self.emitted = 0
        self.hash = hashlib.sha256()

    def read(self, n):
        result = self.raw[self.emitted:self.emitted + n]
        self.emitted += len(result)
        self.hash.update(result)
        return result


@pytest.mark.parametrize('syntax,reason', [
    ('1.2.840.10008.1.2', None), ('1.2.840.10008.1.2.1', None),
    ('1.2.840.10008.1.2.5', 'UNSUPPORTED_TRANSFER_SYNTAX'),
    (None, 'MISSING_TRANSFER_SYNTAX')])
def test_supported_unsupported_missing_stop_before_dataset(syntax, reason):
    raw, end = generated(syntax)
    stream = Memory(raw)
    source = {'member': {'name': 'GENERATED.dcm', 'header_offset': 44}}
    if reason:
        with pytest.raises(probe.HeaderError, match=reason) as caught:
            probe.parse_file_meta(stream, source, probe.CAPS)
        metadata = caught.value.metadata
    else:
        metadata = probe.parse_file_meta(stream, source, probe.CAPS)
    assert stream.emitted == end
    assert metadata['source'] == source
    assert metadata['values']['MediaStorageSOPClassUID'] == probe.legacy.CT
    if syntax is None:
        assert 'TransferSyntaxUID' not in metadata['values']
    else:
        assert metadata['values']['TransferSyntaxUID'] == syntax
        assert metadata['field_offsets']['TransferSyntaxUID']['value_offset'] < end
    assert metadata['prefix_sha256'] == hashlib.sha256(raw[:end]).hexdigest()
    assert 'GENERATED_PIXEL_VALUE' not in json.dumps(metadata)


def test_invalid_uid_not_saved_and_prior_valid_value_retained():
    raw, _ = generated(instance='INVALID_PRIVATE_TEXT')
    with pytest.raises(probe.HeaderError, match='INVALID_UID') as caught:
        probe.parse_file_meta(Memory(raw), {'member': 'GENERATED'}, probe.CAPS)
    assert caught.value.metadata['values'] == {'MediaStorageSOPClassUID': probe.legacy.CT}
    assert 'INVALID_PRIVATE_TEXT' not in json.dumps(caught.value.metadata)


def test_missing_group_length_rejected_without_reading_first_value():
    raw, _ = generated()
    raw = raw[:132] + raw[144:]
    stream = Memory(raw)
    with pytest.raises(probe.HeaderError, match='GROUP_LENGTH_REQUIRED'):
        probe.parse_file_meta(stream, {}, probe.CAPS)
    assert stream.emitted == 136


def test_bad_declared_end_stops_at_non_meta_tag_before_dataset_value():
    raw, end = generated()
    changed = bytearray(raw)
    struct.pack_into('<I', changed, 140, end - 144 + 4)
    stream = Memory(bytes(changed))
    with pytest.raises(probe.HeaderError, match='NON_FILE_META') as caught:
        probe.parse_file_meta(stream, {}, probe.CAPS)
    assert stream.emitted == end + 4  # tag only; no dataset VR or value read
    assert caught.value.metadata['values']['TransferSyntaxUID'] == '1.2.840.10008.1.2.1'


def test_sequence_refused_before_embedded_value():
    raw, end = generated()
    seq = struct.pack('<HH', 2, 0x1001) + b'SQ\0\0' + struct.pack('<I', 8)
    new = bytearray(raw[:end] + seq + b'PIXELS!!' + raw[end:])
    struct.pack_into('<I', new, 140, end - 144 + len(seq) + 8)
    stream = Memory(bytes(new))
    with pytest.raises(probe.HeaderError, match='UNSUPPORTED_STRUCTURE'):
        probe.parse_file_meta(stream, {}, probe.CAPS)
    assert stream.emitted == end + len(seq)


def test_oversized_declared_meta_refused_before_body():
    raw, _ = generated()
    new = bytearray(raw)
    struct.pack_into('<I', new, 140, probe.CAPS['inflated_header_prefix_bytes_per_member'])
    stream = Memory(bytes(new))
    with pytest.raises(probe.HeaderError, match='DECLARED_LENGTH_LIMIT'):
        probe.parse_file_meta(stream, {}, probe.CAPS)
    assert stream.emitted == 144


def test_six_generated_members_use_bounded_production_reader(tmp_path):
    archive = tmp_path / 'generated.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for i in range(6):
            z.writestr(f'GENERATED/{i}.dcm', generated('1.2.840.10008.1.2.5')[0])
        z.writestr('FORBIDDEN.dcm', b'GENERATED_UNSELECTED_BODY')
    with zipfile.ZipFile(archive) as z:
        rows = [{'name': i.filename, 'compression_method': i.compress_type,
                 'compressed_bytes': i.compress_size, 'uncompressed_bytes': i.file_size,
                 'crc32': i.CRC, 'header_offset': i.header_offset} for i in z.infolist()[:6]]
    receipt = tmp_path / 'generated-a0.json'
    receipt.write_text('{}')
    inventory = tmp_path / 'generated-inventory.json'
    inventory.write_text(json.dumps(rows))
    st = archive.stat()
    request = {'caps': copy.deepcopy(probe.CAPS), 'source_archive': {
        'path': str(archive), 'sha256': probe.legacy.sha(archive), 'bytes': st.st_size,
        'stat_binding': {'device': st.st_dev, 'inode': st.st_ino, 'mtime_ns': st.st_mtime_ns},
        'receipt_path': str(receipt), 'receipt_sha256': probe.legacy.sha(receipt)},
        'inventory_binding': {'path': str(inventory), 'sha256': probe.legacy.sha(inventory)},
        'selection': [{'candidate_id': f'GENERATED-{i}', 'member': r} for i, r in enumerate(rows)]}
    out = tmp_path / 'output'
    out.mkdir()
    result = probe.probe(request, out)
    value = json.loads((out / 'file-meta-results.json').read_text())
    assert result['member_count'] == 6
    assert all(r['reason'] == 'UNSUPPORTED_TRANSFER_SYNTAX' for r in value['members'])
    assert all(r['metadata']['values']['TransferSyntaxUID'] == '1.2.840.10008.1.2.5' for r in value['members'])
    assert result['budget']['output_bytes'] == (out / 'file-meta-results.json').stat().st_size
    assert value['pixel_values_emitted'] == value['dataset_values_parsed'] == 0
    assert 'torch' not in sys.modules


def test_cli_consumed_old_approval_cannot_run_probe(monkeypatch, capsys):
    binding = {'request_sha256': '1' * 64, 'source_bindings': [
        {'path': probe.__file__, 'sha256': probe.legacy.sha(probe.__file__)}]}
    request = {'generated': True}
    old_approval = {'request_sha256': probe.legacy.APPLICATION_SHA,
                    'permit_A1a': True, 'permit_A1b': True, 'permit_model': False}
    monkeypatch.setattr(probe, 'bound_json', lambda p, h: {'r': request, 'b': binding, 'a': old_approval}[p])
    monkeypatch.setattr(probe.legacy, 'verify_readiness', lambda b: None)
    monkeypatch.setattr(probe, 'validate_request', lambda r: None)
    monkeypatch.setattr(probe, 'phase', lambda *a: pytest.fail('probe started'))
    args = ['generated', '--request', 'r', '--request-sha256', '1' * 64,
            '--readiness', 'b', '--readiness-sha256', '2' * 64]
    monkeypatch.setattr(sys, 'argv', args)
    probe.main()
    assert json.loads(capsys.readouterr().out)['status'] == 'CHECK_ONLY_NO_ARCHIVE_MEMBER_ACCESS'
    monkeypatch.setattr(sys, 'argv', args + ['--execute'])
    with pytest.raises(probe.legacy.GuardError, match='NEW_EXACT_PROBE_APPROVAL_REQUIRED'):
        probe.main()
    monkeypatch.setattr(sys, 'argv', args + ['--execute', '--approval', 'a', '--approval-sha256', '3' * 64])
    with pytest.raises(probe.legacy.GuardError, match='NEW_PROBE_APPROVAL_SCOPE_MISMATCH'):
        probe.main()


def test_exact_original_order_selection_enforced(monkeypatch):
    original = {'candidates': [{'candidate_id': str(i), 'directory': f'GENERATED/{i}',
                               'members': [{'name': f'GENERATED/{i}/first.dcm'}, {'name': 'second.dcm'}]}
                              for i in range(6)], 'source_archive': {}, 'inventory_binding': {}}
    monkeypatch.setattr(probe, 'bound_json', lambda *args: original)
    request = {'original_request_path': 'generated', 'original_request_sha256': probe.legacy.APPLICATION_SHA,
               'source_archive': {}, 'inventory_binding': {}, 'caps': probe.CAPS,
               'overall_wall_seconds': 90, 'pixel_values_permitted': False, 'models_permitted': False,
               'selection': [{'candidate_id': c['candidate_id'], 'directory': c['directory'],
                              'member_order_index': 0, 'member': c['members'][0]}
                             for c in original['candidates']]}
    probe.validate_request(request)
    request['selection'][0]['member'] = original['candidates'][0]['members'][1]
    with pytest.raises(probe.legacy.GuardError, match='EXACT_SIX_FIRST_MEMBERS_REQUIRED'):
        probe.validate_request(request)
