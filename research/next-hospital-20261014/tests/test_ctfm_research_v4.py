"""Generated source groups only; no patient arrays, weights or GPU probes."""

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[3]
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

from epi_next import ctfm_research_pipeline_v4 as p
from epi_next.ctfm_research_math_v4 import binary_metrics, signed_f0
from epi_next.encoder import CaseLinearHead, HeadConfig, fit_patient_head


@pytest.fixture(scope='module')
def generated(tmp_path_factory):
    torch.set_num_threads(1)
    root = tmp_path_factory.mktemp('generated-v4')
    rows = []
    affine = [[0,0,.7,10],[0,.8,0,20],[1.5,0,0,30],[0,0,0,1]]
    for split, counts in p.COUNTS.items():
        for category, count in counts.items():
            for _ in range(count):
                i = len(rows)
                # Fixed generated volume, unique digest; no masks or patient facts.
                arr = np.full((64,64,64), -900+i*13, dtype=np.float32)
                arr[0,0,0] += i*.25
                path = root/f'native_{i}.npy'
                np.save(path,arr,allow_pickle=False)
                geo = root/f'geo_{i}.json'
                tensor_ref=dict(path=str(path),sha256=p.file_sha(path),shape=[64]*3,axis_order='Z,Y,X')
                geo.write_bytes(p.encoded(dict(GEOMETRY_QA='PASS_COMPLETE_SELECTED_STACK',shape=[64]*3,
                    axis_order='Z,Y,X',affine_LPS=affine,spacing_ZYX_mm=[1.5,.8,.7],
                    PIXEL_QA='PASS',RESCALE_QA='PASS_DECLARED_HU',PROVENANCE_BOUND=True,
                    tensor_artifact=tensor_ref,source_diagnosis=category,task_label=int(category!='Normal'))))
                rows.append(dict(record_id=f'SYN_{i}',source_group_id=f'SYN_SOURCE_{i}',
                    source_group_status='PUBLISHER_SOURCE_SUBJECT_LOCKED',split=split,task_label=int(category!='Normal'),
                    source_diagnosis=category,label_provenance={'kind':'GENERATED_FIXTURE_ONLY'},
                    tensor_artifact=dict(path=str(path),sha256=p.file_sha(path),shape=[64]*3,axis_order='Z,Y,X'),
                    geometry_ledger=dict(path=str(geo),sha256=p.file_sha(geo)),
                    affine_LPS=affine,spacing_ZYX_mm=[1.5,.8,.7],complete_selected_stack=True,
                    approved_consumer_use='CPU_IMPORT_AUDIT_ONLY_PENDING_ENCODER_APPROVAL',
                    research_status='RESEARCH_READY_SOURCE_DEFINED_EXPLORATORY',source_dicom_identity_status='NOT_EVALUATED',
                    clinical_patient_independence_status='UNKNOWN',pretraining_overlap_status='UNKNOWN',
                    GEOMETRY_QA='PASS_COMPLETE_SELECTED_STACK',PIXEL_QA='PASS',RESCALE_QA='PASS_DECLARED_HU',
                    PROVENANCE_BOUND=True,cross_group_duplicate_audit='PASS',label_definition_id='MD_SOURCE_DIAGNOSIS_WEAK_V1'))
    # Exercise DATA's actual unique publisher, not an ENC-only lookalike schema.
    raw_cases=root/'GENERATED_PUBLISHER_CASES.json'
    for row in rows:
        row.update(native_volume_sha256=row['tensor_artifact']['sha256'],publisher_group_evidence_bound=True)
    raw_cases.write_bytes(p.encoded(rows))
    env=dict(os.environ,PYTHONPATH=str(_PUBLIC_ROOT / 'research/next-hospital-20261014'),PYTHONDONTWRITEBYTECODE='1')
    code="from epi_next.research_import import bind_groups,consumer_records;import json,sys; print(json.dumps(consumer_records(bind_groups(json.load(open(sys.argv[1]))))))"
    rows=json.loads(subprocess.check_output([sys.executable,'-c',code,str(raw_cases)],env=env,text=True))
    p.validate_records(rows)
    manifest = root/'GENERATED_DATA_CONSUMER.json'
    manifest.write_bytes(p.encoded(rows))
    class GeneratedEncoder:
        def __init__(self): self.calls=0
        def __call__(self,tensor):
            assert tensor.shape==(1,1,64,64,64) and tensor.device.type=='cpu'
            self.calls+=1
            pooled=tensor.reshape(1,1,4,16,4,16,4,16).mean((3,5,7))
            factors=torch.linspace(.5,1.5,512).reshape(1,512,1,1,1)
            result=(pooled*factors).contiguous()
            result[:,0]=.125  # Constant channel, population-std floor must work.
            return result
    backend=GeneratedEncoder(); meter=p.Meter('cache')
    receipt=p.cache_phase(rows,p.file_sha(manifest),'b'*64,'a'*40,'f'*64,root/'cache',backend,meter,
                          evidence_type='GENERATED_BACKEND_NO_CT_FM')
    assert backend.calls==60
    cache_ref=dict(path=str(root/'cache/cache-receipt.json'),sha256=p.file_sha(root/'cache/cache-receipt.json'))
    train_meter=p.Meter('train')
    checkpoint=p.train_phase(rows,receipt,p.file_sha(manifest),cache_ref['sha256'],root/'train',train_meter)
    head_ref=dict(path=str(root/'train/head-checkpoint.json'),sha256=p.file_sha(root/'train/head-checkpoint.json'))
    eval_meter=p.Meter('evaluate')
    evaluation=p.evaluate_phase(rows,receipt,checkpoint,p.file_sha(manifest),cache_ref['sha256'],head_ref['sha256'],root/'eval',eval_meter)
    return root,rows,receipt,checkpoint,evaluation,meter,train_meter,eval_meter,p.file_sha(manifest)


