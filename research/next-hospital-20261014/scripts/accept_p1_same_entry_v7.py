"""One generated full-entry acceptance; never a production/medical dispatcher.

Only fixture asset hashes, the ResNet factory, short continuation milestones,
isolated queue and child bootstrap command are substituted. Production parent,
worker.main/execute, verified loaders, full W1 restore, v3 guard and storage run.
"""
import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
import torch
import pytest

from epi_next import p1_runner_v4 as worker,p1_recovery_v5 as recovery,first_real_e1_e2 as inputs
from epi_next.spi_recovery_v2 import run_spi,state_sha

HERE=Path(__file__).resolve()
RESEARCH=HERE.parents[1]
sys.path.insert(0,str(RESEARCH/'tests'))
from test_p1_recovery_v5 import fixture as recovery_fixture


class FakeClassifier(torch.nn.Module):
    def __init__(self):
        super().__init__();self.bn=torch.nn.BatchNorm2d(3);self.weight=torch.nn.Parameter(torch.tensor(.01))
        self.grad_paths=0;self.nonzero_logit_backwards=0;self.calls=0
    def forward(self,x):
        self.calls+=1;y=self.bn(x)[:,0].square().mean((1,2))*self.weight
        logits=torch.stack((y*.2,y),1)
        if torch.is_grad_enabled() and x.requires_grad:
            assert logits.requires_grad;self.grad_paths+=1
            def observed(grad):
                if bool((grad!=0).any()):self.nonzero_logit_backwards+=1
                return grad
            logits.register_hook(observed) # Observe existing backward; no extra autograd call.
        return logits


def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
    return recovery.reference(path)


def configure(root,patch):
    if (root/'GENERATED_INPUTS_ONLY').read_text()!='GENERATED_INPUTS_ONLY\n':raise ValueError('fixture sentinel required')
    settings=json.loads((root/'settings.json').read_text())
    for key,value in settings['hashes'].items():
        if hasattr(inputs,key):patch.setattr(inputs,key,value)
        if hasattr(worker,key):patch.setattr(worker,key,value)
    adapter=inputs.baseline_source(Path(settings['integration_source']))
    patch.setattr(adapter,'resnet18',lambda **kw:FakeClassifier()) # Real safe/hash/strict/eval loader remains.
    original_cfg=worker.config_from_proposal
    patch.setattr(worker,'config_from_proposal',lambda p:replace(original_cfg(p),steps=1006))
    original_continue=worker.continue_case
    patch.setattr(worker,'continue_case',lambda *a,**k:original_continue(*a,milestones=(1002,1004,1006),**k))
    supervisor=recovery.load_supervisor_bundle(settings['dependency_root'],recovery.DEPENDENCY_SHA)
    runtime=sys.modules[supervisor.__package__+'.hospital_runtime']
    patch.setattr(runtime,'QUEUE_ROOT',root/'GENERATED_QUEUE')
    return settings,adapter,supervisor


def child(root,argv):
    with pytest.MonkeyPatch.context() as patch:
        settings,adapter,supervisor=configure(root,patch)
        loaded=[];original_loader=adapter.load_verified_resnet18
        def record_loader(*args):
            model=original_loader(*args)
            assert not model.training and all(not p.requires_grad for p in model.parameters())
            loaded.append((model,state_sha(model)));return model
        patch.setattr(adapter,'load_verified_resnet18',record_loader)
        original_finish=worker.finish_child
        def observe_finish(*a,**k):
            assert len(loaded)==1
            model,before=loaded[0]
            assert state_sha(model)==before and not model.training and all(not p.requires_grad for p in model.parameters())
            save(root/'loader-autograd.json',{'actual_bridge_source':recovery.reference(adapter.__file__),
                'factory':'FakeClassifier only','verified_loader_called':True,'frozen_state_unchanged':True,
                'grad_enabled_mask_forwards':model.grad_paths,'existing_nonzero_logit_backwards':model.nonzero_logit_backwards,
                'classifier_calls':model.calls,'extra_autograd_calls':0,
                'loaded_production_modules':{n:recovery.reference(m.__file__) for n,m in list(sys.modules.items())
                    if n.startswith('epi_next.') and getattr(m,'__file__',None) and str(RESEARCH/'epi_next') in m.__file__}})
            return original_finish(*a,**k)
        patch.setattr(worker,'finish_child',observe_finish)
        sys.argv=[worker.__file__,*argv]
        return worker.main() # Exact production CLI/execute; no bind/load/verify bypass.


