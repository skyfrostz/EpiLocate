import torch
from epi_next.hspi import HSPIConfig,hspi_reference,psmi_filter

torch.set_num_threads(1)
class Toy(torch.nn.Module):
    def __init__(self): super().__init__();self.weight=torch.nn.Parameter(torch.tensor(1.))
    def forward(self,x):
        score=(x[:,:,0:2,0:2].sum((1,2,3))+.3*x[:,:,6,6].sum(1))*self.weight
        return torch.stack((score*.2,score),1)


def test_gradient_freezing_restoration_and_hierarchy():
    model=Toy();model.train();original=model.weight.detach().clone()
    cfg=HSPIConfig(grids=((4,4),(5,5)),stages=2,epochs=60,learning_rate=.05,
                   similarity_threshold=5.,sparsity_threshold=.6,mask_weight=.1,min_other_scale_support=0)
    with torch.no_grad():
        result=hspi_reference(model,torch.ones((1,1,8,8)),cfg,torch.ones((8,8),dtype=torch.bool))
    assert result['status']=='OK',result.get('error')
    assert model.training and model.weight.requires_grad and model.weight.grad is None
    assert torch.equal(original,model.weight)
    for si in range(2):
        cells=[r['selected']['cell_yx'] for r in result['stages'] if r['scale_index']==si and 'selected' in r]
        assert len(cells)==2 and cells[0]!=cells[1]
    assert result['model_calls']==sum(1+len(s['trace']) for s in result['stages'])
    assert any(s['trace'][0]['logits']!=s['trace'][-1]['logits'] for s in result['stages'])


def test_no_feasible_mask_is_not_topk():
    cfg=HSPIConfig(grids=((2,2),),epochs=2,similarity_threshold=1e-20,sparsity_threshold=1e-10,min_other_scale_support=0)
    result=hspi_reference(Toy(),torch.ones((1,1,8,8)),cfg,torch.ones((8,8),dtype=torch.bool))
    assert result['status']=='NO_FEASIBLE_MASK' and result['candidates']==[]


def test_psmi_counts_scales_not_patch_count():
    a=torch.tensor([[True,False],[False,False]]);b=~a
    assert psmi_filter([[a],[a,a],[b]],0,2)==[dict(other_scale_support=1,retained=False)]
    assert psmi_filter([[a],[a],[a]],0,2)==[dict(other_scale_support=2,retained=True)]


def test_unknown_empty_and_tie():
    x=torch.ones((1,1,8,8))
    assert hspi_reference(Toy(),x)['status']=='INPUT_UNSUPPORTED'
    assert hspi_reference(Toy(),x,valid_mask=torch.zeros((8,8),dtype=torch.bool))['status']=='INPUT_UNSUPPORTED'
    class Constant(torch.nn.Module):
        def forward(self,x):return torch.zeros((1,2))
    cfg=HSPIConfig(grids=((2,2),),epochs=3,sparsity_threshold=.9,min_other_scale_support=0)
    assert hspi_reference(Constant(),x,cfg,torch.ones((8,8),dtype=torch.bool))['status']=='NO_FEASIBLE_MASK'


def test_invalid_support_preserved_and_failure_restores_model():
    class Inspect(Toy):
        def __init__(self):super().__init__();self.seen=[]
        def forward(self,x):self.seen.append(x.detach().clone());return super().forward(x)
    model=Inspect();valid=torch.ones((8,8),dtype=torch.bool);valid[0,0]=False
    cfg=HSPIConfig(grids=((4,4),),epochs=3,stages=2,similarity_threshold=100.,sparsity_threshold=.9,min_other_scale_support=0)
    result=hspi_reference(model,torch.ones((1,1,8,8)),cfg,valid)
    assert all(float(x[0,0,0,0])==1. for x in model.seen)
    class Bad(Toy):
        def forward(self,x):raise RuntimeError('synthetic failure')
    bad=Bad();bad.eval();bad.weight.requires_grad_(False)
    result=hspi_reference(bad,torch.ones((1,1,8,8)),cfg,valid)
    assert result['status']=='FAILED' and result['model_calls']==1
    assert not bad.training and not bad.weight.requires_grad
