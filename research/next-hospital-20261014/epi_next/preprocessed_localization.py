"""Explicit in-memory E1/E2 preparation; never reads data or invents labels."""
from dataclasses import dataclass
import hashlib
import re
import json
import time
from dataclasses import asdict
import numpy as np
import torch
from .hspi import hspi_reference
from .localization import occlusion_2d, _logits, fixed_target_response


@dataclass(frozen=True)
class Prepared2DInput:
    image: np.ndarray
    valid_mask: np.ndarray
    input_sha256: str
    preprocess_id: str
    task_definition_id: str
    split: str = 'synthetic'
    scope: str = 'SYNTHETIC'
    approval_receipt_sha256: str = ''

    def validate(self):
        x=np.asarray(self.image);v=np.asarray(self.valid_mask)
        if x.ndim!=2 or not np.issubdtype(x.dtype,np.floating) or not np.isfinite(x).all():raise ValueError('finite floating preprocessed H,W required')
        if v.dtype!=np.bool_ or v.shape!=x.shape or not v.any():raise ValueError('explicit valid support required')
        if hashlib.sha256(np.ascontiguousarray(x).tobytes()).hexdigest()!=self.input_sha256:raise ValueError('prepared input SHA mismatch')
        if not self.preprocess_id or not self.task_definition_id:raise ValueError('preprocessing and externally defined task identity required')
        if self.scope=='SYNTHETIC':
            if self.split!='synthetic':raise ValueError('synthetic scope cannot relabel real split')
        elif self.scope=='APPROVED_PREPROCESSED':
            if self.split not in ('train','observed_validation') or not re.fullmatch('[0-9a-f]{64}',self.approval_receipt_sha256):raise ValueError('nonsealed split and supplied approval receipt required')
        else:raise ValueError('explicit input scope required')


def run_prepared_e1_e2(prepared,predict_numpy,differentiable_model,*,target,e1_options,e2_config,agreement_atol=1e-6):
    """Adapters must include exactly the same already-defined normalization.

    No DICOM loading, label construction, patient selection or authorization is
    performed. A caller-supplied approval hash is provenance, not a new permit.
    Two adapter consistency forwards are counted before algorithm execution.
    """
    prepared.validate()
    if isinstance(target,(bool,np.bool_)) or not isinstance(target,(int,np.integer)) or target<0:raise ValueError('fixed integer target required')
    target=int(target)
    if not np.isfinite(agreement_atol) or agreement_atol<0:raise ValueError('invalid agreement tolerance')
    if any(t.device.type!='cpu' for t in [*differentiable_model.parameters(),*differentiable_model.buffers()]):raise ValueError('CPU-only execution scope')
    if any(k in e1_options for k in ('predict','image','valid_mask','target')):raise ValueError('E1 options cannot replace locked input or target')
    e2_config.validate()
    x=np.asarray(prepared.image).copy();v=np.asarray(prepared.valid_mask).copy()
    started=time.monotonic()
    e1_config=dict(e1_options)
    if isinstance(e1_config.get('fill'),np.ndarray):
        f=np.ascontiguousarray(e1_config['fill'])
        e1_config['fill']=dict(dtype=str(f.dtype),shape=list(f.shape),sha256=hashlib.sha256(f.tobytes()).hexdigest())
    config=dict(target=target,e1=e1_config,e2=asdict(e2_config),adapter_agreement_atol=agreement_atol)
    config_sha=hashlib.sha256(json.dumps(config,sort_keys=True,allow_nan=False).encode()).hexdigest()
    out=dict(experiment='EPI-NEXT-PREPARED-E1-E2-v1',status='FAILED',reason='',scope=prepared.scope,input_sha256=prepared.input_sha256,preprocess_id=prepared.preprocess_id,task_definition_id=prepared.task_definition_id,split=prepared.split,actual_model_calls=0,config=config,config_sha256=config_sha,input_shape_yx=list(x.shape),input_dtype=str(x.dtype),valid_mask_sha256=hashlib.sha256(v.tobytes()).hexdigest(),approval_receipt_sha256=prepared.approval_receipt_sha256 or None,label_creation=False,clinical_validity='NOT_ESTABLISHED')
    old_modes=[(module,module.training) for module in differentiable_model.modules()]
    try:
        differentiable_model.eval()
        out['actual_model_calls']+=1;a=_logits(predict_numpy(x.copy()))
        fixed_target_response(a,a,target)
        out['actual_model_calls']+=1
        with torch.no_grad():
            logits=differentiable_model(torch.from_numpy(x.copy())[None,None])
            if logits.ndim!=2 or logits.shape[0]!=1:raise ValueError('expected classifier [1,K] logits')
            b=_logits(logits.detach().cpu().numpy()[0])
        if a.shape!=b.shape or not np.allclose(a,b,atol=agreement_atol,rtol=0):
            out.update(reason='PREPROCESS_ADAPTER_MISMATCH',adapter_logits=[a.tolist(),b.tolist()]);return out
        out['adapter_agreement_max_abs']=float(abs(a-b).max())
        e1=occlusion_2d(predict_numpy,x,v,target,**e1_options)
        out['actual_model_calls']+=e1['model_calls'];out['E1']=e1
        from .verification_vnext import numerical_witness
        out['E1_numerical_diagnosis']=numerical_witness(e1)
        if e1['status']=='FAILED':
            out.update(reason='E1_FAILED');return out
        e2=hspi_reference(differentiable_model,torch.from_numpy(x.copy())[None,None],e2_config,torch.from_numpy(v.copy()))
        out['actual_model_calls']+=e2['model_calls'];out['E2']=e2
        out.update(status='FAILED' if e1['status']=='FAILED' or e2['status']=='FAILED' else 'OK',reason='EXECUTED_NOT_CLINICALLY_VALIDATED',target=int(target),E2_target_semantics='FULL_LOGITS_CONSISTENCY_NOT_FIXED_TARGET_MARGIN')
        if out['status']!='FAILED' and (e1['status']=='PARTIAL_BUDGET' or e2['status']=='PARTIAL_BUDGET'):out.update(status='PARTIAL_BUDGET',reason='ALGORITHM_RESOURCE_LIMIT')
    except Exception as exc:out.update(status='FAILED',reason='PREPARED_ADAPTER_FAILURE',error=str(exc))
    finally:
        out['elapsed_seconds']=time.monotonic()-started
        for module,mode in old_modes:module.training=mode
    return out
