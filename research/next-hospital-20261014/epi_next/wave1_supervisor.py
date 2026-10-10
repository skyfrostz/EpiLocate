"""Cooperative child guard plus independent own-process Wave1 supervisor.

50ms RSS/system and 20ms child telemetry are targets, not instantaneous caps.
No shell, automatic retry, model invocation, production state write or daemon.
"""
import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import threading
import time

from .artifacts import canonical_json, sha256, _safe_name
from .coordinator_writer import write_new, fsync_dir
from .execution_lock import tracked_device_slot, verify_dependencies, validate_administrative_recovery
from . import hospital_runtime

GIB = 1024**3
PRE_STOP = 5 * GIB
BUNDLE_MODULES = ('wave1_supervisor','execution_lock','coordinator_writer','artifacts',
                  'hospital_runtime','hospital_contract','contracts','geometry')


def verify_loaded_bundle(root, expected_sha):
    manifest=verify_dependencies(root,expected_sha)
    if 'numpy' not in manifest['packages']:raise RuntimeError('SUPERVISOR_NUMPY_VERSION_NOT_LOCKED')
    expected={entry['name']:entry['sha256'] for entry in manifest['entries']}
    package=__package__;base=Path(__file__).resolve().parent;loaded={}
    for name in BUNDLE_MODULES:
        module=sys.modules[package+'.'+name]
        path=Path(module.__file__).resolve();digest=sha256(path.read_bytes())
        if path.parent!=base or expected.get(name+'.py')!=digest:
            raise RuntimeError('SUPERVISOR_LOADED_DEPENDENCY_NOT_LOCKED')
        loaded[name]={'path':str(path),'sha256':digest}
    return loaded


IO_CONTRACT_VERSION = 'EPI-NEXT-SUPERVISOR-IO-LOCK-4'


@contextmanager
def supervisor_output_lock(directory, *, timeout_seconds=.1):
    """Serialize atomic temporary-file lifetimes with output accounting.

    This is an IO lock, not queue admission. No ledger acquisition while held.
    A bounded wait failure propagates; it must never be treated as zero bytes.
    """
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not 0 < timeout_seconds < float('inf')):
        raise ValueError('POSITIVE_FINITE_IO_LOCK_TIMEOUT_REQUIRED')
    directory = Path(directory)
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError('OUTPUT_SYMLINK_REFUSED')
    descriptor = os.open(directory / 'supervisor-output.lock',
                         os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a+b') as stream:
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('SUPERVISOR_OUTPUT_LOCK_TIMEOUT')
                time.sleep(.001)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def supervisor_output_size(directory, *, timeout_seconds=.1):
    """Snapshot supervisor bytes under the same lock as atomic_json.

    Charge every file, including any retained temporary file. Refuse symlinks,
    missing entries and walk errors instead of weakening output budget checks.
    Append-only logs can still grow after this observation; this is no hard cap.
    """
    def walk_error(error):
        raise error
    total = 0
    with supervisor_output_lock(directory, timeout_seconds=timeout_seconds):
        for folder, dirs, files in os.walk(directory, followlinks=False, onerror=walk_error):
            for name in (*dirs, *files):
                entry = (Path(folder) / name).lstat()
                if stat.S_ISLNK(entry.st_mode):
                    raise ValueError('OUTPUT_SYMLINK_REFUSED')
                if name in files:
                    total += entry.st_size
    return total


def atomic_json(path, value):
    path = Path(path)
    with supervisor_output_lock(path.parent):
        temporary = path.with_name(path.name + f'.{os.getpid()}.{threading.get_ident()}.tmp')
        with temporary.open('xb') as stream:
            stream.write(canonical_json(value)); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path); fsync_dir(path.parent)


