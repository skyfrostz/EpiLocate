"""Bounded Classic CT selected-field audit. No raw headers/UIDs in output.
Not a complete CT IOD validator. Frozen v1 remains unchanged.
"""
import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import struct
import time
from . import a2_six_sop as v1
from .a0_acquire import bound_json, exclusive, phase, secure_parent

old = v1.old
A, B, OVERALL = dict(v1.A), dict(v1.B), dict(v1.OVERALL)
RESOURCE_CODES = {'WALL_LIMIT','RSS_LIMIT','COMPRESSED_LIMIT','INFLATED_LIMIT','OUTPUT_LIMIT'}
SAFE_PIPELINE_CODES = RESOURCE_CODES | {'DISK_RESERVE','PHASE_OR_OVERALL_TIMEOUT','DECODE_STAGE_TIMEOUT','PUBLICATION_DEADLINE','NATIVE_OUTPUT_LIMIT','QA_PNG_LIMIT','HEADER_REPLAY_DRIFT','NONFINITE_RESCALED_PIXELS','MEMBER_CRC_MISMATCH','ARCHIVE_STAT_DRIFT','ARCHIVE_OPEN_STAT_DRIFT','PROVENANCE_DRIFT','ZIP_MEMBER_BOUNDS','LOCAL_CENTRAL_MISMATCH','LOCAL_CENTRAL_SIZE_CRC','SELECTED_FIELD_RULES_FAILED'}
TRUNCATION_CODES = {'ZIP_SHORT_READ','STORED_MEMBER_SHORT','DEFLATE_SHORT','DEFLATE_NO_END'}
BOUNDARY_CODES = {'INFLATED_PREFIX_OR_SIZE_LIMIT','DEFLATE_OVERSIZE','DEFLATE_TRAILING_DATA'}
PARENT_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
# Type values apply only in the named module/context. LOCAL is not an IOD Type.
RULES = {
 'MediaStorageSOPClassUID': ('1', 'PS3.10-7.1'),
 'MediaStorageSOPInstanceUID': ('1', 'PS3.10-7.1'),
 'TransferSyntaxUID': ('1', 'PS3.10-7.1'),
 'SpecificCharacterSet': ('1C', 'PS3.3-C.12.1'),
 'ImageType': ('1', 'PS3.3-C.8.2.1'),
 'SOPClassUID': ('1', 'PS3.3-C.12.1'),
 'SOPInstanceUID': ('1', 'PS3.3-C.12.1'),
 'Modality': ('1', 'PS3.3-C.7.3.1'),
 'SliceThickness': ('2', 'PS3.3-C.7.6.2'),
 'StudyInstanceUID': ('1', 'PS3.3-C.7.2.1'),
 'SeriesInstanceUID': ('1', 'PS3.3-C.7.3.1'),
 'ImagePositionPatient': ('1', 'PS3.3-C.7.6.2'),
 'ImageOrientationPatient': ('1', 'PS3.3-C.7.6.2'),
 'FrameOfReferenceUID': ('1', 'PS3.3-C.7.4.1'),
 'SamplesPerPixel': ('1', 'PS3.3-C.7.6.3'),
 'PhotometricInterpretation': ('1', 'PS3.3-C.7.6.3'),
 'NumberOfFrames': ('LOCAL', 'SINGLE_FRAME_SCOPE_NOT_IOD_TYPE'),
 'Rows': ('1', 'PS3.3-C.7.6.3'), 'Columns': ('1', 'PS3.3-C.7.6.3'),
 'PixelSpacing': ('1', 'PS3.3-C.7.6.2'),
 'BitsAllocated': ('1', 'PS3.3-C.7.6.3'), 'BitsStored': ('1', 'PS3.3-C.7.6.3'),
 'HighBit': ('1', 'PS3.3-C.7.6.3'), 'PixelRepresentation': ('1', 'PS3.3-C.7.6.3'),
 'PixelPaddingValue': ('1C', 'PS3.3-C.7.5.1'),
 'PixelPaddingRangeLimit': ('1C', 'PS3.3-C.7.6.3'),
 'RescaleIntercept': ('1', 'PS3.3-C.8.2.1'), 'RescaleSlope': ('1', 'PS3.3-C.8.2.1'),
 'RescaleType': ('1C', 'PS3.3-C.8.2.1'),
}
assert set(RULES) == v1.FIELDS

