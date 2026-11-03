"""EPI-NEXT bounded CPU/MPS encoder comparison, synthetic volumes only.

This module imports no torch until the child has disabled MPS CPU fallback.
Results describe numerical differences, not D10/clinical acceptance.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time


DEFAULT_CONFIG = {
    'experiment_id': 'EPI-NEXT-CTFM-MPS-PHASE2-v1',
    'sizes': [32, 64], 'dtype': 'float32', 'seed': 17, 'cpu_threads': 1,
    'timeout_seconds_per_size': 120, 'rss_limit_bytes': 6 * 1024 ** 3,
    'mps_driver_limit_bytes': 6 * 1024 ** 3, 'sampling_seconds': .02,
    'relative_floor_fraction': .001, 'relative_absolute_floor': 1e-12,
    'real_case_count': 0, 'numerical_acceptance': 'NOT_ASSESSED_NO_PREDECLARED_THRESHOLD',
}


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n').encode()


def write_new(path, value):
    with Path(path).open('xb') as f:
        f.write(json_bytes(value))


def update_progress(path, value):
    # Only a progress snapshot inside this exclusively owned run directory is replaced.
    pending = Path(str(path)+'.pending')
    pending.write_bytes(json_bytes(value))
    os.replace(pending, path)


def validate_config(config):
    if config != dict(DEFAULT_CONFIG, sizes=config.get('sizes')):
        raise ValueError('only the bounded size list may vary in phase2 config')
    sizes = config['sizes']
    if sizes not in ([32], [32, 64]):
        raise ValueError('authorized staircase is 32 or 32 then 64 only')


def compare_features(cpu, mps, config=DEFAULT_CONFIG):
    import numpy as np
    a, b = np.asarray(cpu, dtype=np.float64), np.asarray(mps, dtype=np.float64)
    if a.shape != b.shape or not a.size or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('finite matching nonempty feature arrays required')
    delta = b-a
    scale = float(np.max(np.abs(a)))
    floor = max(config['relative_absolute_floor'], config['relative_floor_fraction'] * scale)
    denominator = np.maximum(np.abs(a), floor)
    na, nb = float(np.linalg.norm(a.ravel())), float(np.linalg.norm(b.ravel()))
    cosine = None if na == 0 or nb == 0 else float(np.clip(np.dot(a.ravel(), b.ravel())/(na*nb), -1, 1))
    return dict(max_abs=float(np.max(np.abs(delta))), rmse=float(np.sqrt(np.mean(delta**2))),
                max_relative_to_reference_peak=float(np.max(np.abs(delta))/max(scale, config['relative_absolute_floor'])),
                max_elementwise_relative_with_floor=float(np.max(np.abs(delta)/denominator)),
                relative_denominator_floor=floor, reference_abs_peak=scale, cosine=cosine,
                cosine_status='UNDEFINED_ZERO_NORM' if cosine is None else 'DEFINED',
                reference_l2=na, candidate_l2=nb, feature_shape=list(a.shape),
                numerical_acceptance=config['numerical_acceptance'])


def classify_exception(exc):
    text = str(exc).lower()
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return 'DEPENDENCY_UNAVAILABLE'
    if 'not implemented' in text or 'not currently implemented' in text or 'unsupported' in text:
        return 'UNSUPPORTED_OPERATOR'
    if 'out of memory' in text or 'memory budget' in text:
        return 'MEMORY_BUDGET'
    return 'FAILED'


def run_child(args):
    if 'torch' in sys.modules:
        raise RuntimeError('torch was imported before fallback policy')
    os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '0'
    os.environ['PYTORCH_MPS_FAST_MATH'] = '0'
    os.environ['OMP_NUM_THREADS'] = '1'
    os.environ['MKL_NUM_THREADS'] = '1'
    started = time.perf_counter()
    config = json.loads((args.output/'config.json').read_text())
    child_dir = args.output / ('size_'+str(args.size))
    result = dict(status='RUNNING', size=args.size, phase='IMPORT', actual_encoder_calls=0,
                  real_case_count=0, fallback_enabled=False, exception=None)
    progress = child_dir/'progress.json'
    done = threading.Event()
    sampler = None
    memory = dict(current_allocated_peak_sampled_bytes=0, driver_allocated_peak_sampled_bytes=0,
                  samples=0, sampling_seconds=config['sampling_seconds'])
    try:
        update_progress(progress, result)
        import resource
        import numpy as np
        import torch
        import monai
        import safetensors
        from .encoder import load_ctfm_local, CTFM_MODEL_REVISION
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        torch.manual_seed(config['seed'])
        if not torch.backends.mps.is_built() or not torch.backends.mps.is_available():
            raise RuntimeError('MPS_UNAVAILABLE')
        recommended = int(torch.mps.recommended_max_memory())
        fraction = min(.4, config['mps_driver_limit_bytes']/recommended)
        torch.mps.set_per_process_memory_fraction(fraction)
        result.update(recommended_max_memory_bytes=recommended, allocator_fraction=fraction,
                      allocator_limit_bytes=int(recommended*fraction))
        result['phase'] = 'LOADING'
        update_progress(progress, result)
        before = time.perf_counter()
        adapter = load_ctfm_local(args.weights, args.sha256)
        loading_seconds = time.perf_counter()-before
        x = torch.linspace(0., 1., args.size**3, dtype=torch.float32).reshape(1,1,args.size,args.size,args.size)
        result.update(phase='CPU_INFERENCE', input_shape=list(x.shape), loading_seconds=loading_seconds)
        update_progress(progress, result)
        before = time.perf_counter()
        cpu = adapter.extract(x).numpy().copy()
        cpu_seconds = time.perf_counter()-before
        result.update(actual_encoder_calls=adapter.actual_queries, phase='MPS_TRANSFER', cpu_seconds=cpu_seconds)
        update_progress(progress, result)
        # Start sampling before the model/input transfer. Allocator cap also applies
        # between samples. Driver memory is sampled, not a claimed exact peak.
        def sample_memory():
            try:
                while not done.is_set():
                    current = int(torch.mps.current_allocated_memory())
                    driver = int(torch.mps.driver_allocated_memory())
                    memory['current_allocated_peak_sampled_bytes'] = max(memory['current_allocated_peak_sampled_bytes'], current)
                    memory['driver_allocated_peak_sampled_bytes'] = max(memory['driver_allocated_peak_sampled_bytes'], driver)
                    memory['samples'] += 1
                    if driver > config['mps_driver_limit_bytes']:
                        result.update(status='MEMORY_BUDGET', phase='MPS_MEMORY_LIMIT', mps_memory=dict(memory))
                        update_progress(progress, result)
                        os._exit(88)  # this task's child only; supervisor emits failure receipt
                    done.wait(config['sampling_seconds'])
            except Exception as exc:
                result['sampler_error'] = {'type': type(exc).__name__, 'message': str(exc)}
        sampler = threading.Thread(target=sample_memory, daemon=True)
        sampler.start()
        before = time.perf_counter()
        adapter.to('mps')
        xm = x.to('mps')
        torch.mps.synchronize()
        transfer_seconds = time.perf_counter()-before
        result.update(phase='MPS_INFERENCE', transfer_seconds=transfer_seconds)
        update_progress(progress, result)
        torch.mps.synchronize()
        before = time.perf_counter()
        fm = adapter.extract(xm)
        torch.mps.synchronize()
        mps_seconds = time.perf_counter()-before
        result.update(actual_encoder_calls=adapter.actual_queries, phase='MPS_READBACK', mps_seconds=mps_seconds)
        update_progress(progress, result)
        before = time.perf_counter()
        mps = fm.cpu().numpy().copy()
        torch.mps.synchronize()
        readback_seconds = time.perf_counter()-before
        # Explicit final samples supplement the 20-ms sampler.
        memory['current_allocated_peak_sampled_bytes'] = max(memory['current_allocated_peak_sampled_bytes'], int(torch.mps.current_allocated_memory()))
        memory['driver_allocated_peak_sampled_bytes'] = max(memory['driver_allocated_peak_sampled_bytes'], int(torch.mps.driver_allocated_memory()))
        done.set()
        sampler.join(timeout=1)
        if result.get('sampler_error'):
            raise RuntimeError('memory sampler failed')
        metrics = compare_features(cpu, mps, config)
        for name, array in [('cpu_features',cpu), ('mps_features',mps)]:
            with (child_dir/(name+'.npy')).open('xb') as f:
                np.save(f,array,allow_pickle=False)
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        result.update(status='PASS', phase='COMPLETE', evidence_type='REAL_PRETRAINED_ENCODER_SYNTHETIC_CPU_MPS',
                      acceptance_scope='EXECUTION_ONLY_NOT_NUMERICAL_OR_CLINICAL_GATE',
                      checkpoint_sha256=args.sha256, model_revision=CTFM_MODEL_REVISION,
                      feature_shape=list(cpu.shape), dtype=str(cpu.dtype), metrics=metrics,
                      mps_memory=dict(memory), peak_process_rss_bytes=int(peak if sys.platform=='darwin' else peak*1024),
                      readback_seconds=readback_seconds, total_seconds=time.perf_counter()-started,
                      input_sha256=hashlib.sha256(x.numpy().tobytes()).hexdigest(),
                      output_hashes={name:file_sha(child_dir/(name+'.npy')) for name in ['cpu_features','mps_features']},
                      environment=dict(python=platform.python_version(), torch=torch.__version__, monai=monai.__version__,
                                       safetensors=safetensors.__version__, platform=platform.platform(),
                                       PYTORCH_ENABLE_MPS_FALLBACK=os.environ['PYTORCH_ENABLE_MPS_FALLBACK'],
                                       PYTORCH_MPS_FAST_MATH=os.environ['PYTORCH_MPS_FAST_MATH']),
                      real_three_case_g1='NOT RUN', native_geometry='NOT RUN', clinical_metrics='NOT RUN',
                      pretraining_overlap_status='unknown')
    except BaseException as exc:
        if 'adapter' in locals():
            result['actual_encoder_calls'] = adapter.actual_queries
        result.update(status='MPS_UNAVAILABLE' if str(exc)=='MPS_UNAVAILABLE' else classify_exception(exc),
                      exception={'type':type(exc).__name__, 'message':str(exc)}, total_seconds=time.perf_counter()-started,
                      mps_memory=dict(memory))
    finally:
        done.set()
        if sampler is not None:
            sampler.join(timeout=1)
    write_new(child_dir/'receipt.json', result)
    return 0 if result['status']=='PASS' else 1


def supervise(command, directory, timeout_seconds, rss_limit_bytes):
    """Supervise only a known task child; never discover/kill other processes."""
    directory = Path(directory)
    start = time.monotonic()
    forced_status = None
    rss_peak = 0
    with (directory/'child.log').open('x') as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ))
        try:
            while child.poll() is None:
                if time.monotonic()-start > timeout_seconds:
                    forced_status = 'TIMEOUT'
                    child.kill()
                    break
                text = subprocess.run(['ps','-o','rss=','-p',str(child.pid)],capture_output=True,text=True).stdout.strip()
                rss = int(text)*1024 if text.isdigit() else 0
                rss_peak = max(rss_peak,rss)
                if rss > rss_limit_bytes:
                    forced_status = 'MEMORY_BUDGET'
                    child.kill()
                    break
                time.sleep(.05)
            code = child.wait()
        except BaseException:
            child.kill()
            child.wait()
            raise
    receipt = directory/'receipt.json'
    if not receipt.exists():
        progress = directory/'progress.json'
        data = json.loads(progress.read_text()) if progress.exists() else {}
        data.update(status=forced_status or ('MEMORY_BUDGET' if code==88 else 'FAILED'),
                    exit_code=code, exception=data.get('exception') or {'type':'ChildExit','message':'No complete child receipt'},
                    real_case_count=0)
        write_new(receipt,data)
    data = json.loads(receipt.read_text())
    if forced_status or code != 0:
        data['status'] = forced_status or (data['status'] if data['status']!='PASS' else 'FAILED')
    return dict(status=data['status'], exit_code=code, process_running=False,
                peak_rss_sampled_bytes=rss_peak, elapsed_seconds=time.monotonic()-start,
                receipt_sha256=file_sha(receipt), receipt=data)


def run_staircase(args):
    # Atomic namespace reservation protects every prior result, including failures.
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = dict(experiment_id=DEFAULT_CONFIG['experiment_id'], status='RUNNING', real_case_count=0,
                    started_at=datetime.now(timezone.utc).isoformat(), command=sys.argv,
                    process_running=False, sizes=[], checkpoint_sha256=args.sha256)
    try:
        config = json.loads(args.config.read_text()) if args.config else dict(DEFAULT_CONFIG)
        validate_config(config)
        write_new(args.output/'config.json', config)
        manifest.update(config_sha256=file_sha(args.output/'config.json'), source_sha256=file_sha(__file__),
                        encoder_source_sha256=file_sha(Path(__file__).with_name('encoder.py')),
                        git_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                        source_dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()))
        if file_sha(args.weights) != args.sha256:
            raise ValueError('checkpoint SHA mismatch before any inference')
        for size in config['sizes']:
            folder=args.output/('size_'+str(size))
            folder.mkdir()
            command=[sys.executable,'-m','epi_next.encoder_ctfm_mps_smoke','--child','--size',str(size),
                     '--weights',str(args.weights),'--sha256',args.sha256,'--output',str(args.output)]
            result=supervise(command,folder,config['timeout_seconds_per_size'],config['rss_limit_bytes'])
            manifest['sizes'].append(dict(size=size,**result))
            if result['status']!='PASS':
                manifest['status']=result['status']
                break
        else:
            manifest['status']='PASS'
        manifest['exit_code']=0 if manifest['status']=='PASS' else 1
    except BaseException as exc:
        manifest.update(status='FAILED',exit_code=1,exception={'type':type(exc).__name__,'message':str(exc)})
    write_new(args.output/'manifest.json',manifest)
    print(json.dumps(dict(status=manifest['status'],output=str(args.output),exit_code=manifest['exit_code'],
                          manifest_sha256=file_sha(args.output/'manifest.json'),process_running=False)))
    return manifest['exit_code']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weights',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--config',type=Path)
    parser.add_argument('--child',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--size',type=int,help=argparse.SUPPRESS)
    args=parser.parse_args()
    return run_child(args) if args.child else run_staircase(args)


if __name__=='__main__':
    raise SystemExit(main())
