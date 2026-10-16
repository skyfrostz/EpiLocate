"""Generated-only browser diagnostics using real built Vue/API/TLS/codec paths."""
import argparse
import json
from pathlib import Path
import time
from playwright.sync_api import sync_playwright, expect
from qa.demo64_generated_production import start, core_url
from qa.demo64_readiness import PROBE
from qa.demo64_readiness import wait_ready
from qa.technical_evidence import Evidence


def inspect(plan,folder):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=False)
    data=json.loads(Path(plan).read_bytes());core=core_url(Path(data['frozen']['dist']))
    process,log,run=start(Path(plan),folder)
    config=json.loads((run/'private-config.json').read_bytes())
    evidence=dict(scope='GENERATED_ONLY',core_url=core,console=[],errors=[],requests=[],screenshots=0,medical_model_calls=0)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='chrome',headless=True,args=['--use-angle=swiftshader','--enable-unsafe-swiftshader','--disable-background-networking'])
            try:
                ctx=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000});ctx.add_init_script(path=str(PROBE));page=ctx.new_page()
                page.on('console',lambda m:evidence['console'].append(m.text[:400]));page.on('pageerror',lambda e:evidence['errors'].append(str(e)[:400]))
                page.on('response',lambda r:evidence['requests'].append(dict(path=r.url.split(config['origin'])[-1],status=r.status,type=r.headers.get('content-type'))))
                page.goto(config['origin']+'/mvp/');page.get_by_label('账号',exact=True).fill(config['username']);page.get_by_label('密码',exact=True).fill(config['password']);page.get_by_role('button',name='登录',exact=True).click()
                expect(page.get_by_role('heading',name='历史结果查看',exact=True)).to_be_visible()
                row=data['policy']['records'][0];page.goto(config['origin']+'/mvp/results/'+row['result_id']);expect(page.get_by_role('heading',name='结果工作区',exact=True)).to_be_visible()
                page.wait_for_timeout(3000)  # diagnosis snapshot only, never an acceptance condition
                expected=dict(coreUrl=core,pathname='/mvp/results/'+row['result_id'],width=112,height=80)
                evidence['probe']=page.evaluate('e=>window.__epiTechnicalProbe(e)',expected)
                evidence['dom']=page.evaluate('()=>({stages:document.querySelectorAll(".cornerstone-stage").length,placeholder:[...document.querySelectorAll(".viewer-placeholder")].map(x=>x.textContent),notices:[...document.querySelectorAll(".viewer-note,.notice-error")].map(x=>({text:x.textContent,visible:x.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})})),canvas:[...document.querySelectorAll("canvas")].map(x=>({w:x.width,h:x.height,rect:[x.clientWidth,x.clientHeight]}))})')
                evidence['layout']=page.evaluate('()=>{let el=document.querySelector(".cornerstone-viewport");const ancestors=[];while(el){const s=getComputedStyle(el);ancestors.push({tag:el.tagName,class:el.className,width:el.clientWidth,height:el.clientHeight,display:s.display,position:s.position,cssHeight:s.height,opacity:s.opacity});el=el.parentElement}return {ancestors,sheets:[...document.styleSheets].map(x=>({href:x.href,disabled:x.disabled,rules:x.cssRules.length}))}}')
                evidence['engine']=page.evaluate('async u=>{const m=await import(u);const core=m.getRenderingEngines?m:m.t;return {exports:Object.keys(m),engines:core.getRenderingEngines().map(x=>({id:x.id,viewports:x.getViewports().map(v=>({id:v.id,current:v.getCurrentImageId(),status:v.viewportStatus}))}))}}',core)
                evidence['status']='DIAGNOSTIC_SNAPSHOT'
            finally:browser.close();evidence['browser_closed']=True
    finally:
        process.terminate();process.wait(timeout=8);log.close();evidence['exit']=json.loads((run/'restore-exit.json').read_bytes())
        (folder/'diagnosis.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    return evidence


def regress(plan,folder,lifecycle_only=False):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=False)
    data=json.loads(Path(plan).read_bytes());dist=Path(data['frozen']['dist']);core=core_url(dist)
    process,stream,run=start(Path(plan),folder)
    config=json.loads((run/'private-config.json').read_bytes())
    evidence=dict(scope='GENERATED_ONLY',status='RUNNING',flows=[],checks={},external_requests=0,page_errors=[],screenshots=0,videos=0,traces=0,model_calls=0,requests=[])
    log=Evidence(folder/'regression.json',evidence)
    try:
        from qa import demo64_technical_v3 as driver
        previous=driver.CORE;driver.CORE=core
        try:
            if not lifecycle_only:driver.browse(run,evidence,log)
        finally:driver.CORE=previous
        if not lifecycle_only:
            assert len(evidence['flows'])==3 and evidence['checks']['independent_space']=='PASS'
            log.step('built_result_api_three_flows_including_jpeg_lossless',status='PASS')
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='chrome',headless=True,args=['--use-angle=swiftshader','--enable-unsafe-swiftshader','--disable-background-networking'])
            try:
                context=browser.new_context(ignore_https_errors=True,viewport=dict(width=1440,height=1000));context.add_init_script(path=str(PROBE))
                context.add_init_script("""(()=>{const dispatch=EventTarget.prototype.dispatchEvent;window.generatedEvents=[];
                  EventTarget.prototype.dispatchEvent=function(e){if(e.type.startsWith('CORNERSTONE_')&&window.generatedEvents.length<64)window.generatedEvents.push({type:e.type,connected:this.isConnected,tag:this.tagName});return dispatch.call(this,e)}})()""")
                # Test-only HTML mounts the real compiled viewer, never a Vite dev server.
                context.route('**/mvp/lifecycle.html',lambda r:r.fulfill(body=(dist/'lifecycle.html').read_bytes(),content_type='text/html'))
                context.route('**/mvp/generated.dcm',lambda r:r.fulfill(body=(dist/'generated.dcm').read_bytes(),content_type='application/dicom'))
                phase=['positive'];page=context.new_page();page.on('pageerror',lambda e:evidence.setdefault('lifecycle_errors',[]).append(dict(phase=phase[0],message=str(e)[:300])))
                page.on('response',lambda r:evidence['requests'].append(dict(path=r.url.split(config['origin'])[-1],status=r.status,type=r.headers.get('content-type'))))
                page.on('requestfailed',lambda r:evidence.setdefault('lifecycle_request_failures',[]).append(dict(path=r.url.split(config['origin'])[-1],error=r.failure)))
                page.goto(config['origin']+'/mvp/lifecycle.html');page.wait_for_function('!!window.generated')
                expected=dict(coreUrl=core,pathname='/mvp/lifecycle.html',width=112,height=80)
                ready=wait_ready(page,expected);log.step('initial_nonnull_file_mounted',status='PASS',probe=ready)
                expected.update(assetUrl=page.evaluate('window.generated.url'),assetSize=224)
                wait_ready(page,expected);log.step('initial_overlay_current',status='PASS')
                seq=page.evaluate('e=>window.__epiTechnicalProbe(e)',expected)['renderSequence']
                page.evaluate('window.generated.replace()');wait_ready(page,dict(expected,afterSequence=seq));log.step('replace_file_real_new_render',status='PASS')
                probe=lambda e:page.evaluate('e=>window.__epiTechnicalProbe(e)',e)
                now=probe(expected);assert not probe(dict(expected,afterOverlaySequence=now['overlaySequence']))['ready'];log.step('old_asset_generation_rejected',status='PASS')
                page.evaluate('window.generated.assetClear()');page.evaluate('()=>new Promise(requestAnimationFrame)');assert not probe(expected)['ready'];log.step('cleared_overlay_rejected',status='PASS')
                page.evaluate('window.generated.assetRestore()');wait_ready(page,expected)
                page.evaluate('window.generated.clear()');expect(page.locator('.cornerstone-stage')).to_have_count(0)
                assert not probe(expected)['ready'];assert page.evaluate('async u=>{const c=await import(u);return c.getRenderingEngines().length}',core)==0
                log.step('remove_file_cache_renderer_cleanup',status='PASS')
                page.evaluate('window.generated.replace();window.generated.hide()');expect(page.locator('.cornerstone-stage')).to_have_count(0)
                assert not probe(expected)['ready'];page.evaluate('window.generated.show()');wait_ready(page,expected);log.step('cancel_mount_and_remount',status='PASS')
                phase[0]='invalid_generated_dicom';page.evaluate('window.generated.bad()');expect(page.get_by_role('alert').first).to_be_visible();assert not probe(expected)['ready'];log.step('invalid_dicom_cannot_pass',status='PASS')
                page.evaluate('window.generated.replace()');wait_ready(page,expected);phase[0]='positive';page.reload();page.wait_for_function('!!window.generated')
                try:wait_ready(page,expected)
                except BaseException:
                    log.step('lifecycle_refresh_failure',events=page.evaluate('window.generatedEvents'),snapshot=page.evaluate('async u=>{const c=await import(u);return {engines:c.getRenderingEngines().map(e=>e.getViewports().map(v=>({current:!!v.getCurrentImageId(),status:v.viewportStatus,connected:v.element.isConnected,width:v.element.clientWidth,height:v.element.clientHeight}))),ancestors:[...document.querySelectorAll(".cornerstone-stage")].map(e=>({w:e.clientWidth,h:e.clientHeight}))}}',core));raise
                log.step('production_lifecycle_refresh',status='PASS')
                page.evaluate('window.generated.remove()');expect(page.locator('.cornerstone-stage')).to_have_count(0)
                assert page.evaluate('async u=>{const c=await import(u);return c.getRenderingEngines().length}',core)==0;log.step('unmount_renderer_cleanup',status='PASS')
                failed=browser.new_context(ignore_https_errors=True);failed.add_init_script(path=str(PROBE));failed.route('**/mvp/lifecycle.html',lambda r:r.fulfill(body=(dist/'lifecycle.html').read_bytes(),content_type='text/html'))
                failed.route('**/mvp/generated.dcm',lambda r:r.fulfill(body=(dist/'generated.dcm').read_bytes(),content_type='application/dicom'))
                failed.route('**'+core,lambda r:r.abort());bad=failed.new_page();bad.goto(config['origin']+'/mvp/lifecycle.html');bad.wait_for_function('!!window.generated')
                expect(bad.get_by_role('alert').first).to_be_visible();assert not bad.evaluate('e=>window.__epiTechnicalProbe(e)',expected)['ready'];log.step('core_initialization_failure_visible_no_false_ready',status='PASS')
                failed.close();context.close()
            finally:browser.close();log.step('lifecycle_browser_closed',status='PASS')
        assert not evidence['page_errors'] and not any(e['phase']=='positive' for e in evidence.get('lifecycle_errors',[]));evidence['status']='PASS_GENERATED_PRODUCTION_ONLY'
    except BaseException as exc:
        if not evidence.get('primary_failure'):log.failure(exc)
        raise
    finally:
        process.terminate();process.wait(timeout=8);stream.close();evidence['exit']=json.loads((run/'restore-exit.json').read_bytes());log.step('generated_owned_services_closed',status='PASS' if all(r['exit_code'] is not None for r in evidence['exit']['owned_services']) else 'FAIL');log.save()
    return evidence


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--folder',type=Path,required=True);p.add_argument('--regress',action='store_true');a=p.parse_args()
    e=regress(a.plan,a.folder) if a.regress else inspect(a.plan,a.folder);print(json.dumps({k:e.get(k) for k in ('status','probe','dom','engine','errors','console')},ensure_ascii=False))
