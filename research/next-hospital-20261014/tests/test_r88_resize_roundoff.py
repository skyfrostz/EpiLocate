"""Generated arrays only: bounded resize restoration and full cache with a substitute."""
import json
import numpy as np
import pytest
import torch
from torchvision.transforms import InterpolationMode, functional as tf
from epi_next import resnet18_mil_v1 as m
from epi_next import ctfm_research_pipeline_v4 as p
from test_r85_preprocessing_diagnostic import row


@pytest.mark.parametrize('side,location',[(s,l) for s in ['lower','upper'] for l in ['inside','boundary','outside']])
def test_exact_roundoff_envelope(side,location):
    torch.set_num_threads(1)
    tol=m.RESIZE_ROUNDOFF_ATOL
    edge=torch.tensor(-tol if side=='lower' else 1+tol,dtype=torch.float32)
    if location!='boundary':
        destination=0. if location=='inside' else (-float('inf') if side=='lower' else float('inf'))
        edge=torch.nextafter(edge,torch.tensor(destination))
    value=torch.full((8,1,224,224),.3);value[0,0,0,0]=edge
    if location=='outside':
        with pytest.raises(p.Blocked):m.recover_resize_roundoff(value)
        return
    restored,stat=m.recover_resize_roundoff(value)
    assert restored[0,0,0,0]==(0 if side=='lower' else 1)
    assert stat[side+'_corrected']==1 and stat['max_absolute_correction']<=tol
    assert value[0,0,0,0]==edge  # No in-place mutation.
    assert m.windowed_diagnostic(restored)['failed_predicates']==[]
    assert m.config()['preprocessing']['post_resize_roundoff']['absolute_tolerance']==tol


@pytest.mark.parametrize('kind',['rank','channel','spatial','dtype','nan','inf','meta','empty','minimum','maximum'])
def test_recovery_cannot_hide_other_invalid_inputs(kind):
    value=torch.full((8,1,224,224),.3)
    if kind=='rank':value=value[0]
    if kind=='channel':value=value.repeat(1,3,1,1)
    if kind=='spatial':value=value[:,:,:223,:]
    if kind=='dtype':value=value.double()
    if kind in ['nan','inf','minimum','maximum']:
        value[0,0,0,0]={'nan':float('nan'),'inf':float('inf'),'minimum':-.1,'maximum':1.1}[kind]
    if kind=='meta':value=torch.empty((8,1,224,224),device='meta')
    if kind=='empty':value=value[:0]
    with pytest.raises(p.Blocked) as exc:m.recover_resize_roundoff(value)
    json.dumps(exc.value.diagnostic,allow_nan=False)


def test_legal_path_is_bitwise_unchanged(tmp_path):
    value=torch.linspace(0,1,8*224*224).reshape(8,1,224,224)
    restored,stat=m.recover_resize_roundoff(value)
    assert restored is value and stat['lower_corrected']==stat['upper_corrected']==0
    assert stat['max_absolute_correction']==0
    native=np.full((8,256,256),-900,np.float32);r=row(tmp_path,native)
    raw=tf.resize(torch.from_numpy(np.clip((native+1350)/1500,0,1)).unsqueeze(1),[224,224],interpolation=InterpolationMode.BILINEAR,antialias=True)
    expected=m.normalize_windowed(raw)
    images,geo=m.prepare_bag(r,p.Meter('cache'))
    assert torch.equal(images,expected) and geo['resize_roundoff']['max_absolute_correction']==0
    print('normal generated control bitwise identical to original resize/normalization')


