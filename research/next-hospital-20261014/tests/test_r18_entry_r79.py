"""Actual parent -> -m R18 child -> isolated pinned supervisor. Generated adapters only."""

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[3]
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = Path(str(_PUBLIC_ROOT / 'research/next-hospital-20261014/.local/phase2/wave1-recovery-chain-14bf16e-v1'))

HOOK = r'''
import sys, os, json
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, os.environ['GENERATED_SHARED_ROOT'])
from epinext_wave1_recovery_chain_v1 import wave1_supervisor as shared, hospital_runtime
hospital_runtime.QUEUE_ROOT=Path(os.environ['GENERATED_ROOT'])/'queue'
class Monitor(shared.SystemMonitor):
    def pressure(self):
        return dict(free_fraction=.8,free_bytes=8*shared.GIB,total_bytes=10*shared.GIB,swap_used_bytes=0)
def supervise(spec,cmd,output,dep,sha,**kwargs):
    # Real subprocess and pinned supervisor; only isolated queue/pressure fixture.
    try:
        return shared.run_supervised(spec,cmd,output,dep,sha,_monitor=Monitor())
    except Exception:
        import traceback; traceback.print_exc(); raise
proxy=SimpleNamespace(SupervisionSpec=shared.SupervisionSpec,ChildGuard=shared.ChildGuard,run_supervised=supervise)
def trace(frame,event,arg):
    if event=='call' and frame.f_code.co_name=='main' and frame.f_code.co_filename.endswith('/resnet18_mil_v1.py'):
        g=frame.f_globals;p=g['p']
        g['validate_request']=lambda request: request
        p.load_shared=lambda request: proxy
        p.validate_records=lambda rows: []
        g['build_backbone']=lambda checkpoint: object()
        def generated_cache(records,manifest,context,output,backbone,meter):
            Path(output).mkdir(parents=True,exist_ok=True)
            (Path(output)/'generated-module-loaded.json').write_text(json.dumps(dict(module_spec=g['__spec__'].name,generated_only=True,medical_calls=0)))
        g['cache_phase']=generated_cache
        sys.settrace(None)
        if '--child' in sys.argv and os.environ['GENERATED_MODE']=='early':
            raise SystemExit(7)
    return trace
sys.settrace(trace)
'''


@pytest.mark.parametrize('mode', ['success', 'early'])
def test_real_module_parent_child_receipt(tmp_path, mode):
    from epi_next import ctfm_research_pipeline_v4 as p
    root=tmp_path.resolve();(root/'sitecustomize.py').write_text(HOOK)
    template=json.loads((ROOT/'research/next-hospital-20261014/reports/resnet18_mil_v1/approval_request_v1/cache-request-template.json').read_bytes())['executable_request']
    req=dict(template,delivery_root=str(root/'assets'),output=str(root/'assets/cache'),supervisor_output=str(root/'supervisor'))
    req['spec']=dict(req['spec'],job_id='generated-r79-'+mode,task_key='GENERATED-R79-'+mode,timeout_seconds=30,per_case_seconds=15,telemetry_startup_seconds=15)
    (root/'assets').mkdir()
    empty=root/'generated-records.json';empty.write_text('[]')
    req['data_manifest']=dict(path=str(empty),sha256=p.file_sha(empty))
    req['fixed_group_projection_sha256']=p.digest(p.encoded([]))
    req['administrative_recovery']=dict(path=str(root/'not-used.json'),sha256='0'*64)
    request=root/'request.json';request.write_bytes(p.encoded(req));rs=p.file_sha(request)
    approval=root/'approval.json';approval.write_bytes(p.encoded(dict(schema='R18_MIL_APPROVAL_V1',status='APPROVED_NEW_SCOPE',owner='ENCODER',phase='cache',task_key=req['spec']['task_key'],request_sha256=rs,retry=False)))
    dispatch=root/'dispatch.json';dispatch.write_bytes(p.encoded(dict(schema='R18_MIL_DISPATCH_V1',status='EXCLUSIVE_SLOT_ASSIGNED',owner='ENCODER',phase='cache',task_key=req['spec']['task_key'],request_sha256=rs,approval_sha256=p.file_sha(approval),retry=False)))
    cmd=[sys.executable,'-m','epi_next.resnet18_mil_v1','--request',str(request),'--request-sha',rs,'--approval',str(approval),'--approval-sha',p.file_sha(approval),'--dispatch',str(dispatch),'--dispatch-sha',p.file_sha(dispatch),'--execute']
    env=dict(os.environ,PYTHONPATH=str(root)+':'+str(ROOT/'research/next-hospital-20261014')+':'+str(ROOT),GENERATED_SHARED_ROOT=str(BUNDLE),GENERATED_ROOT=str(root),GENERATED_MODE=mode,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    run=subprocess.run(cmd,env=env,cwd=ROOT,text=True,capture_output=True,timeout=45)
    receipt_path=root/'supervisor'/req['spec']['job_id']/'supervisor-receipt.json'
    assert receipt_path.exists(), (run.returncode,run.stdout,run.stderr)
    receipt=json.loads(receipt_path.read_bytes())
    assert receipt['counters']['forward']==receipt['counters']['backward']==0
    child=json.loads((receipt_path.parent/'command.json').read_bytes())['argv']
    assert child[1:3]==['-m','epi_next.resnet18_mil_v1'] and '--child' in child
    if mode=='success':
        assert run.returncode==0 and receipt['status']=='SUCCESS' and receipt['slot_completed'],(run.stdout,receipt)
        proof=json.loads((root/'assets/cache/generated-module-loaded.json').read_bytes())
        assert proof['module_spec']=='epi_next.resnet18_mil_v1'
    else:
        assert run.returncode==2 and receipt['status']=='FAILED'
        assert not (root/'assets/cache/generated-module-loaded.json').exists()
    (root/'process-result.json').write_text(json.dumps(dict(mode=mode,returncode=run.returncode,stdout=run.stdout,stderr=run.stderr,receipt=receipt),indent=2))
    print(mode, 'exit',run.returncode,'receipt',receipt['status'],'reason',receipt['reason'],'slot_completed',receipt['slot_completed'])
