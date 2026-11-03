"""Loopback, compute-disabled reader of an existing MVP; never runs a Worker.

Original DB/assets/dist are preserved. Only a new private run contains renewed
authentication and a DB copy. Default CLI checks metadata without starting it.
"""
import argparse
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import time
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'qa'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def bound(ref):
    raw = Path(ref['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ref['sha256']: raise ValueError('BOUND_METADATA_DRIFT')
    return json.loads(raw)


def private(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream: stream.write(raw)


def validate_binding(binding):
    if binding['schema'] != 'LOCAL_MVP_READONLY_BINDING_V1' or binding['permission_scope'] != 'LOCAL_MVP_ONLY':
        raise ValueError('LOCAL_MVP_ONLY_BINDING_REQUIRED')
    if binding['mode'] not in {'HISTORICAL_M0', 'SYNTHETIC_TEST_ASSETS'}: raise ValueError('SNAPSHOT_MODE')
    for path, expected in binding['source_sha256'].items():
        if sha(path) != expected: raise ValueError('RESTORE_SOURCE_DRIFT')
    if str(Path(__file__).resolve()) not in binding['source_sha256']: raise ValueError('RESTORE_ENTRY_NOT_BOUND')
    if binding['mode'] == 'HISTORICAL_M0':
        ledger = bound(binding['data_delivery'])
        if ledger['hospital_display_authorized'] or ledger['external_imaging_upload_authorized']:
            raise ValueError('EXPECTED_ORIGINAL_LOCAL_SCOPE')
        if [row['case_index'] for row in ledger['records']] != [1, 2, 3]: raise ValueError('EXACT_THREE_RECORDS')
        if any(row['upload_scope'] != 'LOCAL_MVP_ONLY_NOT_EXTERNAL_UPLOAD_AUTHORIZATION' for row in ledger['records']):
            raise ValueError('LOCAL_DATA_SCOPE_DRIFT')
        if sorted(row['sha256'] for row in ledger['records']) != sorted(binding['input_sha256']):
            raise ValueError('EXACT_APPROVED_INPUTS_REQUIRED')


def prepare_run(binding, run):
    validate_binding(binding)
    source = Path(binding['source_db']['path'])
    if source.is_symlink() or sha(source) != binding['source_db']['sha256']: raise ValueError('SNAPSHOT_DB_DRIFT')
    run = Path(run); run.mkdir(parents=True, mode=0o700, exist_ok=False)
    shutil.copyfile(source, run / 'backend.sqlite'); (run / 'backend.sqlite').chmod(0o600)
    from argon2 import PasswordHasher
    from sqlalchemy import select, func
    from sqlalchemy.orm import Session
    from backend_v2.db.base import make_engine
    from backend_v2.models.entities import Case, Slice, InferenceJob, InferenceResult, Asset, User, UserCredential, WorkerNode
    from backend_v2.auth.credentials import issue_user_credential
    from backend_v2.services.common import now, aware
    engine = make_engine('sqlite:///' + str(run / 'backend.sqlite'))
    objects = {}; results = []; renewed_inputs = 0
    try:
        with Session(engine) as db:
            slices = db.scalars(select(Slice)).all(); cases = db.scalars(select(Case)).all()
            if len(cases) != 3 or len(slices) != 3 or sorted(sl.source_sha256 for sl in slices) != sorted(binding['input_sha256']):
                raise ValueError('SNAPSHOT_CASE_SCOPE_DRIFT')
            if len({case.owner_user_id for case in cases}) != 1 or any(case.status != 'READY' for case in cases):
                raise ValueError('SNAPSHOT_OWNER_STATE_DRIFT')
            jobs = db.scalars(select(InferenceJob)).all(); rows = db.scalars(select(InferenceResult)).all()
            assets = db.scalars(select(Asset)).all()
            if len(jobs) != 3 or len(rows) != 3 or len(assets) != binding['asset_count']:
                raise ValueError('SNAPSHOT_RESULT_SCOPE_DRIFT')
            if any(job.kind != 'OCCLUSION' or job.status != 'COMPLETED' for job in jobs): raise ValueError('LEGACY_COMPLETED_OCCLUSION_ONLY')
            expires = now() + timedelta(hours=8)
            for sl in slices:
                objects[sl.staging_object_key] = sl.source_sha256
                if sl.staging_expires_at is None or aware(sl.staging_expires_at) < expires:
                    sl.staging_expires_at = expires; renewed_inputs += 1
            for row in rows:
                if row.result_json['contract_version'] != '2.0': raise ValueError('LEGACY_RESULT_ONLY')
                results.append('result_' + row.id.hex)
            for asset in assets: objects[asset.object_key] = asset.sha256
            user = db.get(User, cases[0].owner_user_id)
            for credential in db.scalars(select(UserCredential)): credential.revoked_at = now()
            for worker in db.scalars(select(WorkerNode)): worker.disabled_at = now()
            _, token = issue_user_credential(db, user, expires_in=timedelta(hours=8), label='readonly-local-snapshot')
            subject = user.auth_subject; db.commit()
    finally:
        engine.dispose()
    if sha(source) != binding['source_db']['sha256']: raise ValueError('ORIGINAL_DB_CHANGED_DURING_COPY')
    ports = {}
    for name in ('backend', 'gateway', 'edge'):
        with socket.socket() as sock: sock.bind(('127.0.0.1', 0)); ports[name] = sock.getsockname()[1]
    if len(set(ports.values())) != 3: raise ValueError('PORT_COLLISION_STOP')
    origin = 'https://127.0.0.1:' + str(ports['edge']); password = secrets.token_urlsafe(24)
    private(run / 'user.env', ('export EPILOCATE_USER_TOKEN=' + token + '\n').encode())
    private(run / 'accounts.json', {subject: dict(enabled=True, password_hash=PasswordHasher().hash(password), token_file=str(run / 'user.env'))})
    private(run / 'session.key', secrets.token_bytes(32))
    env = dict(EPILOCATE_V2_DATABASE_URL='sqlite:///' + str(run / 'backend.sqlite'),
               EPILOCATE_V2_ALLOW_ENV_TOKENS='false', EPILOCATE_V2_LEASE_SECRET=secrets.token_hex(32),
               EPILOCATE_GATEWAY_PUBLIC_ORIGIN=origin, EPILOCATE_GATEWAY_BACKEND_ORIGIN='http://127.0.0.1:' + str(ports['backend']),
               EPILOCATE_GATEWAY_ACCOUNTS_FILE=str(run / 'accounts.json'), EPILOCATE_GATEWAY_SESSIONS_FILE=str(run / 'sessions.sqlite'),
               EPILOCATE_GATEWAY_SESSION_KEY_FILE=str(run / 'session.key'))
    config = dict(ports=ports, origin=origin, environment=env, source_objects=binding['source_objects'],
                  object_sha256=objects, results=results, username=subject, password=password,
                  mode=binding['mode'], source_db=binding['source_db'], renewed_input_read_leases=renewed_inputs)
    private(run / 'private-config.json', config)
    return config


class ReadonlyStore:
    def __init__(self, config): self.config = config; self.root = Path(config['source_objects'])
    def read(self, key):
        if not key or Path(key).name != key or key not in self.config['object_sha256']: raise ValueError('OBJECT_OUTSIDE_SNAPSHOT')
        path = self.root / key
        if path.is_symlink(): raise ValueError('OBJECT_SYMLINK')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != self.config['object_sha256'][key]: raise ValueError('OBJECT_SHA_DRIFT')
        return raw, (self.root / (key + '.media')).read_text()
    def put(self, *args): raise ValueError('READ_ONLY_SNAPSHOT')
    def delete(self, *args): raise ValueError('READ_ONLY_SNAPSHOT')


def backend_app(config):
    os.environ.update(config['environment'])
    import backend_v2.api.app as api
    from fastapi import FastAPI, Request
    from starlette.responses import JSONResponse
    api.database_engine.cache_clear()
    api.ObjectStore = lambda: ReadonlyStore(config)
    api.app.state.next_algorithms_enabled = False
    wrapper = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    @wrapper.middleware('http')
    async def read_only(request: Request, call_next):
        if request.method not in {'GET', 'HEAD'} or request.url.path.startswith('/api/v2/workers'):
            return JSONResponse(dict(code='READ_ONLY_LOCAL_SNAPSHOT', message='只读历史结果：新任务和上传已关闭。', retryable=False, details={}), status_code=403)
        response = await call_next(request); response.headers['X-Epilocate-Mode'] = 'READ_ONLY_LOCAL_SNAPSHOT'; return response
    wrapper.mount('/', api.app)
    return wrapper


def static_html(raw):
    banner = b'<aside style="position:fixed;bottom:0;left:0;right:0;z-index:9999;background:#fff;padding:8px;border-top:1px solid #aaa" role="status">' + '本机只读历史结果｜新计算和上传已关闭｜医院展示未获授权'.encode() + b'</aside>'
    return raw.replace(b'</body>', banner + b'</body>')


def child(kind, run, dist):
    config = json.loads((run / 'private-config.json').read_bytes()); os.environ.update(config['environment'])
    if kind in {'backend', 'gateway'}:
        import uvicorn
        if kind == 'backend': app = backend_app(config)
        else:
            from session_gateway.app import create_app
            app = create_app()
        uvicorn.run(app, host='127.0.0.1', port=config['ports'][kind], access_log=False, log_level='warning')
        return
    from qa.phase5_local_https import Edge
    class SnapshotEdge(Edge):
        def route(self):
            if self.command not in {'GET', 'HEAD'} and not (self.command == 'POST' and self.path in {'/auth/login', '/auth/logout'}):
                self.send_error(403, 'Read-only local snapshot'); return
            if self.path.startswith(('/api/v2/workers', '/generated-object/')): self.send_error(403); return
            return super().route()
        def static(self):
            if self.path.startswith('/mvp/'): self.path = self.path[len('/mvp'):]
            if self.path.split('?', 1)[0] in {'/favicon.svg'} or '/assets/' in self.path: return super().static()
            raw = static_html((self.server.static_root / 'index.html').read_bytes())
            self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.send_header('Content-Length', str(len(raw))); self.end_headers()
            if self.command != 'HEAD': self.wfile.write(raw)
    server = ThreadingHTTPServer(('127.0.0.1', config['ports']['edge']), SnapshotEdge)
    server.kind = 'browser'; server.backend = config['ports']['backend']; server.gateway = config['ports']['gateway']; server.static_root = dist.resolve()
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); tls.load_cert_chain(run / 'tls.crt', run / 'tls.key'); server.socket = tls.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


def serve(binding, run, dist):
    config = prepare_run(binding, run)
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(run/'tls.key'), '-out', str(run/'tls.crt'),
                    '-days', '3', '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (run/'tls.key').chmod(0o600); processes=[]; logs=[]
    def interrupted(*_): raise KeyboardInterrupt()
    old_handlers = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        for kind in ('backend', 'gateway', 'edge'):
            log=(run/(kind+'.log')).open('xb'); logs.append(log)
            processes.append(subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--child', kind, '--run-directory', str(run), '--dist', str(dist)],
                                               cwd=ROOT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1'), stdout=log, stderr=log))
        import httpx
        deadline = time.monotonic() + 15
        with httpx.Client(verify=ssl.create_default_context(cafile=str(run/'tls.crt')), trust_env=False, timeout=1) as client:
            while True:
                if any(p.poll() is not None for p in processes): raise RuntimeError('OWN_RESTORE_SERVICE_EXITED')
                try:
                    if (client.get('http://127.0.0.1:'+str(config['ports']['backend'])+'/api/v2/cases').status_code==401
                            and client.get(config['origin']+'/auth/session').status_code==401): break
                except httpx.HTTPError: pass
                if time.monotonic() >= deadline: raise RuntimeError('RESTORE_STARTUP_NOT_READY')
                time.sleep(.05)
        private(run/'restore-ready.json', dict(mode='READ_ONLY_LOCAL_SNAPSHOT', service_count=3, model_calls=0, worker_started=False))
        print(json.dumps(dict(mode='READ_ONLY_LOCAL_SNAPSHOT', url=config['origin']+'/mvp/', credentials_path=str(run/'private-config.json'), model_calls=0)), flush=True)
        while True:
            if any(p.poll() is not None for p in processes): raise RuntimeError('OWN_RESTORE_SERVICE_EXITED')
            time.sleep(.25)
    except KeyboardInterrupt:
        pass
    finally:
        for p in processes:
            if p.poll() is None:
                p.terminate()
                try: p.wait(timeout=3)
                except subprocess.TimeoutExpired: p.kill(); p.wait(timeout=3)
        for log in logs: log.close()
        private(run/'restore-exit.json', dict(owned_services=[dict(pid=p.pid,exit_code=p.returncode) for p in processes],
                                             source_db_unchanged=sha(binding['source_db']['path'])==binding['source_db']['sha256'], model_calls=0, worker_started=False))
        for sig, previous in old_handlers.items(): signal.signal(sig, previous)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding',type=Path);parser.add_argument('--binding-sha');parser.add_argument('--run-directory',type=Path)
    parser.add_argument('--dist',type=Path);parser.add_argument('--serve',action='store_true');parser.add_argument('--child',choices=['backend','gateway','edge'])
    args=parser.parse_args()
    if args.child:
        child(args.child,args.run_directory.resolve(),args.dist.resolve());return
    if not args.binding or not args.binding_sha: parser.error('exact binding path/SHA required')
    binding=bound(dict(path=str(args.binding),sha256=args.binding_sha));validate_binding(binding)
    if not args.serve:
        print(json.dumps(dict(status='METADATA_CHECK_ONLY',model_calls=0,service_starts=0,source_db_or_images_read=False)));return
    if not args.run_directory or not args.dist or not args.run_directory.resolve().is_relative_to(ROOT/'.local'):
        parser.error('new task-local private run and existing dist required')
    if args.dist.resolve()!=Path(binding['dist']).resolve(): parser.error('bound dist required')
    serve(binding,args.run_directory.resolve(),args.dist.resolve())


if __name__=='__main__': main()
