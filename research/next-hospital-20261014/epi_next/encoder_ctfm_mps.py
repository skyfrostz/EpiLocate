"""Read-only assessment of handed-off CT-FM CPU/MPS evidence; no Torch import.

Never retroactively apply a new tolerance or repeat an existing GPU experiment.
No DICOM, annotation, model, network or training access occurs in this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from .encoder_ctfm_mps_smoke import file_sha, write_new


def raw_difference(cpu, mps):
    """Compare every spatial/channel element in float64, with no acceptance gate."""
    if cpu.dtype != np.float32 or mps.dtype != np.float32:
        raise ValueError('recorded experiment requires float32 features')
    if cpu.shape != mps.shape or not cpu.size or not np.isfinite(cpu).all() or not np.isfinite(mps).all():
        raise ValueError('matching nonempty finite full output tensors required')
    error = np.abs(cpu.astype(np.float64) - mps.astype(np.float64))
    return dict(elements_compared=int(cpu.size), max_absolute_error=float(error.max()),
                mean_absolute_error=float(error.mean()), rmse=float(np.sqrt(np.mean(error**2))),
                numerical_acceptance='NOT RUN', tolerance=None,
                reason='NO_TOLERANCE_PREDECLARED_FOR_THIS_SOURCE_RUN')


def assess_run(run, expected_manifest_sha):
    """Reject corruption and unexpected scope before deriving descriptive results."""
    run = Path(run)
    if file_sha(run / 'manifest.json') != expected_manifest_sha:
        raise ValueError('source manifest SHA mismatch')
    manifest = json.loads((run / 'manifest.json').read_text())
    if manifest['real_case_count'] != 0 or [r['size'] for r in manifest['sizes']] != [32,64]:
        raise ValueError('expected exact synthetic 32/64 handoff scope')
    if file_sha(run / 'config.json') != manifest['config_sha256']:
        raise ValueError('source config SHA mismatch')
    rows = []
    hashes = {'manifest.json': expected_manifest_sha, 'config.json': manifest['config_sha256']}
    for item in manifest['sizes']:
        size = item['size']
        folder = run / f'size_{size}'
        receipt_path = folder / 'receipt.json'
        if file_sha(receipt_path) != item['receipt_sha256']:
            raise ValueError('source receipt SHA mismatch')
        receipt = json.loads(receipt_path.read_text())
        if receipt != item['receipt']:
            raise ValueError('embedded receipt differs from original')
        if receipt['status'] != 'PASS' or item['exit_code'] != 0 or item['process_running']:
            raise ValueError('source forward did not complete successfully')
        if receipt['environment']['PYTORCH_ENABLE_MPS_FALLBACK'] != '0' or receipt['fallback_enabled']:
            raise ValueError('source run was not strict MPS')
        arrays = []
        for name in ['cpu_features','mps_features']:
            path = folder / (name + '.npy')
            if file_sha(path) != receipt['output_hashes'][name]:
                raise ValueError('source output SHA mismatch')
            hashes[str(path.relative_to(run))] = file_sha(path)
            arrays.append(np.load(path, allow_pickle=False))
        expected_shape = (1,512,size//16,size//16,size//16)
        if arrays[0].shape != expected_shape or arrays[1].shape != expected_shape:
            raise ValueError('unexpected full spatial tensor shape')
        comparison = raw_difference(*arrays)
        if comparison['max_absolute_error'] != receipt['metrics']['max_abs']:
            raise ValueError('source max-error metric disagrees with original tensor')
        log = (folder / 'child.log').read_text()
        fallback_warning = 'fallback' in log.lower() or 'fall back' in log.lower()
        if fallback_warning:
            raise ValueError('source log contains fallback warning')
        hashes[str(receipt_path.relative_to(run))] = file_sha(receipt_path)
        hashes[f'size_{size}/child.log'] = file_sha(folder/'child.log')
        rows.append(dict(input_shape=receipt['input_shape'], feature_shape=list(expected_shape),
            status='PASS', scope='STRICT_FORWARD_EXECUTION_ONLY', dtype='float32',
            loading_seconds=receipt['loading_seconds'], transfer_seconds=receipt['transfer_seconds'],
            cpu_inference_seconds=receipt['cpu_seconds'], mps_inference_seconds=receipt['mps_seconds'],
            warmup_status='NOT RUN', warmup_seconds=None, timing_kind='single_cold_forward_per_device',
            readback_seconds=receipt['readback_seconds'],
            peak_process_rss_bytes=receipt['peak_process_rss_bytes'],
            parent_sampled_peak_rss_bytes=item['peak_rss_sampled_bytes'],
            mps_memory=receipt['mps_memory'], recommended_max_memory_bytes=receipt['recommended_max_memory_bytes'],
            actual_encoder_calls=receipt['actual_encoder_calls'], full_output_comparison=comparison,
            output_hashes=receipt['output_hashes'], input_sha256=receipt['input_sha256'],
            checkpoint_sha256=receipt['checkpoint_sha256'], environment=receipt['environment'],
            fallback_enabled=False, fallback_warning_detected=False,
            unsupported_operator_error=None, log_text=log, failure_reason=None,
            process_running=False, exit_code=item['exit_code']))
    return manifest, rows, hashes


def deliver(args):
    manifest, rows, hashes = assess_run(args.run, args.manifest_sha256)
    if file_sha(args.source_snapshot) != manifest['source_sha256']:
        raise ValueError('exact executed source snapshot SHA mismatch')
    # Consume the coordinator's fixed metadata only; do not create another approval
    # receipt/allowlist or read proposal membership and real-data content.
    state_bytes = args.control_state.read_bytes()
    if hashlib.sha256(state_bytes).hexdigest() != args.control_state_sha256:
        raise ValueError('coordinator state SHA mismatch')
    state = json.loads(state_bytes)
    delivery_bytes = args.data_delivery.read_bytes()
    if hashlib.sha256(delivery_bytes).hexdigest() != args.data_delivery_sha256:
        raise ValueError('DATA-EVAL delivery SHA mismatch')
    delivery = json.loads(delivery_bytes)
    counts = delivery['split_counts']
    if (delivery['case_count'] != 3 or delivery['sop_count'] != 715 or counts.get('train') != 3
            or any(n != 0 for name,n in counts.items() if name != 'train')):
        raise ValueError('DATA-EVAL delivery outside exact authorized scope')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    common = dict(evidence_type='REAL_PRETRAINED_ENCODER_SYNTHETIC_CPU_MPS',
        source_run_manifest_sha256=args.manifest_sha256,
        actual_run_source_sha256=manifest['source_sha256'],
        actual_run_encoder_source_sha256=manifest['encoder_source_sha256'],
        actual_run_source_snapshot_sha_verified=True,
        actual_run_source_snapshot_note='reconstructed by reversing three handoff diagnostic lines; exact historical SHA matched; never executed',
        actual_run_git_sha=manifest['git_sha'],
        assessment_source_sha256=file_sha(__file__),
        assessment_helper_source_sha256=file_sha(Path(__file__).with_name('encoder_ctfm_mps_smoke.py')),
        assessment_git_sha=subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(),
        original_run_argv=manifest['command'],
        original_run_worktree=str(Path.cwd()),
        original_run_command_caveat='manifest records script argv; executable/PYTHONPATH prefix supplied by handoff reproduction, not captured in original manifest',
        assessment_command=[sys.executable, '-m', 'epi_next.encoder_ctfm_mps', *sys.argv[1:]],
        coordinator_state_sha256=args.control_state_sha256, coordinator_state_revision=state['revision'],
        data_delivery_sha256=args.data_delivery_sha256, data_delivery_status=delivery['status'],
        checkpoint_sha256=manifest['checkpoint_sha256'], real_case_count=0,
        remote_rtx_3090='PAUSED', pretraining_overlap_status='unknown',
        clinical_metrics=None, original_artifact_hashes=hashes)
    write_new(args.output_dir/'MPS_COMPATIBILITY.json', dict(status='BLOCKED',
        execution_status='PASS', numerical_acceptance='NOT RUN', warmup_status='NOT RUN',
        reason='SOURCE_RUN_HAS_NO_PREDECLARED_TOLERANCE_OR_SEPARATE_WARMUP; NO_RETROACTIVE_PASS',
        executed_operators=['Conv3d_stride1','Conv3d_stride2','BatchNorm3d_eval','ReLU_inplace',
                            'residual_add_inplace','adapter_isfinite_all'],
        operator_evidence='successful exact encoder forward and reviewed source; no independent kernel profiler trace',
        mps_build_availability_check=dict(is_built=True,is_available=True,
            evidence='original successful child explicitly gates on both; exact executed source SHA verified; this assessor does not import Torch'),
        rows=rows, **common))
    write_new(args.output_dir/'RESOURCE_BENCHMARK.json', dict(status='PASS',
        scope='descriptive resource measurements for exact 32/64 synthetic staircase only',
        formal_post_compatibility_escalation='NOT RUN', trials=rows,
        tested_sizes=[32,64], sizes_above_64='NOT RUN_SCOPE_STOP',
        resource_limits=dict(rss_bytes=6*1024**3,mps_driver_bytes=6*1024**3,seconds_per_size=120),
        memory_caveat='MPS high-water sampled every 20ms; whole-child RSS includes load/CPU/MPS; unified memory figures overlap',
        performance_caveat='no separate warmup or repeat timing; cold single calls cannot establish speedup',
        patching_used=False, patch_mapping=None, patch_full_volume_equivalence='NOT ASSERTED', **common))
    write_new(args.output_dir/'THREE_CASE_SMOKE.json', dict(status='BLOCKED', run_state='NOT RUN',
        reason='ALLOWLIST_RELEASED_WAITING_FOR_DATA_EVAL_VOLUME_LEDGER_AND_INTEGRATION_SPATIAL_CONTRACT',
        authorization_source='read-only coordinator state; no independently created approval receipt',
        dicom_read=False, annotation_read=False, **common))
    write_new(args.output_dir/'F0.json', dict(status='BLOCKED', run_state='NOT RUN',
        reason='REAL_INPUT_SPATIAL_QC_TRUSTED_LABEL_DEFINITION_AND_TRAINING_SCOPE_GATES_OPEN',
        training_executed=False, checkpoint=None, patient_sampling=None,
        training_config=None, seed=None, class_prediction=None, raw_logits=None,
        spatial_coarse_candidate_map=None, model_version=None,
        expert_lesion_masks_used_as_classification_labels=False, **common))
    print(json.dumps(dict(MPS_COMPATIBILITY='BLOCKED', RESOURCE_BENCHMARK='PASS',
                         THREE_CASE_SMOKE='BLOCKED', F0='BLOCKED', new_gpu_calls=0)), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--source-snapshot', type=Path, required=True)
    parser.add_argument('--control-state', type=Path, required=True)
    parser.add_argument('--control-state-sha256', required=True)
    parser.add_argument('--data-delivery', type=Path, required=True)
    parser.add_argument('--data-delivery-sha256', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    deliver(parser.parse_args())


if __name__ == '__main__':
    main()
