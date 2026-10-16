"""Small deterministic algebra fixtures; virtual refs do not identify real assets."""
import copy
import hashlib
import math

from epilocate_next.r18_research_artifact import from_encoder_contributions


def reference(name):
    return dict(path='/GENERATED/' + name, sha256=hashlib.sha256(name.encode()).hexdigest())


def producer_fixture():
    bias = [.25, -.5]
    context = dict(source_commit='GENERATED_FIXTURE_NOT_A_REAL_COMMIT',
        config_sha256=reference('config.json')['sha256'], checkpoint_reference=reference('encoder.fixture'))
    specs = [('GENERATED-NORMAL', 'Normal', 0, [[1. + i/10, -.6 + i/20] for i in range(8)]),
             ('GENERATED-COVID-FN', 'COVID-19', 1, [[0., x] for x in [2., 1., .5, .25, -.5, -1., -2., -3.]]),
             ('GENERATED-CAP', 'CAP', 1, [[0., 3.] for _ in range(8)]),
             ('GENERATED-TIE', 'Normal', 0, [[0., .75] for _ in range(8)])]
    cases = []
    for name, category, label, raw in specs:
        logits = [bias[c] + math.fsum(v[c] for v in raw)/8 for c in range(2)]
        weighted = [[x/8 for x in v] for v in raw]
        component = [[v[c] + bias[c] for c in range(2)] for v in raw]
        positive = 1 / (1 + math.exp(logits[0]-logits[1]))
        predicted = int(logits[1] > logits[0])
        cases.append(dict(record_id=name+'-record', source_group_id=name, split='val_classification', source_diagnosis=category,
            source_label=dict(class_id=label, scope='SOURCE_GROUP', provenance='GENERATED_WEAK_LABEL'),
            correct=predicted == label, saved_predicted_class=predicted, saved_raw_logits=logits,
            saved_positive_probability=positive, model_version=copy.deepcopy(context),
            head_reference=reference('head.json'), effective_bias=bias[:], effective_margin_bias=bias[1]-bias[0],
            reconstruction_status='PASS', expert_slice_label_availability='UNKNOWN',
            feature_reference=reference(name+'-gap.fixture'), geometry_reference=reference(name+'-geometry.json'),
            geometry=dict(indices_Z=[3+4*i for i in range(8)]), raw_class_terms=raw,
            weighted_class_terms=weighted, slice_component_logits=component,
            weighted_margin_terms=[v[1]-v[0] for v in weighted], slice_component_margin=[v[1]-v[0] for v in component]))
    return dict(schema='R92_R18_SLICE_CONTRIBUTIONS_V1', status='PASS', prediction_scope='BAG', K=8,
        contribution_scope='SAVED_SLICE_GAP_AFFINE_COMPONENT', threshold=.5, threshold_tuning=False,
        spatial_maps='NOT AVAILABLE: singleton GAP placeholders', cases=cases,
        numerical_policy=reference('policy.json'), implementation=reference('producer.py'),
        frozen_reference=reference('frozen.json'), counts=dict(backbone_forward=0, torch_head_forward=0,
            backward=0, updates=0, native_CT_reads=0, weight_file_reads=0, numpy_slice_vector_class_projections=32))


def review_fixture():
    value = from_encoder_contributions(producer_fixture(), reference('producer.json'), evidence='GENERATED').model_dump()
    missing = copy.deepcopy(value['cases'][0])
    missing.update(source_group='GENERATED-PREDICTION-ONLY', source_label=None, source_label_provenance=None,
        source_category='UNKNOWN', contribution_status='NOT_RUN', slice_class_dot_products=None)
    value['cases'].append(missing)
    return value
