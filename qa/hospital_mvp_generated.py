"""Generated-only browser -> Gateway -> Backend -> WorkerAgent acceptance.

Uses real local HTTP/SQLite and existing protocols. Injected FakeRunner never
loads a checkpoint or patient image. Wire LIVE_CASE/frozen SHA are compatibility
fixture values, NOT evidence of medical inference. No deployed environment read.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
MODEL_SHA='548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734'
PREP='formal-resnet18-baseline-rule-b-v1'
PROTOCOL='stage1-occlusion-instability-v1'


def private(path,data):
    path.write_bytes(data);path.chmod(0o600)


def config(run):return json.loads((run/'private-config.json').read_text())


def install_generated_worker_doubles(run):
    """Keep existing WorkerAgent transport; replace only inference dependencies.

    WorkerAgent imports torch solely for an exception class even with a fake
    runner. This fixture supplies that class without importing Torch or opening
    any accelerator. Manifest functions are extracted verbatim from current
    source. FrozenRunner construction fails closed.
    """
    import ast
    import types
    from dataclasses import dataclass
    assert 'torch' not in sys.modules and 'algorithm.service' not in sys.modules
    tensor_stub=types.ModuleType('torch')
    class GeneratedOutOfMemoryError(RuntimeError):pass
    tensor_stub.cuda=types.SimpleNamespace(OutOfMemoryError=GeneratedOutOfMemoryError)
    tensor_stub.__epilocate_generated_stub__=True
    sys.modules['torch']=tensor_stub
    constants=types.ModuleType('algorithm.service');constants.MODEL_SHA=MODEL_SHA
    sys.modules['algorithm.service']=constants
    adapter=types.ModuleType('worker.inference')
    sys.modules['worker.inference']=adapter
    def unavailable(*args,**kwargs):raise RuntimeError('FrozenRunner forbidden in generated fixture')
    adapter.__dict__.update(dataclass=dataclass,hashlib=hashlib,MODEL_ID='baseline_resnet18',FrozenRunner=unavailable)
    source=ROOT/'worker/inference.py';tree=ast.parse(source.read_text())
    names={'InferenceOutput','InvalidWorkerInput','ModelHashMismatch','manifest_for_success','manifest_for_failure'}
    nodes=[node for node in tree.body if isinstance(node,(ast.ClassDef,ast.FunctionDef)) and node.name in names]
    assert len(nodes)==len(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),adapter.__dict__)
    (run/'worker-generated-isolation.json').write_text(json.dumps(dict(
        mode='GENERATED_TEST_DOUBLES',real_torch_loaded=False,checkpoint_loaded=False,
        adapter_manifest_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        worker_agent_source_sha256=hashlib.sha256((ROOT/'worker/agent.py').read_bytes()).hexdigest()),indent=2)+'\n')


class TestStore:
    def __init__(self):
        self.run=Path(os.environ['MVP_GENERATED_RUN']);self.root=self.run/'objects'
        self.root.mkdir(mode=0o700,exist_ok=True)
    def put(self,body,media,prefix):
        key=prefix+'-'+secrets.token_hex(24)
        private(self.root/key,body);private(self.root/(key+'.media'),media.encode());return key
    def read(self,key):
        if Path(key).name!=key:raise ValueError('test object key invalid')
        return (self.root/key).read_bytes(),(self.root/(key+'.media')).read_text()
    def delete(self,key):
        (self.root/key).unlink(missing_ok=True);(self.root/(key+'.media')).unlink(missing_ok=True)
    def signed_get(self,sl):return config(self.run)['origin']+'/generated-object/'+sl.staging_object_key


class FakeRunner:
    hardware={'accelerator':'CPU','evidence':'GENERATED_FAKE_MODEL_ONLY'}
    def __init__(self,run):self.run_root=run
    def run(self,claim,input_path,output_dir):
        import pydicom
        from PIL import Image, ImageDraw
        from worker.inference import InferenceOutput, InvalidWorkerInput
        ds=pydicom.dcmread(input_path);assert not str(ds.get('PatientName','')) and not str(ds.get('PatientID',''))
        assert input_path.read_bytes()==(self.run_root/'input.dcm').read_bytes(), 'only exact generated test CT allowed'
        with (self.run_root/'fake-calls.jsonl').open('a') as f:
            f.write(json.dumps({'job_id':claim['job_id'],'kind':claim['job_parameters']['kind'],
                'medical_forward':0,'fake_invocation':1,'input_sha256':hashlib.sha256(input_path.read_bytes()).hexdigest()})+'\n')
        if (self.run_root/'fake-mode.txt').read_text()=='FAIL':raise InvalidWorkerInput('generated failure injection')
        result={'contract_version':'2.0','source':'LIVE_CASE','case_id':claim['case_id'],
            'slice_id':claim['job_parameters']['slice_id'],'kind':claim['job_parameters']['kind'],
            'model_id':'baseline_resnet18','model_version':MODEL_SHA,'preprocessing_version':PREP,
            'protocol_id':PROTOCOL,'prediction':{'predicted_class':0,'class_label':'negative',
                'positive_probability':.1,'predicted_class_confidence':.9,'inference_time_ms':1}}
        assets={};summaries=[];positions=[]
        if result['kind']=='OCCLUSION':
            for scale in claim['job_parameters']['scales']:
                layers={}
                for field,kind,size in [('response_layer','CANDIDATE_RESPONSE',224),
                                       ('candidate_layer','CANDIDATE_TOP10',224),
                                       ('comparison_grid_layer','COMPARISON_GRID',14)]:
                    name=f'generated-{scale}-{kind}.png';im=Image.new('RGBA',(size,size),(0,0,0,0));draw=ImageDraw.Draw(im)
                    if size==224:
                        for x,y in [(4,4),(220,4),(4,220),(220,220),(112,112)]:
                            draw.rectangle((x-4,y-4,x+3,y+3),fill=(255,0,0,255))
                    else:
                        for x,y in [(0,0),(13,0),(0,13),(13,13),(7,7)]:draw.point((x,y),fill=(255,0,0,255))
                    out=io.BytesIO();im.save(out,format='PNG');assets[name]=(out.getvalue(),'image/png')
                    layers[field]={'asset_id':name,'layer_kind':kind,'width':size,'height':size,
                        'coordinate_space':'COMPARISON_14' if size==14 else 'ALGORITHM_224',
                        'value_min':0,'value_max':1,'origin':'TOP_LEFT_PIXEL_EDGE','x_axis':'RIGHT','y_axis':'DOWN','display_interpolation_only':True}
                summaries.append(dict(block_size=scale,stride=scale//2,fill=.5,baseline_positive_probability=.1,
                    median_absolute_probability_change=.02,flip_rate=0,candidate_status='valid',candidate_area_fraction=.1,**layers))
                for y in range(0,224-scale+1,scale//2):
                    for x in range(0,224-scale+1,scale//2):
                        positions.append(dict(x=x,y=y,block_size=scale,baseline_positive_probability=.1,
                            masked_positive_probability=.08,prediction_flip=False,decision_confidence_drop=.02,candidate_response=.02))
            result.update(scale_summaries=summaries,positions=positions,cross_scale=[])
        return InferenceOutput(result,assets)


def child(kind,run,dist):
    c=config(run);os.environ.update(c['env'])
    if kind=='backend':
        import backend_v2.api.app as backend
        backend.ObjectStore=TestStore
        import uvicorn
        uvicorn.run(backend.app,host='127.0.0.1',port=c['backend'],access_log=False,log_level='warning')
    elif kind=='gateway':
        from session_gateway.app import create_app
        import uvicorn
        uvicorn.run(create_app(),host='127.0.0.1',port=c['gateway'],access_log=False,log_level='warning')
    elif kind=='edge':
        from http.server import ThreadingHTTPServer
        from qa.phase5_local_https import Edge
        class GeneratedEdge(Edge):
            def route(self):
                if self.path.startswith('/api/v2/workers/'):
                    self.forward(self.server.backend)
                elif self.path.startswith('/generated-object/'):
                    try:body,media=TestStore().read(self.path.split('/')[-1])
                    except (ValueError,FileNotFoundError):self.send_error(404);return
                    self.send_response(200);self.send_header('Content-Type',media);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
                else:super().route()
            def static(self):
                old=self.path
                if self.path.startswith('/mvp/'):self.path=self.path[len('/mvp'):]
                try:super().static()
                finally:self.path=old
        server=ThreadingHTTPServer(('127.0.0.1',c['edge']),GeneratedEdge)
        server.kind='browser';server.backend=c['backend'];server.gateway=c['gateway'];server.static_root=dist
        tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(run/'tls.crt',run/'tls.key');server.socket=tls.wrap_socket(server.socket,server_side=True);server.serve_forever()
    else:
        install_generated_worker_doubles(run)
        from worker.config import WorkerConfig
        from worker.agent import WorkerAgent
        cfg=WorkerConfig(c['worker_id'],c['origin'],c['worker_token'],MODEL_SHA,run/'unused-frozen-root',
                         run/'worker-data',MODEL_SHA,tls_ca_file=run/'tls.crt',poll_seconds=.2)
        agent=WorkerAgent(cfg,runner=FakeRunner(run));signal.signal(signal.SIGTERM,lambda *_:agent.stop());agent.run_forever()


def free_port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]


def setup(run):
    from argon2 import PasswordHasher
    from sqlalchemy.orm import Session
    from backend_v2.db.base import Base,make_engine
    from backend_v2.models.entities import User
    from backend_v2.auth.credentials import issue_user_credential
    from backend_v2.workers.provision import provision
    ports={k:free_port() for k in ['backend','gateway','edge']};assert len(set(ports.values()))==3
    origin=f'https://127.0.0.1:{ports["edge"]}'
    env=dict(EPILOCATE_V2_DATABASE_URL='sqlite:///'+str(run/'backend.sqlite'),EPILOCATE_V2_LEASE_SECRET=secrets.token_hex(32),
        EPILOCATE_V2_ALLOW_ENV_TOKENS='false',EPILOCATE_GATEWAY_PUBLIC_ORIGIN=origin,
        EPILOCATE_GATEWAY_BACKEND_ORIGIN=f'http://127.0.0.1:{ports["backend"]}',
        EPILOCATE_GATEWAY_ACCOUNTS_FILE=str(run/'accounts.json'),EPILOCATE_GATEWAY_SESSIONS_FILE=str(run/'sessions.sqlite'),
        EPILOCATE_GATEWAY_SESSION_KEY_FILE=str(run/'session.key'),MVP_GENERATED_RUN=str(run))
    os.environ.update(env);engine=make_engine(env['EPILOCATE_V2_DATABASE_URL']);Base.metadata.create_all(engine)
    password=secrets.token_urlsafe(24)
    with Session(engine) as db:
        user=User(auth_subject='generated_mvp');db.add(user);db.flush();_,token=issue_user_credential(db,user,expires_in=timedelta(hours=1))
        wid,wt=provision(db,model_id='baseline_resnet18',model_hash=MODEL_SHA,preprocessing_version=PREP,
            protocol_id=PROTOCOL,display_name='GENERATED FAKE MODEL ONLY');db.commit()
    engine.dispose();private(run/'user.env',('export EPILOCATE_USER_TOKEN='+token+'\n').encode())
    private(run/'accounts.json',json.dumps({'generated_mvp':dict(enabled=True,password_hash=PasswordHasher().hash(password),token_file=str(run/'user.env'))}).encode())
    private(run/'session.key',secrets.token_bytes(32));c=dict(ports,origin=origin,env=env,password=password,worker_id=wid,worker_token=wt)
    private(run/'private-config.json',json.dumps(c).encode());(run/'fake-mode.txt').write_text('SUCCESS')
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(run/'tls.key'),'-out',str(run/'tls.crt'),
        '-days','1','-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    (run/'tls.key').chmod(0o600)
    # Generator is existing repository code; only generated pixels are read.
    import importlib.util
    spec=importlib.util.spec_from_file_location('generated_dicom',ROOT/'frontend/geometry-qa/create_fixture.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.OUTPUT=run;m.make('input.dcm',True)
    import pydicom
    ds=pydicom.dcmread(run/'input.dcm');ds.PatientName='';ds.PatientID='';ds.BurnedInAnnotation='NO';ds.save_as(run/'input.dcm',enforce_file_format=True)
    return c


def browser_flow(run,c):
    from playwright.sync_api import sync_playwright,expect
    evidence=dict(environment='GENERATED_APP_REAL_HTTP_FAKE_RUNNER_SQLITE_TEST_STORAGE',scenarios=[],requests=[],page_errors=[],external_requests=[],flows=[],geometry=[])
    def record(name,**facts):evidence['scenarios'].append(dict(name=name,passed=True,**facts));print('PASS '+name,flush=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='chrome',headless=True,args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        try:
            context=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000})
            def policy(route):
                from urllib.parse import urlsplit
                u=urlsplit(route.request.url)
                if u.hostname in {'127.0.0.1','localhost'} or u.scheme in {'blob','data'}:route.continue_()
                else:evidence['external_requests'].append(u.netloc+u.path);route.abort()
            context.route('**/*',policy)
            context.add_init_script("""addEventListener('DOMContentLoaded',()=>{const b=document.createElement('div');b.textContent='GENERATED TEST CT + FAKE MODEL / 非医学推理';b.style='position:fixed;top:0;left:0;z-index:99999;background:#ffec8b;color:#000;font-size:14px;padding:3px';document.body.append(b)})""")
            page=context.new_page();page.set_default_timeout(20000);page.on('pageerror',lambda e:evidence['page_errors'].append(str(e)))
            page.on('response',lambda r:evidence['requests'].append({'path':r.url.split(c['origin'])[-1].split('?')[0],'method':r.request.method,'status':r.status}) if '/api/v2/' in r.url else None)
            page.goto(c['origin']+'/mvp/cases');page.wait_for_load_state('networkidle')
            page.get_by_label('账号',exact=True).fill('generated_mvp');page.get_by_label('密码',exact=True).fill(c['password']);page.get_by_role('button',name='登录',exact=True).click()
            expect(page.get_by_role('button',name='创建匿名病例',exact=True)).to_be_visible();record('real Gateway login and real Backend cases')
            for number in range(1,4):
                started=time.monotonic();page.goto(c['origin']+'/mvp/cases');page.get_by_role('button',name='创建匿名病例',exact=True).click()
                page.get_by_label('选择已去标识的单张 CT DICOM（最多 20 MiB）').set_input_files(str(run/'input.dcm'))
                page.get_by_role('button',name='上传 DICOM',exact=True).click();expect(page.get_by_role('button',name='运行 Baseline 分类',exact=True)).to_be_enabled()
                case_id=page.url.rsplit('/',1)[-1]
                page.get_by_role('button',name='运行 Baseline 分类',exact=True).click();expect(page.get_by_role('link',name='查看已完成结果 →',exact=True)).to_be_visible(timeout=40000)
                prediction_job=page.url.rsplit('/',1)[-1];page.get_by_role('link',name='查看已完成结果 →',exact=True).click();expect(page.get_by_role('heading',name='结果工作区',exact=True)).to_be_visible()
                page.goto(c['origin']+'/mvp/cases/'+case_id);page.get_by_role('button',name='运行 16 / 32 / 64 px 遮挡',exact=True).click()
                expect(page.get_by_role('link',name='查看已完成结果 →',exact=True)).to_be_visible(timeout=40000);job_id=page.url.rsplit('/',1)[-1]
                page.get_by_role('link',name='查看已完成结果 →',exact=True).click();expect(page.get_by_text('像素校验通过',exact=True)).to_be_visible()
                checkbox=page.get_by_label('显示叠加',exact=True);expect(checkbox).to_be_enabled();checkbox.check()
                for scale in [16,32,64]:
                    page.get_by_role('button',name=f'{scale} px',exact=True).click();expect(page.get_by_role('button',name=f'{scale} px',exact=True)).to_have_attribute('aria-pressed','true')
                import ast
                helper=ast.parse((ROOT/'frontend/geometry-qa/local-integration-browser.py').read_text())
                marker_core=next(n.value.value for n in helper.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MARKER_CORE' for t in n.targets))
                page.evaluate(marker_core)
                measure_source=(ROOT/'frontend/geometry-qa/measure.js').read_text()
                measure='()=>{'+measure_source.split('page.evaluate(() => {',1)[1].rsplit('})',1)[0]+'}'
                page.get_by_role('button',name='重置视图',exact=True).click()
                page.get_by_role('button',name='缩小 CT',exact=True).click();page.get_by_role('button',name='缩小 CT',exact=True).click()
                page.wait_for_timeout(200);metrics=page.evaluate(measure)
                assert all(m['samples']>0 for m in metrics['markers']) and metrics['maxErrorCssPx']<=1,metrics
                evidence['geometry'].append(dict(flow=number,scope='generated oriented non-square single-slice native overlay',**metrics))
                result_id=page.url.rsplit('/',1)[-1];page.reload();expect(page.get_by_text('像素校验通过',exact=True)).to_be_visible();expect(page.get_by_label('显示叠加',exact=True)).to_be_checked();expect(page.get_by_role('button',name='64 px',exact=True)).to_have_attribute('aria-pressed','true')
                page.screenshot(path=str(run/f'generated-flow-{number}.png'),full_page=True)
                evidence['flows'].append(dict(number=number,case_id=case_id,prediction_job_id=prediction_job,occlusion_job_id=job_id,result_id=result_id,seconds=time.monotonic()-started,medical_model_calls=0))
                record(f'generated flow {number}: upload -> WorkerAgent prediction/occlusion -> persisted Result -> overlay/legacy scales -> refresh')
            (run/'fake-mode.txt').write_text('FAIL');page.goto(c['origin']+'/mvp/cases/'+case_id);page.get_by_role('button',name='运行 Baseline 分类',exact=True).click()
            expect(page.get_by_text('失败',exact=True).first).to_be_visible(timeout=40000);failed_job=page.url.rsplit('/',1)[-1];page.reload();expect(page.get_by_text('失败',exact=True).first).to_be_visible();assert page.get_by_role('link',name='查看已完成结果 →',exact=True).count()==0
            page.screenshot(path=str(run/'generated-failure.png'),full_page=True);record('real FAILED job persisted and refresh restored; no completed-result link',job_id=failed_job)
            assert not evidence['page_errors'] and not evidence['external_requests']
        except Exception as exc:
            evidence['status']='FAILED'
            evidence['error_type']=type(exc).__name__
            (run/'generated-failure-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
            raise
        finally:browser.close()
    evidence['medical_model_calls']=0;evidence['business_api_interception']=False;evidence['wire_LIVE_CASE_is_fixture_compatibility_only']=True
    return evidence


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',type=Path,required=True);parser.add_argument('--dist',type=Path,required=True);parser.add_argument('--child',choices=['backend','gateway','edge','worker']);args=parser.parse_args()
    run=args.run.resolve();dist=args.dist.resolve()
    if not run.is_relative_to(ROOT/'frontend/.local') or not dist.is_relative_to(ROOT/'frontend/.local'):parser.error('local generated directories required')
    if args.child:child(args.child,run,dist);return
    run.mkdir(parents=True,mode=0o700,exist_ok=False);run.chmod(0o700)
    # Strip inherited deployed/worker/cloud settings. Only generated test config.
    env={k:v for k,v in os.environ.items() if not k.startswith(('EPILOCATE_','WORKER_','AWS_','TOKEN','BACKEND_URL'))};env.update(PYTHONPATH=str(ROOT)+os.pathsep+os.environ.get('PYTHONPATH',''),PYTHONDONTWRITEBYTECODE='1');os.environ.clear();os.environ.update(env)
    c=setup(run);children=[];handles=[];evidence=None;started=time.monotonic()
    def stop_owned(*_):raise KeyboardInterrupt('stop own generated harness')
    signal.signal(signal.SIGTERM,stop_owned);signal.signal(signal.SIGINT,stop_owned)
    try:
        for kind in ['backend','gateway','edge','worker']:
            handle=(run/(kind+'.log')).open('w');handles.append(handle)
            process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--run',str(run),'--dist',str(dist),'--child',kind],cwd=ROOT,env=env,stdout=handle,stderr=handle);children.append(process)
        import httpx
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if any(p.poll() is not None for p in children):raise RuntimeError('owned generated service failed; inspect private logs')
            try:
                if httpx.get(c['origin']+'/auth/session',verify=str(run/'tls.crt'),trust_env=False).status_code==401:break
            except httpx.RequestError:pass
            time.sleep(.1)
        else:raise RuntimeError('owned generated edge startup timeout')
        evidence=browser_flow(run,c)
        from sqlalchemy import create_engine,select,func
        from sqlalchemy.orm import Session
        from backend_v2.models.entities import InferenceJob,InferenceResult,Asset,WorkerNode
        engine=create_engine(c['env']['EPILOCATE_V2_DATABASE_URL'])
        with Session(engine) as db:
            jobs=db.scalars(select(InferenceJob)).all();evidence['database']=dict(jobs=len(jobs),completed=sum(j.status=='COMPLETED' for j in jobs),failed=sum(j.status=='FAILED' for j in jobs),results=db.scalar(select(func.count()).select_from(InferenceResult)),assets=db.scalar(select(func.count()).select_from(Asset)),workers=db.scalar(select(func.count()).select_from(WorkerNode)))
        engine.dispose();assert evidence['database']==dict(jobs=7,completed=6,failed=1,results=6,assets=27,workers=1)
        evidence['status']='PASS';print(json.dumps(evidence['database']),flush=True)
    finally:
        for p in children:
            if p.poll() is None:p.terminate()
        for p in children:
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
        for h in handles:h.close()
        (run/'owned-process-completion.json').write_text(json.dumps(dict(
            elapsed_seconds=time.monotonic()-started,
            services=[dict(kind=kind,pid=p.pid,returncode=p.returncode,stopped=p.poll() is not None)
                for kind,p in zip(['backend','gateway','edge','worker'],children)],
            medical_model_calls=0),indent=2)+'\n')
        if evidence is not None:
            evidence['owned_services_stopped']=all(p.poll() is not None for p in children)
            (run/'browser-acceptance.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    if evidence is None:raise RuntimeError('no completed generated evidence')


if __name__=='__main__':main()