@pytest.mark.parametrize('injected,accept',[( -4*2**-23,True),(1+4*2**-23,True),(-8*2**-23,False),(1+8*2**-23,False),(float('nan'),False),(float('inf'),False)])
def test_real_prepare_chain_boundary_injection(tmp_path,monkeypatch,injected,accept):
    original=tf.resize
    def resize(*args,**kwargs):
        value=original(*args,**kwargs);value[0,0,0,0]=injected;return value
    monkeypatch.setattr(tf,'resize',resize)
    r=row(tmp_path,np.full((8,224,224),-900,np.float32))
    if accept:
        images,geo=m.prepare_bag(r,p.Meter('cache'))
        assert torch.isfinite(images).all() and geo['resize_roundoff']['max_absolute_correction']<=m.RESIZE_ROUNDOFF_ATOL
    else:
        with pytest.raises(p.Blocked):m.prepare_bag(r,p.Meter('cache'))


def test_generated_cache60_keeps_geometry_and_preprocess_identity(tmp_path,monkeypatch):
    # Create new files here; never consume saved native/real feature arrays.
    monkeypatch.setattr(torch,'load',lambda *a,**k: pytest.fail('No checkpoint load allowed'))
    records=[]
    for split,counts in p.COUNTS.items():
        for diagnosis,n in counts.items():
            for _ in range(n):
                i=len(records);case=tmp_path/f'generated_{i:02d}';case.mkdir()
                data=np.full((64,512,512) if i==0 else (64,64,64),150,np.float32)
                data[0,0,0]=-1024+i
                r=row(case,data);r['tensor_artifact']['axis_order']='Z,Y,X'
                r.update(record_id=f'SYN_R88_{i:02d}',source_group_id=f'SYN_GROUP_{i:02d}',source_diagnosis=diagnosis,task_label=int(diagnosis!='Normal'),split=split,
                    source_group_status='PUBLISHER_SOURCE_SUBJECT_LOCKED',research_status='RESEARCH_READY_SOURCE_DEFINED_EXPLORATORY',source_dicom_identity_status='NOT_EVALUATED',
                    clinical_patient_independence_status='UNKNOWN',pretraining_overlap_status='UNKNOWN',label_definition_id='MD_SOURCE_DIAGNOSIS_WEAK_V1',
                    label_provenance={'GENERATED_ONLY':True},approved_consumer_use='GENERATED_ONLY',complete_selected_stack=True,cross_group_duplicate_audit='PASS')
                gp=case/'geometry.json';geo=json.loads(gp.read_text());geo.update(tensor_artifact=r['tensor_artifact'],source_diagnosis=diagnosis,task_label=r['task_label']);gp.write_text(json.dumps(geo));r['geometry_ledger']['sha256']=p.file_sha(gp);records.append(r)
    class Substitute:
        calls=0
        def __call__(self,images):
            self.calls+=1
            assert images.shape==(8,3,224,224) and torch.isfinite(images).all()
            return images.mean((1,2,3))[:,None].expand(8,512).contiguous()
    backend=Substitute();meter=p.Meter('cache');cfg=m.config()
    receipt=m.cache_phase(records,'a'*64,dict(backbone_sha256='b'*64,config_sha256=p.digest(p.encoded(cfg)),source_commit='c'*40,evidence_type='GENERATED_MODEL_SUBSTITUTE_NO_REAL_ASSETS'),tmp_path/'cache',backend,meter)
    assert backend.calls==meter.returned_forward==60 and receipt['slice_evaluations']==480 and meter.backward==meter.updates==0
    total_lower=total_upper=0;max_delta=0
    for entry in receipt['rows']:
        geo=json.load(open(entry['geometry']['path']));stat=geo['resize_roundoff'];total_lower+=stat['lower_corrected'];total_upper+=stat['upper_corrected'];max_delta=max(max_delta,stat['max_absolute_correction'])
        assert geo['indices_Z']==[4,12,20,28,36,44,52,60]
        assert entry['identity']['preprocess_sha']==p.digest(p.encoded(cfg['preprocessing']))
    assert total_upper>0 and max_delta==2**-22
    print(json.dumps(dict(generated_cache_batches=60,input_positions=480,lower_corrected=total_lower,upper_corrected=total_upper,max_correction=max_delta,medical_calls=0,weights_loaded=0,backward=0,updates=0),sort_keys=True))
