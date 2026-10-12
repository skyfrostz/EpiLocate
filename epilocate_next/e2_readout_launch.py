"""E2-R one-shot loader seam. Import inert; only an admitted child calls it."""
import importlib
import json
from pathlib import Path


class ReadoutFailure(RuntimeError):
    def __init__(self,exc,context,receipt_written):
        super().__init__(type(exc).__name__)
        self.actual_forward=context.forward_count;self.actual_backward=context.backward_count
        self.receipt_written=receipt_written


def run_existing_readout(value, guard, *, modules=None, readout=None, runner_builder=None, output_budget=None):
    # Deferred imports: check-only CLI never imports Torch or reads real arrays.
    from .contracts import ApplicationRequest
    from .e2_adapter import CoreBudgetAdapter
    from .e2_assets import save_json, plain
    from .e2_launch import (ExistingE2Binding, build_existing_e2_runner,
                           locked_json, localization_modules)
    from .runner import HandlerContext
    fields = dict(value['existing_e2_binding'])
    for key in ('localization_root', 'integration_bridge_source'):
        fields[key] = Path(fields[key])
    binding = ExistingE2Binding(**fields)
    req = ApplicationRequest.model_validate(binding.application_request)
    if (binding.case_index != 3 or binding.job_id != value['job_id']
            or (req.budget.forward, req.budget.backward, req.budget.updates) != (18, 0, 0)
            or req.budget.seconds != 120 or req.budget.output_bytes != 67108864
            or req.task.target_class != 1):
        raise ValueError('EXACT_E2_R_SCOPE_REQUIRED')
    directory = Path(value['output_root'])
    if value.get('_output_reserved_by_parent'):
        if not directory.is_dir() or any(directory.iterdir()):raise ValueError('EXACT_EMPTY_RESERVED_OUTPUT_REQUIRED')
    else:directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    if req.execution_mode=='LIVE' and output_budget is None:raise ValueError('CUMULATIVE_OUTPUT_BUDGET_REQUIRED')
    def persist(name,content,terminal=False):
        if output_budget:
            raw=json.dumps(plain(content),sort_keys=True,allow_nan=False).encode()
            output_budget.write_new(directory/name,raw,terminal=terminal)
        else:save_json(directory,name,content,req.budget.output_bytes)
    guard.check(); guard.begin_case(binding.job_id)
    context = HandlerContext(req.budget, guard)
    context.start = guard.started  # same parent clock: no loading-time reset
    try:
        request = locked_json(value['readout_request'])
        lock = locked_json(binding.loc_dependency_lock)
        first, core, requests = modules or localization_modules(binding.localization_root, lock)
        readout = readout or importlib.import_module(core.__package__ + '.e2_readout_v5')
        builder = runner_builder or build_existing_e2_runner
        runner = builder(binding, guard, directory, modules=(first, core, requests),
                         purpose='P1_SELECTED_MASK_FIDELITY_V4')
        adapter = runner.handlers['E2']
        prepared_binding = adapter.prepare(req, None)
        prepared, geometry = prepared_binding.prepared, prepared_binding.geometry
        payload, canonical_sha = adapter.reuse_provider(req)
        if canonical_sha != request['reuse_payload_canonical_sha256']:
            raise ValueError('READOUT_REUSE_CANONICAL_MISMATCH')
        saved_ref = value['saved_fidelity']
        if saved_ref['sha256'] != request['saved_fidelity']['file_sha256']:
            raise ValueError('READOUT_SAVED_REFERENCE_MISMATCH')
        # Exact SHA + all four saved-logit bindings before model loading; no fallback.
        from hashlib import sha256
        path = Path(saved_ref['path'])
        if path.is_symlink(): raise ValueError('READOUT_SAVED_SYMLINK')
        with path.open('rb') as stream: saved = stream.read(67108865)
        if len(saved) > 67108864 or sha256(saved).hexdigest() != saved_ref['sha256']:
            raise ValueError('READOUT_SAVED_FILE_MISMATCH')
        readout.check_saved(saved, request, payload)
        guard.check()
        model = adapter.model(req)
        identity = dict(classifier_kind='2D_SLICE_CLASSIFIER',
            evidence_type='SYNTHETIC' if req.execution_mode == 'SYNTHETIC' else 'APPROVED_DEVELOPMENT',
            model_sha256=req.model.checkpoint_sha256, preprocessing_sha256=req.model.preprocessing_sha256,
            model_adapter_sha256=adapter.model_adapter_sha256,
            reused_stage1_sha256=canonical_sha, geometry_sha256=req.input.geometry_ledger_sha256)
        result = readout.run_readout(prepared, model, geometry, adapter.config(req), payload,
            request=request, identity=identity, saved_fidelity_bytes=saved,
            adapter_predict=model.predict_numpy, budget=CoreBudgetAdapter(context, core.BudgetStopped),
            allow_real=req.execution_mode == 'LIVE')
        if (context.backward_count or context.update_count or context.forward_count > 14
                or result['new_cost']['forward'] != context.forward_count
                or result['new_cost']['backward'] != context.backward_count
                or (result['status'] == 'SUCCESS' and
                    (context.forward_count != 14 or result['historical_logits_reused'] != 4))):
            raise ValueError('READOUT_ACTUAL_COST_MISMATCH')
        result.update(application_loading_entry='run_existing_readout',
                      execution_binding_sha256=value['_binding_sha256'], stop_events=context.stop_events)
        persist('readout.json', result)
        return result
    except BaseException as exc:
        # Keep failure/partial diagnostics and actual counts; never retry a call.
        failure = dict(schema='EPI_NEXT_E2_R_ENTRY_FAILURE_V1', status='FAILED',
            error_type=type(exc).__name__, new_cost=dict(forward=context.forward_count,
            backward=context.backward_count, optimizer_steps=context.update_count),
            stop_events=context.stop_events, execution_binding_sha256=value['_binding_sha256'])
        written=False
        try:persist('entry-failure.json',failure,terminal=True);written=True
        except Exception:pass  # known counters still travel to supervisor completion
        raise ReadoutFailure(exc,context,written) from exc
    finally:
        guard.end_case()
