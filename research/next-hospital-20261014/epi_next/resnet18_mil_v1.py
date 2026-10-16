"""Independent 2D mean-logit MIL candidate; reuse ResNet18 and shared supervisor.

No downloads, DICOM decoding or implicit real execution. DATA owns labels/splits.
"""
from __future__ import annotations

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[3]
import argparse
import gc
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys

import numpy as np

from . import ctfm_research_pipeline_v4 as p
from .ctfm_research_math_v4 import baselines, binary_metrics, probability

IMAGENET_SHA = 'f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec'
LOC_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
LOC_PATH = str(_PUBLIC_ROOT / 'research/next-hospital-20261014/configs/explanation-target-contract-v5.json')
CONFIG_PATH = Path(__file__).parents[1]/'configs/resnet18_mil_candidate_v1.json'
RESIZE_ROUNDOFF_ATOL = 4 * 2**-23  # Absolute envelope at FP32 unit scale.


def config():
    return json.loads(CONFIG_PATH.read_bytes())


def sample_indices(depth):
    if type(depth) is not int or depth < 8:
        raise p.Blocked('EIGHT_DISTINCT_ORDERED_SLICES_REQUIRED')
    return [int((j+.5)*depth/8) for j in range(8)]


def windowed_diagnostic(value):
    """Aggregate-only boundary evidence. Never serialize pixels or source identity."""
    import torch
    result = dict(stage='post_resize_pre_imagenet_normalization',
        python_type=type(value).__name__, axes='N,C,Y,X',
        expected=dict(rank=4, channels=1, spatial=[224,224], dtype='torch.float32',
                      device='cpu', finite=True, minimum=0, maximum=1),
        shape='NOT_EVALUATED', dtype='NOT_EVALUATED', device='NOT_EVALUATED',
        stride='NOT_EVALUATED', contiguous='NOT_EVALUATED', finite='NOT_EVALUATED',
        nonfinite_count='NOT_EVALUATED', finite_min='NOT_EVALUATED', finite_max='NOT_EVALUATED',
        predicates={})
    checks=result['predicates']; checks['tensor']=isinstance(value,torch.Tensor)
    if not checks['tensor']:
        result['failed_predicates']=['tensor'];return result
    result.update(shape=list(value.shape),dtype=str(value.dtype),device=str(value.device),
                  stride=list(value.stride()),contiguous=value.is_contiguous())
    checks.update(rank=value.ndim==4, channels=value.ndim==4 and value.shape[1]==1,
        spatial=value.ndim>=2 and tuple(value.shape[-2:])==(224,224),
        dtype=value.dtype==torch.float32, device=value.device.type=='cpu', nonempty=value.numel()>0)
    # Meta/non-CPU negative fixtures must not force a GPU allocation or data copy.
    if checks['device'] and checks['nonempty'] and not value.is_complex():
        finite=torch.isfinite(value);values=value[finite]
        result.update(finite=bool(finite.all()),nonfinite_count=int((~finite).sum()))
        checks['finite']=result['finite']
        if values.numel():
            result.update(finite_min=float(values.min()),finite_max=float(values.max()))
        checks['minimum']=result['finite'] and result['finite_min']>=0
        checks['maximum']=result['finite'] and result['finite_max']<=1
    result['failed_predicates']=[name for name,ok in checks.items() if not ok]
    return result


def normalize_windowed(value):
    import torch
    diagnostic=windowed_diagnostic(value)
    if diagnostic['failed_predicates']:
        error=p.Blocked('FINITE_CPU_WINDOWED_SCALAR_224_REQUIRED: '+json.dumps(diagnostic,sort_keys=True))
        error.diagnostic=diagnostic
        raise error
    rgb = value.repeat(1,3,1,1)
    mean = torch.tensor([.485,.456,.406]).reshape(1,3,1,1)
    std = torch.tensor([.229,.224,.225]).reshape(1,3,1,1)
    return (rgb-mean)/std


