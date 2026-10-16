"""New generated streams/ZIP metadata only, no real network or medical files."""
import hashlib
import io
import json
import os
import struct
import zipfile
import pytest
from epi_next import r111_full_acquire as a


def archive(name='GENERATED.nii',comment=b''):
    f=io.BytesIO()
    with zipfile.ZipFile(f,'w',compression=zipfile.ZIP_STORED) as z:
        z.writestr(name,b'GENERATED'*40);z.comment=comment
    return f.getvalue()


class Response:
    def __init__(self,data,url,status=200,extra=()):
        self.stream=io.BytesIO(data);self.status=status;self.url=url;self.length=len(data);self.reads=0
        self.headers={'Content-Length':str(len(data)),**dict(extra)}
    def geturl(self):return self.url
    def read(self,n):
        self.reads+=1;value=self.stream.read(n);self.length-=len(value);return value
    def __enter__(self):return self
    def __exit__(self,*_):self.stream.close()


class Transport:
    def __init__(self,bodies,edit=None):self.bodies=bodies;self.edit=edit;self.calls=[];self.responses=[]
    def __call__(self,url,headers,timeout):
        assert headers=={'Accept-Encoding':'identity'} and 0<timeout<=15
        self.calls.append(url)
        key=next(k for k in self.bodies if '/'+k+'/' in url or '/'+k+'?' in url)
        r=Response(self.bodies[key],url)
        if self.edit:self.edit(r,len(self.calls))
        self.responses.append(r);return r


def inputs(tmp_path,first=None):
    bodies={k:archive(comment=b'GEN COMMENT') if first is None or i else first for i,(k,*_) in enumerate(a.FILES)}
    q=dict(output_root=str(tmp_path/'out'),files=[dict(key=k,bytes=len(bodies[k]),md5=hashlib.md5(bodies[k]).hexdigest(),seconds=60,url=a.source_url(k)) for k,*_ in a.FILES])
    return q,bodies


def receipt(q):return json.loads((a.Path(q['output_root'])/'RECEIPT.json').read_text())


@pytest.mark.parametrize('etag',[None,'W/"weak"'])
def test_full_get_without_strong_etag_succeeds_atomic_no_member_decode(tmp_path,monkeypatch,etag):
    q,b=inputs(tmp_path)
    def edit(r,n):
        if etag is not None:r.headers['ETag']=etag
    monkeypatch.setattr(zipfile.ZipFile,'open',lambda *_:pytest.fail('member must not open'))
    monkeypatch.setattr(zipfile.ZipFile,'testzip',lambda *_:pytest.fail('no member CRC decode'))
    observed=[];real=a.a0.publish
    def publish(part,final):
        inode=part.stat().st_ino;real(part,final);observed.append(final.stat().st_ino==inode)
    monkeypatch.setattr(a.a0,'publish',publish)
    t=Transport(b,edit);a.acquire(q,t)
    r=receipt(q);assert r['status']=='FULL_ARCHIVES_AND_LOCAL_DIRECTORIES_ONLY' and r['GET_requests']==2
    assert observed==[True,True] and r['medical_denominator'] is None and r['HTTP_HEAD']==r['HTTP_Range']==0
    for item in r['files']:
        final=a.Path(item['final']);assert final.exists() and not a.Path(item['part']).exists()
        assert item['sha256']==hashlib.sha256(b[final.name]).hexdigest()
        directory=json.loads((final.parent/(final.name+'.directory.json')).read_text())
        assert not directory['member_CRC_or_EOF_verified'] and directory['entries']==1


