"""Reproducible GENERATED analytic control tasks only; zero medical loaders."""
import argparse
from dataclasses import asdict,replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types
import torch
from torch import nn
from epi_next.hspi_core_v3 import HSPIConfig,Budget,run_hspi,tensor_hash,source_sha


def sha(b):return hashlib.sha256(b).hexdigest()

def plain(v):
    if torch.is_tensor(v):return v.detach().cpu().tolist()
    if isinstance(v,dict):return {k:plain(x) for k,x in v.items() if k not in ('checkpoint',)}
    if isinstance(v,(list,tuple)):return [plain(x) for x in v]
    return v


def write(path,value):
    raw=json.dumps(plain(value),sort_keys=True,indent=2,allow_nan=False).encode()+b'\n'
    with path.open('xb') as stream:stream.write(raw)
    return sha(raw)


class Peaks(nn.Module):
    def __init__(self,positions=((7,7),(75,75))):super().__init__();self.positions=positions
    def forward(self,x):
        s=torch.stack([x[:,0,y,z] for y,z in self.positions],1).amax(1).clamp(0,1)
        return torch.stack([s,torch.zeros_like(s)],1)


class Distributed(nn.Module):
    def forward(self,x):
        s=x.mean((1,2,3));return torch.stack([s,torch.zeros_like(s)],1)


class Constant(nn.Module):
    def forward(self,x):
        s=x.sum((1,2,3))*0;return torch.stack([s,s],1)


