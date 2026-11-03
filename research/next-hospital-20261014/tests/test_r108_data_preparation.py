"""New generated HTTP/ZIP/registry fixtures only; no network or saved payloads."""
import copy
import hashlib
import io
import json
import struct
import zipfile
import pytest

from epi_next import r108_zip_structure as z
from epi_next import r108_medical_registry as m


URL = 'https://example.invalid/api/records/3757476/files/GENERATED.zip/content'


class Headers:
    def __init__(self, values):
        self.values = values
    def items(self):
        return self.values


class Response:
    def __init__(self, body, headers, status=206, url=URL):
        self.body = io.BytesIO(body); self.headers = Headers(headers)
        self.status = status; self.url = url; self.length = len(body); self.read_calls = 0
    def geturl(self):
        return self.url
    def read(self, n):
        self.read_calls += 1; raw = self.body.read(n); self.length -= len(raw); return raw
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.body.close()


class Server:
    def __init__(self, archive, change=None):
        self.archive = archive; self.change = change; self.calls = []; self.responses = []
    def __call__(self, url, method, headers, timeout):
        assert url == URL and headers['Accept-Encoding'] == 'identity' and 0 < timeout <= 10
        self.calls.append((method, headers.copy()))
        if method == 'HEAD':
            r = Response(b'', [('Content-Length', str(len(self.archive))), ('ETag', '"GENERATED"'), ('Accept-Ranges', 'bytes')], 200)
        else:
            assert headers['If-Match'] == '"GENERATED"'
            start, end = map(int, headers['Range'][6:].split('-'))
            body = self.archive[start:end+1]
            r = Response(body, [('Content-Length', str(len(body))), ('ETag', '"GENERATED"'),
                               ('Content-Range', f'bytes {start}-{end}/{len(self.archive)}')])
        if self.change:
            self.change(r, len(self.calls))
        self.responses.append(r); return r


def classic(name='generated.nii', payload=b'GENERATED' * 40):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_STORED) as f:
        f.writestr(name, payload)
    return out.getvalue()


def make_zip64():
    raw = classic(); end = struct.unpack('<4s4H2IH', raw[-22:]); offset, length = end[6], end[5]
    start = len(raw)-22
    record = struct.pack('<4sQ2H2I4Q', b'PK\x06\x06', 44, 3*256+45, 45, 0, 0, 1, 1, length, offset)
    locator = struct.pack('<4sIQI', b'PK\x06\x07', 0, start, 1)
    eocd = struct.pack('<4s4H2IH', b'PK\x05\x06', 0, 0, 65535, 65535, 0xffffffff, 0xffffffff, 0)
    return raw[:-22] + record + locator + eocd


def request(raw):
    return dict(source=dict(url=URL, bytes=len(raw)))


@pytest.mark.parametrize('factory,ranges', [(classic, 2), (make_zip64, 3)])
def test_generated_classic_zip64_exact_structure_ranges(factory, ranges):
    raw = factory(); server = Server(raw); result = z.preflight(request(raw), server)
    assert result['Range_requests'] == ranges and result['HEAD_requests'] == 1
    assert result['members'][0]['name'] == 'generated.nii'
    assert result['medical_denominator'] is None and not result['member_bodies_read']
    assert not result['full_archive_checksum_verified'] and not result['decompression']
    plan = result['plan']; intervals = [tuple(map(int, h['Range'][6:].split('-'))) for method,h in server.calls if method == 'GET']
    assert intervals[0] == (len(raw)-42, len(raw)-1)
    assert intervals[-1] == (plan['offset'], plan['offset']+plan['length']-1)
    assert all(start >= plan['offset'] for start,end in intervals)
    assert result['body_bytes'] == 42 + plan['length'] + (56 if ranges == 3 else 0)
    assert server.responses[0].read_calls == 0


@pytest.mark.parametrize('fault,needle', [
    ('200', 'HTTP_STATUS'), ('redirect', 'RESPONSE_URL'), ('etag', 'ETAG_DRIFT'),
    ('range', 'CONTENT_RANGE'), ('length', 'RANGE_LENGTH'), ('gzip', 'CONTENT_ENCODING'),
    ('chunked', 'TRANSFER_ENCODING'), ('duplicate', 'DUPLICATE_HTTP_HEADER')])
