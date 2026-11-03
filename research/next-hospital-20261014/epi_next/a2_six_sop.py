"""Versioned exact-six header/conditional JPEG lossless decode; no model API."""
import argparse
import copy
import importlib.metadata
import json
import math
import os
from pathlib import Path
import resource
import struct
import sys
import time

from . import a1_prepare as old, a1_file_meta_v2 as meta
from .a0_acquire import bound_json, exclusive, phase, publish, secure_parent

JPEG = '1.2.840.10008.1.2.4.70'
PREVIOUS_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
EXCLUDE = {'PatientID', 'IssuerOfPatientID', 'InstanceNumber', 'TemporalPositionIdentifier', 'SpacingBetweenSlices'}
FIELDS = set(old.FIELD_VR) - EXCLUDE
A = {'compressed_input_bytes': 2*1024**2, 'inflated_header_prefix_bytes_per_member': 128*1024,
     'inflated_header_prefix_bytes_total': 768*1024, 'output_bytes_total': 512*1024,
     'RSS_stop_bytes': 256*1024**2, 'wall_seconds': 60,
     'element_count_per_member': 4096, 'whitelist_value_bytes_per_element': 4096}
B = {'compressed_input_bytes': 2*1024**2, 'inflated_member_bytes_per_member': 1024**2,
     'inflated_member_bytes_total': 2*1024**2, 'output_bytes_total': 64*1024**2,
     'RSS_stop_bytes': 512*1024**2, 'wall_seconds': 120, 'per_SOP_wall_seconds': 20,
     'rows_max': 1024, 'columns_max': 1024, 'decoded_pixel_bytes_per_SOP_max': 2*1024**2,
     'native_output_bytes_per_SOP_max': 8*1024**2, 'QA_PNG_count_max': 6,
     'QA_PNG_bytes_total_max': 6*1024**2}
OVERALL = {'wall_seconds': 210, 'cleanup_reserve_seconds': 30,
           'disk_free_floor_bytes': 4*1024**3, 'CPU_threads': 1, 'max_attempts': 1}


class Budget(old.Budget):
    def report(self):
        result = super().report()
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        result['observed_process_peak_RSS_bytes'] = rss if sys.platform == 'darwin' else rss*1024
        result['elapsed_seconds'] = time.monotonic() - self.start
        return result


def header(stream, source, allowed):
    try:
        info = meta.parse_file_meta(stream, source, dict(meta.CAPS,
                                   inflated_header_prefix_bytes_per_member=A['inflated_header_prefix_bytes_per_member']))
    except meta.HeaderError as exc:
        if str(exc) != 'UNSUPPORTED_TRANSFER_SYNTAX' or exc.metadata['values'].get('TransferSyntaxUID') != JPEG:
            raise
        info = exc.metadata
    if info['values'].get('TransferSyntaxUID') != JPEG:
        raise meta.HeaderError('EXACT_JPEG_LOSSLESS_SYNTAX_REQUIRED', info)

    def fail(reason):
        info.update(consumed_prefix_bytes=stream.emitted, prefix_sha256=stream.hash.hexdigest())
        raise meta.HeaderError(reason, info)

    try:
        for _ in range(A['element_count_per_member']):
            offset = stream.emitted
            info['last_element_offset'] = offset
            tag = struct.unpack('<HH', stream.read(4))
            if tag[0] == 2:
                fail('FILE_META_AFTER_DECLARED_BOUNDARY')
            try:
                vr = stream.read(2).decode('ascii')
            except UnicodeError:
                fail('INVALID_DATASET_VR')
            if vr not in old.VRS:
                fail('INVALID_DATASET_VR')
            if vr in old.LONG_VR:
                if stream.read(2) != b'\0\0':
                    fail('DATASET_VR_RESERVED')
                n = struct.unpack('<I', stream.read(4))[0]
            else:
                n = struct.unpack('<H', stream.read(2))[0]
            if tag in old.PIXELS:
                if tag != (0x7fe0, 0x0010) or vr not in ('OB', 'OW') or n != 0xffffffff:
                    fail('ENCAPSULATED_INTEGER_PIXEL_HEADER_REQUIRED')
                info.update(pixel_value_offset=stream.emitted, pixel_length=n,
                            consumed_prefix_bytes=stream.emitted, prefix_sha256=stream.hash.hexdigest())
                return info
            if n == 0xffffffff or vr in ('SQ', 'UN'):
                fail('UNSUPPORTED_CONTAINER_BEFORE_PIXELS')
            if n % 2:
                fail('ODD_DATASET_VALUE_LENGTH')
            key = allowed.get(tag)
            if key:
                if key in info['values']:
                    fail('DUPLICATE_WHITELIST_FIELD')
                if n > A['whitelist_value_bytes_per_element']:
                    raise old.GuardError('WHITELIST_VALUE_LIMIT')
                if vr != old.FIELD_VR[key] and not (key.startswith('PixelPadding') and vr in ('SS', 'US')):
                    fail('WHITELIST_VR_MISMATCH')
                value_offset = stream.emitted
                value = old.field_value(stream.read(n), vr, key, info['values'])
                info['values'][key] = value
                info['field_offsets'][key] = {'element_offset': offset, 'value_offset': value_offset, 'value_bytes': n}
            else:
                stream.skip(n)  # discarded scalar bytes, not clinical interpretation
        fail('DATASET_ELEMENT_LIMIT')
    except meta.HeaderError:
        raise
    except old.HeaderError as exc:
        fail(str(exc))


