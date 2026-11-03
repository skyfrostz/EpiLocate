"""Offline plan validation and supervision adapter; NO real experiment launcher.

No model/data/checkpoint loaders. CLI validates local proposal JSON only.
The explicit --execute gate always refuses; adding a real loader requires a new
reviewed implementation and exact approval/slot/runtime bindings.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from .hspi_core_v3 import HSPIConfig, Budget, BudgetStopped, source_sha


def config_from_proposal(p):
    a=p['algorithm']; i=p['input_policy']
    return HSPIConfig(mode=p['method_mode'],image_size=tuple(i['input_hw']),
        grids=tuple(p['grid_sides']),stages=p['stages_per_scale'],steps=p['max_steps_per_stage_scale'],
        zeta=a['mask_initial_value'],lr=a['learning_rate'],lam=a['lambda_weight'],
        alpha=a['alpha'],beta=a['beta'],reference_grid=p['reference_grid_side'],
        epsilon=p['psmi_min_other_scale_votes'],adam_betas=tuple(a['optimizer']['betas']),
        adam_eps=a['optimizer']['eps'],align_corners=a['soft_interpolation']['align_corners'],
        adapter_policy=json.dumps(i,sort_keys=True,separators=(',',':')),
        masking_policy='preserve_exterior').validate()


def dry_run(path):
    raw=Path(path).read_bytes();p=json.loads(raw);c=config_from_proposal(p)
    binding=p['source_binding']
    if binding['core_sha256']!=source_sha():raise ValueError('CORE_SOURCE_HASH_MISMATCH')
    if binding['profile_adapter_sha256']!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError('PROFILE_ADAPTER_SOURCE_HASH_MISMATCH')
    if p['authority']!='NOT_AUTHORIZED' or p['execution_status']!='NOT_RUN':
        raise ValueError('offline proposals cannot self-authorize')
    cost=p['cost']
    if cost['global_forward_cap']<1 or cost['global_reverse_cap']<1:
        raise ValueError('explicit global caps required')
    return {'schema':'HSPI_PROFILE_DRY_RUN_V3','profile':p['profile'],
        'config_file_sha256':hashlib.sha256(raw).hexdigest(),'core_config_sha256':c.sha256(),
        'core_config':c.__dict__,'uninterrupted_one_case_worst_cost':c.worst_cost(),
        'proposed_global_caps':{'forward':cost['global_forward_cap'],'reverse':cost['global_reverse_cap']},
        'real_forward':0,'real_backward':0,'status':'OFFLINE_CONFIG_VALIDATED',
        'execution_gate':'BLOCKED_NO_NEW_APPROVAL; UNKNOWN_SLOT_BLOCKS; REAL_LOADER_NOT_IMPLEMENTED'}


class MeterBudget(Budget):
    """Bridge to existing W1 ComputeMeter/INTEGRATION ChildGuard and CounterLedger.

    Calls use meter.forward/reverse, which reserve/enter/complete and invoke the
    independent guard immediately before real work. No counter reset. This class
    grants no execution permission; caller must bind approval before loading data.
    """
    def __init__(self,meter):
        super().__init__();self.meter=meter;self._sync()
    def _sync(self):
        self.forward=self.meter.forwards;self.backward=self.meter.backward
        self.optimizer_steps=self.meter.optimizer_steps
    def permits(self,forwards=0,backwards=0):
        self._sync()
        try:self.meter.check()
        except RuntimeError as exc:self.reason=str(exc);return False
        if self.forward+forwards>self.meter.max_forwards:self.reason='FORWARD_BUDGET'
        elif self.meter.backward+self.meter.autograd+backwards>self.meter.max_reverse:self.reason='BACKWARD_BUDGET'
        return self.reason is None
    def forward_call(self,function):
        try:return self.meter.forward(lambda unused:function(),None)
        except RuntimeError as exc:
            from .spi_recovery_v2 import StopBudget
            if isinstance(exc,StopBudget):raise BudgetStopped(str(exc)) from exc
            raise
        finally:self._sync()
    def backward_call(self,function):
        try:return self.meter.reverse('backward',function)
        except RuntimeError as exc:
            from .spi_recovery_v2 import StopBudget
            if isinstance(exc,StopBudget):raise BudgetStopped(str(exc)) from exc
            raise
        finally:self._sync()
    def did_optimizer_step(self):
        self.meter.did_optimizer_step();self._sync()
    def counts(self):
        value=super().counts();value['meter_receipt']=self.meter.receipt()
        value['extra_autograd']=self.meter.autograd
        return value


def refuse_execution(execution_lock=None, slot_status=None):
    if slot_status=='UNKNOWN':raise ValueError('BLOCKED_UNKNOWN_SLOT')
    if execution_lock is None:raise ValueError('BLOCKED_NO_NEW_APPROVAL')
    # There is deliberately no medical loader hidden behind the planning CLI.
    raise ValueError('REAL_EXECUTION_ENTRY_NOT_IMPLEMENTED')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proposal',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--slot-status',default='UNKNOWN')
    args=parser.parse_args()
    if args.execute:refuse_execution(slot_status=args.slot_status)
    print(json.dumps(dry_run(args.proposal),sort_keys=True,indent=2))

if __name__=='__main__':main()
