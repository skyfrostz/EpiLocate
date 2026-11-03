"""Generated normalized metadata only, no actual Index/NPY/DICOM reads."""
import copy
import pytest
from epi_next.slice_evaluation_registry import build_registry, MappingRejected


def fixture():
    ref = {'path': 'GENERATED_ONLY', 'sha256': 'a' * 64}
    evidence = {k: ref for k in ('index', 'labels', 'publisher_order', 'index_base',
                               'version', 'row_extent', 'source_subject_binding')}
    evidence.update(label_version_resolved=True,
                    order_policy='SLICE_LOCATION_ASCENDING')
    group = {'source_group_id': 'GENERATED_A', 'split': 'train_weak', 'depth': 8,
             'geometry_binding': ref, 'fixed8': list(range(8)),
             'native_slices': [{'native_index': i, 'member_key': str(i),
                                'ipp_normal_position': i * 2., 'slice_location': i * 2.}
                               for i in range(8)]}
    index = [{'source_group_id': 'GENERATED_A', 'annotation_case_index': 0}]
    labels = [{'annotation_case_index': 0, 'coverage': 'FULL_SELECTED_STACK_EXPLICIT',
               'labels': [0, 1, None, 0, 0, 0, 0, 1]}]
    return [group], index, labels, evidence


def test_pair_and_unknown_are_evaluation_only():
    groups, index, labels, ev = fixture()
    other = copy.deepcopy(groups[0]); other['source_group_id'] = 'GENERATED_B'
    groups.append(other)
    result = build_registry(groups, index, labels, ev)
    assert result['denominators'] == {'source_groups': 2, 'paired_groups': 1, 'unknown_groups': 1}
    assert result['rows'][0]['fixed8_unknown'] == 1
    assert result['rows'][1]['fixed8_labels'] == [None] * 8
    assert result['rows'][1]['scan_known_positive'] == 0  # unknown denominator retained
    for purpose in ('training', 'slice_selection', 'ROI', 'threshold_selection'):
        with pytest.raises(MappingRejected, match='EVALUATION_ONLY'):
            build_registry(groups, index, labels, ev, purpose=purpose)


@pytest.mark.parametrize('defect', ['duplicate_group', 'duplicate_index', 'missing_row',
    'reversed_native', 'ambiguous_location', 'duplicate_location', 'missing_location',
    'duplicate_member', 'wrong_length', 'padded', 'version', 'order', 'fixed8', 'nan',
    'invalid_label', 'index_base', 'duplicate_annotation', 'missing_geometry'])
def test_fail_closed(defect):
    g, i, a, e = fixture()
    if defect == 'duplicate_group': g.append(copy.deepcopy(g[0]))
    if defect == 'duplicate_index': i.append(copy.deepcopy(i[0]))
    if defect == 'missing_row': a.clear()
    if defect == 'reversed_native': g[0]['native_slices'].reverse()
    if defect == 'ambiguous_location':
        g[0]['native_slices'][1]['slice_location'] = 20
    if defect == 'duplicate_location': g[0]['native_slices'][1]['slice_location'] = 0
    if defect == 'missing_location': del g[0]['native_slices'][1]['slice_location']
    if defect == 'duplicate_member': g[0]['native_slices'][1]['member_key'] = '0'
    if defect == 'wrong_length': a[0]['labels'].append(0)
    if defect == 'padded': a[0]['coverage'] = 'ASSUMED_PADDED'
    if defect == 'version': e['label_version_resolved'] = False
    if defect == 'order': e['order_policy'] = 'UNKNOWN'
    if defect == 'fixed8': g[0]['fixed8'].reverse()
    if defect == 'nan': g[0]['native_slices'][1]['ipp_normal_position'] = float('nan')
    if defect == 'invalid_label': a[0]['labels'][0] = True
    if defect == 'index_base': i[0]['annotation_case_index'] = -1
    if defect == 'duplicate_annotation': a.append(copy.deepcopy(a[0]))
    if defect == 'missing_geometry': del g[0]['geometry_binding']
    with pytest.raises(MappingRejected): build_registry(g, i, a, e)


@pytest.mark.parametrize('policy', ['SLICE_LOCATION_ASCENDING', 'SLICE_LOCATION_DESCENDING'])
def test_proven_reverse_bijection(policy):
    g, i, a, e = fixture(); e['order_policy'] = policy
    for s in g[0]['native_slices']: s['slice_location'] *= -1
    row = build_registry(g, i, a, e)['rows'][0]
    expected = list(reversed(a[0]['labels'])) if policy.endswith('ASCENDING') else a[0]['labels']
    assert row['slice_labels_native_order'] == expected
    assert sorted(row['publisher_to_native_indices']) == list(range(8))
