"""Persist bounded P1 engineering acceptance on GENERATED data only.

Shortened engine plan2→4→6→8 is explicit, not the approved medical profile.
Verifies same restored optimizer trajectory and eighteen metered audit forwards.
"""
import argparse
import hashlib
import json
from pathlib import Path
import torch
from epi_next.hspi_core_v3 import HSPIConfig,adopt_wave1_checkpoint
from epi_next.p1_runner_v4 import continue_case
from epi_next.p1_storage_v4 import BoundedStore
from epi_next.runner_ledger_v3 import CounterLedger
from epi_next.spi_recovery_v2 import ComputeMeter,run_spi

COUNTS={'generated_forward':0,'generated_backward':0,'extra_autograd':0,'real_forward':0,'real_backward':0}
class Model(torch.nn.Module):
    def forward(self,x):
        COUNTS['generated_forward']+=1
        y=x.square().mean((1,2,3))*.05
        return torch.stack([y*.2,y],1)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False);store=BoundedStore(args.output)
    torch.set_num_threads(1);torch.manual_seed(20261010)
    ledger=CounterLedger(store.root/'algorithm-counters.json',experiment_id='GENERATED_P1_V4',max_forwards=36,max_reverse=18,create=True)
    meter=ComputeMeter(max_forwards=36,max_reverse=18,ledger=ledger)
    outcomes=[];real_backward=torch.Tensor.backward
    def counted_backward(t,*a,**kw):COUNTS['generated_backward']+=1;return real_backward(t,*a,**kw)
    torch.Tensor.backward=counted_backward
    try:
        for index in (1,2,3):
            x=torch.linspace(.1,.9,144).reshape(1,1,12,12);valid=torch.ones(12,12,dtype=torch.bool);valid[:2]=False
            cfg=HSPIConfig(mode='E2-CT',image_size=(12,12),grids=(7,),reference_grid=7,epsilon=0,stages=1,
                           steps=8,masking_policy='preserve_exterior',adapter_policy='GENERATED_ENGINE_TEST_ONLY')
            rows=[];saved={};old=run_spi(Model(),x,valid,weight=1,steps=2,gradient_steps=(),checkpoints=(2,),
                         sink=rows.append,checkpoint_sink=lambda n,cp:saved.update({n:cp}))
            provenance={k:'a'*64 for k in ('checkpoint_sha256','source_sha256','input_sha256','model_sha256','preprocessing_sha256','execution_lock_sha256')}
            identity=f'generated-case-{index}'
            cp=adopt_wave1_checkpoint(saved[2],rows,x,valid,cfg,identity=identity,provenance=provenance,expected_baseline=old['baseline_logits'])
            result,times,trace=continue_case(Model(),x,valid,cfg,cp,meter,store,index,identity,milestones=(4,6,8))
            expected=[];full=run_spi(Model(),x,valid,weight=1,steps=8,gradient_steps=(),checkpoints=(),sink=expected.append)
            actual=[json.loads(line) for line in store.path(f'case-{index}-new-epochs.jsonl').read_text().splitlines()]
            assert len(actual)==6
            for r,e in zip(actual,expected[2:]):
                assert r['ls']==e['similarity'] and r['lm']==e['sparsity'] and r['gap']==e['peak_gap']
                assert r['logits']==[e['logits']] and r['mask'][0][0]==e['mask_before']
            assert torch.equal(result['checkpoint']['mask'][0,0],torch.tensor(full['final_mask']))
            outcomes.append({'case_index':index,'status':result['status'],'restores':times['restores'],'trace':trace,
                             'all_new_observations_exact':True,'final_mask_exact':True,'case_time_record':times})
        assert meter.forwards==36 and meter.backward==meter.optimizer_steps==18 and meter.autograd==0
        assert COUNTS['generated_forward']==72 and COUNTS['generated_backward']==48
        store.json('acceptance.json',{'schema':'P1_GENERATED_ENGINE_ACCEPTANCE_V4','status':'GENERATED_ENGINE_PASS',
            'scope':'generated12x12 analytic classifier, legacy2→4→6→8; NOT real P1 execution',
            'outcomes':outcomes,'continuation_meter':meter.receipt(),'all_generated_calls':COUNTS,
            'audit_forwards':18,'observed_optimization_forwards':18,'output_bytes_before_receipt':store.size(),
            'engine_source_sha256':hashlib.sha256(Path(continue_case.__code__.co_filename).read_bytes()).hexdigest(),
            'generator_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},terminal=True)
        path=store.path('acceptance.json');print(json.dumps({'path':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                  'real_model_calls':0,'continuation_forward':36,'continuation_backward':18,'audit_forward':18}))
    finally:torch.Tensor.backward=real_backward

if __name__=='__main__':main()
