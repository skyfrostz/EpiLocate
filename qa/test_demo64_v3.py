"""Generated-only driver terminal/cleanup and candidate template regression."""
import json
import sys
from pathlib import Path
import pytest
from qa import demo64_technical_v3 as driver
from qa.demo64_build import replace_once


def test_template_is_a_vue_fragment_not_inert_html():
    source=Path('qa/demo64_build.py').read_text()
    assert "'<template v-if=\"result\">'" in source
    assert "','<template>')" not in source
    with pytest.raises(ValueError,match='SEAM_DRIFT'):replace_once('drift','expected','fixed')


@pytest.mark.parametrize('failure,cleanup_failure',[(False,False),(True,False),(False,True)])
def test_failure_nonzero_and_primary_step_precedes_cleanup(tmp_path,monkeypatch,failure,cleanup_failure):
    run=driver.ROOT/'.local'/('generated-driver-terminal-'+tmp_path.name)
    # All writes stay in pytest temporary storage by overriding ROOT as well.
    monkeypatch.setattr(driver,'ROOT',tmp_path);run=tmp_path/'.local/run'
    dist=tmp_path/'dist';dist.mkdir();core=dist/'core.js';core.write_text('GENERATED CORE')
    request=dict(schema='DEMO64_TECHNICAL_REQUEST_V3',candidate=dict(path='generated-candidate',sha256='generated'),output=str(run),core_module=dict(path=str(core),sha256=driver.legacy.sha(core),url='/mvp/core.js'),limits=dict(overall_seconds=180,browse_seconds=140,model_calls=0,new_jobs=0,workers=0,uploads=0,screenshots=0,recordings=0,external_transfer=0,retry=0),spatial_protocol=dict(max_error_css_px=.5,points_model_edges=[[0,0],[224,0],[0,224],[224,224],[112,112],[32,32],[96,96]]),driver_bindings=[],browser_runtime=[])
    request['core_module']['url']='/mvp/assets/core.js';(dist/'assets').mkdir();core.rename(dist/'assets/core.js');request['core_module']['path']=str(dist/'assets/core.js')
    monkeypatch.setattr(driver.legacy,'bound',lambda r:request if r['path']=='request' else dict(status='EXPLICIT_LOCAL_TECHNICAL_CONFIRMATION',request_sha256='req-sha'))
    monkeypatch.setattr(driver,'checked',lambda r:(dict(dist=str(dist)),{}));monkeypatch.setattr(driver.signal,'signal',lambda *a:None);monkeypatch.setattr(driver.signal,'alarm',lambda *a:None)
    class Process:
        pid=0;returncode=None
        def __init__(self,*a,**k):
            services=run/'services';services.mkdir();(services/'restore-ready.json').write_text('{}')
            (services/'restore-exit.json').write_text(json.dumps(dict(source_db_unchanged=True,owned_services=[dict(exit_code=0)],model_calls=0,worker_started=False)))
        def poll(self):return self.returncode
        def terminate(self):
            self.returncode=0
            if cleanup_failure:raise RuntimeError('GENERATED_CLEANUP')
        def wait(self,**k):return 0
    monkeypatch.setattr(driver.subprocess,'Popen',Process)
    def browse(path,evidence,log):
        log.step('current_image_readiness',status='STARTED')
        if failure:
            err=ValueError('GENERATED_PRIMARY');log.failure(err)
            log.step('browser_closed',status='PASS');raise err
        log.step('current_image_readiness',status='PASS')
    monkeypatch.setattr(driver,'browse',browse)
    run.parent.mkdir();monkeypatch.setattr(sys,'argv',['driver','--request','request','--request-sha','req-sha','--confirmation','confirmation','--confirmation-sha','confirmation-sha','--execute'])
    result=driver.main();saved=json.loads((run/'acceptance.json').read_bytes())
    assert result==(2 if failure or cleanup_failure else 0)
    assert bool(saved['cleanup_errors'])==cleanup_failure
    if failure:assert saved['primary_failure']['step']=='current_image_readiness'
    assert saved['status']==('FAILED_OR_PARTIAL' if failure or cleanup_failure else 'PASS_TECHNICAL_ONLY')