def test_range_header_failures_stop_before_body(fault, needle):
    def change(r, n):
        if n != 2: return
        if fault == '200': r.status = 200
        elif fault == 'redirect': r.url = URL + '?redirected'
        else:
            key, value = {'etag': ('ETag', '"CHANGED"'), 'range': ('Content-Range', 'bytes 0-1/2'),
                'length': ('Content-Length', '999999999'), 'gzip': ('Content-Encoding', 'gzip'),
                'chunked': ('Transfer-Encoding', 'chunked'), 'duplicate': ('Content-Length', '42')}[fault]
            if fault != 'duplicate': r.headers.values = [(k,v) for k,v in r.headers.values if k.lower() != key.lower()]
            r.headers.values.append((key, value))
    raw = classic(); server = Server(raw, change)
    with pytest.raises(ValueError, match=needle): z.preflight(request(raw), server)
    assert len(server.calls) == 2 and server.responses[-1].read_calls == 0


@pytest.mark.parametrize('etag', [None, 'W/"weak"', 'unquoted', '"bad\nvalue"'])
def test_missing_or_weak_head_identity_no_range(etag):
    def change(r, n):
        if n == 1:
            r.headers.values = [(k,v) for k,v in r.headers.values if k != 'ETag']
            if etag is not None: r.headers.values.append(('ETag', etag))
    raw = classic(); server = Server(raw, change)
    with pytest.raises(ValueError, match='STRONG_ETAG'): z.preflight(request(raw), server)
    assert len(server.calls) == 1 and server.responses[0].read_calls == 0


def test_truncated_body_and_framed_eof_fail_stop():
    raw = classic()
    def change(r, n):
        if n == 2: r.body = io.BytesIO(b'X')
    with pytest.raises(ValueError, match='TRUNCATED'): z.preflight(request(raw), Server(raw, change))
    def non_eof(r, n):
        if n == 2: r.length += 1
    with pytest.raises(ValueError, match='EOF_UNPROVEN'): z.preflight(request(raw), Server(raw, non_eof))


def test_redirect_handler_closes_without_drain():
    class Stream:
        closed=False
        def read(self,*_):pytest.fail('redirect must not drain')
        def close(self):self.closed=True
    fp=Stream()
    with pytest.raises(ValueError,match='REDIRECT_FORBIDDEN'):
        z.NoRedirect().redirect_request(None,fp,302,'generated',{},URL)
    assert fp.closed


@pytest.mark.parametrize('name', ['../bad', '/absolute', 'C:/drive', 'a\\b', 'a/./b'])
def test_unsafe_member_path_rejected(name):
    raw = classic(name)
    with pytest.raises(ValueError, match='PATH_TRAVERSAL'): z.preflight(request(raw), Server(raw))


def test_zip_bomb_and_count_and_zip64_extension_rejected():
    raw = bytearray(classic()); cd = struct.unpack('<4s4H2IH', raw[-22:])[6]
    struct.pack_into('<I', raw, cd+24, 0xffffffff-1)
    with pytest.raises(ValueError, match='ZIP_BOMB'): z.preflight(request(raw), Server(raw))
    raw = bytearray(classic()); struct.pack_into('<HH', raw, len(raw)-14, 2, 2)
    with pytest.raises(ValueError, match='CENTRAL_EOF'): z.preflight(request(raw), Server(raw))
    raw = bytearray(make_zip64()); struct.pack_into('<Q', raw, len(raw)-98+4, 45)
    with pytest.raises(ValueError, match='ZIP64_RECORD'): z.preflight(request(raw), Server(raw))


def test_generated_zip64_member_extra_and_encryption_rejection():
    raw=classic();end=list(struct.unpack('<4s4H2IH',raw[-22:]));cd=end[6]
    h=list(struct.unpack('<4s6H3I5H2I',raw[cd:cd+46]));name=raw[cd+46:cd+46+h[10]]
    extra=struct.pack('<HH3Q',1,24,h[9],h[8],h[16])
    h[2]=45;h[8]=h[9]=h[16]=0xffffffff;h[11]=len(extra)
    directory=struct.pack('<4s6H3I5H2I',*h)+name+extra;end[5]=len(directory)
    generated=raw[:cd]+directory+struct.pack('<4s4H2IH',*end)
    result=z.preflight(request(generated),Server(generated))
    assert result['members'][0]['header_offset']==0 and result['members'][0]['uncompressed_bytes']==360
    encrypted=bytearray(generated);struct.pack_into('<H',encrypted,cd+8,1)
    with pytest.raises(ValueError,match='ENCRYPTION_FLAGS'):z.preflight(request(encrypted),Server(encrypted))


