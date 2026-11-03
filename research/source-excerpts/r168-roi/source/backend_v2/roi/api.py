from __future__ import annotations

import json
import math
import uuid

from fastapi import Depends, FastAPI, Header, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, select, update
from sqlalchemy.exc import IntegrityError

from backend_v2.formal_k8.models import K8Binding, K8SavedReference
from backend_v2.models.entities import Case, User
from backend_v2.services import cases
from backend_v2.services.common import digest, fail, iso, now, valid_key
from backend_v2.roi.models import Annotation, AnnotationAudit, AnnotationOperation

MAX_POINTS = 256
MAX_REQUEST_BYTES = 64 * 1024


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceBody(Strict):
    result_id: str | None = None
    source_image_id: str | None = None
    source_asset_id: str | None = None
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    native_z: int
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    coordinate_system: str
    geometry_version: str


class GeometryBody(Strict):
    type: str
    closed: bool
    points: list[list[float]]


class AnnotationBody(Strict):
    source: SourceBody
    geometry: GeometryBody
    label: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=2000)
    purpose: str
    context: dict = Field(default_factory=dict)


class AnnotationPatch(Strict):
    expected_revision: int = Field(ge=1)
    geometry: GeometryBody | None = None
    label: str | None = Field(default=None, min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=2000)
    context: dict | None = None


class DeleteBody(Strict):
    expected_revision: int = Field(ge=1)


def _segments_cross(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on(p, q, r):
        return min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])

    eps = 1e-9
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if abs(o1) <= eps and on(a, c, b): return True
    if abs(o2) <= eps and on(a, d, b): return True
    if abs(o3) <= eps and on(c, a, d): return True
    if abs(o4) <= eps and on(c, b, d): return True
    return (o1 > eps) != (o2 > eps) and (o3 > eps) != (o4 > eps)


def _validate_geometry(value: GeometryBody, width: int, height: int):
    if value.type != "POLYGON" or value.closed is not True:
        fail("ROI_POLYGON_MUST_BE_CLOSED", 422)
    points = value.points
    if not 3 <= len(points) <= MAX_POINTS:
        fail("ROI_VERTEX_LIMIT", 422)
    normalized = []
    for point in points:
        if len(point) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in point):
            fail("ROI_POINT_INVALID", 422)
        x, y = float(point[0]), float(point[1])
        if not 0 <= x <= width or not 0 <= y <= height:
            fail("ROI_POINT_OUT_OF_BOUNDS", 422)
        normalized.append([x, y])
    if len({(p[0], p[1]) for p in normalized}) != len(normalized):
        fail("ROI_DEGENERATE", 422)
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(normalized, normalized[1:] + normalized[:1]))
    if abs(area) <= 1e-9:
        fail("ROI_DEGENERATE", 422)
    for i, a in enumerate(normalized):
        b = normalized[(i + 1) % len(normalized)]
        for j in range(i + 1, len(normalized)):
            if j in (i - 1, i, i + 1) or (i == 0 and j == len(normalized) - 1):
                continue
            if _segments_cross(a, b, normalized[j], normalized[(j + 1) % len(normalized)]):
                fail("ROI_SELF_INTERSECTION", 422)
    return dict(type="POLYGON", closed=True, points=normalized)


def _source(db, user: User, case_id: str, source: SourceBody):
    case = cases.get_case(db, user.id, case_id)
    binding = db.get(K8Binding, case.id)
    if binding is None:
        fail("ROI_SOURCE_NOT_REGISTERED", 422)
    sample = binding.sample
    shape = sample["geometry"]["native_shape_ZYX"]
    source_id = source.source_image_id or source.source_asset_id
    if not source_id or source.source_image_id and source.source_asset_id and source.source_image_id != source.source_asset_id:
        fail("ROI_SOURCE_ID_REQUIRED", 422)
    if source.coordinate_system != "RAW_PIXEL_EDGE" or source.geometry_version != "RAW_PIXEL_EDGE_V1":
        fail("ROI_GEOMETRY_CONTRACT", 422)
    if source.native_z not in sample["geometry"]["indices_Z"] or source.width != shape[2] or source.height != shape[1]:
        fail("ROI_SOURCE_GEOMETRY_MISMATCH", 422)
    expected_id = f"ct-{source.native_z}"
    reference = db.scalar(select(K8SavedReference).where(K8SavedReference.case_id == case.id))
    if reference is None:
        fail("ROI_SOURCE_REFERENCE_MISSING", 503)
    expected_sha = next((a["sha256"] for a in reference.assets if a["asset_id"] == expected_id), None)
    if source_id != expected_id or source.sha256 != expected_sha:
        fail("ROI_SOURCE_ASSET_MISMATCH", 422)
    if source.result_id and source.result_id not in {reference.source_metadata.get("result_id"), str(reference.id), f"result_{reference.id.hex}"}:
        fail("ROI_RESULT_REFERENCE_MISMATCH", 422)
    return case, source_id


