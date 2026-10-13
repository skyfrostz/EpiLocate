"""Generated native-HU files through the real loader; no weights or model."""
import json
import numpy as np
import pytest
import torch
from epi_next import resnet18_mil_v1 as m
from epi_next import ctfm_research_pipeline_v4 as p


def row(tmp_path, data):
    path=tmp_path/'generated.npy';np.save(path,data)
    ref=dict(path=str(path),sha256=p.file_sha(path),shape=list(data.shape))
    affine=[[0,0,1,0],[0,1,0,0],[1,0,0,0],[0,0,0,1]]
    value=dict(tensor_artifact=ref,shape=ref['shape'],axis_order='Z,Y,X',
        GEOMETRY_QA='PASS_COMPLETE_SELECTED_STACK',PIXEL_QA='PASS',RESCALE_QA='PASS_DECLARED_HU',
        PROVENANCE_BOUND=True,source_diagnosis='SYNTHETIC',task_label=0,
        affine_LPS=affine,spacing_ZYX_mm=[1,1,1])
    geo=tmp_path/'geometry.json';geo.write_text(json.dumps(value))
    return dict(value,geometry_ledger=dict(path=str(geo),sha256=p.file_sha(geo)))


def test_real_loader_legal_numeric_control(tmp_path):
    torch.set_num_threads(1)
    images,geometry=m.prepare_bag(row(tmp_path,np.full((8,256,256),-900,np.float32)),p.Meter('cache'))
    expected=(torch.tensor(.3)-torch.tensor([.485,.456,.406]))/torch.tensor([.229,.224,.225])
    torch.testing.assert_close(images,expected[None,:,None,None].expand(8,3,224,224),atol=1e-6,rtol=0)
    assert geometry['indices_Z']==list(range(8))
    # Synthetic receiver only; no network, backbone or checkpoint.
    assert images.dtype==torch.float32 and images.device.type=='cpu' and images.min()<0


def test_real_loader_reproduces_resize_range_failure(tmp_path):
    with pytest.raises(p.Blocked) as exc:
        m.prepare_bag(row(tmp_path,np.full((8,512,512),150,np.float32)),p.Meter('cache'))
    d=exc.value.diagnostic
    assert d['failed_predicates']==['maximum']
    assert d['finite_max']==1.000000238418579
    assert d['shape']==[8,1,224,224] and d['nonfinite_count']==0
    print(json.dumps(d,sort_keys=True))


@pytest.mark.parametrize('kind',['rank','axes','dtype','nonfinite'])
def test_real_loader_rejects_invalid_native(tmp_path,kind):
    data=np.full((8,224,224),-900,np.float32)
    r=row(tmp_path,data)
    if kind=='rank':r=row(tmp_path,np.full((8,1,224,224),-900,np.float32))
    if kind=='dtype':r=row(tmp_path,data.astype(np.float64))
    if kind=='axes':
        path=r['geometry_ledger']['path'];v=json.load(open(path));v['axis_order']='Y,X,Z'
        open(path,'w').write(json.dumps(v));r['geometry_ledger']['sha256']=p.file_sha(path)
    if kind=='nonfinite':data[0,0,0]=np.nan;r=row(tmp_path,data)
    with pytest.raises((p.Blocked,ValueError)):
        m.prepare_bag(r,p.Meter('cache'))


@pytest.mark.parametrize('kind',['rank','channel','dtype','nan','inf','minimum','maximum','meta','empty'])
def test_boundary_predicates_without_gpu(kind):
    value=torch.full((8,1,224,224),.3)
    if kind=='rank':value=value[0]
    if kind=='channel':value=value.repeat(1,3,1,1)
    if kind=='dtype':value=value.double()
    if kind in ('nan','inf','minimum','maximum'):value[0,0,0,0]={'nan':float('nan'),'inf':float('inf'),'minimum':-.1,'maximum':1.1}[kind]
    if kind=='meta':value=torch.empty((8,1,224,224),device='meta')
    if kind=='empty':value=value[:0]
    with pytest.raises(p.Blocked) as exc:m.normalize_windowed(value)
    assert exc.value.diagnostic['failed_predicates']
    json.dumps(exc.value.diagnostic,allow_nan=False)


def test_diagnostic_entry_uses_same_pipeline_and_records_stages(tmp_path):
    from epi_next.r18_preprocess_diagnostic import diagnose
    result=diagnose(row(tmp_path,np.full((8,512,512),150,np.float32)),p.Meter('cache'))
    assert result['status']=='PREPROCESS_REJECTED' and result['diagnostic']['failed_predicates']==['maximum']
    assert [s['stage'] for s in result['stages']]==['native_header','selected_HU','windowed_pre_resize','post_resize_pre_normalize']
    assert result['weights_loaded']==result['model_calls']==result['cache_written']==0
    json.dumps(result,allow_nan=False)
