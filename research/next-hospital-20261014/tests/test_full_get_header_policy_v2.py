"""New generated responses only. No old suite execution or real HTTP."""
import hashlib
import io
import json
import zipfile
import pytest
from epi_next import full_get_header_policy_v2 as v2


class Items:
    def __init__(self,pairs):self.pairs=pairs
    def items(self):return iter(self.pairs)


class Response:
    def __init__(self,body,url,pairs,status=200):
        self.stream=io.BytesIO(body);self.url=url;self.headers=Items(pairs)
        self.status=status;self.length=len(body);self.reads=0
    def geturl(self):return self.url
    def read(self,n):
        self.reads+=1;b=self.stream.read(n);self.length-=len(b);return b
    def close(self):self.stream.close()


def inputs(tmp_path):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:z.writestr('GENERATED.nii',b'GENERATED'*40)
    body=stream.getvalue();q=dict(output_root=str(tmp_path/'out'),files=[
        dict(key=k,bytes=len(body),md5=hashlib.md5(body).hexdigest(),seconds=60,url=v2.frozen.source_url(k))
        for k,*_ in v2.frozen.FILES])
    return q,body


def run_generated(q,body,extra=(),status=200):
    responses=[]
    def transport(url,headers,timeout):
        assert headers=={'Accept-Encoding':'identity'} and 0<timeout<=15
        r=Response(body,url,[('Content-Length',str(len(body))),*extra],status)
        responses.append(r);return r
    try:v2.acquire(q,transport)
    finally:run_generated.responses=responses
    return responses


def saved(q):
    root=v2.Path(q['output_root'])
    return json.loads((root/'RECEIPT.json').read_text()),json.loads((root/'HTTP_HEADER_AUDIT.json').read_text())


@pytest.mark.parametrize('field',['Set-Cookie','Link','Cache-Control','X-Generated-Info'])
def test_noncritical_repeats_full_stream_success_no_sensitive_values(tmp_path,field):
    q,body=inputs(tmp_path);original=v2.frozen.headers
    rs=run_generated(q,body,[(field,'SECRET_GENERATED_A'),(field.lower(),'SECRET_GENERATED_B')])
    receipt,audit=saved(q)
    assert receipt['status']=='FULL_ARCHIVES_AND_LOCAL_DIRECTORIES_ONLY' and receipt['GET_requests']==2
    assert all(r.reads>0 and r.stream.closed for r in rs)
    assert all(t['field_counts'][field.lower()]==2 and field.lower() in t['duplicate_names'] for t in audit['transactions'])
    assert all(t['status_code']==200 for t in audit['transactions'])
    raw=(v2.Path(q['output_root'])/'HTTP_HEADER_AUDIT.json').read_text()
    assert 'SECRET_GENERATED' not in raw and not audit['header_values_saved']
    assert v2.frozen.headers is original  # No monkey-patching frozen functions.


@pytest.mark.parametrize('field',['Content-Length','Content-Encoding','Transfer-Encoding','Content-Range','Location','ETag'])
def test_critical_repeat_reject_before_body_keeps_diagnostic(tmp_path,field):
    q,body=inputs(tmp_path)
    pairs=[(field,'DO_NOT_SAVE_A'),(field.lower(),'DO_NOT_SAVE_B')]
    with pytest.raises(ValueError,match='DUPLICATE_CRITICAL_HEADER'):run_generated(q,body,pairs)
    receipt,audit=saved(q);rs=run_generated.responses
    assert len(rs)==1 and rs[0].reads==0 and rs[0].stream.closed
    assert receipt['application_body_bytes']==0 and not receipt['files'][0]['promoted']
    assert audit['transactions'][0]['critical_duplicate']==field.lower()
    assert 'DO_NOT_SAVE' not in json.dumps(audit)


