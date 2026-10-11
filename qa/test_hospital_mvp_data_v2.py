"""Generated metadata/isolated locks only. No CT, Torch or actual queue."""
import json
from pathlib import Path
import sys
import fcntl

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import hospital_mvp_protected as p
from hospital_mvp_finalize import queue_snapshot


def fixture(tmp_path,monkeypatch):
    originals=[];records=[];checked=[]
    for i in [1,2,3]:
        source=dict(case_index=i,source_ct_sha256=f'generated-source-{i}',study_uid=f'generated-study-{i}',
                    series_uid=f'generated-series-{i}',source_sop_uid=f'generated-sop-{i}',native_slice_index_zero_based=i)
        originals.append(source)
        c=dict(case_index=i,source_ct_sha256=source['source_ct_sha256'],decoded_pixel_sha256=f'generated-pixel-{i}',
               derivative_sha256=f'generated-old-derivative-{i}',preview_png_sha256=['generated-1','generated-2','generated-3'],
               all_preview_panels_reviewed=True,full_frame_including_edges_reviewed=True,
               burned_in_identity_information_detected='NO');checked.append(c)
        r=dict(source,path=str(tmp_path/f'generated-{i}.dcm'),source_decoded_pixel_sha256=c['decoded_pixel_sha256'],
               derivative_decoded_pixel_sha256=c['decoded_pixel_sha256'],previous_derivative_sha256=c['derivative_sha256'],
               owner_reviewed_at='GENERATED_ONLY',BurnedInAnnotation='NO',
               pixel_phi_visual_review='OWNER_REVIEW_HASH_BOUND_AND_DATA_AUDITED',uid_changes=False,
               lossless_reencoding=False,upload_block_reason=None,upload_scope='LOCAL_MVP_ONLY_NOT_EXTERNAL_UPLOAD_AUTHORIZATION')
        for k in ['pixel_values_equal','native_geometry_equal','deidentification_checked','encoded_pixel_payload_equal',
                  'pixel_representation_and_window_equal','header_deidentification_pass','decoder_available_in_existing_environment','upload_eligible']:r[k]=True
        records.append(r)
    review=dict(schema='EPI_NEXT_OWNER_PIXEL_VISUAL_REVIEW_V1',status='OWNER_RECORD_PENDING_DATA_AUDIT',
                owner_visual_review_affirmed=True,reviewer='钟佳桦',reviewed_at='GENERATED_ONLY',
                derivative_ledger_sha256='generated-old-ledger',preview_binding_sha256='generated-preview',records=checked)
    rp=tmp_path/'generated-review.json';rp.write_text(json.dumps(review));rs=p.sha(rp)
    owner=dict(schema='EPI_NEXT_TWO_DATA_BLOCKERS_OWNER_DECISION_V1',pixel_review_path=str(rp),pixel_review_sha256=rs,
               hospital_display_permitted=False,external_imaging_upload_permitted=False,new_model_calls_permitted=False)
    op=tmp_path/'generated-owner.json';op.write_text(json.dumps(owner));os=p.sha(op)
    monkeypatch.setattr(p,'PIXEL_REVIEW_SHA',rs);monkeypatch.setattr(p,'PIXEL_OWNER_DECISION_SHA',os)
    for r in records:r['owner_review_sha256']=rs
    delivery=dict(schema='EPI_NEXT_MVP_DERIVATIVE_DELIVERY_V2',status='LOCAL_MVP_CONTRACT_READY_WITH_OWNER_VISUAL_EVIDENCE',
                  DATA_final_evidence_audit='PASS',prepared_delivery_sha256='b85eaf6c78d1547e2aa4b93458734f533d34be5de1ed056fd152c30b92ebaa99',
                  owner_scope_sha256=p.REQUEST_SHA,owner_approval_sha256=p.OWNER_SHA,owner_decision_sha256=os,
                  owner_pixel_review_sha256=rs,owner_pixel_review_path=str(rp),previous_ledger_sha256='generated-old-ledger',
                  preview_binding_sha256='generated-preview',source_file_count=3,GT_files_read=0,model_calls=0,
                  hospital_display_authorized=False,external_imaging_upload_authorized=False,records=records)
    return delivery,dict(records=originals),dict(path=str(op),sha256=os)


