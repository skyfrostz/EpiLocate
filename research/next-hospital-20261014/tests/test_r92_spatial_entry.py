"""Generated wrapper, loader and entry authority gates; no real admission/CT."""

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[3]
import json
import numpy as np
import pytest
import torch
from torchvision.models import resnet18
from epi_next import r92_spatial_entry as entry
from epi_next.r92_r18_contributions import canonical, digest


def test_source_closure_includes_only_existing_namespace_package_files():
    sources=entry.source_closure()
    assert all(path.is_file() for path in sources)
    assert entry.POLICY_PATH in sources
    assert entry.r18.CONFIG_PATH in sources


def test_scalar_variable_n_preserves_input_gradient_and_no_constructor_forward():
    torch.set_num_threads(1)
    model=resnet18(weights=None).eval().requires_grad_(False);model.fc=torch.nn.Identity()
    wrapper=entry.scalar_gap_wrapper(model)
    assert wrapper.last_spatial is None
    x=torch.full((1,1,224,224),.5,requires_grad=True)
    gap=wrapper(x)
    grad=torch.autograd.grad(gap.sum(),x)[0]
    assert gap.shape==(1,512) and wrapper.last_spatial.shape==(1,512,7,7)
    assert torch.isfinite(grad).all() and grad.abs().max()>0
    with torch.no_grad():assert wrapper(x.detach().repeat(2,1,1,1)).shape==(2,512)
    assert not model.layer4._forward_hooks


def test_default_entry_refuses_real_without_authority(monkeypatch,tmp_path,capsys):
    q={'schema':'fixture'}
    monkeypatch.setattr(entry.p,'bound_json',lambda ref:q)
    monkeypatch.setattr(entry,'validate_request',lambda value:value)
    monkeypatch.setattr(entry.p,'load_shared',lambda q:pytest.fail('must not load supervisor'))
    assert entry.main(['--request',str(tmp_path/'request'),'--request-sha','0'*64])==0
    assert 'NOT RUN' in capsys.readouterr().out
    with pytest.raises(entry.p.Blocked):entry.main(['--request',str(tmp_path/'request'),'--request-sha','0'*64,'--execute'])


def test_loader_generated_assets_have_zero_implicit_forward(monkeypatch):
    class Meter:
        def check(self):pass
    class NeverRun(torch.nn.Module):
        def forward(self,x):pytest.fail('loader must not run model')
    monkeypatch.setattr(entry,'open_guard',lambda q:Meter())
    row=dict(record_id='generated',source_group_id='generated-group',split='val_classification',source_diagnosis='generated')
    scalar=torch.full((8,1,224,224),.5)
    images=entry.r18.normalize_windowed(scalar)
    geo=dict(indices_Z=list(range(8)))
    sha=digest(canonical(dict(shape=list(images.shape),dtype='float32'))+images.numpy().tobytes())
    cached=dict(row,identity={'input_sha':sha},geometry='geo')
    state={'linear.weight':np.zeros((2,512),np.float32),'linear.bias':np.zeros(2,np.float32),
           'mean':np.zeros(512,np.float32),'scale':np.ones(512,np.float32)}
    frozen=dict(consumer='consumer',cache='cache',evaluation='evaluation',head='head',head_state=state)
    cache=dict(rows=[cached],context={'checkpoint_reference':'generated'})
    objects={'frozen':frozen,'consumer':[row],'cache':cache,'evaluation':{'predictions':[dict(row,raw_logits=[0,0])]},
             'head':dict(cache_receipt='cache',context=cache['context'],state=state),'geo':geo}
    monkeypatch.setattr(entry,'bound_json',lambda ref:objects[ref])
    monkeypatch.setattr(entry.p,'validate_records',lambda values:values)
    def prepare(row,meter,observe):
        observe('post_resize_pre_normalize',scalar);return images,geo
    monkeypatch.setattr(entry.r18,'prepare_bag',prepare)
    monkeypatch.setattr(entry,'bound_bytes',lambda array:bytes())
    monkeypatch.setattr(entry.np,'load',lambda stream,allow_pickle:next(arrays))
    arrays=iter(state.values())
    monkeypatch.setattr(entry.r18,'build_backbone',lambda ref:NeverRun())
    monkeypatch.setattr(entry,'scalar_gap_wrapper',lambda backbone:backbone)
    monkeypatch.setattr(entry,'read_features',lambda cached:np.zeros((8,512),np.float32))
    bundle=entry.load_bundle({'encoder_inputs':{'frozen_reference':'frozen','record_id':'generated'}},Meter())
    assert bundle['images'].shape==(8,1,224,224) and bundle['cached_gap'].shape==(8,512)
    assert bundle['counts']=={'hidden_backbone_forward':0,'hidden_head_forward':0}
    assert bundle['valid'].all() and bundle['native_indices_Z']==list(range(8))
    assert bundle['members']==[f'generated:native_Z={z}' for z in range(8)]
    # Read LOC sources as a pinned cross-worktree dependency, never edit them.
    import importlib.util
    import sys
    from pathlib import Path
    loc=Path(str(_PUBLIC_ROOT / 'research/next-hospital-20261014/epi_next'))
    for name in ('conditional_bag_r92','target_contract_v5','fourgrid_r92','bag_compare_r92'):
        spec=importlib.util.spec_from_file_location('epi_next.'+name,loc/(name+'.py'))
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    from epi_next.conditional_bag_r92 import Meter as LOCMeter
    from epi_next.bag_compare_r92 import run_compare
    class GeneratedEncoder(torch.nn.Module):
        def forward(self,x):
            self.last_spatial=torch.nn.functional.adaptive_avg_pool2d(x,(7,7)).repeat(1,512,1,1)
            return self.last_spatial.mean((2,3))
    bundle['encoder']=GeneratedEncoder()
    bundle['cached_gap'].fill_(.5)
    meter=LOCMeter(46,9,8,53,120)
    result=run_compare(bundle,meter,generated=True)
    assert result['status']=='SUCCESS' and result['schema']=='R92_SAME_BAG_COMPARISON_V1'
    assert meter.returned==dict(forward=46,backward=9,updates=8,samples=53)


