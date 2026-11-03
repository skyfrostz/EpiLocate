"""Bounded local MVP around unchanged FrozenRunner and existing app protocols.

Real mode requires source/data/owner/recovery bindings and chief dispatch.
Generated mode never imports real Torch or accesses the actual device queue.
All patient outputs stay in private ignored local storage. No hospital display.
"""
from __future__ import annotations

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[1]
import argparse
import ast
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

import hospital_mvp_generated as app

ROOT = app.ROOT
TASK = 'EPI-NEXT-HOSPITAL-MVP-THREE-LEGACY-CPU-20261013-V1'
PLAN = [1] + [32]*22 + [25] + [32]*5 + [9] + [32, 4]
REQUEST_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
OWNER_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
DECISION_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
STORAGE = Path(str(_PUBLIC_ROOT / 'research/next-hospital-20261014/epi_next/p1_storage_v4.py'))
STORAGE_SHA = 'bc431dab482538ee3f9f1024c0b89648525f887deeb740c86065f797e9fb39b3'
INDEX_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
PIXEL_OWNER_DECISION_SHA='0000000000000000000000000000000000000000000000000000000000000000'
PIXEL_REVIEW_SHA='0000000000000000000000000000000000000000000000000000000000000000'
RUNTIME_PACKAGES=('torch','torchvision','numpy','pandas','scipy','pydicom','Pillow','PyYAML',
                  'httpx','SQLAlchemy','boto3','argon2-cffi','uvicorn','fastapi','pydantic',
                  'playwright','python-multipart','pylibjpeg','pylibjpeg-libjpeg')


class MVPStopped(RuntimeError):pass


def isolated_environment():
    # Keep supervisor identity/telemetry variables; strip deployment credentials.
    return {k:v for k,v in os.environ.items()
            if not k.startswith(('EPILOCATE_', 'WORKER_', 'AWS_', 'TOKEN', 'BACKEND_URL'))}


def submission_response(claim, response):
    if (not isinstance(response,dict) or response.get('accepted') is not True
            or response.get('job_id')!=claim['job_id']
            or response.get('attempt_id')!=claim['attempt_id']):
        raise MVPStopped('SUBMISSION_RECEIPT_IDENTITY_UNVERIFIED')
    return response


def submit_once(client, claim, manifest, assets, reconcile):
    size=len(json.dumps(manifest).encode())+sum(len(raw) for raw,_ in assets.values())
    if size>64*1024*1024:raise MVPStopped('RESULT_PROTOCOL_SIZE_EXCEEDED')
    try:return submission_response(claim,client.submit(claim['job_id'],manifest,assets))
    except Exception:return submission_response(claim,reconcile(claim,manifest,assets))


def verify_persisted_submission(claim, manifest, assets, job, attempt, result, rows, read_object):
    """Read-only exact transaction reconciliation, including persisted bytes."""
    payload=dict(manifest={k:v for k,v in manifest.items() if k!='lease_token'},
                 assets={k:hashlib.sha256(v).hexdigest() for k,(v,_) in sorted(assets.items())})
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    if (job is None or attempt is None or job.public_id!=claim['job_id']
            or str(attempt.id)!=claim['attempt_id'] or attempt.job_id!=job.id
            or attempt.submission_digest!=digest):raise MVPStopped('UNKNOWN_SUBMISSION_RECONCILE_REQUIRED')
    receipt=submission_response(claim,attempt.accepted_response_json)
    if manifest['outcome']=='FAILED':
        if result is not None or rows or assets or attempt.outcome!='FAILED':
            raise MVPStopped('FAILED_SUBMISSION_STATE_MISMATCH')
        return receipt
    if (result is None or result.job_id!=job.id or result.accepted_attempt_id!=attempt.id
            or result.result_json!=manifest['result'] or job.status!='COMPLETED'
            or attempt.outcome!='SUCCEEDED' or receipt.get('result_id')!='result_'+result.id.hex):
        raise MVPStopped('PERSISTED_RESULT_IDENTITY_MISMATCH')
    descriptors=manifest['assets']
    if len(descriptors)!=len(assets) or len(rows)!=len(descriptors) or len(result.asset_manifest)!=len(rows):
        raise MVPStopped('SUBMISSION_ASSET_COUNT_MISMATCH')
    by_id={row.asset_id:row for row in rows}
    saved={entry['asset_id']:entry for entry in result.asset_manifest}
    if len(by_id)!=len(rows) or len(saved)!=len(rows):raise MVPStopped('DUPLICATE_PERSISTED_ASSET')
    for item in descriptors:
        row=by_id.get(item['asset_id']);entry=saved.get(item['asset_id'])
        raw,media=assets[item['part_name']]
        if (row is None or entry is None or row.result_id!=result.id
                or any(entry.get(k)!=v for k,v in item.items())
                or row.object_key!=entry['object_key'] or row.sha256!=item['sha256']
                or row.size_bytes!=len(raw) or row.media_type!=media
                or hashlib.sha256(raw).hexdigest()!=row.sha256):raise MVPStopped('SUBMISSION_ASSET_MISMATCH')
        stored,stored_media=read_object(row.object_key)
        if stored_media!=media or stored!=raw:raise MVPStopped('PERSISTED_ASSET_BYTES_CHANGED')
    return receipt


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream, 'sha256').hexdigest()


