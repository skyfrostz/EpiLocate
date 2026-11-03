import json
from pathlib import Path
import numpy as np
import pytest
from epi_next.encoder_real_input import center_ledger,prepare_center_patch,read_bound_json
from epi_next.encoder_real_smoke import full_compare,validate_config,supervise

CONFIG=json.loads((Path(__file__).parents[1]/'configs/ctfm_real_m2_v1.json').read_bytes())


def test_asymmetric_signed_permutation_has_independent_correct_voxels_and_lps():
    data=np.arange(9*10*11,dtype=np.float32).reshape(9,10,11)
    affine=np.array([[0,-.7,0,20],[0,0,1.2,-30],[-2,0,0,50],[0,0,0,1.]])
    patch,ledger=prepare_center_patch(data,affine,(4,4,4))
    # S follows decreasing native k; P follows increasing c; L decreasing r.
    expected=data[::-1,::-1,:].transpose(0,2,1)[2:6,3:7,3:7]
    np.testing.assert_array_equal(patch[0,0],(np.clip(expected,-1024,2048)+1024)/3072)
    assert ledger['permutation']==[0,2,1] and ledger['flips']==[True,False,True]
    basis=np.array(ledger['patch_to_lps'])[:3,:3]
    np.testing.assert_allclose(basis,[[0,0,.7],[0,1.2,0],[2,0,0]])
    assert ledger['lps_roundtrip_max_voxel_error']<1e-8
    assert ledger['independent_sample_checks']==9


def test_synthetic_shape_center_offset_and_feature_lattice():
    a=np.array([[0,0,.78125,20],[0,.78125,0,-30],[1.25,0,0,50],[0,0,0,1.]])
    l=center_ledger([223,512,512],a)
    assert l['crop_start_spl']==[79,224,224]
    assert l['center_offset_voxels_spl']==[-.5,0,0]
    assert l['feature_lattice']['receptive_field_voxels']==[469]*3
    np.testing.assert_allclose(np.array(l['patch_to_native'])@[0,0,0,1],[79,224,224,1])


def test_oblique_or_small_volume_fails_without_padding():
    with pytest.raises(ValueError,match='fit'): center_ledger([32,64,64],np.diag([1,1,1,1]))
    a=np.eye(4);a[0,1]=.2
    with pytest.raises(ValueError,match='axis-aligned'): center_ledger([64]*3,a)


def test_complete_tensor_absolute_gate_rejects_relative_close():
    a=np.ones((1,512,2,2,2),dtype='float32')*100
    b=a+.005
    v=full_compare(a,b,CONFIG['tolerance'])
    assert v['allclose'] is True and v['status']=='FAIL' and v['elements']==4096


@pytest.mark.parametrize('change', [{'synthetic_sizes':[128]},{'real_patch_shape_spl':[128]*3},
    {'timeout_seconds_per_trial':121},{'rss_limit_bytes':0},{'checkpoint_sha256':'a'*64},
    {'data_delivery_sha256':'b'*64},{'tolerance':{'max_absolute_error':1}}, {'seed':29}, {'mps_fallback_enabled':True}])
def test_dispatch_policy_changes_rejected(change):
    with pytest.raises(ValueError): validate_config(dict(CONFIG,**change))


def test_initial_monitor_failure_emits_result_without_launch(tmp_path,monkeypatch):
    from epi_next import encoder_real_smoke as b
    def fail(): raise RuntimeError('unavailable monitor')
    monkeypatch.setattr(b,'system_memory',fail)
    value=supervise(['never-launch'],tmp_path,CONFIG)
    assert value['result']['status']=='BLOCKED' and value['process_running'] is False
    assert value['exit_code'] is None
    assert (tmp_path/'supervision.json').exists()


def test_bound_metadata_rejects_changed_bytes_before_parse(tmp_path):
    p=tmp_path/'file.json';p.write_text('invalid')
    with pytest.raises(ValueError,match='SHA'):read_bound_json(p,'a'*64)
