"""Publish exact metadata readiness for chief dispatch; never execute a model.

Consumes DATA's ledger and owner's existing review. The queue sample reads
receipts and briefly checks only the two existing locks; creates no queue file,
slot, allowlist, derived image, GT, dispatch or supervisor completion marker.
"""
import argparse
from datetime import datetime,timezone
import fcntl
import json
import os
from pathlib import Path
import stat
import sys

from hospital_mvp_protected import ROOT,TASK,PIXEL_OWNER_DECISION_SHA,bound,sha,json_new,validate_readiness,real_command,MVPStopped


def queue_snapshot(queue,recovery,task_key):
    descriptors=[]
    try:
        for name in ['wave1.serial.lock','cpu.lock']:
            path=queue/name
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW);descriptors.append(fd)
            if not stat.S_ISREG(os.fstat(fd).st_mode):raise MVPStopped('QUEUE_LOCK_IDENTITY_UNSAFE')
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc:raise MVPStopped('EXISTING_SERIAL_OR_CPU_LOCK_BUSY') from exc
        rows=[]
        for directory in sorted((queue/'slots').iterdir()):
            if directory.is_symlink() or not directory.is_dir():raise MVPStopped('UNRECOGNIZED_QUEUE_SLOT')
            start=directory/'started.json';s=bound(dict(path=str(start),sha256=sha(start)))
            if s['task_key']==task_key:raise MVPStopped('DUPLICATE_MVP_TASK_ALREADY_SPENT')
            end=directory/'finished.json'
            row=dict(job_id=directory.name,task_key=s['task_key'],started_sha256=sha(start))
            if not end.exists():
                if directory.name not in recovery['old_job_ids']:raise MVPStopped('GLOBAL_UNKNOWN_SLOT_RECONCILE_REQUIRED')
                row['status']='OLD_UNKNOWN_PRESERVED_EXCUSED_BY_BOUND_OWNER_CHAIN'
            else:
                terminal=bound(dict(path=str(end),sha256=sha(end)))
                receipt=bound(dict(path=terminal['receipt_path'],sha256=terminal['receipt_sha256']))
                if (receipt.get('job_id')!=directory.name or terminal.get('job_id')!=directory.name
                        or receipt.get('status')!=terminal.get('status')
                        or receipt.get('slot_completed') is not True
                        or receipt.get('exit_monotonic') is None or receipt.get('recovered_monotonic') is None):
                    raise MVPStopped('FINISHED_SLOT_RECEIPT_NOT_RECOVERED')
                row.update(status=receipt['status'],finished_sha256=sha(end),receipt_sha256=terminal['receipt_sha256'])
            rows.append(row)
        return dict(schema='EPI_NEXT_MVP_READONLY_QUEUE_SAMPLE_V1',status='PASS_AT_SAMPLE_TIME',
                    sampled_at=datetime.now(timezone.utc).isoformat(),existing_locks=['wave1.serial.lock','cpu.lock'],
                    rows=rows,queue_files_created=0,queue_files_changed=0,device_initialized=False,
                    slot_reserved=False,actual_admission='Supervisor rechecks serial/device gates at chief dispatch')
    finally:
        for fd in reversed(descriptors):
            fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)


