import copy
import numpy as np
import pytest
import torch
import torch.nn.functional as F
from epi_next.hspi_diagnostics import diagnose_hspi
from epi_next.verification_vnext import nearest_cell


def record():
    gap=.04-.02
    def stage(scale,cell,indices):
        mask=[[.04,.02]] if cell==0 else [[.02,.04]]
        return dict(scale_index=scale,stage=1,grid=[1,2],status='OK',trace=[dict(epoch=0,similarity=.001,sparsity=.04,peak_gap=gap,feasible=True)],selected=dict(cell_yx=[0,cell],selected_epoch=0,similarity=.001,sparsity=.04,peak_gap=gap,learned_mask=mask,mask_flat_indices=indices))
    return dict(config=dict(grids=[[1,2],[1,2]],similarity_threshold=.005,sparsity_threshold=.08,min_peak_gap=0.,benchmark_scale=0,min_other_scale_support=1),status='NO_RELIABLE_RESPONSE',reason='NO_MULTISCALE_SUPPORT',stages=[stage(0,0,[0,2]),stage(1,1,[1,3])],psmi_selection=[dict(other_scale_support=0,retained=False)],candidates=[])


def test_reconstruct_nonoverlap_without_mutating_thresholds():
    r=record();before=copy.deepcopy(r);d=diagnose_hspi(r,(2,2),np.ones((2,2),bool))
    assert d['status']=='PASS' and d['pairwise_overlap'][0]['intersection_pixels']==0
    assert d['stages'][0]['selected']['bounds_yx']==[[0,2],[0,1]] and r==before
    assert all(s['selected']['model_grid_mapping_matches'] for s in d['stages'])


def test_detects_saved_psmi_and_geometry_mismatch():
    r=record();r['stages'][1]['selected']['mask_flat_indices']=[0,3]
    d=diagnose_hspi(r,(2,2),np.ones((2,2),bool))
    assert d['status']=='FAIL' and 'MODEL_GRID_REVERSE_MAPPING_MISMATCH' in d['errors'] and 'PSMI_SAVED_VOTE_MISMATCH' in d['errors']


@pytest.mark.parametrize('shape,grid', [((13,17),(4,7)),((224,224),(7,7)),((3,2),(7,4))])
def test_independent_integer_mapping_matches_nearest_all_cells(shape,grid):
    for y in range(grid[0]):
        for x in range(grid[1]):
            source=torch.zeros((1,1,*grid));source[0,0,y,x]=1
            native=F.interpolate(source,size=shape,mode='nearest')[0,0].bool().numpy()
            assert np.array_equal(nearest_cell(list(grid),[y,x],shape),native)


def test_unknown_support_does_not_claim_mapping_verified():
    d=diagnose_hspi(record(),(2,2))
    assert not d['support_known'] and d['stages'][0]['selected']['model_grid_mapping_matches'] is None


def test_detects_trace_and_selected_round_corruption():
    r=record();r['stages'][0]['trace'][0]['feasible']=False
    r['stages'][0]['selected']['selected_epoch']=99
    d=diagnose_hspi(r,(2,2))
    assert {'CPF_TRACE_CONDITION_MISMATCH','CPF_SELECTED_ROUND_MISMATCH'}.issubset(d['errors'])
