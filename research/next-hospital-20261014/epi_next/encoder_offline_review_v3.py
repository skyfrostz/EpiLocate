"""Offline CT-FM shape algebra and case-level feature/head design oracles.

No Torch import, checkpoint loader, training, patient pixel reader or GPU API.
Tensor/storage/MAC counts are SPEC estimates, never measured activation peaks.
"""
from __future__ import annotations
import ast
import argparse
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
import numpy as np


def source_config(text):
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'CTFM_CONFIG' for t in node.targets):
            if not isinstance(node.value, ast.Call) or not isinstance(node.value.func, ast.Name) or node.value.func.id != 'dict':
                raise ValueError('literal CTFM dict config required')
            return {k.arg: ast.literal_eval(k.value) for k in node.value.keywords}
    raise ValueError('CTFM_CONFIG absent')


def symbolic_profile(config, side):
    """Static isotropic k3/p1 encoder specification; backend workspace unknown."""
    if config != dict(blocks_down=[1, 2, 2, 4, 4], in_channels=1, init_filters=32, spatial_dims=3):
        raise ValueError('architecture requires separate symbolic review')
    if type(side) is not int or side < 16 or side % 16:
        raise ValueError('positive16-aligned isotropic cube required')
    bytes_per_float, kernel_volume = 4, 27
    convs = []; stages = []; params = buffers = 0; receptive = jump = 1

    def conv(name, cin, cout, spatial, stride):
        nonlocal params, receptive, jump
        weights = cin*cout*kernel_volume
        params += weights
        receptive += 2*jump; jump *= stride
        convs.append(dict(name=name, input_channels=cin, output_channels=cout,
                          output_side=spatial, stride=stride, output_fp32_bytes=cout*spatial**3*4,
                          weights_fp32_bytes=weights*4, multiply_accumulate_operations=weights*spatial**3,
                          conditional_full_im2col_fp32_bytes=cin*kernel_volume*spatial**3*4))

    channels = config['init_filters']; spatial = side
    conv('conv_init', 1, channels, spatial, 1)
    for level, blocks in enumerate(config['blocks_down']):
        for block in range(blocks):
            conv(f'level{level}.block{block}.conv1', channels, channels, spatial, 1)
            conv(f'level{level}.block{block}.conv2', channels, channels, spatial, 1)
            params += 4*channels  # two BatchNorms, each weight+bias
            buffers += 4*channels  # two BatchNorms, each running mean+variance
        stages.append(dict(stage=level, blocks=blocks, shape=[1, channels, spatial, spatial, spatial],
                           fp32_bytes=channels*spatial**3*bytes_per_float))
        if level < len(config['blocks_down'])-1:
            conv(f'level{level}.downsample', channels, 2*channels, spatial//2, 2)
            channels *= 2; spatial //= 2
    retained = sum(s['fp32_bytes'] for s in stages)
    return dict(evidence_kind='SPEC_STATIC_ALGEBRA_NOT_RUNTIME_PROFILE', input_shape=[1, 1, side, side, side],
                input_fp32_bytes=side**3*4, final_feature_shape=stages[-1]['shape'], stages=stages,
                conv_count=len(convs), convs=convs, parameter_elements=params,
                running_float_buffer_elements=buffers, batch_counter_int64_elements=26,
                resident_state_fp32_bytes=(params+buffers)*4, batch_counter_int64_bytes=26*8,
                retained_stage_outputs_fp32_bytes=retained,
                first_residual_three_distinct_tensors_illustration_bytes=3*stages[0]['fp32_bytes'],
                named_tensor_accounting_input_state_and_retained_outputs_bytes=side**3*4+(params+buffers)*4+retained+26*8,
                conditional_max_full_im2col_fp32_bytes=max(c['conditional_full_im2col_fp32_bytes'] for c in convs),
                total_convolution_multiply_accumulate_operations=sum(c['multiply_accumulate_operations'] for c in convs),
                lattice=dict(nominal_receptive_field_voxels=receptive, stride=jump, center_offset=0),
                assumptions=['FP32 batch1, isotropic k3/p1, residual stride1, four stride2 downsamplers',
                             'BatchNorm state shape count; actual execution can fuse/reuse allocations',
                             'MONAI retains all stage outputs; named tensors exclude interpreter/library/allocator/workspace',
                             'full im2col is a conditional illustrative backend, not identified actual CPU kernel'],
                measured_activation_peak_bytes=None, actual_cpu_backend=None)


def downsample_generated_control(value):
    """2x cell-average reference; use generated normalized volumes in this round."""
    value = np.asarray(value)
    if value.ndim != 5 or value.shape[:2] != (1, 1) or value.dtype != np.float32:
        raise ValueError('one FP32 single-channel cube required')
    if len(set(value.shape[-3:])) != 1 or value.shape[-1] % 2 or not np.isfinite(value).all():
        raise ValueError('finite even cube required')
    if value.min() < 0 or value.max() > 1:
        raise ValueError('already normalized input required; do not repeat HU normalization')
    n = value.shape[-1]//2
    # FP64 accumulation; only final normalized output rounds to FP32.
    return value.reshape(1, 1, n, 2, n, 2, n, 2).mean(axis=(3, 5, 7), dtype=np.float64).astype(np.float32)


def compose_half_voxel(parent_model_to_native, ratio):
    parent = np.asarray(parent_model_to_native, dtype=np.float64)
    ratio = np.asarray(ratio, dtype=np.float64)
    if (parent.shape != (4, 4) or ratio.shape != (3,) or not np.isfinite(parent).all()
            or not np.isfinite(ratio).all() or np.any(ratio <= 0)
            or not np.allclose(parent[3], [0, 0, 0, 1])):
        raise ValueError('finite affine and positive3D ratio required')
    child_to_parent = np.eye(4); child_to_parent[:3, :3] = np.diag(ratio)
    child_to_parent[:3, 3] = .5*ratio-.5
    return parent @ child_to_parent


def case_gap_oracle(features, *, field_of_view, aggregation_version='whole-series-gap-v1'):
    """Equal feature-cell GAP, matching existing CaseLinearHead; no patch stitching."""
    features = np.asarray(features)
    if (features.ndim != 5 or features.shape[0] != 1 or features.dtype != np.float32
            or not np.isfinite(features).all() or any(n < 1 for n in features.shape)):
        raise ValueError('one finite FP32 spatial feature cube required')
    if field_of_view != 'FULL_APPROVED_SELECTED_SERIES' or aggregation_version != 'whole-series-gap-v1':
        raise ValueError('partial patch or alternate weighting cannot masquerade as whole-Series GAP')
    return features.mean(axis=(2, 3, 4), dtype=np.float64)


def linear_head_oracle(features, mean, scale, weight, bias):
    """Analytic test-only logits/CAM; supplied generated coefficients are not a fitted head."""
    pooled = case_gap_oracle(features, field_of_view='FULL_APPROVED_SELECTED_SERIES')
    mean, scale, weight, bias = [np.asarray(x, dtype=np.float64) for x in (mean, scale, weight, bias)]
    channels = features.shape[1]
    if (mean.shape != (channels,) or scale.shape != (channels,) or weight.ndim != 2
            or weight.shape[1] != channels or bias.shape != (weight.shape[0],)
            or weight.shape[0] < 2 or not all(np.isfinite(x).all() for x in (mean, scale, weight, bias))
            or np.any(scale <= 0)):
        raise ValueError('finite matching analytic head coefficients required')
    logits = ((pooled-mean)/scale) @ weight.T + bias
    spatial = (features.astype(np.float64)-mean[None, :, None, None, None])/scale[None, :, None, None, None]
    cam = np.einsum('ncxyz,kc->nkxyz', spatial, weight)
    return dict(logits=logits, class_prediction=np.argmax(logits, axis=1), signed_contribution=cam,
                reconstructed_logits=cam.mean(axis=(2, 3, 4))+bias,
                clinical_label_or_fitted_head=False)


def patient_manifest_guard(rows):
    """Future train design boundary only; never reads labels or trains a model."""
    ids = [r['patient_key'] for r in rows]
    if len(ids) != len(set(ids)) or any(not p for p in ids):
        raise ValueError('one selected Study/Series vector per patient; explicit resolution needed for duplicates')
    if any(r['split'] not in ('train', 'observed_validation') for r in rows):
        raise ValueError('sealed/test/unknown split forbidden')
    if any(r['label_status'] != 'VERIFIED' or r['label_source'] not in ('EXPERT_STUDY', 'ADJUDICATED_STUDY')
           or r['label'] not in (0, 1) for r in rows):
        raise ValueError('verified independent case-level labels required; no Mask/proxy labels')
    classes = {r['label'] for r in rows if r['split'] == 'train'}
    if classes != {0, 1}:
        raise ValueError('both prospectively defined train classes required; engineering sample is insufficient')
    return dict(status='DESIGN_SCHEMA_PASS_NOT_TRAINING_AUTHORIZATION', patients=len(rows), train_classes=sorted(classes))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('encoder-source', 'monai-source', 'receipt', 'calls', 'data-qa', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args(); started = time.monotonic()
    def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
    if sha(args.receipt) != '0000000000000000000000000000000000000000000000000000000000000000':
        raise ValueError('immutable Wave1 receipt changed')
    if sha(args.data_qa) != '0000000000000000000000000000000000000000000000000000000000000000':
        raise ValueError('DATA input QA changed')
    config = source_config(args.encoder_source.read_text())
    source = args.monai_source.read_text(); tree = ast.parse(source)
    encoder = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SegResEncoder')
    init = next(n for n in encoder.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
    defaults = dict(zip([n.arg for n in init.args.args][-len(init.args.defaults):], init.args.defaults))
    if ast.literal_eval(defaults['norm']) != 'batch' or ast.literal_eval(defaults['anisotropic_scales']) is not None:
        raise ValueError('static architecture assumptions changed')
    forward = next(n for n in encoder.body if isinstance(n, ast.FunctionDef) and n.name == '_forward')
    retained = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                   and isinstance(n.func.value, ast.Name) and n.func.value.id == 'outputs'
                   and n.func.attr == 'append' for n in ast.walk(forward))
    if not retained: raise ValueError('stage retention source changed')
    receipt = json.loads(args.receipt.read_bytes())
    calls = [json.loads(line) for line in args.calls.read_text().splitlines()]
    entered = [e for e in calls if e['event'] == 'NETWORK_ENTERED']
    returned = [e for e in calls if e['event'] == 'NETWORK_RETURNED']
    qa = json.loads(args.data_qa.read_bytes())
    measured = dict(evidence_kind='RESULT_PERSISTED_OBSERVATIONS_NOT_NEW_MODEL_EXECUTION',
                    cpu_entered=sum(e['device'] == 'cpu' for e in entered),
                    mps_entered=sum(e['device'] == 'mps' for e in entered), completed=len(returned),
                    reserved_forward=receipt['counters']['forward'], stop_reason=receipt['reason'],
                    rss_sampled_peak_bytes=max(s['rss_bytes'] for s in receipt['samples']),
                    driver_sampled_peak_bytes=max(s.get('mps_driver_bytes', 0) for s in receipt['samples']),
                    swap_first_sample_bytes=receipt['samples'][0]['swap_used_bytes'],
                    swap_peak_sample_bytes=max(s['swap_used_bytes'] for s in receipt['samples']),
                    trigger_after_start_seconds=receipt['trigger_monotonic']-receipt['started_monotonic'],
                    exit_after_start_seconds=receipt['exit_monotonic']-receipt['started_monotonic'],
                    slot_completed=receipt['slot_completed'], device_recovery='UNKNOWN',
                    cpu_backend='UNKNOWN', inference_seconds=None,
                    causal_limit='whole-machine swap increase; CPU entry coincided, exclusive causal attribution not established')
    if (measured['cpu_entered'], measured['mps_entered'], measured['completed']) != (1, 0, 0):
        raise ValueError('Wave1 observed counts contradict expected source')
    output = dict(schema='CTFM_OFFLINE_RESOURCE_AND_DESIGN_REVIEW_V3', status='PASS_OFFLINE_REVIEW',
                  source_config=config, source_stage_retention=retained,
                  source_evidence=dict(encoder_class_lines=[encoder.lineno, encoder.end_lineno],
                                       forward_lines=[forward.lineno, forward.end_lineno]),
                  consumed_sha256={name: sha(getattr(args, name)) for name in
                                   ('encoder_source', 'monai_source', 'receipt', 'calls', 'data_qa')},
                  analysis_source_sha256=sha(Path(__file__)), measured=measured,
                  estimates={str(n): symbolic_profile(config, n) for n in (64, 128)},
                  input_QA=dict(status=qa['input_QA_status'], source_frozen_manifest_sha256=qa['source_frozen_manifest_sha256'],
                                cases=[{k: c[k] for k in ('case_index', 'status', 'input_sha256', 'ledger_sha256',
                                                        'native_edge_roundtrip_max_error', 'max_probe_error')}
                                       for c in qa['cases']], scientific_smoke_pass=False),
                  new_real_model_calls=0, checkpoint_bytes_read=False, patient_pixels_read=False,
                  Torch_imported='torch' in sys.modules, wall_seconds=time.monotonic()-started,
                  offline_process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  command=[sys.executable, *sys.argv])
    if output['Torch_imported']: raise ValueError('offline review must not import Torch')
    with args.output.open('x') as stream:
        stream.write(json.dumps(output, indent=2, sort_keys=True, allow_nan=False)+'\n')
    print(json.dumps(dict(status=output['status'], output_sha256=sha(args.output),
                         offline_wall_seconds=output['wall_seconds'], new_real_model_calls=0)))
    return 0


if __name__ == '__main__': raise SystemExit(main())