class DiagnosticError(ValueError):
    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        super().__init__(diagnostic['reason_code'])  # never include rejected data


def context(member, domain, tag=None, keyword=None, vr=None, vl=None, offset=None, consumed=0, sequence=()):
    return {'anonymous_member': member, 'domain': domain, 'sequence_path': list(sequence),
            'tag': None if tag is None else '%04X,%04X' % tag, 'keyword': keyword,
            'VR': vr, 'declared_VL': vl, 'element_offset': offset,
            'consumed_prefix_bytes': consumed}


def reject(ctx, reason, rule):
    raise DiagnosticError(dict(ctx, reason_code=reason, rule_id=rule))


def required_value(raw, present, kind, condition, ctx, rule):
    """Type semantics independent of VR. UNKNOWN conditional never passes."""
    if kind in ('1C', '2C'):
        if condition is None:
            reject(ctx, 'CONDITION_UNKNOWN', rule)
        if condition:
            kind = kind[0]
        else:
            kind = '3'  # this bounded profile permits optional presence
    if not present and kind in ('1', '2'):
        reject(ctx, 'REQUIRED_FIELD_ABSENT', rule)
    if present and kind == '1' and not raw:
        reject(ctx, 'TYPE1_EMPTY', rule)


def uid_value(raw, present, kind, condition, ctx, rule):
    required_value(raw, present, kind, condition, ctx, rule)
    if not present or not raw:
        return None
    if len(raw) > 64:
        reject(ctx, 'UID_LENGTH_EXCEEDS_64', 'PS3.5-9.1')
    data = raw[:-1] if raw.endswith(b'\0') else raw
    if raw.endswith(b'\0') and len(data) % 2 != 1:
        reject(ctx, 'UID_INVALID_PADDING', 'PS3.5-6.2')
    if re.fullmatch(rb'(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))*', data) is None:
        reject(ctx, 'UID_SYNTAX_INVALID', 'PS3.5-9.1')
    return data.decode('ascii')