def test_footer_multidisk_comment_and_directory_budget_stop():
    raw = bytearray(classic()); struct.pack_into('<H', raw, len(raw)-18, 1)
    with pytest.raises(ValueError, match='MULTIDISK'): z.footer_plan(bytes(raw[-42:]), len(raw))
    raw = bytearray(classic()); struct.pack_into('<H', raw, len(raw)-2, 1)
    with pytest.raises(ValueError, match='COMMENT'): z.footer_plan(bytes(raw[-42:]), len(raw))
    raw = bytearray(classic()); struct.pack_into('<I', raw, len(raw)-10, z.CAPS['central_directory_bytes']+1)
    with pytest.raises(ValueError, match='CENTRAL_LIMIT'): z.footer_plan(bytes(raw[-42:]), len(raw))
    budget = z.Budget(); budget.ranges = 3
    with pytest.raises(ValueError, match='RANGE_BUDGET'): z.fetch_range(request(raw)['source'], '"GENERATED"', 0, 1, budget, lambda *_: pytest.fail('network'))


def test_failure_receipt_is_exclusive_and_has_partial_cost(tmp_path, monkeypatch):
    raw = classic(); server = Server(raw, lambda r,n: setattr(r,'status',200) if n==2 else None)
    monkeypatch.setattr(z, 'http_open', server)
    q = dict(request(raw), output_root=str(tmp_path/'out'))
    with pytest.raises(ValueError, match='HTTP_STATUS'): z.execute(q, 'GENERATED', None)
    receipt = json.loads((tmp_path/'out/RECEIPT.json').read_text())
    assert receipt['status'] == 'FAILED_STOP_NO_RETRY' and receipt['Range_requests'] == 1 and receipt['body_bytes'] == 0
    with pytest.raises(FileExistsError): z.execute(q, 'GENERATED', None)


def test_cli_check_only_has_no_http_and_source_metadata_binding(tmp_path, monkeypatch, capsys):
    source = dict(url=URL, key='GENERATED.zip', bytes=100, record_id=3757476,
                  version='Verson 1.0', checksum='md5:'+'a'*32)
    p = tmp_path/'metadata.json'
    p.write_text(json.dumps(dict(id=3757476, metadata=dict(version='Verson 1.0'), files=[
        dict(key=source['key'], size=100, checksum=source['checksum'], links=dict(self=URL))])))
    q = dict(schema=z.SCHEMA, caps=z.CAPS, algorithm=z.ALGORITHM, source=source,
        source_bindings=[], runtime_sha256=z.digest(z.sys.executable), package_versions={},
        metadata_binding=dict(path=str(p),sha256=z.digest(p)),
        spec=dict(device='cpu',max_forward=0,max_backward=0,timeout_seconds=60))
    qp=tmp_path/'request.json';qp.write_text(json.dumps(q))
    monkeypatch.setattr(z.sys,'argv',['generated','--request',str(qp),'--sha256',z.digest(qp)])
    monkeypatch.setattr(z,'http_open',lambda *_:pytest.fail('HTTP forbidden'))
    z.main();assert json.loads(capsys.readouterr().out)['status']=='CHECK_ONLY_NO_HTTP_OR_PAYLOAD'
    q['source']['bytes']=101
    with pytest.raises(ValueError,match='METADATA_SOURCE_DRIFT'):z.validate_request(q)