@dataclass(frozen=True)
class SupervisionSpec:
    job_id: str
    task_key: str
    device: str
    owner: str
    max_forward: int
    max_backward: int
    timeout_seconds: float
    per_case_seconds: float | None = None
    telemetry_startup_seconds: float | None = None
    telemetry_max_gap_seconds: float = .25
    request_grace_seconds: float = .25
    term_grace_seconds: float = .75
    recovery_seconds: float = 2.

    def __post_init__(self):
        _safe_name(self.job_id); _safe_name(self.task_key)
        if self.telemetry_startup_seconds is None:
            object.__setattr__(self,'telemetry_startup_seconds',2. if self.owner=='DATA' else 15.)
        if self.device not in {'cpu','mps'} or self.owner not in {'DATA','LOCALIZATION','ENCODER','INTEGRATION'}:
            raise ValueError('INVALID_DEVICE_OR_OWNER')
        if type(self.max_forward) is not int or type(self.max_backward) is not int or min(self.max_forward,self.max_backward)<0:
            raise ValueError('NONNEGATIVE_INTEGER_COUNTER_LIMITS_REQUIRED')
        for key in ('timeout_seconds','telemetry_startup_seconds','telemetry_max_gap_seconds',
                    'request_grace_seconds','term_grace_seconds','recovery_seconds'):
            value=getattr(self,key)
            if not isinstance(value,(int,float)) or not 0<value<float('inf'):raise ValueError('FINITE_POSITIVE_TIME_REQUIRED')
        if self.per_case_seconds is not None and not 0<self.per_case_seconds<=self.timeout_seconds:
            raise ValueError('INVALID_CASE_DEADLINE')


class StopWork(RuntimeError):
    pass


