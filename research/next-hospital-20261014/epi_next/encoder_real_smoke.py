"""Predeclared strict FP32 CT-FM tests then exact DATA-v3 center blocks."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import subprocess
import sys
import threading
import time
import traceback
import warnings

import numpy as np
from .encoder_ctfm_mps_smoke import file_sha,write_new,update_progress
from .encoder_real_input import DATA_V3_SHA,consume_v3,prepare_center_patch


def validate_config(c):
    if (c['synthetic_sizes']!=[32,64] or c['real_patch_shape_spl']!=[64,64,64] or c['case_order']!=[1,2,3]
        or c['warmup_runs_per_device']!=1 or c['timed_runs_per_device']!=3 or c['dtype']!='float32'
        or c['timeout_seconds_per_trial']>120 or c['rss_limit_bytes']>6*1024**3 or c['mps_driver_limit_bytes']>6*1024**3
        or c['mps_fallback_enabled'] or c['mps_fast_math']):
        raise ValueError('dispatch bounds/strict policy changed')
    if (c['tolerance']!={'max_absolute_error':.001,'mean_absolute_error':.0001,'atol':.001,'rtol':.0001}
        or c['checkpoint_sha256']!='b521ff13764ad0fce67f8ad2e5aa9ccc0823f69e4544b446581d8a2dee686215'
        or c['data_delivery_sha256']!=DATA_V3_SHA or c['seed']!=17 or c['cpu_threads']!=1
        or c['native_roundtrip_tolerance_voxels']!=1e-8
        or any(not np.isfinite(c[k]) or c[k]<=0 for k in ['timeout_seconds_per_trial','rss_limit_bytes','mps_driver_limit_bytes','sampling_seconds','max_swap_increase_bytes'])
        or c['minimum_memory_free_percent']<20):
        raise ValueError('predeclared numerical/identity/resource policy changed')


def full_compare(a,b,tol):
    if a.shape!=b.shape or a.dtype!=np.float32 or b.dtype!=np.float32 or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('finite matching FP32 full features required')
    delta=np.abs(a.astype(np.float64)-b.astype(np.float64))
    close=bool(np.allclose(a,b,atol=tol['atol'],rtol=tol['rtol']))
    ok=close and delta.max()<=tol['max_absolute_error'] and delta.mean()<=tol['mean_absolute_error']
    return dict(status='PASS' if ok else 'FAIL',elements=int(a.size),max_absolute_error=float(delta.max()),
        mean_absolute_error=float(delta.mean()),rmse=float(np.sqrt(np.mean(delta**2))),allclose=close,tolerance=tol)


def system_memory():
    p=subprocess.check_output(['memory_pressure','-Q'],text=True)
    swap=subprocess.check_output(['sysctl','-n','vm.swapusage'],text=True)
    number,unit=re.search(r'used\s*=\s*([\d.]+)([KMG])',swap).groups()
    return dict(free_percent=int(re.search(r'free percentage:\s*(\d+)%',p)[1]),
        swap_used_bytes=int(float(number)*1024**{'K':1,'M':2,'G':3}[unit]))


def lattice_from_model(model):
    receptive,jump,offset=1,1,0.
    modules=[model.conv_init]
    for level in model.layers:
        for block in level['blocks']: modules.extend([block.conv1,block.conv2])
        if hasattr(level['downsample'],'kernel_size'): modules.append(level['downsample'])
    for conv in modules:
        k,s,p,d=[v[0] for v in (conv.kernel_size,conv.stride,conv.padding,conv.dilation)]
        if any(len(set(v))!=1 for v in (conv.kernel_size,conv.stride,conv.padding,conv.dilation)):
            raise ValueError('anisotropic architecture requires separate lattice review')
        offset+=((k-1)*d/2-p)*jump
        receptive+=(k-1)*d*jump; jump*=s
    if (receptive,jump,offset)!=(469,16,0): raise ValueError('unexpected encoder spatial lattice')
    return dict(stride=jump,nominal_center_offset=offset,receptive_field=receptive,conv_count=len(modules))


def run_child(args):
    if 'torch' in sys.modules: raise RuntimeError('Torch imported before strict fallback environment')
    os.environ.update(PYTORCH_ENABLE_MPS_FALLBACK='0',PYTORCH_MPS_FAST_MATH='0',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    config=json.loads(args.config.read_bytes());validate_config(config)
    result=dict(status='FAIL',cpu_status='NOT RUN',mps_execution_status='NOT RUN',comparison_status='NOT RUN',
        actual_encoder_calls=0,warnings=[],failure_reason=None,config_sha256=file_sha(args.config),
        source_sha256=file_sha(__file__),input_source_sha256=file_sha(Path(__file__).with_name('encoder_real_input.py')),
        input_kind='synthetic' if args.size else 'real_center_patch',
        cpu_warmup_seconds=[],cpu_inference_seconds=[],mps_warmup_seconds=[],mps_inference_seconds=[])
    stop=threading.Event();sampler=None;sample_error=[]
    memory=dict(current_allocated_peak_sampled_bytes=None,driver_allocated_peak_sampled_bytes=None,samples=0,sampling_seconds=.02)
    caught=[];started=time.perf_counter()
    try:
        import torch,monai,safetensors
        from .encoder import load_ctfm_local,CTFM_MODEL_REVISION
        torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(config['seed'])
        result.update(mps_is_built=torch.backends.mps.is_built(),mps_is_available=torch.backends.mps.is_available(),
            environment=dict(torch=torch.__version__,monai=monai.__version__,safetensors=safetensors.__version__,
                python=sys.version.split()[0],PYTORCH_ENABLE_MPS_FALLBACK='0',PYTORCH_MPS_FAST_MATH='0'),
            model_revision=CTFM_MODEL_REVISION,checkpoint_sha256=config['checkpoint_sha256'])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            before=time.perf_counter();adapter=load_ctfm_local(args.weights,config['checkpoint_sha256'])
            result['loading_seconds']=time.perf_counter()-before
            result['feature_lattice']=lattice_from_model(adapter.encoder)
            if args.size:
                x=torch.linspace(0,1,args.size**3,dtype=torch.float32).reshape(1,1,args.size,args.size,args.size)
            else:
                array=np.load(args.input,allow_pickle=False)
                if array.shape!=(1,1,64,64,64) or array.dtype!=np.float32 or not np.isfinite(array).all() or array.min()<0 or array.max()>1:
                    raise ValueError('preprocessed exact bounded input required')
                x=torch.from_numpy(array)
            result['input_shape']=list(x.shape);result['input_content_sha256']=hashlib.sha256(x.numpy().tobytes()).hexdigest()
            cpu=[];mps=[];readbacks=[]
            with torch.inference_mode():
                for i in range(config['warmup_runs_per_device']+config['timed_runs_per_device']):
                    before=time.perf_counter();features=adapter.extract(x)
                    seconds=time.perf_counter()-before
                    result['cpu_warmup_seconds' if i==0 else 'cpu_inference_seconds'].append(seconds)
                    if i: cpu.append(features.numpy().copy())
            result['cpu_status']='PASS'; result['feature_shape']=list(cpu[-1].shape)
            for i,value in enumerate(cpu):
                with (args.output/f'cpu_features_{i}.npy').open('xb') as f: np.save(f,value,allow_pickle=False)
            if args.mps:
                if not result['mps_is_available']: raise RuntimeError('MPS_UNAVAILABLE')
                recommended=int(torch.mps.recommended_max_memory())
                torch.mps.set_per_process_memory_fraction(min(.4,config['mps_driver_limit_bytes']/recommended))
                result['recommended_max_memory_bytes']=recommended
                def sample():
                    try:
                        while not stop.is_set():
                            current=int(torch.mps.current_allocated_memory());driver=int(torch.mps.driver_allocated_memory())
                            memory['current_allocated_peak_sampled_bytes']=max(memory['current_allocated_peak_sampled_bytes'] or 0,current)
                            memory['driver_allocated_peak_sampled_bytes']=max(memory['driver_allocated_peak_sampled_bytes'] or 0,driver)
                            memory['samples']+=1
                            if driver>config['mps_driver_limit_bytes']:
                                update_progress(args.output/'progress.json',dict(status='BLOCKED',failure_reason='MPS_DRIVER_LIMIT',memory=memory))
                                os._exit(88)
                            stop.wait(config['sampling_seconds'])
                    except Exception as exc:
                        sample_error.append(str(exc))
                        try:
                            update_progress(args.output/'progress.json',dict(status='FAIL',failure_reason='MPS_MONITOR_FAILED',sampler_error=str(exc),memory=memory))
                        finally:
                            os._exit(89) # never continue silently without the resource monitor
                sampler=threading.Thread(target=sample,daemon=True);sampler.start()
                torch.mps.synchronize();before=time.perf_counter();adapter.to('mps');xm=x.to('mps');torch.mps.synchronize()
                result['transfer_seconds']=time.perf_counter()-before
                observations=Counter();wrong_devices=[];hooks=[]
                def audit(module,inputs,output):
                    observations[type(module).__name__]+=1
                    for tensor in [*inputs,output]:
                        if isinstance(tensor,torch.Tensor) and tensor.device.type!='mps': wrong_devices.append(type(module).__name__)
                for module in adapter.modules():
                    if isinstance(module,(torch.nn.Conv3d,torch.nn.BatchNorm3d,torch.nn.ReLU)):
                        hooks.append(module.register_forward_hook(audit))
                with torch.inference_mode():
                    for i in range(config['warmup_runs_per_device']+config['timed_runs_per_device']):
                        torch.mps.synchronize();before=time.perf_counter();features=adapter.extract(xm);torch.mps.synchronize()
                        seconds=time.perf_counter()-before
                        result['mps_warmup_seconds' if i==0 else 'mps_inference_seconds'].append(seconds)
                        if i==0:
                            for hook in hooks: hook.remove()
                            if wrong_devices: raise RuntimeError('CPU_MODULE_TENSOR_INSIDE_MPS_WARMUP')
                        else:
                            before=time.perf_counter();mps.append(features.cpu().numpy().copy());torch.mps.synchronize()
                            readbacks.append(time.perf_counter()-before)
                stop.set();sampler.join(timeout=2)
                if sampler.is_alive() or sample_error or not memory['samples']: raise RuntimeError('MPS_MEMORY_MONITOR_FAILED')
                result.update(mps_execution_status='PASS',readback_seconds=readbacks,
                    mps_warmup_module_observations=dict(observations),cpu_module_tensors=wrong_devices)
                result['comparisons']=[full_compare(a,b,config['tolerance']) for a,b in zip(cpu,mps)]
                result['comparison_status']='PASS' if all(v['status']=='PASS' for v in result['comparisons']) else 'FAIL'
                for i,value in enumerate(mps):
                    with (args.output/f'mps_features_{i}.npy').open('xb') as f: np.save(f,value,allow_pickle=False)
                result['status']=result['comparison_status']
            else:
                result.update(status='PASS',mps_execution_status='NOT RUN',comparison_status='NOT RUN',cpu_only_reason='MPS_GATE_NOT_PASS')
            result['cpu_repeat_max_difference']=max(float(np.max(np.abs(v-cpu[0]))) for v in cpu)
            result['mps_repeat_max_difference']=max(float(np.max(np.abs(v-mps[0]))) for v in mps) if mps else None
    except Exception as exc:
        result.update(status='FAIL',failure_reason=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc())
    finally:
        stop.set()
        if sampler: sampler.join(timeout=2)
        result['warnings']=[str(w.message) for w in caught]
        result['fallback_warning_detected']=any('fallback' in w.lower() or 'fall back' in w.lower() for w in result['warnings'])
        if result['fallback_warning_detected']: result.update(status='FAIL',failure_reason='FALLBACK_WARNING')
        if 'adapter' in locals(): result['actual_encoder_calls']=adapter.actual_queries
        result['peak_process_rss_bytes']=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        result['mps_memory']=memory;result['whole_child_seconds']=time.perf_counter()-started
        result['output_hashes']={p.name:file_sha(p) for p in args.output.glob('*features_*.npy')}
        write_new(args.output/'receipt.json',result)
    return 0 if result['status']=='PASS' else 1


def supervise(command,directory,c):
    start=time.monotonic();reason=None;peak=0;samples=[];child=None
    environment=dict(os.environ,PYTORCH_ENABLE_MPS_FALLBACK='0',PYTORCH_MPS_FAST_MATH='0',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    try:
        initial=system_memory()
        if initial['free_percent']<c['minimum_memory_free_percent']: raise RuntimeError('SYSTEM_MEMORY_PRESSURE_BEFORE_START')
        with (directory/'child.log').open('x') as log:
            child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=environment)
            while child.poll() is None:
                elapsed=time.monotonic()-start
                text=subprocess.run(['ps','-o','rss=','-p',str(child.pid)],capture_output=True,text=True).stdout.strip()
                rss=int(text or 0)*1024;peak=max(peak,rss)
                if not samples or elapsed-samples[-1]['elapsed_seconds']>.5:
                    samples.append(dict(elapsed_seconds=elapsed,rss_bytes=rss,**system_memory()))
                latest=samples[-1]
                if elapsed>c['timeout_seconds_per_trial']: reason='TIMEOUT'
                elif rss>c['rss_limit_bytes']: reason='RSS_LIMIT'
                elif latest['free_percent']<c['minimum_memory_free_percent']: reason='SYSTEM_MEMORY_PRESSURE'
                elif latest['swap_used_bytes']-initial['swap_used_bytes']>c['max_swap_increase_bytes']: reason='SWAP_INCREASE_LIMIT'
                if reason: child.kill();break
                time.sleep(.05)
            code=child.wait()
    except Exception as exc:
        reason=f'SUPERVISOR_ERROR: {exc}';code=None
    finally:
        if child and child.poll() is None: child.kill();child.wait()
    path=directory/'receipt.json'
    result=json.loads(path.read_bytes()) if path.exists() else dict(status='BLOCKED' if reason or code==88 else 'FAIL',
        cpu_status='NOT RUN',mps_execution_status='NOT RUN',comparison_status='NOT RUN',actual_encoder_calls=0,
        failure_reason=reason or ('MPS_DRIVER_LIMIT' if code==88 else 'MPS_MONITOR_FAILED' if code==89 else f'CHILD_EXIT_{code}'))
    if reason: result.update(status='BLOCKED',failure_reason=reason)
    supervision=dict(result=result,command=command,strict_environment={k:environment[k] for k in ['PYTORCH_ENABLE_MPS_FALLBACK','PYTORCH_MPS_FAST_MATH','OMP_NUM_THREADS','MKL_NUM_THREADS']},
        elapsed_seconds=time.monotonic()-start,exit_code=code,process_running=False,parent_sampled_peak_rss_bytes=peak,
        system_memory_samples=samples)
    write_new(directory/'supervision.json',supervision)
    print(json.dumps(dict(trial=directory.name,status=result['status'],cpu_status=result['cpu_status'],
        comparison_status=result['comparison_status'],failure_reason=result.get('failure_reason'))),flush=True)
    return supervision


def run(args):
    c=json.loads(args.config.read_bytes());validate_config(c)
    if args.resume:
        manifest=json.loads((args.output/'first_case_manifest.json').read_bytes())
        if manifest['status']!='PASS' or len(manifest['real'])!=1 or manifest['real'][0]['result']['cpu_status']!='PASS':
            raise ValueError('first-case engineering gate not passed')
        frozen=args.output/'config.json'
        if file_sha(frozen)!=manifest['config_sha256'] or c!=json.loads(frozen.read_bytes()): raise ValueError('resume config changed')
        if manifest['source_sha256']!=file_sha(__file__) or manifest['input_source_sha256']!=file_sha(Path(__file__).with_name('encoder_real_input.py')):
            raise ValueError('resume source changed')
    else:
        args.output.mkdir(parents=True,exist_ok=False,mode=0o700)
        write_new(args.output/'config.json',c);frozen=args.output/'config.json'
        cases,consumer=consume_v3(args.delivery,args.output)
        print(json.dumps(dict(consumer_receipt=str(args.output/'consumer_receipt.json'),consumer_sha256=file_sha(args.output/'consumer_receipt.json'))),flush=True)
        manifest=dict(status='RUNNING',config_sha256=file_sha(frozen),consumer_receipt_sha256=file_sha(args.output/'consumer_receipt.json'),
            synthetic=[],real=[],new_gt_use=False,head_training='NOT RUN',source_sha256=file_sha(__file__),
            input_source_sha256=file_sha(Path(__file__).with_name('encoder_real_input.py')),
            git_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip())
        # Freeze all three geometry-selected inputs before any model forward.
        for case in cases:
            ordinal=case['case_index'];mapping=case['mapping']
            native=np.load(mapping['native_hu_volume_path'],mmap_mode='r',allow_pickle=False)
            x,ledger=prepare_center_patch(native,mapping['affine_lps'],tuple(c['real_patch_shape_spl']));del native
            with (args.output/f'case_{ordinal}_input.npy').open('xb') as f: np.save(f,x,allow_pickle=False)
            ledger.update(case_index=ordinal,data_delivery_sha256=c['data_delivery_sha256'],native_volume_sha256=mapping['native_hu_volume_sha256'],
                case_manifest_sha256=case['case_manifest_sha256'],native_header_audit_scope=case['header_audit_scope'],
                native_slice_sop_mapping=mapping['ordered_sop_uids'])
            write_new(args.output/f'case_{ordinal}_ledger.json',ledger)
        manifest['prepared_input_hashes']={f'case_{i}':file_sha(args.output/f'case_{i}_input.npy') for i in [1,2,3]}
        manifest['prepared_ledger_hashes']={f'case_{i}':file_sha(args.output/f'case_{i}_ledger.json') for i in [1,2,3]}
        manifest['selection_locked_before_model_forward']=True
        write_new(args.output/'selection_lock.json',manifest)
    def trial(folder,size=None,input_path=None,mps=True):
        folder.mkdir()
        cmd=[sys.executable,'-m','epi_next.encoder_real_smoke','--child','--config',str(frozen),'--weights',str(args.weights),'--output',str(folder)]
        if size: cmd.extend(['--size',str(size)])
        if input_path: cmd.extend(['--input',str(input_path)])
        if mps: cmd.append('--mps')
        return supervise(cmd,folder,c)
    if not args.resume:
        for size in c['synthetic_sizes']:
            value=trial(args.output/f'synthetic_{size}',size=size)
            manifest['synthetic'].append(value)
            if value['result']['status']!='PASS': break
    synthetic_ok=len(manifest['synthetic'])==2 and all(v['result']['status']=='PASS' for v in manifest['synthetic'])
    mps_ok=synthetic_ok and all(v['result']['status']=='PASS' for v in manifest['real'])
    for ordinal in ([2,3] if args.resume else [1] if args.first_case_only else [1,2,3]):
        input_path=args.output/f'case_{ordinal}_input.npy'
        if (file_sha(input_path)!=manifest['prepared_input_hashes'][f'case_{ordinal}'] or
                file_sha(args.output/f'case_{ordinal}_ledger.json')!=manifest['prepared_ledger_hashes'][f'case_{ordinal}']):
            raise ValueError('fixed input/ledger changed before real forward')
        value=trial(args.output/f'real_case_{ordinal}',input_path=input_path,mps=mps_ok)
        value['ledger_sha256']=file_sha(args.output/f'case_{ordinal}_ledger.json')
        manifest['real'].append(value)
        if value['result']['cpu_status']!='PASS': break
        if value['result']['status']!='PASS': mps_ok=False
    expected=1 if args.first_case_only else 3
    manifest.update(status='PASS' if len(manifest['real'])==expected and all(v['result']['cpu_status']=='PASS' for v in manifest['real']) else 'FAIL',
        scope=('FIRST_CASE' if args.first_case_only else 'THREE_CASE')+('_CPU_MPS_CENTER_BLOCK_ENGINEERING' if mps_ok else '_CPU_ONLY_OR_MIXED_CENTER_BLOCK_ENGINEERING'),
        mps_compatibility='PASS' if synthetic_ok else 'FAIL',real_mps_status='PASS' if mps_ok else 'FAIL_OR_NOT_RUN',
        actual_encoder_calls=sum(v['result']['actual_encoder_calls'] for v in manifest['synthetic']+manifest['real']),
        real_case_count=len(manifest['real']),process_running=False)
    final_path=args.output/('first_case_manifest.json' if args.first_case_only else 'manifest.json')
    write_new(final_path,manifest)
    print(json.dumps(dict(status=manifest['status'],mps_compatibility=manifest['mps_compatibility'],real_case_count=manifest['real_case_count'],
        actual_encoder_calls=manifest['actual_encoder_calls'],manifest_sha256=file_sha(final_path))),flush=True)
    return 0 if manifest['status']=='PASS' else 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--weights',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--delivery',type=Path);p.add_argument('--child',action='store_true');p.add_argument('--size',type=int,choices=[32,64]);p.add_argument('--input',type=Path);p.add_argument('--mps',action='store_true')
    p.add_argument('--first-case-only',action='store_true');p.add_argument('--resume',action='store_true')
    a=p.parse_args();os.umask(0o077)
    if a.child: return run_child(a)
    try: return run(a)
    except Exception as exc:
        if a.output.exists():
            write_new(a.output/'terminal_failure.json',dict(status='FAIL',failure_reason=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc(),process_running=False))
        raise


if __name__=='__main__':
    raise SystemExit(main())
