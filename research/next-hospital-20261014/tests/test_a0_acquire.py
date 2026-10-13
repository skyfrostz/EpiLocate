"""Generated archive and fake transfer only. No network or patient files."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
import zipfile
import pytest
from epi_next.a0_acquire import acquire, bound_json, directory, exclusive, phase, publish, ResumeHeaders


def fixture_zip(name='COVID-19 subjects/SYNTH-P1/a.dcm'):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:z.writestr(name,b'SYNTHETIC_ONLY_NEVER_DECODE_THIS_MEMBER')
    return stream.getvalue()


def config(tmp_path, payload):
    return {'file':{'compressed_bytes':len(payload),'expected_md5':hashlib.md5(payload).hexdigest()},
            'destination':str(tmp_path/'own'/'fixture.zip'),'temporary_destination':str(tmp_path/'own'/'fixture.zip.part'),
            'disk_plan':{'reserve_bytes':100,'technical_metadata_budget_bytes':100},
            'transfer_plan':{'connect_timeout_seconds':30,'wall_timeout_seconds':5,'low_speed_bytes_per_second':1,'low_speed_seconds':1,'max_http_header_bytes':1024},
            'phase_time_caps_seconds':{'preflight':1,'transfer':3,'integrity_md5_sha256':3,'technical_directory':3,'finalization':1,'overall_including_stopping':30},
            'directory_plan':{'output_destination':str(tmp_path/'own'/'directory'),'max_directory_entries':10,'max_central_directory_bytes':65536,'max_technical_inventory_output_bytes':65536,'max_summary_output_bytes':4096}}


def fake(tmp_path,payload,extra='',headers=20):
    src=tmp_path/'generated-source';src.write_bytes(payload)
    return [sys.executable,'-c',"import os,sys;os.write(int(os.environ['A0_TEST_HEADER_FD']),b'H'*"+str(headers)+");sys.stdout.buffer.write(open(sys.argv[1],'rb').read());sys.stdout.buffer.flush();"+extra,str(src)]


FREE=lambda p:10**9


def test_success_and_raw_request_hash_no_member_decode(tmp_path):
    raw=fixture_zip();c=config(tmp_path,raw)
    req=tmp_path/'request.json';req.write_bytes(b'{ "fixture": true }')
    assert bound_json(req,hashlib.sha256(req.read_bytes()).hexdigest())['fixture']
    with pytest.raises(ValueError,match='SHA_MISMATCH'):bound_json(req,'0'*64)
    receipt=acquire(c,fake(tmp_path,raw),FREE)
    assert receipt['status']=='OPAQUE_CONTAINER_AND_TECHNICAL_DIRECTORY_COMPLETE'
    assert receipt['phases']['integrity']['sha256']==hashlib.sha256(raw).hexdigest()
    assert Path(c['destination']).read_bytes()==raw
    assert not Path(c['temporary_destination']).exists()
    inventory=Path(c['directory_plan']['output_destination'])/'inventory.jsonl'
    assert json.loads(inventory.read_text())['name'].endswith('a.dcm')
    assert 'SYNTHETIC_ONLY_NEVER_DECODE' not in inventory.read_text()
    assert receipt['phases']['directory']['member_bodies_read'] is False


@pytest.mark.parametrize('change',['short','long','md5','headers','exit'])
def test_failed_transfer_or_integrity_preserves_part_without_publish(tmp_path,change):
    raw=fixture_zip();c=config(tmp_path,raw);sent=raw
    if change=='short':sent=raw[:-1]
    if change=='long':sent=raw+b'x'
    if change=='md5':c['file']['expected_md5']='0'*32
    command=fake(tmp_path,sent,'sys.exit(7)' if change=='exit' else '',headers=2048 if change=='headers' else 20)
    receipt=acquire(c,command,FREE)
    assert receipt['status']=='FAILED'
    assert not Path(c['destination']).exists()
    assert Path(c['temporary_destination']).stat().st_size<=len(raw)


def test_no_clobber_and_symlink_parent(tmp_path):
    first=tmp_path/'first';first.write_bytes(b'a');other=tmp_path/'other';other.write_bytes(b'b')
    with pytest.raises(FileExistsError):publish(first,other)
    assert first.read_bytes()==b'a' and other.read_bytes()==b'b'
    with pytest.raises(FileExistsError):exclusive(first)
    alias=tmp_path/'alias';alias.symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(ValueError,match='UNSAFE_PARENT'):exclusive(alias/'new')


def test_low_disk_and_timeout_own_child_reaped(tmp_path):
    with pytest.raises(RuntimeError,match='DISK_RESERVE'):
        phase(time.sleep,(2,),1,time.monotonic()+30,tmp_path,100,lambda p:0)
    started=time.monotonic()
    with pytest.raises(TimeoutError):phase(time.sleep,(20,),.1,time.monotonic()+30,tmp_path,1,FREE)
    assert time.monotonic()-started<4


@pytest.mark.parametrize('failure',['unsafe','duplicate','output','entries','central'])
def test_directory_fail_closed_without_member_extraction(tmp_path,failure):
    raw=fixture_zip('../escape' if failure=='unsafe' else 'SYNTH/file')
    if failure=='duplicate':
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            z.writestr('SYNTH/file',b'A');z.writestr('SYNTH/file',b'B')
        raw=stream.getvalue()
    src=tmp_path/'generated.zip';src.write_bytes(raw);limits=config(tmp_path,raw)['directory_plan']
    if failure=='output':limits['max_technical_inventory_output_bytes']=1
    if failure=='entries':limits['max_directory_entries']=0
    if failure=='central':limits['max_central_directory_bytes']=1
    with pytest.raises(ValueError):directory(src,tmp_path/'metadata',limits)
    assert not (tmp_path/'escape').exists()
    assert not (tmp_path/'metadata'/'inventory.jsonl').exists()


def test_only_eocd_central_bytes_read_and_zip64_records(tmp_path,monkeypatch):
    import builtins,struct
    raw=fixture_zip();original_eocd=raw[-22:];e=struct.unpack('<4s4H2IH',original_eocd)
    # Generate ZIP64 EOCD/locator even for a tiny fixture, preserving central directory.
    prefix=raw[:-22];z64=struct.pack('<4sQ2H2I4Q',b'PK\x06\x06',44,45,45,0,0,1,1,e[5],e[6])
    locator=struct.pack('<4sIQI',b'PK\x06\x07',0,len(prefix),1)
    end=struct.pack('<4s4H2IH',b'PK\x05\x06',0,0,65535,65535,0xffffffff,0xffffffff,0)
    src=tmp_path/'generated.zip';src.write_bytes(prefix+z64+locator+end); real_open=builtins.open;reads=[]
    class Trace:
        def __init__(self,f):self.f=f
        def __enter__(self):return self
        def __exit__(self,*args):self.f.close()
        def read(self,n):
            pos=self.f.tell();data=self.f.read(n);reads.append((pos,pos+len(data)));return data
        def seek(self,*a):return self.f.seek(*a)
        def tell(self):return self.f.tell()
    def traced(path,*a,**k):
        f=real_open(path,*a,**k)
        return Trace(f) if Path(path)==src else f
    monkeypatch.setattr(builtins,'open',traced)
    assert directory(src,tmp_path/'metadata',config(tmp_path,raw)['directory_plan'])['entries']==1
    assert all(start>=e[6] for start,end in reads),reads


def test_disk_drop_and_overall_deadline(tmp_path):
    calls=[0]
    def free(path):
        calls[0]+=1
        return 10**9 if calls[0]==1 else 0
    with pytest.raises(RuntimeError,match='DISK_RESERVE'):
        phase(time.sleep,(20,),3,time.monotonic()+30,tmp_path,100,free)
    with pytest.raises(TimeoutError):
        phase(time.sleep,(20,),10,time.monotonic()+12.1,tmp_path,1,FREE)


def test_commented_archive_rejected_and_group_summary_bounded(tmp_path):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        z.writestr('SYNTH/file',b'SYNTH');z.comment=b'comment'
    src=tmp_path/'commented.zip';src.write_bytes(stream.getvalue())
    with pytest.raises(ValueError,match='EOCD_COMMENT'):
        directory(src,tmp_path/'comment-dir',config(tmp_path,stream.getvalue())['directory_plan'])
    raw=fixture_zip();src=tmp_path/'plain.zip';src.write_bytes(raw)
    limits=config(tmp_path,raw)['directory_plan'];limits['max_summary_output_bytes']=1
    with pytest.raises(ValueError,match='GROUP_SUMMARY_BYTES'):
        directory(src,tmp_path/'summary-dir',limits)


def test_timeout_before_setsid_never_starts_operation(tmp_path,monkeypatch):
    import multiprocessing as mp
    import epi_next.a0_acquire as module
    original=module._phase_child
    def late_ready(conn,fn,args):
        time.sleep(20);original(conn,fn,args)
    monkeypatch.setattr(module,'_phase_child',late_ready)
    with pytest.raises(TimeoutError):
        phase(Path.write_text,(tmp_path/'never-started','SYNTH'),.05,time.monotonic()+30,tmp_path,1,FREE)
    assert not (tmp_path/'never-started').exists()
    assert not mp.active_children()


def test_wrong_group_handshake_kills_exact_child(tmp_path,monkeypatch):
    import epi_next.a0_acquire as module
    def wrong_ready(conn,fn,args):
        conn.send(('READY',os.getpid(),os.getpgrp()));time.sleep(20)
    monkeypatch.setattr(module,'_phase_child',wrong_ready)
    with pytest.raises(RuntimeError,match='HANDSHAKE_MISMATCH'):
        phase(time.sleep,(20,),1,time.monotonic()+30,tmp_path,1,FREE)


def test_zip64_large_entry_fields_sparse_metadata_only(tmp_path):
    import struct
    name=b'SYNTH/member';offset=2**32+4;compressed=2**32+16;uncompressed=2**33+99
    extra=struct.pack('<HH3Q',1,24,uncompressed,compressed,offset)
    central=struct.pack('<4s6H3I5H2I',b'PK\x01\x02',45,45,0,8,0,0,0,0xffffffff,0xffffffff,len(name),len(extra),0,0,0,0,0xffffffff)+name+extra
    cd_offset=2**33+8192;z_offset=cd_offset+len(central)
    z=struct.pack('<4sQ2H2I4Q',b'PK\x06\x06',44,45,45,0,0,1,1,len(central),cd_offset)
    loc=struct.pack('<4sIQI',b'PK\x06\x07',0,z_offset,1)
    end=struct.pack('<4s4H2IH',b'PK\x05\x06',0,0,1,1,len(central),0xffffffff,0)
    src=tmp_path/'sparse-synthetic.zip'
    with open(src,'wb') as f:f.seek(cd_offset);f.write(central+z+loc+end)
    assert src.stat().st_blocks*512<1024*1024
    directory(src,tmp_path/'metadata',config(tmp_path,b'SYNTH')['directory_plan'])
    row=json.loads((tmp_path/'metadata'/'inventory.jsonl').read_text())
    assert row['header_offset']==offset and row['compressed_bytes']==compressed and row['uncompressed_bytes']==uncompressed


def test_comment_failure_keeps_opaque_part(tmp_path):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:z.writestr('SYNTH/file',b'SYNTH');z.comment=b'COMMENT'
    raw=stream.getvalue();c=config(tmp_path,raw);receipt=acquire(c,fake(tmp_path,raw),FREE)
    assert receipt['status']=='FAILED' and receipt['directory_status']=='INCOMPLETE_NOT_READY'
    assert Path(c['temporary_destination']).read_bytes()==raw
    assert not Path(c['destination']).exists()


def resumed_fixture(tmp_path, headers=None, suffix=None, exit_code=0):
    raw=fixture_zip();c=config(tmp_path,raw);offset=len(raw)//2
    part=Path(c['temporary_destination']);part.parent.mkdir();part.write_bytes(raw[:offset])
    c['resume_plan']={'enabled':True,'offset_bytes':offset}
    header=headers if headers is not None else (
        f'HTTP/1.1 206 Partial Content\r\nContent-Range: bytes {offset}-{len(raw)-1}/{len(raw)}\r\n'
        f'Content-Length: {len(raw)-offset}\r\n\r\n').encode()
    sent=raw[offset:] if suffix is None else suffix
    source=tmp_path/'generated-suffix';source.write_bytes(sent)
    argv=[sys.executable,'-c',
          "import os,sys,time;h="+repr(header)+";fd=int(os.environ['A0_TEST_HEADER_FD']);"
          "os.write(fd,h[:7]);time.sleep(.01);os.write(fd,h[7:]);"
          "sys.stdout.buffer.write(open(sys.argv[1],'rb').read());sys.stdout.buffer.flush();"
          "sys.exit("+str(exit_code)+")",str(source)]
    return raw,c,argv


def test_resume_appends_suffix_and_hashes_entire_archive(tmp_path):
    raw,c,argv=resumed_fixture(tmp_path)
    receipt=acquire(c,argv,FREE)
    assert receipt['status']=='OPAQUE_CONTAINER_AND_TECHNICAL_DIRECTORY_COMPLETE'
    transfer=receipt['phases']['transfer']
    assert transfer['range_response_verified'] and transfer['resume_offset_bytes']==len(raw)//2
    assert transfer['bytes']==len(raw)-len(raw)//2
    assert receipt['phases']['integrity']['sha256']==hashlib.sha256(raw).hexdigest()
    assert Path(c['destination']).read_bytes()==raw


@pytest.mark.parametrize('header',[
    b'HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n',
    b'HTTP/1.1 416 Range Not Satisfiable\r\n\r\n',
    b'HTTP/1.1 206 Partial Content\r\nContent-Range: bytes 0-9/10\r\n\r\n',
    b'HTTP/1.1 206 Partial Content\r\nContent-Range: bytes 5-9/11\r\n\r\n',
    b'HTTP/1.1 206 Partial Content\r\nContent-Range: bytes 5-9/10\r\nContent-Encoding: gzip\r\n\r\n',
    b'HTTP/1.1 206 Partial Content\r\nContent-Range: bytes 5-9/10\r\nContent-Length: 6\r\n\r\n',
    b'HTTP/1.1 206 Partial Content\r\nContent-Range: bytes 5-9/10\r\nContent-Range: bytes 5-9/10\r\n\r\n',
    b'HTTP/1.1 302 Found\r\nLocation: https://example.invalid\r\n\r\n',
])
def test_resume_rejects_bad_response_before_any_append(tmp_path,header):
    raw,c,argv=resumed_fixture(tmp_path,headers=header)
    before=Path(c['temporary_destination']).read_bytes()
    receipt=acquire(c,argv,FREE)
    assert receipt['status']=='FAILED'
    assert Path(c['temporary_destination']).read_bytes()==before
    assert not Path(c['destination']).exists()


def test_resume_redirect_and_proxy_headers_fragmented():
    verifier=ResumeHeaders(5,10)
    raw=(b'HTTP/1.1 200 Connection established\r\n\r\n'
         b'HTTP/2 302\r\nLocation: https://example.invalid\r\n\r\n'
         b'HTTP/2 206\r\nContent-Range: bytes 5-9/10\r\n\r\n')
    for byte in raw:verifier.feed(bytes([byte]))
    assert verifier.approved


def test_resume_interruption_keeps_progress_and_numeric_curl_exit(tmp_path):
    raw,c,argv=resumed_fixture(tmp_path,suffix=b'XYZ',exit_code=28)
    receipt=acquire(c,argv,FREE)
    assert receipt['status']=='FAILED' and 'TRANSFER_EXIT_28' in receipt['failure']
    assert Path(c['temporary_destination']).read_bytes()==raw[:len(raw)//2]+b'XYZ'


def test_resume_bad_prefix_never_publishes(tmp_path):
    raw,c,argv=resumed_fixture(tmp_path)
    Path(c['temporary_destination']).write_bytes(b'X'*(len(raw)//2))
    receipt=acquire(c,argv,FREE)
    assert receipt['status']=='FAILED' and 'INTEGRITY_MISMATCH' in receipt['failure']
    assert not Path(c['destination']).exists()


@pytest.mark.parametrize('change',['size','symlink','locked'])
def test_resume_partial_identity_and_lock(tmp_path,change):
    import fcntl
    raw,c,argv=resumed_fixture(tmp_path);part=Path(c['temporary_destination']);handle=None
    if change=='size':part.write_bytes(b'X')
    if change=='symlink':
        target=part.with_name('generated-target');part.rename(target);part.symlink_to(target)
    if change=='locked':
        handle=part.open('rb');fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        with pytest.raises((ValueError,BlockingIOError)):acquire(c,argv,FREE)
        assert not Path(c['destination']).exists()
    finally:
        if handle:handle.close()


def test_resume_disk_budget_counts_remaining_bytes(tmp_path):
    raw,c,argv=resumed_fixture(tmp_path);remaining=len(raw)-len(raw)//2
    receipt=acquire(c,argv,lambda p:200+remaining)
    assert receipt['status']=='OPAQUE_CONTAINER_AND_TECHNICAL_DIRECTORY_COMPLETE'


@pytest.mark.parametrize('response',['range','ignored','wrong'])
def test_real_curl_local_synthetic_range_transport(tmp_path,response):
    import http.server,threading,shutil
    curl=shutil.which('curl')
    if not curl:pytest.skip('curl unavailable')
    raw,c,_=resumed_fixture(tmp_path);offset=len(raw)//2;seen=[]
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            seen.append(self.headers.get('Range'))
            body=raw[offset:] if response!='ignored' else raw
            self.send_response(206 if response!='ignored' else 200)
            self.send_header('Content-Length',str(len(body)))
            if response!='ignored':
                self.send_header('Content-Range',f'bytes {offset if response=="range" else 0}-{len(raw)-1}/{len(raw)}')
            self.end_headers();self.wfile.write(body)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    # A generated local URL is injected only through the existing test hook.
    argv=[sys.executable,'-c',
          'import os,sys;os.execv(sys.argv[1],[sys.argv[1],"--disable","--fail","--silent",'
          '"--max-time","2","--range",sys.argv[2],"--dump-header",'
          '"/dev/fd/"+os.environ["A0_TEST_HEADER_FD"],"--output","-",sys.argv[3]])',
          curl,str(offset)+'-',f'http://127.0.0.1:{server.server_port}/generated.zip']
    try:receipt=acquire(c,argv,FREE)
    finally:server.shutdown();server.server_close();thread.join(2)
    assert seen==['bytes='+str(offset)+'-']
    if response=='range':
        assert receipt['status']=='OPAQUE_CONTAINER_AND_TECHNICAL_DIRECTORY_COMPLETE'
        assert Path(c['destination']).read_bytes()==raw
    else:
        assert receipt['status']=='FAILED'
        assert Path(c['temporary_destination']).read_bytes()==raw[:offset]