def test_generated_same_cache_train_evaluate_entry(generated):
    root,rows,cache,head,evaluation,cm,tm,em,_=generated
    assert (cm.forward,cm.backward,cm.updates)==(60,0,0)
    assert (tm.forward,tm.backward,tm.updates)==(100,100,100)
    assert (em.forward,em.backward,em.updates)==(2,0,0)
    assert cache['extra_pilot_or_warmup']==0 and evaluation['medical_forward']==0
    assert head['final_update']==100 and len(head['losses'])==100
    assert evaluation['evidence_type']=='GENERATED_BACKEND_NO_CT_FM'
    assert not evaluation['clinical_accuracy_claim'] and not evaluation['independent_test_claim']
    assert len(evaluation['F0'])==60
    for row in evaluation['F0']:
        assert len(row['raw_logits'])==2 and row['predicted_class'] in (0,1)
        assert len(row['native_nominal_centers_ZYX'])==64
        assert row['reconstruction_max_absolute_error']<=1e-8
        assert row['model_version']['head_checkpoint_sha256']
    geo=json.loads((root/'cache/case_00_geometry.json').read_bytes())
    assert geo['crop']=='NONE_FULL_APPROVED_SERIES_FOV'
    assert geo['proposed_spacing_spl_mm']==[1.5,.8,.7]
    assert geo['edge_corner_max_error_voxels']==0 and geo['inverse_max_error_voxels']==0
    assert evaluation['metrics']['train_weak']['model']['n']==40
    assert evaluation['metrics']['val_classification']['model']['n']==20


def test_v4_head_matches_old_fit_and_actual_torch_logits(generated):
    root,rows,cache,checkpoint,_,_,_,_,manifest_sha=generated
    gap,features,_=p.read_cache(cache,rows,manifest_sha,p.Meter('train'))
    labels=torch.tensor([r['task_label'] for r in rows])
    old,report=fit_patient_head(torch.from_numpy(gap),labels,[r['source_group_id'] for r in rows],
        ['train' if r['split']=='train_weak' else 'observed_validation' for r in rows],
        config=HeadConfig(seeds=(17,),epochs=100))
    for name,ref in checkpoint['state'].items():
        assert np.array_equal(old.state_dict()[name].numpy(),np.load(ref['path'],allow_pickle=False))
    assert np.array_equal(old.scale.numpy()[0:1],np.array([1e-6],np.float32))
    f=features[0]
    contribution,bias,logits,error=signed_f0(f,old.linear.weight.detach().numpy(),old.linear.bias.detach().numpy(),old.mean.numpy(),old.scale.numpy())
    actual_fp32=old(torch.from_numpy(gap[0:1]).float()).detach().numpy()
    np.testing.assert_allclose(logits,actual_fp32,atol=1e-4,rtol=1e-5)
    actual_fp64=old.double()(torch.from_numpy(gap[0:1])).detach().numpy()
    np.testing.assert_allclose(logits,actual_fp64,atol=1e-10,rtol=1e-12)
    np.testing.assert_allclose(contribution.mean((2,3,4))+bias,actual_fp64,atol=1e-10,rtol=1e-12)
    assert np.any(contribution<0), 'signed values must be retained'
    (root/'F0_NUMERICAL_CONTROL.json').write_bytes(p.encoded(dict(
        evidence_type='GENERATED_ONLY_NO_CT_FM',actual_fp32_logits=actual_fp32.tolist(),
        actual_fp64_logits=actual_fp64.tolist(),f0_rebuilt_logits=(contribution.mean((2,3,4))+bias).tolist(),
        fp32_max_absolute_error=float(np.max(np.abs(logits-actual_fp32))),
        fp32_mean_absolute_error=float(np.mean(np.abs(logits-actual_fp32))),
        fp64_max_absolute_error=float(np.max(np.abs(logits-actual_fp64))),
        signed_map_max_absolute_error=error,constant_channel_scale=float(old.scale[0]),
        checkpoint_matches_old_fixed_head_exactly=True)))


