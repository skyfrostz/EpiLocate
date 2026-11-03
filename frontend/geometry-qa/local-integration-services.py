"""Ephemeral loopback services: real Gateway/Backend, SQLite, TEST_STORAGE.

Never reads deployed settings. Never creates a Worker, inference result, or model
checkpoint. This is an integration harness, not deployment configuration.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time
from datetime import timedelta

ROOT = Path(__file__).resolve().parents[2]


def ports():
    base = int(os.environ.get('CANVAS_QA_PORT_BASE', '5197'))
    return dict(vite=base, preview=base + 1, backend=base + 2, gateway=base + 3)


def private(path, data):
    path.write_bytes(data)
    path.chmod(0o600)
    return path


class TestFileStore:
    """Explicit test adapter. Does not exercise S3/MinIO or signed URLs."""
    def __init__(self):
        self.root = Path(os.environ['CANVAS_QA_RUN']) / 'objects'
        self.root.mkdir(exist_ok=True, mode=0o700)

    def put(self, body, media, prefix):
        key = prefix + '-' + secrets.token_hex(24)
        private(self.root / key, body)
        return key

    def read(self, key):
        if Path(key).name != key:
            raise ValueError('Invalid test object key')
        return (self.root / key).read_bytes(), 'application/dicom'

    def delete(self, key):
        (self.root / key).unlink(missing_ok=True)


def child_app(kind):
    if kind == 'backend':
        import backend_v2.api.app as backend
        backend.ObjectStore = TestFileStore
        return backend.app
    if kind == 'gateway':
        from session_gateway.app import create_app
        return create_app()
    from fastapi import FastAPI, Request
    from starlette.responses import Response
    import httpx
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.api_route('/{path:path}', methods=['GET', 'POST'])
    async def serve(path: str, request: Request):
        if path.startswith(('auth/', 'api/v2/')):
            headers = {key: value for key, value in request.headers.items()
                       if key.lower() not in {'host', 'connection', 'content-length'}}
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
                upstream = await client.request(request.method,
                    f'http://127.0.0.1:{ports()["gateway"]}/' + path, params=request.query_params,
                    content=await request.body(), headers=headers)
            outgoing = {key: value for key, value in upstream.headers.items()
                        if key.lower() in {'content-type', 'set-cookie', 'cache-control'}}
            return Response(upstream.content, status_code=upstream.status_code, headers=outgoing)
        if not path.startswith('mvp/'):
            return Response(status_code=404)
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
            upstream = await client.get(f'http://127.0.0.1:{ports()["vite"]}/' + path, params=request.query_params)
        return Response(upstream.content, status_code=upstream.status_code,
            headers={key:value for key,value in upstream.headers.items()
                     if key.lower() in {'content-type','cache-control','etag'}})

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--dist', type=Path, required=True)
    parser.add_argument('--port-base', type=int, default=5197,
                        help='First of four consecutive loopback ports (Vite, HTTPS, Backend, Gateway)')
    parser.add_argument('--child', choices=['backend', 'gateway', 'preview'])
    args = parser.parse_args()
    if not 1024 <= args.port_base <= 65532:
        parser.error('--port-base must leave room for four nonprivileged ports')
    os.environ['CANVAS_QA_PORT_BASE'] = str(args.port_base)
    run = args.run.resolve()
    if not run.is_relative_to(ROOT / 'frontend/.local'):
        parser.error('Run directory must be inside frontend/.local')
    if args.child:
        import uvicorn
        options = dict(host='127.0.0.1', port=ports()[args.child], access_log=False, log_level='warning')
        if args.child == 'preview':
            options.update(ssl_keyfile=str(run/'tls.key'), ssl_certfile=str(run/'tls.crt'))
        uvicorn.run(child_app(args.child), **options)
        return

    run.mkdir(mode=0o700, exist_ok=True)
    run.chmod(0o700)
    if (run/'backend.sqlite').exists():
        parser.error('Use a fresh run directory; existing test databases are preserved')

    # Only newly generated settings; inherited deployment/database secrets excluded.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('EPILOCATE_', 'AWS_', 'VITE_', 'API_PROXY_', 'CANVAS_QA_'))}
    env.update(PYTHONPATH=str(ROOT), CANVAS_QA_RUN=str(run), CANVAS_QA_DIST=str(args.dist.resolve()), VITE_PUBLIC_BASE='/mvp/',
        EPILOCATE_V2_DATABASE_URL='sqlite:///' + str(run/'backend.sqlite'),
        EPILOCATE_V2_LEASE_SECRET=secrets.token_hex(32),
        EPILOCATE_V2_ALLOW_ENV_TOKENS='false',
        EPILOCATE_GATEWAY_PUBLIC_ORIGIN=f'https://127.0.0.1:{ports()["preview"]}',
        EPILOCATE_GATEWAY_BACKEND_ORIGIN=f'http://127.0.0.1:{ports()["backend"]}',
        EPILOCATE_GATEWAY_ACCOUNTS_FILE=str(run/'accounts.json'),
        EPILOCATE_GATEWAY_SESSIONS_FILE=str(run/'sessions.sqlite'),
        EPILOCATE_GATEWAY_SESSION_KEY_FILE=str(run/'session.key'))
    os.environ.update(env)
    sys.path.insert(0, str(ROOT))
    from argon2 import PasswordHasher
    from sqlalchemy.orm import Session
    from backend_v2.db.base import Base, make_engine
    from backend_v2.models.entities import User, ModelVersion
    from backend_v2.auth.credentials import issue_user_credential
    engine = make_engine(env['EPILOCATE_V2_DATABASE_URL'])
    Base.metadata.create_all(engine)  # SQLite test schema, not Alembic acceptance.
    records, credentials = {}, {}
    with Session(engine) as db:
        for username in ['qa_alice', 'qa_bob']:
            user = User(auth_subject=username)
            db.add(user); db.flush()
            _, token = issue_user_credential(db, user, expires_in=timedelta(hours=2))
            token_file = private(run/(username+'.env'), ('export EPILOCATE_USER_TOKEN='+token+'\n').encode())
            password = secrets.token_urlsafe(24)
            records[username] = dict(password_hash=PasswordHasher().hash(password), token_file=str(token_file), enabled=True)
            credentials[username] = password
        db.add(ModelVersion(model_id='baseline_resnet18',
            version='LOCAL_QA_METADATA_ONLY_NO_CHECKPOINT',
            checkpoint_sha256='548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734',
            preprocessing_version='formal-resnet18-baseline-rule-b-v1',
            protocol_id='stage1-occlusion-instability-v1'))
        db.commit()
    engine.dispose()
    private(run/'accounts.json', json.dumps(records).encode())
    private(run/'browser-credentials.json', json.dumps(credentials).encode())
    private(run/'session.key', secrets.token_bytes(32))
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(run/'tls.key'),
        '-out',str(run/'tls.crt'),'-days','1','-subj','/CN=127.0.0.1',
        '-addext','subjectAltName=IP:127.0.0.1'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (run/'tls.key').chmod(0o600)
    children, handles = {}, []
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        handle = (run/'vite-preview-service.log').open('w'); handles.append(handle)
        children['vite-preview'] = subprocess.Popen(['npm','run','preview','--','--host','127.0.0.1',
            '--port',str(ports()['vite']),'--strictPort','--outDir',str(args.dist.resolve())],
            cwd=ROOT/'frontend',env=env,stdout=handle,stderr=handle,start_new_session=True)
        for kind in ['backend','gateway','preview']:
            handle = (run/(kind+'-service.log')).open('w'); handles.append(handle)
            children[kind] = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                '--run',str(run),'--dist',str(args.dist.resolve()),'--port-base',str(args.port_base),'--child',kind],
                cwd=ROOT, env=env, stdout=handle, stderr=handle,start_new_session=True)
        private(run/'service-pids.json', json.dumps({kind:p.pid for kind,p in children.items()}).encode())
        print(f'LOCAL_INTEGRATION: HTTPS {ports()["preview"]} -> Vite production preview {ports()["vite"]}; real Gateway {ports()["gateway"]}, Backend {ports()["backend"]}; SQLite + TEST_STORAGE; zero Workers/results.', flush=True)
        while all(p.poll() is None for p in children.values()):
            time.sleep(0.5)
        # Browser deliberately stops Backend for the final outage check.
        while children['preview'].poll() is None and children['gateway'].poll() is None:
            time.sleep(0.5)
    finally:
        for p in children.values():
            try: os.killpg(p.pid,signal.SIGTERM)
            except ProcessLookupError: pass
        for p in children.values():
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired: p.kill(); p.wait()
        for handle in handles: handle.close()
        print('Local integration services stopped.', flush=True)


if __name__ == '__main__':
    main()
