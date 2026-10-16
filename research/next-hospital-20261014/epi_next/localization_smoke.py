"""CPU-only deterministic synthetic E1/E2/F1 exercise (no DICOM/checkpoints)."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import numpy as np
import torch
import torch.nn.functional as F
from .localization import BudgetConfig,fixed_target_response,occlusion_2d,hierarchical_input_occlusion_3d
from .hspi import HSPIConfig,hspi_reference


class SyntheticClassifier(torch.nn.Module):
    def __init__(self): super().__init__();self.weight=torch.nn.Parameter(torch.tensor(1.))
    def forward(self,x):
        score=(x[:,:,0:2,0:2].sum((1,2,3))+.3*x[:,:,6,6].sum(1))*self.weight
        return torch.stack((score*.2,score),1)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();torch.set_num_threads(1);torch.manual_seed(20261009)
    if args.output.exists():
        raise FileExistsError(args.output)
    started=time.monotonic();model=SyntheticClassifier()
    image=np.ones((8,8),dtype=np.float32);valid=np.ones_like(image,dtype=bool)
    def predict(a):
        with torch.no_grad():return model(torch.from_numpy(a)[None,None]).numpy()[0]
    e1=occlusion_2d(predict,image,valid,1,patch_sizes=(2,4))
    hcfg=HSPIConfig(grids=((4,4),(5,5)),stages=2,epochs=60,learning_rate=.05,
                   similarity_threshold=5.,sparsity_threshold=.6,min_other_scale_support=1)
    e2=hspi_reference(model,torch.from_numpy(image)[None,None],hcfg,torch.from_numpy(valid))
    volume=np.ones((8,8,8),dtype=np.float32);v=np.ones_like(volume,bool);coarse=volume.copy()
    cfg=BudgetConfig(max_extra_evaluations=4,scales_mm=(1.,2.,3.))
    def predict3d(a):return [0.,float(a.sum())]
    f1=hierarchical_input_occlusion_3d(predict3d,volume,v,coarse,1,(1,1,1),cfg)
    f1_repeat=hierarchical_input_occlusion_3d(predict3d,volume,v,coarse,1,(1,1,1),cfg)
    zero=hierarchical_input_occlusion_3d(lambda a:[0.,1.],volume,v,coarse,1,(1,1,1),BudgetConfig(scales_mm=(1.,)))
    # Local smoothing baseline sensitivity is exercised in model-input units.
    smooth=F.avg_pool2d(torch.from_numpy(image)[None,None],3,stride=1,padding=1,count_include_pad=False).numpy()[0,0]
    e1_smooth=occlusion_2d(predict,image,valid,1,patch_sizes=(2,4),fill=smooth)
    saturation=fixed_target_response([0.,100.],[0.,99.],1)
    target_switch=fixed_target_response([2.,3.],[2.,1.],1)
    checks=dict(saturated_probability_zero=saturation['probability_delta']==0.,
                margin_preserved=saturation['margin_delta']==1.,fixed_target=target_switch['target']==1,
                e1_candidates=e1['status']=='OK',e2_candidates=e2['status']=='OK',
                f1_budget=f1['status']=='PARTIAL_BUDGET' and f1['model_calls']==5,
                f1_probes=f1['random_probes_completed']==2,
                deterministic_records=f1['records']==f1_repeat['records'],
                no_forced_candidates=zero['status']=='NO_RELIABLE_RESPONSE',
                smoothing_sensitivity=e1_smooth['status']=='NO_RELIABLE_RESPONSE')
    config=dict(e1_patch_sizes_pixels=[2,4],e1_min_response=0.,e1_fill=0.,hspi=asdict(hcfg),f1=asdict(cfg))
    config_bytes=json.dumps(config,sort_keys=True).encode()
    sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).parent/'localization.py',Path(__file__).parent/'hspi.py',Path(__file__))}
    payload=dict(run_id='EPI-NEXT-LOCALIZATION-CPU-SYNTHETIC-20261009',evidence='SYNTHETIC_NUMERICAL_ONLY',
                 git_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                 source_sha256=sources,config=config,config_sha256=hashlib.sha256(config_bytes).hexdigest(),
                 input_manifest_sha256=hashlib.sha256(image.tobytes()+volume.tobytes()).hexdigest(),
                 checkpoint_sha256=hashlib.sha256(model.weight.detach().numpy().tobytes()).hexdigest(),
                 checkpoint_type='SYNTHETIC_ONE_PARAMETER_NOT_CLINICAL',seed=20261009,
                 environment=dict(python=sys.version,torch=torch.__version__,numpy=np.__version__,hardware=platform.machine(),platform=platform.platform(),device='cpu',torch_threads=torch.get_num_threads()),
                 peak_gpu_memory_bytes=None,gpu_status='NOT RUN',elapsed_seconds=time.monotonic()-started,
                 checks=checks,status='PASS' if all(checks.values()) else 'FAIL',
                 saturation=saturation,target_switch=target_switch,e1=e1,e2=e2,f1=f1,
                 e1_smoothed_fill=e1_smooth,no_response=zero,
                 process_state_after_command='SYNCHRONOUS_NO_CHILD_PROCESSES')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n')
    digest=hashlib.sha256(args.output.read_bytes()).hexdigest()
    print(json.dumps(dict(status=payload['status'],checks=checks,output=str(args.output),sha256=digest),indent=2))
    return 0 if all(checks.values()) else 1


if __name__=='__main__':raise SystemExit(main())
