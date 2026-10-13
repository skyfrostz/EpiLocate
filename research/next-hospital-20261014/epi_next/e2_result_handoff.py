"""Explicit mode/profile/branch sidecar for LOC-produced E2 results.

No model imports, algorithm implementation, GT parsing or status promotion.
Existing source results and traces are preserved by exact bytes and SHA.
"""
import re
from pathlib import Path

from .artifacts import canonical_json, persist_run, _safe_name, sha256

AXES = {'METHOD_SPEC','IMPLEMENTATION','SYNTHETIC_CHAIN','REAL_CT_COMPONENT',
        'REAL_CT_FULL_CHAIN','LOCALIZATION_BENEFIT'}
TERMINALS = {'SUCCESS','NO_RELIABLE_RESPONSE','PARTIAL_BUDGET','FAILED','BLOCKED','NOT RUN'}
BRANCH_STATES = {'COMPLETE','NO_FEASIBLE_MASK','OPTIMIZATION_PARTIAL','NOT RUN','FAILED','BLOCKED'}


def require_hash(value):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value):
        raise ValueError('EXPLICIT_SHA_REQUIRED')


def branch_key(record):
    scale=record['scale_index'];stage=record['stage'];grid=record['grid_yx']
    if (type(scale) is not int or scale<0 or type(stage) is not int or stage<1
            or not isinstance(grid,list) or len(grid)!=2
            or any(type(v) is not int or v<1 for v in grid)):
        raise ValueError('INVALID_SCALE_STAGE_GRID')
    return scale,tuple(grid),stage


