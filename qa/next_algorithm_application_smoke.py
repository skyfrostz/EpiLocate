#!/usr/bin/env python3
"""Reproducible generated application smoke; no real-data or model options."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--loc-root',type=Path,required=True)
    parser.add_argument('--alembic-site',type=Path)
    args=parser.parse_args();output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    root=Path(__file__).resolve().parents[1]
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',EPI_NEXT_SYNTHETIC_LOC_ROOT=str(args.loc_root.resolve()),EPI_NEXT_SMOKE_RECEIPT_DIRECTORY=str(output),OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    env['PYTHONPATH']=str(root)+os.pathsep+env.get('PYTHONPATH','')
    tests=['backend_v2/tests/test_next_application.py','backend_v2/tests/test_next_loc_adapter.py','backend_v2/tests/test_next_migration.py','backend_v2/tests/test_next_e2_launch.py','backend_v2/tests/test_phase1.py','backend_v2/tests/test_job_idempotency.py','backend_v2/tests/test_auth_security.py']
    test_args=[*tests,'-q','--disable-warnings','--basetemp',str(output/'generated-test-tmp')]
    script='import sys; '
    if args.alembic_site:script+='sys.path.append('+repr(str(args.alembic_site.resolve()))+'); '
    script+='import pytest; sys.exit(pytest.main('+repr(test_args)+'))'
    command=[sys.executable,'-c',script];start=time.monotonic()
    with (output/'tests.log').open('xb') as stream:
        run=subprocess.run(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=60)
    receipt=dict(schema='EPI_NEXT_GENERATED_APPLICATION_SMOKE_V1',status='PASS' if run.returncode==0 else 'FAIL',exit_code=run.returncode,elapsed_seconds=time.monotonic()-start,command=command,scope='SYNTHETIC_ONLY',medical_forward=0,medical_backward=0,medical_updates=0,real_CT_read=False,real_model_weights_read=False,real_browser_run=False,queue_dispatch=False,clinical_validity='NOT_ESTABLISHED',test_log_sha256=hashlib.sha256((output/'tests.log').read_bytes()).hexdigest())
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(dict(status=receipt['status'],receipt=str(output/'receipt.json'))))
    return run.returncode


if __name__=='__main__':raise SystemExit(main())
