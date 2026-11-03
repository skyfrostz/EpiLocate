"""One supervised, fixed 24-attempt whole-Series FOV128 experiment.

The shared INTEGRATION supervisor owns process, RSS, pressure and time monitoring.
This compute child owns actual MPS telemetry, preprocessing and model accounting.
Importing this module does not import Torch, read CT pixels or launch a supervisor.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gc
import hashlib
import importlib
import itertools
import json
import os
from pathlib import Path
import resource
import stat
import sys
import threading
import time
import warnings

import numpy as np

from .encoder_ctfm_mps_smoke import file_sha, json_bytes, write_new
from .encoder_real_input import center_ledger, consume_v3, read_bound_json
from .encoder_real_smoke import full_compare, lattice_from_model
from .encoder_volume_dry_run import full_fov_ledger
from .encoder_volume_guard import APPROVAL_SHA, CONFIG_SHA, stream_area_input

REVISION_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
GIB = 1024**3
PRE_STOP = 5 * GIB
PACKAGE = 'epinext_wave1_supervisor_v1'


def validate_bindings(args):
    """Hash all execution inputs before importing Torch or reading CT/weights."""
    overlay = read_bound_json(args.overlay, args.overlay_sha)
    config = read_bound_json(args.config, CONFIG_SHA)
    approval = read_bound_json(args.approval, APPROVAL_SHA)
    revision = read_bound_json(args.revision, REVISION_SHA)
    if (revision['status'] != 'APPROVED_RESOURCE_SEMANTICS_REVISION'
            or revision['original_approval']['sha256'] != APPROVAL_SHA
            or approval['ctfm_implementation_binding']['sha256'] != CONFIG_SHA
            or overlay['scientific_config_sha256'] != CONFIG_SHA
            or overlay['resource_revision_sha256'] != REVISION_SHA
            or overlay['allocator_limit_bytes'] != PRE_STOP
            or overlay['supervisor_package'] not in (PACKAGE, 'epinext_wave1_supervisor_v2')
            or Path(overlay['supervisor_bundle']['package_path']).name != overlay['supervisor_package']):
        raise ValueError('EXECUTION_SCOPE_BINDING_MISMATCH')
    expected = {'owner': 'ENCODER', 'device': 'mps', 'max_forward': 24,
                'max_backward': 0, 'timeout_seconds': 1200, 'per_case_seconds': 120,
                'telemetry_startup_seconds': 15, 'telemetry_max_gap_seconds': .25,
                'request_grace_seconds': .25, 'term_grace_seconds': .75,
                'recovery_seconds': 2}
    if overlay['supervision'] != expected:
        raise ValueError('SUPERVISION_CONFIG_CHANGED')
    root = Path(__file__).resolve().parent
    required = {Path(__file__).name, 'encoder.py', 'encoder_real_input.py',
                'encoder_real_smoke.py', 'encoder_volume_dry_run.py',
                'encoder_volume_guard.py', 'encoder_ctfm_mps_smoke.py'}
    if set(overlay['source_sha256']) != required:
        raise ValueError('INCOMPLETE_RUNNER_SOURCE_BINDING')
    for name, sha in overlay['source_sha256'].items():
        if file_sha(root / name) != sha:
            raise ValueError('RUNNER_SOURCE_DRIFT:' + name)
    if (os.environ.get('EPI_NEXT_DEPENDENCY_SHA') != args.supervisor_sha
            or overlay['supervisor_bundle']['dependency_sha256'] != args.supervisor_sha
            or Path(os.environ['EPI_NEXT_DEPENDENCY_ROOT']).resolve()
            != Path(overlay['supervisor_bundle']['dependency_root']).resolve()):
        raise ValueError('SUPERVISOR_SHA_ENV_MISMATCH')
    directory = Path(os.environ['EPI_NEXT_SUPERVISOR_DIR'])
    spec = json.loads((directory / 'spec.json').read_bytes())
    if any(spec.get(k) != v for k, v in expected.items()):
        raise ValueError('SUPERVISOR_SPEC_MISMATCH')
    if spec.get('task_key') != config['experiment_id']:
        raise ValueError('SUPERVISOR_TASK_MISMATCH')
    # A unique run directory and the shared durable ledger prevent silent resume.
    output = args.output.resolve()
    private = root.parents[2] / '.local' / 'ctfm-volume-wave1'
    if not output.is_relative_to(private) or output == private or output.exists():
        raise ValueError('NEW_ENCODER_PRIVATE_OUTPUT_REQUIRED')
    return config, overlay, spec


def load_supervisor(overlay):
    """Verify fixed import bytes before importing the isolated shared package."""
    bundle = overlay['supervisor_bundle']
    root = Path(bundle['package_path']).resolve()
    manifest = read_bound_json(bundle['import_manifest_path'], bundle['import_manifest_sha256'])
    names = {'wave1_supervisor.py', 'execution_lock.py', 'coordinator_writer.py', 'artifacts.py',
             'hospital_runtime.py', 'hospital_contract.py', 'contracts.py', 'geometry.py'}
    if set(bundle['files']) != names or manifest['files'] != bundle['files']:
        raise ValueError('EIGHT_SHARED_MODULES_REQUIRED')
    if file_sha(root/'__init__.py') != bundle['initializer_sha256']:
        raise ValueError('SHARED_INITIALIZER_DRIFT')
    for name, sha in bundle['files'].items():
        if file_sha(root/name) != sha: raise ValueError('SHARED_IMPORT_DRIFT:' + name)
    # Require the fixed package location; do not let another epi_next namespace win.
    if str(root.parent) not in sys.path: sys.path.insert(0, str(root.parent))
    if root.name not in (PACKAGE, 'epinext_wave1_supervisor_v2'):
        raise ValueError('SHARED_PACKAGE_NAME_MISMATCH')
    shared = importlib.import_module(root.name+'.wave1_supervisor')
    if Path(shared.__file__).resolve() != root/'wave1_supervisor.py':
        raise ValueError('SHARED_MODULE_LOCATION_MISMATCH')
    loaded = shared.verify_loaded_bundle(bundle['dependency_root'], bundle['dependency_sha256'])
    if any(Path(item['path']).parent != root for item in loaded.values()):
        raise ValueError('SHARED_TRANSITIVE_LOCATION_MISMATCH')
    return shared


class ActualMpsTelemetry:
    """Callback executed by ChildGuard in this compute PID; no monitor thread here."""
    def __init__(self, mps, clock=time.monotonic):
        self.mps, self.clock = mps, clock
        self.lock = threading.Lock()
        self.samples = []
        self.phase = 'startup'

    def __call__(self):
        with self.lock:
            started = self.clock()
            sample = {'pid': os.getpid(), 'phase': self.phase, 'monotonic': started,
                      'interval_seconds': None if not self.samples else started-self.samples[-1]['monotonic']}
            try:
                driver = self.mps.driver_allocated_memory()
                tensor = self.mps.current_allocated_memory()
                if any(type(v) is not int or v < 0 for v in (driver, tensor)):
                    raise ValueError('INVALID_ACTUAL_CHILD_MPS_MEMORY')
                sample.update(driver_bytes=driver, tensor_bytes=tensor, error=None)
            except Exception as exc:
                sample.update(driver_bytes=None, tensor_bytes=None, error=type(exc).__name__)
                raise
            finally:
                sample['api_seconds'] = self.clock()-started
                self.samples.append(sample)
            return {'driver_bytes': driver, 'tensor_bytes': tensor}

    def report(self):
        with self.lock:
            samples = list(self.samples)
        intervals = [s['interval_seconds'] for s in samples if s['interval_seconds'] is not None]
        return {'source': 'actual_compute_child', 'pid': os.getpid(), 'target_interval_seconds': .02,
                'sampled_peak_not_instantaneous_peak': True, 'samples': samples,
                'max_actual_interval_seconds': max(intervals, default=None),
                'gaps_over_target': sum(x > .02 for x in intervals),
                'missing_measurements': sum(s['error'] is not None for s in samples),
                'driver_peak_sampled_bytes': max((s['driver_bytes'] for s in samples if s['error'] is None), default=None),
                'tensor_peak_sampled_bytes': max((s['tensor_bytes'] for s in samples if s['error'] is None), default=None)}


def configure_allocator(mps, limit=PRE_STOP):
    recommended = mps.recommended_max_memory()
    if type(recommended) is not int or recommended <= 0 or limit != PRE_STOP:
        raise ValueError('INVALID_ALLOCATOR_BASIS')
    fraction = limit / recommended
    if not 0 < fraction <= 2:
        raise ValueError('UNSUPPORTED_POSITIVE_ALLOCATOR_FRACTION')
    mps.set_per_process_memory_fraction(fraction)
    return {'requested_allocator_bytes': limit, 'recommended_max_memory_bytes': recommended,
            'fraction': fraction, 'derived_allocator_bytes': fraction*recommended,
            'rss_or_total_metal_quota': False, 'driver_pre_stop_bytes': PRE_STOP,
            'driver_monitored_target_bytes': 6*GIB}


class CallJournal:
    """Shared guard reservations and actual encoder entry are different events."""
    def __init__(self, guard, path):
        self.guard, self.path = guard, path
        self.adapter_attempts = 0
        self.actual = 0
        self.device_counts = Counter()
        self.case, self.device, self.repeat = None, None, None

    def event(self, kind, **extra):
        value = dict(event=kind, monotonic=time.monotonic(), case=self.case,
                     device=self.device, repeat=self.repeat, adapter_attempts=self.adapter_attempts,
                     actual_forward=self.actual, **extra)
        with self.path.open('ab') as stream:
            stream.write((json.dumps(value, sort_keys=True, allow_nan=False)+'\n').encode())
            stream.flush(); os.fsync(stream.fileno())

    def reserve(self, case, device, repeat):
        self.case, self.device, self.repeat = case, device, repeat
        self.guard.before_forward()  # fsync reservation; may stop before model entry
        self.guard.check()
        self.adapter_attempts += 1
        self.event('ADAPTER_ATTEMPT')

    def network_entry(self, _module=None, _inputs=None):
        self.guard.check()  # stops arriving during adapter input validation fence entry
        self.actual += 1
        self.device_counts[self.device] += 1
        self.event('NETWORK_ENTERED')


class PrivateArtifacts:
    def __init__(self, directory, limit):
        self.directory, self.limit = directory, limit
        directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.assets = {}
        self._asset_sizes = {}
        self._write_lock = threading.RLock()

    def _disk_snapshot(self):
        """One complete namespace/size observation; never skip missing entries."""
        snapshot, directories = {}, [self.directory]
        while directories:
            directory = directories.pop()
            info = directory.lstat()
            if not stat.S_ISDIR(info.st_mode): raise RuntimeError('TASK_OUTPUT_UNSAFE_DIRECTORY')
            snapshot[directory] = (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                                   info.st_mtime_ns, info.st_ctime_ns)
            # scandir propagates enumeration errors instead of rglob silently skipping them.
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    info = path.lstat()  # one stat; a vanished path invalidates the whole scan
                    if stat.S_ISDIR(info.st_mode):
                        directories.append(path)
                    elif stat.S_ISREG(info.st_mode):
                        snapshot[path] = (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                                          info.st_mtime_ns, info.st_ctime_ns)
                    else:
                        raise RuntimeError('TASK_OUTPUT_UNSAFE_ENTRY')
        return snapshot

    def check_disk(self, additional=0):
        if type(additional) is not int or additional < 0: raise ValueError('INVALID_ADDITIONAL_BYTES')
        with self._write_lock:
            for _ in range(3):  # bounded whole-tree rescan on rename; include tmp bytes
                try:
                    snapshot = self._disk_snapshot()
                except FileNotFoundError:
                    continue
                for name, recorded_size in self._asset_sizes.items():
                    observed = snapshot.get(self.directory/name)
                    if observed is None or not stat.S_ISREG(observed[2]) or observed[3] < recorded_size:
                        raise RuntimeError('TASK_OUTPUT_COMMITTED_ASSET_MISSING_OR_TRUNCATED')
                size = sum(info[3] for info in snapshot.values() if stat.S_ISREG(info[2]))
                if size + additional > self.limit: raise RuntimeError('TASK_OUTPUT_LIMIT')
                return
            raise RuntimeError('TASK_OUTPUT_SCAN_UNSTABLE')

    def array(self, name, value):
        with self._write_lock:
            self.check_disk(value.nbytes + 4096)
            path = self.directory / name
            with path.open('xb') as stream:
                np.save(stream, value, allow_pickle=False)
                stream.flush(); os.fsync(stream.fileno())
                recorded_size = stream.tell()
            self.assets[name] = file_sha(path)
            self._asset_sizes[name] = recorded_size
            return self.assets[name]

    def json(self, name, value):
        with self._write_lock:
            payload = json_bytes(value)
            self.check_disk(len(payload))
            path = self.directory / name
            with path.open('xb') as stream:
                stream.write(payload); stream.flush(); os.fsync(stream.fileno())
            self.assets[name] = file_sha(path)
            self._asset_sizes[name] = len(payload)
            return self.assets[name]


def area_probes(oriented, model_input, check):
    """Independent cell-overlap integration at eight corners and one center."""
    target = model_input.shape[-3:]
    probes = [*itertools.product(*[(0, n-1) for n in target]), tuple(n//2 for n in target)]
    records = []
    for point in probes:
        check(); indices, weights = [], []
        for n, t, u in zip(oriented.shape, target, point):
            left, right = u*n/t, (u+1)*n/t
            idx = np.arange(int(np.floor(left)), int(np.ceil(right)))
            weight = np.maximum(0, np.minimum(idx+1, right)-np.maximum(idx, left))/(right-left)
            indices.append(idx); weights.append(weight)
        values = oriented[np.ix_(*indices)].astype(np.float64)
        values = (np.clip(values, -1024, 2048)+1024)/3072
        expected = float(np.einsum('i,j,k,ijk->', *weights, values))
        observed = float(model_input[(0, 0, *point)])
        error = abs(expected-observed)
        if error > 6e-8:
            raise ValueError('INDEPENDENT_AREA_SAMPLE_MISMATCH')
        records.append(dict(model_index=list(point), expected=expected, observed=observed, absolute_error=error))
    return records


def prepare_inputs(data_path, config, artifacts, guard, telemetry):
    telemetry.phase = 'data_identity_and_preprocessing'
    guard.check()
    cases, receipt = consume_v3(data_path, artifacts.directory)
    artifacts.assets['consumer_receipt.json'] = file_sha(artifacts.directory/'consumer_receipt.json')
    prepared = []
    for case in cases:
        guard.check(); started = time.monotonic(); index = case['case_index']; m = case['mapping']
        old = center_ledger(m['shape_krc'], m['affine_lps'])
        ledger = full_fov_ledger(old)
        bound = config['geometry_ledgers'][index-1]
        previous = read_bound_json(bound['path'], bound['sha256'])['model_full_fov_proposal']
        if ledger != previous:
            raise ValueError('APPROVED_FULL_FOV_GEOMETRY_DRIFT')
        native = np.load(m['native_hu_volume_path'], mmap_mode='r', allow_pickle=False)
        oriented = native.transpose(old['permutation'])
        for axis, flip in enumerate(old['flips']):
            if flip: oriented = np.flip(oriented, axis=axis)
        value = stream_area_input(oriented, check=guard.check)
        probes = area_probes(oriented, value, guard.check)
        del oriented, native
        guard.check()
        sha = artifacts.array(f'case_{index}_input.npy', value)
        ledger.update(case_index=index, input_file_sha256=sha,
                      input_content_sha256=hashlib.sha256(value.tobytes()).hexdigest(),
                      native_volume_sha256=m['native_hu_volume_sha256'],
                      case_manifest_sha256=case['case_manifest_sha256'],
                      data_delivery_sha256=config['data_delivery_sha256'],
                      preprocessing_source_sha256=file_sha(__file__),
                      input_range=[float(value.min()), float(value.max())],
                      permutation=old['permutation'], flips=old['flips'],
                      native_padding='UNKNOWN', independent_area_probes=probes,
                      preprocessing_seconds=time.monotonic()-started)
        ledger_sha = artifacts.json(f'case_{index}_ledger.json', ledger)
        prepared.append(dict(case_index=index, input_sha256=sha, ledger_sha256=ledger_sha,
                             preprocessing_seconds=ledger['preprocessing_seconds']))
        del value
    guard.check()
    artifacts.json('all_inputs_frozen.json', {'cases': prepared, 'actual_forward': 0,
                                             'consumer_status': receipt['status']})
    return prepared


def device_runs(torch, adapter, x, device, index, config, artifacts, guard, journal, telemetry):
    """Exactly warmup1 + timed3; never auto-retry. Save each completed output."""
    telemetry.phase = f'case_{index}_{device}'
    outputs, timing, readback = [], [], []
    observations, wrong = Counter(), []
    hooks = []
    features = device_input = None
    guard.check(); before = time.monotonic()
    try:
        adapter.to(device); device_input = x.to(device)
        if device == 'mps': torch.mps.synchronize()
        transfer_seconds = time.monotonic()-before
        if device == 'mps':
            def audit(module, inputs, output):
                observations[type(module).__name__] += 1
                for tensor in [*inputs, output]:
                    if isinstance(tensor, torch.Tensor) and tensor.device.type != 'mps':
                        wrong.append(type(module).__name__)
            for module in adapter.modules():
                if isinstance(module, (torch.nn.Conv3d, torch.nn.BatchNorm3d, torch.nn.ReLU)):
                    hooks.append(module.register_forward_hook(audit))
        with torch.inference_mode():
            for repeat in range(4):
                journal.reserve(index, device, repeat)
                if device == 'mps': torch.mps.synchronize()
                guard.check(); before = time.monotonic()
                features = adapter.extract(device_input)
                if device == 'mps': torch.mps.synchronize()
                elapsed = time.monotonic()-before
                timing.append(elapsed)
                journal.event('NETWORK_RETURNED', inference_seconds=elapsed,
                              feature_shape=list(features.shape))
                guard.check()
                if list(features.shape) != config['expected_last_stage_shape']:
                    raise ValueError('UNEXPECTED_SPATIAL_FEATURE_SHAPE')
                if repeat == 0:
                    for hook in hooks: hook.remove()
                    hooks.clear()
                    if wrong: raise RuntimeError('CPU_MODULE_TENSOR_INSIDE_MPS')
                else:
                    before = time.monotonic()
                    array = features.cpu().numpy().copy()
                    if device == 'mps': torch.mps.synchronize()
                    readback.append(time.monotonic()-before)
                    guard.check()
                    artifacts.array(f'case_{index}_{device}_features_{repeat}.npy', array)
                    outputs.append(array)
                features = None
        return outputs, dict(transfer_seconds=transfer_seconds, warmup_seconds=timing[:1],
                             inference_seconds=timing[1:], readback_seconds=readback,
                             module_observations=dict(observations), wrong_module_devices=wrong)
    finally:
        for hook in hooks: hook.remove()
        features = device_input = None


def execute_work(torch, args, config, artifacts, guard, journal, telemetry, result, held):
    from .encoder import load_ctfm_local
    prepared = prepare_inputs(args.data, config, artifacts, guard, telemetry)
    result['prepared'] = prepared
    adapter = None
    for entry in prepared:
        index = entry['case_index']; guard.begin_case(f'case_{index}')
        case_start = time.monotonic()
        item = dict(case_index=index, status='NOT RUN', loading_seconds=0.)
        result['cases'].append(item)
        if adapter is None:
            telemetry.phase = 'model_loading'; guard.check(); before = time.monotonic()
            adapter = load_ctfm_local(args.weights, config['checkpoint_sha256'])
            held['adapter'] = adapter
            item['loading_seconds'] = time.monotonic()-before
            result['feature_lattice'] = lattice_from_model(adapter.encoder)
            held['count_hook'] = adapter.encoder.register_forward_pre_hook(journal.network_entry)
        guard.check()
        input_path = artifacts.directory/f'case_{index}_input.npy'
        if file_sha(input_path) != entry['input_sha256']: raise ValueError('INPUT_DRIFT')
        array = np.load(input_path, allow_pickle=False)
        if array.dtype != np.float32 or list(array.shape) != config['shape'] or not np.isfinite(array).all():
            raise ValueError('FINITE_FP32_INPUT_REQUIRED')
        x = torch.from_numpy(array)
        cpu, item['cpu'] = device_runs(torch, adapter, x, 'cpu', index, config, artifacts, guard, journal, telemetry)
        mps, item['mps'] = device_runs(torch, adapter, x, 'mps', index, config, artifacts, guard, journal, telemetry)
        guard.check()
        item['comparisons'] = [full_compare(a, b, config['tolerance']) for a, b in zip(cpu, mps)]
        item['repeat_max_difference'] = {dev: max(float(np.max(np.abs(v-values[0]))) for v in values)
                                         for dev, values in [('cpu', cpu), ('mps', mps)]}
        # A representation is an engineering asset; it is not logits or a class map.
        artifacts.array(f'case_{index}_mps_gap512.npy', mps[0].mean(axis=(2, 3, 4)))
        item['status'] = 'PASS' if all(c['status'] == 'PASS' for c in item['comparisons']) else 'FAIL'
        item['case_seconds_including_loading'] = time.monotonic()-case_start
        artifacts.json(f'case_{index}_result.json', item)
        if item['status'] != 'PASS': raise ValueError('FULL_OUTPUT_NUMERIC_TOLERANCE_FAILED')
        guard.check(); guard.end_case()
        del cpu, mps, x, array
    guard.check()
    if journal.actual != 24 or journal.device_counts != {'cpu': 12, 'mps': 12}:
        raise RuntimeError('INCOMPLETE_FIXED_CALL_SCHEDULE')


def cleanup_device(mps, telemetry, baseline):
    """Actual-child cleanup only; parent still verifies process exit and pressure."""
    before = time.monotonic(); telemetry.phase = 'cleanup'
    try:
        gc.collect(); mps.synchronize(); mps.empty_cache(); mps.synchronize()
        final = telemetry()
        recovered = (final['tensor_bytes'] <= baseline['tensor_bytes']
                     and final['driver_bytes'] < PRE_STOP and final['tensor_bytes'] < PRE_STOP)
        return dict(device_recovered=recovered, final_actual_child_memory=final,
                    criterion='successful sync/empty_cache/sync; tensor<=startup baseline; driver and tensor<5GiB',
                    cleanup_seconds=time.monotonic()-before, error=None)
    except Exception as exc:
        return dict(device_recovered=False, final_actual_child_memory=None,
                    cleanup_seconds=time.monotonic()-before, error=type(exc).__name__)


def run(args):
    os.umask(0o077)
    config, overlay, spec = validate_bindings(args)
    if 'torch' in sys.modules: raise RuntimeError('TORCH_IMPORTED_BEFORE_STRICT_ENV')
    os.environ.update(PYTORCH_ENABLE_MPS_FALLBACK='0', PYTORCH_MPS_FAST_MATH='0',
                      OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    shared = load_supervisor(overlay)
    # Real import is allowed before guard, within the parent's fixed 15s startup.
    import torch
    telemetry = ActualMpsTelemetry(torch.mps)
    guard = shared.ChildGuard.from_environment(mps_driver=telemetry)
    artifacts = PrivateArtifacts(args.output, config['task_output_limit_bytes'])
    journal = CallJournal(guard, args.output/'calls.jsonl')
    result = dict(schema='CTFM_FOV128_WAVE1_RESULT_V1', status='FAIL', cases=[],
                  scientific_config_sha256=CONFIG_SHA, resource_revision_sha256=REVISION_SHA,
                  overlay_sha256=args.overlay_sha, supervisor_sha256=args.supervisor_sha,
                  job_id=spec['job_id'], command=[sys.executable, *sys.argv],
                  pid=os.getpid(), checkpoint_sha256=config['checkpoint_sha256'],
                  model_revision=config['model_revision'], F0='BLOCKED', head_training='NOT RUN',
                  remote_RTX3090='PAUSED', clinical_accuracy=None,
                  strict_environment={k: os.environ[k] for k in config['strict_environment']},
                  cpu_threads=1, seed=17, torch_version=torch.__version__,
                  resource_semantics='monitored targets with reserve; sampled peaks, accepted gaps and stop latency',
                  preprocessing_charged_to_global_budget=True,
                  case_budget_scope='model loading for first case, transfer, eight attempts, validation and writes',
                  started_monotonic=time.monotonic())
    held = {}; baseline = None; terminal = 'FAILED'; caught = []
    try:
        guard.check()
        with guard.ledger() as ledger:
            if ledger['forward'] or ledger['backward'] or ledger['cases']:
                raise RuntimeError('EXPERIMENT_ALREADY_STARTED_NO_RETRY_OR_COUNTER_RESET')
        result.update(mps_is_built=torch.backends.mps.is_built(), mps_is_available=torch.backends.mps.is_available())
        if not result['mps_is_built'] or not result['mps_is_available']:
            raise RuntimeError('MPS_UNAVAILABLE')
        baseline = telemetry(); result['mps_startup_memory'] = baseline
        result['allocator'] = configure_allocator(torch.mps)
        torch.set_num_threads(1); torch.set_num_interop_threads(1); torch.manual_seed(17)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            warnings.filterwarnings('error', message='.*fallback.*')
            execute_work(torch, args, config, artifacts, guard, journal, telemetry, result, held)
        if any('fallback' in str(w.message).lower() for w in caught):
            raise RuntimeError('FALLBACK_WARNING')
        result['status'] = 'PASS'; terminal = 'SUCCESS'
    except Exception as exc:
        result['failure'] = {'type': type(exc).__name__, 'reason': str(exc)}
        terminal = 'PARTIAL_BUDGET' if isinstance(exc, shared.StopWork) else 'FAILED'
    # Exit the except suite before cleanup so tracebacks do not retain GPU tensors.
    result['warnings'] = [str(w.message) for w in caught]
    result['adapter_internal_queries'] = held['adapter'].actual_queries if 'adapter' in held else 0
    if 'count_hook' in held: held['count_hook'].remove()
    held.clear()
    cleanup = cleanup_device(torch.mps, telemetry, baseline) if baseline is not None else {
        'device_recovered': False, 'final_actual_child_memory': None, 'error': 'STARTUP_BASELINE_UNAVAILABLE'}
    result.update(cleanup=cleanup, actual_forward=journal.actual, actual_backward=0,
                  adapter_attempts=journal.adapter_attempts, actual_by_device=dict(journal.device_counts),
                  process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  compute_child_elapsed_seconds=time.monotonic()-result['started_monotonic'])
    with guard.ledger() as ledger: result['durable_counters'] = dict(ledger)
    if not cleanup['device_recovered']:
        result['status'] = 'FAIL'; terminal = 'FAILED'
    result['states'] = {
        'MPS_COMPATIBILITY': 'PASS' if result['status'] == 'PASS' else ('FAIL' if journal.device_counts['mps'] else 'NOT RUN'),
        'RESOURCE_BENCHMARK': 'PASS' if result['status'] == 'PASS' else 'FAIL',
        'THREE_CASE_SMOKE': 'BLOCKED',  # separate DATA geometry QA must bind these new assets
        'F0': 'BLOCKED',
    }
    result['three_case_engineering_execution'] = 'PASS' if result['status'] == 'PASS' else 'FAIL'
    result['independent_new128_geometry_QA'] = 'NOT RUN'
    artifacts.json('result.json', result)
    guard.complete(status=terminal, reason=result.get('failure', {}).get('reason'),
                   device_recovered=cleanup['device_recovered'], actual_forward=journal.actual, actual_backward=0)
    # Shared completion is authoritative for slot semantics; local details stay private.
    artifacts.json('mps_telemetry.json', telemetry.report())
    artifacts.json('manifest.json', {'assets_sha256': dict(artifacts.assets), 'status': result['status'],
                                    'supervisor_terminal': terminal, 'actual_forward': journal.actual})
    print(json.dumps({'status': result['status'], 'actual_forward': journal.actual,
                      'device_recovered': cleanup['device_recovered'], 'result_sha256': file_sha(args.output/'result.json')}))
    return 0 if terminal == 'SUCCESS' else 2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('config', 'approval', 'revision', 'overlay', 'data', 'weights', 'output'):
        p.add_argument('--'+key, type=Path, required=True)
    for key in ('overlay-sha', 'supervisor-sha'):
        p.add_argument('--'+key, required=True)
    return run(p.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
