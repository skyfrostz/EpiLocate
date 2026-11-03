"""E2-R fixed saved-mask readout, not optimization or new dispatch machinery.

INT supplies hash-verified in-memory data, existing meter and approved loader.
No GT, CT loader, weights loader, unmetered forward or automatic retry here.
"""
import hashlib
import json
import numpy as np
import torch
from .e2_handler_v4 import check_input, import_stage1, input_binding, bbox, cost_delta, digest
from .first_real_e1_e2 import native_lookup
from .hspi_core_v3 import upsample, frozen_classifier, Budget, BudgetStopped
from .target_contract_v5 import check_identity, resolve, response_metrics, logits_array

PERCENTAGES = (5, 10, 20)
READOUT_POLICY = {
    'percentages': [5,10,20], 'denominator': 'prepared.valid_mask true pixels on MODEL grid',
    'rounding': 'floor(valid_pixels*integer_percent/100), never round up',
    'interpolation': 'torch float32 bilinear align_corners=false antialias=false',
    'rank_ties': 'descending upsampled soft value then ascending row-major flat index',
    'random': 'numpy Generator(PCG64(seed17)) single permutation of ascending valid flat indices; nested prefixes',
    'fill': 'scalar 0 before frozen RGB normalization; exterior valid_support preserved',
    'peak': 'nearest whole argmax coarse cell, intersect same valid_support',
    'GT_selection': False,
}
NAMES = ['original','full_mask_keep','peak_patch_keep','peak_patch_remove'] + [
    f'{method}_{percent}_{action}' for percent in PERCENTAGES
    for method in ('ranked','random') for action in ('keep','remove')]


def array_sha(value):
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def construct_regions(soft, peak, valid):
    """Exactly equal cardinality for each control, including sparse/odd FOVs."""
    soft = np.asarray(soft); peak = np.asarray(peak); valid = np.asarray(valid)
    if soft.dtype != np.float32 or valid.dtype != np.bool_ or peak.dtype != np.bool_ or soft.shape != valid.shape or peak.shape != valid.shape or not valid.any() or not np.isfinite(soft).all():
        raise ValueError('READOUT_GRID_INVALID')
    indices = np.flatnonzero(valid)
    ordered = indices[np.argsort(-soft.ravel()[indices], kind='stable')]
    random_order = np.random.Generator(np.random.PCG64(17)).permutation(indices)
    regions = {'original':np.ones(soft.shape, np.float32), 'full_mask_keep':soft,
        'peak_patch_keep':peak & valid, 'peak_patch_remove':(~peak) & valid}
    for percent in PERCENTAGES:
        count = len(indices)*percent//100
        for method, order in (('ranked',ordered), ('random',random_order)):
            region = np.zeros(valid.size, dtype=bool); region[order[:count]] = True
            region = region.reshape(valid.shape)
            regions[f'{method}_{percent}_keep'] = region
            regions[f'{method}_{percent}_remove'] = valid & ~region
    return regions


def check_saved(raw, request, payload):
    """Require exact historical file and science binding, not name-only reuse."""
    reuse = request['saved_fidelity']
    if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != reuse['file_sha256']:
        raise ValueError('SAVED_FIDELITY_FILE_MISMATCH_NO_FALLBACK')
    saved = json.loads(raw)
    if saved.get('schema') != 'E2_SELECTED_FIDELITY_V4' or saved.get('status') != 'SUCCESS' or saved.get('selected_epoch') != payload['best']['epoch'] or saved.get('selected_cell') != int(np.asarray(payload['best']['mask']).argmax()) or saved.get('source_binding') != reuse['source_binding'] or saved.get('cost',{}).get('forward') != 5 or any(saved.get('cost',{}).get(k) != 0 for k in ('backward','optimizer_steps','extra_autograd')):
        raise ValueError('SAVED_FIDELITY_SOURCE_INCOMPATIBLE')
    rows = saved['responses']
    if not np.array_equal(logits_array(rows['original']['logits']), logits_array(payload['baseline_logits'])) or not np.array_equal(logits_array(rows['full_mask_keep']['logits']), logits_array(payload['best']['logits'])):
        raise ValueError('SAVED_FIDELITY_BASELINE_OR_SOFT_MISMATCH')
    return {k:logits_array(rows[k]['logits']).tolist() for k in NAMES[:4]}