def load_sidecar(root):
    package=types.ModuleType('hspi_integration_sidecar')
    package.__path__=[str(root/'epi_next')];sys.modules[package.__name__]=package
    path=root/'epi_next/e2_result_handoff.py'
    spec=importlib.util.spec_from_file_location(package.__name__+'.e2_result_handoff',path)
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
    return mod,sha(path.read_bytes())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--integration-source',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(1);torch.manual_seed(20261010)
    c=HSPIConfig(image_size=(84,84),grids=(5,6,7),stages=2,steps=180,reference_grid=5,epsilon=2)
    x=torch.zeros(1,1,84,84);x[0,0,7,7]=3;x[0,0,75,75]=2
    # Independent analytic feasible witness persisted BEFORE any optimization.
    witness=[]
    for grid in c.grids:
        u=max(0,(7+.5)*grid/84-.5)
        for amplitude,cell in ((3,0),(2,grid*grid-1)):
            score=min(1,amplitude*(1-u)**2)
            record=dict(grid=grid,cell=cell,independent_ls=(1-score)**2,
                        independent_lm=1/(grid*grid),alpha=c.alpha,beta=c.beta)
            assert record['independent_ls']<c.alpha and record['independent_lm']<c.beta
            witness.append(record)
    witness_sha=write(args.output/'feasibility-witness-before-optimization.json',
                      dict(config=asdict(c),records=witness,algorithm_receives_witness=False))
    tasks=[]
    def execute(name,model,img,cfg,budget=None):
        r=run_hspi(model,img,cfg,identity=name+';generated_model_source='+sha(Path(__file__).read_bytes()),
                   budget=budget,include_masks=True)
        path=args.output/(name+'.json');digest=write(path,r)
        record=dict(name=name,result=r,path=path,digest=digest,config=cfg,input=img)
        tasks.append(record);return r
    chain=execute('two-independent-peaks',Peaks(),x,c)
    assert chain['status']=='COMPLETED' and len(chain['psmi']['patches'])==2
    assert [s['cell'] for s in chain['stages']]==[0,24,0,35,0,48]
    single=replace(c,grids=(5,),reference_grid=5,epsilon=0,stages=1)
    left=execute('left-single-evidence',Peaks(((7,7),)),x,single)
    moved=execute('moved-single-evidence',Peaks(((75,75),)),x,single)
    assert left['stages'][0]['cell']==0 and moved['stages'][0]['cell']==24
    negative=execute('distributed-infeasible',Distributed(),torch.ones(1,1,28,28),
                     replace(c,image_size=(28,28),grids=(7,8,9),reference_grid=7))
    assert negative['status']=='NO_RELIABLE_RESPONSE' and not negative['full_plan_completed']
    tie=execute('tie-ambiguity',Constant(),x,replace(single,stages=2,steps=70))
    assert tie['stages'][1]['repeated_exclusion']
    partial=execute('partial-forward-budget',Peaks(),x,c,Budget(max_forward=37))
    assert partial['status']=='PARTIAL_BUDGET'
    clock=[0.]
    class Slow(Peaks):
        def forward(self,x):clock[0]+=5;return super().forward(x)
    timeout=execute('timeout-pending-observation',Slow(),x,c,Budget(seconds=8,clock=lambda:clock[0]))
    assert timeout['cost']['backward']==0 and timeout['stages'][0]['observed_iterations']==1
    class Bad(nn.Module):
        def forward(self,x):return torch.full((1,2),float('nan'))
    failed=execute('nonfinite-failure',Bad(),x,c)
    assert failed['status']=='FAILED'
    mod,sidecar_sha=load_sidecar(args.integration_source)
    # Convert the ACTUAL autonomous optimizer result bytes, no oracle masks.
    task=tasks[0];raw=task['path'].read_bytes();plans=[];branches=[]
    for si,g in enumerate(c.grids):
        for j in range(1,c.stages+1):
            plan=dict(scale_index=si,grid_yx=[g,g],stage=j,max_iterations=c.steps);plans.append(plan)
            s=next(s for s in chain['stages'] if s['grid']==g and s['stage']==j)
            branches.append(dict(scale_index=si,grid_yx=[g,g],stage=j,status='COMPLETE',
                completed_iterations=s['observed_iterations'],selected_iteration=s['best']['epoch'],
                selection_scope='FULL_PLANNED_BUDGET',reason=None,
                trace_asset=dict(path='optimizer-result.json',sha256=sha(raw))))
    axes={axis:dict(status='GENERATED_CONTROL_VERIFIED',scope='analytic control only',reference=task['digest'])
          for axis in ('METHOD_SPEC','IMPLEMENTATION','SYNTHETIC_CHAIN')}
    axes.update({axis:'NOT RUN' for axis in ('REAL_CT_COMPONENT','REAL_CT_FULL_CHAIN','LOCALIZATION_BENEFIT')})
    envelope=dict(schema='EPI-NEXT-E2-RESULT-HANDOFF-3',method_mode='E2-REF',
        algorithm_version='hspi-core-v3;'+source_sha(),run_profile=dict(profile_id='generated-two-peaks-3scale-2stage',
        profile_kind='COMPONENT',config_sha256=c.sha256()),model_sha256=sha(Path(__file__).read_bytes()),
        input_sha256=tensor_hash(x),preprocessing_sha256=sha(b'generated identity preprocessing'),
        source_result=dict(path=str(task['path'].resolve()),sha256=task['digest']),execution_status='SUCCESS',
        algorithm_status=chain['status'],psmi_status='FINALIZED',acceptance_axes=axes,
        planned_branches=plans,branches=branches)
    receipt=mod.save_handoff(args.output/'integration-sidecar','EPI-NEXT-HSPI-v3-generated-two-peaks',envelope,
                             {'optimizer-result.json':raw})
    for s in chain['stages']:
        assert s['observed_iterations']==s['optimizer_updates']==180
    summary=dict(schema='HSPI_GENERATED_CHAIN_DELIVERY_V3',core_source_sha256=source_sha(),
        generator_sha256=sha(Path(__file__).read_bytes()),config_sha256=c.sha256(),
        witness_sha256=witness_sha,witness_persisted_before_optimization=True,
        tasks=[dict(name=t['name'],result_sha256=t['digest'],status=t['result']['status'],
                    cost=t['result']['cost'],full_plan_completed=t['result']['full_plan_completed']) for t in tasks],
        integration_source_sha256=sidecar_sha,integration_receipt=plain(receipt),
        sidecar_epoch_policy='one-based pre-update observation; optimizer update count stored separately',
        real_forward=0,real_backward=0,clinical_claim=False)
    digest=write(args.output/'delivery.json',summary)
    print(json.dumps(dict(output=str(args.output.resolve()),delivery_sha256=digest,
        task_count=len(tasks),real_forward=0,sidecar='SAVED_ACTUAL_OPTIMIZER_BYTES'),indent=2))

if __name__=='__main__':main()
