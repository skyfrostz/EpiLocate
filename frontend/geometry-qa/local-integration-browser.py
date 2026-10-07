"""Independent production-artifact acceptance; LOCAL_INTEGRATION and MOCK_API.

All images are generated test pixels. Mock COMPLETED is a pre-existing result
fixture, never a newly submitted task. Real local jobs never complete here.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
MARKER_CORE = r"""async () => {
  const urls = performance.getEntriesByType('resource').map(r=>r.name).filter(u=>/\/esm-[^/]+\.js$/.test(u));
  for (const url of [...new Set(urls)]) {
    const module = await import(url);
    for (const value of Object.values(module)) {
      if (value && typeof value.getRenderingEngines === 'function') {
        window.__geometryFixture={cornerstone:value};
        return {engines:value.getRenderingEngines().length,cacheBytes:value.cache.getCacheSize()};
      }
    }
  }
  throw new Error('Loaded production Cornerstone namespace unavailable');
}"""


def fixtures(run):
    import pydicom
    from backend_v2.services.cases import validate_single_ct
    for oriented in [False, True]:
        name = 'geometry_synthetic_oriented_ct.dcm' if oriented else 'geometry_synthetic_ct.dcm'
        ds = pydicom.dcmread(ROOT/'frontend/.local'/name)
        ds.PatientName = ''; ds.PatientID = ''; ds.BurnedInAnnotation = 'NO'
        target = run/('oriented.dcm' if oriented else 'normal.dcm')
        ds.save_as(target, enforce_file_format=True)
        assert validate_single_ct(target.read_bytes()) == (112,80)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--url', default='https://127.0.0.1:5198')
    parser.add_argument('--mode', choices=['local','mock'], required=True)
    parser.add_argument('--attempt', default='1')
    args = parser.parse_args()
    assert urlsplit(args.url).hostname in {'127.0.0.1','localhost'}
    run = args.run.resolve(); out = run/(args.mode+'-attempt'+args.attempt); out.mkdir(exist_ok=False)
    sys.path.insert(0,str(ROOT)); fixtures(run)
    evidence = dict(environment='LOCAL_INTEGRATION_SQLITE_TEST_STORAGE' if args.mode=='local' else 'MOCK_API',
        started_at=datetime.now(timezone.utc).isoformat(),url=args.url+'/mvp/',
        scenarios=[],screenshots=[],requests=[],initiated_requests=[],page_errors=[],external_requests=[],geometry=[])
    def record(name, **facts):
        evidence['scenarios'].append(dict(name=name,passed=True,**facts)); print('PASS '+name,flush=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome',headless=True,
            args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        context = browser.new_context(viewport=dict(width=1440,height=1000),ignore_https_errors=True)
        def policy(route):
            parsed=urlsplit(route.request.url)
            if parsed.hostname in {'127.0.0.1','localhost'} or parsed.scheme in {'blob','data'}:
                route.continue_()
            else:
                evidence['external_requests'].append(parsed.netloc+parsed.path); route.abort()
        context.route('**/*',policy)
        page = context.new_page(); page.set_default_timeout(15000)
        page.on('pageerror',lambda error:evidence['page_errors'].append(str(error)))
        def request_started(request):
            try: document_path=urlsplit(request.frame.url).path
            except Exception: document_path=None  # DICOM decode Worker has no document frame.
            evidence['initiated_requests'].append(dict(method=request.method,path=urlsplit(request.url).path,document_path=document_path))
        context.on('request',request_started)
        context.on('response',lambda response:evidence['requests'].append(dict(
            method=response.request.method,path=urlsplit(response.url).path,status=response.status)))
        def goto(path):
            page.goto(args.url+'/mvp/'+path.lstrip('/'))
            # Real unauthenticated fetch may leave an unconsumed 401 body pending.
            # Job polling also precludes networkidle: signoff waits for visible UI states.
            if args.mode=='mock': page.wait_for_load_state('networkidle')
        def shot(name):
            page.evaluate("""label=>{const e=document.createElement('div');e.id='qa-evidence-label';e.textContent=label;
                e.style='position:fixed;bottom:0;right:0;background:#142334;color:white;padding:6px 12px;font:12px monospace;z-index:99999;pointer-events:none';document.body.append(e)}""",evidence['environment'])
            file=name+'.png';page.screenshot(path=str(out/file),animations='disabled',scale='css')
            page.evaluate("document.getElementById('qa-evidence-label').remove()")
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            evidence['screenshots'].append(file)
        def login(username,password):
            page.get_by_label('账号',exact=True).fill(username)
            page.get_by_label('密码',exact=True).fill(password)
            page.get_by_role('button',name='登录',exact=True).click()
        try:
            if args.mode=='local':
                credentials=json.loads((run/'browser-credentials.json').read_text())
                goto('/cases');expect(page.get_by_label('账号',exact=True)).to_be_visible();shot('01-login')
                assert 'next=/cases' in page.url or 'next=%2Fcases' in page.url
                login('qa_alice','wrong-local-fixture')
                expect(page.get_by_role('alert').filter(has_text='密码不正确')).to_be_visible()
                login('qa_alice',credentials['qa_alice'])
                expect(page.get_by_text('暂无病例',exact=True)).to_be_visible()
                cookies=context.cookies(); cookie=next(c for c in cookies if c['name']=='__Host-epilocate_demo')
                assert cookie['httpOnly'] and cookie['secure'] and cookie['sameSite']=='Strict'
                record('real HTTPS login, invalid password, Cookie flags, next deep-link')
                # Real Gateway rejects an unsafe mutation, without recording CSRF or Cookie values.
                response=context.request.post(args.url+'/api/v2/cases',data={'patient_id':None},
                    headers={'Origin':args.url,'Idempotency-Key':'qa-csrf-negative'})
                assert response.status==403 and response.json()['code']=='CSRF_REJECTED'
                record('real Gateway CSRF rejection',status=403)
                page.get_by_role('button',name='创建匿名病例',exact=True).click()
                expect(page.locator('#dicom-upload')).to_be_visible()
                case_id=page.url.rsplit('/',1)[-1]
                # The old synthetic fixture deliberately has PatientName/PatientID: real validation rejects it.
                page.locator('input[type=file]').set_input_files(str(ROOT/'frontend/.local/geometry_synthetic_ct.dcm'))
                page.get_by_role('button',name='上传 DICOM',exact=True).click()
                expect(page.get_by_role('alert').filter(has_text='去标识')).to_be_visible()
                record('real upload de-identification validator rejects identified synthetic tags',status=422)
                page.locator('input[type=file]').set_input_files(str(run/'normal.dcm'))
                page.get_by_role('button',name='上传 DICOM',exact=True).click()
                expect(page.get_by_role('button',name='放大 CT',exact=True)).to_be_visible(timeout=30000)
                shot('02-case-cornerstone');record('real create/upload and protected DICOM, actual production Cornerstone')
                page.reload();expect(page.get_by_role('button',name='放大 CT',exact=True)).to_be_visible(timeout=30000)
                record('real case deep-link refresh restores authorized DICOM')
                # Fault only the lazy JS chunk; the POST still reaches the real Backend.
                context.route('**/JobDetailView-*.js',lambda route:route.abort())
                page.get_by_role('button',name='运行 16 / 32 / 64 px 遮挡',exact=True).click()
                expect(page.get_by_text('任务已创建，页面未能打开。重试会打开同一任务。',exact=True)).to_be_visible()
                shot('03a-accepted-job-navigation-recovery')
                context.unroute('**/JobDetailView-*.js')
                page.get_by_role('link',name='打开已创建任务 →',exact=True).click()
                expect(page.get_by_role('heading',name='任务详情',exact=True)).to_be_visible()
                expect(page.get_by_text('已创建',exact=True).first).to_be_visible()
                job_id=page.url.rsplit('/',1)[-1]
                assert len([r for r in evidence['requests'] if r['path']=='/api/v2/jobs/occlusion' and r['method']=='POST'])==1
                record('production chunk failure full-page recovery link opens the one real accepted Job without a second POST')
                page.reload();expect(page.get_by_text('已创建',exact=True).first).to_be_visible()
                assert page.get_by_role('link',name='查看已完成结果 →').count()==0
                shot('03-job-no-worker');record('real accepted Job and refresh remain CREATED without Worker or Result',job_id=job_id)
                goto('/');expect(page.get_by_role('heading',name='工作概览',exact=True)).to_be_visible()
                expect(page.get_by_role('link',name='打开病例 '+case_id,exact=True)).to_be_visible();shot('04-dashboard')
                assert page.get_by_role('link',name='打开病例 '+case_id,exact=True).get_attribute('href').endswith('/cases/'+case_id)
                assert not any(x in page.inner_text('body') for x in ['模型置信度','分类概率','10%','90%'])
                record('real Dashboard case state without AI probabilities')
                goto('/system');page.get_by_role('button',name='检查病例 API',exact=True).click()
                expect(page.get_by_text('曾响应',exact=True)).to_be_visible();shot('05-worker-unobserved')
                assert page.get_by_text('未接入',exact=True).count()==4
                record('real System request evidence, unsupported GPU/Worker metrics remain unconnected')
                other=context.new_page();other.goto(args.url+'/mvp/cases');expect(other.get_by_role('button',name='退出',exact=True)).to_be_visible()
                other.get_by_role('button',name='退出',exact=True).click()
                expect(page.get_by_label('账号',exact=True)).to_be_visible()
                login('qa_bob',credentials['qa_bob'])
                expect(page.get_by_role('button',name='退出',exact=True)).to_be_visible()
                goto('/cases');expect(page.get_by_text('暂无病例',exact=True)).to_be_visible()
                for path in [f'/cases/{case_id}',f'/cases/{case_id}/dicom',f'/jobs/{job_id}',
                             '/results/result_'+('0'*32),'/results/result_'+('0'*32)+'/assets/fake.png']:
                    assert context.request.get(args.url+'/api/v2'+path).status==404
                assert page.get_by_role('link',name='打开病例 '+case_id,exact=True).count()==0;shot('06-bob-isolation')
                record('real cross-tab logout, account switch, owner-scoped case/DICOM/Job and absent Result/assets 404')
                other.close();page.get_by_role('button',name='退出',exact=True).click()
                login('qa_alice',credentials['qa_alice']);expect(page.get_by_role('button',name='退出',exact=True)).to_be_visible()
                # Mutate only isolated test database to exercise the actual retention gate.
                from sqlalchemy import create_engine,select,func
                from sqlalchemy.orm import Session
                from backend_v2.models.entities import Case,Slice,WorkerNode,InferenceJob,InferenceResult
                engine=create_engine('sqlite:///'+str(run/'backend.sqlite'))
                with Session(engine) as db:
                    row=db.scalar(select(Case).where(Case.anonymous_id==case_id));row.status='EXPIRED'
                    sl=db.scalar(select(Slice).where(Slice.case_id==row.id));sl.staging_expires_at=datetime.now(timezone.utc)-timedelta(seconds=60);db.commit()
                goto('/cases/'+case_id);expect(page.get_by_text('原始影像已过期',exact=True)).to_be_visible()
                assert page.get_by_role('button',name='运行 Baseline 分类',exact=True).is_disabled()
                shot('07-expired-input');record('real retention 410, no CT, disabled new analysis')
                goto('/not-a-route');expect(page.get_by_role('heading',name='页面不存在',exact=True)).to_be_visible();shot('08-not-found')
                record('production /mvp/ fallback and application 404')
                # Stop ONLY the task-owned Backend process. Gateway generates its real 503 error.
                pids=json.loads((run/'service-pids.json').read_text());os.kill(pids['backend'],signal.SIGTERM)
                goto('/cases');expect(page.get_by_role('alert')).to_be_visible();shot('09-backend-unavailable')
                assert any(r['status']==503 and r['path']=='/api/v2/cases' for r in evidence['requests'])
                goto('/jobs/'+job_id);expect(page.get_by_role('alert')).to_be_visible();shot('10-job-service-unavailable')
                assert page.get_by_role('link',name='查看已完成结果 →').count()==0
                page.get_by_role('button',name='退出',exact=True).click();expect(page.get_by_label('账号',exact=True)).to_be_visible()
                login('qa_alice',credentials['qa_alice']);expect(page.get_by_role('alert').filter(has_text='服务暂时不可用')).to_be_visible()
                shot('11-login-service-unavailable');record('actual stopped Backend produces Gateway 503 for cases/Job/login')
                with Session(engine) as db:
                    evidence['database_final']={'workers':db.scalar(select(func.count()).select_from(WorkerNode)),
                        'results':db.scalar(select(func.count()).select_from(InferenceResult)),
                        'jobs':[{'id':j.public_id,'status':j.status,'attempt_no':j.attempt_no} for j in db.scalars(select(InferenceJob))]}
                assert evidence['database_final']['workers']==evidence['database_final']['results']==0
                assert len(evidence['database_final']['jobs'])==1
                assert all(j['status']=='CREATED' and j['attempt_no']==0 for j in evidence['database_final']['jobs'])
                engine.dispose();record('isolated database proves zero Workers/results, no inference attempts')
            else:
                mock_acceptance(context,page,goto,shot,record,evidence,run,args.url)
            assert evidence['page_errors']==[]
            assert evidence['external_requests']==[]
            evidence['status']='PASS'
        except Exception as exc:
            evidence['status']='FAIL';evidence['failure']=str(exc);evidence['failure_url']=page.url
            page.screenshot(path=str(out/'failure.png'),scale='css')
            raise
        finally:
            evidence['finished_at']=datetime.now(timezone.utc).isoformat()
            (out/'browser-acceptance.json').write_text(json.dumps(evidence,indent=2,ensure_ascii=False)+'\n')
            context.close();browser.close()


def mock_acceptance(context,page,goto,shot,record,evidence,run,origin):
    state=dict(logged=True,oriented=False,variant='normal',expired=False,corrupt=False,job_posts=0)
    stamp='2026-10-04T03:00:00Z'
    def case():
        return dict(case_id='case_mock',patient_id='SYNTHETIC_ONLY',status='READY',created_at=stamp,
            input_expires_at='2026-10-11T03:00:00Z',studies=[dict(study_id='study_mock',series=[dict(series_id='series_mock',
                slices=[dict(slice_id='slice_mock',ordinal=0,width_px=112,height_px=80)])])])
    pngs={}
    for size in [224,14]:
        data=page.evaluate("""size=>{const c=document.createElement('canvas');c.width=c.height=size;const x=c.getContext('2d');
            x.fillStyle='#ff0000';const m=size===224?8:1;
            for(const [a,b] of [[0,0],[size-m,0],[0,size-m],[size-m,size-m],[size/2-m/2,size/2-m/2]])x.fillRect(a,b,m,m);
            return c.toDataURL('image/png').split(',')[1]}""",size)
        import base64
        pngs[size]=base64.b64decode(data)
    def result():
        summaries=[]
        for scale in [16,32,64]:
            def layer(kind):
                size=14 if kind=='COMPARISON_GRID' else 224
                return dict(asset_id=f'{scale}-{kind}.png',layer_kind=kind,width=size,height=size,
                    coordinate_space='COMPARISON_14' if size==14 else 'ALGORITHM_224',value_min=0,value_max=1,
                    origin='TOP_LEFT_PIXEL_EDGE',x_axis='RIGHT',y_axis='DOWN',display_interpolation_only=True)
            summaries.append(dict(block_size=scale,stride=scale//2,fill=0.5,baseline_positive_probability=0.1,
                median_absolute_probability_change=0.02,flip_rate=0,candidate_status='valid',candidate_area_fraction=0.1,
                response_layer=layer('CANDIDATE_RESPONSE'),candidate_layer=layer('CANDIDATE_TOP10'),comparison_grid_layer=layer('COMPARISON_GRID')))
        raw=(run/('oriented.dcm' if state['oriented'] else 'normal.dcm')).read_bytes()
        body=dict(result_id='result_fixture_completed',job_id='job_fixture_completed',case_id='case_mock',slice_id='slice_mock',
            kind='OCCLUSION',contract_version='2.0',source='LIVE_CASE',status='COMPLETED',model_id='baseline_resnet18',
            model_version='548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734',
            preprocessing_version='formal-resnet18-baseline-rule-b-v1',protocol_id='stage1-occlusion-instability-v1',
            created_at=stamp,prediction=dict(predicted_class=0,class_label='negative',positive_probability=0.1,predicted_class_confidence=0.9,inference_time_ms=25),
            scale_summaries=summaries,cross_scale=[],provenance=dict(input_sha256=hashlib.sha256(raw).hexdigest().upper()),
            assets=[{k:v for k,v in layer.items() if k in ['asset_id','layer_kind','width','height','coordinate_space']}
                | {'media_type':'image/png'} for summary in summaries for layer in [summary['response_layer'],summary['candidate_layer'],summary['comparison_grid_layer']]])
        if state['variant']=='hash':body['provenance']['input_sha256']='0'*64
        if state['variant']=='slice':body['slice_id']='slice_unrelated'
        if state['variant']=='version':body['model_version']='future-unverified-version'
        if state['variant']=='dimensions':body['assets'][0]['width']=225
        return body
    def json_response(route,body,status=200):route.fulfill(status=status,content_type='application/json',body=json.dumps(body))
    def auth_route(route):
        path=urlsplit(route.request.url).path
        if path=='/auth/logout':state['logged']=False;route.fulfill(status=204);return
        if path=='/auth/login':state['logged']=True
        json_response(route,{'username':'qa_mock','csrf_token':'synthetic-only'} if state['logged'] else {'code':'UNAUTHENTICATED'},200 if state['logged'] else 401)
    def api_route(route):
        path=urlsplit(route.request.url).path
        if path=='/api/v2/cases':json_response(route,dict(items=[case()],next_cursor=None));return
        if path=='/api/v2/cases/case_mock':json_response(route,case());return
        if path.endswith('/dicom'):
            if state['expired']:json_response(route,{'code':'INPUT_EXPIRED'},410)
            else:route.fulfill(content_type='application/dicom',body=(run/('oriented.dcm' if state['oriented'] else 'normal.dcm')).read_bytes())
            return
        if path=='/api/v2/results/result_fixture_completed':json_response(route,result());return
        if '/assets/' in path:
            route.fulfill(content_type='image/png',body=b'corrupt fixture' if state['corrupt'] else pngs[14 if 'COMPARISON_GRID' in path else 224]);return
        if path=='/api/v2/jobs/job_fixture_completed':
            json_response(route,dict(job_id='job_fixture_completed',kind='OCCLUSION',case_id='case_mock',status='COMPLETED',attempt_no=1,retry_count=0,
                lease_expire_time=None,last_heartbeat=None,failure_reason=None,progress=None,estimated_remaining_time_ms=None,
                result_id='result_fixture_completed',error=None,created_at=stamp,finished_at=stamp));return
        json_response(route,{'code':'NOT_FOUND'},404)
    context.route('**/auth/**',auth_route);context.route('**/api/v2/**',api_route)
    goto('/jobs/job_fixture_completed');page.get_by_role('link',name='查看已完成结果 →',exact=True).click()
    expect(page.get_by_role('button',name='放大 CT',exact=True)).to_be_visible(timeout=30000)
    expect(page.get_by_text('像素校验通过',exact=True)).to_be_visible();shot('01-result-fixture')
    record('pre-existing MOCK_API completed Job → Result link, uppercase DICOM SHA, actual production viewer')
    page.get_by_role('checkbox',name='显示叠加',exact=True).check()
    core=page.evaluate(MARKER_CORE);assert core['engines']==1 and core['cacheBytes']>0
    measure_source=(ROOT/'frontend/geometry-qa/measure.js').read_text()
    measure='()=>{'+measure_source.split('page.evaluate(() => {',1)[1].rsplit('})',1)[0]+'}'
    for oriented in [False,True]:
        state['oriented']=oriented
        page.reload();expect(page.get_by_role('button',name='放大 CT',exact=True)).to_be_visible(timeout=30000)
        page.get_by_role('checkbox',name='显示叠加',exact=True).check();page.evaluate(MARKER_CORE)
        page.get_by_role('button',name='重置视图',exact=True).click()
        page.get_by_role('button',name='缩小 CT',exact=True).click();page.get_by_role('button',name='缩小 CT',exact=True).click()
        for stage in ['initial','zoom-pan','resize']:
            if stage=='zoom-pan':
                page.get_by_role('button',name='放大 CT',exact=True).click()
                box=page.locator('.cornerstone-viewport').bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
                page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+18,y+12,steps=5);page.mouse.up()
            if stage=='resize':page.set_viewport_size(dict(width=1024,height=900))
            page.wait_for_timeout(200);metrics=page.evaluate(measure)
            evidence['geometry'].append(dict(oriented=oriented,stage=stage,**metrics))
            assert all(marker['samples']>0 for marker in metrics['markers']) and metrics['maxErrorCssPx']<=1, metrics
        shot('03-geometry-oriented' if oriented else '02-geometry-normal')
        page.set_viewport_size(dict(width=1440,height=1000))
    record('production Cornerstone six geometry groups: non-square, rotated, unequal spacing, zoom/pan/resize, five markers')
    page.get_by_role('button',name='64 px',exact=True).click()
    page.get_by_role('button',name='候选区域',exact=True).click();page.get_by_role('checkbox',name='显示叠加',exact=True).check()
    page.get_by_role('button',name='放大 CT',exact=True).click();page.wait_for_timeout(200)
    before=page.evaluate("()=>{const v=window.__geometryFixture.cornerstone.getRenderingEngines()[0].getViewport('single-slice');return {zoom:v.getZoom(),pan:v.getPan()}}")
    page.reload();expect(page.get_by_role('button',name='放大 CT',exact=True)).to_be_visible(timeout=30000);page.evaluate(MARKER_CORE)
    after=page.evaluate("()=>{const v=window.__geometryFixture.cornerstone.getRenderingEngines()[0].getViewport('single-slice');return {zoom:v.getZoom(),pan:v.getPan()}}")
    assert abs(before['zoom']-after['zoom'])<1e-6 and all(abs(a-b)<1e-5 for a,b in zip(before['pan'],after['pan']))
    expect(page.get_by_role('button',name='64 px',exact=True)).to_have_attribute('aria-pressed','true')
    assert page.get_by_role('checkbox',name='显示叠加',exact=True).is_checked()
    record('production Result refresh restores scale/layer/overlay/camera',before=before,after=after)
    page.set_viewport_size(dict(width=390,height=844));shot('04-result-mobile');page.set_viewport_size(dict(width=1440,height=1000))
    for variant in ['hash','slice','version','dimensions']:
        state['variant']=variant;page.reload()
        page.get_by_role('button',name='16 px',exact=True).click()
        page.get_by_role('button',name='响应图',exact=True).click()
        expect(page.get_by_role('checkbox',name='显示叠加',exact=True)).to_be_disabled()
        if variant=='dimensions':
            expect(page.get_by_text('图层元数据与当前结果不一致，无法显示。',exact=True)).to_be_visible()
            shot('05-gate-'+variant)
            page.get_by_role('button',name='32 px',exact=True).click()
            expect(page.locator('.heatmap-frame img')).to_be_visible()
            record('MOCK_API asset dimensions mismatch rejects unsafe layer, another valid layer remains available')
        else:
            expect(page.locator('.heatmap-frame img')).to_be_visible()
            shot('05-gate-'+variant);record('MOCK_API '+variant+' mismatch blocks overlay, retains independent layer')
    state['variant']='normal';state['corrupt']=True
    page.reload();expect(page.get_by_text('响应图无法解码。',exact=True)).to_be_visible();shot('06-corrupt-layer')
    state['corrupt']=False;page.get_by_role('button',name='重试读取图层',exact=True).click();expect(page.locator('.heatmap-frame img')).to_be_visible()
    record('MOCK_API corrupt PNG rejects layer and explicit retry recovers')
    state['expired']=True;page.get_by_role('button',name='重新读取',exact=True).click()
    expect(page.get_by_text('原始影像已过期',exact=True)).to_be_visible();expect(page.get_by_role('checkbox',name='显示叠加',exact=True)).to_be_disabled()
    expect(page.locator('.heatmap-frame img')).to_be_visible();shot('07-expired-input-independent-layer')
    record('MOCK_API expired DICOM preserves independent result layer and blocks overlay')
    state['expired']=False;dashboard_start=len(evidence['initiated_requests']);goto('/');shot('08-dashboard')
    assert not any(x in page.inner_text('body') for x in ['分类概率','模型置信度','10%','90%'])
    dashboard_requests=[r for r in evidence['initiated_requests'][dashboard_start:] if r['document_path']=='/mvp/']
    assert not any('/dicom' in r['path'] or '/api/v2/results/' in r['path'] for r in dashboard_requests)
    evidence['dashboard_requests']=dashboard_requests
    record('MOCK_API Dashboard displays no concrete probabilities')
    evidence['mock_new_jobs']=state['job_posts'];assert state['job_posts']==0


if __name__=='__main__':
    main()
