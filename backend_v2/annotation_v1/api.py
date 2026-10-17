"""Owner-authorized polygon revisions on an explicitly registered native CT plane.

This additive app never mounts Job/Worker/upload routes. The existing session
Gateway forwards cases/... routes without changing its frozen authentication.
"""
from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import ForeignKey, Integer, JSON, String, UniqueConstraint, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend_v2.api.app import current_user, get_db, http_error, validation_error
from backend_v2.db.base import Base
from backend_v2.models.entities import Case, Slice, User
from backend_v2.services.common import aware, fail, now

MAX_ANNOTATIONS = 20
MAX_REVISIONS = 32


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class ImagePlane(Base):
    __tablename__ = 'annotation_image_planes_v1'
    slice_pk: Mapped[uuid.UUID] = mapped_column(ForeignKey('slices.id'), primary_key=True)
    binding: Mapped[dict] = mapped_column(JSON)


class Head(Base):
    __tablename__ = 'annotation_heads_v1'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_pk: Mapped[uuid.UUID] = mapped_column(ForeignKey('cases.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)


class Revision(Base):
    __tablename__ = 'annotation_revisions_v1'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    annotation_id: Mapped[str] = mapped_column(ForeignKey('annotation_heads_v1.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    operation_id: Mapped[str] = mapped_column(String(36), unique=True)
    request_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('annotation_id', 'version'),)


class Event(Base):
    __tablename__ = 'annotation_events_v1'
    revision_id: Mapped[str] = mapped_column(ForeignKey('annotation_revisions_v1.id'), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


def install_schema(engine):
    """Explicit new-table installation only; never invoked on old demo storage."""
    if engine.dialect.name != 'sqlite':
        raise ValueError('ANNOTATION_V1_SQLITE_ONLY_NOT_PRODUCTION_MIGRATION')
    for table in (ImagePlane.__table__, Head.__table__, Revision.__table__, Event.__table__):
        table.create(engine, checkfirst=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS annotation_case_quota BEFORE INSERT ON annotation_heads_v1 WHEN (SELECT count(*) FROM annotation_heads_v1 WHERE case_pk=NEW.case_pk)>={MAX_ANNOTATIONS} BEGIN SELECT RAISE(ABORT, 'ANNOTATION_CASE_QUOTA'); END")
        conn.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS annotation_revision_quota BEFORE INSERT ON annotation_revisions_v1 WHEN (SELECT count(*) FROM annotation_revisions_v1 WHERE annotation_id=NEW.annotation_id)>={MAX_REVISIONS} BEGIN SELECT RAISE(ABORT, 'ANNOTATION_REVISION_QUOTA'); END")
        for table in (ImagePlane.__tablename__, Revision.__tablename__, Event.__tablename__):
            for verb in ('UPDATE', 'DELETE'):
                conn.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS {table}_{verb.lower()} BEFORE {verb} ON {table} BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_ANNOTATION_RECORD'); END")


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class Binding(Strict):
    case_id: str = Field(min_length=1, max_length=48)
    slice_id: str = Field(min_length=1, max_length=48)
    study_uid: str = Field(min_length=1, max_length=64)
    series_uid: str = Field(min_length=1, max_length=64)
    sop_instance_uid: str = Field(min_length=1, max_length=64)
    frame_of_reference_uid: str = Field(min_length=1, max_length=64)
    ct_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    geometry_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    geometry_version: Literal['DICOM_NATIVE_CENTRES_LPS_V1']


class Mutation(Strict):
    annotation_id: str = Field(pattern='^[0-9a-f-]{36}$')
    operation_id: str = Field(pattern='^[0-9a-f-]{36}$')
    expected_version: int = Field(ge=0)
    binding: Binding
    vertices: list[list[float]] = Field(min_length=3, max_length=256)
    category: Literal['SUSPECTED_INFECTION', 'OTHER']
    state: Literal['ACTIVE', 'WITHDRAWN']
    note: str = Field(default='', max_length=1000)


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def intersects(a, b, c, d):
    def on(p, q, r):
        return abs(cross(p, q, r)) < 1e-8 and all(min(p[i], q[i])-1e-8 <= r[i] <= max(p[i], q[i])+1e-8 for i in (0, 1))
    return (cross(a,b,c)*cross(a,b,d)<0 and cross(c,d,a)*cross(c,d,b)<0) or any((on(a,b,c),on(a,b,d),on(c,d,a),on(c,d,b)))


def world(point, geometry):
    x, y = point
    return [geometry['ipp'][i] + x*geometry['spacing'][1]*geometry['iop'][i] + y*geometry['spacing'][0]*geometry['iop'][i+3] for i in range(3)]


def validate_polygon(vertices, geometry):
    width, height = geometry['width'], geometry['height']
    if any(len(p)!=2 or any(not math.isfinite(v) for v in p) for p in vertices):
        fail('FINITE_NATIVE_XY_REQUIRED')
    if any(not (0 <= p[0] <= width-1 and 0 <= p[1] <= height-1) for p in vertices):
        fail('NATIVE_PIXEL_CENTRE_OUT_OF_BOUNDS')
    if len({tuple(p) for p in vertices}) != len(vertices):
        fail('DUPLICATE_VERTICES')
    n = len(vertices)
    for i in range(n):
        for j in range(i+1, n):
            if j==i+1 or (i==0 and j==n-1):continue
            if intersects(vertices[i],vertices[(i+1)%n],vertices[j],vertices[(j+1)%n]):
                fail('SELF_INTERSECTING_POLYGON')
    area = abs(sum(vertices[i][0]*vertices[(i+1)%n][1]-vertices[(i+1)%n][0]*vertices[i][1] for i in range(n)))/2
    if area < .5:fail('DEGENERATE_POLYGON')
    return [world(p, geometry) for p in vertices]


def owned_plane(db, user, case_id):
    case = db.scalar(select(Case).where(Case.anonymous_id==case_id))
    if case is None:fail('CASE_NOT_FOUND',404)
    if case.owner_user_id != user.id:fail('ANNOTATION_FORBIDDEN',403)
    if case.status != 'READY':fail('CASE_NOT_READY',409)
    sl = db.scalar(select(Slice).where(Slice.case_id==case.id))
    if sl is None:fail('SLICE_NOT_FOUND',404)
    plane = db.get(ImagePlane, sl.id)
    if plane is None:fail('NATIVE_PLANE_NOT_REGISTERED',409)
    b = plane.binding
    if (b['case_id'] != case_id or b['slice_id'] != sl.slice_ref or b['ct_sha256'] != sl.source_sha256
            or b['geometry_sha256'] != digest(b['geometry'])
            or b['geometry']['width'] != sl.width_px or b['geometry']['height'] != sl.height_px):
        fail('AUTHORITATIVE_CT_BINDING_DRIFT',409)
    if not sl.staging_expires_at or aware(sl.staging_expires_at)<=now():fail('INPUT_EXPIRED',410)
    return case, sl, b


def create_app(factory, storage):
    app = FastAPI(title='EpiLocate single-slice annotation workspace v1',docs_url=None,redoc_url=None,openapi_url=None)
    def db_session():
        with factory() as db:
            try:yield db
            finally:db.rollback()
    app.dependency_overrides[get_db] = db_session
    from fastapi import HTTPException
    app.add_exception_handler(HTTPException,http_error)
    app.add_exception_handler(RequestValidationError,validation_error)

    @app.middleware('http')
    async def headers(request: Request, call_next):
        if request.method=='POST':
            declared=request.headers.get('content-length','')
            if not declared.isdigit() or request.headers.get('transfer-encoding'):
                return JSONResponse({'code':'BOUNDED_CONTENT_LENGTH_REQUIRED'},status_code=411)
            if int(declared)>131072:
                return JSONResponse({'code':'ANNOTATION_REQUEST_TOO_LARGE'},status_code=413)
            chunks=[];size=0
            async for chunk in request.stream():
                size+=len(chunk)
                if size>131072:
                    return JSONResponse({'code':'ANNOTATION_REQUEST_TOO_LARGE'},status_code=413)
                chunks.append(chunk)
            if size!=int(declared):
                return JSONResponse({'code':'CONTENT_LENGTH_MISMATCH'},status_code=400)
            # Starlette's cached Request forwards this exact bounded body downstream.
            request._body=b''.join(chunks)
        response=await call_next(request)
        response.headers['Cache-Control']='private,no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response

    @app.get('/api/v2/cases')
    def cases(db: Session=Depends(get_db), user: User=Depends(current_user)):
        return {'items':[{'case_id':c.anonymous_id,'status':c.status} for c in db.scalars(select(Case).where(Case.owner_user_id==user.id))]}

    @app.get('/api/v2/cases/{case_id}/annotation-context')
    def context(case_id: str, db: Session=Depends(get_db), user: User=Depends(current_user)):
        _,_,binding=owned_plane(db,user,case_id)
        return {'binding':binding,'actor':user.auth_subject,'can_edit':True,'scope':'SYNTHETIC_ONLY_NOT_TRAINING_GT'}

    @app.get('/api/v2/cases/{case_id}/dicom')
    def dicom(case_id: str, db: Session=Depends(get_db), user: User=Depends(current_user)):
        _,sl,b=owned_plane(db,user,case_id)
        raw,media=storage.read(sl.staging_object_key)
        if media!='application/dicom' or hashlib.sha256(raw).hexdigest()!=b['ct_sha256']:fail('CT_INTEGRITY_FAILURE',503)
        return Response(raw,media_type=media)

    @app.get('/api/v2/cases/{case_id}/annotations')
    def latest(case_id: str, db: Session=Depends(get_db), user: User=Depends(current_user)):
        case,_,_=owned_plane(db,user,case_id)
        heads=db.scalars(select(Head).where(Head.case_pk==case.id).limit(MAX_ANNOTATIONS)).all()
        return {'items':[db.scalar(select(Revision).where(Revision.annotation_id==h.id,Revision.version==h.version)).payload for h in heads]}

    @app.get('/api/v2/cases/{case_id}/annotations/{annotation_id}/history')
    def history(case_id: str, annotation_id: str, db: Session=Depends(get_db), user: User=Depends(current_user)):
        case,_,_=owned_plane(db,user,case_id);head=db.get(Head,annotation_id)
        if not head or head.case_pk!=case.id:fail('ANNOTATION_NOT_FOUND',404)
        revisions=db.scalars(select(Revision).where(Revision.annotation_id==head.id).order_by(Revision.version).limit(MAX_REVISIONS)).all()
        return {'revisions':[r.payload for r in revisions],'events':[db.get(Event,r.id).payload for r in revisions]}

    @app.get('/api/v2/cases/{case_id}/annotation-operations/{operation_id}')
    def operation(case_id: str, operation_id: str, db: Session=Depends(get_db), user: User=Depends(current_user)):
        case,_,_=owned_plane(db,user,case_id);r=db.scalar(select(Revision).where(Revision.operation_id==operation_id))
        if r is None or db.get(Head,r.annotation_id).case_pk!=case.id:fail('OPERATION_NOT_FOUND',404)
        return r.payload

    @app.post('/api/v2/cases/{case_id}/annotations')
    def save(case_id: str, body: Mutation, db: Session=Depends(get_db), user: User=Depends(current_user)):
        case,_,b=owned_plane(db,user,case_id)
        try:uuid.UUID(body.annotation_id);uuid.UUID(body.operation_id)
        except ValueError:fail('VALID_ANNOTATION_OPERATION_UUID_REQUIRED')
        binding=body.binding.model_dump()
        if binding != {k:b[k] for k in binding}:fail('CT_IDENTITY_OR_GEOMETRY_MISMATCH',409)
        vertices=validate_polygon(body.vertices,b['geometry'])
        request_sha=digest(body.model_dump())
        replay=db.scalar(select(Revision).where(Revision.operation_id==body.operation_id))
        if replay:
            if replay.request_sha256!=request_sha or replay.payload['author_id']!=str(user.id):fail('OPERATION_REUSE_CONFLICT',409)
            return replay.payload
        head=db.get(Head,body.annotation_id);previous=None
        if head is None:
            if body.expected_version!=0 or body.state!='ACTIVE':fail('VERSION_CONFLICT',409)
            head=Head(id=body.annotation_id,case_pk=case.id,version=1);db.add(head)
            action='CREATE'
        else:
            if head.case_pk!=case.id:fail('ANNOTATION_FORBIDDEN',403)
            previous=db.scalar(select(Revision).where(Revision.annotation_id==head.id,Revision.version==head.version)).payload
            if head.version!=body.expected_version:fail('VERSION_CONFLICT',409)
            updated=db.execute(update(Head).where(Head.id==head.id,Head.version==body.expected_version).values(version=body.expected_version+1))
            if updated.rowcount!=1:fail('VERSION_CONFLICT',409)
            action='WITHDRAW' if body.state=='WITHDRAWN' else ('RESTORE' if previous['state']=='WITHDRAWN' else 'UPDATE')
        timestamp=datetime.now(timezone.utc).isoformat()
        payload=dict(annotation_id=body.annotation_id,operation_id=body.operation_id,version=body.expected_version+1,
                     binding=binding,vertices=body.vertices,world_vertices_lps_mm=vertices,category=body.category,
                     state=body.state,note=body.note,author_id=str(user.id),author=user.auth_subject,
                     created_at=previous['created_at'] if previous else timestamp,updated_at=timestamp,
                     review_status='UNREVIEWED',training_gt_eligible=False,
                     previous_revision_sha256=previous['revision_sha256'] if previous else None)
        payload['revision_sha256']=digest(payload);rid=str(uuid.uuid4())
        db.add(Revision(id=rid,annotation_id=head.id,version=payload['version'],operation_id=body.operation_id,request_sha256=request_sha,payload=payload))
        db.add(Event(revision_id=rid,payload=dict(revision_id=rid,annotation_id=head.id,version=payload['version'],action=action,actor_id=str(user.id),actor=user.auth_subject,time=timestamp,revision_sha256=payload['revision_sha256'])))
        try:db.commit()
        except IntegrityError as exc:
            db.rollback()
            if 'ANNOTATION_CASE_QUOTA' in str(exc) or 'ANNOTATION_REVISION_QUOTA' in str(exc):
                fail('ANNOTATION_QUOTA_REACHED',409)
            fail('VERSION_OR_OPERATION_CONFLICT',409)
        return payload
    return app
