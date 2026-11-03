"""R124 ZIP flag-policy regression; exclusively generated tiny archives.

No real archive bytes, network, models, queue or capacity workload is accessed.
The legacy fixture helpers create NIfTI/gzip/ZIP bytes under pytest tmp_path.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import traceback
import zipfile
import zlib

import pytest

from epi_next import first_case_qualification_v1 as qualification
from test_first_case_qualification_v1 import MEMBER, gzip_bytes, inputs, nifti_bytes, result_text, target


DEFLATE_MASK = 0x80e
STORED_MASK = 0x808


def local_fields(*, method=8, flags=0, signature=b'PK\x03\x04'):
    raw = bytearray(zipfile.sizeFileHeader)
    raw[:4] = signature
    struct.pack_into('<HH', raw, 6, flags, method)
    return struct.unpack(zipfile.structFileHeader, raw)


def central_info(*, method=8, flags=0):
    info = zipfile.ZipInfo(MEMBER)
    info.compress_type = method
    info.flag_bits = flags
    return info


def check_policy(*, local_method=8, central_method=None, local_flags=0,
                 central_flags=None, signature=b'PK\x03\x04'):
    info = central_info(method=local_method if central_method is None else central_method,
                        flags=local_flags if central_flags is None else central_flags)
    record = {}
    qualification.validate_zip_local_header(
        local_fields(method=local_method, flags=local_flags, signature=signature), info, record)
    return record['zip_local_header_diagnostic']


def expect_policy_reject(code, **kwargs):
    local_method = kwargs.get('local_method', 8)
    local_flags = kwargs.get('local_flags', 0)
    info = central_info(method=kwargs.get('central_method', local_method),
                        flags=kwargs.get('central_flags', local_flags))
    record = {}
    with pytest.raises(ValueError, match='^' + code + '$'):
        qualification.validate_zip_local_header(local_fields(method=local_method,
            flags=local_flags, signature=kwargs.get('signature', b'PK\x03\x04')), info, record)
    diagnostic = record['zip_local_header_diagnostic']
    assert diagnostic['failed_check'] == code
    for key in ('signature_u32', 'local_method', 'central_method', 'local_flags',
                'central_flags', 'allowed_flags', 'rejected_flags'):
        assert type(diagnostic[key]) is int
    assert diagnostic['local_method'] == local_method
    assert diagnostic['local_flags'] == local_flags
    return diagnostic


@pytest.mark.parametrize('options', [0, 2, 4, 6])
@pytest.mark.parametrize('other_flags', [0, 8, 0x800, 0x808])
def test_deflate_options_descriptor_utf8_are_accepted_and_recorded(options, other_flags):
    flags = options | other_flags
    diagnostic = check_policy(local_flags=flags)
    assert diagnostic['signature_u32'] == 0x04034b50
    assert diagnostic['local_method'] == diagnostic['central_method'] == 8
    assert diagnostic['local_flags'] == diagnostic['central_flags'] == flags
    assert diagnostic['allowed_flags'] == DEFLATE_MASK
    assert diagnostic['rejected_flags'] == 0
    assert diagnostic['failed_check'] is None


@pytest.mark.parametrize('flags', [0, 8, 0x800, 0x808])
def test_stored_allows_descriptor_utf8_but_has_no_deflate_options(flags):
    diagnostic = check_policy(local_method=0, local_flags=flags)
    assert diagnostic['allowed_flags'] == STORED_MASK
    assert diagnostic['rejected_flags'] == 0


@pytest.mark.parametrize('options', [2, 4, 6])
def test_deflate_option_bits_are_rejected_for_stored_method(options):
    diagnostic = expect_policy_reject('ZIP_FLAGS_UNSUPPORTED', local_method=0,
                                      local_flags=options)
    assert diagnostic['allowed_flags'] == STORED_MASK
    assert diagnostic['rejected_flags'] == options


@pytest.mark.parametrize('bit', [4, 5, 7, 8, 9, 10, 12, 14, 15])
def test_every_other_unknown_flag_bit_is_rejected(bit):
    diagnostic = expect_policy_reject('ZIP_FLAGS_UNSUPPORTED', local_flags=1 << bit)
    assert diagnostic['rejected_flags'] == 1 << bit


@pytest.mark.parametrize('bit', [0, 6, 13])
def test_encryption_flags_have_separate_failure_code(bit):
    expect_policy_reject('ZIP_ENCRYPTION_UNSUPPORTED', local_flags=1 << bit)


def test_unsupported_method_is_not_misreported_as_flag_problem():
    expect_policy_reject('ZIP_METHOD_UNSUPPORTED', local_method=9)


def test_local_and_central_methods_must_match():
    expect_policy_reject('ZIP_LOCAL_METHOD_MISMATCH', local_method=0, central_method=8)


def test_local_and_central_flags_must_match_even_when_each_is_supported():
    expect_policy_reject('ZIP_LOCAL_FLAGS_MISMATCH', local_flags=2, central_flags=0)


def test_signature_has_separate_failure_code_and_numeric_diagnostic():
    diagnostic = expect_policy_reject('ZIP_LOCAL_SIGNATURE', signature=b'BAD!')
    assert diagnostic['signature_u32'] == int.from_bytes(b'BAD!', 'little')


def mutate_generated_flags(q, *, options=0, utf8=False, local_only=False,
                           method=None, signature=None):
    """Patch generated headers and then bind generated stat/digest metadata."""
    target = q['targets'][0]
    path = Path(target['archive']['path'])
    raw = bytearray(path.read_bytes())
    local = target['member']['header_offset']
    eocd = raw.rfind(b'PK\x05\x06')
    assert eocd >= 0
    central = struct.unpack_from('<I', raw, eocd + 16)[0]
    assert raw[central:central + 4] == b'PK\x01\x02'
    old_flags = struct.unpack_from('<H', raw, local + 6)[0]
    flags = old_flags | options | (0x800 if utf8 else 0)
    struct.pack_into('<H', raw, local + 6, flags)
    if not local_only:
        struct.pack_into('<H', raw, central + 8, flags)
    if method is not None:
        struct.pack_into('<H', raw, local + 8, method)
        struct.pack_into('<H', raw, central + 10, method)
        target['member']['compression'] = method
    if signature is not None:
        raw[local:local + 4] = signature
    path.write_bytes(raw)
    stat = path.stat()
    target['archive'].update(bytes=stat.st_size, device=stat.st_dev,
        inode=stat.st_ino, mtime_ns=stat.st_mtime_ns,
        stream_sha256=hashlib.sha256(raw).hexdigest())
    return flags


def rebind_generated_archive(target_record, raw):
    path = Path(target_record['archive']['path'])
    path.write_bytes(raw)
    stat = path.stat()
    target_record['archive'].update(bytes=stat.st_size, device=stat.st_dev,
        inode=stat.st_ino, mtime_ns=stat.st_mtime_ns,
        stream_sha256=hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize('options', [0, 2, 4, 6])
@pytest.mark.parametrize('variant', ['plain', 'utf8', 'descriptor', 'utf8_descriptor'])
def test_end_to_end_generated_deflate_options_utf8_and_descriptor(tmp_path, options, variant):
    q = inputs(tmp_path, zip_fault='descriptor_signed' if 'descriptor' in variant else None)
    flags = mutate_generated_flags(q, options=options, utf8='utf8' in variant)
    result = qualification.run(q)
    assert result['status'] == 'UNKNOWN', result
    assert result['technical_status'] == 'PASS'
    assert result['model_calls'] == result['network_calls'] == 0
    assert result['medical_denominator'] is None
    assert len(result['integrity']) == 2
    record = result['integrity'][0]
    assert record['zip_CRC_EOF_verified'] and record['gzip_CRC_EOF_verified']
    diagnostic = record['zip_local_header_diagnostic']
    assert diagnostic['local_flags'] == diagnostic['central_flags'] == flags
    assert diagnostic['rejected_flags'] == 0
    assert len(diagnostic['signature_hex']) == 8


@pytest.mark.parametrize('fault,code', [
    ('signature', 'ZIP_LOCAL_SIGNATURE'),
    ('local_flags', 'ZIP_LOCAL_FLAGS_MISMATCH'),
    ('encryption', 'ZIP_ENCRYPTION_UNSUPPORTED'),
    ('unknown_flag', 'ZIP_FLAGS_UNSUPPORTED'),
])
def test_end_to_end_bad_header_stops_before_mask_and_closes_archive_fd(tmp_path, monkeypatch, fault, code):
    q = inputs(tmp_path)
    if fault == 'signature':
        mutate_generated_flags(q, signature=b'BAD!')
    elif fault == 'local_flags':
        mutate_generated_flags(q, options=2, local_only=True)
    elif fault == 'encryption':
        mutate_generated_flags(q, options=1)
    else:
        mutate_generated_flags(q, options=0x100)
    archives = {row['archive']['path'] for row in q['targets']}
    opened, closed = [], []
    os_open, os_close = os.open, os.close

    def tracked_open(path, *args, **kwargs):
        fd = os_open(path, *args, **kwargs)
        if not isinstance(path, int) and os.fspath(path) in archives:
            opened.append((fd, os.fspath(path)))
        return fd

    def tracked_close(fd):
        closed.append(fd)
        return os_close(fd)

    monkeypatch.setattr(os, 'open', tracked_open)
    monkeypatch.setattr(os, 'close', tracked_close)
    result = qualification.run(q)
    assert result['status'] == 'REJECT'
    assert code in result_text(result).upper()
    assert result['integrity'][0]['zip_local_header_diagnostic']['failed_check'] == code
    assert len(result['integrity']) == 1
    assert opened and all(path == q['targets'][0]['archive']['path'] for _, path in opened)
    assert all(fd in closed for fd, _ in opened)
    assert (Path(q['output_root']) / 'RECEIPT.json').exists()


@pytest.mark.parametrize('scope,fault,expected', [
    ('outer', 'crc', 'CRC'),
    ('outer', 'deflate_truncated', 'ZIP_CRC_MISMATCH'),
    ('outer', 'deflate_trailing', 'TRAILING'),
    ('inner', 'crc', 'GZIP'),
    ('inner', 'truncated', 'GZIP'),
    ('inner', 'extra_stream', 'GZIP'),
    ('inner', 'trailing', 'GZIP'),
])
def test_old_container_crc_eof_and_extra_stream_guards_remain(tmp_path, scope, fault, expected):
    q = inputs(tmp_path, **{'zip_fault' if scope == 'outer' else 'inner_fault': fault})
    sentinel = tmp_path / 'external-sentinel.txt'
    sentinel.write_text('GENERATED_EXTERNAL_PRESERVE')
    mutate_generated_flags(q, options=6, utf8=True)
    result = qualification.run(q)
    assert result['status'] == 'REJECT'
    assert expected in result_text(result).upper()
    assert len(result['integrity']) == 1
    assert (Path(q['output_root']) / 'RECEIPT.json').exists()
    # Only this failed extraction's two new unverified working files are removed.
    assert not (Path(q['output_root']) / 'CT.nii.gz').exists()
    assert not (Path(q['output_root']) / 'CT.nii').exists()
    assert sentinel.read_text() == 'GENERATED_EXTERNAL_PRESERVE'


def test_full_payload_and_correct_crc_without_deflate_final_eof_is_rejected(tmp_path):
    q = inputs(tmp_path)
    item = q['targets'][0]
    path = Path(item['archive']['path'])
    with zipfile.ZipFile(path) as archive:
        payload = archive.read(MEMBER)
    raw = bytearray(path.read_bytes())
    local = item['member']['header_offset']
    name_bytes, extra_bytes = struct.unpack_from('<HH', raw, local + 26)
    payload_start = local + zipfile.sizeFileHeader + name_bytes + extra_bytes
    payload_end = payload_start + item['member']['compressed_bytes']
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    compressed = compressor.compress(payload) + compressor.flush(zlib.Z_SYNC_FLUSH)
    # All original payload/CRC bytes survive; only the Deflate final EOF is absent.
    decoder = zlib.decompressobj(-zlib.MAX_WBITS)
    assert decoder.decompress(compressed) == payload
    assert decoder.eof is False
    raw[payload_start:payload_end] = compressed
    central = payload_start + len(compressed)
    assert raw[central:central + 4] == b'PK\x01\x02'
    struct.pack_into('<I', raw, local + 18, len(compressed))
    struct.pack_into('<I', raw, central + 20, len(compressed))
    eocd = raw.rfind(b'PK\x05\x06')
    struct.pack_into('<I', raw, eocd + 16, central)
    item['member']['compressed_bytes'] = len(compressed)
    rebind_generated_archive(item, raw)
    mutate_generated_flags(q, options=6, utf8=True)
    result = qualification.run(q)
    assert result['status'] == 'REJECT'
    assert 'ZIP_DEFLATE_EOF_OR_TRAILING_BYTES' in result_text(result).upper()
    assert 'ZIP_CRC_MISMATCH' not in result_text(result).upper()
    assert len(result['integrity']) == 1
    output = Path(q['output_root'])
    assert not (output / 'CT.nii.gz').exists()
    assert not (output / 'CT.nii').exists()
    assert result['integrity'][0]['cleanup']['unverified_member_files_removed'] == 2


def test_mask_failure_retains_successful_ct_as_integrity_only_and_cleans_mask(tmp_path):
    q = inputs(tmp_path)
    q['targets'][1] = target(tmp_path, 'INFECTION_MASK',
        gzip_bytes(nifti_bytes(mask=True)), zip_fault='crc')
    mutate_generated_flags(q, options=6, utf8=True)
    result = qualification.run(q)
    assert result['status'] == 'REJECT'
    assert result['medical_denominator'] is None
    assert len(result['integrity']) == 2
    assert 'RETAINED_INTEGRITY_ONLY_NOT_QUALIFIED' in result_text(result).upper()
    output = Path(q['output_root'])
    assert (output / 'CT.nii.gz').exists()
    assert (output / 'CT.nii').exists()
    assert not (output / 'INFECTION_MASK.nii.gz').exists()
    assert not (output / 'INFECTION_MASK.nii').exists()
    assert (output / 'RECEIPT.json').exists()


@pytest.mark.parametrize('fault', ['budget', 'stat'])
def test_budget_and_archive_identity_checks_still_stop_before_mask(tmp_path, fault):
    q = inputs(tmp_path)
    mutate_generated_flags(q, options=6)
    if fault == 'budget':
        q['limits']['local_zip_read_bytes'] = 30
    else:
        q['targets'][0]['archive']['mtime_ns'] -= 1
    result = qualification.run(q)
    assert result['status'] == 'REJECT'
    assert len(result['integrity']) <= 1
    assert not (Path(q['output_root']) / 'INFECTION_MASK.nii.gz').exists()


def test_untrusted_local_filename_is_absent_from_exception_traceback_and_receipt(tmp_path, monkeypatch):
    q = inputs(tmp_path)
    record = q['targets'][0]
    raw = bytearray(Path(record['archive']['path']).read_bytes())
    start = record['member']['header_offset'] + zipfile.sizeFileHeader
    sentinel = b'UNTRUSTED_NAME_' + b'X' * (len(MEMBER) - len(b'UNTRUSTED_NAME_'))
    assert len(sentinel) == len(MEMBER)
    raw[start:start + len(MEMBER)] = sentinel
    rebind_generated_archive(record, raw)

    def no_payload_read(*args, **kwargs):
        raise AssertionError('mismatched local filename reached ZIP payload')

    monkeypatch.setattr(zipfile.ZipExtFile, 'read', no_payload_read)
    direct_root = tmp_path / 'direct-extract'
    direct_root.mkdir()
    budget = qualification.Budget(direct_root, q['limits'], None, None)
    diagnostic = {'role': 'CT'}
    with pytest.raises(ValueError, match='^ZIP_LOCAL_NAME_MISMATCH$') as caught:
        qualification.extract(record, direct_root, budget, diagnostic)
    error = caught.value
    rendered = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
    assert sentinel.decode() not in rendered
    assert error.__suppress_context__ is True
    result = qualification.run(q)
    assert result['status'] == 'REJECT'
    assert 'ZIP_LOCAL_NAME_MISMATCH' in result_text(result).upper()
    receipt = (Path(q['output_root']) / 'RECEIPT.json').read_text()
    assert sentinel.decode() not in receipt
    assert len(result['integrity']) == 1


@pytest.mark.parametrize('untrusted_name', ['../UNTRUSTED.nii.gz', '/UNTRUSTED.nii.gz', 'C:\\UNTRUSTED.nii.gz'])
def test_actual_path_like_member_cannot_replace_fixed_requested_member(tmp_path, monkeypatch, untrusted_name):
    q = inputs(tmp_path)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(untrusted_name, gzip_bytes(nifti_bytes()))
    raw = stream.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        info = archive.getinfo(untrusted_name)
    item = q['targets'][0]
    rebind_generated_archive(item, raw)
    item['member'].update(header_offset=info.header_offset, compression=info.compress_type,
        compressed_bytes=info.compress_size, uncompressed_bytes=info.file_size, declared_crc32=info.CRC)
    assert item['member']['name'] == MEMBER

    def no_member_open(*args, **kwargs):
        raise AssertionError('untrusted member path reached payload open')

    monkeypatch.setattr(zipfile.ZipFile, 'open', no_member_open)
    result = qualification.run(q)
    assert result['status'] == 'REJECT'
    assert 'ZIP_MEMBER_UNIQUE' in result_text(result).upper()
    assert untrusted_name not in json.dumps(result)
    assert len(result['integrity']) == 1
    assert not (Path(q['output_root']) / 'CT.nii.gz').exists()


@pytest.mark.parametrize('field,value', [
    ('header_offset', -1), ('header_offset', 'ARCHIVE_END'),
    ('compressed_bytes', 0), ('compressed_bytes', 'PAST_ARCHIVE_END'),
    ('uncompressed_bytes', 0), ('uncompressed_bytes', 100 * 1024**2 + 1),
])
def test_invalid_bound_member_offset_or_size_rejects_before_archive_read(tmp_path, field, value):
    q = inputs(tmp_path)
    size = q['targets'][0]['archive']['bytes']
    if value == 'ARCHIVE_END':
        value = size
    elif value == 'PAST_ARCHIVE_END':
        value = size + 1
    q['targets'][0]['member'][field] = value
    result = qualification.run(q)
    assert result['status'] == 'REJECT'
    assert 'MEMBER_BOUNDS' in result_text(result).upper()
    assert result['metrics']['local_zip_read_bytes'] == 0
    assert not (Path(q['output_root']) / 'CT.nii.gz').exists()


def test_inner_expansion_cap_cleans_only_own_partial_files_after_fd_close(tmp_path, monkeypatch):
    q = inputs(tmp_path)
    q['limits']['inner_gzip_max_per_member_bytes'] = 200
    sentinel = tmp_path / 'external-prior-output.txt'
    sentinel.write_bytes(b'GENERATED_OLD_OUTPUT_MUST_SURVIVE')
    archive_path = q['targets'][0]['archive']['path']
    os_open, os_close = os.open, os.close
    opened, closed = [], set()

    def track_open(path, *args, **kwargs):
        fd = os_open(path, *args, **kwargs)
        if not isinstance(path, int) and os.fspath(path) == archive_path:
            opened.append(fd)
        return fd

    def track_close(fd):
        closed.add(fd)
        return os_close(fd)

    monkeypatch.setattr(os, 'open', track_open)
    monkeypatch.setattr(os, 'close', track_close)
    result = qualification.run(q)
    assert result['status'] == 'REJECT'
    assert 'GZIP_EXPANDED_LIMIT' in result_text(result).upper()
    assert len(result['integrity']) == 1
    assert opened and all(fd in closed for fd in opened)
    output = Path(q['output_root'])
    assert not (output / 'CT.nii.gz').exists()
    assert not (output / 'CT.nii').exists()
    assert not (output / 'INFECTION_MASK.nii.gz').exists()
    assert result['integrity'][0]['cleanup']['unverified_member_files_removed'] == 2
    assert result['integrity'][0]['cleanup']['prior_outputs_touched'] is False
    assert sentinel.read_bytes() == b'GENERATED_OLD_OUTPUT_MUST_SURVIVE'


def test_late_descriptor_crc_failure_closes_then_removes_both_unverified_spools(tmp_path, monkeypatch):
    q = inputs(tmp_path, zip_fault='descriptor_crc')
    mutate_generated_flags(q, options=6, utf8=True)
    output = Path(q['output_root'])
    owned_paths = {str(output / 'CT.nii.gz'), str(output / 'CT.nii')}
    tracked_paths = owned_paths | {q['targets'][0]['archive']['path']}
    descriptors = []
    os_open, unlink = os.open, Path.unlink
    removed = []

    def track_open(path, *args, **kwargs):
        fd = os_open(path, *args, **kwargs)
        if not isinstance(path, int) and os.fspath(path) in tracked_paths:
            descriptors.append(fd)
        return fd

    def check_closed_before_unlink(path, *args, **kwargs):
        if str(path) in owned_paths:
            for fd in descriptors:
                with pytest.raises(OSError):
                    os.fstat(fd)
            removed.append(str(path))
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, 'open', track_open)
    monkeypatch.setattr(Path, 'unlink', check_closed_before_unlink)
    result = qualification.run(q)
    assert result['status'] == 'REJECT'
    assert 'ZIP_DESCRIPTOR_CRC_SIZE' in result_text(result).upper()
    assert set(removed) == owned_paths
    assert len(descriptors) == 3
    assert result['integrity'][0]['cleanup']['unverified_member_files_removed'] == 2
    assert not (output / 'INFECTION_MASK.nii.gz').exists()
    assert (output / 'RECEIPT.json').exists()