def geometry(info):
    import numpy as np
    v = info['values']
    for key in ('SOPInstanceUID', 'StudyInstanceUID', 'SeriesInstanceUID', 'FrameOfReferenceUID'):
        if not v.get(key):
            raise old.HeaderError('MISSING_' + key)
    if v.get('SOPClassUID') != old.CT or v.get('MediaStorageSOPClassUID') != old.CT or v.get('Modality') != 'CT':
        raise old.HeaderError('CLASSIC_CT_REQUIRED')
    if v.get('MediaStorageSOPInstanceUID', v['SOPInstanceUID']) != v['SOPInstanceUID']:
        raise old.HeaderError('FILE_META_DATASET_SOP_MISMATCH')
    if v.get('SamplesPerPixel') != 1 or v.get('NumberOfFrames', 1) != 1 or v.get('PhotometricInterpretation') != 'MONOCHROME2':
        raise old.HeaderError('SINGLE_FRAME_MONOCHROME_REQUIRED')
    if any(s in v.get('ImageType', '').upper().split('\\') for s in ('SCOUT', 'LOCALIZER')):
        raise old.HeaderError('LOCALIZER')
    if not 2 <= v.get('Rows', 0) <= B['rows_max'] or not 2 <= v.get('Columns', 0) <= B['columns_max']:
        raise old.HeaderError('MATRIX_LIMIT')
    if v.get('BitsAllocated') not in (8, 16) or not 0 < v.get('BitsStored', 0) <= v['BitsAllocated'] or v.get('HighBit') != v['BitsStored']-1 or v.get('PixelRepresentation') not in (0, 1):
        raise old.HeaderError('PIXEL_BITS')
    orient = np.asarray(v.get('ImageOrientationPatient'), dtype=float)
    pos = np.asarray(v.get('ImagePositionPatient'), dtype=float)
    spacing = np.asarray(v.get('PixelSpacing'), dtype=float)
    if orient.shape != (6,) or pos.shape != (3,) or spacing.shape != (2,) or not all(np.isfinite(a).all() for a in (orient, pos, spacing)):
        raise old.HeaderError('MISSING_OR_INVALID_2D_GEOMETRY')
    if abs(np.linalg.norm(orient[:3])-1) > 1e-4 or abs(np.linalg.norm(orient[3:])-1) > 1e-4 or abs(orient[:3]@orient[3:]) > 1e-4:
        raise old.HeaderError('ORIENTATION')
    if np.any(spacing <= 0) or np.any(spacing > 10):
        raise old.HeaderError('PIXEL_SPACING')
    if 'RescaleSlope' in v and (v['RescaleSlope'] is None or v['RescaleSlope'] == 0):
        raise old.HeaderError('RESCALE_SLOPE')
    if 'RescaleIntercept' in v and v['RescaleIntercept'] is None:
        raise old.HeaderError('RESCALE_INTERCEPT')
    return {'status': 'NATIVE_SINGLE_SOP_2D_TECHNICAL_PASS', 'rows': v['Rows'], 'columns': v['Columns'],
            'row_column_spacing_mm': spacing.tolist(), 'IPP': pos.tolist(), 'IOP': orient.tolist(),
            'actual_inter_slice_spacing': 'UNKNOWN_SINGLE_SOP', 'stack_sorting': 'NOT_EVALUATED',
            'patient_independence': 'UNKNOWN', 'resampling': 'NONE'}