def parse(stream, member, allowed):
    values, diagnostics, seen = {}, [], set()
    failures = []
    current = context(member, 'meta', consumed=stream.emitted)
    count = 0
    def fail(reason, rule='BOUNDED_STRUCTURE_V2'):
        reject(dict(current, consumed_prefix_bytes=stream.emitted, previous_diagnostics=diagnostics, validation_failures=failures), reason, rule)
    def read_failure(exc):
        code = str(exc)
        if isinstance(exc, old.GuardError) and code in RESOURCE_CODES | TRUNCATION_CODES | BOUNDARY_CODES:
            current['failure_class'] = 'resource_stop' if code in RESOURCE_CODES else ('truncation' if code in TRUNCATION_CODES else 'boundary_or_prefix_limit')
            fail(code)
        current['failure_class'] = 'truncation' if isinstance(exc, old.HeaderError) else 'unclassified_guard_stop'
        fail('HEADER_READ_TRUNCATED' if isinstance(exc, old.HeaderError) else 'UNCLASSIFIED_READ_GUARD_STOP')
    def read(n, end=None):
        if end is not None and stream.emitted+n > end:
            fail('ELEMENT_EXCEEDS_CONTEXT_BOUNDARY')
        try:
            return stream.read(n)
        except (old.GuardError, old.HeaderError) as exc:
            read_failure(exc)
    def element(domain, end=None):
        nonlocal current, count
        count += 1
        current = context(member, domain, offset=stream.emitted, consumed=stream.emitted)
        if count > A['element_count_per_member']:
            fail('ELEMENT_COUNT_LIMIT')
        tag = struct.unpack('<HH', read(4, end))
        key = allowed.get(tag)
        current.update(tag='%04X,%04X' % tag, keyword=key)
        rawvr = read(2, end)
        try:
            vr = rawvr.decode('ascii')
        except UnicodeError:
            fail('VR_ENCODING_INVALID')
        current['VR'] = vr
        if vr not in old.VRS:
            fail('VR_UNSUPPORTED')
        if vr in old.LONG_VR:
            if read(2, end) != b'\0\0':
                fail('VR_RESERVED_BYTES_INVALID')
            n = struct.unpack('<I', read(4, end))[0]
        else:
            n = struct.unpack('<H', read(2, end))[0]
        current.update(declared_VL=n, consumed_prefix_bytes=stream.emitted)
        return tag, key, vr, n
    def scalar(tag, key, vr, n, end=None):
        if vr in ('SQ', 'UN') or n == 0xffffffff:
            if vr == 'SQ':
                current.update(sequence_path=[current['tag']], domain=current['domain']+'/sequence')
            fail('CONTAINER_NOT_SUPPORTED_NO_VALUE_READ')
        if n % 2:
            fail('ODD_VALUE_LENGTH', 'PS3.5-7.1')
        if end is not None and stream.emitted+n > end:
            fail('ELEMENT_EXCEEDS_CONTEXT_BOUNDARY')
        if not key:
            # Scalar values outside whitelist never decoded or logged.
            try:
                stream.skip(n)
            except (old.HeaderError, old.GuardError) as exc:
                read_failure(exc)
            return
        if key in seen:
            fail('DUPLICATE_WHITELIST_FIELD')
        seen.add(key)
        if vr != old.FIELD_VR[key] and not (key.startswith('PixelPadding') and vr in ('SS', 'US')):
            fail('WHITELIST_VR_MISMATCH')
        if n > A['whitelist_value_bytes_per_element']:
            fail('WHITELIST_VALUE_LIMIT')
        raw = read(n, end)
        ctx = dict(current, consumed_prefix_bytes=stream.emitted)
        kind, rule = RULES[key]
        # Presence with a nonempty value satisfies the requirement independently
        # of the condition; absent/empty conditional fields resolve at end.
        conditional = True if kind.endswith('C') and raw else None
        if vr == 'UI':
            try:
                value = uid_value(raw, True, kind, conditional, ctx, rule)
            except DiagnosticError as exc:
                failures.append(exc.diagnostic); diagnostics.append(exc.diagnostic)
                values[key] = None
                return  # finite scalar boundary known; qualification stays rejected
        else:
            trimmed = raw.rstrip(b' \0') if vr not in old.NUMERIC else raw
            if kind.endswith('C') and not trimmed:
                value = None  # defer until all selected facts available
            else:
                try:
                    required_value(trimmed, True, kind, conditional, ctx, rule)
                    value = old.field_value(raw, vr, key, values) if raw else None
                except DiagnosticError as exc:
                    failures.append(exc.diagnostic); diagnostics.append(exc.diagnostic)
                    values[key] = None; return
                except old.HeaderError:
                    event = dict(ctx, reason_code='FIELD_VALUE_INVALID', rule_id=rule)
                    failures.append(event); diagnostics.append(event)
                    values[key] = None; return
        values[key] = value
        diagnostics.append(dict(ctx, reason_code='PRESENT_EMPTY' if value is None else 'FIELD_VALUE_VALID', rule_id=rule))
    if read(132)[128:] != b'DICM':
        fail('DICM_REQUIRED_NO_FORCE')
    tag, key, vr, n = element('meta')
    if tag != (2, 0) or vr != 'UL' or n != 4:
        fail('FILE_META_GROUP_LENGTH_REQUIRED')
    end = stream.emitted+4+struct.unpack('<I', read(4))[0]
    if end > A['inflated_header_prefix_bytes_per_member'] or end < stream.emitted:
        fail('FILE_META_BOUNDARY_LIMIT')
    while stream.emitted < end:
        tag, key, vr, n = element('meta', end)
        if tag[0] != 2 or tag == (2, 0):
            fail('FILE_META_CONTEXT_TAG_INVALID')
        scalar(tag, key, vr, n, end)
    for key in v1.meta.META_FIELDS.values():
        if key not in values:
            failures.append(dict(context(member, 'meta', keyword=key, consumed=stream.emitted), reason_code='REQUIRED_FIELD_ABSENT', rule_id=RULES[key][1]))
    if values.get('TransferSyntaxUID') != v1.JPEG:
        fail('EXACT_JPEG_LOSSLESS_SYNTAX_REQUIRED', 'TECHNICAL_PROFILE_V2')
    while True:
        tag, key, vr, n = element('dataset')
        if tag[0] == 2:
            fail('FILE_META_AFTER_BOUNDARY')
        if tag in old.PIXELS:
            if tag != (0x7fe0, 0x0010) or vr not in ('OB', 'OW') or n != 0xffffffff:
                fail('ENCAPSULATED_PIXEL_HEADER_REQUIRED')
            break  # do not read PixelData value
        scalar(tag, key, vr, n)
    for key, (kind, rule) in RULES.items():
        if key in v1.meta.META_FIELDS.values() or kind == 'LOCAL':
            continue
        value = values.get(key)
        condition = None
        if kind.endswith('C'):
            if value is not None and value != '':
                condition = True
            elif key in ('PixelPaddingValue', 'PixelPaddingRangeLimit'):
                # No encoded padding means no padding defined; present-but-empty
                # or range with missing value is indeterminate/rejected.
                condition = False if not any(k in values for k in ('PixelPaddingValue','PixelPaddingRangeLimit')) else None
            # charset expansion and output units are not inferred from skipped
            # values/unknown Multi-energy CT Acquisition; missing => UNKNOWN.
        ctx = context(member, 'dataset', keyword=key, consumed=stream.emitted)
        try:
            required_value(b'X' if value is not None and value != '' else b'', key in values, kind, condition, ctx, rule)
        except DiagnosticError as exc:
            failures.append(exc.diagnostic)
    if 'PixelPaddingRangeLimit' in values and 'PixelPaddingValue' not in values:
        fail('PADDING_RANGE_REQUIRES_VALUE', 'PS3.3-C.7.6.3')
    if failures:
        raise DiagnosticError(dict(context(member, 'dataset', consumed=stream.emitted), reason_code='SELECTED_FIELD_RULES_FAILED', rule_id='CT_SELECTED_PROFILE_V2', validation_failures=failures, previous_diagnostics=diagnostics))
    if values['MediaStorageSOPClassUID'] != values['SOPClassUID'] or values['MediaStorageSOPInstanceUID'] != values['SOPInstanceUID']:
        fail('FILE_META_DATASET_UID_MISMATCH', 'TECHNICAL_PROFILE_V2')
    try:
        geom = v1.geometry({'values': values})
    except old.HeaderError:
        fail('NATIVE_2D_TECHNICAL_QA_REJECTED', 'TECHNICAL_PROFILE_V2')
    return {'values': values, 'diagnostics': diagnostics, 'geometry': geom,
            'prefix_sha256': stream.hash.hexdigest(), 'consumed_prefix_bytes': stream.emitted}


