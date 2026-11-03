"""Pure diagnostic preparation, no filesystem/network/NPY/DICOM/model access.
Input bytes and metadata must be supplied only by a separately approved reader.
Path joins are independent of base feasibility; no inferred medical labels.
"""
import csv
import io
from collections import Counter
from pathlib import PurePosixPath

SCHEMA = 'LABEL_INDEX_INDEPENDENT_DIAGNOSTICS_V3'
COLUMNS = ('Label Index', 'Diagnosis', 'Relative Path', 'Folder/ID')
MAX_ROWS = 2048


def repeated(values):
    return sorted(k for k, n in Counter(values).items() if n > 1)


def canonical_subject(row):
    relative = PurePosixPath(row['Relative Path'].strip().replace('\\', '/'))
    folder = row['Folder/ID'].strip()
    if (relative.is_absolute() or '..' in relative.parts or not folder
            or '/' in folder or '\\' in folder or folder in ('.', '..')):
        raise ValueError('INDEX_PATH_UNSAFE')
    return sorted({str(relative), str(relative / folder)})


def matrix_pairing(original, updated=None):
    """Describe supplied validated NPY headers, never infer extent from capacity."""
    for value in (original, updated):
        if value is None:
            continue
        if (set(value) != {'rows', 'columns', 'dtype', 'sha256', 'binary_values_validated', 'allow_pickle'}
                or any(type(value[k]) is not int or not 0 < value[k] <= 10000 for k in ('rows', 'columns'))
                or not isinstance(value['dtype'], str) or not value['dtype']
                or not isinstance(value['sha256'], str) or len(value['sha256']) != 64
                or any(c not in '0123456789abcdef' for c in value['sha256'])
                or value['binary_values_validated'] is not True or value['allow_pickle'] is not False):
            raise ValueError('VALIDATED_MATRIX_HEADER_REQUIRED')
    return {'original': original, 'updated': updated,
            'shape_agrees': None if updated is None else all(original[k] == updated[k] for k in ('rows', 'columns')),
            'dtype_agrees': None if updated is None else original['dtype'] == updated['dtype'],
            'version_applicability': 'UNKNOWN_REQUIRES_AUTHOR_ROW_CORRESPONDENCE',
            'effective_extent': None, 'padding_policy': 'UNKNOWN_NOT_PROVEN_BY_MATRIX_WIDTH'}


def diagnose_index(raw_csv, label_rows, groups):
    if type(raw_csv) is not bytes or len(raw_csv) > 8192:
        raise ValueError('INDEX_BYTES_CAP')
    if type(label_rows) is not int or not 0 < label_rows <= 10000:
        raise ValueError('LABEL_ROW_CAP')
    reader = csv.DictReader(io.StringIO(raw_csv.decode('utf-8-sig')))
    if reader.fieldnames != list(COLUMNS):
        raise ValueError('EXACT_INDEX_COLUMNS_REQUIRED')
    rows = list(reader)
    if not rows or len(rows) > MAX_ROWS or any(set(r) != set(COLUMNS) or any(v is None for v in r.values()) for r in rows):
        raise ValueError('INDEX_ROW_STRUCTURE')
    ids = [g['source_group_id'] for g in groups]
    directories = [g['source_subject_directory'] for g in groups]
    if len(ids) != len(set(ids)) or len(directories) != len(set(directories)):
        raise ValueError('FIXED_GROUP_IDENTITIES_UNIQUE')
    lookup = dict(zip(directories, groups))
    records = []
    for ordinal, row in enumerate(rows):
        try:
            index = int(row['Label Index'])
        except ValueError:
            index = None
        paths = canonical_subject(row)
        hits = [lookup[p] for p in paths if p in lookup]
        records.append({'Index_row_zero_based': ordinal, 'raw_Label_Index': row['Label Index'],
                        'numeric_Label_Index': index, 'diagnosis': row['Diagnosis'].strip(),
                        'folder': row['Folder/ID'].strip(), 'candidate_subject_paths': paths,
                        'path_join_status': 'AMBIGUOUS' if len(hits) > 1 else ('MATCHED' if hits else 'NO_FIXED_GROUP_MATCH'),
                        'path_matches': [{'source_group_id': g['source_group_id'],
                                          'diagnosis_agrees': row['Diagnosis'].strip() == g['source_diagnosis']}
                                         for g in hits]})
    numeric = [r['numeric_Label_Index'] for r in records if r['numeric_Label_Index'] is not None]
    bases = []
    for base in (0, 1):
        invalid = [{'row_zero_based': r['Index_row_zero_based'], 'raw_Label_Index': r['raw_Label_Index'],
                    'mapped_row': None if r['numeric_Label_Index'] is None else r['numeric_Label_Index'] - base}
                   for r in records if r['numeric_Label_Index'] is None or not 0 <= r['numeric_Label_Index'] - base < label_rows]
        bases.append({'base': base, 'in_range': not invalid, 'out_of_range_or_invalid_rows': invalid})
    valid_bases = [b['base'] for b in bases if b['in_range']]
    unique = valid_bases[0] if len(valid_bases) == 1 else None
    minmax = [min(numeric), max(numeric)] if numeric else None
    gaps = (sorted(set(range(minmax[0], minmax[1] + 1)) - set(numeric))
            if minmax is not None and minmax[1] - minmax[0] <= 10000 else None)
    duplicate_subjects = repeated((r['diagnosis'], r['folder']) for r in records)
    duplicates = repeated(numeric)
    mapping_ready = unique is not None and not duplicates and not duplicate_subjects
    return {'schema': SCHEMA, 'Index_rows': len(records), 'matrix_rows': label_rows,
            'rows': records, 'base_candidates': bases, 'valid_bases': valid_bases, 'unique_numeric_base': unique,
            'base_evidence_level': 'NUMERIC_IN_RANGE_INFERENCE_NOT_EXPLICIT_AUTHOR_STATEMENT',
            'numeric_min_max': minmax, 'numeric_gaps': gaps,
            'duplicate_Label_Indices': duplicates, 'duplicate_diagnosis_folder_pairs': duplicate_subjects,
            'raw_path_join_rows': sum(r['path_join_status'] == 'MATCHED' for r in records),
            'raw_path_join_status': 'COMPUTED_INDEPENDENT_OF_BASE_NOT_MEDICAL_PAIRING',
            'numeric_row_mapping_ready': mapping_ready,
            'medical_pairing_ready': False,
            'medical_denominator': None,
            'requires': ['Author effective column domain and padding evidence',
                         'Applicable label version and explicit row correspondence',
                         'Full publisher-member-nativeZ correspondence'],
            'no_dense_renumbering': True, 'no_training_or_sampling_use': True}
