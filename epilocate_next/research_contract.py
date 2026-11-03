"""Additive research validation; frozen next-1/base restore files stay unchanged."""
import copy
from dataclasses import dataclass
import hashlib
import json
import re
from pathlib import Path

from .contracts import ApplicationRequest, HandlerResult, validate_output
from .f0_replay import validate_f0_consumption
from .runner import HandlerOutput

TARGET_SPEC_SHA = 'd852001e0db9d52844c900d81251a19b8afb20000b0b3429de11e80bf90b647c'
RESEARCH_SCHEMA = 'EPI_NEXT_RESEARCH_RESULT_V2'


@dataclass(frozen=True)
class ResearchBinding:
    request_digest: str
    target_request: dict | None = None
    target_spec_path: Path | None = None
    f0_sources: dict | None = None
    f0_identity: dict | None = None


def request_digest(req):
    raw = json.dumps(req.model_dump(mode='json'), sort_keys=True,
                     separators=(',', ':'), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def expected_target(req, metadata, spec_path, prediction):
    raw = Path(spec_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != TARGET_SPEC_SHA:
        raise ValueError('TARGET_CONTRACT_SOURCE_DRIFT')
    spec = json.loads(raw)
    if (metadata['schema'] != spec['schema'] or metadata['prediction_scope'] != 'SLICE'
            or req.algorithm_mode != 'E2' or req.task.unit != 'SLICE'
            or metadata['class_labels'] != req.task.class_labels
            or metadata['loss_definition'] != spec['loss_definition']):
        raise ValueError('RESEARCH_TARGET_SCOPE_LABEL_OR_LOSS_MISMATCH')
    target = metadata['explanation_target']
    if (set(target) != {'policy', 'declared_class'}
            or target['policy'] not in {'ORIGINAL_ARGMAX_FIXED', 'DECLARED_FIXED'}
            or type(target['declared_class']) is not int
            or target['declared_class'] != req.task.target_class):
        raise ValueError('RESEARCH_TARGET_DECLARATION_MISMATCH')
    source = metadata['source_label']
    if source is not None:
        if (set(source) != {'class_id', 'label', 'scope', 'provenance_sha256'}
                or type(source['class_id']) is not int or source['class_id'] not in (0, 1)
                or not isinstance(source['label'], str) or not source['label']
                or source['scope'] not in {'SLICE', 'CASE', 'BAG', 'SOURCE_GROUP'}
                or not re.fullmatch('[a-f0-9]{64}', str(source['provenance_sha256']))):
            raise ValueError('RESEARCH_SOURCE_LABEL_REFERENCE_REQUIRED')
    model = metadata['model_binding']
    if (set(model) != {'model_sha256', 'preprocessing_sha256', 'model_adapter_sha256', 'task_version'}
            or model['model_sha256'] != req.model.checkpoint_sha256
            or model['preprocessing_sha256'] != req.model.preprocessing_sha256
            or model['task_version'] != req.task.definition_id
            or not re.fullmatch('[a-f0-9]{64}', str(model['model_adapter_sha256']))):
        raise ValueError('RESEARCH_TARGET_MODEL_BINDING_MISMATCH')
    if prediction is None:
        return None  # Failed/partial with no baseline cannot invent a resolved class.
    predicted = max(range(len(prediction.logits)), key=lambda c: prediction.logits[c])
    resolved = predicted if target['policy'] == 'ORIGINAL_ARGMAX_FIXED' else target['declared_class']
    if target['declared_class'] != resolved:
        raise ValueError('DECLARED_RESOLVED_TARGET_MISMATCH')
    value = copy.deepcopy(metadata)
    value['explanation_target']['resolved_class'] = resolved
    value.update(predicted_class=predicted, contract_sha256=TARGET_SPEC_SHA)
    return value


def research_envelope(req, binding):
    if request_digest(req) != binding.request_digest:
        raise ValueError('RESEARCH_REQUEST_BINDING_MISMATCH')
    if req.algorithm_mode == 'CTFM' and binding.f0_identity is None:
        raise ValueError('F0_RECORD_APPLICATION_BINDING_REQUIRED')
    return dict(schema=RESEARCH_SCHEMA, request_digest=binding.request_digest,
                target_request=copy.deepcopy(binding.target_request),
                f0_identity=copy.deepcopy(binding.f0_identity))


def validate_research_output(req, output, binding):
    validate_output(req, output)
    if output.diagnostics.get('research_contract') != research_envelope(req, binding):
        raise ValueError('PERSISTED_RESEARCH_REQUEST_MISMATCH')
    if req.algorithm_mode == 'E2':
        if binding.target_request is None or binding.target_spec_path is None:
            raise ValueError('RESEARCH_TARGET_CONTRACT_REQUIRED')
        expected = expected_target(req, binding.target_request, binding.target_spec_path, output.prediction)
        if output.diagnostics.get('target_contract') != expected:
            raise ValueError('PERSISTED_TARGET_CONTRACT_MISMATCH')
        if output.prediction is not None and output.prediction.predicted_class != expected['predicted_class']:
            raise ValueError('RESEARCH_ORIGINAL_ARGMAX_MISMATCH')
        if output.prediction is not None and any(
                output.diagnostics.get('source_model_binding', {}).get(k) != binding.target_request['model_binding'][k]
                for k in ('model_sha256', 'preprocessing_sha256', 'model_adapter_sha256')):
            raise ValueError('PERSISTED_TARGET_MODEL_MISMATCH')
    elif output.prediction is not None:
        if binding.f0_sources is None or output.source_artifacts != binding.f0_sources:
            raise ValueError('F0_BOUND_SOURCE_ARTIFACTS_MISMATCH')
        if output.diagnostics.get('f0', {}).get('consumption_binding') != binding.f0_identity:
            raise ValueError('F0_RECORD_APPLICATION_BINDING_MISMATCH')
        validate_f0_consumption(req, output.prediction, output.diagnostics['f0'], output.source_artifacts)
    return output


def validate_research_wire_result(wire, binding):
    req = ApplicationRequest.model_validate(wire['application_request'])
    return validate_research_output(req, HandlerResult.model_validate(wire['application']), binding)


class ResearchHandler:
    """Wrap existing adapters; persist the exact bound contract in next-1 diagnostics."""
    def __init__(self, handler, binding_provider):
        self.handler = handler
        self.binding_provider = binding_provider

    def __call__(self, req, input_path, directory, context):
        binding = self.binding_provider(req)
        envelope = research_envelope(req, binding)
        try:
            output = self.handler(req, input_path, directory, context)
        except Exception as exc:
            from .runner import BudgetStop
            elapsed = context.clock()-context.start
            if elapsed >= context.budget.seconds and not context.stop_events:
                context.stop_events.append(dict(kind='TIME_BUDGET', elapsed_seconds=elapsed,
                    deadline_elapsed_seconds=context.budget.seconds, new_work_after_stop=False))
            partial = isinstance(exc, BudgetStop) or bool(context.stop_events)
            status = 'PARTIAL_BUDGET' if partial else 'FAILED'
            target = (expected_target(req, binding.target_request, binding.target_spec_path, None)
                      if req.algorithm_mode == 'E2' else None)
            return_failure = HandlerResult(execution_status=status,
                algorithm_status='RESEARCH_HANDLER_STOP',
                reason=(context.stop_events[-1]['kind'] if context.stop_events else 'HANDLER_FAILED'),
                prediction=None, candidates=[], layers=[], actual_forward=context.forward_count,
                actual_backward=context.backward_count, actual_updates=context.update_count,
                runtime_seconds=elapsed, stop_events=context.stop_events,
                source_artifacts={}, diagnostics={'research_contract':envelope, 'target_contract':target})
            return HandlerOutput(return_failure, {})
        output.result.diagnostics['research_contract'] = envelope
        validate_research_output(req, output.result, binding)
        return output