@pytest.mark.parametrize('fail_first', [False, True])
def test_bundle_two_archives_serial_and_first_failure_stops_second(tmp_path, monkeypatch, fail_first):
    raw=classic();server=Server(raw, lambda r,n:setattr(r,'status',200) if fail_first and n==2 else None)
    monkeypatch.setattr(z,'http_open',server)
    monkeypatch.setattr(z,'validate_request',lambda _:None)
    components=[]
    for role,directory in [('CT','ct'),('INFECTION','infection')]:
        q=dict(request(raw),output_root=str(tmp_path/'out'/directory))
        p=tmp_path/(directory+'.json');p.write_text(json.dumps(q))
        components.append(dict(role=role,request=dict(path=str(p),sha256=z.digest(p))))
    q=dict(output_root=str(tmp_path/'out'),components=components)
    if fail_first:
        with pytest.raises(ValueError,match='HTTP_STATUS'):z.execute_bundle(q,'GENERATED',None)
        assert not (tmp_path/'out/infection').exists() and len(server.calls)==2
    else:
        z.execute_bundle(q,'GENERATED',None)
        assert len(server.calls)==6 and [c[0] for c in server.calls]==['HEAD','GET','GET']*2
    r=json.loads((tmp_path/'out/BUNDLE_RECEIPT.json').read_text())
    assert r['medical_denominator'] is None and r['attempted']==(['CT'] if fail_first else ['CT','INFECTION'])


def test_exact_bundle_control_check_only_and_component_cannot_execute(tmp_path, monkeypatch, capsys):
    metadata=dict(id=3757476,metadata=dict(version='Verson 1.0'),files=[])
    names=['COVID-19-CT-Seg_20cases.zip','Infection_Mask.zip']
    for name in names:
        metadata['files'].append(dict(key=name,size=100,checksum='md5:'+'a'*32,
            links=dict(self='https://example.invalid/api/records/3757476/files/'+name+'/content')))
    mp=tmp_path/'meta.json';mp.write_text(json.dumps(metadata))
    common=dict(source_commit='a'*40,source_bindings=[],runtime_sha256=z.digest(z.sys.executable),package_versions={},supervisor={})
    components=[]
    for f,role,directory in zip(metadata['files'],('CT','INFECTION'),('ct','infection')):
        q=dict(common,schema=z.SCHEMA,caps=z.CAPS,algorithm=z.ALGORITHM,bundle_only=True,
            source=dict(key=f['key'],url=f['links']['self'],bytes=100,record_id=3757476,version='Verson 1.0',checksum=f['checksum']),
            metadata_binding=dict(path=str(mp),sha256=z.digest(mp)),output_root=str(tmp_path/'out'/directory),
            spec=dict(device='cpu',max_forward=0,max_backward=0,timeout_seconds=60))
        p=tmp_path/(directory+'.json');p.write_text(json.dumps(q));components.append(dict(role=role,request=dict(path=str(p),sha256=z.digest(p))))
    bundle=dict(common,schema=z.BUNDLE_SCHEMA,caps=z.BUNDLE_CAPS,components=components,output_root=str(tmp_path/'out'),
        spec=dict(device='cpu',max_forward=0,max_backward=0,timeout_seconds=120))
    bp=tmp_path/'bundle.json';bp.write_text(json.dumps(bundle))
    monkeypatch.setattr(z,'http_open',lambda *_:pytest.fail('no HTTP'))
    monkeypatch.setattr(z.sys,'argv',['generated','--request',str(bp),'--sha256',z.digest(bp)])
    z.main();assert 'CHECK_ONLY_NO_HTTP' in capsys.readouterr().out and not (tmp_path/'out').exists()
    r=components[0]['request'];monkeypatch.setattr(z.sys,'argv',['generated','--request',r['path'],'--sha256',r['sha256'],'--execute'])
    with pytest.raises(ValueError,match='COMPONENT_ONLY'):z.main()


def bind():
    return dict(path='GENERATED-EVIDENCE', sha256='1'*64)