@pytest.mark.parametrize('fail_second',[False,True])
def test_extraction_twenty_or_first_failure_stops(monkeypatch,tmp_path,fail_second):
    import io
    import sys
    from pathlib import Path
    monkeypatch.setattr(torch,'set_num_interop_threads',lambda n:None)
    class Guard:
        forward=0
        completion=None
        def check(self):pass
        def begin_case(self,key):pass
        def end_case(self):pass
        def before_forward(self):
            self.forward+=1
            assert self.forward<=20
        def complete(self,status,**kwargs):self.completion=dict(status=status,**kwargs)
    guard=Guard()
    records=[dict(record_id=f'generated{i}',source_group_id=f'group{i}',source_diagnosis='generated',task_label=0,
                  split='train_weak' if i<40 else 'val_classification') for i in range(60)]
    images=torch.zeros((8,3,224,224),dtype=torch.float32)
    input_sha=digest(canonical(dict(shape=list(images.shape),dtype='float32'))+images.numpy().tobytes())
    geo=dict(model_shape=[8,3,224,224],native_shape_ZYX=[16,224,224],indices_Z=list(range(8)),native_to_LPS=np.eye(4).tolist())
    rows=[dict(r,geometry='geo',identity={'input_sha':input_sha}) for r in records]
    state={'linear.weight':np.zeros((2,512),np.float32),'linear.bias':np.zeros(2,np.float32),
           'mean':np.zeros(512,np.float32),'scale':np.ones(512,np.float32)}
    refs={k:k for k in state}
    objects={'frozen':dict(cache='cache',head='head',evaluation='evaluation',head_state=refs),'records':records,
             'cache':dict(rows=rows,context='generated'),
             'head':dict(context='generated',cache_receipt='cache',state=refs),
             'evaluation':dict(context='generated',cache_receipt='cache',head_checkpoint='head',predictions=[dict(r,raw_logits=[0,0]) for r in records]),'geo':geo}
    monkeypatch.setattr(entry,'bound_json',lambda ref:objects[ref])
    monkeypatch.setattr(entry.p,'bound_json',lambda ref,*args:objects[ref])
    monkeypatch.setattr(entry.p,'validate_records',lambda rows:rows)
    def array_bytes(key):
        buffer=io.BytesIO();np.save(buffer,state[key],allow_pickle=False);return buffer.getvalue()
    monkeypatch.setattr(entry,'bound_bytes',array_bytes)
    monkeypatch.setattr(entry,'read_features',lambda row:np.zeros((8,512),np.float32))
    monkeypatch.setattr(entry.r18,'build_backbone',lambda checkpoint:object())
    monkeypatch.setattr(entry.r18,'prepare_bag',lambda row,meter:(images,geo))
    def capture(model,values):
        if fail_second and guard.forward==2:raise RuntimeError('generated in-flight failure')
        return torch.zeros((8,512)),torch.zeros((8,512,7,7)),{'generated':True}
    monkeypatch.setattr(entry,'capture_pre_gap',capture)
    q=dict(delivery_root=str(tmp_path),output=str(tmp_path/'output'),runtime=dict(packages={},python_version=sys.version.split()[0]),
           frozen_reference='frozen',data_manifest='records',selected_record_ids=[r['record_id'] for r in records[40:]],checkpoint='generated',
           fixed_group_projection_sha256=digest(canonical([{k:r[k] for k in ('record_id','source_group_id','source_diagnosis','task_label','split')} for r in records])))
    if fail_second:
        with pytest.raises(RuntimeError):entry.extract(q,guard)
        receipt=json.loads((Path(q['output'])/'failure-receipt.json').read_text())
        assert len(receipt['completed_rows'])==1 and receipt['actual_forward'] is None
        assert guard.forward==2 and guard.completion['status']=='FAILED'
    else:
        result=entry.extract(q,guard)
        assert result['status']=='PASS' and len(result['rows'])==20 and guard.forward==20
        assert guard.completion['actual_forward']==20 and result['actual_slice_positions']==160