def allowed_fields(request):
    return {tuple(int(x, 16) for x in f['tag'].split(',')): f['keyword'] for f in request['field_value_whitelist']}


def discover(request, out):
    budget = v1.Budget(A)
    archive = old.open_bound_archive(request)
    rows = []; global_stop = False
    for selected in request['selection']:
        stream = old.Member(archive, selected['member'], budget, A['inflated_header_prefix_bytes_per_member'], request['source_archive'])
        row = {'anonymous_member': selected['candidate_id'], 'status': 'QUARANTINED'}
        try:
            h = parse(stream, selected['candidate_id'], allowed_fields(request))
            row.update(status='ELIGIBLE_SELECTED_FIELD_TECHNICAL_PROFILE', diagnostics=h['diagnostics'],
                       geometry=h['geometry'], SOP_fingerprint=hashlib.sha256(h['values']['SOPInstanceUID'].encode()).hexdigest())
        except DiagnosticError as exc:
            row['diagnostic'] = exc.diagnostic
            global_stop = exc.diagnostic.get('failure_class') in ('resource_stop','unclassified_guard_stop')
        finally:
            row.update(consumed_prefix_bytes=stream.emitted, prefix_sha256=stream.hash.hexdigest())
            stream.close()
        rows.append(row)
        if global_stop: break
    eligible = [r for r in rows if r['status'].startswith('ELIGIBLE')]
    duplicate = len({r['SOP_fingerprint'] for r in eligible}) != len(eligible)
    obj = {'rows': rows, 'global_stop':global_stop, 'eligible': [] if duplicate or global_stop else [r['anonymous_member'] for r in eligible],
           'duplicate_SOP_batch_blocked': duplicate, 'full_IOD_conformance': 'NOT_EVALUATED', 'pixel_values_emitted': 0}
    # Return only sanitized data to the parent so a stopped worker need not
    # exceed its own wall/RSS budget just to preserve stop diagnostics.
    return {'data':obj, 'budget':budget.report(), 'eligible':obj['eligible'],
            'batch_blocked':duplicate, 'global_stop':global_stop}


