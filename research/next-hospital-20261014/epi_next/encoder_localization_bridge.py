"""Full-input frozen encoder -> case head -> residual localization bridge.

No model/data loading, downloads, cache, GPU/MPS scheduling or GT interface.
The caller supplies already instantiated models and approved preprocessed arrays.
"""
from dataclasses import dataclass
import hashlib
import re
import numpy as np
import torch
import torch.nn.functional as F
from .residual_localization import residual_input_occlusion_3d


def head_state_sha256(head):
    h=hashlib.sha256()
    for name,tensor in sorted(head.state_dict().items()):
        a=tensor.detach().cpu().contiguous().numpy()
        h.update((name+str(a.dtype)+str(a.shape)).encode());h.update(a.tobytes())
    return h.hexdigest()


def _hash(value,name):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value):raise ValueError(name+' must be SHA256')


@dataclass(frozen=True)
class HeadEvidence:
    status: str = 'SYNTHETIC'
    head_state_sha256: str = ''
    training_manifest_sha256: str = ''
    label_audit_sha256: str = ''
    task_definition_id: str = ''
    target_class_names: tuple = ()
    training_split: str = 'train'

    def validate(self,head,target):
        if self.status not in ('SYNTHETIC','TRAINED_VERIFIED'):raise ValueError('head must have explicit training evidence')
        if self.status=='TRAINED_VERIFIED':
            for field in ('head_state_sha256','training_manifest_sha256','label_audit_sha256'):_hash(getattr(self,field),field)
            if self.head_state_sha256!=head_state_sha256(head):raise ValueError('head state does not match verified training receipt')
            if self.training_split!='train' or not self.task_definition_id or len(self.target_class_names)!=head.linear.out_features or not all(self.target_class_names):raise ValueError('verified task labels and train-only provenance required')
        if isinstance(target,(bool,np.bool_)) or not isinstance(target,(int,np.integer)) or not 0<=target<head.linear.out_features:raise ValueError('fixed target must index head classes')


class EncoderResidualPredictor:
    """Each __call__ performs fresh extract+head+CAM, even for repeated input.

    Compatible with FrozenEncoderAdapter and CaseLinearHead. A supplied training
    receipt is checked for identity and completeness, not independently audited
    here; it does not by itself grant patient-data access or clinical validity.
    This bridge currently rejects all non-CPU models, reserving MPS scheduling
    to the separately authorized encoder workline.
    """
    def __init__(self,encoder,head,target,*,evidence=None,scope='SYNTHETIC',input_approval_sha256=None,contribution_map=None):
        self.encoder=encoder;self.head=head;self.target=target
        self.evidence=evidence or HeadEvidence();self.evidence.validate(head,target)
        if scope not in ('SYNTHETIC','APPROVED_PREPROCESSED'):raise ValueError('explicit input scope required')
        if scope=='APPROVED_PREPROCESSED':
            if self.evidence.status!='TRAINED_VERIFIED':raise ValueError('untrained/synthetic head cannot represent real F0/F1')
            _hash(input_approval_sha256,'input_approval_sha256')
        if any(t.device.type!='cpu' for m in (encoder,head) for t in [*m.parameters(),*m.buffers()]):raise ValueError('this bridge execution scope is CPU only')
        if not torch.isfinite(head.scale).all() or (head.scale<=0).any():raise ValueError('head scale must be positive finite')
        if contribution_map is None:
            from .encoder import class_contribution_map
            contribution_map=class_contribution_map
        self.contribution_map=contribution_map;self.scope=scope;self.calls=0;self.call_metadata=[]
        self.dtype=head.linear.weight.dtype
        self.head_sha=head_state_sha256(head)

    def __call__(self,volume):
        a=np.asarray(volume)
        if a.ndim!=3 or not np.issubdtype(a.dtype,np.floating) or not np.isfinite(a).all():raise ValueError('finite preprocessed ZYX floating input required')
        if head_state_sha256(self.head)!=self.head_sha:raise ValueError('head changed during localization')
        self.calls+=1
        before=self.encoder.actual_queries
        with torch.inference_mode():
            tensor=torch.as_tensor(np.ascontiguousarray(a),dtype=self.dtype)[None,None]
            features=self.encoder.extract(tensor,preserve_input_grad=False)
            logits=self.head(features)
            coarse=self.contribution_map(features,self.head,int(self.target))
            if logits.shape!=(1,self.head.linear.out_features) or coarse.shape!=(1,*features.shape[2:]):raise ValueError('unexpected logits/CAM shape')
            if not torch.isfinite(logits).all() or not torch.isfinite(coarse).all():raise ValueError('nonfinite head/CAM')
            expanded=F.interpolate(coarse[:,None],size=a.shape,mode='trilinear',align_corners=False)[0,0]
        if self.encoder.actual_queries-before!=1:raise ValueError('one full extraction required per prediction')
        self.call_metadata.append(dict(call=self.calls,encoder_queries=1,target=int(self.target),input_shape_zyx=list(a.shape),feature_shape_zyx=list(features.shape[2:]),coarse_shape_zyx=list(expanded.shape),interpolation='trilinear',align_corners=False,
             coordinate_space='MODEL_INPUT_GRID_ZYX',sampling_rule='feature_index=(input_index+0.5)*feature_size/input_size-0.5',native_dicom_mapping='NOT_VALIDATED',coarse_evidence_type='CAM_CONTRIBUTION',bias_in_coarse_map=False,
             cam_mean_plus_target_bias=float((coarse.mean()+self.head.linear.bias[self.target]).detach()),target_logit=float(logits[0,self.target].detach()),head_evidence=self.evidence.status,input_scope=self.scope))
        return logits[0].detach().cpu().numpy().copy(),expanded.detach().cpu().numpy().copy()

    def localize(self,volume,valid_mask,spacing_mm,config=None,fill=0.,**kwargs):
        before=self.calls;result=residual_input_occlusion_3d(self,volume,valid_mask,self.target,spacing_mm,config,fill,**kwargs)
        result['encoder_bridge']=dict(head_sha256=self.head_sha,head_evidence=self.evidence.status,input_scope=self.scope,task_definition_id=self.evidence.task_definition_id or 'SYNTHETIC_UNLABELLED_NUMERIC_TASK',actual_full_encoder_calls=self.calls-before,per_call_geometry=self.call_metadata[before:],clinical_validity='NOT_ESTABLISHED')
        if valid_mask is not None:
            from .verification_vnext import residual_region_witness
            result['spatial_diagnosis']=residual_region_witness(result,valid_mask)
        return result
