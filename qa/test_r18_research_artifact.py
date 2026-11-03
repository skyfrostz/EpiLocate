import copy
import hashlib
import json
from unittest.mock import patch

import pytest

from epilocate_next.r18_research_artifact import (ENC_POLICY_SHA, R91_ENCODER_SHA, R91_HEAD_SHA,
    from_encoder_contributions, load_json_metadata, metadata_summary, validate_artifact)
from epilocate_next.r18_research_review import render_review
from qa.r18_research_fixture import producer_fixture, reference, review_fixture


def test_producer_units_and_bias_reconstruct_without_any_asset_reads():
    with patch('pathlib.Path.open', side_effect=AssertionError('ASSET_OPEN_FORBIDDEN')):
        a = from_encoder_contributions(producer_fixture(), reference('producer.json'), evidence='GENERATED')
        summary = metadata_summary(a)
    assert summary['source_label_error_count'] == 1 and summary['model_calls'] == summary['referenced_assets_read'] == 0
    assert a.cases[1].input is None and a.cases[1].slice_input_sha256 is None
    assert a.cases[1].identity_status == 'SYNTHETIC'
    raw = a.cases[1].slice_class_dot_products
    weighted = (raw[0][1] - raw[0][0])/8
    component = raw[0][1]-raw[0][0]+a.model.effective_bias[1]-a.model.effective_bias[0]
    assert weighted == .25 and component == 1.25


def test_equal_logit_tie_remains_normal_and_eight_indices_are_explicit():
    a = validate_artifact(review_fixture())
    tie = next(c for c in a.cases if c.source_group == 'GENERATED-TIE')
    assert tie.bag_logits == [.25, .25] and tie.predicted_class == 0


@pytest.mark.parametrize('mutation', ['old_head', 'scope', 'duplicate_group', 'duplicate_slice', 'tie_class',
    'loose_tolerance', 'nonfinite', 'wrong_probability', 'missing_component', 'bad_reconstruction', 'gap_as_cam', 'invented_input'])
def test_invalid_or_ambiguous_artifacts_rejected(mutation):
    d = review_fixture(); c = d['cases'][0]
    if mutation == 'old_head': d['evidence']='REAL_PRECOMPUTED';d['model']['head']['sha256']='a'*64
    if mutation == 'scope': d['prediction_scope']='SLICE'
    if mutation == 'duplicate_group': d['cases'][1]['source_group']=c['source_group']
    if mutation == 'duplicate_slice': c['native_slice_indices'][1]=c['native_slice_indices'][0]
    if mutation == 'tie_class': d['cases'][3]['predicted_class']=1
    if mutation == 'loose_tolerance': d['declared_reconstruction_atol']=1.
    if mutation == 'nonfinite': c['slice_class_dot_products'][0][0]=float('nan')
    if mutation == 'wrong_probability': c['saved_positive_probability']=.5
    if mutation == 'missing_component': c['slice_class_dot_products'].pop()
    if mutation == 'bad_reconstruction': c['slice_class_dot_products'][0][0]+=1
    if mutation == 'invented_input': c['input']=reference('invented-input')
    if mutation == 'gap_as_cam':
        c['spatial'].update(status='AVAILABLE', source_kind='ACTUAL_PRE_GAP_HOOK', hook='layer4',
            feature_shape=[8,512,1,1], feature_ref=reference('gap'), signed_maps=[reference(str(i)) for i in range(8)])
    with pytest.raises(ValueError): validate_artifact(d)


def test_encoder_unit_confusion_is_rejected_before_normalization():
    d = producer_fixture(); d['cases'][0]['weighted_margin_terms'][0] += .25
    with pytest.raises(ValueError, match='UNITS_MISMATCH'):
        from_encoder_contributions(d, reference('producer.json'), evidence='GENERATED')


def test_duplicate_producer_record_rejected_even_if_group_names_differ():
    d = producer_fixture();d['cases'][1]['record_id']=d['cases'][0]['record_id']
    with pytest.raises(ValueError, match='UNIQUE_RECORD'):
        from_encoder_contributions(d, reference('producer.json'), evidence='GENERATED')


def test_real_static_metadata_page_requires_explicit_opt_in_and_never_embeds_images():
    d = review_fixture();d['evidence']='REAL_PRECOMPUTED';d['model']['head']['sha256']=R91_HEAD_SHA;d['model']['encoder']['sha256']=R91_ENCODER_SHA;d['policy_ref']['sha256']=ENC_POLICY_SHA
    for c in d['cases']:c['identity_status']='NOT_EXPORTED_IN_PRODUCER_JSON'
    a = validate_artifact(d)
    with pytest.raises(ValueError, match='NO_AUTOMATIC_DISPLAY'):render_review(a)
    page = render_review(a, real_metadata_page=True)
    assert '<img' not in page and '<canvas' not in page and 'connect-src \'none\'' in page


def test_json_sha_duplicates_and_nonfinite_rejected(tmp_path):
    p = tmp_path/'test.json'
    for raw in [b'{"x":1,"x":2}', b'{"x":NaN}']:
        p.write_bytes(raw)
        with pytest.raises(ValueError):load_json_metadata(p, hashlib.sha256(raw).hexdigest())
    p.write_text('{}')
    with pytest.raises(ValueError, match='SHA'):load_json_metadata(p, '0'*64)


def test_cache_bag_hash_join_is_not_fabricated_per_slice_hash():
    producer = producer_fixture()
    rows = [dict(record_id=str(i), source_group_id=c['source_group_id'], split=c['split'], source_diagnosis=c['source_diagnosis'],
        task_label=c['source_label']['class_id'], feature=c['feature_reference'], geometry=c['geometry_reference'],
        identity=dict(input_sha=reference(str(i))['sha256'], geometry_sha=c['geometry_reference']['sha256'])) for i,c in enumerate(producer['cases'])]
    for i,c in enumerate(producer['cases']):c['record_id']=str(i)
    cache = dict(status='PASS', context=producer['cases'][0]['model_version'], rows=rows)
    a = from_encoder_contributions(producer, reference('producer.json'), evidence='GENERATED', cache=cache, cache_ref=reference('cache.json'))
    assert a.cases[0].bag_input_sha256 == rows[0]['identity']['input_sha']
    assert a.cases[0].slice_input_sha256 is None and a.cases[0].input is None
    cache['rows'][0]['geometry'] = reference('wrong-geometry')
    with pytest.raises(ValueError, match='JOIN_MISMATCH'):
        from_encoder_contributions(producer, reference('producer.json'), evidence='GENERATED', cache=cache, cache_ref=reference('cache.json'))


def test_html_data_cannot_escape_script_or_create_fetchable_assets():
    d = review_fixture();d['cases'][0]['source_group']='</script><img src=x onerror=alert(1)>'
    page = render_review(validate_artifact(d))
    assert '\\u003c/script>' in page and '</script><img' not in page
    assert 'fetch(' not in page and 'XMLHttpRequest' not in page
