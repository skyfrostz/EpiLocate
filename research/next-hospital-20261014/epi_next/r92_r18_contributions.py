"""Read-only R91 saved-feature algebra. Does not import torch or open native CT.

Slice components are model responses, never slice disease labels. The reference
is the FP64 evaluation path, not the FP32 training/slice-adapter path.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import resource
import sys
import time

import numpy as np


POLICY_PATH = Path(__file__).parents[1] / 'reports/r92_encoder/NUMERICAL_POLICY_V1.json'
POLICY_SHA = 'c72df9804d0efc340c30d17e495ec0e1df918689c9c9271439dcfbd7c6e8e30c'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def reference(path):
    path = Path(path).absolute()
    return dict(path=str(path), sha256=digest(path.read_bytes()))


def bound_bytes(ref, max_bytes=16 * 1024 * 1024):
    path = Path(ref['path'])
    if not path.is_absolute() or path.is_symlink() or path.stat().st_size > max_bytes:
        raise ValueError('absolute regular bounded artifact required')
    data = path.read_bytes()
    if digest(data) != ref['sha256']:
        raise ValueError('artifact SHA mismatch: ' + str(path))
    return data


def bound_json(ref):
    return json.loads(bound_bytes(ref))


def policy():
    return bound_json(dict(path=str(POLICY_PATH), sha256=POLICY_SHA))


def close(actual, expected, tolerance):
    actual, expected = np.asarray(actual), np.asarray(expected)
    return bool(np.isfinite(actual).all() and np.isfinite(expected).all()
                and np.all(np.abs(actual - expected) <= tolerance['atol'] + tolerance['rtol'] * np.abs(expected)))


def effective_head(state):
    shapes = {'linear.weight': (2, 512), 'linear.bias': (2,), 'mean': (512,), 'scale': (512,)}
    if set(state) != set(shapes):
        raise ValueError('four frozen head arrays required')
    for key, shape in shapes.items():
        if state[key].shape != shape or not np.isfinite(state[key]).all():
            raise ValueError('invalid head shape/finite')
    if np.any(state['scale'] < float(np.float32(1e-6))):
        raise ValueError('train scale floor required')
    w, b, mean, scale = (state[k].astype(np.float64) for k in shapes)
    a = w / scale
    return a, b - a @ mean


def decompose(features, state):
    f = np.asarray(features)
    if f.shape != (8, 512) or f.dtype != np.float32 or not np.isfinite(f).all():
        raise ValueError('finite FP32 K8 GAP512 required')
    a, beta = effective_head(state)
    raw = f.astype(np.float64) @ a.T
    weighted = raw / 8
    component = raw + beta
    gap = f.astype(np.float64).mean(0)
    direct = ((gap - state['mean'].astype(np.float64)) / state['scale'].astype(np.float64)) @ state['linear.weight'].astype(np.float64).T + state['linear.bias'].astype(np.float64)
    return dict(effective_bias=beta, raw_class_terms=raw, weighted_class_terms=weighted,
                slice_component_logits=component, slice_component_margin=component[:, 1] - component[:, 0],
                raw_margin_terms=raw[:, 1] - raw[:, 0], weighted_margin_terms=weighted[:, 1] - weighted[:, 0],
                reconstructed_logits=beta + weighted.sum(0), direct_fp64_logits=direct,
                effective_margin_bias=beta[1] - beta[0])


def fp32_roundoff_envelope(features, state):
    """Conservative first-order gamma bound for expanded FP32 affine arithmetic.

    Accounts for mean/subtract/divide/dot/add with absolute (not signed) sums.
    Inputs must be finite and normal; generated tests also cover scale-floor
    constants. This is an audit envelope, not a replacement acceptance gate.
    """
    a, beta = effective_head(state)
    u = np.finfo(np.float32).eps / 2
    gamma = (520 * u) / (1 - 520 * u)
    return gamma * (np.abs(a) @ (np.abs(features.astype(np.float64)).mean(0) + np.abs(state['mean']))
                    + np.abs(state['linear.bias']) + np.abs(beta) + 1)


def generated_validation():
    rng = np.random.default_rng(17)
    errors = []
    for scenario in ('ordinary', 'floor_constants', 'signed_cancellation'):
        f = rng.uniform(0, 3, (8, 512)).astype(np.float32)
        state = {'linear.weight': rng.normal(0, .03, (2, 512)).astype(np.float32),
                 'linear.bias': rng.normal(0, .03, 2).astype(np.float32),
                 'mean': rng.uniform(0, 3, 512).astype(np.float32),
                 'scale': rng.uniform(.2, 2, 512).astype(np.float32)}
        if scenario == 'floor_constants':
            f[:, :64] = state['mean'][:64]
            state['scale'][:64] = np.float32(1e-6)
        if scenario == 'signed_cancellation':
            state['linear.weight'][1] = -state['linear.weight'][0]
        result = decompose(f, state)
        direct32 = ((f.mean(0, dtype=np.float32) - state['mean']) / state['scale']) @ state['linear.weight'].T + state['linear.bias']
        # R91 means FP32 features in FP64; round-to-FP32 bag input is the train path.
        bag32 = f.astype(np.float64).mean(0).astype(np.float32)
        train32 = ((bag32 - state['mean']) / state['scale']) @ state['linear.weight'].T + state['linear.bias']
        err = np.abs(train32.astype(np.float64) - result['direct_fp64_logits'])
        assert close(result['reconstructed_logits'], result['direct_fp64_logits'], policy()['saved_fp64_logits'])
        assert close(train32, result['direct_fp64_logits'], policy()['generated_fp32_reference'])
        assert np.all(err <= fp32_roundoff_envelope(f, state))
        errors.append(dict(scenario=scenario, expanded_fp64_max_error=float(np.max(np.abs(result['reconstructed_logits'] - result['direct_fp64_logits']))),
                           train_fp32_max_error=float(err.max()), mean_fp32_path_max_error=float(np.max(np.abs(direct32 - result['direct_fp64_logits']))),
                           conservative_fp32_envelope=fp32_roundoff_envelope(f, state).tolist()))
    return dict(status='PASS', seed=17, scenarios=errors, policy_sha256=POLICY_SHA,
                domain='generated finite FP32 features; not an all-input numerical proof', real_reads=0)


def read_features(row):
    with np.load(io.BytesIO(bound_bytes(row['feature'])), allow_pickle=False) as archive:
        f = archive['features']
        metadata = json.loads(archive['metadata'].tobytes())
    identity = row['identity']
    content_sha = digest(canonical(dict(shape=list(f.shape), dtype=str(f.dtype))) + f.tobytes())
    if (Path(row['feature']['path']).name != digest(canonical(identity)) + '.npz'
            or metadata != dict(identity=identity, feature_sha=content_sha)
            or f.shape != (8, 512, 1, 1, 1) or f.dtype != np.float32):
        raise ValueError('cache content/key/identity mismatch')
    return f[:, :, 0, 0, 0]


def analyze(frozen_ref, generated_receipt):
    start = time.monotonic()
    frozen = bound_json(frozen_ref)
    generated = bound_json(generated_receipt)
    if generated['status'] != 'PASS' or generated['policy_sha256'] != POLICY_SHA:
        raise ValueError('pre-real generated validation required')
    cache, head, evaluation = (bound_json(frozen[k]) for k in ('cache', 'head', 'evaluation'))
    if (cache['status'] != 'PASS' or head['status'] != 'PASS' or evaluation['status'] != 'PASS'
            or cache['context'] != head['context'] or head['context'] != evaluation['context']
            or head['cache_receipt'] != frozen['cache'] or evaluation['cache_receipt'] != frozen['cache']
            or evaluation['head_checkpoint'] != frozen['head'] or head['state'] != frozen['head_state']
            or len(cache['rows']) != 60 or head['final_update'] != 100):
        raise ValueError('frozen R91 closure mismatch')
    state = {k: np.load(io.BytesIO(bound_bytes(v)), allow_pickle=False) for k, v in head['state'].items()}
    if any(v.dtype != np.float32 for v in state.values()):
        raise ValueError('saved FP32 head parameters required')
    effective_head(state)
    predictions = {r['record_id']: r for r in evaluation['predictions']}
    if len(predictions) != 60 or len({r['record_id'] for r in cache['rows']}) != 60:
        raise ValueError('unique 60 records required')
    cases, failures = [], []
    for row in cache['rows']:
        pred = predictions[row['record_id']]
        for k in ('source_group_id', 'split', 'source_diagnosis'):
            if row[k] != pred[k]:
                raise ValueError('prediction join mismatch')
        if row['task_label'] != pred['source_label']['class_id']:
            raise ValueError('bag label mismatch')
        f = read_features(row)
        gap = np.load(io.BytesIO(bound_bytes(row['gap'])), allow_pickle=False)
        geo = bound_json(row['geometry'])
        identity = row['identity']
        if (gap.shape != (1, 512) or gap.dtype != np.float64
                or not np.array_equal(gap, f.astype(np.float64).mean(0, keepdims=True))
                or geo['data_geometry_sha256'] != row['data_geometry_sha256']
                or len(geo['indices_Z']) != 8 or geo['model_shape'] != [8, 3, 224, 224]
                or identity['geometry_sha'] != row['geometry']['sha256']
                or identity['model_sha'] != cache['context']['backbone_sha256']
                or identity['code_sha'] != cache['context']['source_commit']):
            raise ValueError('GAP/geometry/model identity mismatch')
        d = decompose(f, state)
        saved = np.array(pred['raw_logits'], dtype=np.float64)
        error = np.abs(d['reconstructed_logits'] - saved)
        passed = close(d['reconstructed_logits'], saved, policy()['saved_fp64_logits']) and close(d['direct_fp64_logits'], saved, policy()['saved_fp64_logits'])
        case = dict(record_id=row['record_id'], source_group_id=row['source_group_id'], split=row['split'],
                    source_diagnosis=row['source_diagnosis'], source_label=pred['source_label'],
                    saved_raw_logits=pred['raw_logits'], saved_bag_margin=float(saved[1]-saved[0]),
                    saved_positive_probability=pred['positive_probability'], saved_predicted_class=pred['predicted_class'],
                    correct=pred['predicted_class'] == row['task_label'], expert_slice_label_availability='UNKNOWN',
                    geometry_reference=row['geometry'], geometry=geo, feature_reference=row['feature'],
                    model_version=cache['context'], head_reference=frozen['head'],
                    **{k: v.tolist() if isinstance(v, np.ndarray) else float(v) for k, v in d.items()},
                    absolute_logit_errors=error.tolist(), max_absolute_error=float(error.max()),
                    mean_absolute_error=float(error.mean()), reconstruction_status='PASS' if passed else 'FAIL',
                    margin_error=float(abs(d['effective_margin_bias'] + d['weighted_margin_terms'].sum() - (saved[1]-saved[0]))))
        cases.append(case)
        if not passed:
            failures.append(row['record_id'])
            break
    all_errors = [c for c in cases if not c['correct']]
    covid_fn = []
    for c in all_errors:
        if c['split'] == 'val_classification' and c['source_diagnosis'] == 'COVID-19':
            component = np.array(c['slice_component_margin'])
            weighted = np.array(c['weighted_margin_terms'])
            covid_fn.append(dict(record_id=c['record_id'], indices_Z=c['geometry']['indices_Z'],
                                 component_margins=component.tolist(), positive_component_count=int((component>0).sum()),
                                 positive_component_mean_contribution=float(np.maximum(component,0).sum()/8),
                                 negative_component_mean_contribution=float(np.minimum(component,0).sum()/8),
                                 raw_positive_weighted_sum=float(np.maximum(weighted,0).sum()),
                                 raw_negative_weighted_sum=float(np.minimum(weighted,0).sum()),
                                 effective_margin_bias=c['effective_margin_bias'], saved_bag_margin=c['saved_bag_margin'],
                                 saved_positive_probability=c['saved_positive_probability'], expert_infected_selected_slices='UNKNOWN',
                                 interpretation='Posthoc affine-response cancellation only; positive component is not an infected-slice prediction; no threshold search'))
    return dict(schema='R92_R18_SLICE_CONTRIBUTIONS_V1', status='PASS' if len(cases)==60 and not failures else 'FAIL',
                frozen_reference=frozen_ref, generated_validation=generated_receipt,
                numerical_policy=reference(POLICY_PATH), implementation=reference(__file__),
                prediction_scope='BAG', contribution_scope='SAVED_SLICE_GAP_AFFINE_COMPONENT', K=8,
                formulas=dict(bag='beta + sum_i weighted_class_terms[i]', component='beta + raw_class_terms[i]',
                              margin='beta[1]-beta[0] + sum_i weighted_margin_terms[i]', component_aggregation='mean_i slice_component_margin[i]'),
                cases=cases, classification_errors=[dict(record_id=c['record_id'], split=c['split'], source_diagnosis=c['source_diagnosis'],
                                                       saved_raw_logits=c['saved_raw_logits'], saved_bag_margin=c['saved_bag_margin']) for c in all_errors],
                covid_false_negative_posthoc=covid_fn, failed_reconstructions=failures,
                max_absolute_logit_error=max(c['max_absolute_error'] for c in cases),
                mean_absolute_logit_error=float(np.mean([c['mean_absolute_error'] for c in cases])),
                counts=dict(saved_feature_files_read=len(cases), saved_gap_files_read=len(cases), head_arrays_read=4,
                            geometry_files_read=len(cases), numpy_slice_vector_class_projections=8*len(cases),
                            numpy_class_scalar_dot_products=16*len(cases), numpy_fp64_bag_affine_evaluations=len(cases),
                            backbone_forward=0, torch_head_forward=0, backward=0, updates=0, native_CT_reads=0, weight_file_reads=0),
                access_basis='R92 section2 explicitly requests saved feature/head NumPy algebra; no new model phase or shared queue slot',
                elapsed_seconds=time.monotonic()-start, process_ru_maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform=='darwin' else 1024),
                clinical_patient_independence='UNKNOWN', pretraining_overlap='UNKNOWN', clinical_validity='NOT ESTABLISHED',
                spatial_maps='NOT AVAILABLE: singleton GAP placeholders', threshold=.5, threshold_tuning=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generated-only', action='store_true')
    parser.add_argument('--frozen-reference')
    parser.add_argument('--generated-receipt')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).absolute()
    if output.exists():
        raise ValueError('refusing artifact overwrite')
    result = generated_validation() if args.generated_only else analyze(reference(args.frozen_reference), reference(args.generated_receipt))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(status=result['status'], output=reference(output), torch_imported='torch' in sys.modules)))
    if result['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
