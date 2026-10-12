"""Task-local cumulative IO adapter around the unchanged shared supervisor."""
import ast
from contextlib import contextmanager, redirect_stdout, redirect_stderr
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from types import SimpleNamespace

from qa.hospital_mvp_protected import storage_class

CAP = 64 * 1024 * 1024
RESERVE = 8 * 1024 * 1024
LOG_CAP = 1024 * 1024
LEDGER_WRITE_CHARGE = 512


def output_lock(reference):
    """Reuse the existing IO-lock function verbatim, without importing Torch."""
    path=Path(reference['path']);raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=reference['sha256']:raise ValueError('IO_SOURCE_DRIFT')
    tree=ast.parse(raw);nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='supervisor_output_lock']
    if len(nodes)!=1:raise ValueError('IO_LOCK_SOURCE_CONTRACT')
    scope=dict(contextmanager=contextmanager,Path=Path,os=os,fcntl=fcntl,time=time)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),scope)
    return scope['supervisor_output_lock']


class OutputBudget:
    def __init__(self,value):
        self.root=Path(value['supervision_root']);self.science=Path(value['output_root'])
        self.slot=Path(value['queue_root'])/'slots'/value['job_id']
        self.job_id=value['job_id'];self.ledger=self.root/'output-written-ledger.json'
        self.lock=output_lock(value['io_lock_source']);self.errors=[];self.log_bytes={};self.discarded={};self.reporting=False
        self.store=storage_class()(self.root,cap=CAP,reserve=RESERVE,extra_roots=(self.science,))
        with self.lock(self.root):
            if self.ledger.exists():self.ledger_value()
            else:
                self.store.ensure(LEDGER_WRITE_CHARGE)
                self.save_ledger(dict(schema='EPI_NEXT_E2_R_WRITTEN_LEDGER_V1',job_id=self.job_id,
                    cumulative_reserved_bytes=LEDGER_WRITE_CHARGE,sequence=0,terminal_reserved_bytes=0))
    def ledger_value(self):
        if any(self.root.glob(self.ledger.name+'.*.tmp')):raise RuntimeError('OUTPUT_LEDGER_TRANSACTION_UNKNOWN')
        if self.ledger.is_symlink():raise ValueError('OUTPUT_LEDGER_SYMLINK')
        value=json.loads(self.ledger.read_bytes())
        if value['schema']!='EPI_NEXT_E2_R_WRITTEN_LEDGER_V1' or value['job_id']!=self.job_id:
            raise ValueError('OUTPUT_LEDGER_IDENTITY')
        return value
    def save_ledger(self,value):
        raw=json.dumps(value,sort_keys=True).encode()
        if len(raw)>LEDGER_WRITE_CHARGE:raise ValueError('OUTPUT_LEDGER_RESERVE_TOO_SMALL')
        tmp=self.ledger.with_name(self.ledger.name+f'.{os.getpid()}.{threading.get_ident()}.tmp')
        with tmp.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,self.ledger)
    def charge(self,size,terminal=False):
        """Called under the shared existing IO lock, before any attempted write."""
        self.refresh();self.store.ensure(size+LEDGER_WRITE_CHARGE,terminal=terminal)
        value=self.ledger_value();charge=size+LEDGER_WRITE_CHARGE
        if value['cumulative_reserved_bytes']+charge>CAP-(0 if terminal else RESERVE):
            raise RuntimeError('CUMULATIVE_WRITTEN_BYTE_LIMIT')
        value['cumulative_reserved_bytes']+=charge;value['sequence']+=1
        if terminal:value['terminal_reserved_bytes']+=charge
        self.save_ledger(value)  # reservation persists even if the payload write fails
    def refresh(self):
        self.store.extra_roots=(self.science,)+( (self.slot,) if self.slot.exists() else () )
    def owned(self,path):
        path=Path(path).absolute()
        return any(path.is_relative_to(p.absolute()) for p in (self.root,self.science,self.slot))
    def ensure(self,size=0,terminal=False):
        self.refresh();self.store.ensure(size,terminal=terminal)
        if self.ledger_value()['cumulative_reserved_bytes']+size>CAP-(0 if terminal else RESERVE):
            raise RuntimeError('CUMULATIVE_WRITTEN_BYTE_LIMIT')
    def check(self):
        if self.errors:raise RuntimeError('E2_R_OUTPUT_LIMIT_STOP')
        with self.lock(self.root):self.ensure()
    def write_new(self,path,raw,*,terminal=False):
        if not self.owned(path):raise ValueError('UNOWNED_OUTPUT_PATH')
        with self.lock(self.root):
            self.charge(len(raw),terminal)
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    def atomic(self,path,value):
        raw=json.dumps(value,sort_keys=True,allow_nan=False).encode()
        with self.lock(self.root):
            self.charge(len(raw),terminal=self.reporting)  # old target plus transient, and no lifecycle refund
            tmp=Path(path).with_name(Path(path).name+f'.{os.getpid()}.{threading.get_ident()}.tmp')
            with tmp.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            os.replace(tmp,path)
    def append(self,stream,raw,*,log=False):
        raw=raw.encode() if isinstance(raw,str) else raw
        name=str(stream.name)
        with self.lock(self.root):
            if log and self.log_bytes.get(name,0)+len(raw)>LOG_CAP:
                if 'LOG_BYTE_LIMIT' not in self.errors:self.errors.append('LOG_BYTE_LIMIT')
                self.discarded[name]=self.discarded.get(name,0)+len(raw)
                return len(raw)  # drain pipes; stop is requested by the unchanged monitor
            try:self.charge(len(raw),terminal=self.reporting and not log)
            except BaseException:
                if 'CUMULATIVE_OUTPUT_LIMIT' not in self.errors:self.errors.append('CUMULATIVE_OUTPUT_LIMIT')
                if log:self.discarded[name]=self.discarded.get(name,0)+len(raw);return len(raw)
                raise
            stream.write(raw);stream.flush()
            if log:self.log_bytes[name]=self.log_bytes.get(name,0)+len(raw)
        return len(raw)
    def final(self):
        with self.lock(self.root):
            self.refresh();total=self.store.size();written=self.ledger_value()['cumulative_reserved_bytes']
        value=dict(schema='EPI_NEXT_E2_R_TOTAL_OUTPUT_V1',cap=CAP,reporting_reserve=RESERVE,
            retained_bytes_before_audit=total,log_cap_each=LOG_CAP,errors=self.errors,
            cumulative_reserved_before_audit=written,ledger_write_charge_each=LEDGER_WRITE_CHARGE,
            discarded_log_bytes=self.discarded,roots=['science','supervision_including_parent_child_logs','exact_owned_slot'],
            accounting='lifecycle attempted payload writes + conservative ledger writes; no replacement/failure refund; retained/temp independently checked')
        value['cumulative_reserved_after_audit']=written
        for _ in range(4):value['cumulative_reserved_after_audit']=written+len(json.dumps(value,sort_keys=True).encode())+LEDGER_WRITE_CHARGE
        self.write_new(self.root/'output-budget.json',json.dumps(value,sort_keys=True).encode(),terminal=True)
        return value


