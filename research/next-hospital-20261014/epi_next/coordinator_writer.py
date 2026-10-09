"""Opt-in coordinator-only state writer. Never initializes or restores state.

Policy is pinned by SHA and caller UID/identity. These are local process guards,
not authentication between chats sharing an OS account. The chief installs and
invokes the tool; no project state path is embedded in this module.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from .artifacts import canonical_json, sha256


PROTECTED_ROOTS = {'schema', 'owner', 'ownership', 'private',
                   'public_patient_identifiers_allowed', 'use_permissions',
                   'delegation_policy', 'data', 'budgets', 'resources',
                   'first_real_slice_lock', 'update_rule', 'status_vocabulary'}
PERMISSION_WORDS = re.compile(r'permission|authoriz|allowlist|approval|budget|grant', re.I)


def process_identity(pid=None):
    pid = os.getpid() if pid is None else pid
    start = subprocess.check_output(['ps', '-p', str(pid), '-o', 'lstart='], text=True).strip()
    if not start:
        raise RuntimeError('PROCESS_IDENTITY_UNAVAILABLE')
    return {'pid': pid, 'process_start': start, 'uid': os.geteuid()}


def fsync_dir(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_new(path, raw):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    fsync_dir(path.parent)


@contextmanager
def locked_audit(state):
    audit = state.parent / (state.name + '.writer')
    audit.mkdir(mode=0o700, exist_ok=True)
    if audit.is_symlink():
        raise RuntimeError('UNSAFE_AUDIT_PATH')
    descriptor = os.open(audit / 'writer.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a+b') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('WRITER_BUSY') from exc
        try:
            yield audit
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def read_events(audit):
    path = audit / 'events.jsonl'
    if not path.exists():
        return []
    if path.is_symlink():
        raise RuntimeError('UNSAFE_EVENTS_PATH')
    events = []
    previous = None
    for line in path.read_bytes().splitlines():
        event = json.loads(line)
        digest = event.pop('event_sha256')
        if event['previous_event_sha256'] != previous or sha256(canonical_json(event)) != digest:
            raise RuntimeError('EVENT_CHAIN_CORRUPT')
        event['event_sha256'] = digest
        snapshot = audit / event['snapshot']
        if snapshot.parent != audit or snapshot.is_symlink():
            raise RuntimeError('UNSAFE_SNAPSHOT_PATH')
        if snapshot.exists():
            if sha256(snapshot.read_bytes()) != event['next_hash']:
                raise RuntimeError('SNAPSHOT_HASH_MISMATCH')
        elif event['phase'] == 'COMMITTED':
            raise RuntimeError('COMMITTED_SNAPSHOT_MISSING')
        events.append(event); previous = digest
    return events


def append_event(audit, events, event):
    event = dict(event, previous_event_sha256=events[-1]['event_sha256'] if events else None)
    event['event_sha256'] = sha256(canonical_json(event))
    raw = json.dumps(event, sort_keys=True, allow_nan=False).encode() + b'\n'
    descriptor = os.open(audit / 'events.jsonl', os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'ab') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    fsync_dir(audit)
    events.append(event)


def pending_events(events):
    committed = {e['task_key'] for e in events if e['phase'] == 'COMMITTED'}
    return [e for e in events if e['phase'] == 'PREPARED' and e['task_key'] not in committed]


def permission_fields(value, prefix=()):
    result = {}
    if isinstance(value, dict):
        for key, item in value.items():
            path = prefix + (key,)
            if PERMISSION_WORDS.search(key):
                result[path] = item
            result.update(permission_fields(item, path))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            result.update(permission_fields(item, prefix + (str(i),)))
    return result


def apply_patch(current, patch, policy):
    result = json.loads(json.dumps(current))
    if not patch or not isinstance(patch, dict):
        raise ValueError('NONEMPTY_POINTER_PATCH_REQUIRED')
    for pointer, value in patch.items():
        if pointer not in policy['allowed_pointers'] or not pointer.startswith('/'):
            raise PermissionError('PATCH_POINTER_NOT_ALLOWED')
        keys = [k.replace('~1', '/').replace('~0', '~') for k in pointer[1:].split('/')]
        if (keys[0] in PROTECTED_ROOTS | {'revision', 'previous_revision_sha256', 'updated_at'}
                or any(PERMISSION_WORDS.search(k) for k in keys)):
            raise PermissionError('PERMISSION_OR_RESERVED_FIELD_IMMUTABLE')
        target = result
        for key in keys[:-1]:
            target = target[key]
            if not isinstance(target, dict):
                raise ValueError('PATCH_PARENT_MUST_EXIST_AS_OBJECT')
        target[keys[-1]] = value
    if permission_fields(result) != permission_fields(current):
        raise PermissionError('NESTED_PERMISSION_CHANGE_REFUSED')
    canonical_json(result)  # reject NaN/non-JSON data before journal writes
    return result


def reconcile(state):
    state = Path(state).absolute()
    if state.is_symlink():
        raise RuntimeError('UNSAFE_STATE_PATH')
    with locked_audit(state) as audit:
        raw = state.read_bytes(); current = json.loads(raw)
        events = read_events(audit); pending = pending_events(events)
        digest = sha256(raw)
        status = 'CONSISTENT'
        if pending:
            last = pending[-1]
            status = ('APPLIED_PENDING_EVENT' if digest == last['next_hash'] else
                      'NOT_APPLIED_RECONCILE_REQUIRED' if digest == last['previous_hash'] else
                      'EXTERNAL_STATE_CHANGE')
        elif events and digest != events[-1]['next_hash']:
            status = 'EXTERNAL_STATE_CHANGE'
        return {'status': status, 'revision': current['revision'], 'sha256': digest,
                'pending_task_keys': [e['task_key'] for e in pending]}


def update(state, policy_path, policy_sha, expected_revision, expected_sha,
           writer_id, task_key, reason, patch, *, _checkpoint=lambda phase: None):
    """Checkpoint hook is for isolated crash tests, never required by CLI.

    Interrupted PREPARED transactions fence further writes. Reconciliation is
    observational; no rollback/retry/finalization of an unknown result occurs.
    """
    state = Path(state).absolute()
    policy_raw = Path(policy_path).read_bytes()
    if sha256(policy_raw) != policy_sha:
        raise PermissionError('POLICY_SHA_MISMATCH')
    policy = json.loads(policy_raw)
    identity = process_identity()
    if (policy['writer_id'] != writer_id or policy['uid'] != identity['uid']
            or Path(policy['state_path']).absolute() != state or state.is_symlink()):
        raise PermissionError('COORDINATOR_IDENTITY_OR_TARGET_MISMATCH')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,159}', task_key) or not reason.strip():
        raise ValueError('TASK_KEY_AND_REASON_REQUIRED')
    with locked_audit(state) as audit:
        raw = state.read_bytes(); current = json.loads(raw); digest = sha256(raw)
        events = read_events(audit)
        if pending_events(events):
            raise RuntimeError('UNKNOWN_TRANSACTION_RECONCILE_REQUIRED')
        if any(e['task_key'] == task_key for e in events):
            raise RuntimeError('DUPLICATE_TASK_KEY')
        if events and digest != events[-1]['next_hash']:
            raise RuntimeError('EXTERNAL_STATE_CHANGE_RECONCILE_REQUIRED')
        if (type(current['revision']) is not int or type(expected_revision) is not int
                or current['revision'] != expected_revision or digest != expected_sha):
            raise RuntimeError('STALE_REVISION_OR_SHA')
        next_state = apply_patch(current, patch, policy)
        next_state.update(revision=expected_revision + 1, previous_revision_sha256=digest,
                          updated_at=datetime.now(timezone.utc).isoformat())
        next_raw = canonical_json(next_state); next_hash = sha256(next_raw)
        snapshot_name = f'revision-{next_state["revision"]}-{next_hash}.json'
        event = dict(identity, writer_id=writer_id, task_key=task_key, reason=reason,
                     policy_sha256=policy_sha, previous_hash=digest, next_hash=next_hash,
                     previous_revision=expected_revision, next_revision=expected_revision + 1,
                     snapshot=snapshot_name, timestamp=next_state['updated_at'])
        append_event(audit, events, dict(event, phase='PREPARED'))
        _checkpoint('prepared')
        # Preserve exact old bytes too; existence is accepted only if identical.
        old_snapshot = audit / f'revision-{expected_revision}-{digest}.json'
        if old_snapshot.exists():
            if old_snapshot.is_symlink() or old_snapshot.read_bytes() != raw:
                raise RuntimeError('OLD_SNAPSHOT_CONFLICT')
        else:
            write_new(old_snapshot, raw)
        write_new(audit / snapshot_name, next_raw)
        _checkpoint('snapshot')
        descriptor, name = tempfile.mkstemp(prefix='.state-pending-', dir=state.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(next_raw); stream.flush(); os.fsync(stream.fileno())
        _checkpoint('temporary')
        os.replace(temporary, state); fsync_dir(state.parent)
        _checkpoint('replaced')
        append_event(audit, events, dict(event, phase='COMMITTED'))
        return {'status': 'COMMITTED', 'revision': expected_revision + 1,
                'sha256': next_hash, 'snapshot_path': str(audit / snapshot_name)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('reconcile'); check.add_argument('--state', type=Path, required=True)
    write = sub.add_parser('update')
    for name in ('state', 'policy', 'patch'):
        write.add_argument('--' + name, type=Path, required=True)
    for name in ('policy-sha', 'expected-sha', 'writer-id', 'task-key', 'reason'):
        write.add_argument('--' + name, required=True)
    write.add_argument('--expected-revision', type=int, required=True)
    args = parser.parse_args()
    if args.command == 'reconcile':
        result = reconcile(args.state)
    else:
        result = update(args.state, args.policy, args.policy_sha, args.expected_revision,
                        args.expected_sha, args.writer_id, args.task_key, args.reason,
                        json.loads(args.patch.read_bytes()))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
