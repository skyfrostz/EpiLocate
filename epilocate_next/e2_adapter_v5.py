"""LOC v5 facade injection and zero-model replay; preserve original v4 adapter."""
from .e2_adapter import E2HandlerAdapter
from .e2_replay import E2PrecomputedAdapter
from .research_contract import expected_target
from .contracts import Prediction


def check_raw_target(req, raw, binding):
    if raw['schema'] != 'EPI_NEXT_E2_HANDLER_V5':
        raise ValueError('E2_V5_SOURCE_REQUIRED_NO_LEGACY_RELABEL')
    original = raw['original_logits']
    prediction = None
    if original is not None:
        logits = original[0]
        pred = max(range(len(logits)), key=lambda c: logits[c])
        prediction = Prediction(logits=logits, predicted_class=pred,
                                class_label=req.task.class_labels[pred])
        if raw['original_class'] != pred:
            raise ValueError('E2_V5_ORIGINAL_CLASS_MISMATCH')
    expected = expected_target(req, binding.target_request, binding.target_spec_path, prediction)
    if any(raw['input_binding'].get(k) != binding.target_request['model_binding'][k]
           for k in ('model_sha256', 'preprocessing_sha256', 'model_adapter_sha256')):
        raise ValueError('E2_V5_ACTUAL_MODEL_BINDING_MISMATCH')
    if raw.get('target_contract') != expected or raw.get('publishable_target_metadata') != (expected is not None):
        raise ValueError('E2_V5_ACTUAL_TARGET_MISMATCH')


class E2HandlerAdapterV5(E2HandlerAdapter):
    def __init__(self, *args, research_binding_provider, **kwargs):
        super().__init__(*args, **kwargs)
        self.research_binding_provider = research_binding_provider

    def __call__(self, req, input_path, output_dir, context):
        binding = self.research_binding_provider(req)
        def core(*args, **kwargs):
            raw = self.core(*args, target_contract=binding.target_request, **kwargs)
            check_raw_target(req, raw, binding)
            return raw
        # One ephemeral adapter; no mutable shared request or algorithm math.
        adapter = E2HandlerAdapter(core, self.prepare, self.model, self.config,
            model_adapter_sha256=self.model_adapter_sha256, stop_exception=self.stop_exception,
            reuse_provider=self.reuse_provider, branch_seconds=self.branch_seconds)
        return adapter(req, input_path, output_dir, context)


class E2PrecomputedAdapterV5(E2PrecomputedAdapter):
    def __init__(self, binding_provider, research_binding_provider):
        super().__init__(binding_provider)
        self.research_binding_provider = research_binding_provider

    def __call__(self, req, input_path, output_dir, context):
        output = super().__call__(req, input_path, output_dir, context)
        binding = self.research_binding_provider(req)
        expected = expected_target(req, binding.target_request, binding.target_spec_path, output.result.prediction)
        if output.result.diagnostics.get('source_handler_schema') != 'EPI_NEXT_E2_HANDLER_V5':
            raise ValueError('E2_V5_SOURCE_REQUIRED_NO_LEGACY_RELABEL')
        if output.result.diagnostics.get('target_contract') != expected:
            raise ValueError('E2_V5_ACTUAL_TARGET_MISMATCH')
        if any(output.result.diagnostics['source_model_binding'].get(k) != binding.target_request['model_binding'][k]
               for k in ('model_sha256', 'preprocessing_sha256', 'model_adapter_sha256')):
            raise ValueError('E2_V5_ACTUAL_MODEL_BINDING_MISMATCH')
        return output
