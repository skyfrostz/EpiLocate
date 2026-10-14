"""Isolated generated DB/DICOM/PNG, actual restricted production build and HTTPS.

Never reads historical inputs. Generated API rows use LIVE_CASE solely to exercise
the production source gate; the whole fixture is explicitly SYNTHETIC_ONLY.
"""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import struct
import sys
import time

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend_v2.tests.test_demo64 import generated
from backend_v2.db.base import make_engine
from backend_v2.models.entities import InferenceResult, InferenceJob, Slice, Asset, ModelVersion
from qa import demo64_build, local_mvp_readonly as legacy

ROOT=Path(__file__).resolve().parents[1]
MODEL=dict(model_id='baseline_resnet18',checkpoint_sha256='548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734',preprocessing_version='formal-resnet18-baseline-rule-b-v1',protocol_id='stage1-occlusion-instability-v1')


def generated_lossless(width,height):
    # SOF3 predictor=1, precision=16, constant 32768, one DC Huffman code for zero.
    # All entropy bits are zero; no copied medical or third-party image sample.
    segment=lambda marker,payload:bytes([255,marker])+struct.pack('>H',len(payload)+2)+payload
    return (b'\xff\xd8'+segment(0xc4,b'\0'+bytes([1]+[0]*15)+b'\0')+
        segment(0xc3,bytes([16])+struct.pack('>HH',height,width)+bytes([1,1,0x11,0]))+
        segment(0xda,bytes([1,1,0,1,0,0]))+bytes((width*height+7)//8)+b'\xff\xd9')


def setup(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    binding,policy,_=generated(folder)
    spec=importlib.util.spec_from_file_location('generated_dicom',ROOT/'frontend/geometry-qa/create_fixture.py')
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture);fixture.OUTPUT=folder
    fixture.make('fixture.dcm',True);dicom=(folder/'fixture.dcm').read_bytes();digest=hashlib.sha256(dicom).hexdigest()
    # Three distinct generated SOP payload hashes, as required by exact scope gate.
    import pydicom
    engine=make_engine('sqlite:///'+binding['source_db']['path'])
    with Session(engine) as db:
        model=db.scalar(select(ModelVersion));model.checkpoint_sha256=MODEL['checkpoint_sha256'];model.preprocessing_version=MODEL['preprocessing_version'];model.protocol_id=MODEL['protocol_id']
        for row,result in zip(policy['records'],db.scalars(select(InferenceResult))):
            job=db.get(InferenceJob,result.job_id);sl=db.get(Slice,job.slice_id)
            ds=pydicom.dcmread(io.BytesIO(dicom));ds.SOPInstanceUID=ds.file_meta.MediaStorageSOPInstanceUID='2.25.'+str(100+row['case_index'])
            if row['case_index']==2:
                from pydicom.encaps import encapsulate
                from pydicom.uid import JPEGLosslessSV1
                ds.file_meta.TransferSyntaxUID=JPEGLosslessSV1
                ds.PixelData=encapsulate([generated_lossless(112,80)]);ds['PixelData'].is_undefined_length=True
            stream=io.BytesIO();ds.save_as(stream,enforce_file_format=True);raw=stream.getvalue();digest=hashlib.sha256(raw).hexdigest()
            (Path(binding['source_objects'])/sl.staging_object_key).write_bytes(raw)
            sl.width_px=112;sl.height_px=80;sl.source_sha256=digest;row['input_sha256']=digest
            summaries=[]
            for scale in (16,32,64):
                summary=dict(block_size=scale,stride=scale//2,fill=.5,baseline_positive_probability=.7,median_absolute_probability_change=.1,flip_rate=0,candidate_status='valid',candidate_area_fraction=.1)
                for kind,field,layer_kind in [('response','response_layer','CANDIDATE_RESPONSE'),('candidate','candidate_layer','CANDIDATE_TOP10'),('comparison','comparison_grid_layer','COMPARISON_GRID')]:
                    aid=f'{kind}-{scale}.png';asset=db.scalar(select(Asset).where(Asset.result_id==result.id,Asset.asset_id==aid))
                    size=14 if kind=='comparison' else 224;img=Image.new('L',(size,size),128 if kind=='response' else 255);data=io.BytesIO();img.save(data,format='PNG');png=data.getvalue()
                    (Path(binding['source_objects'])/asset.object_key).write_bytes(png)
                    asset.layer_kind=layer_kind;asset.width=asset.height=size;asset.coordinate_space='COMPARISON_14' if size==14 else 'ALGORITHM_224';asset.sha256=hashlib.sha256(png).hexdigest();asset.size_bytes=len(png)
                    summary[field]=dict(asset_id=aid,layer_kind=layer_kind,width=size,height=size,coordinate_space=asset.coordinate_space,value_min=0,value_max=1,origin='TOP_LEFT_PIXEL_EDGE',x_axis='RIGHT',y_axis='DOWN',display_interpolation_only=True)
                    if scale==64:row['assets'][aid]['sha256']=asset.sha256
                summaries.append(summary)
            result.source='LIVE_CASE';result.result_json=dict(result.result_json,source='LIVE_CASE',model_version=MODEL['checkpoint_sha256'],preprocessing_version=MODEL['preprocessing_version'],protocol_id=MODEL['protocol_id'],scale_summaries=summaries,prediction=dict(predicted_class=1,class_label='positive',positive_probability=.7,predicted_class_confidence=.7,inference_time_ms=1))
        db.commit()
    engine.dispose()
    binding['input_sha256']=[r['input_sha256'] for r in policy['records']];binding['source_db']['sha256']=legacy.sha(binding['source_db']['path'])
    Path(policy['original_binding']['path']).write_text(json.dumps(binding));policy['original_binding']['sha256']=legacy.sha(policy['original_binding']['path']);policy['model']=MODEL
    candidate=folder/'candidate';demo64_build.prepare(candidate,policy)
    (candidate/'public/generated.dcm').write_bytes(dicom)
    (candidate/'lifecycle.html').write_text('''<!doctype html><div id="app"></div><script type="module">
import '/src/style.css';import {createApp,h,ref} from 'vue';import Viewer from '/src/viewer/CornerstoneSliceViewer.vue';
const bytes=await(await fetch('/mvp/generated.dcm')).blob();
const file=ref(new File([bytes],'generated.dcm'));const raster=document.createElement('canvas');raster.width=raster.height=224;raster.getContext('2d').fillRect(0,0,224,224);
const layer={asset_id:'response-64.png',layer_kind:'CANDIDATE_RESPONSE',width:224,height:224,coordinate_space:'ALGORITHM_224',origin:'TOP_LEFT_PIXEL_EDGE',x_axis:'RIGHT',y_axis:'DOWN',display_interpolation_only:true};
const overlay={url:raster.toDataURL(),sliceId:'generated',layer,geometry:{rawWidth:112,rawHeight:80,modelWidth:224,modelHeight:224,rasterWidth:224,rasterHeight:224}};
const shown=ref(true),current=ref(overlay);let app=createApp({setup:()=>()=>h('div',{class:'result-image-panel'},[shown.value?h(Viewer,{file:file.value,sliceId:'generated',sliceWidth:112,sliceHeight:80,overlay:current.value,overlayVisible:true}):null])});app.mount('#app');
window.generated={url:overlay.url,replace:()=>file.value=new File([bytes],'replacement.dcm'),clear:()=>file.value=null,
bad:()=>file.value=new File(['bad'],'bad.dcm'),assetClear:()=>current.value=null,assetRestore:()=>current.value=overlay,
hide:()=>shown.value=false,show:()=>shown.value=true,remove:()=>app.unmount()};
</script>''')
    plan=folder/'generated-plan.json';plan.write_text(json.dumps(dict(frozen=dict(dist=str(candidate/'dist')),policy=policy,scope='GENERATED_ONLY')))
    return candidate,plan


def build(candidate,log):
    config=Path(candidate)/'generated-build.config.mjs'
    config.write_text("import base from './vite.config.ts';export default async env=>{const c=await base(env);c.build={rollupOptions:{input:{app:'index.html',lifecycle:'lifecycle.html'}}};return c;}")
    with Path(log).open('w') as stream:
        env=dict(os.environ,VITE_PUBLIC_BASE='/mvp/')
        subprocess.run(['/opt/homebrew/bin/npm','exec','vue-tsc','--','-b'],cwd=candidate,env=env,stdout=stream,stderr=stream,check=True)
        subprocess.run(['/opt/homebrew/bin/npm','exec','vite','--','build','--config',str(config.resolve())],cwd=candidate,env=env,stdout=stream,stderr=stream,check=True)


def start(plan,folder):
    program='import json,sys;from pathlib import Path;from qa.local_mvp_demo64 import serve;d=json.load(open(sys.argv[1]));serve(d["frozen"],d["policy"],Path(sys.argv[2]))'
    log=(folder/'generated-service.log').open('w');run=folder/'services'
    process=subprocess.Popen([sys.executable,'-c',program,str(plan),str(run)],cwd=ROOT,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(ROOT)+os.pathsep+os.environ.get('PYTHONPATH','')),stdout=log,stderr=log)
    deadline=time.monotonic()+20
    while not (run/'restore-ready.json').exists():
        if process.poll() is not None:raise RuntimeError('GENERATED_SERVICE_EXITED')
        if time.monotonic()>deadline:raise TimeoutError('GENERATED_STARTUP')
        time.sleep(.05)
    return process,log,run


def core_url(dist):
    # Use actual build's core chunk, not a prior build's content-derived filename.
    for p in (Path(dist)/'assets').glob('*.js'):
        if 'as getRenderingEngines' in p.read_text():return '/mvp/assets/'+p.name
    for p in (Path(dist)/'assets').glob('*.js'):
        if 'CORNERSTONE_STACK_NEW_IMAGE' in p.read_text() and 'as t,' in p.read_text():return '/mvp/assets/'+p.name
    raise ValueError('GENERATED_CORE_CHUNK_NOT_FOUND')


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);a=p.parse_args()
    candidate,plan=setup(a.folder);build(candidate,a.folder/'build.log');print(json.dumps(dict(candidate=str(candidate),plan=str(plan))))
