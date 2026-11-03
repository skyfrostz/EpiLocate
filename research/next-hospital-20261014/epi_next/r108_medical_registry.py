"""Pure metadata contract; no file/array/model access or medical verification.

Every predeclared row survives qualification, including failed/UNKNOWN rows.
Evidence references are checked syntactically, never treated as read payloads.
INT must separately verify native geometry and reference extent from authorized
files; this module cannot turn synthetic or self-declared evidence into GT.
"""
import copy
import math
import re

SCHEMA = 'R108_MEDICAL_REGISTRY_V1'
FIELDS = ('case_id', 'source', 'patient', 'license', 'image', 'gt', 'geometry',
          'fixed_k8', 'overlap', 'access', 'prior_use', 'local_use', 'failures')
UNKNOWN = ('UNKNOWN', 'CONFLICT', 'FAILED')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def binding(value):
    return (isinstance(value, dict) and set(value) == {'path', 'sha256'}
            and isinstance(value['path'], str) and 0 < len(value['path']) <= 2048
            and isinstance(value['sha256'], str)
            and re.fullmatch('[0-9a-f]{64}', value['sha256']) is not None)


def text(value):
    return isinstance(value, str) and 0 < len(value) <= 256


def status(part, accepted):
    require(isinstance(part, dict) and part.get('status') in accepted + UNKNOWN, 'STATUS_REQUIRED')


def geometry_claim(g):
    status(g, ('VERIFIED',))
    if g['status'] != 'VERIFIED':
        return
    shape = g['shape_zyx']; affine = g['affine_lps_mm']; spacing = g['spacing_zyx_mm']
    require(isinstance(shape, list) and len(shape) == 3
            and all(type(x) is int and x > 0 for x in shape), 'GEOMETRY_SHAPE')
    require(isinstance(spacing, list) and len(spacing) == 3
            and all(type(x) in (int, float) and math.isfinite(x) and x > 0 for x in spacing), 'GEOMETRY_SPACING')
    require(isinstance(affine, list) and len(affine) == 4
            and all(isinstance(row, list) and len(row) == 4 for row in affine)
            and all(type(x) in (int, float) and math.isfinite(x) for row in affine for x in row)
            and affine[3] == [0, 0, 0, 1], 'GEOMETRY_AFFINE')
    a = affine
    det = (a[0][0]*(a[1][1]*a[2][2]-a[1][2]*a[2][1])
           - a[0][1]*(a[1][0]*a[2][2]-a[1][2]*a[2][0])
           + a[0][2]*(a[1][0]*a[2][1]-a[1][1]*a[2][0]))
    require(abs(det) > 1e-12, 'GEOMETRY_SINGULAR')
    require(all(abs(math.sqrt(sum(a[r][c]**2 for r in range(3)))-spacing[c]) <= 1e-4 for c in range(3)),
            'GEOMETRY_AFFINE_SPACING_DISAGREES')
    require(g.get('axis_order') == 'ZYX_TO_LPS_MM' and g.get('ct_gt_native_grid_equal') is True
            and binding(g.get('qa_binding')) and binding(g.get('transform_binding')), 'GEOMETRY_EXTERNAL_QA_REQUIRED')


