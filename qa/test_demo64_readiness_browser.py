"""Generated DICOM, production Vue viewer/decoder and acceptance probe. No medical assets."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect
from qa.technical_evidence import Evidence
from qa.demo64_readiness import wait_ready
ROOT=Path(__file__).resolve().parents[1]


def test_generated_browser_readiness():
    folder=ROOT/('frontend/.local/r85-readiness-synthetic-'+str(time.time_ns()));folder.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('fixture',ROOT/'frontend/geometry-qa/create_fixture.py')
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture);fixture.OUTPUT=folder
    fixture.make('generated.dcm',True)
    html='''<!doctype html><div id="app"></div><script type="module">
import '/src/style.css';import {createApp,h,ref} from 'vue';import Viewer from '/src/viewer/CornerstoneSliceViewer.vue';
const bytes=await(await fetch('./generated.dcm')).blob();
const file=ref(null),layer=ref(null),note=ref(false);
const raster=document.createElement('canvas');raster.width=raster.height=224;raster.getContext('2d').fillRect(0,0,224,224);
const url=raster.toDataURL();const overlay={url,sliceId:'generated',layer:{asset_id:'response-64.png',layer_kind:'CANDIDATE_RESPONSE',width:224,height:224,coordinate_space:'ALGORITHM_224',origin:'TOP_LEFT_PIXEL_EDGE',x_axis:'RIGHT',y_axis:'DOWN',display_interpolation_only:true},geometry:{rawWidth:112,rawHeight:80,modelWidth:224,modelHeight:224,rasterWidth:224,rasterHeight:224}};
window.generated={url,load:()=>file.value=new File([bytes],'generated.dcm'),fail:()=>{file.value=new File(['bad'],'invalid.dcm');note.value=true},asset:()=>layer.value=overlay,wrong:()=>layer.value={...overlay,sliceId:'wrong'},clear:()=>layer.value=null};
createApp({setup:()=>()=>h('div',{class:'result-image-panel'},[h('p',{style:'display:none'},'hidden auxiliary hint'),note.value?h('p','ready-looking hint'):null,h(Viewer,{file:file.value,sliceId:'generated',sliceWidth:112,sliceHeight:80,overlay:layer.value,overlayVisible:true})])}).mount('#app');
</script>'''
    (folder/'index.html').write_text(html)
    log=Evidence(folder/'regression.json',dict(scope='GENERATED_ONLY',status='RUNNING',screenshots=0,models=0))
    server=None;browser=None;start=time.monotonic()
    base='http://127.0.0.1:5197';path='/'+str(folder.relative_to(ROOT/'frontend'))+'/index.html'
    config=folder/'vite.config.mjs'
    config.write_text("import base from '../../vite.config.ts'; export default async env => {const c=await base(env); c.server.fs={allow:"+json.dumps([str(ROOT/'frontend'),str((ROOT/'frontend/node_modules').resolve().parent)])+"};return c;}")
    try:
        with (folder/'vite.log').open('w') as output:
            server=subprocess.Popen(['/opt/homebrew/bin/node','node_modules/vite/bin/vite.js','--config',str(config),'--host','127.0.0.1','--port','5197','--strictPort'],cwd=ROOT/'frontend',env=dict(os.environ,FRONTEND_DEV_PORT='5197'),stdout=output,stderr=output)
            while True:
                assert server.poll() is None
                try:urllib.request.urlopen(base+path,timeout=.5);break
                except OSError:
                    if time.monotonic()-start>15:raise
                    time.sleep(.05)
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True,args=['--use-angle=swiftshader','--enable-unsafe-swiftshader','--disable-background-networking'])
                context=browser.new_context(viewport=dict(width=1440,height=1000))
                context.route('**/*',lambda r:r.continue_() if r.request.url.startswith((base,'blob:','data:')) else r.abort())
                context.add_init_script(path=str(ROOT/'qa/demo64_readiness.js'))
                page=context.new_page();page.goto(base+path);page.wait_for_function('!!window.generated')
                expected=dict(coreUrl='/node_modules/.vite/deps/@cornerstonejs_core.js',pathname=path,width=112,height=80)
                probe=lambda e:page.evaluate('e=>window.__epiTechnicalProbe(e)',e)
                assert not probe(expected)['ready'];log.step('no_current_image',status='PASS')
                page.evaluate('window.generated.load()')
                wait_ready(page,expected,20000)
                initial=probe(expected);assert initial['ready'];log.step('actual_decode_render',status='PASS',probe=initial)
                # Hide auxiliary hint using test-only CSS; never change production CSS/readiness.
                page.add_style_tag(content='.viewer-note {display:none}')
                assert probe(expected)['ready'];log.step('hidden_hint_rendered',status='PASS')
                expected['assetUrl']=page.evaluate('window.generated.url');expected['assetSize']=224
                assert not probe(expected)['ready'];log.step('missing_asset',status='PASS')
                page.evaluate('window.generated.wrong()');assert not probe(expected)['ready'];log.step('wrong_asset',status='PASS')
                page.evaluate('window.generated.asset()')
                wait_ready(page,expected)
                latest=probe(expected);log.step('actual_asset_decode_draw',status='PASS',probe=latest)
                assert not probe(dict(expected,afterSequence=latest['renderSequence']))['ready'];log.step('old_render_generation_rejected',status='PASS')
                page.evaluate('window.generated.clear()');page.evaluate('()=>new Promise(requestAnimationFrame)')
                assert not probe(expected)['ready'];log.step('cleared_overlay_rejected',status='PASS')
                page.evaluate('window.generated.fail()')
                expect(page.get_by_role('alert').first).to_be_visible(timeout=20000)
                assert not probe(expected)['ready'];log.step('hint_and_canvas_but_decode_failed',status='PASS')
                log.value['status']='PASS_GENERATED_ONLY';log.save()
                browser.close();browser=None;log.step('browser_closed',status='PASS')
    except BaseException as e:log.failure(e);raise
    finally:
        if browser:
            try:browser.close();log.step('browser_closed_after_failure',status='PASS')
            except BaseException as e:log.failure(e,cleanup=True)
        if server:
            try:server.terminate();server.wait(timeout=5);log.step('owned_synthetic_server_exit',exit=server.returncode)
            except BaseException as e:log.failure(e,cleanup=True)
