"""Prepared streaming input/budget logic; hard-ceiling gate blocks real launch.

No Torch import, model construction, real pixel loader or approval-writing API.
Polling is explicitly not a hard RSS/Metal-driver cap. No bypass CLI exists.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import time

import numpy as np
from .encoder_volume_dry_run import area_matrix
from .encoder_real_input import read_bound_json
from .encoder_ctfm_mps_smoke import file_sha,write_new

CONFIG_SHA='1def3c41fe3c205df7a5f1c5fc17f897489f68d8a57b19772cc1a34763fe839b'
APPROVAL_SHA='0000000000000000000000000000000000000000000000000000000000000000'


class BudgetStop(RuntimeError):pass


class ForwardBudget:
    """Operation-boundary guard, not a hard time/memory quota or model caller."""
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.total_deadline=clock()+1200;self.case_deadline=None
        self.case_index=0;self.total_calls=0;self.device_calls={};self.failed=False

    def check(self):
        if self.failed:raise BudgetStop('prior failure; no retry/next case')
        if self.clock()>=self.total_deadline:
            self.failed=True;raise BudgetStop('TOTAL1200_DEADLINE')
        if self.case_deadline is not None and self.clock()>=self.case_deadline:
            self.failed=True;raise BudgetStop('CASE120_DEADLINE')

    def begin_case(self,index):
        self.check()
        if self.case_deadline is not None or index!=self.case_index+1 or index not in (1,2,3):
            raise BudgetStop('fixed serial case order required')
        self.case_index=index;self.device_calls={'cpu':0,'mps':0}
        self.case_deadline=min(self.clock()+120,self.total_deadline)

    def before_forward(self,device):
        self.check()
        if self.case_deadline is None or device not in self.device_calls:
            raise BudgetStop('active case and explicit device required')
        if self.total_calls>=24 or self.device_calls[device]>=4:
            self.failed=True;raise BudgetStop('FORWARD_LIMIT')
        # Caller must enter exactly one encoder call after this reservation.
        # Actual network calls must also be recorded by the frozen adapter.
        self.total_calls+=1;self.device_calls[device]+=1

    def end_case(self,passed):
        self.check()
        if not passed or self.device_calls!={'cpu':4,'mps':4}:
            self.failed=True;raise BudgetStop('CASE_FAILURE_OR_INCOMPLETE_CALLS')
        self.case_deadline=None

    def owned_child_timeout_seconds(self):
        self.check()
        if self.case_deadline is None:raise BudgetStop('no active case')
        return min(self.case_deadline,self.total_deadline)-self.clock()


def stream_area_input(oriented_hu,target=(128,128,128),check=lambda:None,normalize_hu=True):
    """Plane-streamed area averages; invoked only on small synthetic arrays here.

    A future authorized loader supplies the already oriented, hash-bound memmap.
    The final tensor is FP32. Source/matrix/plane workspace is not a kernel quota.
    """
    if oriented_hu.ndim!=3 or any(t>n or t<1 for t,n in zip(target,oriented_hu.shape)):
        raise ValueError('finite3D downsample geometry required')
    matrices=[area_matrix(n,t) for n,t in zip(oriented_hu.shape,target)]
    out=np.empty(target,dtype=np.float32)
    for k,weights in enumerate(matrices[0]):
        check();plane=np.zeros(oriented_hu.shape[1:],dtype=np.float64)
        for source_k in np.flatnonzero(weights):
            check();source=np.asarray(oriented_hu[source_k],dtype=np.float64)
            if not np.isfinite(source).all():raise ValueError('nonfinite input')
            if normalize_hu:source=(np.clip(source,-1024,2048)+1024)/3072
            plane+=weights[source_k]*source
        check();out[k]=matrices[1]@plane@matrices[2].T
    check()
    return np.ascontiguousarray(out[None,None])


def sampled_peak(values,sample_times):
    """Deterministic synthetic counterexample, not an actual memory monitor."""
    return max(value for timestamp,value in values if timestamp in sample_times)


def feasibility(config_path,approval_path):
    config=read_bound_json(config_path,CONFIG_SHA)
    approval=read_bound_json(approval_path,APPROVAL_SHA)
    if (approval['status']!='APPROVED_WITH_HARD_LIMIT_EXECUTION_GATE'
        or approval['ctfm_implementation_binding']['sha256']!=CONFIG_SHA
        or config['max_actual_encoder_calls_total']!=24
        or config['child_seconds_per_case_including_loading']!=120
        or config['wall_seconds_total_including_preprocessing_loading_and_reporting']!=1200):
        raise ValueError('fixed authorization/config scope mismatch')
    source=Path(importlib.util.find_spec('torch').origin).parent/'mps/__init__.py'
    cap=6*1024**3
    return dict(schema='CTFM_HARD_CAP_FEASIBILITY_V2',status='BLOCKED',
        reason='MACOS_RSS_AND_TOTAL_MPS_DRIVER_HARD_CEILINGS_NOT_GUARANTEED_BY_AVAILABLE_RUNNER',
        approved_budget='APPROVED_WITH_HARD_LIMIT_EXECUTION_GATE',approval_receipt_sha256=APPROVAL_SHA,
        config_sha256=CONFIG_SHA,prepared_guard_source_sha256=file_sha(__file__),
        local_torch_mps_API_source_path=str(source),local_torch_mps_API_source_sha256=file_sha(source),
        API_evidence=dict(allocator_lines=[85,107],current_tensor_memory_lines=[110,117],total_driver_memory_lines=[120,127]),
        RSS_hard_cap_guaranteed=False,MPS_total_driver_hard_cap_guaranteed=False,
        allocator_limit_scope='allocator OOM threshold; API does not promise a kernel quota on all Metal/MPSGraph driver bytes',
        current_RLIMIT_RSS=list(resource.getrlimit(resource.RLIMIT_RSS)),
        current_RLIMIT_AS=list(resource.getrlimit(resource.RLIMIT_AS)),
        RSS_kernel_quota_enforcer='NONE_IMPLEMENTED_OR_VALIDATED; no universal macOS impossibility asserted',
        existing_M2_RSS_poll_nominal_seconds=.05,existing_M2_MPS_driver_sample_nominal_seconds=.02,
        existing_M2_system_pressure_poll_nominal_seconds=.5,
        transient_overshoot_possible=True,
        stop_delay='sample gap + API/ps time + scheduler delay + signal delivery + resource release; hard upper bound NOT ESTABLISHED',
        sampled_peak_is_not_instantaneous_peak=True,
        unified_memory_rule='RSS and driver tracked separately and may overlap; do not sum',
        prepared_operation_guards=dict(total_seconds=1200,per_case_seconds=120,calls_per_device_per_case=4,total_calls=24,
            checks='before every case/forward and streaming plane; post-call deadline check records overrun honestly',
            owned_child_timeout='min remaining per-case and remaining global wall; actual launch gated off',
            no_retry=True),
        synthetic_polling_counterexample=dict(samples_at_seconds=[0,.020],hidden_event_at_seconds=.010,
            sampled_bytes=5*1024**3,instantaneous_bytes=7*1024**3,threshold_bytes=cap),
        real_CPU_MPS_worker_launch='DISABLED_BEFORE_WEIGHT_OR_CT_PIXEL_LOAD',
        real128_input_preparation='NOT RUN',real128_model_encoding='NOT RUN',
        actual_encoder_calls=0,actual_mps_calls=0,backward_calls=0,
        no_new_cap_relaxation_or_approval_requested=True,
        next_action='chief consumes this feasibility block before allocating slot; no automatic downgrade to monitored soft limits')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--approval',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();result=feasibility(args.config,args.approval)
    write_new(args.output,result)
    print(json.dumps(dict(status=result['status'],reason=result['reason'],output=str(args.output),
        sha256=file_sha(args.output),actual_encoder_calls=0)))
    return 3


if __name__=='__main__':raise SystemExit(main())