def qualify(row):
    require(isinstance(row, dict) and set(row) == set(FIELDS), 'EXACT_CASE_FIELDS')
    require(text(row['case_id']) and row['local_use'] == 'development', 'DEVELOPMENT_ONLY')
    src = row['source']
    require(all(text(src.get(k)) for k in ('dataset_id', 'version', 'official_split'))
            and binding(src.get('metadata_binding')), 'SOURCE_IDENTITY')
    for key, choices in (('patient', ('VERIFIED',)), ('license', ('CLEARED',)),
                         ('overlap', ('CLEARED', 'KNOWN_OVERLAP')), ('access', ('AUTHORIZED',))):
        status(row[key], choices)
    require(row['patient'].get('group_id') is None or text(row['patient']['group_id']), 'PATIENT_GROUP_TYPE')
    require(isinstance(row['failures'], list) and len(row['failures']) <= 64
            and all(text(x) for x in row['failures']), 'FAILURE_REASONS')
    prior = row['prior_use']
    require(set(prior) == {'training', 'development'}
            and all(v is None or type(v) is bool for v in prior.values()), 'PRIOR_USE')
    image, gt = row['image'], row['gt']
    require(image.get('hu_status') in ('NATIVE_HU_VERIFIED', 'WINDOWED_0_255') + UNKNOWN, 'HU_STATUS')
    require(gt.get('extent') in ('COMPLETE', 'PARTIAL') + UNKNOWN
            and gt.get('coverage_domain') in ('FULL_NATIVE_VOLUME', 'SELECTED_NATIVE_PLANES', 'UNKNOWN')
            and gt.get('unannotated_is_background') is False, 'GT_EXTENT_UNKNOWN_NOT_BACKGROUND')
    require(gt.get('expert_status') in ('SOURCE_REPORTED', 'VERIFIED', 'UNKNOWN')
            and (gt.get('author_source') is None or text(gt['author_source'])), 'EXPERT_PROVENANCE')
    labels = gt.get('labels')
    require(isinstance(labels, list) and len(labels) <= 64
            and all(set(x) == {'value', 'raw_class', 'medical_category'} and type(x['value']) is int
                    and text(x['raw_class']) and x['medical_category'] in ('INFECTION', 'LUNG', 'OTHER', 'UNKNOWN') for x in labels),
            'RAW_LABEL_DICTIONARY')
    require(len({x['value'] for x in labels}) == len(labels), 'DUPLICATE_LABEL_VALUE')
    geometry_claim(row['geometry'])
    blockers = list(row['failures'])
    for key, wanted in (('patient', 'VERIFIED'), ('license', 'CLEARED'), ('access', 'AUTHORIZED')):
        part = row[key]
        if part['status'] != wanted:
            blockers.append(key.upper() + '_' + part['status'])
        elif not binding(part.get('evidence')):
            blockers.append(key.upper() + '_EVIDENCE_MISSING')
    if row['patient']['status'] == 'VERIFIED' and not text(row['patient'].get('group_id')):
        blockers.append('PATIENT_GROUP_MISSING')
    if row['license']['status'] == 'CLEARED' and not text(row['license'].get('identifier')):
        blockers.append('LICENSE_IDENTIFIER_MISSING')
    # Method-specific overlap is a disclosed development risk, not CT/GT
    # identity or access permission. It never grants independent-test status.
    overlap = row['overlap']
    overlap_risks = []
    if overlap['status'] != 'CLEARED':
        overlap_risks.append('OVERLAP_' + overlap['status'])
    if not binding(overlap.get('evidence')):
        overlap_risks.append('OVERLAP_EVIDENCE_MISSING')
    methods = overlap.get('by_method', {})
    require(isinstance(methods, dict) and len(methods) <= 32
            and all(text(k) for k in methods), 'METHOD_OVERLAP_STRUCTURE')
    method_risks = {}
    for name, part in methods.items():
        status(part, ('CLEARED', 'KNOWN_OVERLAP'))
        method_risks[name] = ([] if part['status'] == 'CLEARED' else ['OVERLAP_' + part['status']])
        if not binding(part.get('evidence')):
            method_risks[name].append('OVERLAP_EVIDENCE_MISSING')
    for name, part in (('IMAGE', image), ('GT', gt)):
        if not binding(part.get('binding')) or not binding(part.get('evidence')):
            blockers.append(name + '_BINDING_OR_EVIDENCE_MISSING')
    if image['hu_status'] != 'NATIVE_HU_VERIFIED':
        blockers.append('HU_' + image['hu_status'])
    if row['geometry']['status'] != 'VERIFIED':
        blockers.append('GEOMETRY_' + row['geometry']['status'])
    if not any(x['medical_category'] == 'INFECTION' for x in labels):
        blockers.append('INFECTION_CLASS_UNRESOLVED')
    if gt['expert_status'] == 'UNKNOWN' or not text(gt.get('author_source')):
        blockers.append('GT_EXPERT_SOURCE_UNKNOWN')
    if gt['extent'] not in ('COMPLETE', 'PARTIAL'):
        blockers.append('GT_EXTENT_' + gt['extent'])
    k = row['fixed_k8']
    if row['geometry']['status'] == 'VERIFIED':
        depth = row['geometry']['shape_zyx'][0]
        require(depth >= 8 and isinstance(k.get('native_z'), list)
                and all(type(i) is int for i in k['native_z'])
                and k['native_z'] == [int((j+.5)*depth/8) for j in range(8)], 'FIXED_K8_RULE')
    elif k.get('native_z') is not None:
        blockers.append('K8_GEOMETRY_UNVERIFIED')
    if not binding(k.get('preprocess_binding')):
        blockers.append('FROZEN_PREPROCESS_BINDING_MISSING')
    if gt['extent'] == 'COMPLETE' and gt['coverage_domain'] != 'FULL_NATIVE_VOLUME':
        blockers.append('COMPLETE_GT_DOMAIN_UNPROVEN')
    if gt['extent'] == 'PARTIAL' and gt['coverage_domain'] == 'UNKNOWN':
        blockers.append('PARTIAL_KNOWN_DOMAIN_UNPROVEN')
    return dict(record=copy.deepcopy(row), blockers=blockers, overlap_risks=overlap_risks,
                method_overlap_risks=method_risks,
                status='BLOCKED' if blockers else 'METADATA_CLAIMS_QUALIFIED',
                reference_policy='PARTIAL_COVERAGE_ONLY' if gt['extent'] == 'PARTIAL' else gt['extent'],
                complete_reference_claim_eligible=not blockers and gt['extent'] == 'COMPLETE',
                coverage_claim_eligible=not blockers,
                independent_test_eligible=False,
                permits_full_volume_Dice_without_prediction_domain=False,
                payload_verified_by_this_validator=False)


def validate_registry(value):
    require(value.get('schema') == SCHEMA and value.get('purpose') == 'development_evaluation', 'REGISTRY_SCHEMA_OR_PURPOSE')
    cases = value.get('cases')
    require(isinstance(cases, list) and len(cases) <= 1000, 'CASE_COUNT')
    rows = [qualify(row) for row in cases]
    require(len({r['record']['case_id'] for r in rows}) == len(rows), 'DUPLICATE_CASE_ID')
    groups = [r['record']['patient']['group_id'] for r in rows]
    known = all(r['record']['patient']['status'] == 'VERIFIED' and text(g) for r, g in zip(rows, groups))
    return dict(schema='R108_MEDICAL_REGISTRY_VALIDATION_V1', rows=rows,
                denominators=dict(predeclared_cases=len(rows), retained_cases=len(rows),
                    blocked_cases=sum(r['status'] == 'BLOCKED' for r in rows),
                    metadata_claims_qualified=sum(r['status'] == 'METADATA_CLAIMS_QUALIFIED' for r in rows),
                    distinct_patients=len(set(groups)) if known else None),
                repeated_patient_case_ids=[[r['record']['case_id'] for r in rows if r['record']['patient']['group_id'] == g]
                    for g in sorted({g for g in groups if text(g)}) if groups.count(g) > 1],
                evidence_status='METADATA_CONTRACT_ONLY_NOT_MEDICAL_REFERENCE_VERIFIED',
                medical_denominator=None, real_payload_reads=0)
