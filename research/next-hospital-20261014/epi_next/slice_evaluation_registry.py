"""Pure normalized-metadata contract. No file IO, label loading or model imports.

Caller must obtain separate access permission and supply source-bound inputs.
This registry is evaluation-only; no training/sampling/ROI consumer is supported.
"""
import math
import re


class MappingRejected(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise MappingRejected(reason)


def bound(ref):
    return (isinstance(ref, dict) and isinstance(ref.get('path'), str)
            and bool(ref['path']) and isinstance(ref.get('sha256'), str)
            and re.fullmatch('[0-9a-f]{64}', ref['sha256']) is not None)


def unique(rows, key):
    values = [r[key] for r in rows]
    require(len(values) == len(set(values)), 'DUPLICATE_' + key)
    return {r[key]: r for r in rows}


def increasing(values):
    return (all(type(x) in (int, float) and math.isfinite(x) for x in values)
            and all(b - a > 1e-6 for a, b in zip(values, values[1:])))


def build_registry(groups, index_rows, annotation_rows, evidence, *, purpose='evaluation'):
    """Fail closed unless an authorized adapter proves the entire slice bijection.

    IDs are opaque, exact publisher-subject matches. annotation_case_index is
    normalized zero-based using separately established publisher index evidence.
    No truncation, padded-tail inference, filename sorting or direction guessing.
    None labels and groups absent from Index remain UNKNOWN, never negative.
    """
    require(purpose == 'evaluation', 'EVALUATION_ONLY')
    required = ('index', 'labels', 'publisher_order', 'index_base', 'version',
                'row_extent', 'source_subject_binding')
    require(all(bound(evidence.get(k)) for k in required), 'MISSING_SOURCE_EVIDENCE')
    require(evidence.get('label_version_resolved') is True, 'LABEL_VERSION_UNRESOLVED')
    require(evidence.get('publisher_order') is not None
            and evidence.get('order_policy') in ('SLICE_LOCATION_ASCENDING', 'SLICE_LOCATION_DESCENDING'),
            'ORDER_UNPROVEN')
    gmap = unique(groups, 'source_group_id')
    imap = unique(index_rows, 'source_group_id')
    unique(index_rows, 'annotation_case_index')
    amap = unique(annotation_rows, 'annotation_case_index')
    require(all(type(i) is int and i >= 0 for i in amap), 'INVALID_INDEX_BASE')
    require(all(type(r['annotation_case_index']) is int
                and r['annotation_case_index'] >= 0 for r in index_rows), 'INVALID_INDEX_BASE')
    output = []
    for gid, group in gmap.items():
        depth = group['depth']
        require(type(depth) is int and depth >= 8, 'INVALID_DEPTH')
        expected8 = [int((j + .5) * depth / 8) for j in range(8)]
        require(group['fixed8'] == expected8, 'FIXED8_CHANGED')
        require(bound(group.get('geometry_binding')), 'MISSING_GEOMETRY_BINDING')
        require(group['split'] in ('train_weak', 'val_classification'), 'SPLIT_UNKNOWN')
        labels = [None] * depth
        status = 'UNKNOWN_NOT_IN_INDEX'
        publisher_to_native = None
        if gid in imap:
            case = imap[gid]['annotation_case_index']
            require(case in amap, 'INDEX_ROW_WITHOUT_LABEL_ROW')
            annotation = amap[case]
            require(annotation.get('coverage') == 'FULL_SELECTED_STACK_EXPLICIT',
                    'ANNOTATION_EXTENT_UNPROVEN')
            publisher_labels = annotation['labels']
            require(len(publisher_labels) == depth, 'LABEL_LENGTH_MISMATCH_NO_TRUNCATION')
            require(all(v is None or type(v) is int and v in (0, 1) for v in publisher_labels),
                    'INVALID_LABEL')
            slices = group['native_slices']
            require(len(slices) == depth, 'MISSING_SLICE_METADATA')
            require([s['native_index'] for s in slices] == list(range(depth)),
                    'NATIVE_ORDER_MISSING_OR_REVERSED')
            unique(slices, 'member_key')
            require(all(s['member_key'] for s in slices), 'MISSING_MEMBER_KEY')
            require(increasing([s['ipp_normal_position'] for s in slices]),
                    'IPP_DUPLICATE_MISSING_OR_REVERSED')
            locations = [s.get('slice_location') for s in slices]
            require(all(type(v) in (int, float) and math.isfinite(v) for v in locations),
                    'SLICE_LOCATION_MISSING_OR_NONFINITE')
            require(len(set(locations)) == depth, 'SLICE_LOCATION_DUPLICATE')
            require(increasing(locations) or increasing([-v for v in locations]),
                    'SLICE_LOCATION_NATIVE_DIRECTION_AMBIGUOUS')
            publisher_to_native = sorted(range(depth), key=lambda i: locations[i],
                reverse=evidence['order_policy'] == 'SLICE_LOCATION_DESCENDING')
            labels = [None] * depth
            for ordinal, native_index in enumerate(publisher_to_native):
                labels[native_index] = publisher_labels[ordinal]
            status = 'PAIRED_SLICE_REFERENCE_ONLY'
        selected = [labels[i] for i in expected8]
        output.append({'source_group_id': gid, 'split': group['split'],
                       'status': status, 'geometry_binding': group['geometry_binding'],
                       'publisher_to_native_indices': publisher_to_native,
                       'fixed8_native_indices': expected8, 'fixed8_labels': selected,
                       'fixed8_unknown': sum(x is None for x in selected),
                       'fixed8_known_positive': sum(x == 1 for x in selected),
                       'scan_known_positive': sum(x == 1 for x in labels),
                       'scan_unknown': sum(x is None for x in labels),
                       'slice_labels_native_order': labels,
                       'reference_scope': 'SLICE_INFECTION_NOT_PIXEL_MASK'})
    return {'schema': 'SLICE_EVALUATION_REGISTRY_V1', 'purpose': 'evaluation',
            'forbidden_uses': ['training', 'slice_selection', 'ROI', 'threshold_selection'],
            'evidence': evidence, 'rows': output,
            'denominators': {'source_groups': len(groups),
                             'paired_groups': sum(r['status'].startswith('PAIRED') for r in output),
                             'unknown_groups': sum(r['status'].startswith('UNKNOWN') for r in output)},
            'clinical_patient_independence': 'UNKNOWN', 'pixel_localization': 'NOT_EVALUATED'}