@pytest.mark.parametrize('fault,needle',[('length','EXACT_LENGTH'),('md5','MD5_MISMATCH'),('truncate','TRUNCATED'),('gzip','ENCODING'),('range','ENCODING'),('500','GET_STATUS')])
def test_failure_stops_second_archive_and_never_promotes(tmp_path,fault,needle):
    q,b=inputs(tmp_path)
    if fault=='md5':q['files'][0]['md5']='0'*32
    def edit(r,n):
        if fault=='length':r.headers['Content-Length']=str(len(b[q['files'][0]['key']])+1)
        if fault=='truncate':r.stream=io.BytesIO(b'X')
        if fault=='gzip':r.headers['Content-Encoding']='gzip'
        if fault=='range':r.headers['Content-Range']='bytes 0-1/2'
        if fault=='500':r.status=500
    t=Transport(b,edit)
    with pytest.raises(ValueError,match=needle):a.acquire(q,t)
    r=receipt(q);assert r['status']=='FAILED_STOP_NO_RETRY' and len(t.calls)==1
    assert len(r['files'])==1 and not a.Path(r['files'][0]['final']).exists() and a.Path(r['files'][0]['part']).exists()
    if fault in ('length','gzip','range','500'):assert t.responses[0].reads==0


def test_existing_part_final_and_symlink_not_overwritten(tmp_path):
    q,b=inputs(tmp_path);root=a.Path(q['output_root']);root.mkdir();part=root/(q['files'][0]['key']+'.part');part.write_bytes(b'KEEP')
    with pytest.raises(FileExistsError):a.acquire(q,lambda *_:pytest.fail('network'))
    assert part.read_bytes()==b'KEEP'
    budget=a.Budget(root,0);record={}
    with pytest.raises(ValueError,match='NO_RESUME'):a.transfer_one(q['files'][0],root,budget,lambda *_:pytest.fail('network'),record)
    part.unlink();target=tmp_path/'target';target.write_bytes(b'KEEP');part.symlink_to(target)
    with pytest.raises(ValueError,match='NO_RESUME'):a.transfer_one(q['files'][0],root,budget,lambda *_:pytest.fail('network'),{})
    assert target.read_bytes()==b'KEEP'


@pytest.mark.parametrize('target_kind',['official','other_host','http','different_file'])
def test_only_one_exact_official_redirect_and_no_drain(tmp_path,target_kind):
    q,b=inputs(tmp_path);key=q['files'][0]['key']
    target={'official':a.official_redirect_url(key),'other_host':'https://elsewhere.invalid/file','http':'http://example.invalid/records/3757476/files/'+key+'?download=1','different_file':a.official_redirect_url(q['files'][1]['key'])}[target_kind]
    def edit(r,n):
        if n==1:r.status=302;r.headers['Location']=target
    t=Transport(b,edit)
    if target_kind=='official':
        a.acquire(q,t);assert len(t.calls)==3 and receipt(q)['files'][0]['redirects'][0]['target']==target
    else:
        with pytest.raises(ValueError,match='UNAPPROVED_REDIRECT'):a.acquire(q,t)
        assert len(t.calls)==1
    assert t.responses[0].reads==0 and t.responses[0].stream.closed


def test_redirect_loop_stops_not_retry(tmp_path):
    q,b=inputs(tmp_path)
    def edit(r,n):r.status=302;r.headers['Location']=a.official_redirect_url(q['files'][0]['key'])
    t=Transport(b,edit)
    with pytest.raises(ValueError,match='UNAPPROVED_REDIRECT'):a.acquire(q,t)
    assert len(t.calls)==2 and all(r.reads==0 for r in t.responses)


@pytest.mark.parametrize('name',['../evil','/absolute','a\\b','C:/evil','a/./b','a\nname'])
def test_unsafe_zip_directory_keeps_part_not_promoted(tmp_path,name):
    q,b=inputs(tmp_path,archive(name))
    with pytest.raises(ValueError,match='UNSAFE_MEMBER'):a.acquire(q,Transport(b))
    assert not receipt(q)['files'][0]['promoted'] and receipt(q)['files'][0]['part_exists']