def discover(request, out):
    archive = old.open_bound_archive(request)
    budget = Budget(A)
    allowed = {tuple(int(x, 16) for x in f['tag'].split(',')): f['keyword'] for f in request['field_value_whitelist']}
    rows = []
    for selected in request['selection']:
        member = selected['member']
        stream = old.Member(archive, member, budget, A['inflated_header_prefix_bytes_per_member'], request['source_archive'])
        row = {'candidate_id': selected['candidate_id'], 'member': member, 'status': 'QUARANTINED'}
        try:
            try:
                row['header'] = header(stream, {'candidate_id': selected['candidate_id'], 'member': member}, allowed)
                row['geometry'] = geometry(row['header'])
                row['status'] = 'ELIGIBLE_SINGLE_SOP'
            except meta.HeaderError as exc:
                row.update(reason=str(exc), header=exc.metadata)
            except old.HeaderError as exc:
                row['reason'] = str(exc)
        finally:
            stream.close()
        rows.append(row)
    ids = [r['header']['values'].get('SOPInstanceUID') for r in rows if r['status'] == 'ELIGIBLE_SINGLE_SOP']
    conflict = len(ids) != len(set(ids))
    value = {'rows': rows, 'eligible': [] if conflict else [r['candidate_id'] for r in rows if r['status'] == 'ELIGIBLE_SINGLE_SOP'],
             'duplicate_SOP_batch_blocked': conflict, 'pixel_values_emitted': 0}
    path = Path(out)/'a2a-headers.json'
    digest = old.json_output(path, value, budget)
    return {'path': str(path), 'sha256': digest, 'budget': budget.report(), 'eligible': value['eligible'], 'batch_blocked': conflict}


def encapsulated(stream):
    parts = []
    for i in range(1024):
        data = stream.read(8)
        group, element, length = struct.unpack('<HHI', data)
        if (group, element) == (0xfffe, 0xe0dd):
            if length != 0 or i < 2:
                raise old.HeaderError('BAD_PIXEL_SEQUENCE_DELIMITER')
            return b''.join(parts)
        if (group, element) != (0xfffe, 0xe000) or length == 0xffffffff or length % 2:
            raise old.HeaderError('BAD_PIXEL_FRAGMENT')
        if i == 0 and length not in (0, 4):
            raise old.HeaderError('SINGLE_FRAME_BASIC_OFFSET_TABLE')
        if i == 0:
            value = stream.read(length)
            if value not in (b'', b'\0'*4):
                raise old.HeaderError('BASIC_OFFSET_NOT_ZERO')
        else:
            if length < 2:
                raise old.HeaderError('EMPTY_PIXEL_FRAGMENT')
            value = stream.read(length)
        parts.append(data+value)
    raise old.HeaderError('PIXEL_FRAGMENT_LIMIT')


def validate_jpeg_frame(frame, values):
    if frame[:2] != b'\xff\xd8':
        raise old.HeaderError('JPEG_SOI_REQUIRED')
    offset = 2
    sof = None
    while offset < len(frame):
        if frame[offset] != 255:
            raise old.HeaderError('JPEG_HEADER_MARKER')
        while offset < len(frame) and frame[offset] == 255:
            offset += 1
        if offset >= len(frame):
            raise old.HeaderError('JPEG_HEADER_SHORT')
        marker = frame[offset]; offset += 1
        if offset+2 > len(frame):
            raise old.HeaderError('JPEG_SEGMENT_SHORT')
        length = struct.unpack_from('>H', frame, offset)[0]
        if length < 2 or offset+length > len(frame):
            raise old.HeaderError('JPEG_SEGMENT_LENGTH')
        payload = frame[offset+2:offset+length]; offset += length
        if marker in range(0xc0, 0xd0) and marker not in (0xc4, 0xc8, 0xcc):
            if marker != 0xc3 or sof is not None or len(payload) != 9:
                raise old.HeaderError('JPEG_SINGLE_COMPONENT_SOF3_REQUIRED')
            precision, height, width, components = struct.unpack_from('>BHHB', payload)
            if precision != values['BitsStored']:
                raise old.HeaderError('JPEG_DATASET_PRECISION_MISMATCH')
            if (height, width, components) != (values['Rows'], values['Columns'], 1) or payload[7:] != b'\x11\0':
                raise old.HeaderError('JPEG_DATASET_MATRIX_OR_COMPONENT_MISMATCH')
            sof = payload[6]
        if marker == 0xda:
            if sof is None or len(payload) != 6 or payload[:2] != bytes([1, sof]) or payload[2] & 15 or payload[3:] != b'\1\0\0':
                raise old.HeaderError('JPEG_SV1_SINGLE_SCAN_PREDICTOR_REQUIRED')
            while offset < len(frame):
                if frame[offset] != 255:
                    offset += 1; continue
                offset += 1
                while offset < len(frame) and frame[offset] == 255:
                    offset += 1
                if offset >= len(frame):
                    break
                marker = frame[offset]; offset += 1
                if marker == 0 or 0xd0 <= marker <= 0xd7:
                    continue
                if marker == 0xd9 and frame[offset:] in (b'', b'\0'):
                    return
                raise old.HeaderError('JPEG_TRAILING_OR_UNSUPPORTED_SCAN')
            raise old.HeaderError('JPEG_EOI_REQUIRED')
    raise old.HeaderError('JPEG_SOS_REQUIRED')


