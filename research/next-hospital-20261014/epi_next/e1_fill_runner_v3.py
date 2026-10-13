"""One global E1-FILL job, consumed by the shared INTEGRATION supervisor."""
import argparse
from itertools import product
import json
from pathlib import Path
import sys
import numpy as np
import torch
from .e1_fill_v2 import gaussian_replacement
from .localization import fixed_target_response,_logits
from .spi_recovery_v2 import ComputeMeter,StopBudget
from .first_real_e1_e2 import (locked_json,file_sha,write_json,consume_inputs,CONFIG_SHA,
    CHECKPOINT_SHA,baseline_source,DifferentiablePreparedModel,native_lookup,save_array)
from .runner_ledger_v3 import CounterLedger
from .shared_runner_binding_v3 import bind_child,finish_child,reconcile_counts

PROPOSAL_SHA='775648f0356a38af6fb3121cd43f1905b38c21a798b74f3d4166b8e97293d79c'


def save_fill_maps(result,valid,geometry,folder,record):
    iy,ix=native_lookup(geometry);assets=[];pairs=[]
    for size in (16,32,64):
        scores=np.zeros(valid.shape);reliable=np.zeros(valid.shape,dtype=bool)
        for response in result['records']:
            if response['scale_pixels']!=size:continue
            (y0,y1),(x0,x1)=response['bounds_yx'];scores[y0:y1,x0:x1]=response['margin_delta']
            if response['accepted']:reliable[y0:y1,x0:x1]=True
        reliable&=valid
        for name,array in (('scores',scores),('reliable',reliable)):
            pairs.append(dict(scale=size,kind=name,model=save_array(folder/f'E1-FILL-{size}-{name}-model.npy',array),
                native=save_array(folder/f'E1-FILL-{size}-{name}-native.npy',array[iy,ix])))
        path=folder/f'E1-FILL-{size}-native-bound.npz'
        with path.open('xb') as stream:
            np.savez_compressed(stream,scores=scores[iy,ix],reliable=reliable[iy,ix],
                native_case_manifest_sha256=np.asarray(record['native_manifest_sha256']),
                SOPInstanceUID=np.asarray(record['source_sop_uid']),native_slice_index=np.asarray(record['native_slice_index_zero_based']))
        assets.append(dict(algorithm='E1-FILL',scale=str(size),path=str(path),sha256=file_sha(path)))
    return dict(evaluation_native_npz=assets,model_native_pairs=pairs,GT_read=False,
        rasterization='published native inverse; floor(model_index+0.5)',geometry_source_sha256=record['geometry']['sha256'])