def _snapshot(row: Annotation):
    return dict(annotation_id=str(row.id), case_id=str(row.case_id), owner_user_id=str(row.owner_user_id),
        source_image_id=row.source_image_id, source_asset_sha256=row.source_asset_sha256, native_z=row.native_z,
        width=row.width, height=row.height, coordinate_system=row.coordinate_system, geometry_version=row.geometry_version,
        geometry=row.geometry, label=row.label, note=row.note, purpose=row.purpose, context=row.context,
        revision=row.revision, review_status=row.review_status, soft_deleted=row.soft_deleted,
        actor_user_id=str(row.actor_user_id), created_at=iso(row.created_at), updated_at=iso(row.updated_at))


def _response(row: Annotation):
    value = _snapshot(row)
    value.pop("owner_user_id", None)
    value.pop("actor_user_id", None)
    return value


def attach_routes(app: FastAPI, *, db_dependency, current_user_dependency):
    def session_db(db=Depends(db_dependency)):
        return db

    def authorized(db, user, case_id):
        return cases.get_case(db, user.id, case_id)

    @app.get("/api/v2/cases/{case_id}/annotations")
    def list_annotations(case_id: str, purpose: str | None = Query(None), include_qa: bool = False,
                         include_deleted: bool = False, native_z: int | None = None,
                         limit: int = Query(50, ge=1, le=100), db=Depends(session_db), user=Depends(current_user_dependency)):
        if purpose is not None and purpose not in {"QA_TEST", "RESEARCH_DISCUSSION"}:
            fail("ROI_PURPOSE_INVALID", 422)
        authorized(db, user, case_id)
        query = select(Annotation).where(Annotation.case_id == cases.get_case(db, user.id, case_id).id)
        if purpose: query = query.where(Annotation.purpose == purpose)
        elif not include_qa: query = query.where(Annotation.purpose != "QA_TEST")
        if not include_deleted: query = query.where(Annotation.soft_deleted.is_(False))
        if native_z is not None: query = query.where(Annotation.native_z == native_z)
        rows = db.scalars(query.order_by(Annotation.created_at, Annotation.id).limit(limit)).all()
        return dict(items=[_response(row) for row in rows], next_cursor=None)

    @app.post("/api/v2/cases/{case_id}/annotations", status_code=201)
    def create_annotation(case_id: str, body: AnnotationBody, idempotency_key: str | None = Header(None),
                          db=Depends(session_db), user=Depends(current_user_dependency)):
        key = valid_key(idempotency_key)
        raw = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        if len(raw.encode()) > MAX_REQUEST_BYTES: fail("ROI_REQUEST_TOO_LARGE", 413)
        case, source_id = _source(db, user, case_id, body.source)
        geometry = _validate_geometry(body.geometry, body.source.width, body.source.height)
        if body.purpose not in {"QA_TEST", "RESEARCH_DISCUSSION"}: fail("ROI_PURPOSE_INVALID", 422)
        request_digest = digest(dict(case_id=case_id, body=body.model_dump(mode="json")))
        existing = db.scalar(select(AnnotationOperation).where(AnnotationOperation.owner_user_id == user.id, AnnotationOperation.operation_id == key))
        if existing:
            if existing.request_digest != request_digest: fail("IDEMPOTENCY_CONFLICT", 409)
            return existing.response
        row = Annotation(case_id=case.id, owner_user_id=user.id, actor_user_id=user.id, source_image_id=source_id,
            source_asset_sha256=body.source.sha256, native_z=body.source.native_z, width=body.source.width, height=body.source.height,
            coordinate_system=body.source.coordinate_system, geometry_version=body.source.geometry_version, geometry=geometry,
            label=body.label, note=body.note, purpose=body.purpose, context=body.context, revision=1, review_status="UNREVIEWED", soft_deleted=False)
        db.add(row); db.flush(); db.add(AnnotationAudit(annotation_id=row.id, actor_user_id=user.id, action="CREATE", revision=1, snapshot=_snapshot(row)))
        response = _response(row)
        db.add(AnnotationOperation(owner_user_id=user.id, operation_id=key, request_digest=request_digest, annotation_id=row.id, response=response))
        try: db.commit()
        except IntegrityError:
            db.rollback(); existing = db.scalar(select(AnnotationOperation).where(AnnotationOperation.owner_user_id == user.id, AnnotationOperation.operation_id == key))
            if existing is None or existing.request_digest != request_digest: fail("IDEMPOTENCY_CONFLICT", 409)
            return existing.response
        return response

    @app.patch("/api/v2/cases/{case_id}/annotations/{annotation_id}")
    def update_annotation(case_id: str, annotation_id: uuid.UUID, body: AnnotationPatch,
                          db=Depends(session_db), user=Depends(current_user_dependency)):
        if len(json.dumps(body.model_dump(mode="json"), separators=(",", ":")).encode()) > MAX_REQUEST_BYTES:
            fail("ROI_REQUEST_TOO_LARGE", 413)
        case = authorized(db, user, case_id)
        values = {"updated_at": now(), "revision": Annotation.revision + 1}
        row = db.scalar(select(Annotation).where(Annotation.id == annotation_id, Annotation.case_id == case.id, Annotation.owner_user_id == user.id))
        if row is None: fail("ROI_NOT_FOUND", 404)
        if row.soft_deleted: fail("ROI_DELETED", 410)
        if body.geometry is not None: values["geometry"] = _validate_geometry(body.geometry, row.width, row.height)
        if body.label is not None: values["label"] = body.label
        if body.note is not None: values["note"] = body.note
        if body.context is not None: values["context"] = body.context
        changed = db.execute(update(Annotation).where(and_(Annotation.id == annotation_id, Annotation.owner_user_id == user.id, Annotation.revision == body.expected_revision, Annotation.soft_deleted.is_(False))).values(**values))
        if changed.rowcount != 1: db.rollback(); fail("ROI_REVISION_CONFLICT", 409)
        db.flush(); row = db.get(Annotation, annotation_id); db.add(AnnotationAudit(annotation_id=row.id, actor_user_id=user.id, action="UPDATE", revision=row.revision, snapshot=_snapshot(row))); db.commit(); return _response(row)

    @app.delete("/api/v2/cases/{case_id}/annotations/{annotation_id}")
    def delete_annotation(case_id: str, annotation_id: uuid.UUID, body: DeleteBody,
                          db=Depends(session_db), user=Depends(current_user_dependency)):
        if len(json.dumps(body.model_dump(mode="json"), separators=(",", ":")).encode()) > MAX_REQUEST_BYTES:
            fail("ROI_REQUEST_TOO_LARGE", 413)
        case = authorized(db, user, case_id)
        changed = db.execute(update(Annotation).where(and_(Annotation.id == annotation_id, Annotation.case_id == case.id, Annotation.owner_user_id == user.id, Annotation.revision == body.expected_revision, Annotation.soft_deleted.is_(False))).values(soft_deleted=True, revision=Annotation.revision + 1, updated_at=now()))
        if changed.rowcount != 1: db.rollback(); fail("ROI_REVISION_CONFLICT", 409)
        row = db.get(Annotation, annotation_id); db.add(AnnotationAudit(annotation_id=row.id, actor_user_id=user.id, action="DELETE", revision=row.revision, snapshot=_snapshot(row))); db.commit(); return _response(row)

    @app.get("/api/v2/cases/{case_id}/annotations/operations/{operation_id}")
    def annotation_operation(case_id: str, operation_id: str, db=Depends(session_db), user=Depends(current_user_dependency)):
        case = authorized(db, user, case_id)
        operation = db.scalar(select(AnnotationOperation).where(AnnotationOperation.owner_user_id == user.id, AnnotationOperation.operation_id == operation_id))
        if operation is None:
            return dict(state="NOT_FOUND", annotation=None)
        row = db.get(Annotation, operation.annotation_id) if operation.annotation_id else None
        if row is None or row.case_id != case.id:
            fail("ROI_OPERATION_CONFLICT", 409)
        return dict(state="FOUND", annotation=operation.response)

    @app.get("/api/v2/cases/{case_id}/annotations/{annotation_id}/history")
    def annotation_history(case_id: str, annotation_id: uuid.UUID, db=Depends(session_db), user=Depends(current_user_dependency)):
        case = authorized(db, user, case_id)
        row = db.scalar(select(Annotation).where(Annotation.id == annotation_id, Annotation.case_id == case.id, Annotation.owner_user_id == user.id))
        if row is None: fail("ROI_NOT_FOUND", 404)
        rows = db.scalars(select(AnnotationAudit).where(AnnotationAudit.annotation_id == row.id).order_by(AnnotationAudit.revision)).all()
        return dict(items=[dict(action=a.action, revision=a.revision, actor_user_id=str(a.actor_user_id), snapshot=a.snapshot, created_at=iso(a.created_at)) for a in rows])

