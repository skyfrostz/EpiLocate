"""One owner-confirmed technical check. No screenshot, video, trace or pixel export."""

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[1]
import io
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit
ROOT = Path(str(_PUBLIC_ROOT / '.'))
sys.path.insert(0, str(ROOT))
from qa import local_mvp_readonly as legacy
from qa.local_mvp_demo64 import checked
from qa.demo64_readiness import wait_ready, PROBE
from qa.technical_evidence import Evidence
CANDIDATE = dict(path=str(ROOT / '.local/demo64-candidate-20261013/frozen-candidate-v1.json'), sha256='0000000000000000000000000000000000000000000000000000000000000000')
OUTPUT = ROOT / '.local/demo64-technical-20261013-02'
CORE = '/mvp/assets/esm-BQ03oNGD.js'

def browse(run, evidence, log):
    from playwright.sync_api import sync_playwright, expect
    import pydicom
    config = json.loads((run / 'private-config.json').read_bytes())
    policy = config['demo64_policy']
    deadline = time.monotonic() + 140
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--disable-background-networking', '--disable-sync'])
        try:
            context = browser.new_context(ignore_https_errors=True, viewport={'width': 1440, 'height': 1000})

            def route(r):
                u = urlsplit(r.request.url)
                if u.scheme in {'blob', 'data'} or (u.scheme == 'https' and u.netloc == urlsplit(config['origin']).netloc):
                    r.continue_()
                else:
                    evidence['external_requests'] += 1
                    r.abort()
            context.route('**/*', route)
            context.add_init_script(path=str(PROBE))
            context.add_init_script("(() => {const old=CanvasRenderingContext2D.prototype.drawImage;\n              window.__overlaySequence=0;window.__overlayGeometry=null;\n              CanvasRenderingContext2D.prototype.drawImage=function(...a){const out=old.apply(this,a);\n                if(this.canvas.getAttribute('aria-label')==='模型响应叠加图层') {const m=this.getTransform();\n                  window.__overlayGeometry={sequence:++window.__overlaySequence,matrix:[m.a,m.b,m.c,m.d,m.e,m.f],\n                    imageWidth:a[0].naturalWidth,imageHeight:a[0].naturalHeight,canvasWidth:this.canvas.width,canvasHeight:this.canvas.height};}\n                return out;};})();")
            page = context.new_page()
            page.set_default_timeout(12000)
            page.on('pageerror', lambda e: evidence['page_errors'].append(type(e).__name__))
            page.goto(config['origin'] + '/mvp/', wait_until='domcontentloaded')
            page.get_by_label('账号', exact=True).fill(config['username'])
            page.get_by_label('密码', exact=True).fill(config['password'])
            page.get_by_role('button', name='登录', exact=True).click()
            log.step('expect_01', status='STARTED')
            expect(page.get_by_role('heading', name='历史结果查看', exact=True)).to_be_visible()
            log.step('expect_01', status='PASS')
            evidence['checks']['login'] = 'PASS'
            log.step('login',status='PASS')
            for row in policy['records']:
                log.step('assert_02', status='STARTED')
                assert time.monotonic() < deadline
                log.step('assert_02', status='PASS')
                page.goto(config['origin'] + '/mvp/results/' + row['result_id'], wait_until='domcontentloaded')
                log.step('expect_03', status='STARTED')
                expect(page.get_by_role('heading', name='结果工作区', exact=True)).to_be_visible()
                log.step('expect_03', status='PASS')
                response = page.request.get(config['origin'] + '/api/v2/results/' + row['result_id'])
                log.step('assert_04', status='STARTED')
                assert response.status == 200
                log.step('assert_04', status='PASS')
                body = response.json()
                log.step('assert_05', status='STARTED')
                assert len(body['scale_summaries']) == 1 and body['scale_summaries'][0]['block_size'] == 64
                log.step('assert_05', status='PASS')
                log.step('assert_06', status='STARTED')
                assert {a['asset_id'] for a in body['assets']} == set(row['assets'])
                log.step('assert_06', status='PASS')
                log.step('assert_07', status='STARTED')
                assert page.locator('.scale-switch button').all_text_contents() == ['64 px']
                log.step('assert_07', status='PASS')
                original = page.request.get(config['origin'] + '/api/v2/cases/' + row['case_id'] + '/dicom')
                log.step('assert_08', status='STARTED')
                assert original.status == 200
                log.step('assert_08', status='PASS')
                raw = original.body()
                import hashlib
                log.step('assert_09', status='STARTED')
                assert hashlib.sha256(raw).hexdigest() == row['input_sha256']
                log.step('assert_09', status='PASS')
                ds = pydicom.dcmread(io.BytesIO(raw), stop_before_pixels=True)
                del raw
                width, height = (int(ds.Columns), int(ds.Rows))
                ipp = [float(x) for x in ds.ImagePositionPatient]
                iop = [float(x) for x in ds.ImageOrientationPatient]
                spacing = [float(x) for x in ds.PixelSpacing]
                expected_ready = dict(coreUrl=CORE, pathname='/mvp/results/' + row['result_id'], width=width, height=height)
                readiness = wait_ready(page, expected_ready)
                log.step('current_image_rendered', case_index=row['case_index'], status='PASS', probe=readiness)
                hint = page.get_by_text('单切片 DICOM 已恢复。支持平移、缩放和重置；当前未提供窗宽窗位工具。', exact=True)
                log.step('auxiliary_hint', count=hint.count(), visible=hint.is_visible() if hint.count() == 1 else None)
                flow = dict(case_index=row['case_index'], input_sha256=row['input_sha256'], native_size=[width, height], native_IPP=ipp, native_IOP=iop, native_spacing=spacing, layers=[])
                evidence['flows'].append(flow)
                for label, aid in [('响应图', 'response-64.png'), ('候选区域', 'candidate-64.png'), ('64 px 区域均值', 'comparison-64.png')]:
                    log.step('assert_10', status='STARTED')
                    assert time.monotonic() < deadline
                    log.step('assert_10', status='PASS')
                    previous = page.evaluate('window.__overlaySequence || 0')
                    page.get_by_role('button', name=label, exact=True).click()
                    overlay = page.get_by_label('显示叠加', exact=True)
                    summary = body['scale_summaries'][0]
                    if aid == 'candidate-64.png' and summary['candidate_status'] != 'valid':
                        flow['layers'].append(dict(asset_id=aid, status='NONVALID_CANDIDATE_OVERLAY_DISABLED'))
                        continue
                    log.step('expect_11', status='STARTED')
                    expect(overlay).to_be_enabled()
                    log.step('expect_11', status='PASS')
                    overlay.check()
                    log.step('expect_12', status='STARTED')
                    expect(page.get_by_text('像素校验通过', exact=True)).to_be_visible()
                    log.step('expect_12', status='PASS')
                    size = 14 if aid.startswith('comparison') else 224
                    page.wait_for_function('([s,n])=>window.__overlayGeometry?.imageWidth===s && window.__overlayGeometry.sequence>n', arg=[size, previous])
                    asset_url = page.locator('.heatmap-frame img').get_attribute('src')
                    log.step('assert_13', status='STARTED')
                    assert asset_url
                    log.step('assert_13', status='PASS')
                    layer_ready = wait_ready(page, dict(expected_ready, assetUrl=asset_url, assetSize=size))
                    log.step('current_asset_rendered', case_index=row['case_index'], asset_id=aid, probe=layer_ready, status='PASS')
                    captured = page.evaluate('async url=>{const core=(await import(url)).t;\n                      const v=core.getRenderingEngines()[0].getViewports()[0];const d=v.getImageData();\n                      const el=v.element;const r=el.getBoundingClientRect();\n                      return {camera:v.getCamera(),rotation:v.getRotation(),zoom:v.getZoom(),pan:v.getPan(),\n                        image:{dimensions:d.dimensions,origin:d.origin,spacing:d.spacing,direction:d.direction},\n                        viewport:{width:el.clientWidth,height:el.clientHeight,x:r.x,y:r.y},dpr:devicePixelRatio,overlay:window.__overlayGeometry};} ', CORE)
                    camera = captured['camera']
                    vp = captured['viewport']
                    m = captured['overlay']['matrix']
                    dpr = captured['dpr']
                    n = camera['viewPlaneNormal']
                    up = camera['viewUp']
                    focal = camera['focalPoint']
                    right = [up[1] * n[2] - up[2] * n[1], up[2] * n[0] - up[0] * n[2], up[0] * n[1] - up[1] * n[0]]
                    factor = vp['height'] / (2 * camera['parallelScale'])
                    points = []
                    for mx, my in [(0, 0), (224, 0), (0, 224), (224, 224), (112, 112), (32, 32), (96, 96)]:
                        x, y = (mx * width / 224, my * height / 224)
                        world = [ipp[k] + (x - 0.5) * spacing[1] * iop[k] + (y - 0.5) * spacing[0] * iop[k + 3] for k in range(3)]
                        delta = [world[k] - focal[k] for k in range(3)]
                        ex = vp['width'] / 2 + sum((delta[k] * right[k] for k in range(3))) * factor
                        ey = vp['height'] / 2 - sum((delta[k] * up[k] for k in range(3))) * factor
                        ox = (m[0] * x + m[2] * y + m[4]) / dpr
                        oy = (m[1] * x + m[3] * y + m[5]) / dpr
                        points.append(dict(model_edge=[mx, my], native_edge=[x, y], expected_css=[ex, ey], actual_overlay_css=[ox, oy], error_css_px=math.hypot(ex - ox, ey - oy)))
                    maximum = max((p['error_css_px'] for p in points))
                    flow['layers'].append(dict(asset_id=aid, status='PASS' if maximum <= 0.5 else 'MAPPING_MISMATCH', max_css_error=maximum, points=points, viewport=captured))
                    log.step('assert_14', status='STARTED')
                    assert maximum <= 0.5, 'INDEPENDENT_SPACE_MAPPING_MISMATCH'
                    log.step('assert_14', status='PASS')
                    asset = page.request.get(config['origin'] + '/api/v2/results/' + row['result_id'] + '/assets/' + aid)
                    log.step('assert_15', status='STARTED')
                    assert asset.status == 200
                    log.step('assert_15', status='PASS')
                    log.step('assert_16', status='STARTED')
                    assert hashlib.sha256(asset.body()).hexdigest() == row['assets'][aid]['sha256']
                    log.step('assert_16', status='PASS')
                page.reload()
                log.step('expect_17', status='STARTED')
                expect(page.get_by_role('button', name='64 px', exact=True)).to_have_attribute('aria-pressed', 'true')
                log.step('expect_17', status='PASS')
                log.step('expect_18', status='STARTED')
                expect(page.get_by_text('像素校验通过', exact=True)).to_be_visible()
                log.step('expect_18', status='PASS')
                wait_ready(page, expected_ready)
                log.step('assert_19', status='STARTED')
                assert page.request.get(config['origin'] + '/api/v2/results/' + row['result_id']).json() == body
                log.step('assert_19', status='PASS')
                flow['refresh'] = 'PASS'
                url = config['origin'] + '/api/v2/results/' + row['result_id']
                for path in [url + '/assets/response-16.png', url + '/assets/candidate-32.png', url + '?scale=16', config['origin'] + '/api/v2/results/other', config['origin'] + '/api/v2/cases?limit=1']:
                    log.step('assert_20', status='STARTED')
                    assert page.request.get(path).status == 403
                    log.step('assert_20', status='PASS')
            for path in ['/api/v2/cases', '/api/v2/jobs/occlusion', '/api/v2/jobs/algorithm', '/api/v2/workers/claim']:
                log.step('assert_21', status='STARTED')
                assert page.request.post(config['origin'] + path, data={}).status == 403
                log.step('assert_21', status='PASS')
            log.step('assert_22', status='STARTED')
            assert page.request.get(config['origin'] + '/generated-object/anything').status == 403
            log.step('assert_22', status='PASS')
            evidence['checks'].update(three_results='PASS', only64='PASS', refresh='PASS', scope_denials='PASS', independent_space='PASS')
            log.step('assert_23', status='STARTED')
            assert not evidence['external_requests'] and (not evidence['page_errors'])
            log.step('assert_23', status='PASS')
            context.close()
        finally:
            try:
                browser.close()
                evidence['browser_closed'] = True
                log.step('browser_closed', status='PASS')
            except BaseException as error:
                log.failure(error, cleanup=True)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    for name in ('request', 'request-sha'):
        parser.add_argument('--' + name, required=True)
    for name in ('confirmation', 'confirmation-sha'):
        parser.add_argument('--' + name)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    request = legacy.bound(dict(path=args.request, sha256=args.request_sha))
    if request['candidate'] != CANDIDATE or request['output'] != str(OUTPUT):
        raise ValueError('TECHNICAL_SCOPE_DRIFT')
    for reference in request['driver_bindings'] + request['browser_runtime']:
        if legacy.sha(reference['path']) != reference['sha256']:
            raise ValueError('DRIVER_RUNTIME_DRIFT')
    frozen, policy = checked(CANDIDATE)
    if not args.execute:
        print(json.dumps(dict(status='CHECK_ONLY', services_started=0, medical_arrays_read=0)))
        return
    if not args.confirmation or not args.confirmation_sha:
        raise ValueError('NEW_TECHNICAL_CONFIRMATION_REQUIRED')
    confirmation = legacy.bound(dict(path=args.confirmation, sha256=args.confirmation_sha))
    if confirmation.get('status') != 'EXPLICIT_LOCAL_TECHNICAL_CONFIRMATION' or confirmation.get('request_sha256') != args.request_sha:
        raise ValueError('NEW_TECHNICAL_CONFIRMATION_REQUIRED')
    OUTPUT.mkdir(mode=448, exist_ok=False)
    run = OUTPUT / 'services'
    evidence = dict(status='FAILED_OR_PARTIAL', candidate=CANDIDATE, driver_sha256=legacy.sha(__file__), checks={}, flows=[], external_requests=0, page_errors=[], screenshots=0, videos=0, traces=0, pixel_exports=0, model_calls=0, human_visual='NOT_RUN', final_rehearsals_count=0)
    journal = Evidence(OUTPUT / 'acceptance.json', evidence)
    processes = []
    logs = []
    start = time.monotonic()

    def interrupt(*_):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGALRM, interrupt)
    signal.alarm(180)
    try:
        log = (OUTPUT / 'service.log').open('xb')
        logs.append(log)
        p = subprocess.Popen([sys.executable, str(ROOT / 'qa/local_mvp_demo64.py'), '--candidate', CANDIDATE['path'], '--candidate-sha', CANDIDATE['sha256'], '--serve', '--run-directory', str(run)], cwd=ROOT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), stdout=log, stderr=log)
        processes.append(p)
        while not (run / 'restore-ready.json').exists():
            if p.poll() is not None:
                raise RuntimeError('SERVICE_START_FAILED')
            if time.monotonic() - start > 20:
                raise TimeoutError('SERVICE_START_DEADLINE')
            time.sleep(0.05)
        evidence['checks']['services'] = 'PASS'
        journal.step('services', status='PASS')
        browse(run, evidence, journal)
        evidence['status'] = 'PASS_TECHNICAL_ONLY'
    except BaseException as e:
        journal.failure(e)
    finally:
        signal.alarm(0)
        for owned in reversed(processes):
            try:
                if owned.poll() is None:
                    owned.terminate()
                    try:
                        owned.wait(timeout=6)
                    except subprocess.TimeoutExpired:
                        owned.kill()
                        owned.wait(timeout=3)
                journal.step('owned_service_parent_exit', pid=owned.pid, exit_code=owned.returncode)
            except BaseException as error:
                journal.failure(error, cleanup=True)
        for stream in logs:
            try:
                stream.close()
            except BaseException as error:
                journal.failure(error, cleanup=True)
        try:
            exit_file = run / 'restore-exit.json'
            if not exit_file.exists():
                raise ValueError('MISSING_SERVICE_CLEANUP_RECEIPT')
            result = json.loads(exit_file.read_bytes())
            evidence['exit'] = result
            if not result['source_db_unchanged'] or any((x['exit_code'] is None for x in result['owned_services'])):
                raise ValueError('INCOMPLETE_OR_UNSAFE_CLEANUP')
            journal.step('service_cleanup', status='PASS')
        except BaseException as error:
            journal.failure(error, cleanup=True)
        if evidence.get('cleanup_errors') or evidence.get('primary_failure'):
            evidence['status']='FAILED_OR_PARTIAL'
        evidence['elapsed_seconds'] = time.monotonic() - start
        journal.save()
        print(json.dumps(dict(status=evidence['status'], checks=evidence['checks'], failure=evidence.get('primary_failure'), output=str(OUTPUT), receipt_sha256=legacy.sha(OUTPUT / 'acceptance.json'))))
if __name__ == '__main__':
    main()