def decode_pixels(values, payload):
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.pixels import get_decoder
    from pydicom.encaps import generate_frames
    frames = iter(generate_frames(payload, number_of_frames=1))
    frame = next(frames)
    if next(frames, None) is not None:
        raise old.HeaderError('MULTIPLE_ENCAPSULATED_FRAMES')
    validate_jpeg_frame(frame, values)
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = JPEG
    for key in ('Rows', 'Columns', 'SamplesPerPixel', 'PhotometricInterpretation', 'BitsAllocated', 'BitsStored', 'HighBit', 'PixelRepresentation', 'NumberOfFrames'):
        if key in values:
            setattr(ds, key, values[key])
    ds.PixelData = payload
    # Explicit single existing plugin; no fallback/install or generic dcmread.
    array, properties = get_decoder(JPEG).as_array(ds, decoding_plugin='pylibjpeg')
    if array.shape != (values['Rows'], values['Columns']) or array.nbytes > B['decoded_pixel_bytes_per_SOP_max']:
        raise old.HeaderError('DECODED_SHAPE_OR_SIZE')
    if array.dtype.itemsize != values['BitsAllocated']//8 or array.dtype.kind != ('i' if values['PixelRepresentation'] else 'u'):
        raise old.HeaderError('DECODED_DTYPE')
    if properties['bits_allocated'] != values['BitsAllocated'] or properties['bits_stored'] != values['BitsStored']:
        raise old.HeaderError('JPEG_DATASET_PRECISION_MISMATCH')
    return array


def decode_case(request, row, out, remaining):
    import numpy as np
    from PIL import Image
    import io
    caps = dict(B, **remaining)
    caps['wall_seconds'] = B['per_SOP_wall_seconds']
    budget = Budget(caps)
    archive = old.open_bound_archive(request)
    allowed = {tuple(int(x, 16) for x in f['tag'].split(',')): f['keyword'] for f in request['field_value_whitelist']}
    stream = old.Member(archive, row['member'], budget, B['inflated_member_bytes_per_member'], request['source_archive'])
    try:
        h = header(stream, row['header']['source'], allowed)
        if h != row['header']:
            raise old.GuardError('HEADER_REPLAY_DRIFT')
        payload = encapsulated(stream)
        source_digest = stream.finish()  # CRC/size/SHA; uninterpreted tail discarded
    finally:
        stream.close()
    array = decode_pixels(h['values'], payload)
    budget.check()
    values = h['values']
    paths = []
    directory = Path(out)/row['candidate_id']
    directory.mkdir(mode=0o700)
    native_bytes = 0
    def save_array(name, a):
        nonlocal native_bytes
        buffer = io.BytesIO()
        np.save(buffer, a, allow_pickle=False)
        raw = buffer.getvalue()
        native_bytes += len(raw)
        if native_bytes > B['native_output_bytes_per_SOP_max']:
            raise old.GuardError('NATIVE_OUTPUT_LIMIT')
        budget.count('output', len(raw))
        p = directory/(name+'.npy.part')
        with os.fdopen(exclusive(p), 'wb') as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
        paths.append(p)
    save_array('native-stored', array)
    units = 'UNKNOWN'
    display = array.astype(np.float32)
    if values.get('RescaleSlope') is not None and values.get('RescaleIntercept') is not None:
        display = display*np.float32(values['RescaleSlope'])+np.float32(values['RescaleIntercept'])
        if not np.isfinite(display).all():
            raise old.HeaderError('NONFINITE_RESCALED_PIXELS')
        save_array('native-rescaled', display)
        units = 'HU' if values.get('RescaleType') == 'HU' else 'UNKNOWN'
    low, high = (-1350., 150.) if units == 'HU' else (float(display.min()), float(display.max()))
    image = np.rint(np.clip((display-low)/max(high-low, 1), 0, 1)*255).astype(np.uint8)
    buffer = io.BytesIO(); Image.fromarray(image).save(buffer, format='PNG'); png = buffer.getvalue()
    if len(png) > caps['QA_PNG_bytes_total_max']:
        raise old.GuardError('QA_PNG_BYTES_LIMIT')
    budget.count('output', len(png))
    p = directory/'native-qa.png.part'
    with os.fdopen(exclusive(p), 'wb') as f:
        f.write(png); f.flush(); os.fsync(f.fileno())
    paths.append(p)
    value = {'candidate_id': row['candidate_id'], 'header': h, 'geometry': row['geometry'],
             'source_DICOM_sha256': source_digest, 'units': units, 'window': [low, high],
             'decoder_plugin': 'pylibjpeg', 'no_resampling': True, 'patient_independence': 'UNKNOWN',
             'training_eligible': False, 'artifacts': [{'part_path': str(p), 'final_path': str(p)[:-5], 'sha256': old.sha(p)} for p in paths]}
    manifest = directory/'case.json'
    old.json_output(manifest, value, budget, publish_now=False)
    return {'candidate_id': row['candidate_id'], 'manifest_part': str(manifest)+'.part', 'manifest': value,
            'budget': budget.report(), 'qa_png_bytes': len(png)}


