"""Public-source test scope: historical private bindings are intentionally absent."""
import pytest

PRIVATE_BINDING_MODULES = {'test_encoder_volume_runner.py', 'test_ctfm_weak_case_contract.py', 'test_encoder_wave1_contract.py', 'test_r18_entry_r79.py', 'test_p1_storage_race_v6.py', 'test_p1_runner_v4.py', 'test_ctfm_classifier_r72_gaps.py', 'test_p1_recovery_v5.py', 'test_recovery_chain_v1.py', 'test_p1_retry_binding_v8.py', 'test_wave1_runner_seams_v3.py'}

def pytest_collection_modifyitems(items):
    for item in items:
        if item.path.name in PRIVATE_BINDING_MODULES:
            item.add_marker(pytest.mark.skip(reason="Historical private receipts/bundles are excluded from the public source snapshot"))
