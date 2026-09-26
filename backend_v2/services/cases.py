from __future__ import annotations

import hashlib
import io
import os
from datetime import timedelta

import pydicom
from pydicom.uid import CTImageStorage
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_v2.models.entities import ApiIdempotency, Case, Patient, Series, Slice, Study
from backend_v2.services.common import aware, digest, fail, iso, now, public_id, valid_key


def create_case(db: Session, user_id, patient_public_id: str | None, key: str):
    valid_key(key)
    request_digest = digest({"patient_id": patient_public_id})
    old = db.scalar(select(ApiIdempotency).where(ApiIdempotency.actor_user_id == user_id, ApiIdempotency.scope == "CASE_CREATE", ApiIdempotency.idempotency_key == key))
    if old:
        if old.request_digest != request_digest or old.state != "COMPLETE":
            fail("IDEMPOTENCY_CONFLICT", 409)
        return old.response_json
    reservation = ApiIdempotency(actor_user_id=user_id, scope="CASE_CREATE", idempotency_key=key, request_digest=request_digest, state="PENDING")
    db.add(reservation)
    db.flush()
    patient = db.scalar(select(Patient).where(Patient.owner_user_id == user_id, Patient.anonymous_id == patient_public_id)) if patient_public_id else None
    if patient_public_id and not patient:
        fail("PATIENT_NOT_FOUND", 404)
    if patient is None:
        patient = Patient(owner_user_id=user_id, anonymous_id=public_id("pat"))
        db.add(patient); db.flush()
    case = Case(owner_user_id=user_id, patient_id=patient.id, anonymous_id=public_id("case"))
    db.add(case); db.flush()
    response = {"case_id": case.anonymous_id, "patient_id": patient.anonymous_id, "status": "CREATED", "created_at": iso(case.created_at)}
    reservation.state = "COMPLETE"
    reservation.response_status = 201
    reservation.response_json = response
    return response


def get_case(db: Session, user_id, case_id: str) -> Case:
    case = db.scalar(select(Case).where(Case.anonymous_id == case_id, Case.owner_user_id == user_id, Case.status != "DELETING"))
    if case is None:
        fail("CASE_NOT_FOUND", 404)
    return case


def case_payload(db: Session, case: Case):
    patient = db.get(Patient, case.patient_id)
    studies = []
    expiry = None
    for study in db.scalars(select(Study).where(Study.case_id == case.id).order_by(Study.created_at)):
        items = []
        for series in db.scalars(select(Series).where(Series.study_id == study.id).order_by(Series.created_at)):
            slices = []
            for sl in db.scalars(select(Slice).where(Slice.series_id == series.id).order_by(Slice.ordinal)):
                slices.append({"slice_id": sl.slice_ref, "ordinal": sl.ordinal, "width_px": sl.width_px, "height_px": sl.height_px})
                expiry = iso(sl.staging_expires_at) if sl.staging_expires_at else expiry
            items.append({"series_id": series.series_ref, "slices": slices})
        studies.append({"study_id": study.study_ref, "series": items})
    return {"case_id": case.anonymous_id, "patient_id": patient.anonymous_id, "status": case.status, "created_at": iso(case.created_at), "input_expires_at": expiry, "studies": studies}


def validate_single_ct(raw: bytes):
    if len(raw) > 20 * 1024 * 1024:
        fail("INPUT_TOO_LARGE", 413)
    try:
        ds = pydicom.dcmread(io.BytesIO(raw), stop_before_pixels=True, force=False)
        if str(ds.get("SOPClassUID", "")) != str(CTImageStorage) or str(ds.get("Modality", "")) != "CT":
            fail("UNSUPPORTED_DICOM", 415)
        width, height = int(ds.Columns), int(ds.Rows)
        if not 1 <= width <= 4096 or not 1 <= height <= 4096 or width * height > 16_777_216:
            fail("INVALID_DICOM_DIMENSIONS", 422)
        forbidden = ["PatientName", "PatientID", "PatientBirthDate", "AccessionNumber", "InstitutionName", "ReferringPhysicianName", "StudyDate", "SeriesDate", "AcquisitionDate", "PatientAddress", "StudyDescription", "SeriesDescription", "ImageComments"]
        if any(str(ds.get(name, "")).strip() for name in forbidden) or any(e.tag.is_private for e in ds.iterall()) or str(ds.get("BurnedInAnnotation", "NO")) == "YES":
            fail("DICOM_NOT_DEIDENTIFIED", 422)
        return width, height
    except (AttributeError, ValueError, pydicom.errors.InvalidDicomError):
        fail("INVALID_DICOM", 422)


def upload_case(db: Session, store, user_id, case_id: str, raw: bytes, key: str):
    valid_key(key)
    case = db.scalar(select(Case).where(Case.anonymous_id == case_id, Case.owner_user_id == user_id, Case.status != "DELETING").with_for_update())
    if not case:
        fail("CASE_NOT_FOUND", 404)
    request_digest = digest({"case_id": case_id, "sha256": hashlib.sha256(raw).hexdigest()})
    old = db.scalar(select(ApiIdempotency).where(ApiIdempotency.actor_user_id == user_id, ApiIdempotency.scope == "CASE_UPLOAD", ApiIdempotency.idempotency_key == key))
    if old:
        if old.request_digest != request_digest or old.state != "COMPLETE":
            fail("IDEMPOTENCY_CONFLICT", 409)
        return old.response_json
    if db.scalar(select(Slice).where(Slice.case_id == case.id)):
        fail("CASE_ALREADY_HAS_INPUT", 409)
    width, height = validate_single_ct(raw)
    days = int(os.environ.get("DICOM_RETENTION_DAYS", "7"))
    if not 1 <= days <= 365:
        fail("INVALID_RETENTION_CONFIG", 503)
    object_key = store.put(raw, "application/dicom", "input")
    try:
        study = Study(case_id=case.id, study_ref=public_id("study")); db.add(study); db.flush()
        series = Series(study_id=study.id, case_id=case.id, series_ref=public_id("series")); db.add(series); db.flush()
        sl = Slice(series_id=series.id, case_id=case.id, slice_ref=public_id("slice"), ordinal=0, width_px=width, height_px=height, source_sha256=hashlib.sha256(raw).hexdigest(), staging_object_key=object_key, staging_expires_at=now() + timedelta(days=days))
        db.add(sl); db.flush()
        case.status = "READY"; case.updated_at = now()
        response = {"case_id": case_id, "study_id": study.study_ref, "series_id": series.series_ref, "slice_id": sl.slice_ref, "status": "READY", "input_expires_at": iso(sl.staging_expires_at)}
        db.add(ApiIdempotency(actor_user_id=user_id, scope="CASE_UPLOAD", idempotency_key=key, request_digest=request_digest, state="COMPLETE", response_status=201, response_json=response))
        return response
    except Exception:
        store.delete(object_key)
        raise