def test_canonical_v2_consumed_without_rewriting_owner_pending_status(tmp_path,monkeypatch):
    args=fixture(tmp_path,monkeypatch);before=json.dumps(args[0],sort_keys=True)
    assert p.validate_data_v2(*args) is args[0]
    assert json.dumps(args[0],sort_keys=True)==before
    assert not any(tmp_path.glob('*.dcm'))


@pytest.mark.parametrize('drift',['v1','audit','status','display','scope','pixel','uid','original','header','review','encoding','decoder','count'])
def test_data_v2_and_owner_chain_drift_fails_before_pixels(tmp_path,monkeypatch,drift):
    args=fixture(tmp_path,monkeypatch);d=args[0];r=d['records'][0]
    if drift=='v1':d['schema']='EPI_NEXT_MVP_DERIVATIVE_DELIVERY_V1'
    if drift=='audit':d['DATA_final_evidence_audit']='PENDING'
    if drift=='status':d['status']='UNKNOWN'
    if drift=='display':d['hospital_display_authorized']=True
    if drift=='scope':r['upload_scope']='EXTERNAL'
    if drift=='pixel':r['derivative_decoded_pixel_sha256']='changed'
    if drift=='uid':r['source_sop_uid']='other'
    if drift=='original':r['source_ct_sha256']='other'
    if drift=='header':r['BurnedInAnnotation']='UNKNOWN'
    if drift=='review':r['previous_derivative_sha256']='other'
    if drift=='encoding':r['encoded_pixel_payload_equal']=False
    if drift=='decoder':r['decoder_available_in_existing_environment']=False
    if drift=='count':d['records'][2]['case_index']=2
    with pytest.raises(p.MVPStopped):p.validate_data_v2(*args)
    assert 'torch' not in sys.modules


def queue(tmp_path):
    q=tmp_path/'generated-queue';q.mkdir();(q/'slots').mkdir()
    for n in ['wave1.serial.lock','cpu.lock']:(q/n).write_bytes(b'GENERATED_LOCK')
    old=q/'slots/old-unknown';old.mkdir();(old/'started.json').write_text(json.dumps(dict(task_key='old-task')))
    done=q/'slots/finished';done.mkdir();(done/'started.json').write_text(json.dumps(dict(task_key='finished-task')))
    receipt=tmp_path/'generated-receipt.json';receipt.write_text(json.dumps(dict(job_id='finished',status='SUCCESS',
        slot_completed=True,exit_monotonic=1.,recovered_monotonic=2.)))
    (done/'finished.json').write_text(json.dumps(dict(job_id='finished',status='SUCCESS',receipt_path=str(receipt),receipt_sha256=p.sha(receipt))))
    return q,dict(old_job_ids=['old-unknown']),receipt


def test_readonly_existing_queue_sample_preserves_unknown_and_files(tmp_path):
    q,r,_=queue(tmp_path);before={str(x):x.read_bytes() for x in q.rglob('*') if x.is_file()}
    sample=queue_snapshot(q,r,'mvp-task')
    assert sample['status']=='PASS_AT_SAMPLE_TIME' and sample['slot_reserved'] is False
    assert before=={str(x):x.read_bytes() for x in q.rglob('*') if x.is_file()}
    assert not (q/'slots/old-unknown/finished.json').exists()


@pytest.mark.parametrize('drift',['new_unknown','receipt','spent','busy'])
def test_readonly_queue_gate_refuses_without_new_slot(tmp_path,drift):
    q,r,receipt=queue(tmp_path);held=None
    if drift=='new_unknown':
        u=q/'slots/new-unknown';u.mkdir();(u/'started.json').write_text(json.dumps(dict(task_key='unrecognized')))
    if drift=='receipt':receipt.write_text('{}')
    if drift=='spent':(q/'slots/finished/started.json').write_text(json.dumps(dict(task_key='mvp-task')))
    if drift=='busy':held=(q/'cpu.lock').open('rb');fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        with pytest.raises((p.MVPStopped,RuntimeError)):queue_snapshot(q,r,'mvp-task')
        assert not (q/'slots/mvp-task').exists()
    finally:
        if held:fcntl.flock(held,fcntl.LOCK_UN);held.close()