def bound(ref):
    path = Path(ref['path'])
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise MVPStopped('UNSAFE_BOUND_PATH')
    if sha(path) != ref['sha256']:raise MVPStopped('BOUND_SHA_MISMATCH')
    return json.loads(path.read_text())


def validate_pixel_review(record):
    ref=record.get('burned_in_pixel_review')
    if not isinstance(ref,dict):raise MVPStopped('BURNED_IN_UNKNOWN_MANUAL_REVIEW_REQUIRED')
    review=bound(ref)
    if (review.get('status')!='PASS_NO_BURNED_IN_IDENTIFIERS'
            or review.get('inspection_mode')!='HUMAN_PIXEL_REVIEW'
            or review.get('case_index')!=record['case_index']
            or review.get('source_ct_sha256')!=record['source_ct_sha256']
            or review.get('derived_pixel_sha256')!=record['derived_pixel_sha256']
            or not review.get('reviewer') or not review.get('reviewed_at')):
        raise MVPStopped('BURNED_IN_PIXEL_REVIEW_UNVERIFIED')


def validate_data_v2(delivery,prepared,owner_ref):
    """Consume DATA's ledger verbatim; never create an allowlist or BIA edit."""
    if (delivery.get('schema')!='EPI_NEXT_MVP_DERIVATIVE_DELIVERY_V2'
            or delivery.get('status')!='LOCAL_MVP_CONTRACT_READY_WITH_OWNER_VISUAL_EVIDENCE'
            or delivery.get('DATA_final_evidence_audit')!='PASS'
            or delivery.get('prepared_delivery_sha256')!='0000000000000000000000000000000000000000000000000000000000000000'
            or delivery.get('owner_scope_sha256')!=REQUEST_SHA
            or delivery.get('owner_approval_sha256')!=OWNER_SHA
            or delivery.get('owner_decision_sha256')!=PIXEL_OWNER_DECISION_SHA
            or delivery.get('owner_pixel_review_sha256')!=PIXEL_REVIEW_SHA
            or owner_ref.get('sha256')!=PIXEL_OWNER_DECISION_SHA
            or delivery.get('hospital_display_authorized') is not False
            or delivery.get('external_imaging_upload_authorized') is not False
            or delivery.get('source_file_count')!=3
            or delivery.get('GT_files_read')!=0 or delivery.get('model_calls')!=0):
        raise MVPStopped('CANONICAL_DATA_V2_AUDITED_HANDOFF_REQUIRED')
    owner=bound(owner_ref)
    review_ref=dict(path=delivery['owner_pixel_review_path'],sha256=PIXEL_REVIEW_SHA)
    if (owner.get('schema')!='EPI_NEXT_TWO_DATA_BLOCKERS_OWNER_DECISION_V1'
            or owner.get('pixel_review_path')!=review_ref['path']
            or owner.get('pixel_review_sha256')!=PIXEL_REVIEW_SHA
            or owner.get('hospital_display_permitted') is not False
            or owner.get('external_imaging_upload_permitted') is not False
            or owner.get('new_model_calls_permitted') is not False):
        raise MVPStopped('PIXEL_OWNER_DECISION_IDENTITY_CHANGED')
    review=bound(review_ref)
    if (review.get('schema')!='EPI_NEXT_OWNER_PIXEL_VISUAL_REVIEW_V1'
            or review.get('status')!='OWNER_RECORD_PENDING_DATA_AUDIT'
            or review.get('owner_visual_review_affirmed') is not True
            or review.get('reviewer')!='project-owner' or not review.get('reviewed_at')
            or review.get('derivative_ledger_sha256')!=delivery.get('previous_ledger_sha256')
            or review.get('preview_binding_sha256')!=delivery.get('preview_binding_sha256')
            or [r['case_index'] for r in review['records']]!=[1,2,3]
            or [r['case_index'] for r in delivery['records']]!=[1,2,3]
            or len(prepared['records'])!=3):
        raise MVPStopped('OWNER_PIXEL_REVIEW_CHAIN_UNVERIFIED')
    required_true=('pixel_values_equal','native_geometry_equal','deidentification_checked',
                   'encoded_pixel_payload_equal','pixel_representation_and_window_equal',
                   'header_deidentification_pass','decoder_available_in_existing_environment','upload_eligible')
    for record,original,checked in zip(delivery['records'],prepared['records'],review['records']):
        pixels=record.get('source_decoded_pixel_sha256')
        if (any(record.get(k) is not True for k in required_true)
                or any(record.get(k)!=original.get(k) for k in ['source_ct_sha256','study_uid','series_uid','source_sop_uid','native_slice_index_zero_based'])
                or not pixels or pixels!=record.get('derivative_decoded_pixel_sha256')
                or pixels!=checked.get('decoded_pixel_sha256')
                or record.get('source_ct_sha256')!=checked.get('source_ct_sha256')
                or record.get('previous_derivative_sha256')!=checked.get('derivative_sha256')
                or record.get('owner_review_sha256')!=PIXEL_REVIEW_SHA
                or record.get('owner_reviewed_at')!=review['reviewed_at']
                or checked.get('all_preview_panels_reviewed') is not True
                or checked.get('full_frame_including_edges_reviewed') is not True
                or checked.get('burned_in_identity_information_detected')!='NO'
                or len(checked.get('preview_png_sha256',[]))!=3
                or record.get('BurnedInAnnotation')!='NO'
                or record.get('pixel_phi_visual_review')!='OWNER_REVIEW_HASH_BOUND_AND_DATA_AUDITED'
                or record.get('uid_changes') is not False or record.get('lossless_reencoding') is not False
                or record.get('upload_block_reason') is not None
                or record.get('upload_scope')!='LOCAL_MVP_ONLY_NOT_EXTERNAL_UPLOAD_AUTHORIZATION'
                or not Path(record['path']).is_absolute()):
            raise MVPStopped('DATA_V2_CASE_PIXEL_SPACE_OR_REVIEW_MISMATCH')
    return delivery