class ChildGuard:
    """Create before model loading; actual-child MPS callback belongs to ENCODER.

    Counter allocation is durable and global before each attempt. New guards or
    owned subprocesses share the same ledger; no seed/reset at child startup.
    """
    def __init__(self, directory, spec, started, *, mps_driver=None):
        self.directory=Path(directory);self.spec=spec;self.started=started
        self.mps_driver=mps_driver;self.stop=threading.Event();self.done=threading.Event()
        self.case=None;self.case_started=None;self.device_recovered=False
        self.last_heartbeat=None
        self._previous_handlers={}
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGUSR1,signal.SIGTERM):
                self._previous_handlers[sig]=signal.getsignal(sig)
                signal.signal(sig,lambda *_:self.stop.set())
        self.thread=threading.Thread(target=self._heartbeat_loop,daemon=True)
        self.thread.start()
        while not (self.directory/'ADMITTED').exists():
            self.check();time.sleep(.005)

    @classmethod
    def from_environment(cls, *, mps_driver=None):
        directory=Path(os.environ['EPI_NEXT_SUPERVISOR_DIR'])
        verify_loaded_bundle(os.environ['EPI_NEXT_DEPENDENCY_ROOT'],os.environ['EPI_NEXT_DEPENDENCY_SHA'])
        spec=SupervisionSpec(**json.loads((directory/'spec.json').read_bytes()))
        return cls(directory,spec,float(os.environ['EPI_NEXT_JOB_STARTED_MONOTONIC']),mps_driver=mps_driver)

    @contextmanager
    def ledger(self):
        with (self.directory/'counter.lock').open('a+b') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX)
            value=json.loads((self.directory/'counters.json').read_bytes())
            if value['job_id']!=self.spec.job_id:raise StopWork('COUNTER_JOB_MISMATCH')
            try:yield value
            finally:fcntl.flock(stream,fcntl.LOCK_UN)

    def check(self):
        now=time.monotonic()
        if (self.directory/'runner-complete.json').exists():raise StopWork('JOB_ALREADY_COMPLETED_NO_NEW_WORK')
        if self.stop.is_set() or (self.directory/'STOP').exists():raise StopWork('STOP_REQUESTED')
        if now-self.started>=self.spec.timeout_seconds:raise StopWork('GLOBAL_DEADLINE')
        if self.case_started is not None and self.spec.per_case_seconds is not None and now-self.case_started>=self.spec.per_case_seconds:
            raise StopWork('CASE_DEADLINE')

    def _before(self, kind):
        with self.ledger() as ledger:
            self.check()
            cap=self.spec.max_forward if kind=='forward' else self.spec.max_backward
            if ledger[kind]>=cap:raise StopWork('CALL_BUDGET_EXHAUSTED')
            ledger[kind]+=1;ledger['sequence']+=1
            atomic_json(self.directory/'counters.json',ledger)
        self.check()  # stop arriving during fsync fences the pending attempt too

    def before_forward(self):self._before('forward')
    def before_backward(self):self._before('backward')

    def begin_case(self, key):
        self.check()
        if self.case is not None:raise StopWork('CASE_ALREADY_ACTIVE')
        # Case deadline persisted across new guards/restarts; key cannot reset it.
        with self.ledger() as ledger:
            if key in ledger['cases']:raise StopWork('CASE_ALREADY_STARTED_NO_RETRY')
            self.case=key;self.case_started=time.monotonic()
            ledger['cases'][key]=self.case_started
            atomic_json(self.directory/'counters.json',ledger)

    def end_case(self):self.case=None;self.case_started=None

    def heartbeat(self):
        with self.ledger() as ledger:counts=dict(ledger)
        measurement=self.mps_driver() if self.mps_driver is not None else None
        driver=measurement.get('driver_bytes') if isinstance(measurement,dict) else measurement
        tensor=measurement.get('tensor_bytes') if isinstance(measurement,dict) else None
        if driver is not None and (type(driver) is not int or driver<0):raise StopWork('INVALID_MPS_MEASUREMENT')
        if tensor is not None and (type(tensor) is not int or tensor<0):raise StopWork('INVALID_MPS_TENSOR_MEASUREMENT')
        value={'job_id':self.spec.job_id,'pid':os.getpid(),'monotonic':time.monotonic(),
               'forward':counts['forward'],'backward':counts['backward'],'sequence':counts['sequence'],
               'case':self.case,'case_started':self.case_started,'mps_driver_bytes':driver,
               'mps_tensor_bytes':tensor,
               'device_recovered':self.device_recovered,'stop_seen':self.stop.is_set() or (self.directory/'STOP').exists()}
        value['actual_interval_seconds']=None if self.last_heartbeat is None else value['monotonic']-self.last_heartbeat
        self.last_heartbeat=value['monotonic']
        with (self.directory/'child-samples.jsonl').open('ab') as stream:
            stream.write(json.dumps(value,sort_keys=True,allow_nan=False).encode()+b'\n');stream.flush()
        atomic_json(self.directory/'telemetry.json',value)

    def _heartbeat_loop(self):
        while not self.done.is_set():
            try:self.heartbeat()
            except BaseException as exc:
                self.stop.set()
                atomic_json(self.directory/'telemetry-error.json',{'error_type':type(exc).__name__,'monotonic':time.monotonic()})
                return
            self.done.wait(.02)

    def close(self, *, device_recovered=False):
        self.done.set();self.thread.join(timeout=1.)
        if self.thread.is_alive():raise StopWork('TELEMETRY_THREAD_NOT_STOPPED')
        self.device_recovered=device_recovered;self.heartbeat()
        for sig,handler in self._previous_handlers.items():signal.signal(sig,handler)

    def complete(self, status='SUCCESS', *, reason=None, device_recovered=False,
                 actual_forward=None, actual_backward=None):
        if status not in {'SUCCESS','NO_RELIABLE_RESPONSE','PARTIAL_BUDGET','FAILED','BLOCKED','NOT RUN'}:
            raise ValueError('INVALID_CHILD_TERMINAL_STATUS')
        self.close(device_recovered=device_recovered)
        with self.ledger() as ledger:
            for actual,kind in ((actual_forward,'forward'),(actual_backward,'backward')):
                if actual is not None and (type(actual) is not int or not 0<=actual<=ledger[kind]):
                    raise ValueError('ACTUAL_COUNT_MUST_NOT_EXCEED_RESERVED_ATTEMPTS')
        write_new(self.directory/'runner-complete.json',canonical_json({
            'job_id':self.spec.job_id,'status':status,'reason':reason,'monotonic':time.monotonic(),
            'actual_forward':actual_forward,'actual_backward':actual_backward}))


