"""Concrete case3-only loader under original INT supervisor/IO, no dispatch.

Imported only after exact source lock and a NEW admitted child environment.
Never call the old three-array consumer for this one-case supplement.
"""
import json
from pathlib import Path
import sys


def old_binding(q):
    from epi_next.r92_entry import locked
    return locked(q['old_binding'])


def check_environment(q):
    import os
    directory=Path(os.environ['EPI_NEXT_SUPERVISOR_DIR'])
    if str(directory)!=str(Path(q['supervision_root'])/q['job_id']):
        raise ValueError('NEW_SUPERVISOR_DIRECTORY_REQUIRED')
    spec=json.loads((directory/'spec.json').read_bytes())
    if (spec['job_id']!=q['job_id'] or spec['task_key']!=q['task_key']
            or spec['max_forward']!=q['limits']['forward'] or spec['max_backward']!=q['limits']['backward']
            or spec['timeout_seconds']!=q['limits']['seconds'] or spec['device']!='cpu'):
        raise ValueError('NEW_EXACT_SUPERVISION_SPEC_REQUIRED')


def open_guard(q):
    check_environment(q)
    b=old_binding(q)
    from epi_next.r92_entry import locked
    sys.path.insert(0,q['integration_root'])
    from qa.next_selected_fidelity_parent import load_supervisor
    modules=load_supervisor(locked(b['supervisor_index']))
    return modules['wave1_supervisor'].ChildGuard.from_environment()


def load_bundle(q,meter):
    import hashlib
    import numpy as np
    import torch
    from epi_next.r92_entry import locked,sha
    from epi_next import first_real_e1_e2 as first
    from epi_next.e2_handler_v4 import import_stage1
    from epi_next.hspi_core_v3 import HSPIConfig
    b=old_binding(q);old=locked(b['readout_request']);f=b['existing_e2_binding']
    delivery=locked(f['prepared_delivery'])
    if delivery['checkpoint_sha256']!=old['input_binding']['model_sha256']:
        raise ValueError('OLD_CHECKPOINT_IDENTITY')
    records=[r for r in delivery['records'] if r['case_index']==3]
    if len(records)!=1:raise ValueError('EXACT_ONE_CASE3')
    record=records[0];arrays={}
    for key in ('image','valid_mask','model_tensor'):
        meter.guard();ref=record['arrays'][key];path=Path(ref['path'])
        if path.is_symlink() or sha(path)!=ref['sha256']:raise ValueError('PREPARED_FILE_SHA')
        value=np.load(path,allow_pickle=False)
        if (hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()!=ref['array_sha256']
                or list(value.shape)!=ref['shape'] or str(value.dtype)!=ref['dtype']):
            raise ValueError('PREPARED_ARRAY_IDENTITY')
        arrays[key]=value
    spec=first.locked_json(Path(f['prepared_delivery']['path']).parent/'preprocessing.json',delivery['preprocess_sha256'])
    expected=(arrays['image'][None].repeat(3,axis=0)-np.asarray(spec['normalization_mean'],np.float32)[:,None,None])/np.asarray(spec['normalization_std'],np.float32)[:,None,None]
    if not np.array_equal(expected,arrays['model_tensor']):raise ValueError('NORMALIZATION_CHANGED')
    prepared=first.Prepared2DInput(arrays['image'],arrays['valid_mask'],**record['prepared_contract']);prepared.validate()
    payload=locked(f['reuse_stage1'])
    if hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()!=old['reuse_payload_canonical_sha256']:
        raise ValueError('SAVED_MASK_CANONICAL_IDENTITY')
    cfg=dict(old['core_config']);cfg['image_size']=tuple(cfg['image_size']);cfg['grids']=tuple(cfg['grids']);cfg['adam_betas']=tuple(cfg['adam_betas'])
    config=HSPIConfig(**cfg)
    identity=dict(classifier_kind='2D_SLICE_CLASSIFIER',evidence_type='APPROVED_DEVELOPMENT',
        **{k:old['input_binding'][k] for k in ('model_sha256','preprocessing_sha256','model_adapter_sha256')},
        reused_stage1_sha256=old['reuse_payload_canonical_sha256'])
    stage=import_stage1(payload,prepared,config,identity)
    if stage['best']['epoch']!=3604 or stage['cell']!=43:raise ValueError('FIXED_SAVED_SELECTION')
    soft=torch.nn.functional.interpolate(stage['best']['mask'],(224,224),mode='bilinear',align_corners=False,antialias=False)[0,0]
    bridge=first.baseline_source(f['integration_bridge_source'])
    meter.guard()
    classifier=bridge.load_verified_resnet18(Path(delivery['checkpoint_path']),old['input_binding']['model_sha256'])
    model=first.DifferentiablePreparedModel(classifier,spec).eval().requires_grad_(False)
    meter.guard()
    return dict(model=model,adapter_predict=model.predict_numpy,image=torch.from_numpy(arrays['image'].copy()),
        valid=torch.from_numpy(arrays['valid_mask'].copy()),soft=soft,peak=stage['patch'],
        saved_bytes=Path(q['saved_readout']['path']).read_bytes(),audit={})


def write_result(q,result):
    # Same existing cumulative output adapter. Parent must reserve science/supervision
    # roots for this new job; no lock/queue/admission is created here.
    from qa.e2_readout_output import OutputBudget
    budget=OutputBudget(q['output_policy'])
    path=Path(q['output_root'])/'result.json'
    raw=json.dumps(result,sort_keys=True,allow_nan=False).encode()
    budget.write_new(path,raw,terminal=result['status']!='SUCCESS')