def decode_case(request, row, out, remaining):
    import io
    import numpy as np
    from PIL import Image
    selected = next(s for s in request['selection'] if s['candidate_id'] == row['anonymous_member'])
    budget = v1.Budget(dict(B, **remaining, wall_seconds=B['per_SOP_wall_seconds']))
    stream = old.Member(old.open_bound_archive(request), selected['member'], budget, B['inflated_member_bytes_per_member'], request['source_archive'])
    try:
        h = parse(stream, row['anonymous_member'], allowed_fields(request))
        if h['prefix_sha256'] != row['prefix_sha256'] or h['consumed_prefix_bytes'] != row['consumed_prefix_bytes']:
            raise old.GuardError('HEADER_REPLAY_DRIFT')
        payload = v1.encapsulated(stream)
        source_sha = stream.finish()
    finally:
        stream.close()
    stored = v1.decode_pixels(h['values'], payload)
    values = h['values']
    rescaled = stored.astype(np.float32)*np.float32(values['RescaleSlope'])+np.float32(values['RescaleIntercept'])
    if not np.isfinite(rescaled).all():
        raise old.GuardError('NONFINITE_RESCALED_PIXELS')
    budget.check()
    directory = Path(out)/row['anonymous_member']; directory.mkdir(mode=0o700)
    artifacts = []
    native_bytes = 0
    for name, arr in (('native-stored', stored), ('native-rescaled', rescaled)):
        b = io.BytesIO(); np.save(b, arr, allow_pickle=False); raw = b.getvalue()
        native_bytes += len(raw)
        if native_bytes > B['native_output_bytes_per_SOP_max']:
            raise old.GuardError('NATIVE_OUTPUT_LIMIT')
        budget.count('output', len(raw)); p = directory/(name+'.npy.part')
        with os.fdopen(exclusive(p), 'wb') as f: f.write(raw)
        artifacts.append({'name': p.name[:-5], 'bytes': len(raw), 'sha256': old.sha(p)})
    units = 'HU' if values.get('RescaleType') == 'HU' else 'UNKNOWN'
    low, high = (-1350., 150.) if units == 'HU' else (float(rescaled.min()), float(rescaled.max()))
    img = np.rint(np.clip((rescaled-low)/max(high-low,1),0,1)*255).astype(np.uint8)
    b = io.BytesIO(); Image.fromarray(img).save(b, format='PNG'); raw = b.getvalue()
    if len(raw) > remaining['QA_PNG_bytes_total_max']: raise old.GuardError('QA_PNG_LIMIT')
    budget.count('output',len(raw)); p = directory/'native-qa.png.part'
    with os.fdopen(exclusive(p),'wb') as f: f.write(raw)
    artifacts.append({'name': p.name[:-5], 'bytes':len(raw),'sha256':old.sha(p)})
    manifest = {'anonymous_member':row['anonymous_member'],'source_sha256':source_sha,'geometry':h['geometry'],
                'units':units,'window':[low,high],'artifacts':artifacts,'CRC':'PASS','no_resampling':True,
                'training_eligible':False,'full_IOD_conformance':'NOT_EVALUATED'}
    old.json_output(directory/'case.json',manifest,budget,publish_now=False)
    return {'anonymous_member':row['anonymous_member'],'budget':budget.report(),'qa_png_bytes':len(raw)}