def run_readout(prepared, model, geometry, config, payload, *, request,
                identity, saved_fidelity_bytes, adapter_predict, budget=None, allow_real=False):
    """16 objects; required compatible 4-object reuse + 2 checks => 14 new F.

    adapter_predict is one unmetered-call callable whose single underlying
    predictor invocation is charged HERE, just like the differentiable f.
    It must not implement retry, batching extra objects, or internal audits.
    The INT parent meters loading-to-cleanup against the requested 120 seconds.
    """
    from .e2_readout_request_v5 import validate_request_value
    validate_request_value(request, synthetic=prepared.scope=='SYNTHETIC')
    check_input(prepared, config, identity, allow_real)
    check_identity(request['target_contract'], identity)
    if allow_real and budget is None: raise ValueError('REAL_CALL_REQUIRES_EXTERNAL_METER')
    if torch.get_num_threads() != 1 or any(t.device.type != 'cpu' for t in [*model.parameters(),*model.buffers()]):
        raise ValueError('READOUT_CPU1_REQUIRED')
    if config.sha256() != request['core_config_sha256'] or input_binding(prepared, identity) != request['input_binding']:
        raise ValueError('READOUT_INPUT_OR_CONFIG_MISMATCH')
    stage = import_stage1(payload, prepared, config, identity)
    if identity.get('reused_stage1_sha256') != request['reuse_payload_canonical_sha256']:
        raise ValueError('READOUT_REQUEST_SELECTION_SHA_MISMATCH')
    if stage['best'] is None or (payload.get('case_index'),stage['best']['epoch'],stage['cell']) != (3,3604,43):
        raise ValueError('ONLY_FIXED_CASE3_EPOCH3604_CELL43')
    resolved = resolve(request['target_contract'], payload['baseline_logits'])
    if resolved['explanation_target']['resolved_class'] != 1: raise ValueError('E2_R_FIXED_ORIGINAL_TARGET1_REQUIRED')
    iy, ix = native_lookup(geometry)
    if tuple(geometry['model_shape_yx']) != config.image_size: raise ValueError('GEOMETRY_MODEL_GRID_MISMATCH')
    if allow_real and identity.get('geometry_sha256') != request['geometry_sha256']:
        raise ValueError('EXACT_GEOMETRY_SHA_REQUIRED')
    cached = check_saved(saved_fidelity_bytes, request, payload)
    if not callable(adapter_predict): raise ValueError('SINGLE_FORWARD_ADAPTER_CHECK_REQUIRED')
    budget = Budget(max_forward=18,max_backward=0,seconds=120) if budget is None else budget
    before = budget.counts(); start = budget.clock()
    x = torch.from_numpy(prepared.image.copy())[None,None]
    valid = torch.from_numpy(prepared.valid_mask.copy())[None,None]
    soft = upsample(stage['best']['mask'],config.image_size,'bilinear',False)[0,0].numpy()
    regions = construct_regions(soft, stage['patch'].numpy(), prepared.valid_mask)
    rows = {}; checks = []; status = 'SUCCESS'; error = None

    def forward(fn):
        if budget.clock()-start >= 120 or budget.counts()['forward']-before['forward'] >= 14 or not budget.permits(forwards=1):
            raise BudgetStopped('READOUT_BUDGET_OR_DEADLINE')
        result = budget.forward_call(fn)
        # Count the in-flight call even if it overruns; parent guard supervises
        # process lifetime. Do not add another call after the deadline.
        if budget.clock()-start >= 120 or not budget.permits():
            raise BudgetStopped('READOUT_INFLIGHT_DEADLINE')
        return result

    try:
        with frozen_classifier(model), torch.no_grad():
            adapter_logits = np.asarray(forward(lambda:adapter_predict(prepared.image.copy())))
            if adapter_logits.shape not in ((2,),(1,2)): raise ValueError('NUMPY_ADAPTER_BINARY_LOGITS_REQUIRED')
            a = logits_array(adapter_logits.reshape(1,2))
            b = logits_array(forward(lambda:model(x)).detach().cpu().numpy())
            base = logits_array(cached['original'])
            checks = [{'kind':'numpy_vs_differentiable', 'max_abs':float(abs(a-b).max())},
                      {'kind':'current_vs_saved_original', 'max_abs':float(abs(b-base).max())}]
            if not np.allclose(a,b,atol=1e-6,rtol=0) or not np.allclose(b,base,atol=1e-6,rtol=0):
                raise ValueError('ADAPTER_OR_SAVED_MODEL_MISMATCH_NO_FRESH_FALLBACK')
            resolve(request['target_contract'], b)
            for name in NAMES:
                region = regions[name]
                masked = torch.where(valid, x*torch.from_numpy(region)[None,None], x)
                logits = cached.get(name)
                if logits is None:
                    logits = forward(lambda:model(masked)).detach().cpu().numpy()
                row = response_metrics(base, logits, 1)
                active = (region > 0) & prepared.valid_mask
                native = active[iy,ix]
                row.update(origin='REUSED_COMPATIBLE_5F_LOGITS' if name in cached else 'NEW_FORWARD',
                    region_sha256=array_sha(region), masked_input_sha256=array_sha(masked.numpy()),
                    valid_pixels=int(prepared.valid_mask.sum()), model_positive_pixels=int(active.sum()),
                    model_weight_sum=float(region[prepared.valid_mask].astype(np.float64).sum()),
                    model_bounds_yx_half_open=bbox(active), native_positive_pixels=int(native.sum()),
                    native_bounds_yx_half_open=bbox(native), model_region=region, native_region=region[iy,ix],
                    region_semantics='retained input weights; remove objects show complement within same FOV, not candidate area')
                if name.startswith(('ranked','random')):
                    percent = int(name.split('_')[1]); selected = regions[name.rsplit('_',1)[0]+'_keep']
                    row.update(selected_area_percent=percent, selected_pixels=int(selected.sum()),
                               selected_fraction=float(selected.sum()/prepared.valid_mask.sum()),
                               selected_region_sha256=array_sha(selected), selected_native_pixels=int(selected[iy,ix].sum()),
                               selected_region_status='NONEMPTY' if selected.any() else 'EMPTY_AREA_BUDGET_NO_PADDING')
                rows[name] = row
    except BudgetStopped as exc:
        status = 'PARTIAL_BUDGET'; error = str(exc)
    except Exception as exc:
        status = 'FAILED'; error = {'type':type(exc).__name__, 'message':str(exc)}
    return {'schema':'E2_READOUT_RESULT_V5', 'status':status, 'error':error,
        'target_contract':resolved, 'input_binding':input_binding(prepared,identity),
        'request_canonical_sha256':digest(request), 'core_config_sha256':config.sha256(),
        'source_binding':request['source_binding'], 'saved_fidelity_sha256':request['saved_fidelity']['file_sha256'],
        'selected_epoch':3604, 'selected_cell':43, 'readout_policy':READOUT_POLICY,
        'responses':rows, 'adapter_checks':checks, 'planned_objects':NAMES,
        'unrun_objects':[name for name in NAMES if name not in rows],
        'new_cost':cost_delta(before,budget.counts()), 'cumulative_meter_cost':budget.counts(),
        'historical_logits_reused':sum(row['origin']=='REUSED_COMPATIBLE_5F_LOGITS' for row in rows.values()),
        'GT_selection':False, 'clinical_validity':'NOT_ESTABLISHED',
        'selection_bias':'adaptive case3/epoch3604 from P1, mechanism exploration, not independent test'}
