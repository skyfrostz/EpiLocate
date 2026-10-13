"""Versioned explanation metadata/metrics; no model calls or legacy mutation."""
import copy
import hashlib
import json
from pathlib import Path
import numpy as np

CONTRACT_PATH = Path(__file__).parents[1]/'configs/explanation-target-contract-v5.json'
CONTRACT_SHA256 = 'd852001e0db9d52844c900d81251a19b8afb20000b0b3429de11e80bf90b647c'
SCHEMA = 'EPI_NEXT_EXPLANATION_TARGET_CONTRACT_V5'


def specification():
    raw = CONTRACT_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CONTRACT_SHA256:
        raise ValueError('TARGET_CONTRACT_SOURCE_DRIFT')
    return json.loads(raw)


def validate_metadata(metadata):
    spec = specification()
    if metadata.get('schema') != SCHEMA or metadata.get('prediction_scope') != 'SLICE':
        raise ValueError('V5_EXPLICIT_SLICE_CONTRACT_REQUIRED')
    labels = metadata.get('class_labels')
    if not isinstance(labels, list) or len(labels) != 2 or any(not isinstance(s, str) or not s for s in labels) or len(set(labels)) != 2:
        raise ValueError('ORDERED_BINARY_CLASS_MAP_REQUIRED')
    target = metadata.get('explanation_target', {})
    if not isinstance(target,dict) or set(target) != {'policy', 'declared_class'} or target['policy'] not in ('ORIGINAL_ARGMAX_FIXED', 'DECLARED_FIXED'):
        raise ValueError('EXPLICIT_FIXED_TARGET_POLICY_REQUIRED')
    if type(target['declared_class']) is not int or not 0 <= target['declared_class'] < len(labels):
        raise ValueError('DECLARED_CLASS_OUT_OF_RANGE')
    if metadata.get('loss_definition') != spec['loss_definition']:
        raise ValueError('LOSS_DEFINITION_MISMATCH')
    if 'source_label' not in metadata:
        raise ValueError('SOURCE_LABEL_MUST_BE_EXPLICIT_NULL_OR_REFERENCE')
    source = metadata['source_label']
    if source is not None:
        if not isinstance(source,dict) or set(source) != {'class_id', 'label', 'scope', 'provenance_sha256'}:
            raise ValueError('SOURCE_LABEL_PROVENANCE_REQUIRED')
        if type(source['class_id']) is not int or not 0 <= source['class_id'] < len(labels) or not isinstance(source['label'], str) or not source['label']:
            raise ValueError('SOURCE_LABEL_CLASS_INVALID')
        if source['scope'] not in ('SLICE', 'CASE', 'BAG', 'SOURCE_GROUP'):
            raise ValueError('SOURCE_LABEL_SCOPE_INVALID')
        _sha(source['provenance_sha256'])
    binding = metadata.get('model_binding', {})
    if not isinstance(binding,dict) or set(binding) != {'model_sha256', 'preprocessing_sha256', 'model_adapter_sha256', 'task_version'} or not isinstance(binding['task_version'], str) or not binding['task_version']:
        raise ValueError('MODEL_TASK_BINDING_REQUIRED')
    for key in ('model_sha256', 'preprocessing_sha256', 'model_adapter_sha256'):
        _sha(binding[key])
    return copy.deepcopy(metadata)


def _sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('SHA256_REQUIRED')


def check_identity(metadata, identity):
    validate_metadata(metadata)
    if any(metadata['model_binding'][k] != identity.get(k) for k in ('model_sha256', 'preprocessing_sha256', 'model_adapter_sha256')):
        raise ValueError('TARGET_MODEL_BINDING_MISMATCH')


def logits_array(logits):
    value = np.asarray(logits, dtype=np.float64)
    if value.shape != (1, 2) or not np.isfinite(value).all():
        raise ValueError('FINITE_BINARY_SLICE_LOGITS_REQUIRED')
    return value


def resolve(metadata, original_logits):
    result = validate_metadata(metadata)
    predicted = int(logits_array(original_logits)[0].argmax())
    target = result['explanation_target']
    resolved = predicted if target['policy'] == 'ORIGINAL_ARGMAX_FIXED' else target['declared_class']
    if target['declared_class'] != resolved:
        raise ValueError('DECLARED_RESOLVED_TARGET_MISMATCH')
    target['resolved_class'] = resolved
    result['predicted_class'] = predicted
    result['contract_sha256'] = CONTRACT_SHA256
    return result


def validate_persisted(request, result_metadata, original_logits):
    if resolve(request, original_logits) != result_metadata:
        raise ValueError('PERSISTED_TARGET_CONTRACT_MISMATCH')


def response_metrics(original_logits, logits, resolved_class):
    base = logits_array(original_logits); value = logits_array(logits)
    if type(resolved_class) is not int or resolved_class not in (0, 1):
        raise ValueError('FIXED_TARGET_REQUIRED')
    def pair(z):
        p = np.exp(z-z.max()); p /= p.sum()
        return float(z[0,resolved_class]-z[0,1-resolved_class]), float(p[0,resolved_class])
    bm, bp = pair(base); margin, probability = pair(value)
    return {'logits':value.tolist(), 'fixed_target':resolved_class,
        'all_logits_squared_difference':float(((base-value)**2).sum()),
        'target_logit_margin':margin, 'margin_drop':bm-margin,
        'target_probability':probability, 'probability_drop':bp-probability,
        'perturbed_predicted_class':int(value[0].argmax())}
