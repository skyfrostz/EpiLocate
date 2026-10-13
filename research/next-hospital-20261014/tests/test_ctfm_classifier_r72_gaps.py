"""R72 missing checks only. Historical generated assets; no CT-FM or training."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest
import torch

from epi_next import ctfm_research_pipeline_v4 as p
from epi_next.ctfm_research_math_v4 import binary_metrics, probability
from epi_next.encoder import CaseLinearHead, fit_patient_head


@pytest.fixture(scope='module')
def historical_generated():
    torch.set_num_threads(1)
    evidence = Path(__file__).parents[1]/'reports/ctfm_research_v4/GENERATED_VALIDATION_V4.json'
    original = json.loads(evidence.read_bytes())
    assert original['status'] == 'PASS' and original['medical_CT_FM_calls'] == 0
    receipts = {name: p.bound_json(ref) for name, ref in original['raw_receipts'].items()}
    assert receipts['cache']['evidence_type'] == 'GENERATED_BACKEND_NO_CT_FM'
    root = Path(original['raw_receipts']['cache']['path']).parent.parent
    rows = p.bound_json(dict(path=str(root/'GENERATED_DATA_CONSUMER.json'),
                            sha256=receipts['cache']['data_manifest_sha256']))
    assert all(row['record_id'].startswith('SYN_') for row in rows)
    return receipts, rows


def test_saved_update_delta_and_train_only_statistics(historical_generated):
    receipts, rows = historical_generated
    saved = {}
    for name, ref in receipts['head']['state'].items():
        assert p.file_sha(ref['path']) == ref['sha256']
        saved[name] = np.load(ref['path'], allow_pickle=False)
    gap = []
    for row in receipts['cache']['rows']:
        assert p.file_sha(row['gap']['path']) == row['gap']['sha256']
        gap.append(np.load(row['gap']['path'], allow_pickle=False)[0])
    x = torch.from_numpy(np.stack(gap)).float()
    train = torch.tensor([row['split'] == 'train_weak' for row in rows])
    np.testing.assert_array_equal(saved['mean'], x[train].mean(0).numpy())
    np.testing.assert_array_equal(saved['scale'], x[train].std(0, unbiased=False).clamp_min(1e-6).numpy())
    assert not np.array_equal(saved['mean'], x.mean(0).numpy())
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(17)
        initial = CaseLinearHead(512, 2)
    for name in ('linear.weight', 'linear.bias'):
        delta = np.abs(saved[name] - initial.state_dict()[name].numpy())
        assert np.isfinite(delta).all() and delta.max() > 0
        print(f'{name} saved_vs_initial_maxabs={float(delta.max())!r}')
    print('train_only_statistics_exact=True; no forward/backward/update executed')


def test_probability_extreme_logits_and_rejections():
    logits = np.array([[0., 0.], [1000., -1000.], [-1000., 1000.], [1000., 1001.]])
    expected = [0.5, 0., 1., 1/(1+np.exp(-1))]
    np.testing.assert_allclose(probability(logits), expected, atol=1e-15, rtol=0)
    np.testing.assert_allclose(probability(logits + 10000), expected, atol=1e-15, rtol=0)
    for bad in (np.zeros(2), np.zeros((2, 3)), [[0, np.nan]], [[0, np.inf]]):
        with pytest.raises(ValueError):
            probability(bad)
    print(f'extreme_positive_probabilities={probability(logits).tolist()}')


def test_nontrivial_auc_ap_tied_ranking():
    y, score = [1, 0, 1, 0], [.9, .8, .8, .1]
    metric = binary_metrics(y, score)
    # Pairwise positive-negative wins: 3.5/4; tied threshold AP: 1/2 + (1/2)*(2/3).
    assert metric['AUROC'] == 7/8
    assert metric['AUPRC_average_precision'] == pytest.approx(5/6, abs=1e-15)
    for order in ([3, 2, 1, 0], [2, 0, 3, 1]):
        permuted = binary_metrics(np.array(y)[order], np.array(score)[order])
        assert permuted == metric
    print(f"nontrivial_AUROC={metric['AUROC']!r}; AP={metric['AUPRC_average_precision']!r}")


def test_invalid_metric_inputs_rejected():
    for y, score in (([], []), ([0, 2], [.1, .9]), ([0, -1], [.1, .9]),
                     ([0, np.nan], [.1, .9]), ([0, 'bad'], [.1, .9]),
                     ([0, 1], [.1]), ([0, 1], [-.1, .9]),
                     ([0, 1], [.1, 1.1]), ([0, 1], [.1, np.nan])):
        with pytest.raises(ValueError):
            binary_metrics(y, score)
    with pytest.raises(ValueError, match='PREDICTION_SHAPE'):
        binary_metrics([0, 1], [.1, .9], [True])


def test_additional_group_label_and_single_class_guards(historical_generated):
    _, rows = historical_generated
    # Within-split duplicates differ from the already tested cross-split group collision.
    bad = copy.deepcopy(rows)
    bad[1]['source_group_id'] = bad[0]['source_group_id']
    with pytest.raises(p.Blocked, match='SOURCE_GROUP'):
        p.validate_records(bad)
    bad = copy.deepcopy(rows)
    bad[1]['tensor_artifact']['sha256'] = bad[0]['tensor_artifact']['sha256']
    with pytest.raises(p.Blocked, match='DUPLICATE_NATIVE_TENSOR'):
        p.validate_records(bad)
    for label in (-1, 2, 1.0, '1', None, float('nan')):
        bad = copy.deepcopy(rows)
        bad[0]['task_label'] = label
        with pytest.raises(p.Blocked, match='LABEL_OR_SPLIT'):
            p.validate_records(bad)
    bad = copy.deepcopy(rows)
    for row in bad:
        row['task_label'] = 0
        row['source_diagnosis'] = 'Normal'
    with pytest.raises(p.Blocked, match='FIXED_SOURCE_CATEGORY_COUNTS'):
        p.validate_records(bad)
    # Legacy reused fitter must fail before optimizer construction for missing classes.
    with pytest.raises(ValueError, match='each declared class'):
        fit_patient_head(torch.zeros(2, 512), torch.zeros(2, dtype=torch.long),
                         ['SYN_A', 'SYN_B'], ['train', 'train'])


def test_corrupt_checkpoint_rejected_before_head_forward(historical_generated, monkeypatch, tmp_path):
    receipts, rows = historical_generated
    head = copy.deepcopy(receipts['head'])
    corrupt = tmp_path/'corrupt_weight.npy'
    np.save(corrupt, np.zeros((2, 512), np.float32), allow_pickle=False)
    head['state']['linear.weight']['path'] = str(corrupt)
    # SHA remains the original saved asset: intentionally corrupt, generated only.
    monkeypatch.setattr(p, 'read_cache', lambda *args: (None, None, None))
    meter = p.Meter('evaluate')
    with pytest.raises(p.Blocked, match='HEAD_ASSET_SHA'):
        p.evaluate_phase(rows, receipts['cache'], head, head['data_manifest_sha256'],
                         head['cache_receipt_sha256'], 'a'*64, tmp_path/'out', meter)
    assert (meter.forward, meter.backward, meter.returned_updates) == (0, 0, 0)
    assert not (tmp_path/'out').exists()
