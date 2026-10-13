"""Metadata-only argv derivation. Never dispatches or reserves a slot."""
from pathlib import Path
from qa import next_e2_readout as entry
from qa.next_selected_fidelity import bound


def derive(dispatch_ref):
    # Preserve signed strings; do not resolve/sanitize paths into a new identity.
    if not Path(dispatch_ref['path']).is_absolute():raise ValueError('ABSOLUTE_DISPATCH_REQUIRED')
    dispatch=bound(dispatch_ref);reference=dispatch['binding']
    if not Path(reference['path']).is_absolute():raise ValueError('ABSOLUTE_BINDING_REQUIRED')
    value=bound(reference)
    entry.check_dispatch(reference,value,dispatch_ref,executing=False)
    return dict(cwd=str(entry.ROOT),argv=entry.command(reference,dispatch_ref),
        status='CHECK_ONLY_NO_EXECUTE',binding=reference,
        execution_requirement='new explicit incremental confirmation and fresh unconsumed dispatch/window; append execute only then')
