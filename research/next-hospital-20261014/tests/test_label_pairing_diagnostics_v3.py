"""New generated-only checks; old R103 test suite is not invoked."""
import pytest
from epi_next import label_pairing_diagnostics_v3 as d
HEADER=b'Label Index,Diagnosis,Relative Path,Folder/ID\n'
GROUPS=[dict(source_group_id='GEN-A',source_subject_directory='COVID-19 Cases/P001',source_diagnosis='COVID-19')]


def test_ambiguous_base_preserves_path_join():
    x=d.diagnose_index(HEADER+b'1,COVID-19,COVID-19 Cases,P001\n',3,GROUPS)
    assert x['valid_bases']==[0,1] and x['unique_numeric_base'] is None
    assert x['raw_path_join_rows']==1 and not x['medical_pairing_ready']


def test_zero_feasible_base_preserves_all_outliers():
    x=d.diagnose_index(HEADER+b'4,COVID-19,COVID-19 Cases,P001\n',3,GROUPS)
    assert x['valid_bases']==[] and x['raw_path_join_rows']==1
    assert [v['out_of_range_or_invalid_rows'][0]['mapped_row'] for v in x['base_candidates']]==[4,3]


def test_unique_base_does_not_establish_extent():
    x=d.diagnose_index(HEADER+b'0,COVID-19,COVID-19 Cases,P001\n',3,GROUPS)
    assert x['unique_numeric_base']==0 and x['numeric_row_mapping_ready']
    assert x['medical_denominator'] is None


def test_duplicates_gaps_and_invalid_index_retained():
    raw=HEADER+b'0,COVID-19,COVID-19 Cases,P001\n0,COVID-19,COVID-19 Cases,P001\n2,CAP,CAP Cases,P001\nBAD,CAP,CAP Cases,P002\n'
    x=d.diagnose_index(raw,3,GROUPS)
    assert x['numeric_gaps']==[1] and x['duplicate_Label_Indices']==[0]
    assert x['duplicate_diagnosis_folder_pairs']==[('COVID-19','P001')]
    assert all(not v['in_range'] for v in x['base_candidates'])


def test_path_join_conflict_not_used_as_medical_truth():
    groups=GROUPS+[dict(source_group_id='GEN-B',source_subject_directory='COVID-19 Cases',source_diagnosis='CAP')]
    x=d.diagnose_index(HEADER+b'0,COVID-19,COVID-19 Cases,P001\n',3,groups)
    assert x['rows'][0]['path_join_status']=='AMBIGUOUS'
    assert [m['diagnosis_agrees'] for m in x['rows'][0]['path_matches']]==[False,True]


def test_shape_dtype_are_version_diagnostics_not_padding():
    a=dict(rows=79,columns=200,dtype='int64',sha256='a'*64,binary_values_validated=True,allow_pickle=False)
    b=dict(a,dtype='int32',sha256='b'*64)
    x=d.matrix_pairing(a,b)
    assert x['shape_agrees'] and not x['dtype_agrees'] and x['effective_extent'] is None
    with pytest.raises(ValueError):d.matrix_pairing(dict(a,allow_pickle=True))


@pytest.mark.parametrize('row',[b'0,COVID-19,../COVID-19 Cases,P001\n',b'0,COVID-19,COVID-19 Cases,../P001\n'])
def test_unsafe_subject_paths_rejected(row):
    with pytest.raises(ValueError,match='UNSAFE'):d.diagnose_index(HEADER+row,79,GROUPS)
