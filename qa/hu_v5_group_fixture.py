"""Generated timeout injection into the approved v4 wrapper source, never run it."""

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[1]
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import signal
import subprocess


def main():
    receipt = Path(str(_PUBLIC_ROOT / '.local/phase2/hu-single-diagnostic-decode-v4-request-20261012/HU_V4_SINGLE_EXECUTION_DELIVERY_20261012.json'))
    raw = receipt.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '0000000000000000000000000000000000000000000000000000000000000000'
    delivery = json.loads(raw)
    tree = ast.parse(delivery['thin_wrapper_source'])
    candidates = [node for node in ast.walk(tree) if isinstance(node, ast.Try)
                  and ast.unparse(node.body[0]).endswith('child.communicate(timeout=90)')]
    assert len(candidates) == 1
    events = []
    class FakeChild:
        pid = 100
        calls = 0
        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls <= 2: raise subprocess.TimeoutExpired('GENERATED_ONLY', timeout)
            return b'', b''
    # Synthetic independent phase group101 is outside CLI group100.
    namespace = dict(os=SimpleNamespace(killpg=lambda pid, sig: events.append((pid, sig))),
                     signal=signal, subprocess=subprocess, child=FakeChild(), d={})
    exec(compile(ast.Module(body=candidates, type_ignores=[]), 'V4_BOUND_TIMEOUT_BLOCK', 'exec'), namespace)
    assert events == [(100, signal.SIGTERM), (100, signal.SIGKILL)]
    assert not any(pid == 101 for pid, _ in events)
    assert namespace['d']['outer_overall_stop'] is True
    print(json.dumps(dict(scope='GENERATED_WRAPPER_TIMEOUT_ONLY', status='PHASE_WORKER_EXIT_NOT_PROVEN',
                         wrapper_sha256=delivery['wrapper_sha256'], signalled_generated_groups=[pid for pid, _ in events],
                         independent_phase_group_signalled=False, processes_started=0, queue_calls=0,
                         codec_calls=0, model_calls=0, patient_reads=0)))


if __name__ == '__main__':
    main()
