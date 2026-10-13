"""Generated-only executable E2 handler chain; never loads medical assets."""
import argparse
from dataclasses import asdict,replace
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from epi_next.hspi_core_v3 import HSPIConfig,Budget,source_sha,run_hspi
from epi_next.preprocessed_localization import Prepared2DInput
from epi_next.e2_handler_v4 import run_prepared_e2,plain,digest,semantics,input_binding


class Peaks(torch.nn.Module):
    def __init__(self,positions=((2,2),(81,81))):
        super().__init__();self.positions=positions
        self.weight=torch.nn.Parameter(torch.tensor(1.))
        self.calls=0
    def forward(self,x):
        self.calls+=1
        s=torch.stack([x[:,0,y,z] for y,z in self.positions],1).amax(1).clamp(0,1)*self.weight
        return torch.stack([s,torch.zeros_like(s)],1)


def fixture():
    image=np.zeros((84,84),np.float32);image[2,2]=3;image[81,81]=2
    prepared=Prepared2DInput(image,np.ones(image.shape,bool),hashlib.sha256(image.tobytes()).hexdigest(),
        'generated-identity-float32','generated-two-independent-evidence')
    identity={'classifier_kind':'2D_SLICE_CLASSIFIER','evidence_type':'SYNTHETIC',
        'model_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'model_adapter_sha256':digest('generated-identity-adapter'),'preprocessing_sha256':digest('identity')}
    c=HSPIConfig(mode='E2-CT',image_size=(84,84),grids=(7,10,13),stages=2,steps=180,
        reference_grid=7,epsilon=2,masking_policy='preserve_exterior',adapter_policy='generated identity; scalar zero; all valid')
    # Published centre ledger for exact generated identity; no patient geometry.
    geometry={'native_shape_rc':[84,84],'model_shape_yx':[84,84],'native_slice_index_zero_based':0,
        'native_to_model_zyx':np.eye(4).tolist(),'model_to_native_zyx':np.eye(4).tolist()}
    return prepared,identity,c,geometry


def reuse_payload(prepared,identity,config,stage):
    return {'schema':'E2_VERIFIED_STAGE1_REUSE_V4','verification':'FULL_TRACE_CPF_AND_SAME_STEP_MASK_VERIFIED',
        'input_binding':input_binding(prepared,identity),'branch_semantics':semantics(config),
        'core_sha256':source_sha(),'grid':7,'observed_iterations':config.steps,'optimizer_updates':config.steps,
        'feasible_count':stage['feasible_count'],'best':plain(stage['best']),'baseline_logits':stage['baseline_logits'],
        'source_evidence':'GENERATED_VERIFIED_TERMINAL_STAGE_ONLY'}


def independent_witness(config):
    # At each corner evidence, bilinear align_corners=False clamps to coarse
    # cell centre 0 / g-1: u=(2.5*g/84)-.5<0 even for g13.
    # One-hot M independently gives score=min(amplitude,1)=1, Ls=0,
    # Lm=1/g^2. The algorithm receives neither witness nor cell coordinates.
    records=[]
    for g in config.grids:
        assert 2.5*g/84-.5<0
        for amplitude,cell in ((3,0),(2,g*g-1)):
            records.append({'grid':g,'cell':cell,'amplitude':amplitude,'ls':0.,'lm':1/g**2})
            assert 1/g**2<config.beta
    return {'formula':'independent bilinear corner weight 1; retained amplitude saturated >=1',
        'records':records,'algorithm_receives_witness':False,'assertion_only':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(1);torch.manual_seed(20261011)
    prepared,identity,c,geometry=fixture()
    def write(name,value):
        raw=json.dumps(plain(value),sort_keys=True,indent=2,allow_nan=False).encode()+b'\n'
        (args.output/name).write_bytes(raw);return hashlib.sha256(raw).hexdigest()
    witness_sha=write('witness-before-optimization.json',independent_witness(c))
    rows=[];model=Peaks();result=run_prepared_e2(prepared,model,geometry,c,identity=identity,trace_sink=rows.append)
    result_sha=write('fresh-handler.json',result);trace_sha=write('scalar-coordinate-trace.json',rows)
    assert result['execution_status']=='SUCCESS'
    assert [s['cell'] for s in result['stages']]==[0,48,0,99,0,168]
    assert [v['votes'] for v in result['psmi']['votes']]==[2,2]
    assert result['new_cost']['forward']==model.calls==1086
    assert result['new_cost']['backward']==result['new_cost']['optimizer_steps']==1080
    assert np.array_equal(result['native_space']['reliable'],result['model_space']['reliable'])
    payload=reuse_payload(prepared,identity,c,result['stages'][0]);reuse_id={**identity,'reused_stage1_sha256':digest(payload)}
    reuse=run_prepared_e2(prepared,Peaks(),geometry,c,identity=reuse_id,reused_stage1=payload)
    reuse_sha=write('terminal-selection-reuse-handler.json',reuse)
    assert reuse['new_cost']['forward']==905 and reuse['new_cost']['optimizer_steps']==900
    assert np.array_equal(reuse['model_space']['reliable'],result['model_space']['reliable'])
    summary={'schema':'E2_HANDLER_SYNTHETIC_V4','status':'PASS','config':asdict(c),'config_sha256':c.sha256(),
        'core_sha256':source_sha(),'handler_sha256':hashlib.sha256(Path(__file__).parents[1].joinpath('epi_next/e2_handler_v4.py').read_bytes()).hexdigest(),
        'witness_sha256':witness_sha,'fresh_result_sha256':result_sha,'trace_sha256':trace_sha,'reuse_result_sha256':reuse_sha,
        'fresh_cost':result['new_cost'],'reuse_cost':reuse['new_cost'],'actual_cells':[s['cell'] for s in result['stages']],
        'stages':6,'scales':3,'actual_vote_counts':[v['votes'] for v in result['psmi']['votes']],
        'medical_forward':0,'medical_backward':0,'clinical_validity':'NOT_ESTABLISHED',
        'application_job_save_display_refresh':'INT_SCOPE_NOT_CLAIMED'}
    write('summary.json',summary);print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
