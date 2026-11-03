"""Generated metadata acceptance/publication and resource guards only."""
import hashlib,json,time,sys
from pathlib import Path
import pytest
from epi_next import ri_metadata_supplement_v1 as sup
from test_ri_receipt_index_v1 import generated,write


def plan(tmp_path):
    failure,_,consumer,release=generated(tmp_path)
    d=json.loads(Path(failure['path']).read_text());chief=write(tmp_path/'chief.json',{'status':'SAVED_METADATA_CHECK_PASS_BATCH_PUBLICATION_FAILED','old_batch_failure_preserved':True,'consumer':consumer,'ledger_refs':[{k:r[k] for k in ('path','sha256','bytes','stage','frames')} for r in d['group_ledger_index']],'fixed_projection_sha256':'0000000000000000000000000000000000000000000000000000000000000000','source_dicom_identity_counts':{'SOURCE_DICOM_ID_NONCONFORMANT':6,'NOT_EVALUATED':54}})
    refs={'failure':failure,'consumer':consumer,'release':release,'chief_check':chief,'ledgers':d['group_ledger_index']}
    index=sup.preview(refs,sup.Budget())
    return {'schema':'R77_METADATA_ONLY_SUPPLEMENT_PLAN_V1','caps':sup.CAPS,'input_refs':refs,'source_bindings':[],'preview_binding':{'sha256':hashlib.sha256(sup.ix.encoded(index)).hexdigest()},'output_root':str(tmp_path/'supplement'),'python_runtime':{'executable':sys.executable,'sha256':hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()}}


def accept(sha):return {'schema':'R77_METADATA_ONLY_ACCEPTANCE_V1','plan_sha256':sha,'accept_metadata_supplement':True,'accept_existing_exact60_for_original_CTFM_and_R18_permissions':True,'preserve_original_batch_exit1':True,'permit_source_zip_read':False,'permit_pixel_array_read':False,'permit_decode':False,'permit_model_calls':False,'permit_new_scientific_budget':False,'permit_queue_writes':False}


def test_generated_preview_and_accepted_actual_publication(tmp_path):
    p=plan(tmp_path);check=sup.run(p,'GENERATED_SHA');assert check['original_batch_exit_code']==1 and not Path(p['output_root']).exists()
    out=sup.run(p,'GENERATED_SHA',accept('GENERATED_SHA'));r=json.loads(Path(out['path']).read_text())
    assert r['status']=='ENGINEERING_SUPPLEMENT_PUBLISHED_ORIGINAL_BATCH_FAILED' and r['original_batch_exit_code']==1 and r['model_dispatch'] is False
    assert sum(f.stat().st_size for f in Path(p['output_root']).iterdir())<sup.CAPS['output_bytes']
    assert json.loads(Path(p['input_refs']['release']['path']).read_text())['status']=='DISPATCHED'
    with pytest.raises(FileExistsError):sup.run(p,'GENERATED_SHA',accept('GENERATED_SHA'))


def test_inexact_acceptance_no_output(tmp_path):
    p=plan(tmp_path)
    with pytest.raises(sup.ix.Reject,match='EXACT_METADATA_ACCEPTANCE'):sup.run(p,'GENERATED_SHA',accept('WRONG'))
    assert not Path(p['output_root']).exists()


def test_wall_and_memory_guards(monkeypatch):
    b=sup.Budget();b.start-=61
    with pytest.raises(sup.ix.Reject,match='METADATA_WALL'):b.check()
    b.start=time.monotonic();monkeypatch.setattr(b,'peak',lambda:sup.CAPS['RSS_bytes']+1)
    with pytest.raises(sup.ix.Reject,match='METADATA_RSS'):b.check()


def test_cumulative_output_guard_before_file(tmp_path):
    b=sup.Budget();b.output=sup.CAPS['output_bytes']
    with pytest.raises(sup.ix.Reject,match='METADATA_OUTPUT'):b.write(tmp_path/'unwritten.json',{})
    assert not list(tmp_path.iterdir())


def test_acceptance_template_is_not_permission(tmp_path):
    p=plan(tmp_path);a=accept('GENERATED_SHA');a['TEMPLATE_NOT_AN_APPROVAL']=True
    with pytest.raises(sup.ix.Reject,match='ACCEPTANCE_TEMPLATE_NOT_APPROVED'):sup.run(p,'GENERATED_SHA',a)
    assert not Path(p['output_root']).exists()
