"""Project the existing, SHA-bound MVP inventory; never read image/object bytes."""
import json
from pathlib import Path
from qa import local_mvp_readonly as legacy

ROOT = legacy.ROOT
ASSETS = ('candidate-64.png', 'response-64.png', 'comparison-64.png')


def derive(binding_ref, audit_ref):
    binding = legacy.bound(binding_ref)
    legacy.validate_binding(binding)
    audit = legacy.bound(audit_ref)
    inventory = audit['artifact_inventory']
    if inventory['data_delivery']['sha256'] != binding['data_delivery']['sha256']:
        raise ValueError('ORIGINAL_LEDGER_REQUIRED')
    ledger = legacy.bound(binding['data_delivery'])
    flows = legacy.bound(inventory['browser acceptance'])['flows']
    rows = []
    model = None
    for n, original in enumerate(ledger['records'], 1):
        saved = legacy.bound(inventory[f'case {n} result'])
        result = saved['result']
        flow = next(f for f in flows if f['case_index'] == n)
        if saved['input_reference']['sha256'] != original['sha256']:
            raise ValueError('SOP_RESULT_MISMATCH')
        current_model = {k: result[k] for k in ('model_id', 'preprocessing_version', 'protocol_id')}
        current_model['checkpoint_sha256'] = result['model_version']
        if model is not None and model != current_model:
            raise ValueError('MODEL_IDENTITY_MISMATCH')
        model = current_model
        assets = {}
        for aid in ASSETS:
            ref = inventory[f'case {n} stored {aid}']
            if Path(ref['path']).parent != Path(binding['source_objects']):
                raise ValueError('ORIGINAL_OBJECT_ROOT_REQUIRED')
            assets[aid] = dict(object_key=Path(ref['path']).name, sha256=ref['sha256'])
        rows.append(dict(case_index=n, case_id=result['case_id'], slice_id=result['slice_id'],
                         result_id=flow['result_id'], job_id=flow['job_id'],
                         input_sha256=original['sha256'], assets=assets,
                         saved_result=inventory[f'case {n} result']))
    return dict(schema='MVP_DEMO64_PROJECTION_V1', permission_scope='LOCAL_MVP_ONLY',
                status='CANDIDATE_NOT_HOSPITAL_APPROVAL', allowed_scale=64,
                original_binding=binding_ref, inventory=audit_ref,
                data_delivery=binding['data_delivery'], model=model, records=rows,
                provenance='Restriction of existing ledger and inventory, not a new data allowlist')


def validate(policy):
    if (policy['schema'] != 'MVP_DEMO64_PROJECTION_V1' or policy['allowed_scale'] != 64
            or policy['permission_scope'] != 'LOCAL_MVP_ONLY'
            or [r['case_index'] for r in policy['records']] != [1, 2, 3]):
        raise ValueError('EXACT_DEMO64_SCOPE_REQUIRED')
    for key in ('case_id', 'slice_id', 'result_id', 'job_id', 'input_sha256'):
        if len({r[key] for r in policy['records']}) != 3:
            raise ValueError('DUPLICATE_DEMO_IDENTITY')
    for row in policy['records']:
        if set(row['assets']) != set(ASSETS):
            raise ValueError('EXACT_64_ASSETS_REQUIRED')
        for ref in row['assets'].values():
            if Path(ref['object_key']).name != ref['object_key'] or len(ref['sha256']) != 64:
                raise ValueError('OBJECT_BINDING_REQUIRED')


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('binding', 'binding-sha', 'audit', 'audit-sha', 'output'):
        p.add_argument('--' + name, required=True)
    a = p.parse_args()
    policy = derive(dict(path=a.binding, sha256=a.binding_sha), dict(path=a.audit, sha256=a.audit_sha))
    validate(policy)
    legacy.private(Path(a.output), policy)
