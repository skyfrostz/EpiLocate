"""Run EPI-NEXT CPU-only synthetic plumbing checks, never a CT-FM smoke test."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tempfile
import time

import torch
from torch import nn

from .encoder import (FrozenEncoderAdapter, HeadConfig, FeatureCache, canonical_json,
                      class_contribution_map, ctfm_availability, fit_patient_head, sha256_bytes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('existing evidence preserved; choose a new output')
    torch.set_num_threads(1)
    started = time.perf_counter()
    root = Path(__file__).resolve().parents[3]
    config_path = Path(__file__).resolve().parents[1] / 'configs/encoder_cpu_v1.json'
    config = json.loads(config_path.read_text())
    config_hash = sha256_bytes(config_path.read_bytes())
    git_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    source_hash = sha256_bytes(Path(__file__).with_name('encoder.py').read_bytes())
    torch.manual_seed(17)
    volume = torch.linspace(-1., 1., 8 * 4 * 5 * 6).reshape(8, 1, 4, 5, 6)
    model = nn.Conv3d(1, 4, kernel_size=1)
    adapter = FrozenEncoderAdapter(model)
    features = adapter.extract(volume)
    labels = torch.tensor([0, 0, 0, 1, 1, 1, 0, 1])
    splits = ['train'] * 6 + ['observed_validation'] * 2
    patients = [f'SYNTHETIC-{n}' for n in range(8)]
    weights_bytes = b''.join(v.detach().numpy().tobytes() for _, v in sorted(model.state_dict().items()))
    hcfg = HeadConfig(**dict(config['head'], seeds=tuple(config['head']['seeds'])))
    runs = []
    for seed in hcfg.seeds:
        head, log = fit_patient_head(features.mean((2, 3, 4)), labels, patients, splits, hcfg, seed)
        logits = head(features)
        cam = class_contribution_map(features, head, 1)
        error = float((cam.mean((1, 2, 3)) + head.linear.bias[1] - logits[:, 1]).detach().abs().max())
        if error > 1e-6:
            raise AssertionError('CAM algebra failed')
        runs.append(dict(log, raw_logits=logits.detach().tolist(),
                         cam_min=float(cam.detach().min()), cam_max=float(cam.detach().max()),
                         cam_logit_max_abs_error=error))
    metadata = dict(input_sha=sha256_bytes(volume.numpy().tobytes()), model_sha=sha256_bytes(weights_bytes),
                    preprocess_sha=sha256_bytes(b'synthetic-identity-v1'), geometry_sha=sha256_bytes(b'synthetic-index-grid-no-native-CT'),
                    config_sha=config_hash, code_sha=git_sha, split="synthetic",
                    split_manifest_sha=sha256_bytes(canonical_json(dict(patients=patients, splits=splits))))
    with tempfile.TemporaryDirectory(prefix='epi-next-encoder-synthetic-') as directory:
        cache = FeatureCache(directory)
        key = cache.write(metadata, features)
        recovered = cache.read(metadata)
        cache_error = float((features - recovered).abs().max())
        cache_blob_sha = sha256_bytes((Path(directory) / (key + '.npz')).read_bytes())
        if cache_error != 0:
            raise AssertionError('cache roundtrip failed')
    result = dict(experiment_id=config['experiment_id'], evidence_type='SYNTHETIC_NUMERIC_ONLY',
                  status='PASS', git_sha=git_sha, source_sha256=source_hash, config_sha256=config_hash,
                  input_manifest_sha256=sha256_bytes(canonical_json(dict(patients=patients, splits=splits, labels=labels.tolist()))),
                  model_sha256=metadata['model_sha'], model_id='SYNTHETIC-Conv3d-1x1-NOT-CTFM',
                  feature_shape=list(features.shape), actual_encoder_calls=adapter.actual_queries,
                  environment=dict(python=platform.python_version(), torch=torch.__version__, platform=platform.platform(), device='cpu'),
                  elapsed_seconds=time.perf_counter()-started, peak_gpu_memory_bytes=None,
                  cache_key=key, cache_blob_sha256=cache_blob_sha, cache_max_abs_error=cache_error,
                  ctfm=ctfm_availability(), real_three_case_smoke='NOT RUN', real_f0='NOT RUN',
                  native_geometry='NOT RUN', clinical_metrics='NOT RUN', per_seed=runs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps(dict(status=result['status'], evidence_type=result['evidence_type'], output=str(args.output),
                          artifact_sha256=sha256_bytes(args.output.read_bytes()), actual_encoder_calls=adapter.actual_queries,
                          elapsed_seconds=result['elapsed_seconds'], cam_errors=[r['cam_logit_max_abs_error'] for r in runs])))


if __name__ == '__main__':
    main()