def case(cid='GEN1'):
    return dict(case_id=cid, local_use='development', failures=[],
        source=dict(dataset_id='GENERATED', version='1', official_split='train', metadata_binding=bind()),
        patient=dict(status='VERIFIED', group_id='GEN-PATIENT', evidence=bind()),
        license=dict(status='CLEARED', identifier='GENERATED', evidence=bind()),
        image=dict(binding=bind(), hu_status='NATIVE_HU_VERIFIED', evidence=bind()),
        gt=dict(binding=bind(), extent='COMPLETE', coverage_domain='FULL_NATIVE_VOLUME', unannotated_is_background=False,
                expert_status='SOURCE_REPORTED', author_source='GENERATED EXPERT', evidence=bind(),
                labels=[dict(value=1, raw_class='infection', medical_category='INFECTION')]),
        geometry=dict(status='VERIFIED', axis_order='ZYX_TO_LPS_MM', shape_zyx=[16,4,4], spacing_zyx_mm=[2,1,1],
            affine_lps_mm=[[0,0,1,0],[0,1,0,0],[2,0,0,0],[0,0,0,1]], ct_gt_native_grid_equal=True, qa_binding=bind(), transform_binding=bind()),
        fixed_k8=dict(native_z=list(range(1,16,2)), preprocess_binding=bind()),
        overlap=dict(status='CLEARED', evidence=bind()), access=dict(status='AUTHORIZED', evidence=bind()),
        prior_use=dict(training=False, development=True))


def registry(*cases):
    return m.validate_registry(dict(schema=m.SCHEMA, purpose='development_evaluation', cases=list(cases)))


def test_registry_preserves_unknown_failed_and_partial_cases():
    complete = case(); partial = case('GEN2'); partial['gt'].update(extent='PARTIAL', coverage_domain='SELECTED_NATIVE_PLANES')
    unknown = case('GEN3'); unknown['patient'].update(status='UNKNOWN',group_id=None); unknown['failures']=['SOURCE_MISSING']
    unknown['image']['hu_status']='WINDOWED_0_255'
    result = registry(complete, partial, unknown)
    assert result['denominators']['retained_cases']==3 and result['denominators']['distinct_patients'] is None
    assert result['rows'][0]['complete_reference_claim_eligible']
    assert result['rows'][1]['coverage_claim_eligible'] and not result['rows'][1]['complete_reference_claim_eligible']
    assert 'SOURCE_MISSING' in result['rows'][2]['blockers'] and 'HU_WINDOWED_0_255' in result['rows'][2]['blockers']
    assert result['medical_denominator'] is None and all(not r['payload_verified_by_this_validator'] for r in result['rows'])
    assert result['rows'][2]['record']==unknown and not result['rows'][0]['independent_test_eligible']


def test_registry_repeated_patients_and_native_geometry_rejection():
    result=registry(case(),case('GEN2')); assert result['denominators']['distinct_patients']==1
    assert result['repeated_patient_case_ids']==[['GEN1','GEN2']]
    bad=case();bad['geometry']['spacing_zyx_mm']=[1,1,1]
    with pytest.raises(ValueError,match='SPACING_DISAGREES'):registry(bad)
    bad=case();bad['fixed_k8']['native_z']=[0]*8
    with pytest.raises(ValueError,match='FIXED_K8'):registry(bad)
    bad=case();bad['gt']['unannotated_is_background']=True
    with pytest.raises(ValueError,match='NOT_BACKGROUND'):registry(bad)
    with pytest.raises(ValueError,match='DUPLICATE_CASE'):registry(case(),case())


def test_registry_unknown_overlap_and_no_infection_semantics_block():
    record=case();record['overlap']['status']='UNKNOWN'
    record['gt']['labels'][0]['medical_category']='OTHER'
    result=registry(record)
    assert 'OVERLAP_UNKNOWN' in result['rows'][0]['overlap_risks']
    assert 'INFECTION_CLASS_UNRESOLVED' in result['rows'][0]['blockers']
    assert result['denominators']['retained_cases']==1 and not result['rows'][0]['coverage_claim_eligible']


def test_development_unknown_and_known_method_overlap_disclosed_not_identity_gate():
    record=case();record['overlap'].update(status='UNKNOWN',evidence=None,by_method={
        'R18':dict(status='UNKNOWN',evidence=None),'Inf-Net':dict(status='KNOWN_OVERLAP',evidence=bind())})
    result=registry(record)['rows'][0]
    assert result['coverage_claim_eligible'] and result['complete_reference_claim_eligible']
    assert not result['independent_test_eligible'] and not result['payload_verified_by_this_validator']
    assert 'OVERLAP_UNKNOWN' in result['method_overlap_risks']['R18']
    assert 'OVERLAP_KNOWN_OVERLAP' in result['method_overlap_risks']['Inf-Net']
    assert result['record']['overlap']==record['overlap']