def run_fill_case(model,image,valid,meter,*,target=1,patch_sizes=(16,32,64),sink=None):
    """Same disjoint tiles and response as frozen E1; replacement alone changes."""
    x=np.asarray(image);v=np.asarray(valid)
    if x.dtype!=np.float32 or x.ndim!=2 or v.dtype!=bool or v.shape!=x.shape or not v.any():raise ValueError('prepared scalar/support required')
    result=dict(algorithm='EPI-NEXT-E1-FILL-fixed-Gaussian21-sigma5',status='RUNNING',target=target,
        records=[],candidates=[],adapter_agreement_max_abs=None,baseline_logits=None)
    before=meter.forwards;algo_started=None
    try:
        meter.check();replacement=gaussian_replacement(x)
        with torch.inference_mode():
            a=_logits(meter.forward(model,torch.from_numpy(x.copy())[None,None])[0].cpu().numpy())
            normalized=(torch.from_numpy(x.copy())[None,None].repeat(1,3,1,1)-model.mean)/model.std
            b=_logits(meter.forward(model.classifier,normalized)[0].cpu().numpy())
        result['adapter_agreement_max_abs']=float(abs(a-b).max())
        if not np.allclose(a,b,atol=1e-6,rtol=0):raise ValueError('PREPROCESS_ADAPTER_MISMATCH')
        algo_started=meter.forwards
        with torch.inference_mode():base=_logits(meter.forward(model,torch.from_numpy(x.copy())[None,None])[0].cpu().numpy())
        fixed_target_response(base,base,target);result['baseline_logits']=base.tolist()
        for size in patch_sizes:
            for y,z in product(range(0,x.shape[0],size),range(0,x.shape[1],size)):
                meter.set_phase(scale_pixels=size,bounds_yx=[[y,min(y+size,x.shape[0])],[z,min(z+size,x.shape[1])]])
                mask=np.zeros_like(v);mask[y:y+size,z:z+size]=True;mask&=v
                if not mask.any():continue
                occluded=np.where(mask,replacement,x)
                with torch.inference_mode():logits=meter.forward(model,torch.from_numpy(occluded)[None,None])[0].cpu().numpy()
                response=fixed_target_response(base,logits,target)
                response.update(bounds_yx=[[y,min(y+size,x.shape[0])],[z,min(z+size,x.shape[1])]],
                    scale_pixels=size,support_pixels=int(mask.sum()),accepted=response['margin_delta']>0)
                result['records'].append(response)
                if response['accepted']:result['candidates'].append(response)
                if sink is not None:sink(response)
        meter.check();result['status']='OK' if result['candidates'] else 'NO_RELIABLE_RESPONSE'
    except StopBudget as exc:result.update(status='PARTIAL_BUDGET',reason=str(exc))
    except Exception as exc:result.update(status='FAILED',reason=str(exc))
    result.update(global_attempts_before=before,cost_cumulative=meter.receipt(),
        adapter_attempts=(meter.forwards-before if algo_started is None else algo_started-before),
        model_calls=0 if algo_started is None else meter.forwards-algo_started)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('execution-lock','proposal','prepared-delivery','baseline-config','baseline-run','integration-source',
                 'output','resource-revision','dependency-root'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--lock-sha',required=True);parser.add_argument('--dependency-sha',required=True)
    args=parser.parse_args();args.worker_path=Path(__file__)
    lock=locked_json(args.execution_lock,args.lock_sha);proposal=locked_json(args.proposal,PROPOSAL_SHA)
    if (lock.get('status')!='LOCKED_FOR_E1_FILL_CPU_EXECUTION' or lock.get('real_model_execution_authorized') is not True
        or lock.get('proposal_sha256')!=PROPOSAL_SHA or lock.get('max_network_forwards')!=792
        or lock.get('max_reverse_calls')!=0 or lock.get('soft_timeout_seconds_total')!=120):raise ValueError('E1 exact execution lock required')
    output=args.output.resolve();allowed=Path(__file__).resolve().parents[3]/'.local'/'phase2'
    if not output.is_relative_to(allowed) or output.exists():raise ValueError('new private local output required')
    guard,binding=bind_child(args,lock,PROPOSAL_SHA,max_forward=792,max_reverse=0,seconds=120)
    meter=None;status='FAILED';reason=None;records=[];model=None
    try:
        allowed.mkdir(parents=True,exist_ok=True)
        write_json(allowed/'E1-FILL-wave1-d9eca7166f74a1bc-attempt.json',dict(output=str(output),lock_sha256=args.lock_sha))
        output.mkdir(parents=True,exist_ok=False);torch.set_num_threads(1);torch.manual_seed(20261009)
        ledger=CounterLedger(output/'algorithm-counters.json',experiment_id=guard.spec.job_id,max_forwards=792,max_reverse=0,create=True)
        meter=ComputeMeter(max_forwards=792,max_reverse=0,max_seconds=120,guard=guard,ledger=ledger,stop_file=guard.directory/'STOP')
        write_json(output/'submission.json',dict(binding=binding,proposal_sha256=PROPOSAL_SHA,lock_sha256=args.lock_sha,status='STARTED'))
        delivery,_,spec,inputs=consume_inputs(args.prepared_delivery,proposal['prepared_delivery_sha256'],args.baseline_config,CONFIG_SHA)
        baseline=locked_json(args.baseline_run,'0000000000000000000000000000000000000000000000000000000000000000')
        meter.check();adapter=baseline_source(args.integration_source)
        model=DifferentiablePreparedModel(adapter.load_verified_resnet18(Path(delivery['checkpoint_path']),CHECKPOINT_SHA),spec).eval()
        for record,p,geometry in inputs:
            folder=output/f"case-{record['case_index']}";folder.mkdir()
            meter.set_phase(algorithm='E1-FILL',case_index=record['case_index'])
            with (folder/'responses.jsonl').open('x') as stream:
                def sink(value):stream.write(json.dumps(value,allow_nan=False)+'\n');stream.flush()
                result=run_fill_case(model,p.image,p.valid_mask,meter,sink=sink)
            old_record=next(r for r in baseline['records'] if r['case_index']==record['case_index'])
            old=locked_json(old_record['result_path'],old_record['result_sha256'])['E1']
            reference=old['records'][0]['baseline_logits']
            if result['baseline_logits'] is not None and result['baseline_logits']!=reference:
                result.update(status='FAILED',reason='FROZEN_BASELINE_MISMATCH')
            payload=dict(status=result['status'],E1=result,prepared_record=record,GT_access=False,
                proposal_sha256=PROPOSAL_SHA,resource_binding=binding,frozen_reference_baseline_logits=reference)
            payload['candidate_maps']=save_fill_maps(result,p.valid_mask,geometry,folder,record)
            write_json(folder/'result.json',payload)
            records.append(dict(case_index=record['case_index'],status=result['status'],result_path=str(folder/'result.json'),
                result_sha256=file_sha(folder/'result.json'),windows=len(result['records']),accepted=len(result['candidates'])))
            if result['status'] in ('PARTIAL_BUDGET','FAILED'):
                status=result['status'];reason=result.get('reason');break
        else:status='NO_RELIABLE_RESPONSE' if all(r['status']=='NO_RELIABLE_RESPONSE' for r in records) else 'SUCCESS'
    except StopBudget as exc:status='PARTIAL_BUDGET';reason=str(exc)
    except Exception as exc:status='FAILED';reason=str(exc)
    finally:
        cost=meter.receipt() if meter is not None else dict(forward_attempts=0,forward_entered=0,reverse_entered=0)
        # Include direct normalized adapter calls in actual network entry count.
        actual=cost['forward_entered']
        try:counter_comparison=reconcile_counts(guard,cost,actual)
        except Exception as exc:
            status='FAILED';reason='COUNTER_RECONCILIATION_FAILED: '+str(exc)
            counter_comparison=dict(error=str(exc),reservations_equal=False)
        if status in ('SUCCESS','NO_RELIABLE_RESPONSE') and not counter_comparison['reservations_equal']:
            status='FAILED';reason='GLOBAL_COUNTER_MISMATCH'
        try:
            if output.exists():
                write_json(output/'run_delivery.json',dict(status=status,reason=reason,cost=cost,records=records,
                    actual_classifier_forward_entered=actual,wrapper_forward_calls=None if model is None else model.classifier_calls,
                    counter_comparison=counter_comparison,
                    proposal_sha256=PROPOSAL_SHA,binding=binding,source_sha256=file_sha(__file__),GT_access=False,
                    automatic_retries=0,command=sys.argv))
        except Exception as exc:status='FAILED';reason='RESULT_WRITE_FAILED: '+str(exc)
        finally:finish_child(guard,output/'run_delivery.json',status,cost,actual_forward=actual,reason=reason)
    return 0 if status in ('SUCCESS','NO_RELIABLE_RESPONSE') else 2


if __name__=='__main__':raise SystemExit(main())