class SystemMonitor:
    def processes(self):
        output=subprocess.check_output(['ps','-axo','pid=,ppid=,pgid=,rss=,stat=,lstart='],text=True,timeout=.5)
        table={}
        for line in output.splitlines():
            fields=line.split(None,5)
            if len(fields)!=6:raise RuntimeError('PS_PARSE_FAILURE')
            pid,ppid,pgid,rss=map(int,fields[:4])
            table[pid]={'pid':pid,'ppid':ppid,'pgid':pgid,'rss_bytes':rss*1024,'state':fields[4],'start':fields[5]}
        return table

    def pressure(self):
        if sys.platform=='darwin':
            raw=subprocess.check_output(['memory_pressure','-Q'],text=True,timeout=.5)
            fraction=float(re.search(r'System-wide memory free percentage:\s*([\d.]+)%',raw).group(1))/100
            total=int(subprocess.check_output(['sysctl','-n','hw.memsize'],text=True,timeout=.5))
            free=int(fraction*total)
            swap=subprocess.check_output(['sysctl','-n','vm.swapusage'],text=True,timeout=.5)
            value,unit=re.search(r'used\s*=\s*([\d.]+)([KMGT])',swap).groups()
            used=int(float(value)*1024**('KMGT'.index(unit)+1))
        else:
            values={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()}
            total=values['MemTotal'];free=values['MemFree'];used=values['SwapTotal']-values['SwapFree']
        if total<=0 or not 0<=free<=total or used<0:raise RuntimeError('INVALID_SYSTEM_MEMORY_SAMPLE')
        return {'free_bytes':free,'total_bytes':total,'free_fraction':free/total,'swap_used_bytes':used,
                'free_metric_source':'memory_pressure -Q System-wide memory free percentage' if sys.platform=='darwin' else '/proc/meminfo MemFree',
                'free_metric_raw':raw if sys.platform=='darwin' else None}


def owned_group(table, process, identity):
    exited=process.poll() is not None
    members=[v for v in table.values() if v['pgid']==process.pid and not v.get('state','').startswith('Z') and not (exited and v['pid']==process.pid)]
    root=table.get(process.pid)
    if root is not None and (root['start']!=identity['start'] or root['pgid']!=process.pid):
        raise RuntimeError('OWN_PROCESS_IDENTITY_CHANGED')
    for member in members:
        try:
            if os.getsid(member['pid'])!=process.pid:raise RuntimeError('FOREIGN_SESSION_MEMBER')
        except ProcessLookupError:
            continue  # disappeared during sampling; never signal stale individual PID
    return members


def validated_completion(directory, spec, telemetry, child_pid, started, now):
    """Only the owned child's same-job terminal marker ends heartbeat duty.

    Completion does not confirm process exit, recovery or extend the deadline.
    Invalid/unbound markers leave active-heartbeat safeguards in force.
    """
    path=directory/'runner-complete.json'
    if not path.exists() or path.is_symlink() or telemetry is None:return None
    try:
        marker=json.loads(path.read_bytes())
        if (marker['job_id']!=spec.job_id or telemetry['job_id']!=spec.job_id
                or telemetry['pid']!=child_pid
                or marker['status'] not in {'SUCCESS','NO_RELIABLE_RESPONSE','PARTIAL_BUDGET','FAILED','BLOCKED','NOT RUN'}
                or not started<=telemetry['monotonic']<=marker['monotonic']<=now):return None
        for kind,limit in (('forward',spec.max_forward),('backward',spec.max_backward)):
            actual=marker['actual_'+kind]
            if actual is not None and (type(actual) is not int or not 0<=actual<=telemetry[kind]<=limit):return None
        return marker
    except (OSError,ValueError,TypeError,KeyError):
        return None


