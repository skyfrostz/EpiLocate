"""Calls the LOC-owned core; only application metering, serialization and PNGs."""
import time
from dataclasses import dataclass
from .runner import BudgetStop
from .e2_assets import output_from_saved_e2, save_compressed_json

@dataclass(frozen=True)
class PreparedBinding:
    prepared: object
    geometry: dict
    source_sha256: str
    preprocessing_sha256: str
    geometry_ledger_sha256: str
    mapping_qa_sha256: str

class CoreBudgetAdapter:
    def __init__(self,context,stop_exception=BudgetStop):
        self.context=context;self.reason=None;self.clock=context.clock;self.stop_exception=stop_exception
    def permits(self,forwards=0,backwards=0):
        c=self.context;b=c.budget;elapsed=c.clock()-c.start
        kind=None
        if elapsed>=b.seconds:kind='TIME_BUDGET'
        elif c.forward_count+forwards>b.forward:kind='FORWARD_BUDGET'
        elif c.backward_count+backwards>b.backward:kind='BACKWARD_BUDGET'
        elif backwards and c.update_count>=b.updates:kind='UPDATE_BUDGET'
        if kind:
            self.reason='TIMEOUT' if kind=='TIME_BUDGET' else kind
            if not c.stop_events:c.stop_events.append(dict(kind=kind,elapsed_seconds=elapsed,deadline_elapsed_seconds=b.seconds if kind=='TIME_BUDGET' else elapsed,new_work_after_stop=False))
        return self.reason is None
    def forward_call(self,fn):self.context.forward();return fn()
    def backward_call(self,fn):
        self.context.backward();value=fn()
        # An in-flight backward may finish after deadline. Count it, then fence
        # the next optimizer step using the LOC-owned stop exception.
        if not self.permits():raise self.stop_exception(self.reason)
        return value
    def did_optimizer_step(self):
        # Called after an admitted optimizer step completed, even if it crossed
        # deadline. Do not erase completed work by re-checking time here.
        self.context.update_count+=1
    def counts(self):
        c=self.context
        return dict(forward=c.forward_count,backward=c.backward_count,extra_autograd=0,optimizer_steps=c.update_count,elapsed_seconds=c.clock()-c.start,stop_reason=self.reason)

class E2HandlerAdapter:
    """Providers are bound by chief/LOC/DATA; no file/weight loader is inferred."""
    def __init__(self,run_prepared_e2,prepared_provider,model_provider,config_provider,*,model_adapter_sha256,stop_exception=BudgetStop,reuse_provider=None,branch_seconds=None):
        self.core=run_prepared_e2;self.prepare=prepared_provider;self.model=model_provider;self.config=config_provider;self.model_adapter_sha256=model_adapter_sha256;self.stop_exception=stop_exception;self.reuse_provider=reuse_provider;self.branch_seconds=branch_seconds
    def __call__(self,req,input_path,output_dir,context):
        if req.algorithm_mode!='E2' or req.execution_mode=='PRECOMPUTED':raise ValueError('E2_CORE_ONLY_EXPLICIT_2D_EXECUTION')
        binding=self.prepare(req,input_path);prepared=binding.prepared;geometry=binding.geometry
        prepared.validate()
        if (req.execution_mode=='SYNTHETIC')!=(prepared.scope=='SYNTHETIC'):raise ValueError('E2_SOURCE_SCOPE_MISMATCH')
        if (binding.source_sha256!=req.input.input_sha256 or binding.preprocessing_sha256!=req.model.preprocessing_sha256
                or binding.geometry_ledger_sha256!=req.input.geometry_ledger_sha256 or binding.mapping_qa_sha256!=req.input.mapping_qa_sha256
                or tuple(prepared.image.shape)!=req.input.model_shape or prepared.preprocess_id!=req.model.preprocessing_version
                or prepared.task_definition_id!=req.task.definition_id or len(req.task.class_labels)!=2):raise ValueError('PREPARED_INPUT_BINDING_MISMATCH')
        if tuple(geometry['native_shape_rc'])!=req.input.native_shape_zyx[1:] or geometry['native_slice_index_zero_based']!=req.input.native_slice_index:raise ValueError('E2_NATIVE_GEOMETRY_MISMATCH')
        config=self.config(req)
        if config.sha256()!=req.config_sha256:raise ValueError('E2_CONFIG_SHA_MISMATCH')
        start=time.monotonic();identity=dict(classifier_kind='2D_SLICE_CLASSIFIER',evidence_type='SYNTHETIC' if req.execution_mode=='SYNTHETIC' else 'APPROVED_DEVELOPMENT',model_sha256=req.model.checkpoint_sha256,preprocessing_sha256=req.model.preprocessing_sha256,model_adapter_sha256=self.model_adapter_sha256)
        reused=None
        if self.reuse_provider:
            reused,reuse_sha=self.reuse_provider(req)
            identity['reused_stage1_sha256']=reuse_sha
        sequence=[0]
        def persist(kind,value):
            sequence[0]+=1
            name='trace.jsonl.gz' if kind=='trace' else f'{kind}-{sequence[0]}.json.gz'
            save_compressed_json(output_dir,name,value,req.budget.output_bytes//2,append=kind=='trace')
        raw=self.core(prepared,self.model(req),geometry,config,identity=identity,budget=CoreBudgetAdapter(context,self.stop_exception),allow_real=req.execution_mode=='LIVE' and context.guard is not None,reused_stage1=reused,branch_seconds=self.branch_seconds,
                      trace_sink=lambda row:persist('trace',row),stage_sink=lambda row:persist('stage',row),checkpoint_sink=lambda grid,stage,cp:persist('checkpoint',dict(grid=grid,stage=stage,checkpoint=cp)))
        return output_from_saved_e2(req,raw,output_dir,context,start)
