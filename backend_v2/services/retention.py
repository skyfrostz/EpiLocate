from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_v2.models.entities import Case, InferenceJob, Slice
from backend_v2.services.common import now


def expire_inputs(db: Session, store, *, at=None) -> int:
    """Delete due original DICOM objects; keep anonymous metadata and results."""
    at = at or now()
    slices = db.scalars(select(Slice).where(Slice.staging_object_key.is_not(None), Slice.staging_expires_at <= at).with_for_update(skip_locked=True)).all()
    for sl in slices:
        store.delete(sl.staging_object_key)
        sl.staging_object_key = None
        sl.staging_expires_at = None
        case = db.get(Case, sl.case_id)
        if case and case.status == "READY":
            case.status = "EXPIRED"
            case.updated_at = at
        for job in db.scalars(select(InferenceJob).where(InferenceJob.slice_id == sl.id, InferenceJob.status.in_(["CREATED", "QUEUED"]))):
            job.status = "FAILED"
            job.failure_reason = "INPUT_EXPIRED"
            job.error_message = "Input expired."
            job.finished_at = at
            job.updated_at = at
    return len(slices)
