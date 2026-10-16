"""Versioned six-member file-meta probe; legacy A1 source stays unchanged."""
import argparse
import copy
import json
import os
from pathlib import Path
import struct
import sys
import time

from . import a1_prepare as legacy
from .a0_acquire import bound_json, exclusive, phase, secure_parent

META_FIELDS = {
    (0x0002, 0x0002): 'MediaStorageSOPClassUID',
    (0x0002, 0x0003): 'MediaStorageSOPInstanceUID',
    (0x0002, 0x0010): 'TransferSyntaxUID',
}
CAPS = {
    'members': 6,
    'compressed_input_bytes': 1024 * 1024,
    'inflated_header_prefix_bytes_per_member': 64 * 1024,
    'inflated_header_prefix_bytes_total': 384 * 1024,
    'element_count_per_member': 128,
    'whitelist_value_bytes_per_element': 64,
    'output_bytes_total': 32 * 1024,
    'RSS_stop_bytes': 256 * 1024 * 1024,
    'wall_seconds': 60,
    'disk_free_floor_bytes': 4 * 1024**3,
}


class HeaderError(legacy.HeaderError):
    """Failure plus validated fields/offsets, never unvalidated raw values."""
    def __init__(self, reason, metadata):
        super().__init__(reason)
        self.metadata = copy.deepcopy(metadata)


def parse_file_meta(stream, source, caps):
    metadata = {'source': copy.deepcopy(source), 'values': {}, 'field_offsets': {},
                'declared_file_meta_end_offset': None, 'last_element_offset': None}

    def fail(reason):
        metadata.update(consumed_prefix_bytes=stream.emitted,
                        prefix_sha256=stream.hash.hexdigest())
        raise HeaderError(reason, metadata)

    def read(n, end=None):
        if end is not None and stream.emitted + n > end:
            fail('FILE_META_ELEMENT_EXCEEDS_DECLARED_END')
        data = stream.read(n)
        if len(data) != n:
            fail('FILE_META_SHORT_READ')
        return data

    try:
        if read(132)[128:] != b'DICM':
            fail('DICM_REQUIRED_NO_FORCE')
        metadata['last_element_offset'] = stream.emitted
        # Group length is mandatory here: never look ahead into a dataset to
        # discover a boundary. Missing/invalid length is rejected, not guessed.
        if struct.unpack('<HH', read(4)) != (0x0002, 0x0000):
            fail('FILE_META_GROUP_LENGTH_REQUIRED')
        if read(4) != b'UL\x04\x00':
            fail('FILE_META_GROUP_LENGTH_VR_OR_LENGTH')
        length = struct.unpack('<I', read(4))[0]
        end = stream.emitted + length
        metadata['declared_file_meta_end_offset'] = end
        if end > caps['inflated_header_prefix_bytes_per_member'] or length < 8:
            fail('FILE_META_DECLARED_LENGTH_LIMIT')
        count = 0
        while stream.emitted < end:
            count += 1
            if count > caps['element_count_per_member']:
                fail('FILE_META_ELEMENT_COUNT_LIMIT')
            element_offset = stream.emitted
            metadata['last_element_offset'] = element_offset
            tag = struct.unpack('<HH', read(4, end))
            if tag[0] != 0x0002 or tag == (0x0002, 0x0000):
                fail('NON_FILE_META_OR_DUPLICATE_GROUP_LENGTH')
            try:
                vr = read(2, end).decode('ascii')
            except UnicodeError:
                fail('FILE_META_INVALID_VR')
            if vr not in legacy.VRS:
                fail('FILE_META_INVALID_VR')
            if vr in legacy.LONG_VR:
                if read(2, end) != b'\x00\x00':
                    fail('FILE_META_VR_RESERVED')
                n = struct.unpack('<I', read(4, end))[0]
            else:
                n = struct.unpack('<H', read(2, end))[0]
            value_offset = stream.emitted
            if n == 0xffffffff or vr in ('SQ', 'UN'):
                fail('FILE_META_UNSUPPORTED_STRUCTURE')
            if n % 2 or value_offset + n > end:
                fail('FILE_META_VALUE_LENGTH')
            key = META_FIELDS.get(tag)
            if key:
                if key in metadata['values']:
                    fail('DUPLICATE_FILE_META_FIELD')
                if vr != 'UI' or n > caps['whitelist_value_bytes_per_element']:
                    fail('FILE_META_FIELD_VR_OR_SIZE')
                value = legacy.field_value(read(n, end), vr, key, metadata['values'])
                # Only values which passed the legacy UID validation are saved.
                metadata['values'][key] = value
                metadata['field_offsets'][key] = {
                    'element_offset': element_offset, 'value_offset': value_offset,
                    'value_bytes': n}
            else:
                read(n, end)  # discarded structural file-meta bytes, no decoding
        if 'TransferSyntaxUID' not in metadata['values']:
            fail('MISSING_TRANSFER_SYNTAX')
        if metadata['values']['TransferSyntaxUID'] not in legacy.SYNTAXES:
            fail('UNSUPPORTED_TRANSFER_SYNTAX')
        metadata.update(consumed_prefix_bytes=stream.emitted,
                        prefix_sha256=stream.hash.hexdigest())
        return metadata
    except HeaderError:
        raise
    except legacy.HeaderError as exc:
        fail(str(exc))