def json_new(path, value):
    raw = json.dumps(value, sort_keys=True, allow_nan=False).encode() + b'\n'
    with path.open('xb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    path.chmod(0o600)


def storage_class():
    """Reuse LOC scanner verbatim, without importing optimization/Torch."""
    import errno
    import re
    import stat
    if sha(STORAGE) != STORAGE_SHA:raise MVPStopped('STORAGE_SOURCE_DRIFT')
    tree = ast.parse(STORAGE.read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in {'_ScanChanged', 'BoundedStore'}]
    if len(nodes)!=2:raise MVPStopped('STORAGE_AST_CONTRACT_CHANGED')
    scope = dict(os=os, errno=errno, re=re, stat=stat, Path=Path,
                 BudgetStopped=MVPStopped, hashlib=hashlib, json=json)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(STORAGE), 'exec'), scope)
    return scope['BoundedStore']


class CallFence:
    """Hooks only the top-level model. No diagnostic forward or backward."""
    def __init__(self, guard, store):
        self.guard=guard;self.store=store;self.case=None;self.claim=None;self.used=set()
        self.entered=0;self.completed=0;self.samples=0;self.case_entered=0
        self.case_completed=0;self.case_samples=0;self.pending=None;self.failed=False
    def select(self, case):
        if self.failed or self.claim is not None:raise MVPStopped('CASE_OR_ATTEMPT_STILL_ACTIVE')
        self.case=case;self.case_entered=0;self.case_completed=0;self.case_samples=0
    def bind_claim(self, claim, input_path):
        if self.failed or self.case is None:raise MVPStopped('MVP_RUN_STOPPED')
        identity=(claim['job_id'], claim['attempt_id'])
        if any(job==identity[0] for job,_ in self.used) or self.claim is not None:
            raise MVPStopped('NO_MODEL_ATTEMPT_REPLAY')
        params=claim['job_parameters'];model=claim['model_version']
        if (params.get('kind')!='OCCLUSION' or params.get('scales')!=[16,32,64]
                or model.get('checkpoint_sha256')!=app.MODEL_SHA
                or model.get('preprocessing_version')!=app.PREP
                or model.get('protocol_id')!=app.PROTOCOL
                or claim['input_reference']['sha256']!=self.case['sha256']
                or sha(input_path)!=self.case['sha256']):
            raise MVPStopped('UNAPPROVED_JOB_OR_INPUT')
        self.used.add(identity);self.claim=identity
    def before(self, model, inputs):
        self.guard.check()
        if self.failed or self.claim is None or self.pending is not None:
            raise MVPStopped('FORWARD_OUTSIDE_APPROVED_ATTEMPT')
        n=int(inputs[0].shape[0])
        if self.case_entered>=len(PLAN) or n!=PLAN[self.case_entered] or self.entered>=96:
            raise MVPStopped('FORWARD_BATCH_PLAN_EXHAUSTED_OR_CHANGED')
        self.store.ensure(16384)
        self.guard.before_forward()  # Durable global reservation BEFORE model entry.
        self.entered+=1;self.case_entered+=1;self.samples+=n;self.case_samples+=n
        self.pending=dict(case_index=self.case['case_index'], job_id=self.claim[0], attempt_id=self.claim[1],
            sequence=self.entered, case_batch=self.case_entered, batch_size=n,
            admitted_monotonic=time.monotonic(),
            input_sha256=self.case['sha256'], status='ADMITTED_AT_MODEL_PRE_HOOK')
        self.store.json('forward-admitted-'+str(self.entered)+'.json', self.pending)
    def after(self, model, inputs, output):
        self.guard.check()
        if self.pending is None:raise MVPStopped('UNRESERVED_FORWARD_RESULT')
        logits=output.detach().cpu().tolist()
        if len(logits)!=self.pending['batch_size'] or any(len(row)!=2 or any(not math.isfinite(x) for x in row) for row in logits):
            raise MVPStopped('INVALID_RAW_LOGITS')
        self.store.json('forward-completed-'+str(self.entered)+'.json', dict(self.pending,
            status='COMPLETED', completed_monotonic=time.monotonic(),raw_logits=logits,
            evidence_type='FROZEN_SLICE_CLASSIFIER_LOGITS'))
        self.completed+=1;self.case_completed+=1;self.pending=None
    def finish(self, output):
        if self.case_completed!=32 or self.case_samples!=935 or self.pending is not None:
            raise MVPStopped('INCOMPLETE_CASE_FORWARD_PLAN')
        status='SUCCESS' if any(s['candidate_status']=='valid' for s in output.result['scale_summaries']) else 'NO_RELIABLE_RESPONSE'
        asset_refs={}
        for name,(data,media) in output.assets.items():
            if Path(name).name!=name:raise MVPStopped('ASSET_PATH_UNSAFE')
            filename='case-'+str(self.case['case_index'])+'-asset-'+name
            digest=self.store.write(filename,data)
            asset_refs[name]=dict(path=filename,sha256=digest,size_bytes=len(data),media_type=media)
        self.store.json('case-'+str(self.case['case_index'])+'-result.json', dict(
            schema='EPI_NEXT_LEGACY_MVP_RESULT_V1',input_reference=self.case,
            status=status, algorithm='HISTORICAL_FROZEN_BASELINE_OCCLUSION', evidence_type='INPUT_OCCLUSION',
            result=output.result, entered=self.case_entered, completed=self.case_completed,
            image_evaluations=self.case_samples, backward=0, updates=0,
            runtime_seconds=time.monotonic()-self.guard.case_started,
            assets=asset_refs))
        self.store.ensure(sum(len(data) for data,_ in output.assets.values())+65536)
        self.claim=None