def make_assets(root,patch):
    root.mkdir(parents=True,exist_ok=False);(root/'GENERATED_INPUTS_ONLY').write_text('GENERATED_INPUTS_ONLY\n')
    # Reuse the established fixed-v3 recovery fixture; do not resample/probe R0.
    supervisor,queue,slot,ready,_,_,_=recovery_fixture(root,patch)
    prepared=root/'prepared';prepared.mkdir()
    def array(name,value):
        path=prepared/name
        with path.open('xb') as f:np.save(f,value,allow_pickle=False)
        return {**recovery.reference(path),'array_sha256':hashlib.sha256(value.tobytes()).hexdigest(),
                'shape':list(value.shape),'dtype':str(value.dtype)}
    image=np.linspace(.1,.9,224*224,dtype=np.float32).reshape(224,224)
    valid=np.ones(image.shape,dtype=bool);valid[:2]=False
    spec={'resize':[224,224],'crop':'NONE','pad':'NONE','channel_policy':'repeat_one_channel_rgb',
          'normalization_mean':[.485,.456,.406],'normalization_std':[.229,.224,.225]}
    spec_ref=save(prepared/'preprocessing.json',spec)
    normalized=(image[None].repeat(3,axis=0)-np.asarray(spec['normalization_mean'],np.float32)[:,None,None])/np.asarray(spec['normalization_std'],np.float32)[:,None,None]
    arrays={'image':array('image.npy',image),'valid_mask':array('valid.npy',valid),'model_tensor':array('tensor.npy',normalized)}
    slices=[];records=[]
    for index in (1,2,3):
        selected={'case_index':index,'case_id':f'GENERATED-{index}','study_uid':f'GENERATED-STUDY-{index}',
            'series_uid':f'GENERATED-SERIES-{index}','sop_uid':f'GENERATED-SOP-{index}',
            'native_slice_index_zero_based':0,'native_volume_sha256':'a'*64,'native_manifest_sha256':'b'*64}
        slices.append(selected);record={k:v for k,v in selected.items() if k!='sop_uid'}
        record['source_sop_uid']=selected['sop_uid']
        geometry={'status':'TECHNICAL_PASS','source_sop_uid':record['source_sop_uid'],'native_shape_rc':[224,224],
            'native_slice_index_zero_based':0,'model_shape_yx':[224,224],
            'native_to_model_zyx':np.eye(4).tolist(),'model_to_native_zyx':np.eye(4).tolist()}
        record.update(arrays=arrays,geometry=save(prepared/f'geometry-{index}.json',geometry),
            prepared_contract={'input_sha256':arrays['image']['array_sha256'],'preprocess_id':'GENERATED',
                              'task_definition_id':'GENERATED','scope':'SYNTHETIC','split':'synthetic'})
        records.append(record)
    slice_ref=save(prepared/'slices.json',{'slices':slices})
    cfg_ref=save(prepared/'config.json',{'status':'LOCKED_BY_COORDINATOR_BEFORE_REAL_MODEL_RUN','slice_lock_path':slice_ref['path'],'scope':'GENERATED_ONLY'})
    classifier_path=prepared/'FAKE_CLASSIFIER.pt'
    torch.save({'model_state_dict':FakeClassifier().state_dict()},classifier_path)
    delivery={'schema':'EPI-NEXT-PREPARED-DELIVERY-1','status':'READY_FOR_LOCALIZATION_CPU',
        'data_delivery_sha256':'c'*64,'slice_lock_sha256':slice_ref['sha256'],'algorithm_config_sha256':cfg_ref['sha256'],
        'checkpoint_sha256':worker.file_sha(classifier_path),'checkpoint_path':str(classifier_path),
        'model_forwards':0,'gt_reference_files_opened':False,'gt_geometry_used_for_preparation':False,
        'hospital_display_authorized':False,'preprocess_sha256':spec_ref['sha256'],'records':records}
    delivery_ref=save(prepared/'delivery.json',delivery)
    settings={'hashes':{'DATA_SHA':'c'*64,'SLICE_SHA':slice_ref['sha256'],'CONFIG_SHA':cfg_ref['sha256'],
        'CHECKPOINT_SHA':worker.file_sha(classifier_path),'PREPARED_SHA':delivery_ref['sha256']},
        'integration_source':ready['integration_source'],'dependency_root':ready['dependency_root']}
    save(root/'settings.json',settings)
    _,adapter,_=configure(root,patch)
    # Generate one real 1000-step W1 prefix for identical generated inputs, reuse
    # it under three fixture identities. No manual mask/Adam insertion.
    model=inputs.DifferentiablePreparedModel(adapter.load_verified_resnet18(classifier_path,worker.CHECKPOINT_SHA),spec)
    rows=[];checkpoints={}
    prior=run_spi(model,torch.from_numpy(image)[None,None],torch.from_numpy(valid),weight=1.,steps=1000,
        gradient_steps=(),checkpoints=(1000,),sink=rows.append,checkpoint_sink=lambda n,c:checkpoints.update({n:c}))
    if prior['status'] in ('FAILED','PARTIAL_BUDGET'):raise ValueError('generated prefix failed: '+str(prior))
    cp=checkpoints[1000];cp.update(execution_lock_sha256='d'*64,proposal_sha256='e'*64)
    legacy=root/'legacy';legacy.mkdir();cp_path=legacy/'checkpoint-1000.pt';torch.save(cp,cp_path)
    epochs=legacy/'epochs.jsonl';epochs.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    result_ref=save(legacy/'result.json',{'proposal_sha256':'e'*64,'baseline_logits':prior['baseline_logits']})
    ready.update(prepared_delivery=delivery_ref,baseline_config=cfg_ref,
        records=[{'case_index':r['case_index'],'prepared_record':r,'result':result_ref,'epochs':recovery.reference(epochs),
            'checkpoint':{**recovery.reference(cp_path),'step':1000},'execution_lock_sha256':'d'*64} for r in records],
        execution_output=str(root/'runner'),supervision_output_root=str(root/'supervision'))
    ready_ref=save(root/'fixture-readiness.json',ready);lock=recovery.dispatch_template(ready,ready_ref)
    lock.update(status='LOCKED_FOR_P1_CPU_EXECUTION',real_model_execution_authorized=True,unique_queue_verified_by_chief=True)
    lock_ref=save(root/'fixture-lock.json',lock)
    return ready,ready_ref,lock_ref,slot,{'forward':1001,'backward':1000,'autograd_grad':0}


