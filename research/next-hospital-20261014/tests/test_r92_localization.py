"""Generated tensors only. No patient IO, weights or downloads."""
import hashlib
import json
import time
import sys
from types import SimpleNamespace
import numpy as np
import pytest
import torch
from torch import nn
from torch.nn import functional as F
from epi_next.conditional_bag_r92 import ConditionalBag, Meter, Limit, bag_losses
from epi_next.bag_compare_r92 import run_compare
from epi_next.fourgrid_r92 import four_masks, perturb, effects, translated_controls, run_fourgrid, byte_sha
from epi_next.target_contract_v5 import response_metrics


class GeneratedEncoder(nn.Module):
    def __init__(self, channels=512):
        super().__init__()
        self.factor=nn.Parameter(torch.linspace(.1,1,channels)[None,:,None,None])
        self.last_spatial=None
    def forward(self,x):
        self.last_spatial=F.adaptive_avg_pool2d(x,(7,7))*self.factor
        return F.adaptive_avg_pool2d(self.last_spatial,1).flatten(1)


def bundle():
    torch.manual_seed(17)
    images=torch.rand(8,1,224,224)
    enc=GeneratedEncoder()
    with torch.no_grad(): cache=enc(images).clone()
    mean=torch.zeros(512,dtype=torch.float64);scale=torch.ones(512,dtype=torch.float64)
    weight=torch.stack((-torch.ones(512),torch.ones(512))).double()/512
    bias=torch.tensor([.1,-.1],dtype=torch.float64)
    z=F.linear(cache.double().mean(0,keepdim=True),weight,bias)
    return dict(images=images,encoder=enc,cached_gap=cache,mean=mean,scale=scale,weight=weight,
        bias=bias,members=[f'generated{i}' for i in range(8)],saved_bag_logits=z,
        valid=torch.ones(224,224,dtype=torch.bool))


def adapter(b,meter):
    return ConditionalBag(b['encoder'],b['cached_gap'],b['mean'],b['scale'],b['weight'],b['bias'],b['members'],meter)


def test_affine_input_gradient_multi_member_and_residual():
    torch.set_num_threads(1)
    b=bundle();m=Meter(10,0,0,20,60);model=adapter(b,m)
    x=(b['images'][:1]*.1).requires_grad_(True)
    y=model({b['members'][0]:x})
    slice_z=F.linear((b['encoder'](x).double()-model.mean)/model.scale,model.weight,model.bias)
    base_slice=F.linear((model.gap[:1]-model.mean)/model.scale,model.weight,model.bias)
    torch.testing.assert_close(y-model.original_logits,(slice_z-base_slice)/8,atol=1e-14,rtol=1e-12)
    losses=bag_losses(model.original_logits,y)
    torch.testing.assert_close(losses['K2_COMPONENT_LS_R92_V1'],(slice_z-base_slice).square().sum(),atol=1e-14,rtol=1e-12)
    gy=torch.autograd.grad(y[0,1],x,retain_graph=True)[0]
    gs=torch.autograd.grad(slice_z[0,1],x)[0]
    torch.testing.assert_close(gy*8,gs)
    assert gy.abs().sum()>0 and all(not p.requires_grad for p in model.parameters())
    model.train();assert not model.training and not model.encoder.training
    replacements={b['members'][0]:x,b['members'][1]:b['images'][1:2]*.2}
    multi=model(replacements)
    all_images=b['images'].clone();all_images[:1]=x.detach();all_images[1:2]*=.2
    direct=model.aggregate(b['encoder'](all_images).double())
    torch.testing.assert_close(multi,direct,atol=1e-14,rtol=1e-12)
    target=model.target;receipt=model.advance(replacements)
    assert receipt['baseline_kind']=='CURRENT_RESIDUAL_BAG' and model.target==target
    torch.testing.assert_close(model(replacements),model.current_logits)
    assert model.stage==1
    flipped=model({member:torch.zeros_like(b['images'][:1]) for member in b['members']})
    assert int(flipped.argmax(1))==0 and model.target==target==1
    previous=m.reserved.copy()
    with pytest.raises(ValueError,match='ONLY_FIXED'):model({'not_member':x})
    assert m.reserved==previous


def test_budget_and_loss_versions_do_not_inherit_cpf():
    b=bundle();m=Meter(0,0,0,0,60);model=adapter(b,m)
    with pytest.raises(Limit):model({b['members'][0]:b['images'][:1]})
    assert m.returned['forward']==0 and model.metadata()['cpf']=='NOT_CALIBRATED_NOT_APPLIED'
    clock=[0.];meter=Meter(1,1,1,1,1,clock=lambda:clock[0]);clock[0]=2.
    with pytest.raises(Limit,match='TIMEOUT'):meter.call('forward',lambda:None,samples=1)
    assert meter.reserved['forward']==0


