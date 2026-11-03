"""Bounded thin two-lock CLI lease; reuse V5's existing phase supervision."""

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[3]
import argparse,fcntl,hashlib,json,os,re,selectors,signal,subprocess,sys,time
from pathlib import Path
from . import ri_hu_v5_precision as core
old=core.old
CAPTURE_LIMIT=32*1024


def process_identity(pid):
    p=subprocess.run(['ps','-p',str(pid),'-o','ppid=,pgid=,lstart='],capture_output=True,text=True,timeout=2)
    if p.returncode or not p.stdout.strip():return None
    parent,group,birth=p.stdout.strip().split(maxsplit=2)
    return {'pid':pid,'ppid':int(parent),'pgid':int(group),'process_start':birth.strip()}


def phase_state(output,cli_pid,cli_exited=False):
    path=Path(output)/'stage-checkpoint-v5.json'
    if not path.exists():return {'status':'UNKNOWN_NO_PHASE_CHECKPOINT','identity':None}
    data=core.bound_json(path,old.sha(path));identity=data['worker_identity']
    if identity['ppid']!=cli_pid or identity['pgid']!=identity['pid']:return {'status':'UNKNOWN_IDENTITY_CONFLICT','identity':None}
    current=process_identity(identity['pid'])
    if current is None or current['process_start']!=identity['process_start']:return {'status':'VERIFIED_ORIGINAL_WORKER_GONE','identity':identity}
    if current!=identity:
        if cli_exited and current==dict(identity,ppid=1):
            return {'status':'VERIFIED_OWN_WORKER_ALIVE','identity':current,'recorded_identity':identity,'reparented_to_init':True}
        return {'status':'UNKNOWN_IDENTITY_CONFLICT','identity':None}
    return {'status':'VERIFIED_OWN_WORKER_ALIVE','identity':identity}


def stop_owned_phase(state):
    identity=state.get('identity')
    if state['status']!='VERIFIED_OWN_WORKER_ALIVE' or process_identity(identity['pid'])!=identity:return False
    try:
        os.killpg(identity['pgid'],signal.SIGTERM);time.sleep(.2)
        if process_identity(identity['pid'])==identity:os.killpg(identity['pgid'],signal.SIGKILL)
    except ProcessLookupError:pass
    return True


