"""Saved P1 CPF evaluation through the existing partial-reference protocol."""
import argparse
import base64
import io
import json
from pathlib import Path

import numpy as np
import pydicom
from PIL import Image

from .data_delivery import read_bound
from .evaluation_protocol import BUDGETS, evaluate_variant, fixed_slice_binding
from .first_real_evaluation import native_cell_lookup
from .gt_vnext import sha256
from .ref_support_qa import patch_support, native_support

INDEX_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
TEMPLATE_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
PREPARED_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
MVP_LEDGER_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
SCALE = 'single-scale-7x7-CPF-peak-patch'


def bilinear_half_pixel(coarse, size=224):
    """NumPy display reconstruction, not a model call or new candidate rule."""
    coarse = np.asarray(coarse, dtype=np.float64)
    h, w = coarse.shape
    y = (np.arange(size) + .5) * h / size - .5
    x = (np.arange(size) + .5) * w / size - .5
    y0, x0 = np.floor(y).astype(int), np.floor(x).astype(int)
    fy, fx = y - y0, x - x0
    a, b = np.clip(y0, 0, h - 1), np.clip(y0 + 1, 0, h - 1)
    c, d = np.clip(x0, 0, w - 1), np.clip(x0 + 1, 0, w - 1)
    rows = coarse[a] * (1 - fy[:, None]) + coarse[b] * fy[:, None]
    return rows[:, c] * (1 - fx[None, :]) + rows[:, d] * fx[None, :]


def edge(mask):
    inside = mask.copy()
    inside[1:] &= mask[:-1]
    inside[:-1] &= mask[1:]
    inside[:, 1:] &= mask[:, :-1]
    inside[:, :-1] &= mask[:, 1:]
    inside[[0, -1], :] = False
    inside[:, [0, -1]] = False
    return mask & ~inside


def png(path, image):
    buffer = io.BytesIO()
    Image.fromarray(image).save(buffer, format='PNG')
    raw = buffer.getvalue()
    with path.open('xb') as f:
        f.write(raw)
    return {'path': str(path), 'sha256': sha256(path), 'bytes': len(raw)}, raw


