"""One bounded saved-result browser check. No upload, Worker, inference or media export."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qa import local_mvp_readonly as reader


def checked(plan):
    if plan['schema'] != 'LOCAL_MVP_R71_READONLY_ACCEPTANCE_PLAN_V1' or plan['seconds'] != 180:
        raise ValueError('EXACT_BOUNDED_PLAN_REQUIRED')
    if plan['media_exports'] != dict(screenshot=False, video=False, trace=False, pixels=False):
        raise ValueError('MEDIA_EXPORT_NOT_ALLOWED')
    for name, digest in plan['entry_sha256'].items():
        if reader.sha(name) != digest: raise ValueError('ACCEPTANCE_ENTRY_DRIFT')
    command = reader.bound(plan['command_index'])
    binding = reader.bound(command['binding']); reader.validate_binding(binding)
    if command['binding']['sha256'] != '0000000000000000000000000000000000000000000000000000000000000000':
        raise ValueError('ORIGINAL_READONLY_BINDING_REQUIRED')
    output = Path(plan['output'])
    if not output.is_absolute() or not output.is_relative_to(ROOT / '.local'):
        raise ValueError('PRIVATE_TASK_OUTPUT_REQUIRED')
    return command, binding, output


def browse(plan, output):
    from playwright.sync_api import sync_playwright, expect
    from session_gateway.app import backend_token
    import httpx
    run = output / 'services'; cfg = json.loads((run / 'private-config.json').read_bytes())
    evidence = dict(checks={}, flows=[], page_error_types=[], external_request_count=0,
                    screenshots=0, videos=0, traces=0, pixel_exports=0, model_calls=0)
    deadline = time.monotonic() + 140
    with httpx.Client(verify=str(run / 'tls.crt'), trust_env=False) as client:
        old_token = backend_token(plan['old_credential_path'])
        # Public edge/Gateway requires a session, so check the direct
        # loopback backend with the old credential; never log credential bytes.
        status = client.get('http://127.0.0.1:' + str(cfg['ports']['backend']) + '/api/v2/cases',
                            headers={'Authorization': 'Bearer ' + old_token}).status_code
        evidence['checks']['2_old_auth'] = 'PASS' if status == 401 else 'FAIL'
        del old_token
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=True,
                args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--disable-background-networking', '--disable-sync'])
        try:
            context = browser.new_context(ignore_https_errors=True, viewport={'width': 1440, 'height': 1000})
            def policy(route):
                uri = urlsplit(route.request.url)
                if uri.scheme in {'blob', 'data'} or (uri.scheme == 'https' and uri.netloc == urlsplit(cfg['origin']).netloc):
                    route.continue_()
                else:
                    evidence['external_request_count'] += 1; route.abort()
            context.route('**/*', policy)
            # Coordinate telemetry only. No getImageData/toDataURL, screenshots,
            # video, trace, HAR, console dump, DOM export or saved response body.
            context.add_init_script("""(() => { const old=CanvasRenderingContext2D.prototype.drawImage;
              window.__overlaySequence=0; window.__overlayGeometry=null;
              CanvasRenderingContext2D.prototype.drawImage=function(...args){
                const value=old.apply(this,args);
                if(this.canvas.getAttribute('aria-label')==='模型响应叠加图层') {
                  const m=this.getTransform();const image=args[0];
                  window.__overlayGeometry={sequence:++window.__overlaySequence,
                    matrix:[m.a,m.b,m.c,m.d,m.e,m.f],imageWidth:image.naturalWidth,imageHeight:image.naturalHeight,
                    canvasWidth:this.canvas.width,canvasHeight:this.canvas.height};
                }return value;}; })();""")
            page = context.new_page(); page.set_default_timeout(15000)
            page.on('pageerror', lambda error: evidence['page_error_types'].append(type(error).__name__))
            page.goto(cfg['origin'] + '/mvp/cases', wait_until='domcontentloaded')
            page.get_by_label('账号', exact=True).fill(cfg['username']); page.get_by_label('密码', exact=True).fill(cfg['password'])
            page.get_by_role('button', name='登录', exact=True).click()
            expect(page.get_by_role('button', name='创建匿名病例', exact=True)).to_be_visible()
            evidence['checks']['2_new_auth'] = 'PASS'
            # Original scripts' read-only result/scale/overlay/reload assertions.
            # Intentionally omit their create/upload/Worker and screenshot paths.
            for index, rid in enumerate(cfg['results'], 1):
                if time.monotonic() >= deadline: raise TimeoutError('BROWSER_DEADLINE')
                page.goto(cfg['origin'] + '/mvp/results/' + rid, wait_until='domcontentloaded')
                expect(page.get_by_role('heading', name='结果工作区', exact=True)).to_be_visible()
                response = page.request.get(cfg['origin'] + '/api/v2/results/' + rid); assert response.status == 200
                body = response.json()
                assert body['kind'] == 'OCCLUSION' and body['model_version'] == '548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734'
                case = page.request.get(cfg['origin'] + '/api/v2/cases/' + body['case_id']).json()
                slices = [sl for study in case['studies'] for series in study['series'] for sl in series['slices']]
                sl = next(sl for sl in slices if sl['slice_id'] == body['slice_id'])
                original = page.request.get(cfg['origin'] + '/api/v2/cases/' + body['case_id'] + '/dicom')
                assert original.status == 200 and hashlib.sha256(original.body()).hexdigest() == body['provenance']['input_sha256']
                case_index = plan['input_case_index'][body['provenance']['input_sha256']]
                assert [sl['height_px'], sl['width_px']] == plan['input_shape'][body['provenance']['input_sha256']]
                expect(page.get_by_text('单切片 DICOM 已恢复。支持平移、缩放和重置；当前未提供窗宽窗位工具。', exact=True)).to_be_visible()
                flow = dict(case_index=case_index, result_id=rid, input_sha256=body['provenance']['input_sha256'], scales=[], geometry=[])
                for scale in (16, 32, 64):
                    if time.monotonic() >= deadline: raise TimeoutError('BROWSER_DEADLINE')
                    previous = page.evaluate('window.__overlaySequence || 0')
                    page.get_by_role('button', name=f'{scale} px', exact=True).click()
                    expect(page.get_by_role('button', name=f'{scale} px', exact=True)).to_have_attribute('aria-pressed', 'true')
                    overlay = page.get_by_label('显示叠加', exact=True); expect(overlay).to_be_enabled(); overlay.check()
                    expect(page.get_by_text('像素校验通过', exact=True)).to_be_visible()
                    page.wait_for_function('(n)=>window.__overlayGeometry && window.__overlayGeometry.sequence>n', arg=previous)
                    geometry = page.evaluate('window.__overlayGeometry')
                    assert geometry['imageWidth'] == geometry['imageHeight'] == 224
                    a,b,c,d,e,f = geometry['matrix']; assert abs(a*d-b*c) > 1e-9
                    assert all(abs(value) < 1e7 for value in (a,b,c,d,e,f))
                    viewport = page.get_by_label('单切片 DICOM 查看器', exact=True).bounding_box()
                    canvas = page.get_by_label('模型响应叠加图层', exact=True).bounding_box()
                    assert viewport and canvas and all(abs(viewport[k]-canvas[k]) < 1 for k in ('x','y','width','height'))
                    flow['scales'].append(scale); flow['geometry'].append(dict(scale=scale, **geometry))
                page.reload(); expect(page.get_by_role('button', name='64 px', exact=True)).to_have_attribute('aria-pressed', 'true')
                expect(page.get_by_text('像素校验通过', exact=True)).to_be_visible()
                restored = page.request.get(cfg['origin'] + '/api/v2/results/' + rid); assert restored.json() == body
                flow['refresh'] = 'PASS'; evidence['flows'].append(flow)
            for path in ['/api/v2/cases', '/api/v2/predictions', '/api/v2/jobs/occlusion', '/api/v2/jobs/algorithm', '/api/v2/workers/claim']:
                assert page.request.post(cfg['origin'] + path, data={}).status == 403
            assert page.request.get(cfg['origin'] + '/api/v2/workers/anything').status == 403
            evidence['checks'].update({'3_results': 'PASS', '4_input_binding': 'PASS', '5_scales': 'PASS',
                    '6_overlay_pixel_coordinates': 'PASS', '7_refresh': 'PASS', '8_writes_rejected': 'PASS'})
            evidence['independent_anatomical_visual_review'] = 'NOT RUN; no screenshot/manual review claimed'
            assert not evidence['page_error_types'] and evidence['external_request_count'] == 0
            context.close()
        except BaseException as error:
            error.readonly_evidence = evidence
            raise
        finally: browser.close()
    return evidence


def execute(plan, plan_ref):
    command, binding, output = checked(plan)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    run = output / 'services'; argv = list(command['serve_argv']); argv[argv.index('--run-directory')+1] = str(run)
    processes=[]; handles=[]; evidence=dict(status='FAILED', checks={}, screenshots=0, videos=0, traces=0, pixel_exports=0)
    started=time.monotonic()
    try:
        for name, args in [('services', argv), ('browser', [sys.executable, str(Path(__file__).resolve()), '--plan', plan_ref['path'], '--plan-sha', plan_ref['sha256'], '--browser-child'])]:
            log=(output/(name+'.log')).open('xb');handles.append(log)
            process=subprocess.Popen(args,cwd=ROOT,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),stdout=log,stderr=log);processes.append(process)
            if name=='services':
                while not (run/'restore-ready.json').exists():
                    if process.poll() is not None:raise RuntimeError('RESTORE_SERVICE_START_FAILED')
                    if time.monotonic()-started>=20:raise TimeoutError('SERVICE_START_DEADLINE')
                    time.sleep(.05)
                evidence['checks']['1_services']='PASS'
            else:
                process.wait(timeout=max(1,plan['seconds']-(time.monotonic()-started)-10))
                if process.returncode!=0:raise RuntimeError('BROWSER_ACCEPTANCE_FAILED')
                evidence.update(reader.bound(dict(path=str(output/'browser.json'),sha256=reader.sha(output/'browser.json'))))
                evidence['checks']['1_services']='PASS'
    except BaseException as error:
        evidence['error_type']=type(error).__name__
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
        for handle in handles:handle.close()
        if (run/'restore-exit.json').exists():
            completed=json.loads((run/'restore-exit.json').read_bytes())
            evidence['checks']['10_exit_original_unchanged']='PASS' if completed['source_db_unchanged'] and all(p['exit_code'] is not None for p in completed['owned_services']) else 'FAIL'
            evidence['checks']['9_zero_model']='PASS' if not completed['worker_started'] and completed['model_calls']==0 else 'FAIL'
            cfg=json.loads((run/'private-config.json').read_bytes())
            evidence['asset_hashes_unchanged']=all(reader.sha(Path(cfg['source_objects'])/name)==value for name,value in cfg['object_sha256'].items())
            if not evidence['asset_hashes_unchanged']:evidence['checks']['10_exit_original_unchanged']='FAIL'
        evidence['elapsed_seconds']=time.monotonic()-started
        evidence['status']='PASS_TECHNICAL_READONLY_RESTORE' if len(evidence['checks'])==11 and all(v=='PASS' for v in evidence['checks'].values()) else 'FAILED_OR_PARTIAL'
        evidence['independent_visual_alignment']='NOT RUN; numeric/canvas binding only'
        reader.private(output/'acceptance.json',evidence)
    return evidence


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--plan-sha',required=True)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--browser-child',action='store_true');args=parser.parse_args()
    ref=dict(path=str(args.plan),sha256=args.plan_sha);plan=reader.bound(ref);_,_,output=checked(plan)
    if args.browser_child:
        def interrupted(*_):raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM,interrupted)
        try:result=browse(plan,output)
        except BaseException as error:
            result=getattr(error,'readonly_evidence',dict(checks={},flows=[],screenshots=0,videos=0,traces=0,pixel_exports=0))
            result.update(status='FAILED',error_type=type(error).__name__)
        reader.private(output/'browser.json',result);return 0 if result.get('status')!='FAILED' else 1
    if not args.execute:
        if output.exists():raise ValueError('EXISTING_ACCEPTANCE_OUTPUT_RECONCILE_NO_RETRY')
        print(json.dumps(dict(status='CHECK_ONLY_NOT_EXECUTED',seconds=180,output=str(output),source_db_images_or_old_credential_read=False,
                             browser_started=False,screenshots=0,videos=0,traces=0,pixel_exports=0,model_calls=0)));return 0
    result=execute(plan,ref);print(json.dumps(dict(status=result['status'],output=str(output),checks=result['checks'])));return 0 if result['status'].startswith('PASS') else 1


if __name__=='__main__':sys.exit(main())
