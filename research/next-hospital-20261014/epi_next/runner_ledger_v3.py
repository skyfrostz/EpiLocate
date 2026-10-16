"""Private experiment counters shared by children; no coordinator-state writes."""
import fcntl
import json
import os
from pathlib import Path
import time


def atomic_json(path,value):
    path=Path(path);temporary=path.with_name(path.name+f'.tmp-{os.getpid()}')
    with temporary.open('x') as stream:
        json.dump(value,stream,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


class CounterLedger:
    def __init__(self,path,*,experiment_id,max_forwards,max_reverse,create=False):
        self.path=Path(path);self.lock_path=self.path.with_suffix(self.path.suffix+'.lock')
        self.experiment_id=experiment_id;self.max_forwards=max_forwards;self.max_reverse=max_reverse
        if create:
            value=dict(schema='EPI_NEXT_EXPERIMENT_COUNTERS_V3',experiment_id=experiment_id,
                max_forwards=max_forwards,max_reverse=max_reverse,forward_attempts=0,forward_completed=0,
                loss_backward_calls=0,autograd_grad_calls=0,reverse_completed=0,optimizer_steps=0,
                forward_entered=0,reverse_entered=0,
                phase={},pending=None,last_operation_status=None,last_update_monotonic=time.monotonic())
            with self.path.open('x') as stream:
                json.dump(value,stream);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        value=self.read()
        if value.get('schema')!='EPI_NEXT_EXPERIMENT_COUNTERS_V3' or value['experiment_id']!=experiment_id or value['max_forwards']!=max_forwards or value['max_reverse']!=max_reverse:raise ValueError('global counter identity/budget mismatch')

    def read(self):return json.loads(self.path.read_text())
    def change(self,function):
        with self.lock_path.open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            try:
                value=self.read();result=function(value)
                value['last_update_monotonic']=time.monotonic();atomic_json(self.path,value)
                return result
            finally:fcntl.flock(lock,fcntl.LOCK_UN)
    def phase(self,phase):
        self.change(lambda value:value.update(phase=phase))
    def begin(self,kind):
        def reserve(value):
            if value['pending'] is not None:raise RuntimeError('UNKNOWN_INFLIGHT_COUNTER_TRANSACTION')
            if kind=='forward':
                if value['forward_attempts']>=self.max_forwards:raise RuntimeError('FORWARD_LIMIT')
                value['forward_attempts']+=1
            else:
                if value['loss_backward_calls']+value['autograd_grad_calls']>=self.max_reverse:raise RuntimeError('REVERSE_LIMIT')
                value['loss_backward_calls' if kind=='backward' else 'autograd_grad_calls']+=1
            value['pending']=dict(kind=kind,pid=os.getpid(),reserved_before_invoke=True)
        self.change(reserve)
    def end(self,kind,completed,entered=False):
        def finish(value):
            pending=value['pending']
            if pending is None or pending['kind']!=kind or pending['pid']!=os.getpid():raise RuntimeError('COUNTER_TRANSACTION_OWNER_MISMATCH')
            if completed:value['forward_completed' if kind=='forward' else 'reverse_completed']+=1
            value['last_operation_status']='COMPLETED' if completed else 'FAILED';value['pending']=None
        self.change(finish)
    def entered(self,kind):
        def mark(value):
            pending=value['pending']
            if pending is None or pending['kind']!=kind or pending['pid']!=os.getpid():raise RuntimeError('COUNTER_TRANSACTION_OWNER_MISMATCH')
            if pending.get('entered'):raise RuntimeError('COUNTER_ENTERED_TWICE')
            pending['entered']=True
            value['forward_entered' if kind=='forward' else 'reverse_entered']+=1
        self.change(mark)
    def optimizer_step(self):
        self.change(lambda value:value.update(optimizer_steps=value['optimizer_steps']+1))