def finalize(binding_ref,data_ref,generated_ref,completion_ref,owner_ref,output,dispatch_path):
    ready=bound(binding_ref)
    if ready['schema']!='EPI_NEXT_MVP_PROTECTED_READINESS_V1' or ready['status']!='NOT READY':
        raise MVPStopped('FRESH_METADATA_BINDING_FRAGMENT_REQUIRED')
    ready.update(status='READY_FOR_CHIEF_DISPATCH',blockers=[],data_delivery=data_ref,
                 generated_protected_acceptance=generated_ref,generated_owned_completion=completion_ref,
                 pixel_owner_decision=owner_ref,metadata_binding_parent=binding_ref)
    modules,delivery=validate_readiness(ready)  # Only metadata/package/receipt reads.
    decision=bound(ready['decision']);queue=Path(decision['queue_root'])
    recovery=modules['execution_lock'].validate_administrative_recovery(queue,TASK,
                ready['decision']['path'],ready['decision']['sha256'])
    sample=queue_snapshot(queue,recovery,TASK)
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    json_new(output/'queue-sample.json',sample)
    ready['queue_sample']=dict(path=str(output/'queue-sample.json'),sha256=sha(output/'queue-sample.json'))
    ready['authorization_boundary']='Readiness is not dispatch or hospital display permission'
    json_new(output/'readiness.json',ready)
    rr=dict(path=str(output/'readiness.json'),sha256=sha(output/'readiness.json'))
    argv=real_command(rr,dict(path=str(dispatch_path),sha256='CHIEF_PUBLISHED_DISPATCH_SHA256'))
    command=dict(schema='EPI_NEXT_MVP_CHIEF_COMMAND_REQUEST_V1',status='WAIT_CHIEF_DISPATCH_SHA',
        task_key=TASK,job_id_proposal='hospital-mvp-three-legacy-cpu-20261011-01',cwd=str(ROOT),
        environment=dict(PYTHONDONTWRITEBYTECODE='1',PYTHONPATH='.:frontend/.local/mvp-20261011-browser-deps'),
        argv_without_dispatch_sha=argv[:-2],argv_tail_to_bind=['--dispatch-sha','CHIEF_PUBLISHED_DISPATCH_SHA256'],
        python=sys.executable,readiness=rr,data_delivery=data_ref,source_git_sha=ready['source_git_sha'],
        source_sha256=ready['source_sha256'],compute=ready['compute'],
        owner_approval_sha256=ready['owner']['sha256'],decision_sha256=ready['decision']['sha256'],
        supervisor_index_sha256=ready['supervisor_index']['sha256'],
        **{k:ready[k] for k in ['run_directory','supervision_root','dist','frozen_root']})
    json_new(output/'command-request.json',command)
    json_new(output/'finalization-receipt.json',dict(schema='EPI_NEXT_MVP_FINALIZATION_RECEIPT_V1',
        status='READY_FOR_CHIEF_DISPATCH',readiness=rr,
        command_request=dict(path=str(output/'command-request.json'),sha256=sha(output/'command-request.json')),
        data_delivery=data_ref,data_schema=delivery['schema'],source_git_sha=ready['source_git_sha'],
        source_files=len(ready['source_sha256']),model_calls=0,backward=0,updates=0,
        patient_pixels_read=0,checkpoint_reads=0,torch_imported='torch' in sys.modules,
        queue_sample=ready['queue_sample'],queue_files_changed=0,actual_slot_reserved=False,
        hospital_display_authorized=False))
    print(json.dumps(dict(status=ready['status'],readiness=rr,
                        command_request=str(output/'command-request.json'),medical_forward=0)))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['binding','data-ledger','generated','completion','pixel-owner-decision']:
        parser.add_argument('--'+name,type=Path,required=True);parser.add_argument('--'+name+'-sha',required=True)
    parser.add_argument('--output-directory',type=Path,required=True)
    parser.add_argument('--dispatch-path',type=Path,required=True)
    args=parser.parse_args();output=args.output_directory.absolute()
    if not output.is_relative_to(ROOT/'research/next-hospital-20261014/.local'):
        parser.error('fresh task-local output directory required')
    refs=[dict(path=str(getattr(args,n).absolute()),sha256=getattr(args,n+'_sha'))
          for n in ['binding','data_ledger','generated','completion','pixel_owner_decision']]
    if refs[-1]['sha256']!=PIXEL_OWNER_DECISION_SHA:parser.error('exact chief owner decision required')
    finalize(*refs,output,args.dispatch_path.absolute())


if __name__=='__main__':main()
