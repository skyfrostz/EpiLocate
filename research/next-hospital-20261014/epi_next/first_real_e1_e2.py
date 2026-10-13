"""Execute locked E1/E2 on INTEGRATION's prepared three-slice delivery.

No DICOM decoding, HU preprocessing, patient selection, GT access or training.
All case-level arrays and numerical outputs must remain in private local storage.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import time
import types
import numpy as np
import torch
from .hspi import HSPIConfig
from .preprocessed_localization import Prepared2DInput, run_prepared_e1_e2
from .verification_vnext import hspi_witness


DATA_SHA='0000000000000000000000000000000000000000000000000000000000000000'
SLICE_SHA='0000000000000000000000000000000000000000000000000000000000000000'
CONFIG_SHA='0000000000000000000000000000000000000000000000000000000000000000'
CHECKPOINT_SHA='548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734'
SOURCE_HASHES={'baseline_bridge.py':'caaed7c1e73924b3a5c034cf3dcdfd01485db35dffd7f994736436f2dc74f56f',
               'contracts.py':'2b67e80410672a7547d0d117db76d6f91a18b0f68822d08a1721891f5e42f9e5'}


def file_sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def locked_json(path,expected):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('locked artifact SHA mismatch')
    value=json.loads(raw)
    if not isinstance(value,dict):raise ValueError('locked artifact must be object')
    return value


def write_json(path,value):
    with Path(path).open('x') as stream:stream.write(json.dumps(value,indent=2,allow_nan=False)+'\n')


def save_array(path,array):
    with Path(path).open('xb') as stream:np.save(stream,array,allow_pickle=False)
    return dict(path=str(Path(path).resolve()),sha256=file_sha(path),shape=list(array.shape),dtype=str(array.dtype))


def baseline_source(source):
    source=Path(source).resolve()
    for name,expected in SOURCE_HASHES.items():
        if file_sha(source/name)!=expected:raise ValueError('verified baseline adapter source changed')
    # Keep the sibling package separate; never copy/edit its source or import its CLI.
    alias='_epi_next_integration_readonly'
    package=types.ModuleType(alias);package.__path__=[str(source)];sys.modules[alias]=package
    return importlib.import_module(alias+'.baseline_bridge')


class DifferentiablePreparedModel(torch.nn.Module):
    def __init__(self,classifier,spec):
        super().__init__();self.classifier=classifier;self.classifier_calls=0
        self.register_buffer('mean',torch.tensor(spec['normalization_mean'])[None,:,None,None])
        self.register_buffer('std',torch.tensor(spec['normalization_std'])[None,:,None,None])

    def forward(self,x):
        normalized=(x.repeat(1,3,1,1)-self.mean)/self.std
        self.classifier_calls+=1
        return self.classifier(normalized)

    def predict_numpy(self,image):
        # Frozen antialias resize can exceed 1 by a few float32 ULPs. The input
        # was bound to the exact frozen tensor at reception; do not clamp it or
        # impose the synthetic adapter's stricter intensity assumption.
        value=np.asarray(image)
        if value.shape!=(224,224) or value.dtype!=np.float32 or not np.isfinite(value).all():raise ValueError('expected exact finite prepared float32 grid')
        with torch.inference_mode():logits=self(torch.from_numpy(value.copy())[None,None])[0]
        return logits.detach().cpu().numpy().astype(np.float64)


def consume_inputs(delivery_path,delivery_sha,config_path,config_sha):
    delivery=locked_json(delivery_path,delivery_sha);cfg=locked_json(config_path,config_sha)
    if config_sha!=CONFIG_SHA or cfg['status']!='LOCKED_BY_COORDINATOR_BEFORE_REAL_MODEL_RUN':raise ValueError('first-run configuration not locked')
    if (delivery['schema']!='EPI-NEXT-PREPARED-DELIVERY-1' or delivery['status']!='READY_FOR_LOCALIZATION_CPU'
        or delivery['data_delivery_sha256']!=DATA_SHA or delivery['slice_lock_sha256']!=SLICE_SHA
        or delivery['algorithm_config_sha256']!=CONFIG_SHA or delivery['checkpoint_sha256']!=CHECKPOINT_SHA
        or delivery['model_forwards']!=0 or delivery['gt_reference_files_opened'] is not False
        or delivery['gt_geometry_used_for_preparation'] is not False
        or delivery['hospital_display_authorized'] is not False or len(delivery['records'])!=3):raise ValueError('prepared scope/binding mismatch')
    root=Path(delivery_path).resolve().parent
    spec=locked_json(root/'preprocessing.json',delivery['preprocess_sha256'])
    if spec['resize']!=[224,224] or spec['crop']!='NONE' or spec['pad']!='NONE':raise ValueError('unsupported prepared model grid')
    if spec['channel_policy']!='repeat_one_channel_rgb' or spec['normalization_mean']!=[.485,.456,.406] or spec['normalization_std']!=[.229,.224,.225]:raise ValueError('baseline normalization mismatch')
    selection=locked_json(cfg['slice_lock_path'],SLICE_SHA)
    prepared=[]
    for record in delivery['records']:
        selected=[r for r in selection['slices'] if r['case_index']==record['case_index']]
        if len(selected)!=1:raise ValueError('case not in exact coordinator slice lock')
        selected=selected[0]
        for name in ('case_id','study_uid','series_uid','source_sop_uid','native_slice_index_zero_based'):
            key='sop_uid' if name=='source_sop_uid' else name
            if record[name]!=selected[key]:raise ValueError('prepared slice identity mismatch')
        if record['native_volume_sha256']!=selected['native_volume_sha256'] or record['native_manifest_sha256']!=selected['native_manifest_sha256']:raise ValueError('prepared native provenance mismatch')
        arrays={}
        for name in ('image','valid_mask','model_tensor'):
            asset=record['arrays'][name]
            if file_sha(asset['path'])!=asset['sha256']:raise ValueError('prepared array file hash mismatch')
            array=np.load(asset['path'],allow_pickle=False)
            if hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()!=asset['array_sha256']:raise ValueError('prepared array content hash mismatch')
            if list(array.shape)!=asset['shape'] or str(array.dtype)!=asset['dtype']:raise ValueError('prepared shape/dtype mismatch')
            arrays[name]=array
        p=Prepared2DInput(arrays['image'],arrays['valid_mask'],**record['prepared_contract']);p.validate()
        geometry=locked_json(record['geometry']['path'],record['geometry']['sha256'])
        if geometry['status']!='TECHNICAL_PASS' or geometry['source_sop_uid']!=record['source_sop_uid']:raise ValueError('prepared geometry mismatch')
        if geometry['model_shape_yx']!=list(p.image.shape) or geometry['native_slice_index_zero_based']!=record['native_slice_index_zero_based']:raise ValueError('prepared coordinate binding mismatch')
        if not np.array_equal(arrays['model_tensor'],((arrays['image'][None].repeat(3,axis=0)-np.asarray(spec['normalization_mean'],dtype=np.float32)[:,None,None])/np.asarray(spec['normalization_std'],dtype=np.float32)[:,None,None])):raise ValueError('published frozen tensor mismatch')
        prepared.append((record,p,geometry))
    if len({r['case_index'] for r,_,_ in prepared})!=3:raise ValueError('duplicate prepared case')
    return delivery,cfg,spec,prepared


def native_lookup(geometry):
    """Apply the producer's inverse ledger; do not infer a new transform.

    Native pixel centres sample model cells bounded at centre +/- 0.5.
    This is discrete candidate-region rasterization, not inverse HU resampling.
    """
    h,w=geometry['native_shape_rc'];yy,xx=np.mgrid[:h,:w]
    points=np.stack((np.full_like(yy,geometry['native_slice_index_zero_based']),yy,xx),axis=-1)
    inverse=np.asarray(geometry['native_to_model_zyx'],float)
    forward=np.asarray(geometry['model_to_native_zyx'],float)
    if inverse.shape!=(4,4) or forward.shape!=(4,4) or not np.allclose(inverse@forward,np.eye(4),atol=1e-9,rtol=0):raise ValueError('published model/native inverse mismatch')
    mapped=points@inverse[:3,:3].T+inverse[:3,3]
    if not np.allclose(mapped[...,0],0,atol=1e-9,rtol=0):raise ValueError('native lookup leaves selected model slice')
    iy=np.floor(mapped[...,1]+.5).astype(np.int64);ix=np.floor(mapped[...,2]+.5).astype(np.int64)
    mh,mw=geometry['model_shape_yx']
    if iy.min()<0 or ix.min()<0 or iy.max()>=mh or ix.max()>=mw:raise ValueError('native lookup outside model FOV')
    return iy,ix


def save_candidate_maps(result,valid,geometry,folder,record):
    iy,ix=native_lookup(geometry);assets={}
    native_pairs=[]
    for scale in (16,32,64):
        raw=np.zeros(valid.shape,float);reliable=np.zeros_like(valid)
        for r in result.get('E1',{}).get('records',[]):
            if r['scale_pixels']!=scale:continue
            (y0,y1),(x0,x1)=r['bounds_yx'];raw[y0:y1,x0:x1]=r['margin_delta']
            if r['accepted']:reliable[y0:y1,x0:x1]=True
        reliable &= valid
        for name,array in [('response',raw),('reliable',reliable)]:
            key=f'E1-{scale}-{name}';assets[key+'-model']=save_array(folder/(key+'-model.npy'),array)
            assets[key+'-native']=save_array(folder/(key+'-native.npy'),array[iy,ix])
        native_pairs.append((f'E1-{scale}',str(scale),raw[iy,ix],reliable[iy,ix]))
    reliable=np.zeros_like(valid);score=np.zeros(valid.shape,float)
    for r in result.get('E2',{}).get('candidates',[]):
        indices=r['mask_flat_indices'];reliable.flat[indices]=True
        score.flat[indices]=np.maximum(score.flat[indices],r['peak_gap'])
    reliable &= valid
    for name,array in [('reliable',reliable),('cpf-gap-score',score)]:
        key='E2-final-'+name;assets[key+'-model']=save_array(folder/(key+'-model.npy'),array)
        assets[key+'-native']=save_array(folder/(key+'-native.npy'),array[iy,ix])
    native_pairs.append(('E2-final','benchmark-4x4',score[iy,ix],reliable[iy,ix]))
    evaluation_assets=[]
    for name,scale,scores,reliable in native_pairs:
        path=folder/(name+'-native-bound.npz')
        with path.open('xb') as stream:
            np.savez_compressed(stream,scores=scores,reliable=reliable,
                                native_case_manifest_sha256=np.asarray(record['native_manifest_sha256']),
                                SOPInstanceUID=np.asarray(record['source_sop_uid']),
                                native_slice_index=np.asarray(record['native_slice_index_zero_based']))
        evaluation_assets.append(dict(algorithm='E1' if name.startswith('E1-') else 'E2',scale=scale,
                                      path=str(path.resolve()),sha256=file_sha(path),shape=list(scores.shape)))
    return dict(assets=assets,geometry_sha256=hashlib.sha256(json.dumps(geometry,sort_keys=True).encode()).hexdigest(),
                evaluation_native_npz=evaluation_assets,
                rasterization='published native_to_model_zyx; native pixel centres; floor(model_index+0.5)',
                E1_score='per-scale raw fixed-target margin response; eligible pixels require accepted=True',
                E2_score='CPF gap on final PSMI-retained benchmark patch only; no quota fill',
                geometry_source='INTEGRATION_SHA_BOUND_PREPARED_LEDGER',GT_read=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('prepared-delivery','config','integration-source','output'):parser.add_argument('--'+name,type=Path,required=True)
    for name in ('prepared-sha','config-sha'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('existing real run preserved; reconcile before any new model run')
    delivery,cfg,spec,inputs=consume_inputs(args.prepared_delivery,args.prepared_sha,args.config,args.config_sha)
    # Verify all coordinate lookups before any prediction.
    for _,_,geometry in inputs:native_lookup(geometry)
    torch.set_num_threads(cfg['cpu_threads']);torch.manual_seed(20261009)
    adapter=baseline_source(args.integration_source)
    began=time.monotonic();model=adapter.load_verified_resnet18(Path(delivery['checkpoint_path']),CHECKPOINT_SHA)
    differentiable=DifferentiablePreparedModel(model,spec)
    load_seconds=time.monotonic()-began
    args.output.mkdir(parents=True,exist_ok=False)
    source_git=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    write_json(args.output/'submission.json',dict(status='STARTED',prepared_sha256=args.prepared_sha,config_sha256=args.config_sha,source_git=source_git))
    records=[]
    for record,p,geometry in inputs:
        index=record['case_index'];folder=args.output/f'case-{index}';folder.mkdir()
        print(json.dumps(dict(case_index=index,status='RUNNING',device='cpu')),flush=True)
        options={k:cfg['E1'][k] for k in ('patch_sizes','min_response','max_model_calls','timeout_seconds')};options['fill']=cfg['input_fill']
        e2=dict(cfg['E2']);e2['grids']=tuple(tuple(g) for g in e2['grids'])
        before=differentiable.classifier_calls
        result=run_prepared_e1_e2(p,differentiable.predict_numpy,differentiable,target=cfg['fixed_target'],e1_options=options,e2_config=HSPIConfig(**e2))
        result['actual_classifier_forwards']=differentiable.classifier_calls-before
        result.update(case_index=index,prepared_record=record,geometry_source_sha256=record['geometry']['sha256'],
                      locked_config_sha256=args.config_sha,prepared_delivery_sha256=args.prepared_sha,target_semantics=cfg['target_semantics'],
                      evidence_scope='REAL_RICORD_TRAIN_FIXED_SINGLE_SLICE_OLD_COLLECTION_PROXY_MODEL',GT_access=False)
        if 'E2' in result:result['E2_diagnosis']=hspi_witness(result['E2'],list(p.image.shape),p.valid_mask)
        result['candidate_maps']=save_candidate_maps(result,p.valid_mask,geometry,folder,record)
        write_json(folder/'result.json',result)
        summary=dict(case_index=index,status=result['status'],E1_status=result.get('E1',{}).get('status'),E2_status=result.get('E2',{}).get('status'),
                     E1_candidates=len(result.get('E1',{}).get('candidates',[])),E2_candidates=len(result.get('E2',{}).get('candidates',[])),
                     actual_model_calls=result['actual_model_calls'],actual_classifier_forwards=result['actual_classifier_forwards'],elapsed_seconds=result['elapsed_seconds'],
                     result_path=str((folder/'result.json').resolve()),result_sha256=file_sha(folder/'result.json'))
        records.append(summary);print(json.dumps(summary),flush=True)
    run=dict(schema='EPI-NEXT-FIRST-REAL-E1E2-RESULT-1',status='FAILED' if any(r['status']=='FAILED' for r in records) else 'EXECUTED',
             source_git_sha=source_git,source_hashes={p.name:file_sha(p) for p in Path(__file__).parent.glob('*.py')},
             prepared_delivery_path=str(args.prepared_delivery.resolve()),prepared_delivery_sha256=args.prepared_sha,
             config_path=str(args.config.resolve()),config_sha256=args.config_sha,checkpoint_sha256=CHECKPOINT_SHA,
             data_delivery_sha256=DATA_SHA,slice_lock_sha256=SLICE_SHA,model_load_seconds=load_seconds,elapsed_seconds=time.monotonic()-began,
             actual_model_calls=sum(r['actual_model_calls'] for r in records),actual_classifier_forwards=differentiable.classifier_calls,records=records,patient_count=3,slice_count=3,
             device='cpu',cpu_threads=cfg['cpu_threads'],MPS='NOT RUN',remote_GPU='NOT RUN',GT_access=False,training=False,
             native_masks='PUBLISHED_USING_PRODUCER_LEDGER',native_overlay_browser_validation='INTEGRATION_PENDING',
             independent_test=False,clinical_validity='NOT_ESTABLISHED',hospital_display_authorized=False,command=sys.argv)
    write_json(args.output/'run_delivery.json',run)
    print(json.dumps(dict(run_delivery_path=str((args.output/'run_delivery.json').resolve()),sha256=file_sha(args.output/'run_delivery.json'),actual_model_calls=run['actual_model_calls'])),flush=True)
    return 1 if run['status']=='FAILED' else 0


if __name__=='__main__':raise SystemExit(main())
