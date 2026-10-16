"""One locked CPU telemetry run. No retries, GT reads or parameter search."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
import torch
from .first_real_e1_e2 import (CHECKPOINT_SHA, CONFIG_SHA, SLICE_SHA,
    DifferentiablePreparedModel, baseline_source, consume_inputs, file_sha,
    locked_json, write_json)
from .hspi import HSPIConfig, hspi_reference


class ResourceStop(RuntimeError):pass


class ForwardGuard:
    def __init__(self, model, started, max_calls, max_seconds, max_rss):
        self.model=model;self.started=started;self.max_calls=max_calls
        self.max_seconds=max_seconds;self.max_rss=max_rss

    def check(self, before_forward=False):
        if time.monotonic()-self.started >= self.max_seconds:raise ResourceStop('GLOBAL_TIME_LIMIT')
        # macOS ru_maxrss is bytes; Linux reports KiB.
        peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)
        if peak>self.max_rss:raise ResourceStop('PROCESS_PEAK_RSS_LIMIT')
        if before_forward and self.model.classifier_calls>=self.max_calls:raise ResourceStop('GLOBAL_MODEL_CALL_LIMIT')


class GuardedModel(DifferentiablePreparedModel):
    def forward(self,x):
        self.guard.check(before_forward=True)
        return super().forward(x)


def locked_inputs(args):
    lock=locked_json(args.lock,args.lock_sha)
    if lock['status']!='LOCKED_FOR_ONE_LOCAL_CPU_RUN' or lock['actual_runs']!=0:raise ValueError('not a fresh one-run lock')
    proposal=locked_json(lock['proposal_path'],lock['proposal_sha256'])
    if proposal!=lock['config']:raise ValueError('proposal/config mismatch')
    freeze=locked_json(lock['E1_freeze_path'],lock['E1_freeze_sha256'])
    if freeze['status']!='E1_BASELINE_FROZEN_WITH_LIMITATIONS':raise ValueError('E1 not frozen')
    if (proposal['device']!='cpu' or proposal['training_model_weights'] or proposal['remote_GPU']
        or proposal['parameter_changes'] or proposal['GT_generation_access']
        or proposal['case_and_slice_lock_sha256']!=SLICE_SHA
        or proposal['checkpoint_sha256']!=CHECKPOINT_SHA
        or proposal['max_total_model_calls']!=606 or lock['max_total_wall_seconds']!=360
        or lock['process_peak_rss_limit_bytes']!=6*1024**3):raise ValueError('locked scope mismatch')
    delivery,cfg,spec,inputs=consume_inputs(args.prepared_delivery,proposal['prepared_delivery_sha256'],args.baseline_config,CONFIG_SHA)
    e2=dict(cfg['E2']);e2['grids']=tuple(tuple(g) for g in e2['grids'])
    hcfg=HSPIConfig(**e2)
    for key,value in asdict(hcfg).items():
        pk={'max_model_calls':'max_model_calls_per_slice','timeout_seconds':'timeout_seconds_per_slice'}.get(key,key)
        expected=proposal[pk]
        if key=='grids':expected=tuple(tuple(g) for g in expected)
        if value!=expected:raise ValueError('telemetry changes baseline algorithm: '+key)
    if cfg['cpu_threads']!=1 or proposal['stages']!=1 or proposal['epochs']!=100:raise ValueError('invalid CPU/iteration scope')
    return lock,proposal,delivery,spec,inputs,hcfg


def worker(args):
    lock,proposal,delivery,spec,inputs,hcfg=locked_inputs(args)
    submission=json.loads((args.output/'submission.json').read_text())
    if submission['supervisor_pid']!=os.getppid() or submission['lock_sha256']!=args.lock_sha:raise ValueError('worker must be owned by its supervisor')
    started=time.monotonic();torch.set_num_threads(1);torch.manual_seed(proposal['seed'])
    adapter=baseline_source(args.integration_source)
    classifier=adapter.load_verified_resnet18(Path(delivery['checkpoint_path']),CHECKPOINT_SHA)
    classifier.eval()
    for parameter in classifier.parameters():parameter.requires_grad_(False)
    model=GuardedModel(classifier,spec)
    model.guard=ForwardGuard(model,started,proposal['max_total_model_calls'],lock['max_total_wall_seconds'],lock['process_peak_rss_limit_bytes'])
    summaries=[]
    # Baseline is saved evidence only; comparison below performs no forwards.
    baseline=locked_json(args.baseline_run,'0000000000000000000000000000000000000000000000000000000000000000')
    for record,p,_ in inputs:
        index=record['case_index'];folder=args.output/f'case-{index}';folder.mkdir()
        before=model.classifier_calls;events=[]
        with (folder/'epochs.jsonl').open('x') as stream:
            def sink(event):
                stream.write(json.dumps(event,allow_nan=False)+'\n');stream.flush();events.append(event)
            result=hspi_reference(model,torch.from_numpy(p.image.copy())[None,None],hcfg,
                torch.from_numpy(p.valid_mask.copy()),telemetry_sink=sink,resource_guard=model.guard.check)
        old_record=next(r for r in baseline['records'] if r['case_index']==index)
        old=locked_json(old_record['result_path'],old_record['result_sha256'])['E2']
        unchanged=(result['status']==old['status'] and result['model_calls']==old['model_calls']
            and result['candidates']==old['candidates']
            and [(s['baseline_logits'],s['trace']) for s in result['stages']]==[(s['baseline_logits'],s['trace']) for s in old['stages']])
        result.update(case_index=index,baseline_trace_exact_match=unchanged,
            actual_classifier_forwards=model.classifier_calls-before,
            checkpoint_sha256=CHECKPOINT_SHA,prepared_delivery_sha256=proposal['prepared_delivery_sha256'],
            lock_sha256=args.lock_sha,GT_access=False)
        write_json(folder/'result.json',result)
        summary=dict(case_index=index,status=result['status'],actual_classifier_forwards=model.classifier_calls-before,
            baseline_trace_exact_match=unchanged,epoch_events=len(events),result_path=str(folder/'result.json'),result_sha256=file_sha(folder/'result.json'),
            telemetry_path=str(folder/'epochs.jsonl'),telemetry_sha256=file_sha(folder/'epochs.jsonl'),
            gradient_decomposition_max_error=max((e['gradient_decomposition_max_error'] for e in events),default=None),
            total_projection_clipped=sum(e['projection_below_zero']+e['projection_above_one'] for e in events))
        summaries.append(summary);print(json.dumps(summary),flush=True)
        if result['status'] in ('FAILED','PARTIAL_BUDGET') or not unchanged:break
    status='EXECUTED' if len(summaries)==3 and all(r['baseline_trace_exact_match'] for r in summaries) else 'FAILED_OR_PARTIAL'
    run=dict(schema='EPI_NEXT_E2_MECHANISM_TELEMETRY_RESULT_V1',status=status,
        actual_classifier_forwards=model.classifier_calls,worker_seconds=time.monotonic()-started,
        process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
        source_git_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        source_hashes={p.name:file_sha(p) for p in Path(__file__).parent.glob('*.py')},
        lock_sha256=args.lock_sha,proposal_sha256=lock['proposal_sha256'],E1_freeze_sha256=lock['E1_freeze_sha256'],
        baseline_run_sha256=file_sha(args.baseline_run),prepared_delivery_sha256=proposal['prepared_delivery_sha256'],
        checkpoint_sha256=CHECKPOINT_SHA,records=summaries,device='cpu',cpu_threads=1,
        automatic_retries=0,parameter_changes=False,GT_access=False,training=False,remote_GPU=False,command=sys.argv)
    write_json(args.output/'run_delivery.json',run)
    return 0 if status=='EXECUTED' else 1


def supervise(args):
    started=time.monotonic()
    lock,_,_,_,_,_=locked_inputs(args)
    allowed=Path(__file__).resolve().parents[3]/'.local'/'phase2'
    if not args.output.resolve().is_relative_to(allowed):raise ValueError('telemetry output must remain in this worktree private phase2')
    if args.output.exists():raise ValueError('existing output preserved; no repeat permitted')
    # Exclusive durable one-attempt marker prevents selecting a second output
    # directory for the same lock. Never edit coordinator state or lock.
    allowed.mkdir(parents=True,exist_ok=True)
    write_json(allowed/('e2-telemetry-attempt-'+args.lock_sha+'.json'),dict(output=str(args.output),lock_sha256=args.lock_sha))
    args.output.mkdir(parents=True,exist_ok=False)
    write_json(args.output/'submission.json',dict(supervisor_pid=os.getpid(),lock_sha256=args.lock_sha,status='ONE_ATTEMPT_STARTED'))
    peak=0;stop=None
    command=[sys.executable,'-u','-m','epi_next.e2_mechanism_telemetry',*sys.argv[1:],'--worker']
    with (args.output/'worker.log').open('x') as log:
        child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        try:
            while child.poll() is None:
                try:rss=int(subprocess.check_output(['ps','-o','rss=','-p',str(child.pid)],text=True).strip())*1024
                except (subprocess.CalledProcessError,ValueError):
                    if child.poll() is not None:break
                    raise RuntimeError('cannot monitor own child RSS')
                peak=max(peak,rss)
                if time.monotonic()-started>=lock['max_total_wall_seconds']:stop='GLOBAL_TIME_LIMIT'
                if rss>lock['process_peak_rss_limit_bytes']:stop='RSS_LIMIT'
                if stop:
                    child.terminate()
                    try:child.wait(timeout=2)
                    except subprocess.TimeoutExpired:child.kill();child.wait()
                    break
                time.sleep(.1)
        finally:
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=2)
                except subprocess.TimeoutExpired:child.kill();child.wait()
        code=child.wait()
    receipt=dict(child_pid=child.pid,child_exit_code=code,status='STOPPED_BY_GUARD' if stop else 'EXITED',reason=stop,
        wall_seconds=time.monotonic()-started,observed_peak_rss_bytes=peak,
        rss_sampling_seconds=.1,stop_targets='ONLY_OWN_CHILD',automatic_retries=0,process_state='OWN_CHILD_REAPED',lock_sha256=args.lock_sha)
    write_json(args.output/'supervisor_receipt.json',receipt)
    print(json.dumps(receipt),flush=True)
    return 1 if stop or code else 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('lock','prepared-delivery','baseline-config','baseline-run','integration-source','output'):parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--lock-sha',required=True);parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args();args.output=args.output.resolve()
    return worker(args) if args.worker else supervise(args)


if __name__=='__main__':raise SystemExit(main())