def pipeline(request, out, permit_decode):
    started = time.monotonic()
    out = Path(out); secure_parent(out); out.mkdir(mode=0o700, exist_ok=False)
    receipt = {'status': 'FAILED', 'attempts': 1, 'model_calls': 0}
    try:
        result = phase(discover, (request, str(out)), A['wall_seconds'], started+OVERALL['wall_seconds'], out, OVERALL['disk_free_floor_bytes'])
        receipt['A2a'] = result
        if not permit_decode:
            receipt['status'] = 'A2A_COMPLETE_A2B_NOT_APPROVED'; return receipt
        if result['batch_blocked']:
            receipt['status'] = 'A2B_BLOCKED_DUPLICATE_SOP'; return receipt
        discovery = bound_json(result['path'], result['sha256'])
        used = {'compressed_input_bytes': 0, 'inflated_member_bytes_total': 0, 'output_bytes_total': 128*1024, 'QA_PNG_bytes_total_max': 0}
        cases = []; b_start = time.monotonic()
        for row in discovery['rows']:
            if row['candidate_id'] not in result['eligible']:
                continue
            seconds = min(B['per_SOP_wall_seconds'], B['wall_seconds']-(time.monotonic()-b_start))
            if seconds <= 0:
                raise old.GuardError('A2B_STAGE_TIMEOUT')
            case = phase(decode_case, (request, row, str(out), {k: B[k]-n for k, n in used.items()}), seconds, started+OVERALL['wall_seconds'], out, OVERALL['disk_free_floor_bytes'])
            cases.append(case)
            for field, report in (('compressed_input_bytes', 'compressed_input_bytes'), ('inflated_member_bytes_total', 'inflated_bytes'), ('output_bytes_total', 'output_bytes')):
                used[field] += case['budget'][report]
            used['QA_PNG_bytes_total_max'] += case['qa_png_bytes']
        control = Budget(dict(B, output_bytes_total=96*1024))
        canonical = {'status': 'COMPLETE_ELIGIBLE_SINGLE_SOP_SUBSET' if cases else 'NO_ELIGIBLE_SOP',
                     'cases': [{'candidate_id': c['candidate_id'], 'manifest_path': c['manifest_part'][:-5], 'budget': c['budget']} for c in cases],
                     'excluded': [{'candidate_id': r['candidate_id'], 'reason': r.get('reason')} for r in discovery['rows'] if r['candidate_id'] not in result['eligible']],
                     'patient_independence': 'UNKNOWN', 'training_eligible': False, '3D_geometry_QA': 'NOT_EVALUATED_SINGLE_SOP'}
        old.json_output(out/'canonical.json', canonical, control, publish_now=False)
        for c in cases:
            for item in c['manifest']['artifacts']:
                if time.monotonic() > started+OVERALL['wall_seconds']-12:
                    raise old.GuardError('PUBLICATION_DEADLINE')
                publish(item['part_path'], item['final_path'])
            publish(c['manifest_part'], c['manifest_part'][:-5])
        publish(out/'canonical.json.part', out/'canonical.json')
        receipt.update(status=canonical['status'], A2b={'decoded_SOP_count': len(cases), 'budget_with_control_reserve': used,
                       'canonical_sha256': old.sha(out/'canonical.json')})
    except Exception as exc:
        receipt['failure'] = type(exc).__name__+':'+str(exc)[:160]
    finally:
        receipt['elapsed_seconds'] = time.monotonic()-started
    return receipt


