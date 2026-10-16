"""Constructible generated receipt chain; no real approvals, data or queue."""
import hashlib
import json
from pathlib import Path
import pytest
from qa import next_selected_fidelity as launch


def ref(path, value):
    raw = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(raw)
    return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest())


def chain(tmp_path):
    source = tmp_path / 'generated-source.py'
    source.write_text('# GENERATED\n')
    sources = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
               for path in (source, Path(launch.__file__))}
    scope = dict(schema='EPI_NEXT_SELECTED_FIDELITY_APPLICATION_BINDING_V2',
                 status='ENGINEERING_BOUND_NOT_DISPATCHED', task_key='GENERATED_ONLY',
                 compute=dict(device='CPU', forward=5, backward=0, updates=0,
                              seconds=120, output_bytes=67108864),
                 source_sha256=sources, output_root=str(tmp_path / 'new-output'))
    binding = ref(tmp_path / 'binding.json', scope)
    # Order is source -> immutable binding -> receipts -> external dispatch.
    # Every object is generated. Passing this test grants no actual admission.
    owner = ref(tmp_path / 'owner.json', dict(scope='GENERATED_ONLY'))
    admission = ref(tmp_path / 'admission.json', dict(scope='GENERATED_ONLY'))
    dispatch = dict(status='READY_FOR_CHIEF_DISPATCH', binding_sha256=binding['sha256'],
                    task_key=scope['task_key'], source_sha256=sources,
                    owner_receipt=owner, new_admission_decision=admission)
    return scope, binding, ref(tmp_path / 'dispatch.json', dispatch), source


def test_generated_full_external_chain_is_constructible(tmp_path):
    scope, binding, dispatch, _ = chain(tmp_path)
    result = launch.validate_bindings(scope, binding['sha256'], dispatch)
    assert result['binding_sha256'] == binding['sha256']
    assert launch.bound(binding) == scope
    assert all(key not in scope for key in ('chief_dispatch', 'owner_receipt', 'new_admission_decision'))


@pytest.mark.parametrize('tamper', ['binding', 'dispatch', 'source', 'owner'])
def test_generated_chain_tampering_is_rejected(tmp_path, tamper):
    scope, binding, dispatch, source = chain(tmp_path)
    if tamper == 'binding':
        binding['sha256'] = '0' * 64
    elif tamper == 'dispatch':
        Path(dispatch['path']).write_text('{}')
    elif tamper == 'source':
        source.write_text('# TAMPERED\n')
    else:
        Path(launch.bound(dispatch)['owner_receipt']['path']).write_text('{}')
    with pytest.raises(ValueError):
        launch.validate_bindings(scope, binding['sha256'], dispatch)


def test_missing_dispatch_or_existing_output_refuses(tmp_path):
    scope, binding, dispatch, _ = chain(tmp_path)
    with pytest.raises(ValueError, match='NOT_BOUND'):
        launch.validate_bindings(scope, binding['sha256'], None)
    Path(scope['output_root']).mkdir()
    with pytest.raises(ValueError, match='RECONCILE_NO_RETRY'):
        launch.validate_bindings(scope, binding['sha256'], dispatch)
