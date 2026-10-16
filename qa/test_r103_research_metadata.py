from pathlib import Path

import pytest

from epilocate_next.r103_research_metadata import from_r102_receipt, validate_metadata
from epilocate_next.r103_research_review import render_metadata_review
from qa.r103_research_fixture import comparison_fixture, label_fixture, old_fixture, spatial_fixture, reference
from epilocate_next.r18_research_artifact import from_encoder_contributions, Reference


def consume(value):
    return from_r102_receipt(value,reference('receipt.json'),evidence='GENERATED')


def test_spatial_references_only_never_open_arrays(monkeypatch):
    monkeypatch.setattr(Path,'open',lambda *_a,**_k:pytest.fail('ASSET_OPEN'))
    a=consume(spatial_fixture());c=a.cases[0]
    assert c.spatial.signed_margin.sha256==c.spatial.positive_derived_from_sha256
    assert c.slice_signed_contribution_status=='NOT_EXPORTED_IN_THIS_JSON'
    assert c.expert_slice_reference==c.expert_pixel_reference=='UNKNOWN'
    assert c.bag_logits==[2.,1.]


def test_real_lineage_cannot_accept_generated_head():
    with pytest.raises(ValueError,match='MODEL_BINDING_DRIFT'):
        from_r102_receipt(spatial_fixture(),reference('receipt.json'))


def test_signed_positive_cannot_alias_or_claim_wrong_origin():
    value=consume(spatial_fixture()).model_dump()
    value['cases'][0]['spatial']['positive_margin_display']=value['cases'][0]['spatial']['signed_margin']
    with pytest.raises(ValueError,match='PROVENANCE'):validate_metadata(value)


def test_gap_placeholder_cannot_claim_real_spatial_hook():
    v=spatial_fixture();v['rows'][0]['hook']['shape']=[8,512,1,1]
    with pytest.raises(ValueError,match='PRE_GAP'):consume(v)


def test_r92_gap_adapter_still_rejects_new_spatial_schema():
    with pytest.raises(ValueError):from_encoder_contributions(spatial_fixture(),reference('receipt.json'))


def test_fixed_normal_target_empty_candidates_is_unknown_not_no_lesion():
    a=consume(comparison_fixture());c=a.cases[0]
    assert c.target.class_label=='Normal_SOURCE' and c.absence_of_lesions=='UNKNOWN'
    assert c.reliable_candidates==[] and c.candidate_status=='NO_CALIBRATED_RELIABILITY_RULE'
    r=c.responses[0];assert r.raw_bag_squared_loss==.25 and r.K2_component_squared_loss==16.
    page=render_metadata_review(a)
    assert 'Normal_SOURCE' in page and '可靠候选为空不等于无病灶' in page


@pytest.mark.parametrize('mutation',['target','loss','reference','candidate'])
def test_semantic_contradictions_rejected(mutation):
    v=consume(comparison_fixture()).model_dump();c=v['cases'][0]
    if mutation=='target':c['target']['class_id']=1;c['target']['contrast_class']=0;c['target']['class_label']='COVID-19_OR_CAP_SOURCE'
    if mutation=='loss':c['responses'][0]['K2_component_squared_loss']=.25
    if mutation=='reference':c['expert_slice_reference']='PAIRED'
    if mutation=='candidate':c['reliable_candidates']=['infection-lesion']
    with pytest.raises(ValueError):validate_metadata(v)


def test_inline_arrays_not_accessed_or_copied():
    class ScalarOnly(dict):
        def __getitem__(self,key):
            if key in {'cam','E2_final_mask','E1_tiles'}:pytest.fail('INLINE_ARRAY_PROJECTION')
            return super().__getitem__(key)
    a=consume(ScalarOnly(comparison_fixture()))
    assert 'signed_class_maps' not in a.model_dump_json() and 'E2_final_mask' not in a.model_dump_json()


def test_label_dimensions_do_not_create_denominators():
    a=consume(label_fixture());assert not a.cases
    assert a.labels.mapping_status=='UNKNOWN' and a.labels.paired_source_groups is None and a.labels.evaluable_slices is None


def test_old_model_kept_separate_and_no_invented_class_label():
    a=consume(old_fixture());c=a.cases[0]
    assert c.lineage=='OLD_CASE3_NOT_R18' and c.prediction_scope=='OLD_SINGLE_SLICE'
    assert c.bag_logits is None and c.target.class_label=='NOT_EXPORTED_IN_THIS_JSON'
    value=a.model_dump();value['kind']='CONDITIONAL_BAG'
    with pytest.raises(ValueError,match='LINEAGES'):validate_metadata(value)