class Stream:
    def __init__(self,budget,stream,log=False):self.budget=budget;self.stream=stream;self.log=log
    def write(self,raw):return self.budget.append(self.stream,raw,log=self.log)
    def __getattr__(self,name):return getattr(self.stream,name)
    def __enter__(self):return self
    def __exit__(self,*args):return self.stream.__exit__(*args)


def drain_pipe(pipe,target,budget):
    try:
        while True:
            raw=pipe.read(65536)
            if not raw:break
            budget.append(target,raw,log=True)
    except BaseException as exc:budget.errors.append('LOG_DRAIN_'+type(exc).__name__)
    finally:pipe.close()


@contextmanager
def parent_native_logs(budget,out,err):
    backups=[];threads=[]
    try:
        for fd,target in ((1,out),(2,err)):
            backup=os.dup(fd);read_fd,write_fd=os.pipe();backups.append((fd,backup))
            thread=threading.Thread(target=drain_pipe,args=(os.fdopen(read_fd,'rb'),target,budget),daemon=True)
            thread.start();threads.append(thread);os.dup2(write_fd,fd);os.close(write_fd)
        yield
    finally:
        for fd,backup in backups:os.dup2(backup,fd);os.close(backup)
        for thread in threads:thread.join(timeout=.25)
        if any(t.is_alive() for t in threads):raise RuntimeError('OWN_PARENT_LOG_DRAIN_UNKNOWN')