def evaluate(index_path, root, out):
    index = read_bound(index_path, INDEX_SHA)
    assert [r['case_index'] for r in index['cases']] == [1, 2, 3]
    assert index['actual_candidate_regions_by_case'] == {'1': 0, '2': 0, '3': 1}
    run = read_bound(index['run_delivery']['path'], index['run_delivery']['sha256'])
    assert run['status'] == 'SUCCESS' and run['reason'] is None
    assert run['cost']['forward_entered'] == 27018 and run['cost']['reverse_entered'] == 27000
    exit_record = read_bound(index['actual_exit']['path'], index['actual_exit']['sha256'])
    assert exit_record['exit_code'] == 0
    review = read_bound(index['saved_review']['path'], index['saved_review']['sha256'])
    assert review['terminal_denominators'] == index['complete_denominators']
    supervisor = read_bound(index['supervisor_receipt']['path'], index['supervisor_receipt']['sha256'])
    assert supervisor['status'] == 'SUCCESS' and supervisor['slot_completed'] is True
    readiness = read_bound(index['readiness']['path'], index['readiness']['sha256'])
    prepared = read_bound(readiness['prepared_delivery']['path'], PREPARED_SHA)
    # Read source only to bind display interpolation semantics, never import LOC.
    core = next(p for p in readiness['local_source_bindings'] if p.endswith('/hspi_core_v3.py'))
    assert sha256(core) == readiness['local_source_bindings'][core]
    core_text = Path(core).read_text()
    assert "soft = upsample(omega*mask, config.image_size, 'bilinear', config.align_corners)" in core_text
    assert 'align_corners: bool = False' in core_text
    template = read_bound(root / '.local/phase2/evaluation_fixed_slice_request_template_v1.json', TEMPLATE_SHA)
    lock = read_bound(template['fixed_slice_lock_path'], template['fixed_slice_lock_sha256'])
    gtp = Path(template['gt_manifest_path'])
    gt = read_bound(gtp, template['gt_manifest_sha256'])
    mvp = read_bound(root / '.local/phase2/mvp-three-sop-derivatives-v1-20261011/MVP_THREE_SOP_DERIVATIVE_LEDGER_V1.json', MVP_LEDGER_SHA)
    out.mkdir(mode=0o700, exist_ok=False)
    results, sections, assets = [], [], []
    lookup = native_cell_lookup()
    for row in index['cases']:
        i = row['case_index']
        p = next(r for r in prepared['records'] if r['case_index'] == i)
        assert row['prepared_record'] == p
        selected = next(r for r in lock['slices'] if r['case_index'] == i)
        case_ref = next(r for r in gt['cases'] if r['patient_id'] == selected['patient_id'])
        case = read_bound(gtp.parent / case_ref['manifest_path'], case_ref['manifest_sha256'])
        k, sop = fixed_slice_binding(lock, selected['patient_id'], case, case_ref['manifest_sha256'])
        assert p['source_sop_uid'] == sop and p['native_slice_index_zero_based'] == k
        assert p['native_manifest_sha256'] == case_ref['manifest_sha256']
        entry = next(r for r in template['case_inputs'] if r['patient_id'] == selected['patient_id'])
        assert sha256(entry['support_path']) == entry['support_sha256']
        support = np.load(entry['support_path'], allow_pickle=False)
        assert support.shape == (512, 512) and support.dtype == bool and support.all()
        result = read_bound(row['result']['path'], row['result']['sha256'])
        assert result['status'] == row['status'] and result['observed_iterations'] == 10000
        assert result['feasible_count'] == row['conditions']['joint_pass']
        candidate = row['candidate']
        assert sha256(candidate['path']) == candidate['sha256']
        with np.load(candidate['path'], allow_pickle=False) as array:
            assert str(array['native_case_manifest_sha256'].item()) == case_ref['manifest_sha256']
            assert str(array['SOPInstanceUID'].item()) == sop and int(array['native_slice_index'].item()) == k
            scores, reliable = array['scores'].copy(), array['reliable'].copy()
        assert scores.shape == reliable.shape == (512, 512) and reliable.dtype == bool
        assert np.isfinite(scores).all()
        expected = np.zeros((512, 512), bool)
        soft_native = None
        mask_evidence = {'status': 'NO_SELECTED_FEASIBLE_MASK', 'not_candidate_region': True}
        if row['selected'] is None:
            assert row['status'] == 'NO_FEASIBLE_MASK' and result['best'] is None
            assert not reliable.any() and not scores.any()
        else:
            s = row['selected']
            best = result['best']
            assert best['epoch'] == s['epoch'] == 3604
            for key in ('ls', 'lm', 'gap', 'mask'):
                assert best[key] == s[key]
            coarse = np.asarray(s['mask'], dtype=np.float32).reshape(7, 7)
            assert np.isfinite(coarse).all() and np.min(coarse) >= 0 and np.max(coarse) <= 1
            assert int(coarse.argmax()) == s['cell_flat'] == 43
            assert abs(float(np.abs(coarse).mean()) - s['lm']) < 1e-7
            top = np.sort(coarse.ravel())[-2:]
            assert float(top[1] - top[0]) == s['gap']
            model = patch_support((224, 224), (7, 7), (s['coarse_row'], s['coarse_column']))
            expected = native_support(model, (512, 512))
            assert expected.sum() == candidate['reliable_pixels'] == 5329
            ys, xs = np.where(expected)
            assert [int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1] == [439, 512, 73, 146]
            assert np.all(scores[expected] == s['gap']) and not scores[~expected].any()
            # Entire continuous mask remains a separate display-only asset.
            mask_path = out / f'case-{i}-selected-coarse-continuous-mask.npy'
            with mask_path.open('xb') as f:
                np.save(f, coarse, allow_pickle=False)
            soft_native = bilinear_half_pixel(coarse)[np.ix_(lookup, lookup)]
            native_mask_path = out / f'case-{i}-display-continuous-mask-native.npy'
            with native_mask_path.open('xb') as f:
                np.save(f, soft_native, allow_pickle=False)
            mask_evidence = {'status': 'SELECTED_CONTINUOUS_MASK_DISPLAY_ONLY',
                             'coarse_path': str(mask_path), 'coarse_sha256': sha256(mask_path),
                             'native_display_path': str(native_mask_path), 'native_display_sha256': sha256(native_mask_path),
                             'epoch': s['epoch'], 'coarse_mean_Lm': s['lm'], 'not_area_or_coverage': True,
                             'mapping': 'NumPy halfpixel bilinear7->224 border clamp, then existing nearest halfpixel224->512 inverse; no Torch numerical replay',
                             'not_candidate_region': True, 'thresholded': False, 'evaluated_as_binary_candidate': False}
        assert np.array_equal(reliable, expected)
        objects, mask_bindings = [], []
        key = tuple(entry['reference_key'])
        reference = np.zeros((512, 512), bool)
        for obj in case['annotations']:
            category = (obj['raw_label']['name'], obj['raw_annotation'].get('createdById'),
                        obj['raw_label']['label_group_id'], obj['raw_annotation']['labelId'])
            if obj['status'] != 'PASS' or obj['identity']['SOPInstanceUID'] != sop or category != key:
                continue
            path = gtp.parent / obj['mask_path']
            assert sha256(path) == obj['mask_sha256']
            with Image.open(path) as image:
                mask = np.asarray(image, bool)
            objects.append({'annotation_id': obj['annotation_id'], 'reference_key': key, 'mask': mask})
            reference |= mask
            mask_bindings.append({'annotation_id': obj['annotation_id'], 'path': str(path), 'sha256': obj['mask_sha256']})
        measured = evaluate_variant({SCALE: {'scores': scores, 'reliable': reliable}}, objects,
                                    support, key, spacing_krc_mm=case['geometry']['spacing_krc_mm'])
        for fraction in BUDGETS:
            metric = measured['budgets'][str(fraction)]['scales'][SCALE]
            assert metric['candidate_voxels'] == int(reliable.sum())
            metric['annotation_units_missed'] = metric['annotation_units_evaluable'] - metric['annotation_units_hit']
            metric['candidate_outside_observed_reference_pixels_uncertain'] = int((reliable & ~reference).sum())
            assert metric['dice'] is None and metric['false_positive_voxels'] is None
        results.append({'case_index': i, 'algorithm_status': row['status'],
                        'native_slice_index': k, 'candidate_regions': int(reliable.any()),
                        'observed_iterations': 10000, 'computational_failure': False,
                        'reference_status': 'OBSERVED_PARTIAL_REFERENCE' if objects else 'NO_APPLICABLE_POLYGON_UNKNOWN',
                        'reference_key': list(key), 'reference_objects': mask_bindings,
                        'continuous_mask': mask_evidence, 'mapping_qa': 'EXACT_NATIVE_PATCH_AND_SOP_BINDING_PASS',
                        'cross_scale_status': 'NOT_APPLICABLE_SINGLE_SCALE', **measured})
        image_record = next(r for r in mvp['records'] if r['case_index'] == i)
        assert image_record['source_ct_sha256'] == p['source_ct_sha256']
        assert sha256(image_record['path']) == image_record['sha256']
        ds = pydicom.dcmread(image_record['path'])
        assert str(ds.SOPInstanceUID) == sop
        pixels = ds.pixel_array
        value = pixels.astype(float) * float(ds.RescaleSlope) + float(ds.RescaleIntercept)
        gray = np.rint(np.clip((value + 1350) / 1500, 0, 1) * 255).astype(np.uint8)
        base = np.repeat(gray[:, :, None], 3, axis=2)
        peak = base.copy()
        peak[reliable] = np.rint(peak[reliable] * .55 + np.array([255, 60, 60]) * .45)
        peak[edge(reliable)] = [255, 50, 50]
        peak[edge(reference)] = [0, 255, 110]
        pictures = [('native-ct', base, '原生CT像素；固定SOP像素等值本地派生'),
                    ('peak-patch-partial-reference', peak, '红：可靠peak patch；绿：部分参考对象边界；三个预算候选相同')]
        if soft_native is not None:
            alpha = soft_native[:, :, None] * .65
            soft_view = np.rint(base * (1 - alpha) + np.array([255, 180, 0]) * alpha).astype(np.uint8)
            soft_view[edge(reference)] = [0, 255, 110]
            pictures.append(('continuous-mask-display', soft_view, '橙：完整连续mask值；仅展示、不阈值化、不当作CPF区域或病灶概率'))
        panels = []
        for name, image, label in pictures:
            spec, raw = png(out / f'case-{i}-{name}.png', image)
            assets.append({'case_index': i, 'type': name, 'source_ct_sha256': p['source_ct_sha256'],
                           'derivative_sha256': image_record['sha256'], **spec})
            panels.append('<figure><figcaption>' + label + '</figcaption><img width="512" height="512" src="data:image/png;base64,' + base64.b64encode(raw).decode() + '"></figure>')
        sections.append('<section><h2>case_index ' + str(i) + ' / ' + row['status'] + '</h2><p>可靠候选 ' + str(int(reliable.sum())) + ' pixels；部分参考polygon对象 ' + str(len(objects)) + '；' + mask_evidence['status'] + '</p><div>' + ''.join(panels) + '</div></section>')
    summaries = []
    for fraction in BUDGETS:
        metrics = [r['budgets'][str(fraction)]['scales'][SCALE] for r in results]
        valid = [m['observed_reference_coverage'] for m in metrics if m['observed_reference_coverage'] is not None]
        summaries.append({'budget_fraction': fraction, 'expected_cases': 3, 'evaluated_cases': 3,
                          'candidate_pixels_by_case': [m['candidate_voxels'] for m in metrics],
                          'effective_candidate_rate': sum(m['candidate_voxels'] > 0 for m in metrics) / 3,
                          'abstention_rate': 2 / 3, 'computational_failure_rate': 0,
                          'patient_equal_observed_reference_coverage_mean': float(np.mean(valid)) if valid else None,
                          'coverage_patient_denominator': len(valid),
                          'annotation_units_hit': sum(m['annotation_units_hit'] for m in metrics),
                          'annotation_units_evaluable': sum(m['annotation_units_evaluable'] for m in metrics),
                          'cross_scale_consistency': None, 'no_padding_to_budget': True})
    output = {'schema': 'DATA_P1_SAVED_PARTIAL_REFERENCE_EVALUATION_V1',
              'status': 'PARTIAL_REFERENCE_EVALUATED', 'index_sha256': INDEX_SHA,
              'gt_manifest_sha256': template['gt_manifest_sha256'],
              'slice_lock_sha256': template['fixed_slice_lock_sha256'], 'protocol_source_sha256': sha256(Path(__file__).with_name('evaluation_protocol.py')),
              'case_results': results, 'summary': summaries, 'cost_from_saved_LOC_run': run['cost'],
              'DATA_model_calls': 0, 'independent_test_eligible': False,
              'complete_metrics_eligible': False, 'no_GT_rebuild': True,
              'annotation_units_are_polygon_objects_not_3D_lesions': True,
              'unannotated_regions_are_unknown': True, 'overlay_assets': assets,
              'full_continuous_mask_evaluated_as_candidate': False}
    with (out / 'evaluation.json').open('x') as f:
        json.dump(output, f, indent=2, allow_nan=False)
        f.write('\n')
    page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'; connect-src \'none\'"><title>P1部分参考本机叠加</title><style>body{font-family:system-ui;margin:24px}section{border:1px solid #aaa;padding:16px;margin:24px 0}section>div{display:flex;flex-wrap:wrap;gap:16px}figure{margin:0;width:512px;max-width:100%}img{width:100%;height:auto}figcaption{min-height:3em}</style><h1>P1：固定原三SOP，部分参考叠加</h1><p>仅本机开发检查。源像素烧录PHI仍UNKNOWN，不得上传/医院展示。参考不完整；未标注区域UNKNOWN。红peak patch与橙连续mask分开；连续mask不是病灶概率。无完整Dice/IoU/FP或独立测试结论。</p>' + ''.join(sections) + '</html>'
    with (out / 'NATIVE_CT_CANDIDATE_PARTIAL_REFERENCE_V1.html').open('x') as f:
        f.write(page)
    return summaries


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--index', required=True)
    parser.add_argument('--root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps({'summary': evaluate(Path(args.index), Path(args.root), Path(args.output))}))