def bounded_child(argv,cwd,env,output,update,total_seconds=90):
    child=subprocess.Popen(argv,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    selector=selectors.DefaultSelector();captures={'stdout':bytearray(),'stderr':bytearray()};start=time.monotonic();term_sent=False;cap_stop=False
    def phase():
        try:return phase_state(output,child.pid,child.poll() is not None)
        except Exception:return {'status':'UNKNOWN_CHECKPOINT_UNREADABLE','identity':None}
    def signal_cli(sig):
        if child.poll() is None:
            try:os.killpg(child.pid,sig)
            except ProcessLookupError:pass
    try:
        update({'child_pid':child.pid,'child_identity':process_identity(child.pid),'dispatch_monotonic':start,'attempts':1})
        for name,pipe in [('stdout',child.stdout),('stderr',child.stderr)]:
            os.set_blocking(pipe.fileno(),False);selector.register(pipe,selectors.EVENT_READ,name)
        while selector.get_map() or child.poll() is None:
            elapsed=time.monotonic()-start
            if elapsed>=max(0,total_seconds-min(12,total_seconds/2)) and child.poll() is None and not term_sent:
                signal_cli(signal.SIGTERM);term_sent=True
                update({'cooperative_cli_TERM':True,'phase_at_TERM':phase()})
            if elapsed>=total_seconds:
                state=phase();handled=stop_owned_phase(state);signal_cli(signal.SIGKILL)
                update({'hard_escalation_phase_state':state,'exact_owned_phase_signalled':handled,'pipes_closed_at_deadline':bool(selector.get_map())})
                break
            for key,_ in selector.select(min(.1,max(.001,total_seconds-elapsed))):
                chunk=os.read(key.fileobj.fileno(),4096)
                if not chunk:selector.unregister(key.fileobj);continue
                if cap_stop:continue
                remaining=CAPTURE_LIMIT-sum(len(x) for x in captures.values())
                captures[key.data].extend(chunk[:remaining])
                if len(chunk)>remaining:
                    cap_stop=True;signal_cli(signal.SIGTERM);term_sent=True
                    update({'capture_limit_stop':True})
        exit_code=child.wait(timeout=2)
        return {'exit_code':exit_code,'elapsed_seconds':time.monotonic()-start,'child_exited':True,'phase_final_state':phase(),
                'stdout':captures['stdout'].decode('utf-8','replace'),'stderr':captures['stderr'].decode('utf-8','replace'),
                'stdout_bytes':len(captures['stdout']),'stderr_bytes':len(captures['stderr']),'bounded_capture_limit':CAPTURE_LIMIT,'capture_limit_stop':cap_stop}
    finally:
        # Also runs if receipt writing or pipe reads fail. Never signal an unverified phase.
        primary_active=sys.exc_info()[0] is not None
        cleanup_error=None
        try:
            signal_cli(signal.SIGTERM)
            try:child.wait(timeout=min(2,max(.1,total_seconds-(time.monotonic()-start))))
            except subprocess.TimeoutExpired:pass
            stop_owned_phase(phase())
        except Exception as exc:cleanup_error=exc
        finally:
            try:signal_cli(signal.SIGKILL);child.wait(timeout=2)
            except Exception as exc:cleanup_error=cleanup_error or exc
            selector.close();child.stdout.close();child.stderr.close()
        if cleanup_error is not None:
            try:update({'reporting_error':core.v4.exception_record(cleanup_error,'LEASE_CLEANUP'),'no_followup_dispatch':True})
            except Exception:pass
            if not primary_active:raise cleanup_error


def run_lease(r,request_path,request_sha,approval_path,approval_sha):
    root=Path(r['command_templates']['cwd']);queue=Path(str(_PUBLIC_ROOT / '.local/private-bindings/epi-next-device-queue'))
    output=Path(r['output_root']);lease=Path(str(output)+'-lease');lease.mkdir(mode=0o700,exist_ok=False)
    delivery=lease/'execution-delivery-v5.json';used=0;record={'status':'CLAIMED_NOT_RUN','attempts':0,'request_sha256':request_sha,'approval_sha256':approval_sha}
    def update(fields):
        nonlocal used
        record.update(fields);content=old.encoded(record)
        retained=sum(p.stat().st_size for p in lease.iterdir() if p.is_file())
        capture=record.get('stdout_bytes',0)+record.get('stderr_bytes',0)
        if max(used+len(content),retained+len(content))+capture>core.OUTER_RESERVE:raise RuntimeError('OUTER_OUTPUT_RESERVE_LIMIT')
        used+=len(content);part=delivery.with_suffix('.json.part')
        with part.open('xb') as f:f.write(content);f.flush();os.fsync(f.fileno())
        part.chmod(0o600);os.replace(part,delivery)
    update({});locks=[];start=time.monotonic()
    try:
        assert not output.exists()
        for name in ('wave1.serial.lock','cpu.lock'):
            fd=os.open(queue/name,os.O_RDWR|os.O_NOFOLLOW)
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BaseException:os.close(fd);raise
            locks.append((name,fd))
        procs=subprocess.check_output(['ps','-Ao','pid=,command='],text=True)
        same=[line for line in procs.splitlines() if int(line.strip().split()[0])!=os.getpid() and re.match(r'^\s*\d+\s+\S*python\S*\s+-m\s+epi_next\.ri_hu_v5_(precision|leased)(?:\s|$)',line)]
        if same:raise RuntimeError('DUPLICATE_EXACT_V5_ENTRY')
        coord=Path(str(_PUBLIC_ROOT / '.local/private-bindings/manifests/epi-next-phase2-coordinator'))
        recovery={'ADMINISTRATIVE_RECOVERY_DECISION_20261010_V1.json':'0000000000000000000000000000000000000000000000000000000000000000','next-sprint-20261011/ADMINISTRATIVE_RECOVERY_NEW_C1_V1.json':'0000000000000000000000000000000000000000000000000000000000000000'}
        for name,digest in recovery.items():assert core.bound_json(coord/name,digest)['status']=='APPROVED_ADMINISTRATIVE_RECOVERY'
        unfinished=[slot.name for slot in (queue/'slots').iterdir() if slot.is_dir() and (slot/'started.json').exists() and not (slot/'finished.json').exists()]
        if set(unfinished)!={'ctfm-fov128-wave1-20261009-01','ctfm-v3-fullseries64-pair-01'}:raise RuntimeError('NEW_UNRECOVERED_SLOT')
        assert not output.exists()
        argv=[sys.executable,'-m','epi_next.ri_hu_v5_precision','--request',str(request_path),'--request-sha256',request_sha,'--execute','--approval',str(approval_path),'--approval-sha256',approval_sha]
        env=dict(os.environ,**r['command_templates']['environment'])
        update({'status':'DISPATCHING','argv':argv,'environment':r['command_templates']['environment'],'historical_unfinished_preserved':unfinished})
        result=bounded_child(argv,root,env,output,update,max(1,90-(time.monotonic()-start)))
        known=result['phase_final_state']['status']=='VERIFIED_ORIGINAL_WORKER_GONE' and not result['capture_limit_stop']
        update(dict(result,status='EXITED_CONFIRMED' if known else 'BLOCKED_PHASE_EXIT_UNKNOWN',no_followup_dispatch=True))
    except Exception as exc:
        try:update({'status':'NOT_RUN' if not record['attempts'] else 'STOPPED_OR_BLOCKED','error':core.v4.exception_record(exc,'LEASE'),'no_followup_dispatch':True})
        except Exception as reporting:record['reporting_error']=core.v4.exception_record(reporting,'LEASE_RECEIPT')
    finally:
        released=[]
        for name,fd in reversed(locks):fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd);released.append(name)
        try:update({'released_locks':released,'lock_release_is_not_phase_exit_proof':True,'total_elapsed_seconds':time.monotonic()-start,'outer_cumulative_bytes_before_final':used})
        except Exception as reporting:
            record['status']='STOPPED_OR_BLOCKED';record['reporting_error']=core.v4.exception_record(reporting,'LEASE_FINAL_RECEIPT')
    return record


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--request-sha256',required=True);p.add_argument('--execute',action='store_true');p.add_argument('--approval');p.add_argument('--approval-sha256');a=p.parse_args()
    r=core.bound_json(a.request,a.request_sha256)
    if r['lease_wrapper_binding']['path']!=str(Path(__file__).resolve()) or old.sha(__file__)!=r['lease_wrapper_binding']['sha256']:raise RuntimeError('LEASE_BINDING_DRIFT')
    # Reuse the existing core read-only admission/closure check, not tests.
    saved=sys.argv;sys.argv=[saved[0],'--request',a.request,'--request-sha256',a.request_sha256]
    try:core.main()
    finally:sys.argv=saved
    if not a.execute:return
    if not a.approval or not a.approval_sha256:raise RuntimeError('NEW_V5_APPROVAL_REQUIRED')
    grant=core.bound_json(a.approval,a.approval_sha256)
    expected={'schema':'RI_HU_PRECISION_APPROVAL_V5','request_sha256':a.request_sha256,'permit_parameter_probe':True,'permit_precision_discrepancy_diagnostic':True,'permit_raw_diagnostic_save':True,'permit_conditional_rescale':True,'permit_model':False,'permit_training':False,'permit_retry':False,'accept_source_supported_research_only':False}
    if any(type(grant.get(k)) is not type(v) or grant.get(k)!=v for k,v in expected.items()):raise RuntimeError('EXACT_NEW_V5_APPROVAL_REQUIRED')
    result=run_lease(r,a.request,a.request_sha256,a.approval,a.approval_sha256);print(json.dumps({'status':result['status']}))
    if result['status']!='EXITED_CONFIRMED' or result.get('exit_code')!=0:raise SystemExit(1)

if __name__=='__main__':
    try:main()
    except Exception as exc:print(json.dumps({'status':'LEASE_CONTROL_REJECTED','error':core.v4.exception_record(exc,'LEASE_CONTROL')}));raise SystemExit(1) from None