@pytest.mark.parametrize('fault,needle',[('encrypted','ENCRYPTION'),('bomb','ZIP_BOMB'),('oversize_directory','DIRECTORY_LIMIT')])
def test_zip_declaration_bounds_before_publish(tmp_path,fault,needle):
    raw=bytearray(archive());end=struct.unpack('<4s4H2IH',raw[-22:]);cd=end[6]
    if fault=='encrypted':struct.pack_into('<H',raw,cd+8,1)
    if fault=='bomb':struct.pack_into('<I',raw,cd+24,0xfffffffe)
    if fault=='oversize_directory':struct.pack_into('<I',raw,len(raw)-10,a.CAPS['directory_bytes']+1)
    q,b=inputs(tmp_path,bytes(raw))
    with pytest.raises(ValueError,match=needle):a.acquire(q,Transport(b))
    assert not receipt(q)['files'][0]['promoted']


def test_disk_and_output_and_body_and_time_guards(tmp_path):
    q,b=inputs(tmp_path);t=Transport(b)
    with pytest.raises(ValueError,match='DISK_RESERVE'):a.acquire(q,t,free_fn=lambda _:0)
    assert t.calls==[]
    root=tmp_path/'budget';root.mkdir();budget=a.Budget(root,0)
    with pytest.raises(ValueError,match='METADATA_OUTPUT'):a.write_metadata(root/'too-big',{'x':'12345'},budget,1)
    assert not(root/'too-big').exists()
    budget.body=a.CAPS['body_bytes'];record={}
    with pytest.raises(ValueError,match='BODY_LIMIT_BEFORE_READ'):a.transfer_one(q['files'][0],root,budget,t,record)
    assert t.responses[-1].reads==0
    budget.deadline=0
    with pytest.raises(ValueError,match='TIME_LIMIT'):budget.check()


def test_generated_zip64_directory_via_stdlib(tmp_path):
    raw=archive();e=list(struct.unpack('<4s4H2IH',raw[-22:]));start=len(raw)-22
    z64=struct.pack('<4sQ2H2I4Q',b'PK\x06\x06',44,45,45,0,0,1,1,e[5],e[6])
    loc=struct.pack('<4sIQI',b'PK\x06\x07',0,start,1)
    footer=struct.pack('<4s4H2IH',b'PK\x05\x06',0,0,65535,65535,0xffffffff,0xffffffff,0)
    q,b=inputs(tmp_path,raw[:-22]+z64+loc+footer)
    a.acquire(q,Transport(b));assert receipt(q)['files'][0]['promoted']


def test_check_only_no_http_and_old_approval_rejected(tmp_path,monkeypatch,capsys):
    q=dict(schema=a.SCHEMA,caps=a.CAPS,files=[dict(key=k,bytes=n,md5=m,seconds=s,url=a.source_url(k)) for k,n,m,s in a.FILES],
        spec=dict(device='cpu',max_forward=0,max_backward=0,timeout_seconds=1800),source_bindings=[],stdlib_bindings=[],
        runtime_sha256=a.a0.digest_bytes(a.Path(a.sys.executable).read_bytes()),python_version=a.platform.python_version(),
        package_versions={},metadata_evidence=[],output_root=str(tmp_path/'out'))
    p=tmp_path/'request.json';p.write_text(json.dumps(q));sha=a.a0.digest_bytes(p.read_bytes())
    monkeypatch.setattr(a,'http_open',lambda *_:pytest.fail('network forbidden'))
    monkeypatch.setattr(a.sys,'argv',['generated','--request',str(p),'--sha256',sha]);a.main()
    assert 'CHECK_ONLY_NO_HTTP_NO_FILES' in capsys.readouterr().out and not(tmp_path/'out').exists()
    owner=tmp_path/'oldowner.json';owner.write_text(json.dumps(dict(schema='R108_ZIP_STRUCTURE_BUNDLE_APPROVAL_V1',status='APPROVED_NEW_SCOPE',request_sha256=sha)))
    monkeypatch.setattr(a.sys,'argv',['generated','--request',str(p),'--sha256',sha,'--execute',
        '--approval',str(owner),'--approval-sha256',a.a0.digest_bytes(owner.read_bytes()),'--dispatch','NOT_READ','--dispatch-sha256','NOT_READ'])
    with pytest.raises(ValueError,match='NEW_EXACT_APPROVAL'):a.main()
    assert not(tmp_path/'out').exists()