class ProtectedRunner:
    def __init__(self, delegate, fence):self.delegate=delegate;self.fence=fence;self.hardware=delegate.hardware
    def run(self, claim, input_path, output_dir):
        try:
            self.fence.bind_claim(claim,input_path)
            # FrozenRunner's native artifacts survive WorkerAgent's temporary
            # attempt-directory cleanup, including partial failed outputs.
            self.fence.store.ensure(1048576)
            output_dir=self.fence.store.root/('case-'+str(self.fence.case['case_index'])+'-native-output')
            output_dir.mkdir(mode=0o700,exist_ok=False)
            output=self.delegate.run(claim,input_path,output_dir)
            self.fence.finish(output);return output
        except BaseException:
            self.fence.failed=True;raise
    def release_cached_memory(self):
        release=getattr(self.delegate,'release_cached_memory',None)
        if release:release()


def supervisor(index):
    root=Path(index['bundle_root']);sys.path.insert(0,str(root))
    modules={name:importlib.import_module(index['package']+'.'+name) for name in index['modules']}
    modules['wave1_supervisor'].verify_loaded_bundle(index['dependency_root'],index['dependency_sha256'])
    return modules


def required_source_paths(dist):
    paths={Path(__file__).resolve(),ROOT/'qa/hospital_mvp_generated.py',
           ROOT/'qa/hospital_mvp_protected_fake.py',ROOT/'qa/phase5_local_https.py',
           ROOT/'qa/hospital_mvp_binding.py',
           ROOT/'qa/hospital_mvp_finalize.py',
           ROOT/'scripts/occlusion_runner.py',STORAGE}
    for folder in ['worker','backend_v2','session_gateway','algorithm','src']:
        paths.update(p.resolve() for p in (ROOT/folder).rglob('*.py') if '.local' not in p.parts)
    paths.update(p.resolve() for p in Path(dist).rglob('*') if p.is_file())
    return {str(path) for path in paths}