def test_complete_generated_bag_comparison_exact_counts(tmp_path,monkeypatch):
    from epi_next.r92_entry import run_admitted,check_request
    torch.set_num_threads(1)
    monkeypatch.setattr(torch,'get_num_interop_threads',lambda:1)
    def save(name,value):
        p=tmp_path/name;p.write_text(json.dumps(value));return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    limits=dict(forward=46,backward=9,updates=8,encoder_samples=53,seconds=120)
    provider_ref=save('provider.json',{})
    cfg=save('config.json',dict(limits=dict(BAG_COMPARE=limits)))
    q=dict(schema='R92_LOC_EXECUTION_PREPARATION_V1',retry=0,stage='BAG_COMPARE',job_id='generated',task_key='generated',
        execution_readiness='FULLY_BOUND_PENDING_APPROVAL',evidence_scope='GENERATED_ONLY',
        runtime=dict(python_version=sys.version.split()[0],executable=sys.executable,packages={}),provider=provider_ref,source_lock=[provider_ref],runtime_lock=[],scientific_config=cfg,limits=limits)
    reference=save('request.json',q)
    class Guard:
        spec=SimpleNamespace(job_id='generated',task_key='generated',max_forward=46,max_backward=9,timeout_seconds=120,device='cpu')
        started=time.monotonic()
        forward=0;backward=0;done=[]
        def check(self):pass
        def begin_case(self,key):assert key=='generated'
        def end_case(self):pass
        def before_forward(self):self.forward+=1
        def before_backward(self):self.backward+=1
        def complete(self,status,**kw):self.done.append((status,kw))
    guard=Guard();captured={}
    def load(q,meter):
        captured['meter']=meter;return bundle()
    provider=SimpleNamespace(open_guard=lambda q:guard,load_bundle=load,write_result=lambda q,r:None)
    r=run_admitted(reference,provider);m=captured['meter']
    # This test called the actual worker in a generated parent double; no authority.
    assert len(guard.done)==1 and guard.done[0][0]=='SUCCESS'
    assert (guard.forward,guard.backward)==(46,9)
    q['limits']['forward']=45;bad=save('bad-budget.json',q)
    with pytest.raises(ValueError,match='FIXED_BUDGET'):check_request(bad)
    assert r['evidence']=='GENERATED_ONLY' and r['status']=='SUCCESS'
    assert m.returned==dict(forward=46,backward=9,updates=8,samples=53)
    assert m.batches==[8]+[1]*45
    assert r['adapter']['bag_aggregations']==47
    assert len(r['responses'])==19 and len(r['E2_trace'])==8
    assert r['model_parameter_updates']==0 and r['adapter']['cpf']=='NOT_CALIBRATED_NOT_APPLIED'
    for row in r['E2_trace']:assert row['component_ls']==pytest.approx(row['raw_bag_ls']*64)


def test_fourgrid_paths_interaction_and_translation_missing():
    s=torch.tensor([[.2,.3],[.4,.5]],dtype=torch.float32);p=torch.tensor([[True,False],[False,False]])
    masks=four_masks(s,p);x=torch.ones_like(s);valid=torch.tensor([[True,True],[True,False]])
    assert perturb(x,masks['B'],valid)[1,1]==1 # exterior preserved
    rows={k:response_metrics([[0.,0.]],[[0.,float(v.sum()**2)]],1) for k,v in masks.items()}
    e=effects(rows)
    assert np.allclose(e['interaction'],-np.array(e['hardening_effect_soft_outside_minus_zero_outside']))
    region=np.zeros((8,8),bool);region[2:4,3:5]=True
    t=translated_controls(region,np.ones_like(region),count=5)
    assert t['available']==5
    assert len({(c['dy'],c['dx']) for c in t['controls']})==5
    for c in t['controls']:assert c['region'].sum()==region.sum()
    missing=translated_controls(region,region,count=5)
    assert missing['missing']==5 and missing['status']=='MISSING_VALID_TRANSLATIONS'


