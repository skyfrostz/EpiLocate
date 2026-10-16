import json
from qa.technical_evidence import Evidence

def test_persist_each_step_and_preserve_both_failures(tmp_path):
    path=tmp_path/'receipt.json';log=Evidence(path,dict(status='RUNNING'))
    log.step('login',status='PASS');assert json.loads(path.read_text())['steps'][0]['status']=='PASS'
    log.step('readiness',status='STARTED');log.failure(ValueError('primary'))
    log.failure(RuntimeError('cleanup'),cleanup=True)
    saved=json.loads(path.read_text());assert saved['primary_failure']['message']=='primary'
    assert saved['cleanup_errors'][0]['message']=='cleanup' and len(saved['steps'])==2
    assert not path.with_suffix('.tmp').exists()