def validate_readiness(ready):
    if ready['schema']!='EPI_NEXT_MVP_PROTECTED_READINESS_V1':raise MVPStopped('READINESS_SCHEMA')
    if ready.get('status')!='READY_FOR_CHIEF_DISPATCH':raise MVPStopped('MVP_READINESS_NOT_COMPLETE')
    for key in ['run_directory','supervision_root','dist']:
        path=Path(ready[key])
        if not path.is_absolute() or not path.resolve().is_relative_to(ROOT):raise MVPStopped('LOCAL_WORKTREE_PATH_REQUIRED')
    request=bound(ready['request']);owner=bound(ready['owner'])
    if (ready['request']['sha256']!=REQUEST_SHA or ready['owner']['sha256']!=OWNER_SHA
            or owner['request_sha256']!=REQUEST_SHA or 'MVP_LOCAL' not in owner['approved_items']
            or owner['hospital_display'] is not False):raise MVPStopped('OWNER_MVP_LOCAL_SCOPE_REQUIRED')
    approved=request['items']['MVP_LOCAL']['request']
    if ready['task_key']!=TASK or ready['compute']!=approved['compute'] or ready['model']!=approved['model']:
        raise MVPStopped('APPROVED_FROZEN_BUDGET_CHANGED')
    prepared=bound(approved['data']['fixed_slice_input_reference'])
    delivery=bound(ready['data_delivery'])
    validate_data_v2(delivery,prepared,ready['pixel_owner_decision'])
    if ready['decision']['sha256']!=DECISION_SHA:raise MVPStopped('NEW_C1_DECISION_REQUIRED')
    if ready['supervisor_index']['sha256']!=INDEX_SHA:raise MVPStopped('FIXED_RECOVERY_INDEX_REQUIRED')
    index=bound(ready['supervisor_index']);modules=supervisor(index)
    decision=bound(ready['decision'])
    modules['execution_lock'].validate_administrative_recovery(Path(decision['queue_root']),TASK,
        ready['decision']['path'],ready['decision']['sha256'])  # Read-only; no queue admission here.
    if set(ready['source_sha256'])!=required_source_paths(ready['dist']):
        raise MVPStopped('MVP_SOURCE_CLOSURE_UNBOUND')
    for path,digest in ready['source_sha256'].items():
        if sha(path)!=digest:raise MVPStopped('MVP_SOURCE_DRIFT')
    if ready['source_sha256'].get(str(Path(__file__).resolve()))!=sha(__file__):
        raise MVPStopped('RUNNER_SOURCE_NOT_BOUND')
    if set(ready['packages'])!=set(RUNTIME_PACKAGES):raise MVPStopped('RUNTIME_PACKAGES_UNBOUND')
    for name,version in ready['packages'].items():
        if importlib.metadata.version(name)!=version:raise MVPStopped('RUNTIME_PACKAGE_DRIFT')
    generated=bound(ready['generated_protected_acceptance'])
    completion=bound(ready['generated_owned_completion'])
    if (generated.get('status')!='PASS' or generated.get('generated_model') is not True
            or generated.get('medical_forward')!=0 or generated.get('batch_invocations')!=96
            or generated.get('completed_batches')!=96 or generated.get('image_evaluations')!=2805
            or generated.get('source_sha256')!=ready['source_sha256']
            or completion.get('worker_threads_stopped') is not True
            or any(s.get('returncode') is None for s in completion.get('services',[]))
            or len(completion.get('services',[]))!=3):raise MVPStopped('CURRENT_PROTECTED_GENERATED_FLOW_NOT_ACCEPTED')
    if ready['frozen_root']!=str(Path(prepared['checkpoint_path']).parents[4]):
        raise MVPStopped('FROZEN_ROOT_IDENTITY_CHANGED')
    if ready['python']!=sys.executable or Path.cwd()!=ROOT:raise MVPStopped('PYTHON_RUNTIME_OR_CWD_CHANGED')
    if Path(ready['run_directory']).exists():raise MVPStopped('FRESH_OUTPUT_REQUIRED_NO_RETRY')
    return modules,delivery


def validate_dispatch(ready, ready_ref, dispatch, dispatch_ref):
    if (dispatch['schema']!='EPI_NEXT_MVP_LOCAL_DISPATCH_V1' or dispatch['status']!='CHIEF_EXCLUSIVE_DISPATCH'
            or dispatch['task_key']!=TASK or dispatch['readiness_sha256']!=ready_ref['sha256']
            or dispatch['data_delivery_sha256']!=ready['data_delivery']['sha256']
            or dispatch['decision_sha256']!=DECISION_SHA or dispatch['owner_approval_sha256']!=OWNER_SHA
            or dispatch['compute']!=ready['compute']):raise MVPStopped('CHIEF_EXACT_DISPATCH_REQUIRED')
    for key in ['run_directory','supervision_root','dist','frozen_root']:
        if dispatch[key]!=ready[key]:raise MVPStopped('DISPATCH_PATH_CHANGED')
    if (not re.fullmatch(r'hospital-mvp-three-legacy-cpu-[A-Za-z0-9_-]{1,64}',dispatch['job_id'])
            or dispatch['python']!=ready['python'] or dispatch['cwd']!=str(ROOT)
            or dispatch['source_sha256']!=ready['source_sha256']
            or dispatch['supervisor_index_sha256']!=INDEX_SHA
            or dispatch['argv_without_dispatch_sha']!=real_command(ready_ref,dispatch_ref)[:-2]):
        raise MVPStopped('DISPATCH_EXECUTION_IDENTITY_CHANGED')


def real_command(ready_ref, dispatch_ref, *, child=False):
    return [sys.executable,str(Path(__file__).resolve()),*(['--child'] if child else []),
            '--readiness',ready_ref['path'],'--readiness-sha',ready_ref['sha256'],
            '--dispatch',dispatch_ref['path'],'--dispatch-sha',dispatch_ref['sha256']]