@contextmanager
def bounded_supervisor(value,modules):
    """Same supervisor/identity signaling; IO callbacks only, no scheduler/queue lock."""
    Path(value['supervision_root']).mkdir(mode=0o700,parents=True,exist_ok=False)
    Path(value['output_root']).mkdir(mode=0o700,parents=True,exist_ok=False)
    budget=OutputBudget(value);wave=modules['wave1_supervisor'];writer=modules['coordinator_writer'];execution=modules['execution_lock']
    saved={ (m,k):getattr(m,k) for m,k in ((wave,'atomic_json'),(wave,'write_new'),(writer,'write_new'),(execution,'write_new'),(wave,'subprocess')) }
    original_open=Path.open
    def write(path,raw):
        if budget.owned(path):return budget.write_new(path,raw,terminal=Path(path).name in {'supervisor-receipt.json','runner-complete.json','finished.json'})
        return saved[(writer,'write_new')](path,raw)
    wave.write_new=writer.write_new=execution.write_new=write
    wave.atomic_json=lambda p,v:budget.atomic(p,v) if budget.owned(p) else saved[(wave,'atomic_json')](p,v)
    def opened(path,*args,**kwargs):
        stream=original_open(path,*args,**kwargs)
        return Stream(budget,stream) if budget.owned(path) and Path(path).name=='child-samples.jsonl' and 'a' in (args[0] if args else kwargs.get('mode','r')) else stream
    Path.open=opened
    def popen(argv,**kwargs):
        stdout,stderr=kwargs.pop('stdout'),kwargs.pop('stderr')
        process=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)
        threads=[]
        for pipe,target in ((process.stdout,stdout),(process.stderr,stderr)):
            thread=threading.Thread(target=drain_pipe,args=(pipe,target,budget),daemon=True);thread.start();threads.append(thread)
        class Process:
            def poll(self):
                result=process.poll()
                return None if result is not None and any(t.is_alive() for t in threads) else result
            def __getattr__(self,name):return getattr(process,name)
        return Process()
    wave.subprocess=SimpleNamespace(Popen=popen,check_output=subprocess.check_output)
    monitor=wave.SystemMonitor()
    class Monitor:
        def processes(self):return monitor.processes()
        def pressure(self):budget.check();return monitor.pressure()
    try:
        with original_open(budget.root/'parent-stdout.log','xb') as out,original_open(budget.root/'parent-stderr.log','xb') as err:
            with parent_native_logs(budget,out,err),redirect_stdout(Stream(budget,out,True)),redirect_stderr(Stream(budget,err,True)):
                try:yield budget,Monitor()
                except BaseException as exc:
                    budget.errors.append('PARENT_EXCEPTION_'+type(exc).__name__)
                    print(json.dumps(dict(status='FAILED',error_type=type(exc).__name__),sort_keys=True))
                    raise
    finally:
        try:budget.final()
        finally:
            Path.open=original_open
            for (module,key),old in saved.items():setattr(module,key,old)


@contextmanager
def bounded_child(value,modules):
    budget=OutputBudget(value);wave=modules['wave1_supervisor'];writer=modules['coordinator_writer']
    old_atomic,old_write,old_open=wave.atomic_json,writer.write_new,Path.open
    wave.atomic_json=budget.atomic
    writer.write_new=lambda p,raw:budget.write_new(p,raw,terminal=Path(p).name=='runner-complete.json')
    old_wave_write=wave.write_new;wave.write_new=writer.write_new
    def opened(path,*args,**kwargs):
        stream=old_open(path,*args,**kwargs)
        return Stream(budget,stream) if Path(path).name=='child-samples.jsonl' and budget.owned(path) else stream
    Path.open=opened
    try:yield budget
    finally:wave.atomic_json=old_atomic;wave.write_new=old_wave_write;writer.write_new=old_write;Path.open=old_open