def pipeline(request, out, permit_decode):
    start = time.monotonic(); out = Path(out); secure_parent(out); out.mkdir(mode=0o700,exist_ok=False)
    receipt = {'status':'FAILED','attempts':1,'model_calls':0,'decoded_SOP_count':0}
    try:
        a = phase(discover,(request,str(out)),A['wall_seconds'],start+OVERALL['wall_seconds'],out,OVERALL['disk_free_floor_bytes'])
        control=v1.Budget(A)
        diagnostic_path=out/'diagnostics.json'
        diagnostic_sha=old.json_output(diagnostic_path,a.pop('data'),control)
        a.update(path=str(diagnostic_path),sha256=diagnostic_sha,control_output_bytes=control.report()['output_bytes'])
        receipt['diagnosis'] = a
        if a['global_stop']: receipt['status']='DIAGNOSIS_RESOURCE_STOP'; return receipt
        if not permit_decode: receipt['status']='DIAGNOSIS_COMPLETE_DECODE_NOT_APPROVED'; return receipt
        if a['batch_blocked']: receipt['status']='DUPLICATE_SOP_BATCH_BLOCKED'; return receipt
        d = bound_json(a['path'],a['sha256'])
        used = {'compressed_input_bytes':0,'inflated_member_bytes_total':0,'output_bytes_total':131072,'QA_PNG_bytes_total_max':0}
        decoded=[]; bstart=time.monotonic()
        for row in d['rows']:
            if row['anonymous_member'] not in a['eligible']: continue
            seconds=min(B['per_SOP_wall_seconds'],B['wall_seconds']-(time.monotonic()-bstart))
            if seconds<=0: raise old.GuardError('DECODE_STAGE_TIMEOUT')
            c=phase(decode_case,(request,row,str(out),{k:B[k]-n for k,n in used.items()}),seconds,start+OVERALL['wall_seconds'],out,OVERALL['disk_free_floor_bytes'])
            decoded.append(c)
            for k,r in (('compressed_input_bytes','compressed_input_bytes'),('inflated_member_bytes_total','inflated_bytes'),('output_bytes_total','output_bytes')): used[k]+=c['budget'][r]
            used['QA_PNG_bytes_total_max']+=c['qa_png_bytes']
        for row in decoded:
            for name in ('native-stored.npy','native-rescaled.npy','native-qa.png','case.json'):
                if time.monotonic()>start+OVERALL['wall_seconds']-12: raise old.GuardError('PUBLICATION_DEADLINE')
                target=out/row['anonymous_member']/name
                v1.publish(str(target)+'.part',str(target))
        receipt.update(status='COMPLETE_TECHNICAL_SUBSET' if decoded else 'NO_ELIGIBLE_SOP',decoded_SOP_count=len(decoded),decode_budget_with_control_reserve=used,decoded=decoded)
    except Exception as exc:
        # External decoder exceptions may contain sensitive data. No str(exc).
        receipt['failure_type']=type(exc).__name__
        code=str(exc)
        if code.startswith(('PHASE_FAILED:GuardError:','PHASE_FAILED:HeaderError:','PHASE_FAILED:DiagnosticError:')):
            code=code.split(':',2)[2]
        receipt['reason_code']=code if code in SAFE_PIPELINE_CODES | TRUNCATION_CODES | BOUNDARY_CODES else 'BOUNDED_PIPELINE_FAILURE'
    finally: receipt['elapsed_seconds']=time.monotonic()-start
    return receipt


