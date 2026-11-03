"""Existing E2 loaders + existing ChildGuard, never creates authorization/queue.

Import is inert. Only a chief-dispatched caller supplies the admitted guard and
the SHA-bound per-Job binding. No additional forward audits or preprocessing.
"""
from dataclasses import dataclass
import hashlib
import importlib
import json
from pathlib import Path
import sys
import types
from .contracts import ApplicationRequest
from .e2_adapter import E2HandlerAdapter, PreparedBinding
from .runner import ApplicationRunner, HandlerContext
from worker.next_application import run_one_application


def locked_json(reference):
    path=Path(reference['path'])
    if path.is_symlink():raise ValueError('BOUND_METADATA_SYMLINK')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=reference['sha256']:raise ValueError('BOUND_METADATA_SHA_MISMATCH')
    return json.loads(raw)


def localization_modules(root,lock):
    root=Path(root).resolve()
    for name,expected in lock['module_sha256'].items():
        if hashlib.sha256((root.parent/name).read_bytes()).hexdigest()!=expected:raise ValueError('LOC_SOURCE_DRIFT:'+name)
    alias='_epinext_loc_'+lock['core_sha256'][:16]
    package=types.ModuleType(alias);package.__path__=[str(root)];sys.modules[alias]=package
    return tuple(importlib.import_module(alias+'.'+name) for name in ('first_real_e1_e2','e2_handler_v4','e2_request_v4'))


@dataclass(frozen=True)
class ExistingE2Binding:
    job_id: str
    application_request: dict
    prepared_delivery: dict
    preparation_config: dict
    scientific_request: dict
    loc_dependency_lock: dict
    localization_root: Path
    integration_bridge_source: Path
    case_index: int
    mapping_qa_sha256: str
    reuse_stage1: dict | None = None


def build_existing_e2_runner(binding,guard,output_root,*,modules=None,purpose='E2_Q_THREE_FIXED_SLICES_V4'):
    """Called inside admission, before download/weight load. Inject modules in QA."""
    guard.check()
    req=ApplicationRequest.model_validate(binding.application_request)
    if req.execution_mode!='LIVE' or req.algorithm_mode!='E2' or binding.case_index not in (1,2,3):raise ValueError('EXPLICIT_EXISTING_E2_LIVE_BINDING_REQUIRED')
    lock=locked_json(binding.loc_dependency_lock)
    first,core,requests=modules or localization_modules(binding.localization_root,lock)
    scientific=locked_json(binding.scientific_request)
    if scientific.get('profile')!=purpose:raise ValueError('LIVE_SCIENTIFIC_PROFILE_MISMATCH')
    config=requests.config_from_request(scientific)
    if config.sha256()!=req.config_sha256 or lock['core_sha256']!=scientific['source_binding']['core_sha256']:raise ValueError('LIVE_CONFIG_CORE_BINDING_MISMATCH')
    cache={}
    def prepare(request,input_path):
        guard.check()
        if 'inputs' not in cache:
            delivery,_,preprocess,inputs=first.consume_inputs(binding.prepared_delivery['path'],binding.prepared_delivery['sha256'],binding.preparation_config['path'],binding.preparation_config['sha256'])
            if delivery['checkpoint_sha256']!=request.model.checkpoint_sha256 or delivery['preprocess_sha256']!=request.model.preprocessing_sha256:raise ValueError('LIVE_DELIVERY_MODEL_PREPROCESS_MISMATCH')
            cache.update(delivery=delivery,preprocess=preprocess,inputs=inputs)
        selected=[v for v in cache['inputs'] if v[0]['case_index']==binding.case_index]
        if len(selected)!=1:raise ValueError('LIVE_SELECTED_INPUT_MISSING')
        record,prepared,geometry=selected[0]
        if record['source_ct_sha256']!=request.input.input_sha256 or record['geometry']['sha256']!=request.input.geometry_ledger_sha256 or binding.mapping_qa_sha256!=request.input.mapping_qa_sha256:raise ValueError('LIVE_SOURCE_GEOMETRY_BINDING_MISMATCH')
        # Case/Study/Series keys on ApplicationRequest are application identities,
        # not rewritten original DICOM UIDs. The per-Job binding is chief supplied.
        return PreparedBinding(prepared,geometry,record['source_ct_sha256'],cache['delivery']['preprocess_sha256'],record['geometry']['sha256'],binding.mapping_qa_sha256)
    def model(request):
        guard.check()
        if 'model' not in cache:
            bridge=first.baseline_source(binding.integration_bridge_source)
            classifier=bridge.load_verified_resnet18(Path(cache['delivery']['checkpoint_path']),request.model.checkpoint_sha256)
            cache['model']=first.DifferentiablePreparedModel(classifier,cache['preprocess'])
        return cache['model']
    def reuse(request):
        guard.check();value=locked_json(binding.reuse_stage1)
        return value,core.digest(value)
    adapter=E2HandlerAdapter(core.run_prepared_e2,prepare,model,lambda _:config,model_adapter_sha256=lock['module_sha256']['epi_next/first_real_e1_e2.py'],stop_exception=core.BudgetStopped,reuse_provider=reuse if binding.reuse_stage1 else None,branch_seconds=scientific['limits'].get('per_branch_seconds'))
    runner=ApplicationRunner({'E2':adapter},output_root,permit_real=True,context_factory=lambda q:HandlerContext(q.budget,guard),model_id=req.model.model_id,hardware={'accelerator':'CPU','max_concurrent_jobs':1})
    delegate=runner.run
    def bound_run(claim,input_path,temporary):
        if claim['job_id']!=binding.job_id or ApplicationRequest.model_validate(claim['job_parameters']['application']).model_dump()!=req.model_dump():raise ValueError('LIVE_JOB_REQUEST_BINDING_MISMATCH')
        return delegate(claim,input_path,temporary)
    runner.run=bound_run
    return runner