def validate_handoff(envelope, assets):
    if envelope['schema']!='EPI-NEXT-E2-RESULT-HANDOFF-3':raise ValueError('INVALID_SCHEMA')
    mode=envelope['method_mode']
    if mode not in {'E2-W1','E2-REF','E2-CT'}:raise ValueError('EXPLICIT_METHOD_MODE_REQUIRED')
    if not isinstance(envelope['algorithm_version'],str) or not envelope['algorithm_version'].strip():
        raise ValueError('ALGORITHM_VERSION_REQUIRED')
    profile=envelope['run_profile']
    if not profile['profile_id'] or profile['profile_kind'] not in {'HISTORICAL_COMPONENT','COMPONENT','FULL_CORE_CONFIG','CT_ADAPTATION'}:
        raise ValueError('EXPLICIT_RUN_PROFILE_REQUIRED')
    if (mode=='E2-W1' and profile['profile_kind']!='HISTORICAL_COMPONENT'
            or mode=='E2-CT' and profile['profile_kind']!='CT_ADAPTATION'
            or mode=='E2-REF' and profile['profile_kind'] not in {'COMPONENT','FULL_CORE_CONFIG'}):
        raise ValueError('MODE_PROFILE_MISMATCH')
    for digest in [profile['config_sha256'],envelope['model_sha256'],envelope['input_sha256'],
                   envelope['preprocessing_sha256'],envelope['source_result']['sha256']]:require_hash(digest)
    if envelope['execution_status'] not in TERMINALS:raise ValueError('INVALID_EXECUTION_STATUS')
    if not envelope['algorithm_status']:raise ValueError('RAW_ALGORITHM_STATUS_REQUIRED')
    if envelope['psmi_status'] not in {'FINALIZED','NOT_APPLICABLE','NOT_FINALIZED_INCOMPLETE_OPTIMIZATION','NOT RUN'}:
        raise ValueError('EXPLICIT_PSMI_STATUS_REQUIRED')
    if set(envelope['acceptance_axes'])!=AXES:raise ValueError('SEPARATE_ACCEPTANCE_AXES_REQUIRED')
    for axis in envelope['acceptance_axes'].values():
        if axis!='NOT RUN' and (not isinstance(axis,dict) or not axis.get('status') or not axis.get('scope') or not axis.get('reference')):
            raise ValueError('SCOPED_ACCEPTANCE_EVIDENCE_REQUIRED')
    plans={}
    for plan in envelope['planned_branches']:
        key=branch_key(plan);budget=plan['max_iterations']
        if key in plans or type(budget) is not int or budget<1:raise ValueError('INVALID_OR_DUPLICATE_BRANCH_PLAN')
        plans[key]=budget
    if not plans:raise ValueError('EXPLICIT_BRANCH_PLAN_REQUIRED')
    seen=set();traces=set();partial=False;unrun=False;feasible=False
    for branch in envelope['branches']:
        key=branch_key(branch)
        if key not in plans or key in seen:raise ValueError('BRANCH_PLAN_IDENTITY_MISMATCH')
        seen.add(key);n=branch['completed_iterations'];selected=branch['selected_iteration'];state=branch['status']
        if state not in BRANCH_STATES or type(n) is not int or not 0<=n<=plans[key]:raise ValueError('INVALID_BRANCH_STATE_OR_ITERATIONS')
        if selected is not None and (type(selected) is not int or not 1<=selected<=n):raise ValueError('SELECTED_ITERATION_OUTSIDE_OBSERVED_PREFIX')
        scope=branch['selection_scope'];trace=branch['trace_asset']
        if scope not in {'NONE','BEST_SO_FAR','FULL_PLANNED_BUDGET'}:raise ValueError('EXPLICIT_SELECTION_SCOPE_REQUIRED')
        if (selected is None)!=(scope=='NONE'):raise ValueError('SELECTION_SCOPE_MISMATCH')
        if state=='COMPLETE' and (n!=plans[key] or selected is None or scope!='FULL_PLANNED_BUDGET'):
            raise ValueError('COMPLETE_REQUIRES_FULL_PLAN_AND_SELECTION')
        if state=='NO_FEASIBLE_MASK' and (n!=plans[key] or selected is not None):raise ValueError('NO_FEASIBLE_REQUIRES_COMPLETED_PLAN')
        if state=='OPTIMIZATION_PARTIAL' and scope=='FULL_PLANNED_BUDGET':
            raise ValueError('PARTIAL_CANNOT_CLAIM_FULL_OPTIMUM')
        if state=='NOT RUN' and (n!=0 or selected is not None or trace is not None):raise ValueError('UNRUN_NOT_ZERO_CANDIDATE_RESULT')
        if state!='COMPLETE' and not branch['reason']:raise ValueError('NONCOMPLETE_REASON_REQUIRED')
        if n and trace is None:raise ValueError('OBSERVED_TRACE_REQUIRED')
        if trace is not None:
            name=_safe_name(trace['path']);require_hash(trace['sha256'])
            if name=='handoff.json' or name not in assets or sha256(assets[name])!=trace['sha256']:
                raise ValueError('TRACE_ASSET_HASH_OR_BINDING_MISMATCH')
            traces.add(name)
        partial|=state=='OPTIMIZATION_PARTIAL';unrun|=state in {'NOT RUN','FAILED','BLOCKED'}
        feasible|=selected is not None
    if seen!=set(plans):raise ValueError('MISSING_BRANCH_MUST_BE_EXPLICIT_UNRUN')
    if set(assets)!=traces:raise ValueError('ONLY_DECLARED_TRACE_ASSETS_ACCEPTED')
    if envelope['execution_status'] in {'SUCCESS','NO_RELIABLE_RESPONSE'} and (partial or unrun):
        raise ValueError('UNFINISHED_BRANCH_CANNOT_PROMOTE_EXECUTION')
    if envelope['execution_status']=='SUCCESS' and not feasible:raise ValueError('SUCCESS_WITHOUT_SELECTED_BRANCH')
    if envelope['execution_status']=='NOT RUN' and any(b['status']!='NOT RUN' for b in envelope['branches']):
        raise ValueError('UNRUN_EXECUTION_HAS_OBSERVED_BRANCH')
    if envelope['psmi_status']=='FINALIZED' and (partial or unrun):raise ValueError('INCOMPLETE_PSMI_NOT_FINALIZED')
    canonical_json(envelope)


def save_handoff(root, run_id, envelope, assets):
    """Replays only byte-identical sidecars. Original results stay external.

    Envelope describes a run, not a new data/model authorization or a hospital
    runtime installation. Mapping QA continues to belong to DATA.
    """
    if not isinstance(assets,dict) or not all(isinstance(v,bytes) for v in assets.values()):
        raise ValueError('EXISTING_TRACE_BYTES_REQUIRED')
    validate_handoff(envelope,assets)
    source=Path(envelope['source_result']['path'])
    if source.is_symlink() or sha256(source.read_bytes())!=envelope['source_result']['sha256']:
        raise ValueError('SOURCE_RESULT_HASH_MISMATCH')
    payload=dict(assets,**{'handoff.json':canonical_json(envelope)})
    return persist_run(Path(root),run_id,payload)