def validate_request(request):
    original = bound_json(request['original_request_path'], legacy.APPLICATION_SHA)
    if request['original_request_sha256'] != legacy.APPLICATION_SHA:
        raise legacy.GuardError('ORIGINAL_APPLICATION_MISMATCH')
    selected = [{'candidate_id': c['candidate_id'], 'directory': c['directory'],
                 'member_order_index': 0, 'member': c['members'][0]}
                for c in original['candidates']]
    if len(selected) != 6 or request['selection'] != selected:
        raise legacy.GuardError('EXACT_SIX_FIRST_MEMBERS_REQUIRED')
    if any(not c['member']['name'].lower().endswith('.dcm') for c in selected):
        raise legacy.GuardError('SELECTED_MEMBER_NOT_DICOM')
    if request['caps'] != CAPS or request['overall_wall_seconds'] != 90:
        raise legacy.GuardError('EXACT_PROBE_CAPS_REQUIRED')
    for key in ('source_archive', 'inventory_binding'):
        if request[key] != original[key]:
            raise legacy.GuardError('ORIGINAL_SOURCE_BINDING_REQUIRED')
    if request['pixel_values_permitted'] is not False or request['models_permitted'] is not False:
        raise legacy.GuardError('FILE_META_ONLY_REQUIRED')
    return original


def probe(request, out):
    caps = request['caps']
    budget = legacy.Budget(caps)
    archive = legacy.open_bound_archive(request)
    rows = []
    for selected in request['selection']:
        row = selected['member']
        source = {'archive_sha256': request['source_archive']['sha256'],
                  'candidate_id': selected['candidate_id'], 'member': row}
        stream = legacy.Member(archive, row, budget,
                               caps['inflated_header_prefix_bytes_per_member'],
                               request['source_archive'])
        try:
            try:
                metadata = parse_file_meta(stream, source, caps)
                rows.append({'status': 'SUPPORTED_BY_A1_V1', 'metadata': metadata})
            except HeaderError as exc:
                rows.append({'status': 'FILE_META_DIAGNOSTIC_FAILURE',
                             'reason': str(exc), 'metadata': exc.metadata})
        finally:
            stream.close()
    result = {'status': 'SIX_FILE_META_PROBE_COMPLETE', 'members': rows,
              'pixel_values_emitted': 0, 'model_calls': 0,
              'dataset_values_parsed': 0,
              'budget_before_report_write': budget.report()}
    path = Path(out) / 'file-meta-results.json'
    digest = legacy.json_output(path, result, budget)
    return {'status': result['status'], 'path': str(path), 'sha256': digest,
            'budget': budget.report(), 'member_count': len(rows)}


def main():
    parser = argparse.ArgumentParser()
    for flag in ('request', 'request-sha256', 'readiness', 'readiness-sha256'):
        parser.add_argument('--' + flag, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--approval')
    parser.add_argument('--approval-sha256')
    args = parser.parse_args()
    request = bound_json(args.request, args.request_sha256)
    binding = bound_json(args.readiness, args.readiness_sha256)
    legacy.verify_readiness(binding)
    here = Path(__file__).resolve()
    if not any(Path(i['path']).resolve() == here and i['sha256'] == legacy.sha(here)
               for i in binding['source_bindings']):
        raise legacy.GuardError('NEW_PROBE_SOURCE_BINDING_REQUIRED')
    if binding['request_sha256'] != args.request_sha256:
        raise legacy.GuardError('READINESS_REQUEST_MISMATCH')
    validate_request(request)  # reads only saved application JSON
    if not args.execute:
        print(json.dumps({'status': 'CHECK_ONLY_NO_ARCHIVE_MEMBER_ACCESS'}))
        return
    if not args.approval or not args.approval_sha256:
        raise legacy.GuardError('NEW_EXACT_PROBE_APPROVAL_REQUIRED')
    approval = bound_json(args.approval, args.approval_sha256)
    expected = {'request_sha256': args.request_sha256,
                'readiness_sha256': args.readiness_sha256,
                'permit_exact_six_file_meta_probe': True,
                'permit_pixel_values': False, 'permit_model': False}
    if any(type(approval.get(k)) is not type(v) or approval.get(k) != v
           for k, v in expected.items()):
        raise legacy.GuardError('NEW_PROBE_APPROVAL_SCOPE_MISMATCH')
    out = Path(request['output_root'])
    secure_parent(out)
    out.mkdir(mode=0o700, exist_ok=False)
    started = time.monotonic()
    receipt = {'status': 'FAILED', 'attempts': 1, 'request_sha256': args.request_sha256,
               'readiness_sha256': args.readiness_sha256,
               'approval_sha256': args.approval_sha256, 'model_calls': 0}
    try:
        receipt['result'] = phase(probe, (request, str(out)), CAPS['wall_seconds'],
                                  started + request['overall_wall_seconds'], out,
                                  CAPS['disk_free_floor_bytes'])
        receipt['status'] = 'SIX_FILE_META_PROBE_COMPLETE'
    except Exception as exc:
        receipt['failure'] = type(exc).__name__ + ':' + str(exc)[:160]
    receipt['elapsed_seconds'] = time.monotonic() - started
    raw = legacy.encoded(receipt)
    if len(raw) > 8192:
        raise legacy.GuardError('PROBE_RECEIPT_LIMIT')
    with os.fdopen(exclusive(out / 'receipt.json'), 'wb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    print(json.dumps({'status': receipt['status']}))
    if receipt['status'] == 'FAILED':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