def browse(run, config, records, fence, worker_done, worker_error, store, generated):
    from playwright.sync_api import sync_playwright,expect
    evidence=dict(source='GENERATED' if generated else 'LIVE_CASE', flows=[], page_errors=[], external_requests=[],
                  medical_forward=0 if generated else None, hospital_display_authorized=False)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='chrome',headless=True,args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        page=None
        try:
            context=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000})
            def policy(route):
                from urllib.parse import urlsplit
                parts=urlsplit(route.request.url)
                if parts.hostname in {'127.0.0.1','localhost'} or parts.scheme in {'blob','data'}:route.continue_()
                else:evidence['external_requests'].append(parts.netloc);route.abort()
            context.route('**/*',policy)
            label='GENERATED CT + FAKE MODEL / 非医学推理' if generated else 'LOCAL DEVELOPMENT CT / 仅本机工程验收，医院展示未获批'
            context.add_init_script("addEventListener('DOMContentLoaded',()=>{const b=document.createElement('div');b.textContent="+json.dumps(label)+";b.style='position:fixed;top:0;left:0;z-index:99999;background:#ffec8b;color:#000;padding:3px';document.body.append(b)})")
            page=context.new_page();page.set_default_timeout(15000);page.on('pageerror',lambda e:evidence['page_errors'].append(type(e).__name__))
            page.goto(config['origin']+'/mvp/cases',wait_until='domcontentloaded')
            expect(page.get_by_label('账号',exact=True)).to_be_visible()
            page.get_by_label('账号',exact=True).fill('generated_mvp');page.get_by_label('密码',exact=True).fill(config['password'])
            page.get_by_role('button',name='登录',exact=True).click()
            expect(page.get_by_role('button',name='创建匿名病例',exact=True)).to_be_visible()
            for record in records:
                if record['case_index']!=1:
                    fence.guard.begin_case('case_'+str(record['case_index']));fence.select(record)
                started=time.monotonic();fence.guard.check();worker_done.clear()
                page.goto(config['origin']+'/mvp/cases');page.get_by_role('button',name='创建匿名病例',exact=True).click()
                page.get_by_label('选择已去标识的单张 CT DICOM（最多 20 MiB）').set_input_files(record['path'])
                page.get_by_role('button',name='上传 DICOM',exact=True).click()
                expect(page.get_by_role('button',name='运行 16 / 32 / 64 px 遮挡',exact=True)).to_be_enabled()
                page.get_by_role('button',name='运行 16 / 32 / 64 px 遮挡',exact=True).click()
                link=page.get_by_role('link',name='查看已完成结果 →',exact=True)
                while not link.count():
                    fence.guard.check()
                    if worker_error or fence.failed:raise MVPStopped('WORKER_FAILED_NO_RETRY')
                    page.wait_for_timeout(100)
                fence.guard.check();job=page.url.rsplit('/',1)[-1]
                if not job.startswith('job_'):raise MVPStopped('BROWSER_JOB_NAVIGATION_NOT_CONFIRMED')
                link.click();expect(page.get_by_role('heading',name='结果工作区',exact=True)).to_be_visible()
                while not worker_done.wait(.05):
                    fence.guard.check()
                    if worker_error:raise MVPStopped('WORKER_SUBMISSION_UNRESOLVED')
                for scale in [16,32,64]:
                    fence.guard.check();page.get_by_role('button',name=f'{scale} px',exact=True).click()
                    expect(page.get_by_role('button',name=f'{scale} px',exact=True)).to_have_attribute('aria-pressed','true')
                overlay=page.get_by_label('显示叠加',exact=True)
                stored=json.loads((run/f'case-{record["case_index"]}-result.json').read_text())
                selected=next(s for s in stored['result']['scale_summaries'] if s['block_size']==64)
                if selected['candidate_status']=='valid':
                    expect(overlay).to_be_enabled();overlay.check()
                    expect(page.get_by_text('像素校验通过',exact=True)).to_be_visible()
                else:
                    expect(page.get_by_text('正响应不足',exact=True)).to_be_visible()
                    expect(overlay).to_be_disabled()
                result=page.url.rsplit('/',1)[-1];page.reload()
                expect(page.get_by_role('button',name='64 px',exact=True)).to_have_attribute('aria-pressed','true')
                store.ensure(4*1024*1024);page.screenshot(path=str(run/f'flow-{record["case_index"]}.png'),full_page=True)
                evidence['flows'].append(dict(case_index=record['case_index'],job_id=job,result_id=result,
                    seconds=time.monotonic()-started,forward_batches=32,image_evaluations=935))
                fence.guard.check();fence.guard.end_case();fence.case=None
            if evidence['page_errors'] or evidence['external_requests']:raise MVPStopped('BROWSER_ERRORS_OR_EXTERNAL_REQUEST')
        except BaseException as exc:
            try:
                store.json('browser-failure.json',dict(evidence,status='FAILED',error_type=type(exc).__name__))
                if page is not None:
                    store.ensure(4*1024*1024)
                    page.screenshot(path=str(run/'browser-failure.png'),full_page=True)
            except Exception:pass  # Keep the original failure and terminal reserve.
            raise
        finally:browser.close()
    return evidence


