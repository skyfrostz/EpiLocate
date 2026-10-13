"""Freeze eight existing supervisor modules; two narrow v3 lineage changes.

No queue access, models, GPU probe or authority file creation. Existing v3
snapshot stays immutable. Requires committed source and a fresh local output.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    base = repo / 'research/next-hospital-20261014'
    old = base / '.local/phase2/wave1-supervisor-c9f5369-recovery-v3'
    out = args.output.resolve()
    if not out.is_relative_to(base / '.local/phase2') or out.exists():
        parser.error('fresh integration .local/phase2 directory required')
    commit = args.source_commit
    if len(commit) != 40:
        parser.error('full source commit required')
    sys.path.insert(0, str(old))
    prefix = 'epinext_wave1_supervisor_recovery_v3'
    names = ('wave1_supervisor', 'execution_lock', 'coordinator_writer', 'artifacts',
             'hospital_runtime', 'hospital_contract', 'contracts', 'geometry')
    old_modules = {name: importlib.import_module(prefix + '.' + name) for name in names}
    previous = json.loads((old / 'dependencies/EPI-NEXT-shared-supervisor-recovery-v3/dependency_lock.json').read_text())
    previous_hashes = {e['name']: e['sha256'] for e in previous['entries']}
    entries = []
    for name in names:
        if name in {'execution_lock', 'wave1_supervisor'}:
            relative = 'research/next-hospital-20261014/runtime/recovery_chain_v1/' + name + '.py'
            source_commit = commit
        else:
            relative = 'research/next-hospital-20261014/epi_next/' + name + '.py'
            source_commit = 'c9f5369b7384f4e132365616f8b6f64b624dbea2'
        path = repo / relative
        committed = subprocess.check_output(['git', 'show', source_commit + ':' + relative], cwd=repo)
        if committed != path.read_bytes():
            raise ValueError('uncommitted dependency: ' + name)
        if digest(Path(old_modules[name].__file__)) != previous_hashes[name + '.py']:
            raise ValueError('old v3 snapshot drift')
        entries.append(dict(name=name + '.py', repo=str(repo), relative_path=relative,
            commit=source_commit, sha256=digest(path), live_replay_check=True))
    dependency_root = out / 'dependencies'
    lock_sha = old_modules['execution_lock'].dependency_snapshot(dependency_root,
        'EPI-NEXT-recovery-chain-v1', entries, previous['packages'])
    dependency_root /= 'EPI-NEXT-recovery-chain-v1'
    package_name = 'epinext_wave1_recovery_chain_v1'
    package = out / package_name
    package.mkdir()
    (package / '__init__.py').write_text('')
    for name in names:
        shutil.copyfile(dependency_root / (name + '.py'), package / (name + '.py'))
    sys.path.insert(0, str(out))
    loaded = {name: importlib.import_module(package_name + '.' + name) for name in names}
    loaded['wave1_supervisor'].verify_loaded_bundle(dependency_root, lock_sha)
    receipt = dict(schema='EPI_NEXT_RECOVERY_CHAIN_BUNDLE_V1', source_git_sha=commit,
        base_source_git_sha='c9f5369b7384f4e132365616f8b6f64b624dbea2', package=package_name,
        bundle_root=str(out), dependency_root=str(dependency_root), dependency_sha256=lock_sha,
        modules={name: dict(path=str(package / (name + '.py')),
            sha256=digest(package / (name + '.py'))) for name in names},
        initializer_sha256=digest(package / '__init__.py'), scope='BOUND_RECOVERY_CHAIN_AND_R1_ONLY',
        io_lock_change=False, queue_writes=0, model_calls=0, gpu_probes=0)
    path = out / 'bundle_receipt.json'
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    for path in out.rglob('*'):
        if path.is_file():path.chmod(0o444)
    print(json.dumps(dict(bundle_receipt=str(out / 'bundle_receipt.json'),
        bundle_receipt_sha256=digest(out / 'bundle_receipt.json'), **receipt), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
