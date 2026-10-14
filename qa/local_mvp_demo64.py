"""Restricted historical-result candidate. Default CLI is metadata-only.

The legacy reader, DB, object files and v16 dist remain immutable. Actual serve
requires a separately authorized use; a frozen candidate is not that approval.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qa import local_mvp_readonly as legacy
from qa.demo64_policy import derive, validate


def checked(reference):
    frozen = legacy.bound(reference)
    if frozen['schema'] != 'MVP_DEMO64_FROZEN_CANDIDATE_V1':
        raise ValueError('FROZEN_CANDIDATE_REQUIRED')
    policy = legacy.bound(frozen['policy'])
    validate(policy)
    if policy != derive(policy['original_binding'], policy['inventory']):
        raise ValueError('ORIGINAL_INVENTORY_PROJECTION_DRIFT')
    for path, digest in frozen['source_sha256'].items():
        if legacy.sha(path) != digest:
            raise ValueError('DEMO_SOURCE_DRIFT')
    if str(Path(__file__).resolve()) not in frozen['source_sha256']:
        raise ValueError('DEMO_ENTRY_NOT_BOUND')
    if str(Path(sys.executable).resolve()) != frozen['runtime']['resolved_python']:
        raise ValueError('DEMO_PYTHON_DRIFT')
    for ref in frozen['runtime']['references']:
        if legacy.sha(ref['path']) != ref['sha256']:
            raise ValueError('DEMO_RUNTIME_REFERENCE_DRIFT')
    dist = Path(frozen['dist'])
    actual = {str(p.relative_to(dist)): legacy.sha(p) for p in dist.rglob('*') if p.is_file()}
    if actual != frozen['dist_sha256'] or 'index.html' not in actual:
        raise ValueError('DEMO_DIST_DRIFT')
    return frozen, policy


def restrict_config(config, policy):
    """Match the copied DB metadata before publishing any restricted service."""
    validate(policy)
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from backend_v2.db.base import make_engine
    from backend_v2.models.entities import InferenceResult, InferenceJob, Slice, Asset
    engine = make_engine(config['environment']['EPILOCATE_V2_DATABASE_URL'])
    objects = {}
    try:
        with Session(engine) as db:
            if set(config['results']) != {r['result_id'] for r in policy['records']}:
                raise ValueError('RESULT_SET_DRIFT')
            for expected in policy['records']:
                row = next((x for x in db.scalars(select(InferenceResult))
                            if 'result_' + x.id.hex == expected['result_id']), None)
                if row is None: raise ValueError('MISSING_RESULT')
                job = db.get(InferenceJob, row.job_id)
                sl = db.get(Slice, job.slice_id)
                if (job.public_id != expected['job_id'] or sl.slice_ref != expected['slice_id']
                        or sl.source_sha256 != expected['input_sha256']):
                    raise ValueError('INPUT_IDENTITY_DRIFT')
                filter_result(dict(row.result_json, result_id=expected['result_id'],
                                   job_id=job.public_id, provenance=dict(input_sha256=sl.source_sha256)), expected, policy)
                objects[sl.staging_object_key] = sl.source_sha256
                for aid, ref in expected['assets'].items():
                    asset = db.scalar(select(Asset).where(Asset.result_id == row.id, Asset.asset_id == aid))
                    if asset is None or (asset.object_key, asset.sha256) != (ref['object_key'], ref['sha256']):
                        raise ValueError('ASSET_BINDING_DRIFT')
                    objects[asset.object_key] = asset.sha256
    finally:
        engine.dispose()
    if len(objects) != 12 or any(config['object_sha256'].get(k) != v for k, v in objects.items()):
        raise ValueError('OBJECT_SET_DRIFT')
    restricted = copy.deepcopy(config)
    restricted['object_sha256'] = objects
    restricted['demo64_policy'] = policy
    return restricted


def filter_result(body, expected, policy):
    if any(body.get(k) != expected[k] for k in ('result_id', 'job_id', 'case_id', 'slice_id')):
        raise ValueError('RESULT_IDENTITY_DRIFT')
    model = policy['model']
    if (body.get('kind') != 'OCCLUSION' or body.get('contract_version') != '2.0'
            or body.get('model_id') != model['model_id']
            or body.get('model_version') != model['checkpoint_sha256']
            or body.get('preprocessing_version') != model['preprocessing_version']
            or body.get('protocol_id') != model['protocol_id']
            or body.get('provenance', {}).get('input_sha256') != expected['input_sha256']):
        raise ValueError('RESULT_MODEL_DRIFT')
    summaries = [x for x in body['scale_summaries'] if x['block_size'] == 64]
    if len(summaries) != 1 or {summaries[0][k]['asset_id'] for k in
            ('candidate_layer', 'response_layer', 'comparison_grid_layer')} != set(expected['assets']):
        raise ValueError('RESULT_64_LAYER_DRIFT')
    # An explicit response projection prevents auxiliary fields leaking 16/32 data.
    keys = ('result_id', 'job_id', 'case_id', 'slice_id', 'kind', 'contract_version',
            'model_id', 'model_version', 'preprocessing_version', 'protocol_id',
            'prediction', 'source', 'status', 'created_at', 'provenance')
    result = {k: body[k] for k in keys if k in body}
    result.update(scale_summaries=summaries, cross_scale=[],
                  assets=[a for a in body.get('assets', []) if a['asset_id'] in expected['assets']])
    return result


def backend_app(config):
    from fastapi import FastAPI, Request
    from starlette.responses import JSONResponse
    policy = config['demo64_policy']; validate(policy)
    inner = legacy.backend_app(config)
    wrapper = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    paths = {}
    for row in policy['records']:
        paths['/api/v2/results/' + row['result_id']] = ('result', row)
        paths['/api/v2/cases/' + row['case_id']] = ('case', row)
        paths['/api/v2/cases/' + row['case_id'] + '/dicom'] = ('binary', row)
        for aid in row['assets']:
            paths['/api/v2/results/' + row['result_id'] + '/assets/' + aid] = ('binary', row)

    def refused():
        return JSONResponse(dict(code='DEMO64_SCOPE', message='仅限固定历史切片与64尺度图层。',
                                 retryable=False, details={}), status_code=403)

    @wrapper.middleware('http')
    async def scope(request: Request, call_next):
        selected = paths.get(request.url.path)
        if request.method not in {'GET', 'HEAD'} or selected is None or request.url.query:
            return refused()
        response = await call_next(request)
        if response.status_code == 200 and selected[0] in {'result', 'case'}:
            raw = b''.join([chunk async for chunk in response.body_iterator])
            try:
                body = json.loads(raw)
                kind, row = selected
                if kind == 'result':
                    body = filter_result(body, row, policy)
                    if {a['asset_id'] for a in body['assets']} != set(row['assets']):
                        return refused()
                else:
                    slices = [sl for study in body['studies'] for series in study['series'] for sl in series['slices']]
                    if body['case_id'] != row['case_id'] or len(slices) != 1 or slices[0]['slice_id'] != row['slice_id']:
                        return refused()
                response = JSONResponse(body, headers={'Cache-Control': 'private,no-store'})
            except (ValueError, KeyError, TypeError):
                return refused()
        response.headers['X-Epilocate-Mode'] = 'DEMO64_HISTORICAL_ONLY'
        return response
    wrapper.mount('/', inner)
    return wrapper


def child(kind, run, dist):
    if kind == 'edge':
        # Built Vue/codec modules arrive in a parallel burst; stdlib backlog=5
        # can reset TLS connections before a handler can accept them.
        class CandidateHTTPServer(legacy.ThreadingHTTPServer):
            request_queue_size = 64
            def serve_forever(self, *args, **kwargs):
                # A browser preconnect must not hold the single accept loop in
                # TLS handshake. The existing handler thread performs it on IO.
                self.socket.do_handshake_on_connect = False
                return super().serve_forever(*args, **kwargs)
        legacy.ThreadingHTTPServer = CandidateHTTPServer
        return legacy.child(kind, run, dist)
    import uvicorn
    config = json.loads((run / 'private-config.json').read_bytes())
    os.environ.update(config['environment'])
    if kind == 'backend':
        app = backend_app(config)
    else:
        import httpx
        from session_gateway.app import create_app
        class CandidateTransport(httpx.AsyncBaseTransport):
            """Authenticate against an exact result; never reopen case listing."""
            async def handle_async_request(self, request):
                if request.url.path == '/api/v2/cases' and request.url.query == b'limit=1':
                    request.url = request.url.copy_with(path='/api/v2/results/'+config['results'][0], query=None)
                async with httpx.AsyncHTTPTransport() as transport:
                    response = await transport.handle_async_request(request)
                    await response.aread()
                    return response
        app = create_app(backend_transport=CandidateTransport())
        @app.middleware('http')
        async def deny_public_probe(request, call_next):
            # The transport rewrite is solely for login's internal token probe.
            # A browser/direct gateway caller must not enter that special seam.
            if request.url.path.rstrip('/') == '/api/v2/cases':
                from starlette.responses import JSONResponse
                return JSONResponse({'code': 'DEMO64_SCOPE'}, status_code=403)
            return await call_next(request)
    uvicorn.run(app, host='127.0.0.1', port=config['ports'][kind],
                access_log=False, log_level='warning')


def serve(frozen, policy, run):
    config = legacy.prepare_run(legacy.bound(policy['original_binding']), run)
    config = restrict_config(config, policy)
    # Only the new task-owned private config is replaced; original DB/objects stay intact.
    temp = run / 'restricted-config.json'; legacy.private(temp, config)
    os.replace(temp, run / 'private-config.json')
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(run/'tls.key'),
                    '-out', str(run/'tls.crt'), '-days', '3', '-subj', '/CN=127.0.0.1',
                    '-addext', 'subjectAltName=IP:127.0.0.1'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (run/'tls.key').chmod(0o600)
    processes = []; logs = []
    def interrupted(*_): raise KeyboardInterrupt()
    previous = {s: signal.signal(s, interrupted) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        for kind in ('backend', 'gateway', 'edge'):
            log = (run/(kind+'.log')).open('xb'); logs.append(log)
            processes.append(subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--child', kind,
                '--run-directory', str(run), '--dist', frozen['dist']], cwd=ROOT,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1'),
                stdout=log, stderr=log))
        import httpx
        deadline = time.monotonic()+15
        with httpx.Client(verify=str(run/'tls.crt'), trust_env=False, timeout=1) as client:
            while True:
                if any(p.poll() is not None for p in processes): raise RuntimeError('OWN_SERVICE_EXITED')
                try:
                    if client.get(config['origin']+'/auth/session').status_code == 401:
                        probe = client.get('http://127.0.0.1:'+str(config['ports']['backend'])+
                                           '/api/v2/results/'+config['results'][0])
                        if probe.status_code == 401: break
                except httpx.HTTPError: pass
                if time.monotonic() >= deadline: raise TimeoutError('STARTUP_DEADLINE')
                time.sleep(.05)
        legacy.private(run/'restore-ready.json', dict(mode='DEMO64_HISTORICAL_ONLY', model_calls=0, worker_started=False))
        print(json.dumps(dict(url=config['origin']+'/mvp/', credentials_path=str(run/'private-config.json'))), flush=True)
        while True:
            if any(p.poll() is not None for p in processes): raise RuntimeError('OWN_SERVICE_EXITED')
            time.sleep(.25)
    except KeyboardInterrupt: pass
    finally:
        for p in reversed(processes):
            if p.poll() is None:
                p.terminate()
                try: p.wait(timeout=3)
                except subprocess.TimeoutExpired: p.kill(); p.wait(timeout=3)
        for log in logs: log.close()
        legacy.private(run/'restore-exit.json', dict(owned_services=[dict(pid=p.pid,exit_code=p.returncode) for p in processes],
            source_db_unchanged=legacy.sha(config['source_db']['path'])==config['source_db']['sha256'], model_calls=0, worker_started=False))
        for s, handler in previous.items(): signal.signal(s, handler)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate'); p.add_argument('--candidate-sha'); p.add_argument('--serve', action='store_true')
    p.add_argument('--run-directory', type=Path); p.add_argument('--dist', type=Path)
    p.add_argument('--child', choices=('backend','gateway','edge')); a = p.parse_args()
    if a.child:
        child(a.child, a.run_directory, a.dist)
    else:
        if not a.candidate or not a.candidate_sha: p.error('exact candidate path/SHA required')
        frozen, policy = checked(dict(path=a.candidate, sha256=a.candidate_sha))
        if not a.serve:
            print(json.dumps(dict(status='CANDIDATE_METADATA_PASS', model_calls=0, services=0, payload_read=False)))
        else:
            if not a.run_directory or not a.run_directory.resolve().is_relative_to(ROOT/'.local'):
                p.error('new task-local run directory required')
            serve(frozen, policy, a.run_directory.resolve())