def recover_resize_roundoff(value):
    """Restore the window target only for bounded FP32 resize excursions."""
    diagnostic = windowed_diagnostic(value)
    failed = set(diagnostic['failed_predicates'])
    if (failed - {'minimum', 'maximum'}
            or diagnostic['finite_min'] < -RESIZE_ROUNDOFF_ATOL
            or diagnostic['finite_max'] > 1 + RESIZE_ROUNDOFF_ATOL):
        # Reuse the strict boundary's aggregate evidence and fail-closed error.
        normalize_windowed(value)
        raise p.Blocked('RESIZE_ROUNDOFF_RECOVERY_REJECTED')
    lower = int((value < 0).sum()); upper = int((value > 1).sum())
    summary = dict(policy='FP32_RESIZE_ABSOLUTE_4EPS_CLAMP_EXCURSIONS_V1',
        absolute_tolerance=RESIZE_ROUNDOFF_ATOL,
        finite_min_before=diagnostic['finite_min'], finite_max_before=diagnostic['finite_max'],
        lower_corrected=lower, upper_corrected=upper,
        max_absolute_correction=max(0., -diagnostic['finite_min'], diagnostic['finite_max']-1))
    return (value.clamp(0,1) if lower or upper else value), summary


def prepare_bag(row, meter, *, observe=None):
    """Consume QA-bound HU only. Never reapply slope/intercept or default units."""
    import torch
    from torchvision.transforms import InterpolationMode, functional as tf
    ref = row['tensor_artifact']
    if p.file_sha(ref['path'],meter.check,512*1024**2+4096) != ref['sha256']:
        raise p.Blocked('NATIVE_TENSOR_SHA_MISMATCH')
    native = np.load(ref['path'],mmap_mode='r',allow_pickle=False)
    geo = p.bound_json(row['geometry_ledger'],meter.check)
    if observe: observe('native_header', dict(shape=list(native.shape),dtype=str(native.dtype),axes=geo.get('axis_order')))
    if (native.dtype != np.float32 or list(native.shape) != ref['shape'] or native.nbytes > 512*1024**2
            or geo.get('tensor_artifact') != ref or geo.get('shape') != ref['shape']
            or geo.get('axis_order') != 'Z,Y,X' or geo.get('GEOMETRY_QA') != 'PASS_COMPLETE_SELECTED_STACK'
            or geo.get('PIXEL_QA') != 'PASS' or geo.get('RESCALE_QA') != 'PASS_DECLARED_HU'
            or geo.get('PROVENANCE_BOUND') is not True
            or geo.get('source_diagnosis') != row['source_diagnosis'] or geo.get('task_label') != row['task_label']
            or geo.get('affine_LPS') != row['affine_LPS'] or geo.get('spacing_ZYX_mm') != row['spacing_ZYX_mm']):
        raise p.Blocked('BOUND_COMPLETE_HU_GEOMETRY_LABEL_QA_REQUIRED')
    affine = np.asarray(geo['affine_LPS'],np.float64)
    if (affine.shape != (4,4) or not np.isfinite(affine).all()
            or not np.allclose(affine[3],[0,0,0,1],atol=1e-7,rtol=0)
            or not np.allclose(affine[:2,0],0,atol=1e-7,rtol=0)
            or not np.allclose(affine[2,1:3],0,atol=1e-7,rtol=0)
            or not np.allclose(np.linalg.norm(affine[:3,:3],axis=0),geo['spacing_ZYX_mm'],atol=1e-7,rtol=1e-7)
            or abs(np.linalg.det(affine[:3,:3])) < 1e-8):
        raise p.Blocked('NATIVE_Z_AXIAL_GEOMETRY_REQUIRED')
    indices = sample_indices(native.shape[0])
    selected = np.array(native[indices],copy=True)
    if observe: observe('selected_HU', selected)
    if not np.isfinite(selected).all():
        raise p.Blocked('NONFINITE_SELECTED_HU')
    # Keep the old window/resize/RGB/mean/std using DATA's validated HU.
    # This independent R18 path adds explicit 4eps resize recovery below;
    # it is not fully numerically equivalent to frozen src.preprocessing.
    scalar = torch.from_numpy(np.clip((selected+1350)/1500,0,1)).unsqueeze(1)
    if observe: observe('windowed_pre_resize', scalar)
    scalar = tf.resize(scalar,[224,224],interpolation=InterpolationMode.BILINEAR,antialias=True)
    if observe: observe('post_resize_pre_normalize', scalar)
    scalar, roundoff = recover_resize_roundoff(scalar)
    if observe: observe('resize_roundoff_recovery', roundoff)
    images = normalize_windowed(scalar)
    if observe: observe('imagenet_normalized', images)
    geometry = dict(schema='R18_MIL_SAMPLE_GEOMETRY_V1',native_shape_ZYX=list(native.shape),
        native_to_LPS=affine.tolist(),indices_Z=indices,crop='NONE',
        coverage='eight uniform slice centers in complete selected Series; not all-slice inference',
        model_shape=[8,3,224,224],native_YX_per_model_pixel=[native.shape[1]/224,native.shape[2]/224],
        model_to_native_YX='(index+.5)*native_size/224-.5; nominal bilinear centers',
        data_geometry_sha256=row['geometry_ledger']['sha256'],unit='HU_ALREADY_RESCALED_ONCE',
        resize_roundoff=roundoff)
    return images,geometry


