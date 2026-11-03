"""One immutable metadata preparation; does not load CT, weights or optimizers."""
import argparse
import copy
import json
from pathlib import Path
import sys

from epi_next import p1_recovery_v5 as recovery, p1_runner_v4 as worker
from epi_next.p1_retry_binding_v8 import activity_seconds, control_paths
from epi_next.shared_runner_binding_v3 import verify_model_runtime

BASE_SHA='0000000000000000000000000000000000000000000000000000000000000000'
CONFIG_SHA='0000000000000000000000000000000000000000000000000000000000000000'
DECISION_SHA='0000000000000000000000000000000000000000000000000000000000000000'
TASK='EPI-NEXT-HSPI-P1-CPU-EXACT-CONTINUATION-RETRY1-20261011'
JOB='EPI-NEXT-HSPI-P1-CPU-20261011-RETRY1'


def prepare(control):
    root=Path(worker.__file__).resolve().parents[3]
    control=control.absolute()
    if control!=root/'.local/phase2/p1-retry-v8/control':
        raise ValueError('EXACT_APPROVED_CONTROL_ROOT_REQUIRED')
    ready_path=control/'final-readiness-v8.json'
    template_path=control/'dispatch-template-v8.json'
    if ready_path.exists() or template_path.exists():
        raise ValueError('IMMUTABLE_PREPARATION_EXISTS')
    base_ref={'path':str(root/'.local/phase2/p1-final-combo-v7/execution-manifest-v7.json'),'sha256':BASE_SHA}
    base=recovery.bound_reference(base_ref)
    config_ref={'path':str(control/'retry-config-v8.json'),'sha256':CONFIG_SHA}
    config=recovery.bound_reference(config_ref)
    if config['task_key']!=TASK or config['job_id']!=JOB:
        raise ValueError('EXACT_APPROVED_RETRY_IDENTITY_REQUIRED')
    # Reuse immutable record bindings; no reread of patient arrays/checkpoints.
    keys=('schema','original_config_sha256','original_consolidated_proposal_sha256','conditional_approval',
        'proposal','prepared_delivery','baseline_config','core_config_sha256','caps','milestones','records',
        'integration_source','resource_revision','python_version','model_runtime_packages','legacy_execution_lock')
    ready={k:copy.deepcopy(base[k]) for k in keys}
    if ready['caps']!=worker.CAPS or ready['original_config_sha256']!=worker.P1_SHA:
        raise ValueError('ORIGINAL_SCIENTIFIC_SCOPE_DRIFT')
    for path,sha in base['local_source_bindings'].items():
        if Path(path).name not in ('p1_runner_v4.py','p1_recovery_v5.py') and worker.file_sha(path)!=sha:
            raise ValueError('UNCHANGED_RUNTIME_SOURCE_DRIFT')
    for key in ('conditional_approval','proposal','prepared_delivery','baseline_config','legacy_execution_lock'):
        recovery.bound_reference(ready[key])
    for name,sha in worker.SOURCE_HASHES.items():
        if worker.file_sha(Path(ready['integration_source'])/name)!=sha:
            raise ValueError('FROZEN_LOADER_SOURCE_DRIFT')
    index_path=root.parent/'epi-next-integration/hospital-release/20261011-recovery-chain-v12/manifest.json'
    index_ref={'path':str(index_path),'sha256':recovery.CHAIN_INDEX_SHA}
    index=recovery.bound_reference(index_ref)
    decision_ref=index['decision']
    if decision_ref['sha256']!=DECISION_SHA:raise ValueError('EXACT_NEW_C1_DECISION_REQUIRED')
    _,binding=recovery.recovery_context(index_ref,decision_ref,TASK)
    ready.update(status='PREPARED_NOT_DISPATCH',previous_readiness=base_ref,recovery_binding=binding,
        dependency_root=index['dependency_root'],dependency_sha256=recovery.CHAIN_DEPENDENCY_SHA,
        supervisor_job_id=JOB,supervisor_task_key=TASK,execution_output=config['execution_output'],
        supervision_output_root=config['supervision_output_root'],retry_budget=config['retry_budget'],retry_config=config_ref,
        parent_source_sha256=worker.file_sha(recovery.__file__),python_executable=str(Path(sys.executable).absolute()),
        cwd=str(Path.cwd().resolve()),prepare_command=sys.argv,
        local_source_bindings={str(Path(worker.__file__).with_name(n).resolve()):
            worker.file_sha(Path(worker.__file__).with_name(n)) for n in worker.MODULES},
        real_model_forwards=0,real_model_backwards=0,automatic_retry=False,
        execution_gate='Exact chief single dispatch required; no real run during preparation')
    verify_model_runtime(ready)
    assert activity_seconds(ready)==3540
    if any(Path(ready[k]).exists() for k in ('execution_output','supervision_output_root')):
        raise ValueError('FRESH_OUTPUT_ROOTS_REQUIRED')
    for path,value in ((ready_path,ready),(template_path,None)):
        if value is None:value=recovery.dispatch_template(ready,recovery.reference(ready_path))
        with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
    control_paths(ready,ready_path,template_path)
    return {'readiness':recovery.reference(ready_path),'dispatch_template':recovery.reference(template_path),
        'config':config_ref,'dependency_sha256':ready['dependency_sha256'],
        'real_model_forwards':0,'real_model_backwards':0,'queue_writes':0,'status':'PREPARED_NOT_DISPATCH'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(prepare(args.control),indent=2))
