"""Offline request verifier; real dispatch/model/input loading belongs to INT."""
import argparse
import hashlib
import json
from pathlib import Path
from .hspi_core_v3 import HSPIConfig,source_sha
from .e2_handler_v4 import semantics


def config_from_request(request):
    c=dict(request['core_config'])
    for key in ('image_size','grids','adam_betas'):c[key]=tuple(c[key])
    return HSPIConfig(**c).validate()


def validate_request(path):
    path=Path(path);raw=path.read_bytes();p=json.loads(raw);c=config_from_request(p)
    if p['authority']!='NOT_AUTHORIZED' or p['execution_status']!='NOT_RUN':
        raise ValueError('REQUEST_CANNOT_SELF_AUTHORIZE')
    if c.sha256()!=p['core_config_sha256'] or source_sha()!=p['source_binding']['core_sha256']:
        raise ValueError('CONFIG_OR_CORE_SHA_MISMATCH')
    root=Path(__file__).parents[1]
    for relative,expected in p['source_binding']['module_sha256'].items():
        if hashlib.sha256((root/relative).read_bytes()).hexdigest()!=expected:
            raise ValueError('SOURCE_DEPENDENCY_DRIFT:'+relative)
    if p['profile']=='E2_Q_THREE_FIXED_SLICES_V4':
        if (c.grids,c.stages,c.steps,c.reference_grid,c.epsilon,c.lam)!=( (7,10,13),2,10000,7,2,1.):
            raise ValueError('Q_PROFILE_CHANGED')
        costs=p['cost'];cases=p['reuse_plan']['cases']
        new_branches=sum(len(v['new_branch_maxima']) for v in cases)
        if new_branches!=13 or [r['case_index'] for r in cases]!=[1,2,3]:raise ValueError('REUSE_PLAN_CHANGED')
        if (costs['forward'],costs['backward'],costs['optimizer_updates'])!=(130013,130000,130000):
            raise ValueError('Q_COST_MISMATCH')
        if any(semantics(c)!=v['branch_semantics'] for v in cases):raise ValueError('REUSE_SCIENCE_MISMATCH')
        if costs['resume_events'] or costs['audit_forwards'] or costs['extra_autograd']:
            raise ValueError('UNREQUESTED_RESTORE_OR_AUDIT')
    elif p['profile']=='P1_SELECTED_MASK_FIDELITY_V4':
        if p['cost']!={'forward':5,'backward':0,'optimizer_updates':0,'extra_autograd':0}:
            raise ValueError('FIDELITY_COST_MISMATCH')
    else:raise ValueError('UNKNOWN_PROFILE')
    return {'schema':'E2_OFFLINE_REQUEST_CHECK_V4','status':'VALIDATED_NOT_AUTHORIZED_NOT_RUN',
        'request_sha256':hashlib.sha256(raw).hexdigest(),'core_config_sha256':c.sha256(),
        'profile':p['profile'],'cost':p['cost'],'medical_forward':0,'medical_backward':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--request',required=True,type=Path)
    parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    if args.execute:parser.error('REAL_EXECUTION_BLOCKED: request is not authority; use approved INT controlled entry')
    print(json.dumps(validate_request(args.request),indent=2))


if __name__=='__main__':main()
