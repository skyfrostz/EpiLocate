"""Approval-gated full-Series64 pair: exactly CPU1 then MPS1, no warmup/retry.

Uses INTEGRATION's pinned supervisor, never creates another scheduler. Default
preflight rejects absent approval/dispatch or any unresolved prior queue slot.
Importing this module does not read pixels/checkpoints or import Torch.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
import warnings

import numpy as np

from .encoder_ctfm_mps_smoke import file_sha, write_new
from .encoder_real_input import read_bound_json
from .encoder_real_smoke import full_compare, lattice_from_model
from .encoder_offline_review_v3 import (downsample_generated_control, compose_half_voxel, case_gap_oracle)
from .encoder_volume_runner import (ActualMpsTelemetry, CallJournal, PrivateArtifacts,
                                    cleanup_device, configure_allocator, load_supervisor)

TASK = 'CTFM-V3-ONECASE-FULLSERIES64-PAIR'
JOB = 'ctfm-v3-fullseries64-pair-01'
PROPOSAL_SHA = '839902cc3958df26e7f33d1d4379482c9e47432ff4ebef0ac2ecf3a6d11e2138'
DEPENDENCY_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
SPEC = dict(job_id=JOB, task_key=TASK, owner='ENCODER', device='mps', max_forward=2,
            max_backward=0, timeout_seconds=180, per_case_seconds=120,
            telemetry_startup_seconds=15, telemetry_max_gap_seconds=.25,
            request_grace_seconds=.25, term_grace_seconds=.75, recovery_seconds=2)
TOLERANCE = dict(max_absolute_error=.001, mean_absolute_error=.0001, atol=.001, rtol=.0001)


class AdmissionBlocked(RuntimeError): pass


def queue_gate(queue, *, own_job=None):
    """Read-only mirror of shared UNKNOWN/replay fences; shared lock is authoritative."""
    root = Path(queue)/'slots'; observed = []
    if not root.exists(): return observed
    for slot in root.iterdir():
        if slot.is_symlink() or not slot.is_dir(): raise AdmissionBlocked('UNKNOWN_QUEUE_ENTRY')
        started = json.loads((slot/'started.json').read_bytes())
        if own_job is not None and slot.name == own_job:
            if started['job_id'] != own_job or started['task_key'] != TASK:
                raise AdmissionBlocked('OWN_SLOT_SCOPE_MISMATCH')
            continue
        if not (slot/'finished.json').is_file(): raise AdmissionBlocked('UNKNOWN_SLOT:'+slot.name)
        terminal = json.loads((slot/'finished.json').read_bytes())
        if file_sha(terminal['receipt_path']) != terminal['receipt_sha256']:
            raise AdmissionBlocked('QUEUE_TERMINAL_SHA_MISMATCH')
        if started['task_key'] == TASK: raise AdmissionBlocked('NO_RETRY_OR_NEW_JOB_COUNTER_RESET')
        observed.append(dict(job_id=started['job_id'], terminal_sha256=terminal['receipt_sha256']))
    return observed


def load_authority(args, config, binding):
    """Receipt bytes supplied by chief; preparation alone never authorizes a run."""
    if not all(getattr(args, name, None) for name in ('approval', 'approval_sha', 'dispatch', 'dispatch_sha')):
        raise AdmissionBlocked('APPROVAL_AND_DISPATCH_REQUIRED_BEFORE_REAL_ACCESS')
    approval = read_bound_json(args.approval, args.approval_sha)
    dispatch = read_bound_json(args.dispatch, args.dispatch_sha)
    identity = dict(task_key=TASK, job_id=JOB, config_sha256=args.config_sha,
                    binding_sha256=args.binding_sha, command_template_sha256=args.command_sha,
                    dependency_sha256=DEPENDENCY_SHA, max_forward=2, max_backward=0,
                    timeout_seconds=180, per_case_seconds=120, case_index=1,
                    source_input_sha256=config['selection']['source_input_sha256'],
                    source_ledger_sha256=config['selection']['source_ledger_sha256'])
    for receipt, schema, status in ((approval, 'CTFM_V3_PAIR_APPROVAL_V1', 'APPROVED_NEW_SCOPE'),
                                     (dispatch, 'CTFM_V3_PAIR_DISPATCH_V1', 'EXCLUSIVE_SLOT_ASSIGNED')):
        if (receipt.get('schema') != schema or receipt.get('status') != status
                or receipt.get('owner') != 'ENCODER' or receipt.get('retry') is not False
                or receipt.get('head_training') is not False
                or any(receipt.get(k) != v for k, v in identity.items())):
            raise AdmissionBlocked('AUTHORITY_SCOPE_OR_BUDGET_MISMATCH')
    if dispatch.get('approval_sha256') != args.approval_sha:
        raise AdmissionBlocked('DISPATCH_APPROVAL_BINDING_MISMATCH')
    recovery = approval.get('prior_unknown_reconciliation')
    if (not isinstance(recovery, dict) or recovery.get('status') != 'EXTERNALLY_VERIFIED_RECOVERY'
            or not recovery.get('path') or not recovery.get('sha256')):
        raise AdmissionBlocked('EXTERNAL_UNKNOWN_RECONCILIATION_REQUIRED')
    read_bound_json(recovery['path'], recovery['sha256'])
    # A receipt claiming recovery cannot bypass the shared queue's actual state.
    return dict(approval_sha256=args.approval_sha, dispatch_sha256=args.dispatch_sha,
                recovery_reference=recovery, identity=identity)


def validate_preflight(args):
    config = read_bound_json(args.config, args.config_sha)
    binding = read_bound_json(args.binding, args.binding_sha)
    command = read_bound_json(args.command_template, args.command_sha)
    if (binding['proposal_sha256'] != PROPOSAL_SHA or config['proposal_sha256'] != PROPOSAL_SHA
            or binding['config_sha256'] != args.config_sha or config['spec'] != SPEC
            or config['tolerance'] != TOLERANCE or config['shape'] != [1, 1, 64, 64, 64]
            or config['feature_shape'] != [1, 512, 4, 4, 4]
            or config['calls'] != dict(cpu=1, mps=1, warmup=0, repeats=0, backward=0, retry=False)
            or binding['supervisor_bundle']['dependency_sha256'] != DEPENDENCY_SHA
            or command['binding_sha256'] != args.binding_sha
            or command['config_sha256'] != args.config_sha):
        raise AdmissionBlocked('FIXED_EXECUTION_BINDING_MISMATCH')
    # Missing approval blocks before imports of Torch or any source pixel hashing.
    authority = load_authority(args, config, binding)
    module = Path(__file__).resolve().parent
    names = {'encoder_fov64_pair.py', 'encoder.py', 'encoder_offline_review_v3.py', 'encoder_volume_runner.py',
             'encoder_real_input.py', 'encoder_real_smoke.py', 'encoder_volume_dry_run.py',
             'encoder_volume_guard.py', 'encoder_ctfm_mps_smoke.py'}
    if set(binding['source_sha256']) != names: raise AdmissionBlocked('INCOMPLETE_SOURCE_BINDING')
    for name, sha in binding['source_sha256'].items():
        if file_sha(module/name) != sha: raise AdmissionBlocked('SOURCE_DRIFT:'+name)
    shared = load_supervisor(binding)
    if (str(Path(sys.executable).resolve()) != str(Path(command['python']).resolve())
            or command['cwd'] != str(module.parents[2])
            or command['runner_module'] != 'epi_next.encoder_fov64_pair'
            or file_sha(binding['spec_path']) != binding['spec_sha256']
            or json.loads(Path(binding['spec_path']).read_bytes()) != SPEC):
        raise AdmissionBlocked('COMMAND_OR_SPEC_BINDING_MISMATCH')
    if config['queue_root'] != str(shared.hospital_runtime.QUEUE_ROOT): raise AdmissionBlocked('QUEUE_ROOT_MISMATCH')
    queue = queue_gate(config['queue_root'], own_job=JOB if args.mode == 'child' else None)
    output = Path(config['output']).resolve()
    private = module.parents[2]/'.local/ctfm-v3-fov64-pair'
    if not output.is_relative_to(private) or output == private or output.exists():
        raise AdmissionBlocked('NEW_PRIVATE_OUTPUT_REQUIRED_NO_RESUME')
    if args.mode == 'child':
        if (os.environ.get('EPI_NEXT_DEPENDENCY_SHA') != DEPENDENCY_SHA
                or Path(os.environ['EPI_NEXT_DEPENDENCY_ROOT']).resolve()
                != Path(binding['supervisor_bundle']['dependency_root']).resolve()
                or json.loads((Path(os.environ['EPI_NEXT_SUPERVISOR_DIR'])/'spec.json').read_bytes()) != SPEC):
            raise AdmissionBlocked('ACTUAL_CHILD_SUPERVISION_BINDING_MISMATCH')
    return config, binding, command, authority, shared, queue


def prepare_input(config, artifacts, guard):
    """Only authorized child reads the bound saved128 normalized volume."""
    guard.check(); before = time.monotonic(); selected = config['selection']
    old = read_bound_json(selected['source_ledger_path'], selected['source_ledger_sha256'])
    if file_sha(selected['source_input_path']) != selected['source_input_sha256']:
        raise ValueError('SAVED128_INPUT_SHA_MISMATCH')
    if old['input_file_sha256'] != selected['source_input_sha256']:
        raise ValueError('PARENT_INPUT_LEDGER_BINDING_MISMATCH')
    parent = np.load(selected['source_input_path'], allow_pickle=False)
    if parent.shape != (1, 1, 128, 128, 128): raise ValueError('BOUND128_SHAPE_REQUIRED')
    guard.check(); value = downsample_generated_control(parent); guard.check()
    probes = []
    for point in [*itertools.product([0, 63], repeat=3), (32, 32, 32)]:
        guard.check()
        block = parent[(0, 0, *[slice(2*u, 2*u+2) for u in point])]
        expected = sum(float(v) for v in block.ravel())/8
        observed = float(value[(0, 0, *point)])
        if abs(expected-observed) > 6e-8: raise ValueError('CELL_AVERAGE_PROBE_FAILED')
        probes.append(dict(model64_index=list(point), expected=expected, observed=observed,
                           absolute_error=abs(expected-observed)))
    native = compose_half_voxel(old['model_to_native'], [2, 2, 2])
    lps = compose_half_voxel(old['model_to_lps'], [2, 2, 2])
    edges = np.array([[*p, 1] for p in itertools.product([-.5, 63.5], repeat=3)]).T
    parent_edges = np.array([[*p, 1] for p in itertools.product([-.5, 127.5], repeat=3)]).T
    edge_error = float(np.max(np.abs(native@edges-np.asarray(old['model_to_native'])@parent_edges)))
    inverse_error = float(np.max(np.abs(np.linalg.inv(native)@native@edges-edges)))
    if max(edge_error, inverse_error) > 1e-8: raise ValueError('WHOLE_FOV_GEOMETRY_FAILED')
    del parent
    input_sha = artifacts.array('input64.npy', value)
    ledger = dict(schema='CTFM_FOV64_PAIR_LEDGER_V1', case_index=1, task_key=TASK,
                  input_shape=list(value.shape), proposed_feature_shape=[1, 512, 4, 4, 4],
                  source_input_sha256=selected['source_input_sha256'], source_ledger_sha256=selected['source_ledger_sha256'],
                  input_file_sha256=input_sha, input_content_sha256=hashlib.sha256(value.tobytes()).hexdigest(),
                  model_to_native=native.tolist(), native_to_model=np.linalg.inv(native).tolist(),
                  model_to_lps=lps.tolist(), lps_to_model=np.linalg.inv(lps).tolist(),
                  nominal_feature_to_native=(native@np.diag([16, 16, 16, 1])).tolist(),
                  spacing_spl_mm=(2*np.asarray(old['proposed_spacing_spl_mm'])).tolist(),
                  field_of_view='FULL_APPROVED_SELECTED_SERIES', crop='NONE', new_padding='NONE',
                  native_padding='UNKNOWN', edge_error_voxels=edge_error, inverse_error_voxels=inverse_error,
                  cell_average_probes=probes, preprocessing_seconds=time.monotonic()-before,
                  normalization='already normalized saved128; no repeatedHU scaling', input_range=[float(value.min()), float(value.max())])
    ledger_sha = artifacts.json('ledger64.json', ledger)
    prepared = dict(input_path=str(artifacts.directory/'input64.npy'), input_sha256=input_sha,
                    ledger_path=str(artifacts.directory/'ledger64.json'), ledger_sha256=ledger_sha)
    artifacts.json('prepared64.json', prepared)
    return prepared


def verify_prepared(prepared, artifacts):
    for kind in ('input', 'ledger'):
        if file_sha(prepared[kind+'_path']) != prepared[kind+'_sha256']:
            raise ValueError('FROZEN64_'+kind.upper()+'_DRIFT')
    ledger = json.loads(Path(prepared['ledger_path']).read_bytes())
    if (ledger['input_file_sha256'] != prepared['input_sha256'] or ledger['task_key'] != TASK
            or ledger['field_of_view'] != 'FULL_APPROVED_SELECTED_SERIES'):
        raise ValueError('FROZEN_INPUT_LEDGER_SCOPE_MISMATCH')
    value = np.load(prepared['input_path'], allow_pickle=False)
    if value.shape != (1, 1, 64, 64, 64) or value.dtype != np.float32 or not np.isfinite(value).all():
        raise ValueError('FINITE_FP32_FOV64_REQUIRED')
    return value


def execute_pair(prepared, artifacts, guard, journal, backend, result):
    """Independent fixed pair; backend can be generated/fake for engineering tests."""
    guard.check(); value = verify_prepared(prepared, artifacts); guard.check()
    before = time.monotonic(); backend.load(journal)
    result['loading_seconds'] = time.monotonic()-before
    outputs = []
    for device in ('cpu', 'mps'):
        guard.check(); journal.reserve(1, device, 0); guard.check()
        array, measurements = backend.infer(value, device)
        journal.event('NETWORK_RETURNED', **measurements); guard.check()
        if array.shape != (1, 512, 4, 4, 4) or array.dtype != np.float32 or not np.isfinite(array).all():
            raise ValueError('FINITE_FP32_FULL_FEATURE_REQUIRED')
        artifacts.array(device+'_features.npy', array)
        artifacts.array(device+'_gap512.npy', case_gap_oracle(array, field_of_view='FULL_APPROVED_SELECTED_SERIES').astype(np.float32))
        outputs.append(array); result[device] = measurements
    guard.check()
    result['comparison'] = full_compare(*outputs, TOLERANCE)
    if result['comparison']['status'] != 'PASS': raise ValueError('FULL_TENSOR_TOLERANCE_FAILED')
    if journal.actual != 2 or journal.device_counts != {'cpu': 1, 'mps': 1}:
        raise ValueError('EXACT_TWO_NETWORK_ENTRIES_REQUIRED')
    return result


class TorchBackend:
    def __init__(self, torch, config, telemetry):
        self.torch, self.config, self.telemetry = torch, config, telemetry
        self.adapter = self.count_hook = None

    def load(self, journal):
        from .encoder import load_ctfm_local
        self.telemetry.phase = 'model_loading'
        self.adapter = load_ctfm_local(self.config['checkpoint_path'], self.config['checkpoint_sha256'])
        self.lattice = lattice_from_model(self.adapter.encoder)
        self.count_hook = self.adapter.encoder.register_forward_pre_hook(journal.network_entry)

    def infer(self, value, device):
        torch = self.torch; self.telemetry.phase = device+'_single_cold_forward'; hooks = []
        observations, wrong = {}, []
        x = features = None
        try:
            before = time.monotonic(); self.adapter.to(device); x = torch.from_numpy(value).to(device)
            if device == 'mps': torch.mps.synchronize()
            transfer = time.monotonic()-before
            if device == 'mps':
                def audit(module, inputs, output):
                    name = type(module).__name__; observations[name] = observations.get(name, 0)+1
                    if any(isinstance(v, torch.Tensor) and v.device.type != 'mps' for v in (*inputs, output)):
                        wrong.append(name)
                for module in self.adapter.modules():
                    if isinstance(module, (torch.nn.Conv3d, torch.nn.BatchNorm3d, torch.nn.ReLU)):
                        hooks.append(module.register_forward_hook(audit))
            before = time.monotonic()
            with torch.inference_mode(): features = self.adapter.extract(x)
            if device == 'mps': torch.mps.synchronize()
            inference = time.monotonic()-before
            if wrong: raise ValueError('CPU_MODULE_TENSOR_INSIDE_MPS')
            before = time.monotonic(); array = features.cpu().numpy().copy()
            if device == 'mps': torch.mps.synchronize()
            return array, dict(transfer_seconds=transfer, cold_forward_seconds=inference,
                               readback_seconds=time.monotonic()-before, module_observations=observations,
                               feature_shape=list(array.shape), warmed_benchmark=False)
        finally:
            for hook in hooks: hook.remove()
            x = features = None

    def release(self):
        if self.count_hook is not None: self.count_hook.remove()
        self.count_hook = self.adapter = None


def finish_child(artifacts, guard, journal, result, cleanup, telemetry):
    with guard.ledger() as counters: result['durable_counters'] = dict(counters)
    result.update(actual_forward=journal.actual, actual_backward=0, adapter_attempts=journal.adapter_attempts,
                  actual_by_device=dict(journal.device_counts), cleanup=cleanup,
                  THREE_CASE_SMOKE='NOT RUN', F0='BLOCKED', independent64_DATA_QA='PENDING')
    if not cleanup['device_recovered']: result['status'] = 'FAIL'
    result['states'] = dict(MPS_COMPATIBILITY='PASS' if result['status']=='PASS' else
                           ('FAIL' if journal.device_counts['mps'] else 'NOT RUN'),
                           RESOURCE_BENCHMARK='PASS' if result['status']=='PASS' else 'FAIL',
                           THREE_CASE_SMOKE='NOT RUN', F0='BLOCKED')
    result['single_case_engineering_execution'] = result['status']
    terminal = 'SUCCESS' if result['status'] == 'PASS' else 'FAILED'
    # Keep all local writes inside heartbeat duty. Shared complete is the final action.
    artifacts.json('result.json', result)
    artifacts.json('mps_telemetry_before_complete.json', telemetry.report())
    artifacts.json('manifest.json', dict(assets_sha256=dict(artifacts.assets), status=result['status']))
    guard.complete(status=terminal, reason=result.get('failure', {}).get('reason'),
                   device_recovered=cleanup['device_recovered'], actual_forward=journal.actual, actual_backward=0)
    return 0 if terminal == 'SUCCESS' else 2


def run_child(config, binding, authority, shared):
    if 'torch' in sys.modules: raise AdmissionBlocked('TORCH_ALREADY_IMPORTED_BEFORE_STRICT_ENV')
    os.umask(0o077)
    os.environ.update(PYTORCH_ENABLE_MPS_FALLBACK='0', PYTORCH_MPS_FAST_MATH='0',
                      OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    import torch
    telemetry = ActualMpsTelemetry(torch.mps)
    guard = shared.ChildGuard.from_environment(mps_driver=telemetry)
    artifacts = PrivateArtifacts(Path(config['output']), 16*1024**2)
    journal = CallJournal(guard, artifacts.directory/'calls.jsonl')
    backend = TorchBackend(torch, config, telemetry); baseline = None; caught = []
    result = dict(status='FAIL', task_key=TASK, job_id=JOB, command=[sys.executable, *sys.argv],
                  authority=authority, torch_version=torch.__version__, source_sha256=binding['source_sha256'],
                  checkpoint_sha256=config['checkpoint_sha256'], started_monotonic=time.monotonic())
    try:
        with guard.ledger() as counters:
            if counters['forward'] or counters['backward'] or counters['cases']:
                raise AdmissionBlocked('GLOBAL_EXPERIMENT_ALREADY_STARTED_NO_RETRY')
        guard.check(); guard.begin_case('case_1')
        if not torch.backends.mps.is_built() or not torch.backends.mps.is_available(): raise RuntimeError('MPS_UNAVAILABLE')
        baseline = telemetry(); result['allocator'] = configure_allocator(torch.mps)
        torch.set_num_threads(1); torch.set_num_interop_threads(1); torch.manual_seed(17)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always'); warnings.filterwarnings('error', message='.*fallback.*')
            prepared = prepare_input(config, artifacts, guard); result['prepared'] = prepared
            execute_pair(prepared, artifacts, guard, journal, backend, result)
        guard.check(); guard.end_case(); result['status'] = 'PASS'
    except Exception as exc:
        result['failure'] = dict(type=type(exc).__name__, reason=str(exc))
    # Exception tracebacks gone before deleting the last model reference/cleanup.
    result['warnings'] = [str(w.message) for w in caught]
    result['adapter_internal_queries'] = backend.adapter.actual_queries if backend.adapter is not None else 0
    backend.release()
    cleanup = cleanup_device(torch.mps, telemetry, baseline) if baseline is not None else dict(
        device_recovered=False, final_actual_child_memory=None, error='STARTUP_BASELINE_UNAVAILABLE')
    result['compute_child_elapsed_seconds'] = time.monotonic()-result['started_monotonic']
    result['sampled_process_peak_rss_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return finish_child(artifacts, guard, journal, result, cleanup, telemetry)


def launch(args, config, binding, command, authority, shared, queue):
    """Only invoke existing supervisor; its serial admission remains authoritative."""
    os.umask(0o077)
    local = Path(config['output']).parent
    local.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = dict(config_sha256=args.config_sha, binding_sha256=args.binding_sha,
                   command_template_sha256=args.command_sha, authority=authority, queue_observed=queue)
    child = [sys.executable, '-m', 'epi_next.encoder_fov64_pair', '--mode', 'child']
    for key in ('config', 'config_sha', 'binding', 'binding_sha', 'command_template', 'command_sha',
                'approval', 'approval_sha', 'dispatch', 'dispatch_sha'):
        child.extend(['--'+key.replace('_', '-'), str(getattr(args, key))])
    bundle = binding['supervisor_bundle']
    parent = [sys.executable, '-c', 'from epinext_wave1_supervisor_v2.wave1_supervisor import main; raise SystemExit(main())',
              '--spec', binding['spec_path'], '--output-root', config['supervisor_output_root'],
              '--dependency-root', bundle['dependency_root'], '--dependency-sha', DEPENDENCY_SHA, '--', *child]
    env = dict(os.environ, **command['environment'])
    receipt.update(argv=parent, environment=command['environment'], cwd=command['cwd'])
    write_new(local/'actual_command_binding.json', receipt)  # fails on any retry
    completed = subprocess.run(parent, cwd=command['cwd'], env=env)
    write_new(local/'launch_exit.json', dict(exit_code=completed.returncode))
    return completed.returncode


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=('preflight', 'launch', 'child'), default='preflight')
    for key in ('config', 'binding', 'command-template'):
        p.add_argument('--'+key, type=Path, required=True)
    for key in ('config-sha', 'binding-sha', 'command-sha'): p.add_argument('--'+key, required=True)
    for key in ('approval', 'dispatch'): p.add_argument('--'+key, type=Path)
    for key in ('approval-sha', 'dispatch-sha'): p.add_argument('--'+key)
    args = p.parse_args()
    try:
        config, binding, command, authority, shared, queue = validate_preflight(args)
        if args.mode == 'preflight':
            print(json.dumps(dict(status='PREFLIGHT_PASS_NOT_EXECUTED', real_model_calls=0))); return 0
        if args.mode == 'child': return run_child(config, binding, authority, shared)
        return launch(args, config, binding, command, authority, shared, queue)
    except AdmissionBlocked as exc:
        print(json.dumps(dict(status='BLOCKED', reason=str(exc), real_model_calls_started_by_this_admission=0)))
        return 3


if __name__ == '__main__': raise SystemExit(main())