def accept(root):
    torch.set_num_threads(1);torch.manual_seed(20261011)
    with pytest.MonkeyPatch.context() as patch:
        ready,ready_ref,lock_ref,old_slot,prefix_cost=make_assets(root,patch)
        _,_,supervisor=configure(root,patch)
        for k,v in {'PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1','PYTHONPATH':str(RESEARCH)}.items():patch.setenv(k,v)
        original_command=recovery.worker_command
        patch.setattr(recovery,'worker_command',lambda *a:[sys.executable,str(HERE),'--generated-child',str(root),*original_command(*a)[3:]])
        before={p.name:p.read_bytes() for p in old_slot.iterdir()}
        receipt=recovery.run_parent(ready_ref,lock_ref) # Actual production parent + fixed v3, no supervisor substitute.
        if receipt['status'] not in ('SUCCESS','NO_RELIABLE_RESPONSE'):
            raise ValueError('same-entry parent failed: '+json.dumps(receipt,default=str))
        delivered=json.loads((root/'runner/run_delivery.json').read_text())
        autograd=json.loads((root/'loader-autograd.json').read_text())
        assert delivered['cost']['forward_attempts']==36 and delivered['cost']['loss_backward_calls']==18
        assert delivered['cost']['optimizer_steps']==18 and delivered['cost']['autograd_grad_calls']==0
        assert autograd['classifier_calls']==36 and autograd['grad_enabled_mask_forwards']==18
        assert autograd['existing_nonzero_logit_backwards']>0 and autograd['frozen_state_unchanged']
        assert before=={p.name:p.read_bytes() for p in old_slot.iterdir()}
        for i in (1,2,3):
            output=json.loads((root/f'runner/case-{i}-result.json').read_text())
            assert output['completed_steps']==1006 and output['time']['restores']==3
            assert len((root/f'runner/case-{i}-new-epochs.jsonl').read_text().splitlines())==6
        for n in ('case-1-time.json','case-1-latest.pt','algorithm-counters.json'):
            assert (root/'runner'/n).exists() # Actual normal atomic replacement paths were executed.
        evidence={'status':'PASS_GENERATED_SAME_ENTRY','prefix_cost':prefix_cost,'continuation_cost':delivered['cost'],
            'actual_command':json.loads((root/'supervision/generated-new/command.json').read_text()),
            'actual_parent_supervisor_modules':receipt['actual_loaded_supervisor_modules'],
            'loader_autograd':autograd,'parent_status':receipt['status'],'production_queue_transactions':0,
            'medical_forward':0,'medical_backward':0,'steps':'GENERATED_SHORT_1000_TO_1002_TO_1004_TO_1006',
            'unchanged_entry_functions':['p1_recovery_v5.run_parent','p1_runner_v4.main','p1_runner_v4.execute',
                'first_real_e1_e2.consume_inputs','baseline_bridge.load_verified_resnet18','p1_runner_v4.load_legacy',
                'p1_runner_v4.continue_case','shared_runner_binding_v3.bind_child','shared_runner_binding_v3.finish_child'],
            'fixture_substitutions':['generated asset hashes/IDs','isolated queue/authority fixtures',
                'ResNet construction factory to FakeClassifier','short continuation steps/milestones','child instrumentation bootstrap'],
            'retry_authorization':'ABSENT_NOT_DISPATCH'}
        save(root/'acceptance.json',evidence)
        print(json.dumps({'acceptance':recovery.reference(root/'acceptance.json'),'status':evidence['status']}))


def main():
    if len(sys.argv)>2 and sys.argv[1]=='--generated-child':
        return child(Path(sys.argv[2]).resolve(),sys.argv[3:])
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path)
    args,remaining=p.parse_known_args()
    if remaining or args.output is None:p.error('new ignored generated output required')
    root=args.output.resolve();allowed=RESEARCH.parents[1]/'.local/phase2'
    if not root.is_relative_to(allowed) or root.exists():p.error('new ignored fixture root; no rerun/overwrite')
    accept(root);return 0


if __name__=='__main__':raise SystemExit(main())
