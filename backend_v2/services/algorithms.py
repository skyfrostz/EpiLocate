"""Opt-in application extension. Reuses existing jobs/leases/storage, no scheduler."""
from datetime import datetime
from types import SimpleNamespace
from sqlalchemy import select
from epilocate_next.contracts import ApplicationRequest, HandlerResult, validate_output
from backend_v2.models.entities import Case, InferenceJob, ModelVersion, Series, Slice, Study
from backend_v2.services.common import aware, digest, fail, now, public_id, valid_key


def create_algorithm_job(db, user, request, key, resolver=None):
    valid_key(key)
    req=ApplicationRequest.model_validate(request);i=req.input
    case=db.scalar(select(Case).where(Case.anonymous_id==i.case_id,Case.owner_user_id==user.id,Case.status=='READY'))
    if case is None:fail('CASE_NOT_FOUND',404)
    sl=db.scalar(select(Slice).where(Slice.slice_ref==i.slice_id,Slice.case_id==case.id))
    series=db.get(Series,sl.series_id) if sl else None;study=db.get(Study,series.study_id) if series else None
    if not sl or not series or not study or series.series_ref!=i.series_id or study.study_ref!=i.study_id:fail('ALGORITHM_INPUT_IDENTITY_MISMATCH')
    if sl.source_sha256!=i.display_sha256 or (sl.height_px,sl.width_px)!=(i.native_shape_zyx[1],i.native_shape_zyx[2]):fail('ALGORITHM_DISPLAY_BINDING_MISMATCH')
    canonical=req.model_dump(mode='json');request_digest=digest(canonical)
    # One bound application request is one computation, including after refresh
    # or a lost create response. A fresh client UUID never grants another run.
    key='algorithm-'+request_digest
    old=db.scalar(select(InferenceJob).where(InferenceJob.requested_by_user_id==user.id,InferenceJob.idempotency_key==key))
    if old:
        if old.kind!='ALGORITHM' or old.request_digest!=request_digest:fail('IDEMPOTENCY_CONFLICT',409)
        return old
    models=db.scalars(select(ModelVersion).where(ModelVersion.model_id==req.model.model_id,ModelVersion.lifecycle_state=='ACTIVE')).all()
    if len(models)!=1:fail('MODEL_UNAVAILABLE',422)
    model=models[0]
    if (model.checkpoint_sha256,model.preprocessing_version,model.protocol_id)!=(req.model.checkpoint_sha256,req.model.preprocessing_version,req.model.protocol_id):fail('MODEL_HASH_MISMATCH')
    if resolver is None:
        if i.scope!='SINGLE_SLICE' or i.display_kind!='DICOM':fail('VOLUME_INPUT_HANDOFF_REQUIRED',422)
        binding=dict(object_key=sl.staging_object_key,sha256=sl.source_sha256,expires_at=sl.staging_expires_at)
    else:binding=resolver(db,user,req,sl)
    expiry=binding['expires_at']
    if isinstance(expiry,str):expiry=datetime.fromisoformat(expiry)
    if not binding.get('object_key') or binding['sha256']!=i.input_sha256 or not expiry or aware(expiry)<=now():fail('ALGORITHM_INPUT_UNAVAILABLE',410)
    params=dict(kind='ALGORITHM',case_id=i.case_id,slice_id=i.slice_id,model_id=model.model_id,protocol_id=model.protocol_id,scales=[],application=canonical,algorithm_input=dict(object_key=binding['object_key'],sha256=binding['sha256'],expires_at=aware(expiry).isoformat()))
    job=InferenceJob(public_id=public_id('job'),case_id=case.id,slice_id=sl.id,requested_by_user_id=user.id,model_version_id=model.id,kind='ALGORITHM',status='CREATED',request_json=params,request_digest=request_digest,idempotency_key=key,max_attempts=1)
    db.add(job);db.flush();return job


def input_available(job):
    try:
        binding=job.request_json['algorithm_input']
        return bool(binding['object_key']) and aware(datetime.fromisoformat(binding['expires_at']))>now()
    except (KeyError,TypeError,ValueError):return False


def input_proxy(job):
    b=job.request_json['algorithm_input']
    return SimpleNamespace(staging_object_key=b['object_key'],source_sha256=b['sha256'],staging_expires_at=datetime.fromisoformat(b['expires_at']))


def validate_wire_result(result, job, model):
    req=ApplicationRequest.model_validate(job.request_json['application'])
    source={'LIVE':'LIVE_CASE','PRECOMPUTED':'PRECOMPUTED','SYNTHETIC':'SYNTHETIC'}[req.execution_mode]
    expected=dict(contract_version='next-1',source=source,case_id=req.input.case_id,slice_id=req.input.slice_id,kind='ALGORITHM',model_id=model.model_id,model_version=model.checkpoint_sha256,preprocessing_version=model.preprocessing_version,protocol_id=model.protocol_id)
    if set(result)!=set(expected)|{'application','application_request'} or any(result.get(k)!=v for k,v in expected.items()) or result['application_request']!=req.model_dump(mode='json'):raise ValueError('ALGORITHM_RESULT_IDENTITY_MISMATCH')
    output=validate_output(req,HandlerResult.model_validate(result['application']))
    return output