def run_supervised(spec, command, output_root, dependency_root, dependency_sha, *, _monitor=None, recovery_decision_path=None, recovery_decision_sha=None):
    queue=hospital_runtime.QUEUE_ROOT;queue.mkdir(parents=True,exist_ok=True)
    descriptor=os.open(queue/'wave1.serial.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'a+b') as stream:
        try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise RuntimeError('WAVE1_SERIAL_SLOT_BUSY') from exc
        try:
            recovery=validate_administrative_recovery(queue,spec.task_key,recovery_decision_path,recovery_decision_sha)
            slots=queue/'slots'
            if slots.exists():
                for slot in slots.iterdir():
                    if (slot.is_symlink() or not slot.is_dir()
                            or (not (slot/'finished.json').exists()
                                and (recovery is None or slot.name != recovery['old_job_id']))):
                        raise RuntimeError('WAVE1_GLOBAL_UNKNOWN_SLOT_RECONCILE_REQUIRED')
                    if json.loads((slot/'started.json').read_bytes())['task_key']==spec.task_key:
                        raise RuntimeError('WAVE1_DUPLICATE_TASK_SCOPE_NO_COUNTER_RESET')
            return _run_supervised(spec,command,output_root,dependency_root,dependency_sha,_monitor=_monitor,
                                   recovery_decision_path=recovery_decision_path,recovery_decision_sha=recovery_decision_sha)
        finally:fcntl.flock(stream,fcntl.LOCK_UN)


def _run_supervised(spec, command, output_root, dependency_root, dependency_sha, *, _monitor=None, recovery_decision_path=None, recovery_decision_sha=None):
    """One job wraps the whole experiment; no subprocess restart/next-job reset.

    Scientific/data approval and command binding remain the chief's responsibility.
    Failure leaves outputs and unknown slot intact; no cleanup/deletion.
    """
    if not command or not all(isinstance(x,str) for x in command):raise ValueError('ARGV_REQUIRED_NO_SHELL')
    monitor=_monitor or SystemMonitor();directory=Path(output_root)/_safe_name(spec.job_id)
    loaded=verify_loaded_bundle(dependency_root,dependency_sha)
    budget={'max_model_calls':spec.max_forward,'max_seconds':spec.timeout_seconds,
            'max_rss_bytes':6*GIB,'max_mps_driver_bytes':6*GIB,'max_backward':spec.max_backward}
    with tracked_device_slot(spec.device,owner=spec.owner,job_id=spec.job_id,task_key=spec.task_key,
                             budget=budget,dependency_root=dependency_root,dependency_sha=dependency_sha,recovery_decision_path=recovery_decision_path,
                             recovery_decision_sha=recovery_decision_sha) as slot:
        directory.mkdir(parents=True,exist_ok=False,mode=0o700)
        write_new(directory/'spec.json',canonical_json(asdict(spec)))
        write_new(directory/'counters.json',canonical_json({'job_id':spec.job_id,'forward':0,'backward':0,'sequence':0,'cases':{}}))
        write_new(directory/'command.json',canonical_json({'argv':command,'dependency_sha256':dependency_sha}))
        started=time.monotonic();events=[];samples=[];missing=[];intervals=[]
        initial=None;process=None;identity=None;reason=None;trigger=None;exit_at=None;recovered_at=None
        last_telemetry=None;last_counts=(0,0,0);last_sample=started;requested=False;terminated=False;killed=False
        accepted_completion=None
        completion_counts=None
        def event(kind, **values):events.append(dict(kind=kind,monotonic=time.monotonic(),**values))
        def request(why):
            nonlocal reason,trigger,requested
            if requested:return
            reason=why;trigger=time.monotonic();requested=True
            event('TRIGGER',reason=why)
            if not (directory/'STOP').exists():
                write_new(directory/'STOP',canonical_json({'reason':why,'monotonic':trigger}))
            event('STOP_REQUEST_FILE')
            if process is not None and identity is not None:
                try:
                    if owned_group(monitor.processes(),process,identity):
                        os.killpg(process.pid,signal.SIGUSR1);event('STOP_REQUEST_SIGNAL')
                except BaseException as exc:
                    event('STOP_SIGNAL_NOT_SENT',error_type=type(exc).__name__)
        with (directory/'stdout.log').open('xb') as stdout,(directory/'stderr.log').open('xb') as stderr:
            try:
                initial=monitor.pressure()
                if initial['free_fraction']<.2:raise RuntimeError('SYSTEM_FREE_PRESTOP')
                env=dict(os.environ,EPI_NEXT_SUPERVISOR_DIR=str(directory.absolute()),
                         EPI_NEXT_JOB_STARTED_MONOTONIC=str(started),
                         EPI_NEXT_DEPENDENCY_ROOT=str(Path(dependency_root).absolute()),
                         EPI_NEXT_DEPENDENCY_SHA=dependency_sha)
                process=subprocess.Popen(command,stdout=stdout,stderr=stderr,env=env,start_new_session=True)
                table=monitor.processes();identity=table[process.pid]
                if identity['ppid']!=os.getpid() or os.getsid(process.pid)!=process.pid:
                    raise RuntimeError('OWN_PROCESS_CREATION_NOT_VERIFIED')
                slot.track_child(process);event('CHILD_STARTED',identity=identity)
                write_new(directory/'ADMITTED',canonical_json({'pid':process.pid,'start':identity['start']}))
                while True:
                    now=time.monotonic();intervals.append(now-last_sample);last_sample=now
                    table=monitor.processes();members=owned_group(table,process,identity)
                    pressure=monitor.pressure();rss=sum(m['rss_bytes'] for m in members)
                    sample=dict(pressure,monotonic=now,rss_bytes=rss,rss_by_pid=members);samples.append(sample)
                    if now-started>=spec.timeout_seconds:request('GLOBAL_DEADLINE')
                    if rss>=PRE_STOP:request('RSS_PRESTOP')
                    if pressure['free_fraction']<.2:request('SYSTEM_FREE_PRESTOP')
                    if pressure['swap_used_bytes']-initial['swap_used_bytes']>GIB:request('SWAP_GROWTH_PRESTOP')
                    if (directory/'telemetry-error.json').exists():request('CHILD_TELEMETRY_FAILURE')
                    path=directory/'telemetry.json'
                    if path.exists():
                        telemetry=json.loads(path.read_bytes())
                        if telemetry['job_id']!=spec.job_id or telemetry['pid'] not in {m['pid'] for m in members}:
                            if process.poll() is None:request('TELEMETRY_OWNERSHIP_MISMATCH')
                        counts=(telemetry['forward'],telemetry['backward'],telemetry['sequence'])
                        if any(type(v) is not int or v<old for v,old in zip(counts,last_counts)):request('COUNTER_REGRESSION')
                        if counts[0]>spec.max_forward or counts[1]>spec.max_backward:request('CALL_LIMIT_EXCEEDED')
                        last_counts=counts
                        if last_telemetry is None or telemetry['monotonic']!=last_telemetry['monotonic']:
                            if last_telemetry is not None:sample['child_telemetry_interval_seconds']=telemetry['monotonic']-last_telemetry['monotonic']
                            last_telemetry=telemetry
                        sample['mps_driver_bytes']=telemetry['mps_driver_bytes']
                        sample['mps_tensor_bytes']=telemetry['mps_tensor_bytes']
                        if spec.device=='mps' and telemetry['mps_driver_bytes'] is None:
                            missing.append({'monotonic':now,'kind':'MPS_DRIVER'})
                            if now-started>spec.telemetry_startup_seconds:request('MPS_DRIVER_MISSING')
                        elif spec.device=='mps' and telemetry['mps_driver_bytes']>=PRE_STOP:request('MPS_DRIVER_PRESTOP')
                        if telemetry['case_started'] is not None and spec.per_case_seconds is not None and now-telemetry['case_started']>=spec.per_case_seconds:
                            request('CASE_DEADLINE')
                        completion=validated_completion(directory,spec,telemetry,process.pid,started,time.monotonic())
                        if completion is not None and accepted_completion is None:
                            accepted_completion=completion;completion_counts=counts
                            event('VALID_CHILD_COMPLETION_EXIT_WAIT')
                        if accepted_completion is not None and completion!=accepted_completion:
                            request('CHILD_COMPLETION_CHANGED')
                        if accepted_completion is not None:
                            ledger=json.loads((directory/'counters.json').read_bytes())
                            durable_counts=(ledger['forward'],ledger['backward'],ledger['sequence'])
                            if ledger['job_id']!=spec.job_id or counts!=completion_counts or durable_counts!=completion_counts:
                                request('CHILD_COUNTER_CHANGED_AFTER_COMPLETION')
                        if accepted_completion is None and now-telemetry['monotonic']>spec.telemetry_max_gap_seconds:
                            request('STALE_CHILD_TELEMETRY')
                    else:
                        missing.append({'monotonic':now,'kind':'TELEMETRY'})
                        if accepted_completion is None and now-started>spec.telemetry_startup_seconds:request('CHILD_TELEMETRY_MISSING')
                    if requested and members:
                        if not terminated and time.monotonic()-trigger>=spec.request_grace_seconds:
                            # Re-read immediately before group signaling; unknown means no signal.
                            if owned_group(monitor.processes(),process,identity):
                                os.killpg(process.pid,signal.SIGTERM);event('TERM_REQUEST')
                            terminated=True
                        if not killed and time.monotonic()-trigger>=spec.request_grace_seconds+spec.term_grace_seconds:
                            if owned_group(monitor.processes(),process,identity):
                                os.killpg(process.pid,signal.SIGKILL);event('KILL_REQUEST')
                            killed=True
                    if process.poll() is not None and not members:
                        exit_at=time.monotonic();event('OWN_GROUP_EXITED',returncode=process.returncode)
                        break
                    if killed and time.monotonic()-trigger>spec.request_grace_seconds+spec.term_grace_seconds+spec.recovery_seconds:
                        raise RuntimeError('OWN_GROUP_EXIT_UNKNOWN')
                    time.sleep(.05)
            except BaseException as exc:
                request('MONITOR_FAILURE_'+type(exc).__name__)
                event('MONITOR_EXCEPTION',error_type=type(exc).__name__)
                # Independent fallback identity probe; never signal if probe fails.
                if process is not None and identity is not None:
                    try:
                        for sig,delay in ((signal.SIGTERM,spec.term_grace_seconds),(signal.SIGKILL,.1)):
                            if owned_group(SystemMonitor().processes(),process,identity):
                                os.killpg(process.pid,sig);event('FAIL_CLOSED_SIGNAL',signal=int(sig));time.sleep(delay)
                        if process.poll() is not None and not owned_group(SystemMonitor().processes(),process,identity):
                            exit_at=time.monotonic();event('OWN_GROUP_EXITED',returncode=process.returncode)
                    except BaseException as probe:
                        event('IDENTITY_OR_EXIT_UNKNOWN',error_type=type(probe).__name__)
            stdout.flush();os.fsync(stdout.fileno());stderr.flush();os.fsync(stderr.fileno())
        if exit_at is not None:
            until=time.monotonic()+spec.recovery_seconds
            while time.monotonic()<until:
                try:
                    pressure=monitor.pressure()
                    mps_ok=spec.device=='cpu' or (last_telemetry is not None and last_telemetry['device_recovered'] and type(last_telemetry['mps_driver_bytes']) is int and 0<=last_telemetry['mps_driver_bytes']<PRE_STOP and type(last_telemetry['mps_tensor_bytes']) is int and 0<=last_telemetry['mps_tensor_bytes']<PRE_STOP)
                    if pressure['free_fraction']>=.2 and initial is not None and pressure['swap_used_bytes']-initial['swap_used_bytes']<=GIB and mps_ok:
                        recovered_at=time.monotonic();event('DEVICE_RECOVERED');break
                except BaseException as exc:event('RECOVERY_MONITOR_FAILURE',error_type=type(exc).__name__);break
                time.sleep(.05)
        counters=json.loads((directory/'counters.json').read_bytes())
        complete=accepted_completion
        if reason is None and (process is None or process.returncode!=0 or complete is None):reason='RUNNER_FAILURE_OR_MISSING_COMPLETION'
        status=('BLOCKED' if exit_at is None or recovered_at is None else
                complete['status'] if reason is None else
                'PARTIAL_BUDGET' if reason in {'GLOBAL_DEADLINE','CASE_DEADLINE','RSS_PRESTOP','MPS_DRIVER_PRESTOP','SYSTEM_FREE_PRESTOP','SWAP_GROWTH_PRESTOP','CALL_LIMIT_EXCEEDED'} else 'FAILED')
        assets={}
        for path in directory.rglob('*'):
            if path.is_file() and not path.is_symlink():
                with path.open('rb') as stream:assets[str(path.relative_to(directory))]=hashlib.file_digest(stream,'sha256').hexdigest()
        receipt={'schema':'EPI-NEXT-WAVE1-SUPERVISION-1','job_id':spec.job_id,'task_key':spec.task_key,
                 'status':status,'reason':reason,'started_monotonic':started,'trigger_monotonic':trigger,
                 'exit_monotonic':exit_at,'recovered_monotonic':recovered_at,'events':events,
                 'sampling_target_seconds':.05,'child_target_seconds':.02,'actual_parent_intervals_seconds':intervals,
                 'missing_samples':missing,'samples':samples,'counters':counters,'sampled_peak_not_absolute':True,
                 'counter_semantics':'DURABLE_RESERVED_ATTEMPTS; stop after reservation may prevent actual model entry',
                 'runner_actual_counts':None if complete is None else {'forward':complete.get('actual_forward'),'backward':complete.get('actual_backward')},
                 'rss_semantics':'SUM_OF_OWN_GROUP_PROCESS_RSS; shared resident pages may be counted more than once',
                 'rss_and_mps_not_added':True,'slot_completed':exit_at is not None and recovered_at is not None,
                 'asset_hashes':assets,'dependency_sha256':dependency_sha}
        receipt['actual_loaded_supervisor_modules']=loaded
        receipt['io_contract_version']=IO_CONTRACT_VERSION
        write_new(directory/'supervisor-receipt.json',canonical_json(receipt))
        if receipt['slot_completed']:
            slot.complete(directory/'supervisor-receipt.json',sha256((directory/'supervisor-receipt.json').read_bytes()))
        return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec',type=Path,required=True);parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--dependency-root',type=Path,required=True);parser.add_argument('--dependency-sha',required=True)
    parser.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args();command=args.command[1:] if args.command[:1]==['--'] else args.command
    receipt=run_supervised(SupervisionSpec(**json.loads(args.spec.read_bytes())),command,args.output_root,args.dependency_root,args.dependency_sha)
    print(json.dumps({'job_id':receipt['job_id'],'status':receipt['status'],'reason':receipt['reason'],'slot_completed':receipt['slot_completed']}))
    return 0 if receipt['status'] in {'SUCCESS','NO_RELIABLE_RESPONSE'} else 2


if __name__=='__main__':sys.exit(main())
