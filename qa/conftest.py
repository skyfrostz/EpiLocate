"""Explicit exclusions for historical private-receipt integration fixtures."""
import pytest

PRIVATE_BINDING_MODULES = {'test_e2_readout_launch.py', 'test_e2_readout_lifecycle.py'}
PRIVATE_BINDING_FUNCTIONS = {'test_native_stdout_stderr_are_drained_bounded_and_failure_recorded', 'test_actual_shared_guard_completion_persists_known_partial_counts'}

def pytest_collection_modifyitems(items):
    for item in items:
        if item.path.name in PRIVATE_BINDING_MODULES or item.originalname in PRIVATE_BINDING_FUNCTIONS:
            item.add_marker(pytest.mark.skip(reason="Historical private execution bindings and sealed bundles are excluded from the public snapshot"))
