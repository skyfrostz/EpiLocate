from argparse import Namespace
import json
from pathlib import Path
import sys

import numpy as np
import pytest

from epi_next.encoder_ctfm_mps_smoke import (
    DEFAULT_CONFIG, classify_exception, compare_features, run_staircase,
    supervise, validate_config, write_new,
)


def test_difference_metrics_known_answer():
    a=np.array([0.,2.,-2.]);b=np.array([1.,2.,-2.])
    m=compare_features(a,b)
    assert m['max_abs']==1
    assert m['rmse']==pytest.approx(np.sqrt(1/3))
    assert m['max_relative_to_reference_peak']==.5
    assert m['relative_denominator_floor']==.002
    assert m['max_elementwise_relative_with_floor']==500
    assert m['cosine']==pytest.approx(np.sqrt(8/9))
    assert m['numerical_acceptance']=='NOT_ASSESSED_NO_PREDECLARED_THRESHOLD'


def test_zero_reference_is_finite_and_cosine_explicitly_undefined():
    m=compare_features(np.zeros(4),np.ones(4))
    assert m['cosine'] is None
    assert m['cosine_status']=='UNDEFINED_ZERO_NORM'
    assert m['max_elementwise_relative_with_floor']==1e12
    assert np.isfinite(m['rmse'])


@pytest.mark.parametrize('a,b', [([1],[1,2]),([float('nan')],[0]),([] ,[])])
def test_invalid_numeric_arrays_rejected(a,b):
    with pytest.raises(ValueError):compare_features(a,b)


@pytest.mark.parametrize('change',[{'sizes':[64]},{'sizes':[32,128]},{'timeout_seconds_per_size':10000}, {'rss_limit_bytes':1<<40}])
def test_resource_escalation_is_rejected(change):
    with pytest.raises(ValueError):validate_config(dict(DEFAULT_CONFIG,**change))


def test_valid_single_stage_and_staircase():
    validate_config(dict(DEFAULT_CONFIG))
    validate_config(dict(DEFAULT_CONFIG,sizes=[32]))


def test_exclusive_json_receipt(tmp_path):
    p=tmp_path/'receipt.json';write_new(p,{'status':'FIRST'})
    with pytest.raises(FileExistsError):write_new(p,{'status':'SECOND'})
    assert json.loads(p.read_text())['status']=='FIRST'


def test_failure_before_inference_leaves_manifest_and_refuses_reuse(tmp_path):
    args=Namespace(output=tmp_path/'run',weights=tmp_path/'missing',sha256='a'*64,config=None)
    assert run_staircase(args)==1
    before=(args.output/'manifest.json').read_bytes()
    assert json.loads(before)['status']=='FAILED'
    assert json.loads(before)['real_case_count']==0
    with pytest.raises(FileExistsError):run_staircase(args)
    assert (args.output/'manifest.json').read_bytes()==before


def test_supervisor_preserves_nonzero_child_failure(tmp_path):
    result=supervise([sys.executable,'-c','raise SystemExit(7)'],tmp_path,2,1024**3)
    assert result['exit_code']==7 and result['status']=='FAILED'
    assert result['process_running'] is False
    assert (tmp_path/'receipt.json').is_file()


def test_supervisor_timeout_kills_only_known_child_and_writes_receipt(tmp_path):
    result=supervise([sys.executable,'-c','import time;time.sleep(10)'],tmp_path,.1,1024**3)
    assert result['status']=='TIMEOUT'
    assert result['exit_code']!=0 and result['process_running'] is False
    assert json.loads((tmp_path/'receipt.json').read_text())['status']=='TIMEOUT'


def test_supervisor_memory_limit_records_failure(tmp_path):
    result=supervise([sys.executable,'-c','import time; x=bytearray(10_000_000);time.sleep(10)'],tmp_path,2,1)
    assert result['status']=='MEMORY_BUDGET'
    assert result['process_running'] is False


def test_unsupported_and_memory_errors_have_distinct_status():
    assert classify_exception(RuntimeError('operation not implemented for MPS'))=='UNSUPPORTED_OPERATOR'
    assert classify_exception(RuntimeError('MPS backend out of memory'))=='MEMORY_BUDGET'
    assert classify_exception(ImportError('no monai'))=='DEPENDENCY_UNAVAILABLE'
