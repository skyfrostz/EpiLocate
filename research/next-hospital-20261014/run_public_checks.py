"""Run isolated generated regression groups; never dispatch a medical experiment."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'research/next-hospital-20261014'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log-dir', type=Path, required=True)
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--frontend', action='store_true')
    args = parser.parse_args()
    args.log_dir.mkdir(parents=True, exist_ok=False)
    inventory = json.loads((ROOT / 'docs/consolidation/EPI_NEXT_SOURCE_FILES_20261014.json').read_text())
    data = [r['path'] for r in inventory['files'] if r['source_lane'] == 'data-eval' and '/tests/test_' in r['path']]
    bootstrap = ['research/next-hospital-20261014/tests/test_encoder_c1_delta_entry.py']
    rest = [str(p.relative_to(ROOT)) for p in sorted((BASE / 'tests').glob('test_*.py')) if str(p.relative_to(ROOT)) not in data + bootstrap]
    api = ['backend_v2/tests', 'session_gateway/tests', 'tests/test_worker/test_protocol.py',
           'qa/test_e2_corrected_argv.py', 'qa/test_demo64_driver_cleanup.py', 'qa/test_technical_evidence.py',
           'qa/test_e2_readout_launch.py', 'qa/test_e2_readout_lifecycle.py', 'qa/test_e2_readout_output.py']
    groups = [('data-' + Path(path).stem, [path]) for path in data]
    groups += [('encoder-bootstrap', bootstrap), ('research', rest), ('api-worker-qa', api)]
    if args.browser:
        groups.append(('browser', ['qa/test_demo64_readiness_browser.py']))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    env['PYTHONPATH'] = os.pathsep.join([str(ROOT / 'qa'), str(BASE), str(BASE / 'tests'), str(ROOT), env.get('PYTHONPATH', '')])
    for label, paths in groups:
        with (args.log_dir / (label + '.log')).open('x') as output:
            result = subprocess.run([sys.executable, '-m', 'pytest', '-p', 'public_source_guard', *paths, '-q'], cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
        print(label, result.returncode, flush=True)
        if result.returncode:
            return result.returncode
    if args.frontend:
        for command in ('test', 'build'):
            with (args.log_dir / ('frontend-' + command + '.log')).open('x') as output:
                result = subprocess.run(['npm', 'run', command], cwd=ROOT / 'frontend', env=env, stdout=output, stderr=subprocess.STDOUT)
            if result.returncode:
                return result.returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