def execute(run, dist, records, guard, frozen_root=None, generated=False, progress=None, first_case_started=False):
    if not first_case_started:guard.begin_case('case_1')
    run.mkdir(parents=True,mode=0o700,exist_ok=False);run.chmod(0o700)
    # The unchanged setup includes one small unused generated CT fixture. Only
    # the exact three delivery records may enter this protected runner.
    config=app.setup(run)
    if generated:records=[dict(case_index=n,path=str(run/'input.dcm'),sha256=sha(run/'input.dcm')) for n in [1,2,3]]
    store=storage_class()(run,extra_roots=(guard.directory,) if hasattr(guard,'directory') else (),reserve=2097152)
    fence=CallFence(guard,store);fence.select(records[0])
    if progress is not None:progress.update(fence=fence,store=store)
    processes=[];handles=[];thread=None;agent=None;done=threading.Event();errors=[];evidence=None
    try:
        for kind in ['backend','gateway','edge']:
            handle=(run/(kind+'.log')).open('x');handles.append(handle)
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
            process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--service',kind,'--run',str(run),'--dist',str(dist)],
                cwd=ROOT,env=env,stdout=handle,stderr=handle);processes.append(process)
        import httpx
        while True:
            guard.check()
            if any(p.poll() is not None for p in processes):raise MVPStopped('OWN_SERVICE_EXITED')
            try:
                edge_ready=httpx.get(config['origin']+'/auth/session',verify=str(run/'tls.crt'),trust_env=False).status_code==401
                backend_ready=httpx.get(f'http://127.0.0.1:{config["backend"]}/api/v2/cases',trust_env=False).status_code==401
                if edge_ready and backend_ready:break
            except httpx.RequestError:pass
            time.sleep(.1)
        if generated:
            app.install_generated_worker_doubles(run)
            from hospital_mvp_protected_fake import FakeDelegate
            delegate=FakeDelegate(run,fence)
        else:
            import torch
            torch.set_num_threads(1);torch.set_num_interop_threads(1)
            from worker.inference import FrozenRunner
            delegate=FrozenRunner(frozen_root,app.MODEL_SHA,'CPU')
            model=delegate.baseline.load()
            if model.training or next(model.parameters()).device.type!='cpu':raise MVPStopped('FROZEN_CPU_EVAL_REQUIRED')
            model.register_forward_pre_hook(fence.before);model.register_forward_hook(fence.after)
            def no_backward(*_):raise MVPStopped('BACKWARD_NOT_APPROVED')
            model.register_full_backward_pre_hook(no_backward)
        from worker.config import WorkerConfig
        from worker.agent import WorkerAgent
        # Submission gets one send. Lost responses reconcile the persisted local
        # DB and asset SHA, never cause another send or another model invocation.
        class LocalAgent(WorkerAgent):
            def run_once(self):
                key,recovering=self._claim_key()
                claim=self.client.claim(self.config.worker_id,self.config.model_hash,key,0 if recovering else 1)
                self._clear_claim_key()
                if claim is None:return None
                self._validate_claim(claim)
                # No download replay and no claim resend after an unknown response.
                return self.process_claim(claim,None)
            def _submit_with_retry(self,claim,manifest,assets):
                if manifest['outcome']!='SUCCEEDED':fence.failed=True
                def reconcile(claim,manifest,assets):
                    from sqlalchemy import select
                    from sqlalchemy.orm import Session
                    from backend_v2.db.base import make_engine
                    from backend_v2.models.entities import InferenceResult,InferenceJob,JobAttempt,Asset
                    engine=make_engine(config['env']['EPILOCATE_V2_DATABASE_URL'])
                    try:
                        with Session(engine) as db:
                            import uuid
                            job=db.scalar(select(InferenceJob).where(InferenceJob.public_id==claim['job_id']))
                            attempt=db.get(JobAttempt,uuid.UUID(claim['attempt_id']))
                            result=db.scalar(select(InferenceResult).where(InferenceResult.accepted_attempt_id==uuid.UUID(claim['attempt_id'])))
                            rows=[] if result is None else db.scalars(select(Asset).where(Asset.result_id==result.id)).all()
                            receipt=verify_persisted_submission(claim,manifest,assets,job,attempt,result,rows,app.TestStore().read)
                            store.json('reconciled-'+str(len(fence.used))+'.json',dict(job_id=claim['job_id'],attempt_id=claim['attempt_id'],model_reexecuted=False))
                            return receipt
                    finally:engine.dispose()
                return submit_once(self.client,claim,manifest,assets,reconcile)
        cfg=WorkerConfig(config['worker_id'],config['origin'],config['worker_token'],app.MODEL_SHA,
            run/'unused-frozen-root',run/'worker-data',app.MODEL_SHA,tls_ca_file=run/'tls.crt',poll_seconds=.1)
        agent=LocalAgent(cfg,runner=ProtectedRunner(delegate,fence))
        agent.register();agent.heartbeat_once();agent.start_heartbeats()
        def work():
            try:
                while not agent.stop_event.is_set():
                    guard.check()
                    response=agent.run_once()
                    if response is not None:
                        if fence.failed:raise MVPStopped('FAILED_MODEL_ATTEMPT_NO_RETRY')
                        done.set()
                        if len(fence.used)==3:return
                    time.sleep(.1)
            except BaseException as exc:errors.append(type(exc).__name__);agent.stop();done.set()
        thread=threading.Thread(target=work,name='owned-protected-worker',daemon=False);thread.start()
        evidence=browse(run,config,records,fence,done,errors,store,generated)
        if errors or fence.entered!=96 or fence.completed!=96 or fence.samples!=2805:
            raise MVPStopped('INCOMPLETE_THREE_JOB_ACCOUNTING')
        from sqlalchemy import create_engine,select,func
        from sqlalchemy.orm import Session
        from backend_v2.models.entities import InferenceJob,InferenceResult,Asset,WorkerNode
        engine=create_engine(config['env']['EPILOCATE_V2_DATABASE_URL'])
        try:
            with Session(engine) as db:
                jobs=db.scalars(select(InferenceJob)).all()
                evidence['database']=dict(jobs=len(jobs),completed=sum(j.status=='COMPLETED' for j in jobs),
                    results=db.scalar(select(func.count()).select_from(InferenceResult)),
                    assets=db.scalar(select(func.count()).select_from(Asset)),
                    workers=db.scalar(select(func.count()).select_from(WorkerNode)))
                if (len(jobs)!=3 or any(j.kind!='OCCLUSION' or j.status!='COMPLETED' or j.attempt_no!=1 for j in jobs)
                        or evidence['database']['results']!=3 or evidence['database']['workers']!=1):
                    raise MVPStopped('PERSISTED_THREE_JOB_ACCOUNTING_MISMATCH')
        finally:engine.dispose()
        guard.check();store.ensure(65536)
        store.json('browser-acceptance.json',dict(evidence,status='PASS',medical_forward=0 if generated else fence.entered,
            medical_backward=0,updates=0,batch_invocations=fence.entered,completed_batches=fence.completed,
            image_evaluations=fence.samples,generated_model=generated,source='GENERATED' if generated else 'LIVE_CASE',
            source_sha256={p:sha(p) for p in sorted(required_source_paths(dist))}))
        return fence,store
    finally:
        if agent:agent.stop()
        if thread:thread.join(timeout=2)
        for process in processes:
            if process.poll() is None:process.terminate()
        for process in processes:
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)
        for handle in handles:handle.close()
        stopped=(thread is None or not thread.is_alive()) and (agent is None or agent._heartbeat_thread is None or not agent._heartbeat_thread.is_alive())
        if progress is not None:progress['owned_stopped']=stopped and all(p.poll() is not None for p in processes)
        store.json('owned-completion.json',dict(worker_threads_stopped=stopped,
            services=[dict(pid=p.pid,returncode=p.returncode) for p in processes],entered=fence.entered,
            completed=fence.completed,image_evaluations=fence.samples,failed=fence.failed,worker_errors=errors),terminal=True)
        if not stopped:raise MVPStopped('OWNED_WORKER_STILL_ALIVE_RECOVERY_UNVERIFIED')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--readiness',type=Path);parser.add_argument('--readiness-sha')
    parser.add_argument('--dispatch',type=Path);parser.add_argument('--dispatch-sha')
    parser.add_argument('--child',action='store_true');parser.add_argument('--generated',action='store_true')
    parser.add_argument('--service',choices=['backend','gateway','edge']);parser.add_argument('--run',type=Path);parser.add_argument('--dist',type=Path)
    args=parser.parse_args()
    env=isolated_environment();os.environ.clear();os.environ.update(env)
    if args.service:
        app.child(args.service,args.run.resolve(),args.dist.resolve());return
    if args.generated:
        if not args.run or not args.dist or not args.run.resolve().is_relative_to(ROOT/'frontend/.local'):
            parser.error('generated run and dist required in local worktree')
        from hospital_mvp_protected_fake import GeneratedGuard
        def interrupted(*_):raise KeyboardInterrupt()
        previous=signal.signal(signal.SIGTERM,interrupted)
        try:execute(args.run.resolve(),args.dist.resolve(),[],GeneratedGuard(),generated=True)
        finally:signal.signal(signal.SIGTERM,previous)
        return
    if not all([args.readiness,args.readiness_sha,args.dispatch,args.dispatch_sha]):
        parser.error('BLOCKED: exact readiness and chief dispatch required; no real assets or Torch opened')
    ready_ref=dict(path=str(args.readiness.resolve()),sha256=args.readiness_sha)
    ready=bound(ready_ref);modules,delivery=validate_readiness(ready)
    dispatch_ref=dict(path=str(args.dispatch.resolve()),sha256=args.dispatch_sha)
    dispatch=bound(dispatch_ref);validate_dispatch(ready,ready_ref,dispatch,dispatch_ref)
    wave=modules['wave1_supervisor']
    if not args.child:
        spec=wave.SupervisionSpec(job_id=dispatch['job_id'],task_key=TASK,device='cpu',owner='INTEGRATION',
            max_forward=96,max_backward=0,timeout_seconds=540,per_case_seconds=180)
        command=real_command(ready_ref,dispatch_ref,child=True)
        index=bound(ready['supervisor_index'])
        receipt=wave.run_supervised(spec,command,ready['supervision_root'],index['dependency_root'],index['dependency_sha256'],
            recovery_decision_path=ready['decision']['path'],recovery_decision_sha=DECISION_SHA)
        return 0 if receipt['status'] in {'SUCCESS','NO_RELIABLE_RESPONSE'} else 2
    guard=wave.ChildGuard.from_environment();fence=None;progress={}
    try:
        guard.check();guard.begin_case('case_1')
        for record in delivery['records']:
            if sha(record['path'])!=record['sha256']:raise MVPStopped('DATA_DERIVATIVE_BYTES_CHANGED')
        fence,store=execute(Path(ready['run_directory']),Path(ready['dist']),delivery['records'],guard,Path(ready['frozen_root']),progress=progress,first_case_started=True)
        guard.complete('SUCCESS',device_recovered=True,actual_forward=fence.entered,actual_backward=0)
    except BaseException as exc:
        fence=progress.get('fence')
        reason=str(exc)
        status='PARTIAL_BUDGET' if any(s in reason for s in ['DEADLINE','CALL_BUDGET','OUTPUT_BYTE_LIMIT']) else 'FAILED'
        guard.complete(status,reason=type(exc).__name__,device_recovered=progress.get('owned_stopped',False),
            actual_forward=None if fence is None else fence.entered,actual_backward=0)
        raise


if __name__=='__main__':sys.exit(main())
