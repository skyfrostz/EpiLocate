"""LOC boundary around ENC's no-forward R18 bundle loader; no duplicated hook.

Only a separately approved new existing child may open guard/load real assets.
"""
import importlib
from pathlib import Path
import sys
import types
from epi_next.r92_fourgrid_provider import check_environment, write_result


def encoder_entry(q):
    name='_epinext_enc_r92'
    if name not in sys.modules:
        package=types.ModuleType(name)
        package.__path__=[str(Path(q['encoder_root'])/'research/next-hospital-20261014/epi_next')]
        sys.modules[name]=package
    return importlib.import_module(name+'.r92_spatial_entry')


def open_guard(q):
    check_environment(q)
    sys.path.insert(0,q['integration_root']) # existing cumulative IO adapter only
    return encoder_entry(q).open_guard(q)


def load_bundle(q,meter):
    from epi_next.r92_entry import locked
    frozen=locked(q['frozen_reference'])
    records=locked(frozen['consumer'])
    row=next(r for r in records if r['split']=='val_classification')
    if row!=q['selected_consumer_row'] or q['encoder_inputs']['record_id']!=row['record_id']:
        raise ValueError('PRELOCKED_FIRST_VALIDATION_SOURCE_REQUIRED')
    result=encoder_entry(q).load_bundle(q,meter)
    if result['counts']!=dict(hidden_backbone_forward=0,hidden_head_forward=0):
        raise ValueError('LOADER_HIDDEN_CALLS_FORBIDDEN')
    result.update(source_group_id=row['source_group_id'],expert_reference_status='UNKNOWN')
    return result
