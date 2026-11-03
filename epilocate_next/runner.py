"""Thin injected-handler adapter; no HSPI/CT-FM code or implicit model loading."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import time
from .contracts import ApplicationRequest, HandlerResult, validate_output

class BudgetStop(RuntimeError):
    pass

class HandlerContext:
    """One counting boundary. Supply the existing supervisor guard for real use.

    Algorithms call these at their actual computation boundary; do not also
    count the same operation via a second model hook. No device lock is created.
    """
    def __init__(self, budget, guard=None, clock=time.monotonic):
        self.budget=budget;self.guard=guard;self.clock=clock;self.start=clock()
        self.forward_count=0;self.backward_count=0;self.update_count=0;self.stop_events=[]
    def _step(self, field, maximum):
        elapsed=self.clock()-self.start
        if self.stop_events:raise BudgetStop('STOP_ALREADY_RECORDED')
        kind=None
        if elapsed>=self.budget.seconds:kind='TIME_BUDGET'
        elif getattr(self,field)>=maximum:kind=field.upper().replace('_COUNT','')+'_BUDGET'
        if kind:
            self.stop_events.append(dict(kind=kind,elapsed_seconds=elapsed,deadline_elapsed_seconds=self.budget.seconds if kind=='TIME_BUDGET' else elapsed,new_work_after_stop=False))
            raise BudgetStop(kind)
        if self.guard:
            if field=='forward_count':self.guard.before_forward()
            elif field=='backward_count':self.guard.before_backward()
            else:self.guard.check()
        setattr(self,field,getattr(self,field)+1)
    def forward(self):self._step('forward_count',self.budget.forward)
    def backward(self):self._step('backward_count',self.budget.backward)
    def update(self):self._step('update_count',self.budget.updates)

@dataclass
class HandlerOutput:
    result: HandlerResult
    assets: dict[str,bytes]

@dataclass
class ApplicationOutput:
    result: dict
    assets: dict[str,tuple[bytes,str]]

class ApplicationRunner:
    def __init__(self, handlers, output_root, *, permit_real=False, context_factory=None, model_id=None, hardware=None):
        self.handlers=handlers;self.output_root=Path(output_root);self.permit_real=permit_real;self.context_factory=context_factory
        if permit_real and (not model_id or not hardware):raise ValueError('REAL_WORKER_IDENTITY_REQUIRED')
        self.model_id=model_id
        self.hardware=hardware or {'accelerator':'INJECTED','max_concurrent_jobs':1}
    def run(self, claim, input_path, _temporary_output):
        req=ApplicationRequest.model_validate(claim['job_parameters']['application'])
        if req.execution_mode!='SYNTHETIC' and (not self.permit_real or self.context_factory is None):raise ValueError('REAL_APPLICATION_NOT_ADMITTED')
        if hashlib.sha256(Path(input_path).read_bytes()).hexdigest()!=req.input.input_sha256:raise ValueError('APPLICATION_INPUT_HASH_MISMATCH')
        if claim['model_version']['checkpoint_sha256']!=req.model.checkpoint_sha256 or claim['case_id']!=req.input.case_id or claim['job_parameters']['kind']!='ALGORITHM':raise ValueError('APPLICATION_CLAIM_MISMATCH')
        handler=self.handlers.get(req.algorithm_mode)
        if handler is None:raise ValueError('ALGORITHM_HANDLER_NOT_INSTALLED')
        for ident in [claim['job_id'],claim['attempt_id']]:
            if not ident or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in ident):raise ValueError('UNSAFE_JOB_ID')
        self.output_root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.output_root.is_symlink():raise ValueError('UNSAFE_OUTPUT_ROOT')
        # One immutable directory per Job. New attempt IDs cannot re-run it.
        directory=self.output_root/claim['job_id'];directory.mkdir(mode=0o700,exist_ok=False)
        context=self.context_factory(req) if self.context_factory else HandlerContext(req.budget)
        if req.execution_mode=='LIVE' and context.guard is None:raise ValueError('REAL_SUPERVISOR_GUARD_REQUIRED')
        start=time.monotonic()
        try:
            output=handler(req,Path(input_path),directory,context)
        except Exception as exc:
            partial=isinstance(exc,BudgetStop)
            output=HandlerOutput(HandlerResult(execution_status='PARTIAL_BUDGET' if partial else 'FAILED',algorithm_status='APPLICATION_BUDGET_STOP' if partial else 'HANDLER_EXCEPTION',reason='BUDGET_STOP' if partial else 'HANDLER_EXCEPTION',prediction=None,candidates=[],layers=[],actual_forward=context.forward_count,actual_backward=context.backward_count,actual_updates=context.update_count,runtime_seconds=time.monotonic()-start,stop_events=context.stop_events,source_artifacts={},diagnostics={}),{})
        result=validate_output(req,output.result)
        if (result.actual_forward,result.actual_backward,result.actual_updates)!=(context.forward_count,context.backward_count,context.update_count):raise ValueError('HANDLER_CALL_COUNT_MISMATCH')
        if set(output.assets)!={l.asset_id for l in result.layers}:raise ValueError('HANDLER_ASSET_SET_MISMATCH')
        for layer in result.layers:
            data=output.assets[layer.asset_id]
            if len(data)<24 or data[:8]!=b'\x89PNG\r\n\x1a\n' or struct.unpack('>II',data[16:24])!=(layer.width,layer.height):raise ValueError('NATIVE_PNG_DIMENSION_MISMATCH')
            with (directory/layer.asset_id).open('xb') as stream:stream.write(data)
        wire=dict(contract_version='next-1',kind='ALGORITHM',source={'LIVE':'LIVE_CASE','PRECOMPUTED':'PRECOMPUTED','SYNTHETIC':'SYNTHETIC'}[req.execution_mode],case_id=req.input.case_id,slice_id=req.input.slice_id,model_id=req.model.model_id,model_version=req.model.checkpoint_sha256,preprocessing_version=req.model.preprocessing_version,protocol_id=req.model.protocol_id,application_request=req.model_dump(mode='json'),application=result.model_dump(mode='json'))
        raw=json.dumps(wire,allow_nan=False,sort_keys=True).encode()
        total=len(raw)+sum(p.stat().st_size for p in directory.rglob('*') if p.is_file())
        if any(p.is_symlink() for p in directory.rglob('*')) or total>req.budget.output_bytes:raise ValueError('APPLICATION_OUTPUT_BUDGET')
        with (directory/'result.json').open('xb') as stream:stream.write(raw)
        (directory/'result.json').chmod(0o600)
        return ApplicationOutput(wire,{name:(data,'image/png') for name,data in output.assets.items()})
