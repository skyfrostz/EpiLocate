"""Target-enforcing facade over immutable v4/shared core; INT owns IO/dispatch."""
from . import e2_handler_v4 as legacy
from .target_contract_v5 import check_identity, resolve, response_metrics
import torch


class FirstBaselineTarget(torch.nn.Module):
    """Validate first actual baseline in the existing counted forward."""
    def __init__(self, model, metadata):
        super().__init__(); self.model = model; self.metadata = metadata
        self.resolved = None; self.target_error = None

    def forward(self, x):
        result = self.model(x)
        if self.resolved is None:
            try:
                self.resolved = resolve(self.metadata, result.detach().cpu().numpy())
            except ValueError as exc:
                self.target_error = exc
                raise
        return result


def run_prepared_e2(prepared, model, geometry, config, *, target_contract, identity, **kwargs):
    check_identity(target_contract, identity)
    reused = kwargs.get('reused_stage1')
    if reused is not None:
        legacy.import_stage1(reused, prepared, config, identity)
        resolve(target_contract, reused['baseline_logits'])
    checked = FirstBaselineTarget(model, target_contract)
    # With imported stage1 the first new call can be a residual baseline, so
    # the immutable original reuse is the explanation anchor instead.
    if reused is not None: checked.resolved = resolve(target_contract, reused['baseline_logits'])
    result = legacy.run_prepared_e2(prepared, checked, geometry, config, identity=identity, **kwargs)
    if checked.target_error is not None: raise checked.target_error
    original = result['original_logits']
    # No result with unresolved/misdeclared target may reach persistence. Stops
    # without an original baseline remain explicit failed/partial, unpublishable.
    result['target_contract'] = None if original is None else resolve(target_contract, original)
    result['publishable_target_metadata'] = original is not None
    result['schema'] = 'EPI_NEXT_E2_HANDLER_V5'
    return result


def selected_fidelity(prepared, model, config, payload, *, target_contract, identity, **kwargs):
    check_identity(target_contract, identity)
    legacy.import_stage1(payload, prepared, config, identity)
    resolve(target_contract, payload['baseline_logits'])
    checked = FirstBaselineTarget(model, target_contract)
    result = legacy.selected_fidelity(prepared, checked, config, payload, identity=identity, **kwargs)
    if checked.target_error is not None: raise checked.target_error
    original = result['responses'].get('original')
    if original is not None:
        result['target_contract'] = resolve(target_contract, original['logits'])
        target = result['target_contract']['explanation_target']['resolved_class']
        result['responses'] = {k:response_metrics(original['logits'], v['logits'], target) for k,v in result['responses'].items()}
    else:
        result['target_contract'] = None
    result['publishable_target_metadata'] = original is not None
    result['schema'] = 'E2_SELECTED_FIDELITY_V5'
    return result