def run_existing_e2_job(config,binding,guard,output_root,*,client=None,download_transport=None,modules=None):
    """Actual one-Job entry. Chief owns ChildGuard.from_environment/complete."""
    guard.check();guard.begin_case(binding.job_id)
    try:
        runner=build_existing_e2_runner(binding,guard,output_root,modules=modules)
        return run_one_application(config,runner,client=client,download_transport=download_transport)
    finally:
        guard.end_case()


def run_existing_selected_fidelity(binding,guard,output_root,*,modules=None):
    """Concrete separate 5F/0B/0-update entry, not a new E2 optimization run."""
    from .e2_adapter import CoreBudgetAdapter
    from .e2_assets import save_json
    req=ApplicationRequest.model_validate(binding.application_request)
    if (req.budget.forward,req.budget.backward,req.budget.updates)!=(5,0,0) or req.budget.seconds>120 or binding.case_index!=3 or binding.reuse_stage1 is None:
        raise ValueError('EXACT_SELECTED_FIDELITY_SCOPE_REQUIRED')
    directory=Path(output_root);directory.mkdir(parents=True,exist_ok=False,mode=0o700)
    guard.check();guard.begin_case(binding.job_id)
    context=HandlerContext(req.budget,guard)
    try:
        lock=locked_json(binding.loc_dependency_lock)
        first,core,requests=modules or localization_modules(binding.localization_root,lock)
        scientific=locked_json(binding.scientific_request)
        runner=build_existing_e2_runner(binding,guard,directory,modules=(first,core,requests),purpose='P1_SELECTED_MASK_FIDELITY_V4')
        adapter=runner.handlers['E2'];prepared=adapter.prepare(req,None).prepared
        payload,canonical_sha=adapter.reuse_provider(req)
        if canonical_sha!=scientific['scope']['reuse_payload_canonical_sha256']:raise ValueError('FIDELITY_REUSE_CANONICAL_SHA_MISMATCH')
        identity=dict(classifier_kind='2D_SLICE_CLASSIFIER',evidence_type='APPROVED_DEVELOPMENT',model_sha256=req.model.checkpoint_sha256,preprocessing_sha256=req.model.preprocessing_sha256,model_adapter_sha256=adapter.model_adapter_sha256,reused_stage1_sha256=canonical_sha)
        result=core.selected_fidelity(prepared,adapter.model(req),adapter.config(req),payload,identity=identity,budget=CoreBudgetAdapter(context,core.BudgetStopped),allow_real=True)
        result['application_loading_entry']='run_existing_selected_fidelity'
        result['stop_events']=context.stop_events
        result['source_binding']=dict(scientific_request_sha256=binding.scientific_request['sha256'],prepared_delivery_sha256=binding.prepared_delivery['sha256'],reuse_stage1_sha256=binding.reuse_stage1['sha256'])
        save_json(directory,'selected-fidelity.json',result,req.budget.output_bytes)
        return result
    finally:guard.end_case()