def validate(request):
    parent=bound_json(request['parent_request_path'],PARENT_SHA)
    for key in ('selection','source_archive','inventory_binding','field_value_whitelist'):
        if request[key]!=parent[key]: raise old.GuardError('FIXED_SIX_SCOPE_DRIFT')
    if request['diagnosis_caps']!=A or request['decode_caps']!=B or request['overall_caps']!=OVERALL:
        raise old.GuardError('CAPS_DRIFT')
    if request['rules']!={k:list(v) for k,v in RULES.items()} or request['schema']!='A2_DIAGNOSTIC_V2': raise old.GuardError('RULE_SCOPE_DRIFT')
    if request['models_permitted'] is not False or request['new_codecs_permitted'] is not False: raise old.GuardError('NO_MODEL_NO_INSTALL')


def main():
    p=argparse.ArgumentParser()
    for flag in ('request','request-sha256','readiness','readiness-sha256'):p.add_argument('--'+flag,required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--approval');p.add_argument('--approval-sha256')
    args=p.parse_args();request=bound_json(args.request,args.request_sha256);binding=bound_json(args.readiness,args.readiness_sha256)
    old.verify_readiness(binding)
    required={str(Path(m.__file__).resolve()) for m in (v1,v1.meta,importlib.import_module(__name__))}
    if not required.issubset({str(Path(i['path']).resolve()) for i in binding['source_bindings']}):raise old.GuardError('V2_SOURCE_BINDING_REQUIRED')
    if binding['request_sha256']!=args.request_sha256:raise old.GuardError('REQUEST_READINESS_DRIFT')
    for package,version in binding['decoder_distributions'].items():
        if importlib.metadata.version(package)!=version:raise old.GuardError('DECODER_VERSION_DRIFT')
    for i in binding['decoder_module_bindings']:
        m=importlib.import_module(i['module'])
        if Path(m.__file__).resolve()!=Path(i['path']).resolve() or old.sha(i['path'])!=i['sha256']:raise old.GuardError('DECODER_MODULE_DRIFT')
    for i in binding['decoder_binary_bindings']:
        if old.sha(i['path'])!=i['sha256']:raise old.GuardError('DECODER_BINARY_DRIFT')
    validate(request)
    if not args.execute:print(json.dumps({'status':'CHECK_ONLY_NO_ARCHIVE_MEMBER_ACCESS'}));return
    if not args.approval or not args.approval_sha256:raise old.GuardError('NEW_V2_APPROVAL_REQUIRED')
    a=bound_json(args.approval,args.approval_sha256)
    expected={'schema':'A2_DIAGNOSTIC_V2_APPROVAL','request_sha256':args.request_sha256,'readiness_sha256':args.readiness_sha256,'permit_diagnosis':True,'permit_model':False,'permit_new_codecs':False}
    if any(type(a.get(k)) is not type(v) or a.get(k)!=v for k,v in expected.items()) or type(a.get('permit_conditional_decode')) is not bool:raise old.GuardError('NEW_ITEMIZED_APPROVAL_REQUIRED')
    if any(os.environ.get(k)!='1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')):raise old.GuardError('ONE_THREAD_REQUIRED')
    r=pipeline(request,request['output_root'],a['permit_conditional_decode']);r.update(request_sha256=args.request_sha256,readiness_sha256=args.readiness_sha256,approval_sha256=args.approval_sha256)
    b=old.encoded(r)
    if len(b)>32768:raise old.GuardError('RECEIPT_LIMIT')
    with os.fdopen(exclusive(Path(request['output_root'])/'receipt.json'),'wb') as f:f.write(b)
    print(json.dumps({'status':r['status']}))
    if r['status'] in ('FAILED','DUPLICATE_SOP_BATCH_BLOCKED','DIAGNOSIS_RESOURCE_STOP'):raise SystemExit(1)

if __name__=='__main__': main()
