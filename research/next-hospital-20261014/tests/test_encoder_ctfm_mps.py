"""CPU-only evidence validation; no retroactive tolerance or inference."""
from types import SimpleNamespace

import numpy as np
import pytest

from epi_next import encoder_ctfm_mps as assessor
from epi_next.encoder_ctfm_mps import assess_run, raw_difference
from epi_next.encoder_ctfm_mps_smoke import file_sha, write_new


def test_full_tensor_difference_catches_pooling_cancellation():
    cpu = np.zeros((1,512,2,2,2), dtype=np.float32)
    mps = cpu.copy()
    mps.flat[0], mps.flat[1] = .01, -.01
    assert mps.mean() == cpu.mean()
    metrics = raw_difference(cpu, mps)
    assert metrics['elements_compared'] == 4096
    assert metrics['max_absolute_error'] == pytest.approx(.01)
    assert metrics['mean_absolute_error'] == pytest.approx(.02/4096)
    assert metrics['numerical_acceptance'] == 'NOT RUN'
    assert metrics['tolerance'] is None


def test_zero_error_is_not_retroactive_numerical_pass():
    metrics = raw_difference(np.zeros(4,dtype='float32'),np.zeros(4,dtype='float32'))
    assert metrics['max_absolute_error'] == metrics['mean_absolute_error'] == 0
    assert metrics['numerical_acceptance'] == 'NOT RUN'


@pytest.mark.parametrize('other', [np.array([np.nan],dtype='float32'),
    np.array([np.inf],dtype='float32'), np.zeros(2,dtype='float32'), np.zeros(1,dtype='float16')])
def test_invalid_tensor_evidence_rejected(other):
    with pytest.raises(ValueError): raw_difference(np.zeros(1,dtype='float32'),other)


def test_manifest_hash_checked_before_parsing(tmp_path):
    (tmp_path/'manifest.json').write_text('invalid JSON')
    with pytest.raises(ValueError,match='manifest SHA'): assess_run(tmp_path,'a'*64)


def test_real_data_or_changed_scope_evidence_rejected(tmp_path):
    path=tmp_path/'manifest.json'
    write_new(path,dict(real_case_count=1,sizes=[]))
    with pytest.raises(ValueError,match='scope'): assess_run(tmp_path,file_sha(path))


def assessment_arguments(tmp_path, monkeypatch):
    source = tmp_path/'source.py'
    source.write_text('historical source')
    monkeypatch.setattr(assessor,'assess_run', lambda *a: ({'source_sha256':file_sha(source)},[],{}))
    state = tmp_path/'state.json'
    write_new(state, {'revision':4})
    delivery = tmp_path/'delivery.json'
    write_new(delivery, {'case_count':3,'sop_count':715,'split_counts':{'train':3,'test':0,'val':0}})
    return SimpleNamespace(run=tmp_path, manifest_sha256='unused', source_snapshot=source,
        control_state=state, control_state_sha256=file_sha(state), data_delivery=delivery,
        data_delivery_sha256=file_sha(delivery), output_dir=tmp_path/'out')


@pytest.mark.parametrize('changed_file, expected', [('control_state','state SHA'),
    ('data_delivery','delivery SHA'),('source_snapshot','source snapshot SHA')])
def test_changed_dependencies_fail_before_any_result_write(tmp_path, monkeypatch, changed_file, expected):
    args = assessment_arguments(tmp_path, monkeypatch)
    # Freeze original source hash before mutating it.
    source_sha = file_sha(args.source_snapshot)
    monkeypatch.setattr(assessor,'assess_run', lambda *a: ({'source_sha256':source_sha},[],{}))
    getattr(args,changed_file).write_text('changed bytes')
    with pytest.raises(ValueError,match=expected): assessor.deliver(args)
    assert not args.output_dir.exists()


def test_out_of_scope_delivery_cannot_create_results(tmp_path, monkeypatch):
    args = assessment_arguments(tmp_path, monkeypatch)
    args.data_delivery.unlink()
    write_new(args.data_delivery, {'case_count':4,'sop_count':716,'split_counts':{'train':3,'test':1}})
    args.data_delivery_sha256 = file_sha(args.data_delivery)
    with pytest.raises(ValueError,match='scope'): assessor.deliver(args)
    assert not args.output_dir.exists()
