"""Minimal immutable dependency snapshot and tracked shared device slot.

Only declared dependencies are covered; callers must enumerate their actual
modules/configs and package versions. No model, process kill or queue daemon.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import types

from . import hospital_runtime
from .artifacts import canonical_json, persist_run, reconcile_run, sha256, _safe_name
from .coordinator_writer import process_identity, write_new


def dependency_snapshot(root, run_id, entries, packages):
    artifacts = {}; records = []
    for entry in entries:
        name = _safe_name(entry['name'])
        if name in artifacts or name == 'dependency_lock.json':
            raise ValueError('DUPLICATE_OR_RESERVED_DEPENDENCY')
        repo = Path(entry['repo']).resolve()
        relative = Path(entry['relative_path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('DEPENDENCY_PATH_MUST_BE_REPO_RELATIVE')
        commit = entry['commit']
        if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
            raise ValueError('FULL_COMMIT_REQUIRED')
        path = repo / relative
        raw = path.read_bytes()
        if sha256(raw) != entry['sha256']:
            raise ValueError('DECLARED_DEPENDENCY_DRIFT')
        committed = subprocess.check_output(['git', 'show', f'{commit}:{relative.as_posix()}'], cwd=repo)
        dirty = raw != committed
        if dirty and not entry.get('allow_dirty_bytes', False):
            raise ValueError('DIRTY_DEPENDENCY_NOT_EXPLICITLY_LOCKED')
        artifacts[name] = raw
        records.append(dict(entry, source_dirty=dirty, committed_blob_sha256=sha256(committed)))
    if not records:
        raise ValueError('DEPENDENCIES_REQUIRED')
    for package, version in packages.items():
        if importlib.metadata.version(package) != version:
            raise ValueError('PACKAGE_VERSION_DRIFT')
    manifest = {'schema': 'EPI-NEXT-DEPENDENCY-LOCK-1', 'entries': records,
                'packages': packages, 'python_version':platform.python_version(),
                'scope': 'DECLARED_DEPENDENCIES_ONLY'}
    artifacts['dependency_lock.json'] = canonical_json(manifest)
    persist_run(Path(root), run_id, artifacts)
    return sha256(artifacts['dependency_lock.json'])


def verify_dependencies(root, expected_sha):
    root = Path(root)
    if reconcile_run(root.parent, root.name)['state'] != 'COMMITTED':
        raise RuntimeError('DEPENDENCY_SNAPSHOT_NOT_COMMITTED')
    raw = (root / 'dependency_lock.json').read_bytes()
    if sha256(raw) != expected_sha:
        raise ValueError('DEPENDENCY_LOCK_SHA_MISMATCH')
    manifest = json.loads(raw)
    if manifest.get('python_version',platform.python_version()) != platform.python_version():
        raise ValueError('PYTHON_VERSION_DRIFT')
    for entry in manifest['entries']:
        if sha256((root / entry['name']).read_bytes()) != entry['sha256']:
            raise ValueError('SNAPSHOT_DEPENDENCY_DRIFT')
        # Refuse changed source when replay claims the same live dependency set.
        path = Path(entry['repo']) / entry['relative_path']
        if entry.get('live_replay_check', True) and sha256(path.read_bytes()) != entry['sha256']:
            raise ValueError('LIVE_DEPENDENCY_DRIFT')
    for name, version in manifest['packages'].items():
        if importlib.metadata.version(name) != version:
            raise ValueError('PACKAGE_VERSION_DRIFT')
    return manifest


def load_locked_module(root, expected_sha, filename, module_name):
    manifest = verify_dependencies(root, expected_sha)
    if filename not in {e['name'] for e in manifest['entries']} or not filename.endswith('.py'):
        raise ValueError('UNDECLARED_PYTHON_MODULE')
    raw = (Path(root) / filename).read_bytes()
    entry = next(e for e in manifest['entries'] if e['name'] == filename)
    if sha256(raw) != entry['sha256']:
        raise ValueError('MODULE_CHANGED_BEFORE_COMPILE')
    module = types.ModuleType(module_name)
    module.__file__ = str(Path(root) / filename)
    module.__package__ = module_name.rpartition('.')[0]
    if module_name in sys.modules:
        raise ValueError('MODULE_NAME_ALREADY_LOADED')
    sys.modules[module_name] = module
    try:
        exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    except BaseException:
        del sys.modules[module_name]
        raise
    return module


@dataclass
class DeviceSlot:
    directory: Path
    record: dict
    children: list = field(default_factory=list)

    def track_child(self, process):
        if not isinstance(process, subprocess.Popen) or process.poll() is not None:
            raise ValueError('LIVE_TASK_OWNED_CHILD_REQUIRED')
        identity = process_identity(process.pid)
        parent = subprocess.check_output(['ps','-p',str(process.pid),'-o','ppid='],text=True).strip()
        if parent != str(os.getpid()):
            raise ValueError('CHILD_NOT_OWNED_BY_SLOT_PROCESS')
        write_new(self.directory / f'child-{process.pid}.json', canonical_json(identity))
        self.children.append((process, identity))

    def complete(self, receipt_path, receipt_sha, *, child_pids=()):
        # Caller must not release admission while confirmed compute children live.
        if child_pids:
            raise RuntimeError('CHILD_COMPLETION_MUST_BE_CONFIRMED_BEFORE_RELEASE')
        if any(process.poll() is None for process, _ in self.children):
            raise RuntimeError('TASK_CHILD_STILL_RUNNING')
        raw = Path(receipt_path).read_bytes()
        if sha256(raw) != receipt_sha:
            raise ValueError('COMPUTE_RECEIPT_HASH_MISMATCH')
        receipt = json.loads(raw)
        if (receipt.get('job_id') != self.record['job_id']
                or receipt.get('status') not in {'SUCCESS','NO_RELIABLE_RESPONSE','PARTIAL_BUDGET','FAILED','BLOCKED','NOT RUN'}):
            raise ValueError('TERMINAL_JOB_RECEIPT_REQUIRED')
        write_new(self.directory / 'finished.json', canonical_json({
            'receipt_path': str(Path(receipt_path).absolute()), 'receipt_sha256': receipt_sha,
            'job_id': self.record['job_id'], 'status': receipt['status'],
            'process_identity': process_identity(),
            'children': [dict(identity, exit_code=process.returncode) for process, identity in self.children]}))


def validate_administrative_recovery(queue_root, task_key, decision_path=None, decision_sha=None):
    """Consume an explicit chief-published decision; never repair the old slot.

    SHA binding is integrity, not authentication against a same-UID writer.
    Scientific authorization and dispatch remain separate chief responsibilities.
    """
    if decision_path is None and decision_sha is None:
        return None
    def read_bound(path, digest):
        path = Path(path)
        if not path.is_absolute() or any(part.is_symlink() for part in (path, *path.parents)):
            raise ValueError('RECOVERY_REFERENCE_PATH_UNSAFE')
        raw = path.read_bytes()
        if sha256(raw) != digest:
            raise ValueError('RECOVERY_REFERENCE_SHA_MISMATCH')
        return json.loads(raw)
    decision = read_bound(decision_path, decision_sha)
    if (decision.get('schema') != 'EPI-NEXT-ADMINISTRATIVE-RECOVERY-1'
            or decision.get('status') != 'APPROVED_ADMINISTRATIVE_RECOVERY'
            or decision.get('queue_root') != str(Path(queue_root).absolute())
            or decision.get('historical_status_unchanged') is not True
            or decision.get('model_authorization_granted') is not False):
        raise ValueError('EXPLICIT_ADMINISTRATIVE_RECOVERY_REQUIRED')
    scope = decision['scope']
    approval = read_bound(**decision['approval_reference'])
    if (approval.get('schema') != 'EPI-NEXT-OWNER-RECOVERY-APPROVAL-1'
            or approval.get('status') != 'EXPLICIT_ADMINISTRATIVE_RECOVERY_APPROVED'
            or approval.get('principal') != '钟佳桦'
            or approval.get('scope_sha256') != sha256(canonical_json(scope))):
        raise ValueError('INDEPENDENT_OWNER_APPROVAL_REQUIRED')
    if task_key not in scope['allowed_next_task_keys'] or task_key == scope['old_task_key']:
        raise ValueError('RECOVERY_NEXT_TASK_NOT_APPROVED')
    job = _safe_name(scope['old_job_id'])
    slot = Path(queue_root) / 'slots' / job
    start = read_bound(slot / 'started.json', scope['started_sha256'])
    receipt = read_bound(**scope['supervisor_reference'])
    review = read_bound(**scope['r0_reference'])
    if (start['job_id'] != job or start['task_key'] != scope['old_task_key']
            or receipt['job_id'] != job or receipt['status'] not in {'BLOCKED', 'FAILED'}
            or receipt.get('slot_completed') is not False
            or (slot / 'finished.json').exists()
            or review.get('status') != 'REVIEW_CONDITIONS_MET_NOT_DEVICE_RECOVERY_PROOF'
            or review.get('schema') != 'EPI_NEXT_R0_ONCE_READONLY'
            or review.get('samples') != 61
            or set(review.get('checks', {})) != {'61_samples_no_missing', 'timing_bounds',
                'free_all_at_least20', 'swap_delta_strict_less1GiB', 'no_registered_identity_rows'}
            or any(value is not True for value in review['checks'].values())
            or review.get('unknown_slot_changed') is not False
            or review.get('finished_exists_after') is not False
            or review.get('model_calls') != 0
            or review.get('no_gpu_probe') is not True or review.get('no_process_signals') is not True):
        raise ValueError('RECOVERY_ORIGINAL_EVIDENCE_INVALID')
    for name, digest in review['raw_sha256'].items():
        if Path(name).name != name:
            raise ValueError('RECOVERY_RAW_REFERENCE_UNSAFE')
        path = Path(scope['r0_reference']['path']).parent / name
        if path.is_symlink() or sha256(path.read_bytes()) != digest:
            raise ValueError('RECOVERY_RAW_SHA_MISMATCH')
    return {'old_job_id': job, 'decision_path': str(decision_path),
            'decision_sha256': decision_sha, 'scope_sha256': approval['scope_sha256']}


@contextmanager
def tracked_device_slot(device, *, owner, job_id, task_key, budget,
                        dependency_root, dependency_sha, recovery_decision_path=None, recovery_decision_sha=None):
    job_id = _safe_name(job_id); task_key = _safe_name(task_key)
    for field in ('max_model_calls','max_seconds','max_rss_bytes'):
        value = budget[field]
        minimum_ok=value>=0 if field=='max_model_calls' and isinstance(value,(int,float)) else isinstance(value,(int,float)) and value>0
        if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or not minimum_ok:
            raise ValueError('POSITIVE_FINITE_RESOURCE_LIMIT_REQUIRED')
    if type(budget['max_model_calls']) is not int or type(budget['max_rss_bytes']) is not int:
        raise ValueError('INTEGER_CALL_AND_MEMORY_LIMIT_REQUIRED')
    if device == 'mps' and (type(budget.get('max_mps_driver_bytes')) is not int or budget['max_mps_driver_bytes'] <= 0):
        raise ValueError('MPS_MEMORY_LIMIT_REQUIRED')
    with hospital_runtime.device_lease(device, owner=owner):
        verify_dependencies(dependency_root, dependency_sha)
        recovery = validate_administrative_recovery(hospital_runtime.QUEUE_ROOT, task_key,
                                                    recovery_decision_path, recovery_decision_sha)
        slots = hospital_runtime.QUEUE_ROOT / 'slots'
        slots.mkdir(mode=0o700, exist_ok=True)
        for directory in slots.iterdir():
            if not directory.is_dir() or directory.is_symlink():
                raise RuntimeError('UNRECOGNIZED_SLOT_RECONCILE_REQUIRED')
            start = json.loads((directory / 'started.json').read_bytes())
            if start['task_key'] == task_key:
                raise RuntimeError('WAVE1_DUPLICATE_TASK_SCOPE_NO_COUNTER_RESET')
            if (not (directory / 'finished.json').exists()
                    and (recovery is None or directory.name != recovery['old_job_id'])):
                raise RuntimeError('PRIOR_SLOT_UNKNOWN_RECONCILE_REQUIRED')
            if (directory / 'finished.json').exists():
                terminal = json.loads((directory / 'finished.json').read_bytes())
                if sha256(Path(terminal['receipt_path']).read_bytes()) != terminal['receipt_sha256']:
                    raise RuntimeError('PRIOR_SLOT_RECEIPT_CHANGED')
        directory = slots / job_id
        directory.mkdir(mode=0o700)  # exclusive job identity, including completed jobs
        record = dict(process_identity(), job_id=job_id, task_key=task_key, owner=owner,
                      device=device, resource_limits=budget, dependency_sha256=dependency_sha,
                      dependency_root=str(Path(dependency_root).absolute()))
        if recovery is not None:
            record['administrative_recovery'] = recovery
        write_new(directory / 'started.json', canonical_json(record))
        yield DeviceSlot(directory, record)
        # Missing terminal receipt deliberately remains UNKNOWN even after flock
        # release/process exit. No PID recycling inference or automatic retry.