@pytest.mark.parametrize('field,value',[
    ('research_status','LIMITED_SINGLE_FRAME'),('source_group_status','UNKNOWN'),
    ('clinical_patient_independence_status','VERIFIED'),('cross_group_duplicate_audit','UNKNOWN'),
    ('source_diagnosis','CAP'),('split','sealed_test'),('task_label',False)])
def test_qualification_and_label_boundaries(generated,field,value):
    rows=copy.deepcopy(generated[1]);rows[-1][field]=value
    with pytest.raises(p.Blocked):p.validate_records(rows)


def test_missing_data_fields_and_group_conflicts(generated):
    rows=copy.deepcopy(generated[1]);del rows[0]['geometry_ledger']
    with pytest.raises(p.Blocked,match='REQUIRED_FIELDS_MISSING'):p.validate_records(rows)
    rows=copy.deepcopy(generated[1]);rows[-1]['source_group_id']=rows[0]['source_group_id']
    with pytest.raises(p.Blocked,match='SOURCE_GROUP'):p.validate_records(rows)
    with pytest.raises(p.Blocked,match='EXACT_60'):p.validate_records(rows[:59])


def test_tampered_gap_or_cache_identity_rejected(generated,tmp_path):
    root,rows,cache,*_=generated;manifest_sha=generated[-1]
    bad=copy.deepcopy(cache);bad['rows'][0]['identity']['preprocess_sha']='0'*64
    with pytest.raises(p.Blocked,match='CACHE_IDENTITY'):p.read_cache(bad,rows,manifest_sha,p.Meter('train'))
    wrong=tmp_path/'wrong.npy';np.save(wrong,np.zeros((1,512),np.float64),allow_pickle=False)
    bad=copy.deepcopy(cache);bad['rows'][0]['gap']=dict(path=str(wrong),sha256=p.file_sha(wrong))
    with pytest.raises(p.Blocked,match='GAP_SPATIAL'):p.read_cache(bad,rows,manifest_sha,p.Meter('train'))


def test_metrics_ties_single_class_and_baseline():
    value=binary_metrics([1,0],[.5,.5])
    assert value['AUROC']==.5 and value['AUPRC_average_precision']==.5
    assert value['tp']==0 and value['tn']==1 and value['balanced_accuracy']==.5
    assert binary_metrics([1,1],[.6,.7])['AUROC'] is None
    assert binary_metrics([0,0],[.1,.2])['AUPRC_average_precision'] is None
    assert binary_metrics([0,1,0,1],[.1,.9,.2,.8])['AUROC']==1
    assert binary_metrics([0,1,0,1],[.1,.9,.2,.8])['AUPRC_average_precision']==1


def test_attempt_budget_no_counter_reset():
    m=p.Meter('evaluate');m.before('forward');m.before('forward')
    with pytest.raises(p.Blocked,match='LIMIT'):m.before('forward')
    assert m.forward==2


def test_native_oblique_and_unsupported_shape_rejected(generated):
    rows=copy.deepcopy(generated[1]);rows[0]['tensor_artifact']['shape']=[32,64,64]
    with pytest.raises(p.Blocked,match='DOWNSAMPLING'):p.validate_records(rows)
    from epi_next.encoder_real_input import center_ledger
    with pytest.raises(ValueError,match='axis-aligned'):
        center_ledger((64,64,64),[[1,.2,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],(1,1,1))


def test_past_authority_cannot_authorize_v4(tmp_path):
    request=dict(phase='cache',spec=dict(task_key='CTFM-V4-CACHE-60-CPU'))
    old=dict(schema='CTFM_V3_PAIR_APPROVAL_V1',status='APPROVED_NEW_SCOPE',owner='ENCODER',retry=False)
    path=tmp_path/'old-approval.json';path.write_bytes(p.encoded(old))
    ref=dict(path=str(path),sha256=p.file_sha(path))
    with pytest.raises(p.Blocked,match='NEW_EXACT'):
        p.authority(request,'f'*64,ref,ref)


def test_shared_durable_reservation_and_failed_update_receipt():
    class Guard:
        def __init__(self):self.events=[]
        def check(self):pass
        def before_forward(self):self.events.append('F')
        def before_backward(self):self.events.append('B')
    guard=Guard();meter=p.Meter('train',guard)
    meter.before('forward');meter.returned_forward+=1
    meter.before('backward');meter.returned_backward+=1
    meter.before('updates')
    assert guard.events==['F','B']
    assert meter.report()['attempted_optimizer_updates']==1
    assert meter.report()['optimizer_updates']==0