def test_generated_preview_escapes_strings_and_refuses_real_display():
    a=consume(comparison_fixture());a.cases[0].source_group='GENERATED-</pre><img src=x onerror=alert(1)>'
    page=render_metadata_review(a);assert '<img ' not in page and '&lt;img' in page
    a.evidence='REAL_PRECOMPUTED_JSON'
    with pytest.raises(ValueError,match='GENERATED_PREVIEW_ONLY'):render_metadata_review(a)


def test_unknown_producer_is_not_guessed():
    with pytest.raises(ValueError,match='UNSUPPORTED_METADATA_SCHEMA'):
        consume({'schema':'R103_FUTURE_UNRELEASED'})


def test_real_flag_cannot_bypass_new_profile_render_gate(tmp_path,monkeypatch):
    import hashlib,json,sys
    from epilocate_next.r18_research_review import main
    value=consume(comparison_fixture()).model_dump();value['evidence']='REAL_PRECOMPUTED_JSON'
    p=tmp_path/'metadata.json';p.write_text(json.dumps(value));target=tmp_path/'no-real-page.html'
    monkeypatch.setattr(sys,'argv',['review','--artifact',str(p),'--sha',hashlib.sha256(p.read_bytes()).hexdigest(),
        '--profile','metadata-v1','--html',str(target),'--real-metadata-page'])
    with pytest.raises(ValueError,match='GENERATED_PREVIEW_ONLY'):main()
    assert not target.exists()


def test_saved_scalar_join_uses_exact_head_geometry_input_and_no_asset_io(monkeypatch):
    from qa.r103_research_fixture import joined_fixture
    from epilocate_next.r103_research_metadata import join_saved_contributions
    args=joined_fixture();monkeypatch.setattr(Path,'open',lambda *_a,**_k:pytest.fail('ASSET_OPEN'))
    a=join_saved_contributions(*args);c=a.cases[0]
    assert c.slice_signed_contribution_status=='AVAILABLE_SAVED_GAP_SCALARS'
    assert c.expert_slice_reference=='UNKNOWN' and len(c.slice_contributions.class_dot_products)==8
    assert 'class1 raw/8' in render_metadata_review(a)


@pytest.mark.parametrize('drift',['indices','head','geometry','logits','development'])
def test_saved_scalar_join_rejects_cross_case_or_lineage_drift(drift):
    from qa.r103_research_fixture import joined_fixture
    from epilocate_next.r103_research_metadata import join_saved_contributions
    spatial,scalar,control,ref=joined_fixture()
    if drift=='indices':control['rows'][0]['fixed8_native_indices'][0]+=1
    if drift=='head':spatial.cases[0].head=Reference.model_validate(reference('other-head.json'))
    if drift=='geometry':control['rows'][0]['sample_geometry_reference']=reference('other-geometry.json')
    if drift=='logits':spatial.cases[0].bag_logits[0]+=1
    if drift=='development':control['development_record_ids']=[]
    with pytest.raises(ValueError):join_saved_contributions(spatial,scalar,control,ref)



def test_missing_area_result_cannot_be_silently_dropped():
    v=comparison_fixture();del v['responses']['E1_20_remove']
    with pytest.raises(ValueError,match='EXACT_FIXED_AREA'):consume(v)


def test_label_rows_not_equal_shape_is_rejected():
    v=label_fixture();v['index_rows_observed']=78
    with pytest.raises(ValueError,match='DIMENSION_MISMATCH'):consume(v)


def test_existing_cli_generated_scalar_join(tmp_path,monkeypatch,capsys):
    import hashlib,json,sys
    from qa.r18_research_fixture import producer_fixture
    from qa.r103_research_fixture import joined_fixture
    from epilocate_next.r18_research_review import main
    spatial,_,control,_=joined_fixture();producer=producer_fixture();producer['cases']=producer['cases'][:1]
    def save(name,value):
        p=tmp_path/name;p.write_text(json.dumps(value));return p,hashlib.sha256(p.read_bytes()).hexdigest()
    raw,sha=save('scalar.json',producer);control['source_artifact']=dict(path=str(raw),sha256=sha)
    cp,ch=save('control.json',control);sp,sh=save('spatial.json',spatial.model_dump(mode='json'))
    out=tmp_path/'normalized.json'
    monkeypatch.setattr(sys,'argv',['review','--artifact',str(sp),'--sha',sh,'--profile','metadata-v1',
        '--slice-contributions-json',str(raw),'--slice-contributions-sha',sha,
        '--fixed8-control-json',str(cp),'--fixed8-control-sha',ch,'--normalized',str(out)])
    assert main()==0
    normalized=validate_metadata(json.loads(out.read_text()))
    assert normalized.cases[0].slice_contributions is not None
    assert json.loads(capsys.readouterr().out)['json_metadata_files_read']==3