@pytest.mark.parametrize('code',[302,403,500])
def test_status_saved_but_existing_status_redirect_gates_unchanged(tmp_path,code):
    q,body=inputs(tmp_path)
    with pytest.raises(ValueError,match='GET_STATUS|UNAPPROVED_REDIRECT'):
        run_generated(q,body,[('Set-Cookie','PRIVATE'),('set-cookie','PRIVATE2')],status=code)
    receipt,audit=saved(q)
    assert audit['transactions'][0]['status_code']==code and receipt['application_body_bytes']==0
    assert len(run_generated.responses)==1 and run_generated.responses[0].reads==0


def test_lengths_digests_still_gate_and_audit_is_bounded(tmp_path):
    q,body=inputs(tmp_path);q['files'][0]['md5']='0'*32
    with pytest.raises(ValueError,match='MD5_MISMATCH'):
        run_generated(q,body,[('Vary','A'),('vary','B')])
    receipt,audit=saved(q);assert not receipt['files'][0]['promoted'] and receipt['GET_requests']==1
    assert (v2.Path(q['output_root'])/'HTTP_HEADER_AUDIT.json').stat().st_size<=v2.AUDIT_BYTES
    q2,_=inputs(tmp_path/'second')
    with pytest.raises(ValueError,match='DUPLICATE_CRITICAL'):run_generated(q2,body,[('content-length','999999')])
    assert run_generated.responses[0].reads==0


def test_weak_etag_still_not_required_by_full_get(tmp_path):
    q,body=inputs(tmp_path)
    run_generated(q,body,[('ETag','W/"GENERATED"'),('Set-Cookie','SECRET_A'),('set-cookie','SECRET_B')])
    receipt,audit=saved(q)
    assert receipt['status']=='FULL_ARCHIVES_AND_LOCAL_DIRECTORIES_ONLY'
    assert 'SECRET_' not in json.dumps(audit) and 'GENERATED' not in json.dumps(audit)


@pytest.mark.parametrize('fault',['single_wrong_length','truncated_body'])
def test_framing_after_noncritical_projection_still_stops_mask(tmp_path,fault):
    q,body=inputs(tmp_path);responses=[]
    def transport(url,headers,timeout):
        pairs=[('Content-Length','1' if fault=='single_wrong_length' else str(len(body))),
               ('Link','PRIVATE_A'),('link','PRIVATE_B')]
        r=Response(body,url,pairs)
        if fault=='truncated_body':r.stream=io.BytesIO(b'X')
        responses.append(r);return r
    with pytest.raises(ValueError,match='EXACT_LENGTH_BEFORE_BODY|TRUNCATED_OR_OVERLONG_BODY'):
        v2.acquire(q,transport)
    receipt,audit=saved(q)
    assert receipt['GET_requests']==1 and len(receipt['files'])==1 and len(responses)==1
    assert not receipt['files'][0]['promoted'] and responses[0].stream.closed
    assert audit['transactions'][0]['field_counts']['link']==2 and 'PRIVATE_' not in json.dumps(audit)
    if fault=='single_wrong_length':assert responses[0].reads==0


def test_header_name_limits_and_no_url_value_leak(tmp_path):
    q,body=inputs(tmp_path)
    with pytest.raises(ValueError,match='HEADER_NAME_COUNT_LIMIT'):
        run_generated(q,body,[('X-'+str(i),'SENSITIVE') for i in range(v2.MAX_NAMES)])
    _,audit=saved(q);assert 'SENSITIVE' not in json.dumps(audit)
    r=Response(body,'https://INVALID/?SECRET=VALUE',[('Content-Length',str(len(body)))])
    a=v2.Audit()
    with pytest.raises(ValueError,match='RESPONSE_URL_DRIFT'):a.observe(r,'https://EXPECTED/')
    assert 'SECRET' not in json.dumps(a.records) and a.records[0]['response_URL_matches_requested'] is False


def test_existing_output_not_touched(tmp_path):
    q,body=inputs(tmp_path);root=v2.Path(q['output_root']);root.mkdir();p=root/'KEEP';p.write_text('GENERATED')
    with pytest.raises(ValueError,match='OUTPUT_ALREADY_EXISTS'):run_generated(q,body)
    assert p.read_text()=='GENERATED' and not(root/'HTTP_HEADER_AUDIT.json').exists()