def validate(request):
    previous = bound_json(request['previous_request_path'], PREVIOUS_SHA)
    original = bound_json(previous['original_request_path'], old.APPLICATION_SHA)
    expected = [f for f in original['requests'][0]['field_value_whitelist'] if f['keyword'] in FIELDS]
    if request['selection'] != previous['selection'] or request['source_archive'] != previous['source_archive'] or request['inventory_binding'] != previous['inventory_binding']:
        raise old.GuardError('EXACT_SIX_PREVIOUS_BINDING_REQUIRED')
    if request['field_value_whitelist'] != expected or request['A2a_caps'] != A or request['A2b_caps'] != B or request['overall_caps'] != OVERALL:
        raise old.GuardError('EXACT_SCOPE_CAPS_FIELDS_REQUIRED')
    if request['models_permitted'] is not False or request['new_codecs_permitted'] is not False:
        raise old.GuardError('NO_MODELS_NO_INSTALL_REQUIRED')


def main():
    parser = argparse.ArgumentParser()
    for flag in ('request', 'request-sha256', 'readiness', 'readiness-sha256'):
        parser.add_argument('--'+flag, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--approval'); parser.add_argument('--approval-sha256')
    args = parser.parse_args()
    request = bound_json(args.request, args.request_sha256)
    binding = bound_json(args.readiness, args.readiness_sha256)
    old.verify_readiness(binding)
    required = {str(Path(__file__).resolve()), str(Path(meta.__file__).resolve())}
    if not required.issubset({str(Path(i['path']).resolve()) for i in binding['source_bindings']}):
        raise old.GuardError('NEW_A2_SOURCE_BINDING_REQUIRED')
    for package, version in binding['decoder_distributions'].items():
        if importlib.metadata.version(package) != version:
            raise old.GuardError('DECODER_VERSION_DRIFT')
    for i in binding['decoder_module_bindings']:
        loaded = importlib.import_module(i['module'])
        if Path(loaded.__file__).resolve() != Path(i['path']).resolve() or old.sha(i['path']) != i['sha256']:
            raise old.GuardError('DECODER_MODULE_DRIFT')
    for i in binding['decoder_binary_bindings']:
        if old.sha(i['path']) != i['sha256']:
            raise old.GuardError('DECODER_BINARY_DRIFT')
    if binding['request_sha256'] != args.request_sha256:
        raise old.GuardError('READINESS_REQUEST_MISMATCH')
    validate(request)
    if not args.execute:
        print(json.dumps({'status': 'CHECK_ONLY_NO_ARCHIVE_MEMBER_ACCESS'})); return
    if not args.approval or not args.approval_sha256:
        raise old.GuardError('NEW_EXACT_A2_APPROVAL_REQUIRED')
    approval = bound_json(args.approval, args.approval_sha256)
    expected = {'request_sha256': args.request_sha256, 'readiness_sha256': args.readiness_sha256,
                'permit_A2a': True, 'permit_model': False, 'permit_new_codecs': False}
    if any(type(approval.get(k)) is not type(v) or approval.get(k) != v for k, v in expected.items()) or type(approval.get('permit_A2b')) is not bool:
        raise old.GuardError('A2_ITEMIZED_APPROVAL_REQUIRED')
    if any(os.environ.get(k) != '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS')):
        raise old.GuardError('ONE_THREAD_ENV_REQUIRED')
    receipt = pipeline(request, request['output_root'], approval['permit_A2b'])
    receipt.update(request_sha256=args.request_sha256, readiness_sha256=args.readiness_sha256, approval_sha256=args.approval_sha256)
    raw = old.encoded(receipt)
    if len(raw) > 32768:
        raise old.GuardError('RECEIPT_LIMIT')
    with os.fdopen(exclusive(Path(request['output_root'])/'receipt.json'), 'wb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    print(json.dumps({'status': receipt['status']}))
    if receipt['status'] in ('FAILED', 'A2B_BLOCKED_DUPLICATE_SOP'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