def test_fourgrid_real_function_on_generated_input_and_strict_reuse():
    class Model(nn.Module):
        def forward(self,x):
            z=x.mean((1,2,3));return torch.stack((-z,z),1)
    model=Model();x=torch.linspace(0,1,224*224).reshape(224,224)
    valid=torch.ones_like(x,dtype=torch.bool);s=torch.ones_like(x)*.2;p=torch.zeros_like(valid);p[192:224,32:64]=True
    masks=four_masks(s,p);base=model(x[None,None]).numpy()
    responses={}
    for name,key in (('original',None),('full_mask_keep','A'),('peak_patch_keep','C')):
        retention=torch.ones_like(x) if key is None else masks[key]
        image=perturb(x,retention,valid)
        responses[name]=dict(response_metrics(base,model(image[None,None]).numpy(),1),
            masked_input_sha256=byte_sha(image),region_sha256=byte_sha(p if key=='C' else retention))
    saved=dict(status='SUCCESS',selected_epoch=3604,selected_cell=43,execution_binding_sha256='b'*64,
        input_binding=dict(input_sha256=byte_sha(x),valid_sha256=byte_sha(valid)),responses=responses,
        target_contract=dict(explanation_target=dict(policy='ORIGINAL_ARGMAX_FIXED',declared_class=1,resolved_class=1)))
    raw=json.dumps(saved).encode();request=dict(saved_readout=dict(sha256=hashlib.sha256(raw).hexdigest()),
        old_binding_sha256='b'*64,input_binding=saved['input_binding'])
    meter=Meter(4,0,0,4,10)
    r=run_fourgrid(model,lambda a:model(torch.from_numpy(a)[None,None]).numpy(),x,valid,s,p,raw,request,meter)
    assert r['status']=='SUCCESS' and meter.returned==dict(forward=4,backward=0,updates=0,samples=4)
    assert [r['responses'][k]['origin'] for k in 'ABCD']==['REUSED_R91','NEW_FORWARD','REUSED_R91','NEW_FORWARD']
    s[0,0]+=.01
    with pytest.raises(ValueError,match='STRICTLY_COMPATIBLE'):run_fourgrid(model,lambda _:None,x,valid,s,p,raw,request,Meter(4,0,0,4,10))


def parent_fixture(tmp_path):
    from datetime import datetime,timezone,timedelta
    def save(name,value):
        p=tmp_path/name;p.write_text(json.dumps(value));return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    limits=dict(forward=4,backward=0,updates=0,encoder_samples=4,seconds=120)
    spec=dict(job_id='generated-parent',task_key='GENERATED-PARENT',device='cpu',owner='LOCALIZATION',
        max_forward=4,max_backward=0,timeout_seconds=120,per_case_seconds=120,telemetry_startup_seconds=15,
        telemetry_max_gap_seconds=.25,request_grace_seconds=.25,term_grace_seconds=.75,recovery_seconds=2)
    provider=save('provider.json',{})
    cfg=save('config.json',dict(limits=dict(FOURGRID=limits)))
    policy=dict(output_root=str(tmp_path/'science'),supervision_root=str(tmp_path/'supervision'),
                queue_root=str(tmp_path/'generated-queue-never-opened'),job_id=spec['job_id'])
    q=dict(schema='R92_LOC_EXECUTION_PREPARATION_V1',stage='FOURGRID',retry=0,limits=limits,
        task_key=spec['task_key'],spec=spec,parent_entry='epi_next.r92_parent',
        provider=provider,scientific_config=cfg,source_lock=[provider],runtime_lock=[],output_policy=policy,
        **policy,runtime=dict(executable=sys.executable),command_environment=dict(R92_GENERATED_ONLY='1'),
        supervisor_dependency_root=str(tmp_path/'generated-dependency-never-opened'),supervisor_dependency_sha256='d'*64)
    reference=save('request.json',q)
    item=dict(id='R92-LOC-FOURGRID',request=reference,task_key=q['task_key'],job_id=q['job_id'],limits=limits,
        supervision_spec=spec,output_root=q['output_root'],supervision_root=q['supervision_root'])
    aggregate=save('aggregate.json',dict(items=[item],scope='GENERATED_ONLY_NOT_AUTHORITY'))
    owner=save('owner.json',dict(status='EXPLICIT_ITEMIZED_APPROVAL',approved_item_ids=['R92-LOC-FOURGRID'],request=aggregate))
    admission=save('admission.json',dict(status='APPROVED_ADMINISTRATIVE_RECOVERY',queue_root=q['queue_root'],
        scope=dict(allowed_next_task_keys=[q['task_key']],basis=dict(r92_loc_itemized_owner=dict(digest=owner['sha256']),r92_loc_itemized_request=dict(digest=aggregate['sha256'])))))
    now=datetime.now(timezone.utc)
    dispatch=save('dispatch.json',dict(schema='EPI_NEXT_R92_LOC_DISPATCH_V1',status='READY_FOR_CHIEF_DISPATCH',
        request=reference,task_key=q['task_key'],job_id=q['job_id'],limits=limits,supervision_spec=spec,
        output_root=q['output_root'],supervision_root=q['supervision_root'],owner_receipt=owner,new_admission_decision=admission,
        execution_window=dict(status='CHIEF_SLOT_GRANTED',slot_id='GENERATED_ONLY',not_before_utc=(now-timedelta(seconds=10)).isoformat(),not_after_utc=(now+timedelta(seconds=600)).isoformat())))
    return q,reference,owner,admission,dispatch,now


