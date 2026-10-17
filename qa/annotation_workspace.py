"""Generate and serve an isolated single-slice annotation product workspace.

Only generates its own DICOM; no research files, historical DB or model inputs.
Credentials are written owner-only, never printed. All HTTP stays on loopback.
"""
from __future__ import annotations
import argparse
from datetime import timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import ssl
import subprocess
import sys
import time
import uuid

from sqlalchemy.orm import sessionmaker
from backend_v2.db.base import Base, make_engine
from backend_v2.models.entities import User, Patient, Case, Study, Series, Slice
from backend_v2.auth.credentials import issue_user_credential
from backend_v2.services.common import now
from backend_v2.annotation_v1.api import ImagePlane, digest, install_schema

ROOT=Path(__file__).resolve().parents[1]


def private(path, value):
    raw=(json.dumps(value,indent=2)+'\n').encode() if not isinstance(value,bytes) else value
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as out:out.write(raw)


class TestStorage:
    """Explicit generated-only TEST_STORAGE, not a production storage adapter."""
    def __init__(self, root):self.root=Path(root)
    def read(self,key):
        if key!='generated-ct.dcm':raise ValueError('TEST_STORAGE_GENERATED_OBJECT_ONLY')
        return (self.root/key).read_bytes(),'application/dicom'


