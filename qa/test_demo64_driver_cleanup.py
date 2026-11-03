"""Generated service metadata only; exercise actual driver's failure/finally path."""
import json
import sys
import pytest
from qa import demo64_technical_v2 as driver


@pytest.mark.parametrize('cleanup_fails',[False,True])
def test_driver_persists_primary_and_independent_cleanup(tmp_path,monkeypatch,cleanup_fails):
    output=tmp_path/'run';monkeypatch.setattr(driver,'OUTPUT',output)
    request=dict(candidate=driver.CANDIDATE,output=str(output),driver_bindings=[],browser_runtime=[])
    def bound(ref):
        return request if ref['path']=='generated-request' else dict(status='EXPLICIT_LOCAL_TECHNICAL_CONFIRMATION',request_sha256='generated-sha')
    monkeypatch.setattr(driver.legacy,'bound',bound);monkeypatch.setattr(driver,'checked',lambda ref:({},{}))
    monkeypatch.setattr(driver.signal,'signal',lambda *a:None);monkeypatch.setattr(driver.signal,'alarm',lambda *a:None)
    class GeneratedProcess:
        pid=0;returncode=None
        def __init__(self,*a,**k):
            run=output/'services';run.mkdir();(run/'restore-ready.json').write_text('{}')
            (run/'restore-exit.json').write_text(json.dumps(dict(source_db_unchanged=True,owned_services=[dict(exit_code=0)],worker_started=False,model_calls=0)))
        def poll(self):return self.returncode
        def terminate(self):
            if cleanup_fails:raise RuntimeError('GENERATED_CLEANUP_FAILURE')
            self.returncode=0
        def wait(self,**k):return self.returncode
    monkeypatch.setattr(driver.subprocess,'Popen',GeneratedProcess)
    def failed_browse(run,evidence,log):
        log.step('generated_first_completed_step',status='PASS')
        assert json.loads((output/'acceptance.json').read_text())['steps'][-1]['status']=='PASS'
        log.step('generated_readiness',status='STARTED')
        raise ValueError('GENERATED_PRIMARY_FAILURE')
    monkeypatch.setattr(driver,'browse',failed_browse)
    monkeypatch.setattr(sys,'argv',['driver','--request','generated-request','--request-sha','generated-sha','--execute','--confirmation','generated-confirmation','--confirmation-sha','generated-sha'])
    driver.main()
    saved=json.loads((output/'acceptance.json').read_text())
    assert saved['primary_failure']['message']=='GENERATED_PRIMARY_FAILURE'
    assert bool(saved['cleanup_errors'])==cleanup_fails and saved['exit']['source_db_unchanged']
    assert saved['status']=='FAILED_OR_PARTIAL'