def test_parent_rejects_missing_authority_bad_sha_and_exact_scope(tmp_path,monkeypatch):
    from epi_next.r92_parent import run,authority
    q,ref,owner,admission,dispatch,now=parent_fixture(tmp_path)
    touched=[]
    loader=lambda _:touched.append('MUST_NOT_LOAD')
    assert run(ref,loader=loader)['queue_observations']==0
    with pytest.raises(ValueError,match='NEW_OWNER'):run(ref,execute=True,loader=loader)
    with pytest.raises(ValueError,match='EXACT_ABSOLUTE_REFERENCE'):
        run(ref,owner,admission,dict(dispatch,sha256='0'*64),execute=True,loader=loader)
    modified=dict(q);modified['job_id']='different'
    with pytest.raises(ValueError,match='ITEMIZED_SCOPE'):
        authority(ref,modified,owner,admission,dispatch)
    with pytest.raises(ValueError,match='NEW_OWNER'):run(ref,execute=True,child=True,loader=loader)
    assert touched==[]
    # Actual provider must dereference its supervisor-index reference before
    # passing metadata to the existing loader. Only generated files/doubles.
    from epi_next.r92_fourgrid_provider import open_guard
    import types
    def save(name,value):
        p=tmp_path/name;p.write_text(json.dumps(value));return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    index=dict(bundle_root='GENERATED',package='GENERATED',modules=['wave1_supervisor'])
    q['old_binding']=save('old-binding.json',dict(supervisor_index=save('index.json',index)))
    q['integration_root']=str(tmp_path)
    directory=__import__('pathlib').Path(q['supervision_root'])/q['job_id'];directory.mkdir(parents=True)
    (directory/'spec.json').write_text(json.dumps(q['spec']))
    monkeypatch.setenv('EPI_NEXT_SUPERVISOR_DIR',str(directory))
    parent=types.ModuleType('qa');parent.__path__=[]
    module=types.ModuleType('qa.next_selected_fidelity_parent');seen=[]
    def load(value):
        assert value['bundle_root']=='GENERATED';seen.append(value)
        return dict(wave1_supervisor=SimpleNamespace(ChildGuard=SimpleNamespace(from_environment=lambda:'GENERATED_GUARD')))
    module.load_supervisor=load
    monkeypatch.setitem(sys.modules,'qa',parent);monkeypatch.setitem(sys.modules,'qa.next_selected_fidelity_parent',module)
    assert open_guard(q)=='GENERATED_GUARD' and seen==[index]


def test_parent_simulated_supervisor_success_failure_and_no_retry(tmp_path):
    from contextlib import contextmanager
    from epi_next.r92_parent import run
    q,ref,owner,admission,dispatch,now=parent_fixture(tmp_path)
    calls=[];outcome=['SUCCESS']
    def supervised(spec,argv,output,dependency,dependency_sha,**kw):
        calls.append(argv)
        assert '--child' in argv and '--execute' in argv and argv[argv.index('--request')+1]==ref['path']
        assert argv[argv.index('--owner-sha')+1]==owner['sha256']
        assert (spec.max_forward,spec.max_backward)==(4,0)
        assert kw['recovery_decision_path']==admission['path'] and kw['recovery_decision_sha']==admission['sha256']
        return dict(status=outcome[0],reason=None if outcome[0]=='SUCCESS' else 'GENERATED_CHILD_FAILURE',slot_completed=True,runner_actual_counts=dict(forward=4,backward=0))
    @contextmanager
    def io(value,modules):
        assert value==q['output_policy'];yield SimpleNamespace(errors=[]),None
    modules=dict(wave1_supervisor=SimpleNamespace(SupervisionSpec=lambda **kw:SimpleNamespace(**kw),run_supervised=supervised))
    loader=lambda _:modules
    assert run(ref,owner,admission,dispatch,execute=True,loader=loader,io_factory=io,now=now)['status']=='SUCCESS'
    assert len(calls)==1
    outcome[0]='FAILED'
    r=run(ref,owner,admission,dispatch,execute=True,loader=loader,io_factory=io,now=now)
    assert r['status']=='FAILED' and r['reason']=='GENERATED_CHILD_FAILURE' and len(calls)==2
    assert 'R92_GENERATED_ONLY' not in __import__('os').environ