def seed(run):
    from array import array
    from argon2 import PasswordHasher
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian
    run=Path(run);run.mkdir(mode=0o700,parents=True,exist_ok=False)
    store=run/'TEST_STORAGE';store.mkdir(mode=0o700)
    uid=lambda:'2.25.'+str(uuid.uuid4().int)
    study_uid,series_uid,sop_uid,frame_uid=[uid() for _ in range(4)]
    meta=FileMetaDataset();meta.MediaStorageSOPClassUID=CTImageStorage;meta.MediaStorageSOPInstanceUID=sop_uid;meta.TransferSyntaxUID=ExplicitVRLittleEndian;meta.ImplementationClassUID=uid()
    image=FileDataset('generated-ct',{},file_meta=meta,preamble=b'\0'*128)
    image.SOPClassUID=CTImageStorage;image.SOPInstanceUID=sop_uid;image.StudyInstanceUID=study_uid;image.SeriesInstanceUID=series_uid;image.FrameOfReferenceUID=frame_uid
    image.PatientName='GENERATED^ANNOTATION';image.PatientID='SYNTHETIC-ONLY';image.Modality='CT'
    image.Rows=80;image.Columns=112;image.PixelSpacing=[.7,1.2];image.ImagePositionPatient=[12,34,56];image.ImageOrientationPatient=[0,1,0,-1,0,0]
    image.SamplesPerPixel=1;image.PhotometricInterpretation='MONOCHROME2';image.BitsAllocated=16;image.BitsStored=16;image.HighBit=15;image.PixelRepresentation=0
    image.RescaleSlope=1;image.RescaleIntercept=-1024;image.WindowCenter=-400;image.WindowWidth=1200
    pixels=array('H',(400+250*((r//10+c//14)%2)+r*8 for r in range(80) for c in range(112)))
    if sys.byteorder!='little':pixels.byteswap()
    image.PixelData=pixels.tobytes();stream=io.BytesIO();image.save_as(stream,enforce_file_format=True);raw=stream.getvalue();private(store/'generated-ct.dcm',raw)
    engine=make_engine('sqlite:///'+str(run/'backend.sqlite'));Base.metadata.create_all(engine);install_schema(engine);factory=sessionmaker(engine,expire_on_commit=False)
    auth={};accounts={}
    with factory.begin() as db:
        owner=User(auth_subject='synthetic-doctor');other=User(auth_subject='synthetic-observer');db.add_all([owner,other]);db.flush()
        patient=Patient(owner_user_id=owner.id,anonymous_id='GENERATED_PATIENT');db.add(patient);db.flush()
        case=Case(owner_user_id=owner.id,patient_id=patient.id,anonymous_id='GENERATED_ANNOTATION_CASE',status='READY');db.add(case);db.flush()
        study=Study(case_id=case.id,study_ref='GENERATED_STUDY');db.add(study);db.flush()
        series=Series(case_id=case.id,study_id=study.id,series_ref='GENERATED_SERIES');db.add(series);db.flush()
        sl=Slice(series_id=series.id,case_id=case.id,slice_ref='GENERATED_SLICE',ordinal=0,width_px=112,height_px=80,source_sha256=hashlib.sha256(raw).hexdigest(),staging_object_key='generated-ct.dcm',staging_expires_at=now()+timedelta(hours=8));db.add(sl);db.flush()
        geometry=dict(width=112,height=80,ipp=[12.,34.,56.],iop=[0.,1.,0.,-1.,0.,0.],spacing=[.7,1.2])
        binding=dict(case_id=case.anonymous_id,slice_id=sl.slice_ref,study_uid=study_uid,series_uid=series_uid,sop_instance_uid=sop_uid,frame_of_reference_uid=frame_uid,ct_sha256=sl.source_sha256,geometry=geometry,geometry_sha256=digest(geometry),geometry_version='DICOM_NATIVE_CENTRES_LPS_V1')
        db.add(ImagePlane(slice_pk=sl.id,binding=binding))
        for user in [owner,other]:
            _,token=issue_user_credential(db,user,expires_in=timedelta(hours=8),label='synthetic-annotation-workspace')
            password=secrets.token_urlsafe(24);tokenfile=run/(user.auth_subject+'.env');private(tokenfile,('export EPILOCATE_USER_TOKEN='+token+'\n').encode())
            accounts[user.auth_subject]=dict(enabled=True,password_hash=PasswordHasher().hash(password),token_file=str(tokenfile))
            auth[user.auth_subject]=dict(username=user.auth_subject,password=password)
    engine.dispose();private(run/'accounts.json',accounts);private(run/'session.key',secrets.token_bytes(32))
    ports={}
    for kind in ['backend','gateway','edge']:
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));ports[kind]=sock.getsockname()[1]
    assert len(set(ports.values()))==3
    config=dict(scope='SYNTHETIC_ONLY',storage='TEST_STORAGE',accounts=auth,binding=binding,ports=ports,origin='https://localhost:'+str(ports['edge']),run_directory=str(run))
    private(run/'private-config.json',config)
    private(run/'seed-manifest.json',dict(schema='GENERATED_ANNOTATION_SEED_V1',config_sha256=digest(config),
            binding_sha256=digest(binding),ct_sha256=hashlib.sha256(raw).hexdigest(),
            generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    return config


def validate_generated_run(run, *, require_local=True):
    run=Path(run)
    if run.is_symlink() or (require_local and not run.resolve().is_relative_to(ROOT/'.local')):
        raise ValueError('TASK_LOCAL_GENERATED_RUN_REQUIRED')
    run=run.resolve()
    for name in ['private-config.json','seed-manifest.json','TEST_STORAGE/generated-ct.dcm']:
        path=run/name
        if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o077:
            raise ValueError('PRIVATE_GENERATED_SEED_REQUIRED')
    config=json.loads((run/'private-config.json').read_bytes());manifest=json.loads((run/'seed-manifest.json').read_bytes())
    b=config.get('binding',{})
    if (config.get('scope')!='SYNTHETIC_ONLY' or config.get('storage')!='TEST_STORAGE'
            or config.get('origin')!='https://localhost:'+str(config.get('ports',{}).get('edge'))
            or config.get('run_directory')!=str(run) or b.get('case_id')!='GENERATED_ANNOTATION_CASE'
            or b.get('slice_id')!='GENERATED_SLICE' or manifest.get('schema')!='GENERATED_ANNOTATION_SEED_V1'
            or manifest.get('config_sha256')!=digest(config) or manifest.get('binding_sha256')!=digest(b)
            or manifest.get('generator_sha256')!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()):
        raise ValueError('GENERATED_WORKSPACE_IDENTITY_DRIFT')
    raw=(run/'TEST_STORAGE/generated-ct.dcm').read_bytes()
    if len(raw)>65536 or hashlib.sha256(raw).hexdigest()!=manifest['ct_sha256'] or b['ct_sha256']!=manifest['ct_sha256']:
        raise ValueError('GENERATED_CT_IDENTITY_DRIFT')
    return config


def child(kind,run,dist):
    import uvicorn
    config=validate_generated_run(run);run=Path(run).resolve()
    if kind=='backend':
        from backend_v2.annotation_v1.api import create_app
        engine=make_engine('sqlite:///'+str(run/'backend.sqlite'));app=create_app(sessionmaker(engine,expire_on_commit=False),TestStorage(run/'TEST_STORAGE'))
    elif kind=='gateway':
        from session_gateway.app import create_app,Settings
        app=create_app(Settings(config['origin'],'http://127.0.0.1:'+str(config['ports']['backend']),run/'accounts.json',run/'sessions.sqlite',run/'session.key'))
    else:
        from http.server import ThreadingHTTPServer
        from qa.phase5_local_https import Edge
        class AnnotationEdge(Edge):
            def static(self):
                if self.path.startswith('/annotations/'):
                    self.path=self.path[len('/annotations'):]
                    return super().static()
                self.send_error(404)
        class Server(ThreadingHTTPServer):
            request_queue_size=64
        server=Server(('127.0.0.1',config['ports']['edge']),AnnotationEdge)
        server.kind='browser';server.gateway=config['ports']['gateway'];server.backend=config['ports']['backend'];server.static_root=Path(dist).resolve()
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(run/'tls.crt',run/'tls.key')
        server.socket=context.wrap_socket(server.socket,server_side=True,do_handshake_on_connect=False);server.serve_forever();return
    uvicorn.run(app,host='127.0.0.1',port=config['ports'][kind],access_log=False,log_level='warning')


def serve(run,dist):
    import httpx
    run=Path(run).resolve();dist=Path(dist).resolve()
    if not run.is_relative_to(ROOT/'.local') or not (dist/'index.html').is_file():raise ValueError('ISOLATED_LOCAL_RUN_AND_BUILT_FRONTEND_REQUIRED')
    config=seed(run)
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(run/'tls.key'),'-out',str(run/'tls.crt'),'-days','3','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True);(run/'tls.key').chmod(0o600)
    processes=[];logs=[]
    def stop(*_):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    private(run/'parent.json',dict(pid=os.getpid(),start=subprocess.check_output(['ps','-p',str(os.getpid()),'-o','lstart='],text=True).strip()))
    try:
        for kind in ['backend','gateway','edge']:
            log=(run/(kind+'.log')).open('xb');logs.append(log)
            processes.append(subprocess.Popen([sys.executable,'-m','qa.annotation_workspace','--child',kind,'--run',str(run),'--dist',str(dist)],cwd=ROOT,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1'),stdout=log,stderr=log))
        deadline=time.monotonic()+20
        with httpx.Client(verify=ssl.create_default_context(cafile=str(run/'tls.crt')),trust_env=False,timeout=1) as client:
            while True:
                if any(p.poll() is not None for p in processes):raise RuntimeError('OWN_SERVICE_EXITED')
                try:
                    if client.get(config['origin']+'/auth/session').status_code==401:break
                except httpx.HTTPError:pass
                if time.monotonic()>deadline:raise TimeoutError('ANNOTATION_STARTUP')
                time.sleep(.1)
        private(run/'ready.json',dict(url=config['origin']+'/annotations/',credentials_path=str(run/'private-config.json'),owned_services=[p.pid for p in processes],scope='SYNTHETIC_ONLY',model_calls=0,workers=0))
        print(json.dumps(dict(url=config['origin']+'/annotations/',credentials_path=str(run/'private-config.json'))),flush=True)
        while True:
            if any(p.poll() is not None for p in processes):raise RuntimeError('OWN_SERVICE_EXITED')
            time.sleep(.3)
    except KeyboardInterrupt:pass
    finally:
        for p in reversed(processes):
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=3)
                except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)
        for log in logs:log.close()
        private(run/'exit.json',dict(owned_services=[dict(pid=p.pid,exit_code=p.returncode) for p in processes],model_calls=0,workers=0))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--dist',type=Path,default=ROOT/'annotation_workspace/dist');p.add_argument('--child',choices=['backend','gateway','edge']);a=p.parse_args()
    child(a.child,a.run,a.dist) if a.child else serve(a.run,a.dist)
