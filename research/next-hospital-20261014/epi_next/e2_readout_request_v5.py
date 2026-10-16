"""Source-only E2-R request verification; never authorizes or loads a model."""
import argparse
import hashlib
import json
from pathlib import Path
from .e2_request_v4 import config_from_request
from .e2_readout_v5 import READOUT_POLICY, NAMES
from .target_contract_v5 import CONTRACT_SHA256, validate_metadata

ROOT = Path(__file__).parents[1]
OLD_REQUEST_SHA = 'ab7b2df246a7b9c9c46dddce9b10304686158884fcb33bad06b25000a14f6f1c'
SAVED_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
PAYLOAD_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
PAYLOAD_CANONICAL = '0000000000000000000000000000000000000000000000000000000000000000'
REAL_INPUT = {
    'input_sha256':'0000000000000000000000000000000000000000000000000000000000000000',
    'valid_sha256':'0000000000000000000000000000000000000000000000000000000000000000',
    'model_sha256':'548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734',
    'preprocessing_sha256':'0000000000000000000000000000000000000000000000000000000000000000',
    'model_adapter_sha256':'0debca405ff9ed247fff95548b8ebeab54c11fbaebb07b04849ac853f9b86e50'}
COST = {'maximum_forward':18, 'planned_new_forward':14, 'adapter_check_forward':2,
    'new_readout_forward':12, 'historical_objects_reused':4, 'unallocated_forward':4,
    'backward':0, 'optimizer_updates':0, 'extra_autograd':0,
    'retry':0, 'restore':0, 'audit_replay':0}
LIMITS = {'device':'cpu', 'threads':1, 'seconds_loading_to_cleanup':120,
    'output_bytes':67108864, 'rss_pre_stop_bytes':5368709120, 'rss_supervision_bytes':6442450944}


def validate_request_value(request, *, synthetic=False):
    if request.get('schema') != 'E2_READOUT_REQUEST_V5' or request.get('authority') != 'NOT_AUTHORIZED' or request.get('execution_status') != 'NOT_RUN':
        raise ValueError('REQUEST_IS_NOT_EXECUTION_AUTHORITY')
    if request.get('readout_policy') != READOUT_POLICY or request.get('objects') != NAMES or request.get('cost') != COST or request.get('limits') != LIMITS:
        raise ValueError('FIXED_READOUT_POLICY_COST_OR_LIMITS_CHANGED')
    validate_metadata(request['target_contract'])
    if request.get('contract_sha256') != CONTRACT_SHA256 or request['target_contract']['explanation_target'] != {'policy':'ORIGINAL_ARGMAX_FIXED','declared_class':1}:
        raise ValueError('E2_R_TARGET_CONTRACT_MISMATCH')
    config = config_from_request(request)
    if config.sha256() != request['core_config_sha256']:
        raise ValueError('CONFIG_SHA_MISMATCH')
    if synthetic:
        if request.get('profile') != 'GENERATED_E2_READOUT_V5': raise ValueError('EXPLICIT_GENERATED_PROFILE_REQUIRED')
        return request
    if request.get('profile') != 'E2_R_FIXED_CASE3_V5': raise ValueError('REAL_PROFILE_REQUIRED')
    raw = (ROOT/'configs/e2-selected-fidelity-v4.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != OLD_REQUEST_SHA: raise ValueError('LEGACY_SCIENCE_DRIFT')
    old = json.loads(raw)
    if request['core_config'] != old['core_config'] or request['data_bindings'] != old['data_bindings'] or request['input_binding'] != REAL_INPUT:
        raise ValueError('REAL_BINDING_OR_SCIENCE_CHANGED')
    if request['target_contract']['model_binding'] != {**{k:REAL_INPUT[k] for k in ('model_sha256','preprocessing_sha256','model_adapter_sha256')}, 'task_version':'FrozenBaseline_2D_SLICE_P1'}:
        raise ValueError('E2_R_MODEL_TASK_CHANGED')
    if request['reuse_payload_file_sha256'] != PAYLOAD_SHA or request['reuse_payload_canonical_sha256'] != PAYLOAD_CANONICAL or request['geometry_sha256'] != '0000000000000000000000000000000000000000000000000000000000000000':
        raise ValueError('FIXED_SELECTION_OR_GEOMETRY_CHANGED')
    if request['saved_fidelity'] != {'file_sha256':SAVED_SHA, 'source_binding':{
        'prepared_delivery_sha256':old['data_bindings']['prepared_delivery_sha256'],
        'reuse_stage1_sha256':PAYLOAD_SHA, 'scientific_request_sha256':OLD_REQUEST_SHA}}:
        raise ValueError('SAVED_FIDELITY_LOCK_CHANGED')
    required = set(old['source_binding']['module_sha256']) | {
        'epi_next/target_contract_v5.py','epi_next/e2_handler_v5.py',
        'epi_next/e2_readout_v5.py','epi_next/e2_readout_request_v5.py',
        'configs/explanation-target-contract-v5.json'}
    if set(request['source_binding']['module_sha256']) != required:
        raise ValueError('INCOMPLETE_TRANSITIVE_SOURCE_LOCK')
    for relative, expected in request['source_binding']['module_sha256'].items():
        if hashlib.sha256((ROOT/relative).read_bytes()).hexdigest() != expected:
            raise ValueError('SOURCE_DRIFT:'+relative)
    return request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    args = parser.parse_args()
    if args.execute: parser.error('NOT_AUTHORIZED: approved INT loader/slot/parent entry required')
    raw = args.request.read_bytes(); request = validate_request_value(json.loads(raw))
    print(json.dumps({'schema':'E2_R_OFFLINE_CHECK_V5', 'status':'VALIDATED_NOT_AUTHORIZED_NOT_RUN',
        'request_sha256':hashlib.sha256(raw).hexdigest(), 'cost':request['cost'],
        'entry':'epi_next.e2_readout_v5.run_readout', 'medical_forward':0,'medical_backward':0},indent=2))


if __name__ == '__main__': main()
