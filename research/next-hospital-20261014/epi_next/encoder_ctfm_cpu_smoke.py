"""Bounded genuine CT-FM weights / synthetic input CPU test. Never a three-case G1."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def child(args):
    start = time.perf_counter()
    import torch
    import monai
    import safetensors
    from .encoder import CTFM_CONFIG, CTFM_MODEL_REVISION, load_ctfm_local, ctfm_availability
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(17)
    if digest(args.weights) != args.sha256:
        raise ValueError('checkpoint SHA256 mismatch')
    loading = time.perf_counter()
    adapter = load_ctfm_local(args.weights, args.sha256)
    model = adapter.encoder
    keys = len(model.state_dict())
    loading_seconds = time.perf_counter() - loading
    # 32 is divisible by encoder stride 16; this is a synthetic index grid,
    # not reoriented/resampled native DICOM or a resource estimate for full CT.
    x = torch.linspace(0, 1, 32 ** 3).reshape(1, 1, 32, 32, 32)
    infer = time.perf_counter()
    features = adapter.extract(x)
    inference_seconds = time.perf_counter() - infer
    assert torch.isfinite(features).all()
    pooled = features.mean((2, 3, 4))
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes = int(peak if sys.platform == 'darwin' else peak * 1024)
    output = dict(experiment_id='EPI-NEXT-CTFM-CPU-ADAPTER-SYNTHETIC-v2', status='PASS',
        evidence_type='REAL_PRETRAINED_ENCODER_SYNTHETIC_INPUT', checkpoint_sha256=args.sha256,
        model_revision=CTFM_MODEL_REVISION, config=CTFM_CONFIG,
        config_sha256=hashlib.sha256(json.dumps(CTFM_CONFIG, sort_keys=True).encode()).hexdigest(),
        git_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        source_sha256=digest(__file__), encoder_source_sha256=digest(Path(__file__).with_name('encoder.py')), input_shape=list(x.shape), feature_shape=list(features.shape),
        pooled_shape=list(pooled.shape), input_sha256=hashlib.sha256(x.numpy().tobytes()).hexdigest(),
        feature_sha256=hashlib.sha256(features.numpy().tobytes()).hexdigest(),
        feature_min=float(features.min()), feature_max=float(features.max()),
        pooled_values=pooled.tolist(), parameter_count=sum(p.numel() for p in model.parameters()),
        strict_load=True, missing_keys=[], unexpected_keys=[],
        adapter_runtime=ctfm_availability()['runtime_path'],
        float_buffer_numel=sum(b.numel() for b in model.buffers() if b.is_floating_point()),
        integer_buffer_numel=sum(b.numel() for b in model.buffers() if not b.is_floating_point()),
        state_tensor_count=keys, actual_encoder_calls=adapter.actual_queries,
        loading_seconds=loading_seconds, inference_seconds=inference_seconds,
        total_child_seconds=time.perf_counter()-start, peak_process_rss_bytes=peak_bytes,
        memory_measurement='resource.RUSAGE_SELF.ru_maxrss; whole child process, not isolated inference increment',
        peak_gpu_memory_bytes=None, device='cpu', threads=1,
        environment=dict(python=platform.python_version(), torch=torch.__version__, monai=monai.__version__,
                         safetensors=safetensors.__version__, platform=platform.platform()),
        real_three_case_g1='NOT RUN', native_geometry_qc='NOT RUN', clinical_metrics='NOT RUN',
        pretraining_overlap_status='unknown', head_training='NOT RUN')
    with args.output.open('x') as f:
        json.dump(output, f, indent=2, allow_nan=False)
        f.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weights', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        child(args)
        return
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-m', 'epi_next.encoder_ctfm_cpu_smoke', '--child',
               '--weights', str(args.weights), '--sha256', args.sha256, '--output', str(args.output)]
    start = time.monotonic()
    log_path = args.output.with_suffix('.log')
    outcome = 'FAILED'
    with log_path.open('x') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1'))
        while process.poll() is None:
            if time.monotonic() - start > 60:
                outcome = 'TIMEOUT'
                process.kill()  # only this known child
                break
            rss = subprocess.run(['ps', '-o', 'rss=', '-p', str(process.pid)], text=True, capture_output=True).stdout.strip()
            if rss and int(rss) * 1024 > 3 * 1024 ** 3:
                outcome = 'MEMORY_BUDGET'
                process.kill()
                break
            time.sleep(.2)
        code = process.wait()
    if code != 0:
        if not args.output.exists():
            args.output.write_text(json.dumps(dict(status=outcome, exit_code=code, real_three_case_g1='NOT RUN',
                                                  clinical_metrics='NOT RUN', elapsed_seconds=time.monotonic()-start), indent=2)+'\n')
        raise SystemExit(1)
    print(json.dumps(dict(status='PASS', output=str(args.output), artifact_sha256=digest(args.output),
                          exit_code=code, subprocess_ended=True)))


if __name__ == '__main__':
    main()