def build_backbone(checkpoint=None):
    """checkpoint=None is generated random initialization only; never downloads."""
    import torch
    from src.model import build_model
    model = build_model({'model':dict(name='resnet18',pretrained=False,num_classes=2)})
    if checkpoint is not None:
        if checkpoint['sha256'] != IMAGENET_SHA or p.file_sha(checkpoint['path']) != IMAGENET_SHA:
            raise p.Blocked('EXACT_EXISTING_IMAGENET_CHECKPOINT_REQUIRED')
        state = torch.load(checkpoint['path'],map_location='cpu',weights_only=True)
        del state['fc.weight'],state['fc.bias']
        model.fc = torch.nn.Identity()
        model.load_state_dict(state,strict=True)
    else:
        model.fc = torch.nn.Identity()
    model.eval().requires_grad_(False)
    return model


def build_slice_predictor(backbone, head):
    """LOC v5 SLICE adapter; CASE/BAG label is never attached as slice truth."""
    import torch
    class SlicePredictor(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.backbone,self.head = backbone,head.double()
            self.eval().requires_grad_(False)
        def train(self,mode=True):
            super().train(False)
            return self
        def forward(self,scalar):
            if scalar.shape != (1,1,224,224):
                raise p.Blocked('LOC_V5_SINGLE_SLICE_REQUIRED_NO_BAG_SUBSTITUTION')
            features = self.backbone(normalize_windowed(scalar))
            logits = self.head(features.double()).float()
            if logits.shape != (1,2) or not torch.isfinite(logits).all():
                raise p.Blocked('NONFINITE_SLICE_LOGITS')
            return logits  # Deliberately no no_grad, inference_mode or detach.
    return SlicePredictor()


def slice_contract(model_binding, explanation_target, source_label=None, prediction_scope='SLICE'):
    contract = p.bound_json(dict(path=LOC_PATH,sha256=LOC_SHA))
    if prediction_scope != 'SLICE' or source_label is not None:
        raise p.Blocked('ONLY_UNLABELLED_SLICE_RESPONSE_SUPPORTED_BAG_PROTOCOL_NOT_BOUND')
    if (explanation_target.get('policy') not in ('ORIGINAL_ARGMAX_FIXED','DECLARED_FIXED')
            or type(explanation_target.get('declared_class')) is not int
            or explanation_target['declared_class'] not in (0,1)):
        raise p.Blocked('LOC_V5_EXPLICIT_DECLARATION_REQUIRED')
    required = {'model_sha256','preprocessing_sha256','adapter_sha256','task_version'}
    if (not required.issubset(model_binding) or model_binding['task_version']!=config()['task']
            or any(not isinstance(model_binding[k],str) or not re.fullmatch('[a-f0-9]{64}',model_binding[k])
                   for k in required-{'task_version'})):
        raise p.Blocked('LOC_V5_MODEL_BINDING_REQUIRED')
    return dict(contract_sha256=LOC_SHA,prediction_scope='SLICE',source_label=None,
        class_labels=['Normal_SOURCE','COVID-19_OR_CAP_SOURCE'],model_binding=model_binding,
        explanation_target=explanation_target,loss_definition=contract['loss_definition'],
        limitation='versioned slice response of a bag-trained model; no slice disease truth')


def resolve_loc_target(original_logits, explanation_target):
    """Validate LOC v5 declaration against the actual unmasked slice logits."""
    logits=np.asarray(original_logits,dtype=np.float64)
    if logits.ndim!=2 or logits.shape[0]!=1 or logits.shape[1]<2 or not np.isfinite(logits).all():
        raise p.Blocked('LOC_V5_FINITE_SINGLE_SLICE_LOGITS_REQUIRED')
    policy=explanation_target.get('policy');declared=explanation_target.get('declared_class')
    if (policy not in ('ORIGINAL_ARGMAX_FIXED','DECLARED_FIXED') or type(declared) is not int
            or not 0<=declared<logits.shape[1]):
        raise p.Blocked('LOC_V5_EXPLICIT_DECLARATION_REQUIRED')
    predicted=int(np.argmax(logits[0]))  # First index wins ties, as LOC v5 specifies.
    resolved=predicted if policy=='ORIGINAL_ARGMAX_FIXED' else declared
    if declared!=resolved:
        raise p.Blocked('LOC_V5_DECLARED_RESOLVED_TARGET_MISMATCH')
    return dict(policy=policy,declared_class=declared,resolved_class=resolved,
                predicted_class=predicted,prediction_scope='SLICE')


def cache_phase(records, manifest_sha, context, output, backbone, meter):
    import torch
    from .encoder import FeatureCache,canonical_json
    p.validate_records(records)
    store = p.PrivateArtifacts(p.safe_path(output),p.PHASES['cache']['assets'])
    cache = FeatureCache(store.directory/'features'); rows=[]
    for i,row in enumerate(records):
        meter.begin(row['record_id'])
        images,geometry = prepare_bag(row,meter)
        geometry_sha = store.json(f'case_{i:02d}_geometry.json',geometry)
        input_sha = p.digest(p.encoded(dict(shape=list(images.shape),dtype='float32'))+images.numpy().tobytes())
        identity = dict(input_sha=input_sha,model_sha=context['backbone_sha256'],
            preprocess_sha=p.digest(p.encoded(config()['preprocessing'])),geometry_sha=geometry_sha,
            config_sha=context['config_sha256'],code_sha=context['source_commit'],
            split_manifest_sha=manifest_sha,split='train' if row['split']=='train_weak' else 'observed_validation')
        meter.before('forward')
        with torch.no_grad():
            features = backbone(images)
        meter.returned_forward+=1;meter.check()
        if features.shape != (8,512) or features.dtype != torch.float32 or features.device.type != 'cpu' or not torch.isfinite(features).all():
            raise p.Blocked('R18_EIGHT_BY_512_FINITE_CPU_FP32_REQUIRED')
        # Reuse spatial-cache format: singleton spatial axes hold per-slice GAP.
        value = features.reshape(8,512,1,1,1)
        with store._write_lock:
            store.check_disk(2*(value.numel()*4+len(canonical_json(identity))+8192))
            key = cache.write(identity,value);path = cache.directory/(key+'.npz')
            store._asset_sizes['features/'+path.name] = path.stat().st_size
            store.assets['features/'+path.name] = p.file_sha(path,meter.check)
        bag_gap=features.numpy().astype(np.float64).mean(0,keepdims=True)
        gap_name=f'case_{i:02d}_bag_gap512.npy';gap_sha=store.array(gap_name,bag_gap)
        rows.append(dict(record_id=row['record_id'],source_group_id=row['source_group_id'],split=row['split'],
            task_label=row['task_label'],source_diagnosis=row['source_diagnosis'],native_sha256=row['tensor_artifact']['sha256'],
            data_geometry_sha256=row['geometry_ledger']['sha256'],identity=identity,
            feature=dict(path=str(path),sha256=store.assets['features/'+path.name]),
            gap=dict(path=str(store.directory/gap_name),sha256=gap_sha),
            geometry=dict(path=str(store.directory/f'case_{i:02d}_geometry.json'),sha256=geometry_sha)))
        del images,features,value,bag_gap
        meter.end()
    result = dict(schema='R18_MIL_CACHE_V1',status='PASS',data_manifest_sha256=manifest_sha,
        context=context,rows=rows,calls=meter.report(),slice_evaluations=480,warmup=0)
    store.json('cache-receipt.json',result)
    return result


def read_cache(receipt,records,manifest_sha,meter):
    from .encoder import FeatureCache
    p.validate_records(records)
    if (receipt['schema'] != 'R18_MIL_CACHE_V1' or receipt['status'] != 'PASS'
            or receipt['data_manifest_sha256'] != manifest_sha or len(receipt['rows']) != 60):
        raise p.Blocked('R18_CACHE_MANIFEST_REQUIRED')
    bags=[]
    for row,cached in zip(records,receipt['rows']):
        if any(row[k] != cached[k] for k in ('record_id','source_group_id','split','task_label','source_diagnosis')):
            raise p.Blocked('R18_CACHE_RECORD_BINDING')
        identity=cached['identity']; context=receipt['context']
        expected=dict(model_sha=context['backbone_sha256'],config_sha=context['config_sha256'],
            code_sha=context['source_commit'],preprocess_sha=p.digest(p.encoded(config()['preprocessing'])),
            split_manifest_sha=manifest_sha,geometry_sha=cached['geometry']['sha256'],
            split='train' if row['split']=='train_weak' else 'observed_validation')
        if (any(identity[k]!=v for k,v in expected.items())
                or cached['native_sha256'] != row['tensor_artifact']['sha256']
                or cached['data_geometry_sha256'] != row['geometry_ledger']['sha256']):
            raise p.Blocked('R18_CACHE_VERSION_INPUT_SPLIT_BINDING')
        for name in ('feature','gap','geometry'):
            if p.file_sha(cached[name]['path'],meter.check) != cached[name]['sha256']:
                raise p.Blocked('R18_CACHE_ASSET_SHA')
        path=p.safe_path(cached['feature']['path'])
        from .encoder import feature_cache_key
        if path.name != feature_cache_key(identity)+'.npz':
            raise p.Blocked('R18_CACHE_KEY_PATH')
        f=FeatureCache(path.parent).read(identity).numpy()
        gap=np.load(cached['gap']['path'],allow_pickle=False)
        geo=p.bound_json(cached['geometry'],meter.check)
        expected_gap=f[:,:,0,0,0].astype(np.float64).mean(0,keepdims=True)
        if (f.shape!=(8,512,1,1,1) or f.dtype!=np.float32 or gap.shape!=(1,512)
                or gap.dtype!=np.float64 or not np.array_equal(gap,expected_gap)
                or geo['indices_Z']!=sample_indices(row['tensor_artifact']['shape'][0])
                or geo['data_geometry_sha256']!=row['geometry_ledger']['sha256']):
            raise p.Blocked('R18_CACHE_FEATURE_SAMPLE_BINDING')
        bags.append(gap[0])
    return np.stack(bags)


def fit_head(gap, labels, train_mask, meter):
    import torch
    from .encoder import CaseLinearHead
    if (gap.shape!=(60,512) or gap.dtype!=np.float64 or len(labels)!=60
            or any(type(y) is not int or y not in (0,1) for y in labels)
            or train_mask.shape!=(60,) or train_mask.dtype!=np.bool_):
        raise p.Blocked('R18_EXACT_GROUP_FEATURE_LABEL_TYPES')
    x=torch.from_numpy(gap[train_mask]).float();y=torch.tensor(labels,dtype=torch.long)[train_mask]
    if x.shape != (40,512) or set(y.tolist()) != {0,1} or not torch.isfinite(x).all():
        raise p.Blocked('FIXED_40_TWO_CLASS_FINITE_TRAIN_REQUIRED')
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(17);head=CaseLinearHead(512,2)
        head.mean.copy_(x.mean(0));head.scale.copy_(x.std(0,unbiased=False).clamp_min(1e-6))
        opt=torch.optim.AdamW(head.parameters(),lr=.001,weight_decay=.0001);losses=[]
        for _ in range(100):
            opt.zero_grad(set_to_none=True);meter.before('forward');logits=head(x);meter.returned_forward+=1
            loss=torch.nn.functional.cross_entropy(logits,y)
            if not torch.isfinite(loss): raise p.Blocked('NONFINITE_BAG_CE')
            meter.before('backward');loss.backward();meter.returned_backward+=1
            if any(v.grad is None or not torch.isfinite(v.grad).all() for v in head.parameters()):
                raise p.Blocked('NONFINITE_HEAD_GRADIENT')
            meter.before('updates');opt.step();meter.returned_updates+=1;losses.append(float(loss.detach()))
    return head.eval(),losses


def save_head(head,losses,cache_ref,cache,output,meter):
    if (len(losses),meter.returned_forward,meter.returned_backward,meter.returned_updates)!=(100,100,100,100):
        raise p.Blocked('NO_PARTIAL_REAL_FINAL_CHECKPOINT')
    store=p.PrivateArtifacts(p.safe_path(output),p.PHASES['train']['assets']);state={}
    for name,tensor in head.state_dict().items():
        fname=name.replace('.','_')+'.npy';sha=store.array(fname,tensor.detach().numpy())
        state[name]=dict(path=str(store.directory/fname),sha256=sha)
    checkpoint=dict(schema='R18_MIL_HEAD_V1',status='PASS',state=state,final_update=100,
        class_labels=['Normal_SOURCE','COVID-19_OR_CAP_SOURCE'],prediction_scope='BAG',
        context=cache['context'],cache_receipt=cache_ref,data_manifest_sha256=cache['data_manifest_sha256'],
        config=config(),losses=losses,calls=meter.report(),calibration='UNCALIBRATED',
        clinical_patient_independence='UNKNOWN',selection='fixed final update; no val selection')
    store.json('head-checkpoint.json',checkpoint)
    return checkpoint


def restore_head(checkpoint,meter):
    import torch
    from .encoder import CaseLinearHead
    if (checkpoint['schema']!='R18_MIL_HEAD_V1' or checkpoint['status']!='PASS'
            or checkpoint['final_update']!=100 or checkpoint['config']!=config()
            or checkpoint['prediction_scope']!='BAG'
            or checkpoint['class_labels']!=['Normal_SOURCE','COVID-19_OR_CAP_SOURCE']):
        raise p.Blocked('R18_FINAL_CHECKPOINT_REQUIRED')
    state={}
    for name,ref in checkpoint['state'].items():
        if p.file_sha(ref['path'],meter.check,64*1024)!=ref['sha256']: raise p.Blocked('R18_HEAD_SHA')
        value=np.load(ref['path'],allow_pickle=False)
        if value.dtype!=np.float32 or not np.isfinite(value).all(): raise p.Blocked('R18_HEAD_DTYPE_FINITE')
        state[name]=torch.from_numpy(value.copy()).double()
    with torch.random.fork_rng(devices=[]): head=CaseLinearHead(512,2).double()
    head.load_state_dict(state,strict=True)
    if torch.any(head.scale<=0): raise p.Blocked('R18_HEAD_SCALE')
    return head.eval()


def evaluate_phase(head,gap,records,meter):
    import torch
    labels=np.array([r['task_label'] for r in records]);train=np.array([r['split']=='train_weak' for r in records])
    result={};predictions=[]
    for split in ('train_weak','val_classification'):
        mask=np.array([r['split']==split for r in records]);meter.before('forward')
        with torch.no_grad(): logits=head(torch.from_numpy(gap[mask])).numpy()
        meter.returned_forward+=1;scores=probability(logits)
        result[split]=dict(model=binary_metrics(labels[mask],scores),baselines=baselines(labels[train],labels[mask]))
        selected=[r for r,m in zip(records,mask) if m]
        subgroup={}
        for category in ('COVID-19','CAP','Normal'):
            sub=np.array([r['source_diagnosis']==category for r in selected])
            if sub.any():
                subgroup_labels=labels[mask][sub];subgroup_scores=scores[sub]
                subgroup_prediction=subgroup_scores>.5
                subgroup[category]=dict(n=int(sub.sum()),source_class=int(subgroup_labels[0]),
                    correct_at_fixed_threshold=int(np.sum(subgroup_prediction==subgroup_labels.astype(bool))),
                    accuracy_at_fixed_threshold=float(np.mean(subgroup_prediction==subgroup_labels.astype(bool))),
                    mean_positive_probability=float(subgroup_scores.mean()),
                    discrimination_metrics='UNDEFINED_SINGLE_SOURCE_CLASS')
        result[split]['source_subgroups']=subgroup
        for row,z,score in zip(selected,logits,scores):
            predictions.append(dict(record_id=row['record_id'],source_group_id=row['source_group_id'],split=split,
                source_diagnosis=row['source_diagnosis'],source_label=dict(class_id=row['task_label'],scope='BAG',
                    provenance=row['label_provenance']),raw_logits=z.tolist(),positive_probability=float(score),
                predicted_class=int(score>.5),prediction_scope='BAG'))
    return dict(schema='R18_MIL_EVALUATION_V1',status='PASS',metrics=result,predictions=predictions,
        calls=meter.report(),clinical_accuracy_claim=False,independent_test_claim=False,
        clinical_patient_independence='UNKNOWN',pretraining_overlap='UNKNOWN')


def validate_request(request):
    phase=request.get('phase');cfg=config()
    if request.get('schema')!='R18_MIL_RESOLVED_EXECUTION_V1' or phase not in p.PHASES or request.get('config')!=cfg or request.get('retry') is not False:
        raise p.Blocked('EXACT_APPROVED_R18_PHASE_REQUIRED')
    limits=p.PHASES[phase]
    expected=dict(owner='ENCODER',device='cpu',max_forward=limits['forward'],max_backward=limits['backward'],
        timeout_seconds=limits['seconds'],per_case_seconds=limits['per_case'],
        task_key=cfg['task_keys'][phase],job_id=cfg['job_ids'][phase])
    if any(request['spec'].get(k)!=v for k,v in expected.items()): raise p.Blocked('R18_FIXED_SPEC_REQUIRED')
    if request['checkpoint']['sha256']!=IMAGENET_SHA: raise p.Blocked('R18_INITIALIZATION_BINDING')
    if request['data_contract']['sha256']!=p.DATA_CONTRACT_SHA: raise p.Blocked('R18_DATA_CONTRACT')
    p.bound_json(request['data_contract']);p.bound_json(dict(path=LOC_PATH,sha256=LOC_SHA))
    repo=Path(__file__).resolve().parents[3]
    required=set(p.source_closure())|{Path(__file__).resolve(),CONFIG_PATH.resolve(),repo/'src/model.py',repo/'src/data_checks.py'}
    if {p.safe_path(ref['path']) for ref in request['sources']}!=required: raise p.Blocked('R18_SOURCE_CLOSURE_REQUIRED')
    for ref in request['sources']:
        if p.file_sha(ref['path'])!=ref['sha256']: raise p.Blocked('R18_SOURCE_DRIFT')
        blob=subprocess.check_output(['git','-C',str(repo),'show',request['source_commit']+':'+str(Path(ref['path']).relative_to(repo))],timeout=5)
        if p.digest(blob)!=ref['sha256']: raise p.Blocked('R18_COMMITTED_SOURCE_REQUIRED')
    for ref in request['runtime']['references']:
        if p.file_sha(ref['path'])!=ref['sha256']: raise p.Blocked('R18_RUNTIME_REFERENCE_DRIFT')
    if request['runtime']['packages']!={'torch':'2.14.0','torchvision':'0.29.0','numpy':'2.4.6','pandas':'3.0.6','PyYAML':'6.0.3'} or request['runtime']['python_version']!='3.11.15':
        raise p.Blocked('R18_PINNED_EXISTING_RUNTIME_REQUIRED')
    for key in ('output','supervisor_output'):
        if p.safe_path(request['delivery_root']) not in p.safe_path(request[key]).parents:
            raise p.Blocked('R18_OUTPUT_BOUNDARY')
    return request


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('request','request-sha'): parser.add_argument('--'+name,required=True)
    for name in ('approval','approval-sha','dispatch','dispatch-sha'): parser.add_argument('--'+name)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--child',action='store_true')
    args=parser.parse_args(argv);guard=meter=backbone=None
    try:
        request=validate_request(p.bound_json(dict(path=args.request,sha256=args.request_sha)))
        if not args.execute: raise p.Blocked('REAL_R18_EXECUTION_NOT_AUTHORIZED_BY_PREPARATION')
        if not all((args.approval,args.approval_sha,args.dispatch,args.dispatch_sha)):
            raise p.Blocked('EXACT_APPROVAL_AND_EXCLUSIVE_DISPATCH_REQUIRED')
        approval=p.bound_json(dict(path=args.approval,sha256=args.approval_sha))
        dispatch=p.bound_json(dict(path=args.dispatch,sha256=args.dispatch_sha))
        for value,schema,status in ((approval,'R18_MIL_APPROVAL_V1','APPROVED_NEW_SCOPE'),(dispatch,'R18_MIL_DISPATCH_V1','EXCLUSIVE_SLOT_ASSIGNED')):
            if (value.get('schema')!=schema or value.get('status')!=status or value.get('owner')!='ENCODER'
                    or value.get('request_sha256')!=args.request_sha or value.get('phase')!=request['phase']
                    or value.get('task_key')!=request['spec']['task_key'] or value.get('retry') is not False):
                raise p.Blocked('R18_EXACT_AUTHORITY_REQUIRED')
        if dispatch['approval_sha256']!=args.approval_sha: raise p.Blocked('R18_DISPATCH_APPROVAL')
        shared=p.load_shared(request)
        if not args.child:
            # The admitted child must load the package module by its stable name.
            # ``-m __main__`` leaves __spec__ unset and fails before R18 entry.
            child=[sys.executable,'-m','epi_next.resnet18_mil_v1','--request',args.request,'--request-sha',args.request_sha,
                '--approval',args.approval,'--approval-sha',args.approval_sha,'--dispatch',args.dispatch,
                '--dispatch-sha',args.dispatch_sha,'--execute','--child']
            recovery=request['administrative_recovery']
            receipt=shared.run_supervised(shared.SupervisionSpec(**request['spec']),child,request['supervisor_output'],
                request['supervisor']['dependency_root'],p.SHARED_SHA,recovery_decision_path=recovery['path'],recovery_decision_sha=recovery['sha256'])
            return 0 if receipt['status']=='SUCCESS' and receipt['slot_completed'] else 2
        guard=shared.ChildGuard.from_environment()
        if vars(guard.spec)!=vars(shared.SupervisionSpec(**request['spec'])): raise p.Blocked('R18_CHILD_SPEC')
        meter=p.Meter(request['phase'],guard,request['delivery_root'])
        for name,version in request['runtime']['packages'].items():
            if importlib.metadata.version(name)!=version: raise p.Blocked('R18_RUNTIME_VERSION')
        if sys.version.split()[0]!=request['runtime']['python_version']: raise p.Blocked('R18_PYTHON_VERSION')
        records=p.validate_records(p.bound_json(request['data_manifest'],meter.check))
        projection=[{k:r[k] for k in ('record_id','source_group_id','source_diagnosis','task_label','split')} for r in records]
        if p.digest(p.encoded(projection))!=request['fixed_group_projection_sha256']:
            raise p.Blocked('R18_APPROVED_GROUP_PROJECTION')
        import torch
        torch.set_num_threads(1);torch.set_num_interop_threads(1)
        context=dict(backbone_sha256=IMAGENET_SHA,checkpoint_reference=request['checkpoint'],
            config_sha256=p.digest(p.encoded(config())),source_commit=request['source_commit'],evidence_type='REAL_R18_MIL')
        if request['phase']=='cache':
            backbone=build_backbone(request['checkpoint'])
            cache_phase(records,request['data_manifest']['sha256'],context,request['output'],backbone,meter)
            backbone=None
        else:
            cache=p.bound_json(request['cache_receipt'],meter.check)
            if cache['context']!=context: raise p.Blocked('R18_REAL_CACHE_CONTEXT')
            gap=read_cache(cache,records,request['data_manifest']['sha256'],meter)
            if request['phase']=='train':
                head,losses=fit_head(gap,[r['task_label'] for r in records],np.array([r['split']=='train_weak' for r in records]),meter)
                save_head(head,losses,request['cache_receipt'],cache,request['output'],meter)
            else:
                checkpoint=p.bound_json(request['head_checkpoint'],meter.check)
                if (checkpoint['context']!=context or checkpoint['cache_receipt']!=request['cache_receipt']
                        or checkpoint['data_manifest_sha256']!=request['data_manifest']['sha256']):
                    raise p.Blocked('R18_EVALUATION_HEAD_CONTEXT')
                head=restore_head(checkpoint,meter);evaluation=evaluate_phase(head,gap,records,meter)
                evaluation.update(context=context,cache_receipt=request['cache_receipt'],head_checkpoint=request['head_checkpoint'],data_manifest=request['data_manifest'])
                store=p.PrivateArtifacts(p.safe_path(request['output']),p.PHASES['evaluate']['assets'])
                store.json('evaluation.json',evaluation)
        gc.collect();meter.check()
        guard.complete('SUCCESS',device_recovered=True,actual_forward=meter.returned_forward,actual_backward=meter.returned_backward)
        print(json.dumps(dict(status='PASS',calls=meter.report())))
        return 0
    except Exception as exc:
        backbone=None;gc.collect()
        if guard: guard.complete('FAILED',reason=type(exc).__name__,device_recovered=False,
            actual_forward=meter.returned_forward if meter else 0,actual_backward=meter.returned_backward if meter else 0)
        print(json.dumps(dict(status='BLOCKED' if isinstance(exc,p.Blocked) else 'FAIL',reason=str(exc) if isinstance(exc,p.Blocked) else type(exc).__name__)))
        return 3


if __name__=='__main__':
    raise SystemExit(main())
