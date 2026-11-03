from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend_v2.db.base import Base, utcnow
from backend_v2.models.entities import JSONType, uid


class Annotation(Base):
    __tablename__ = "research_annotations"

    id: Mapped[uuid.UUID] = uid()
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("cases.id"), index=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    source_image_id: Mapped[str] = mapped_column(String(128))
    source_asset_sha256: Mapped[str] = mapped_column(String(64))
    native_z: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    coordinate_system: Mapped[str] = mapped_column(String(32))
    geometry_version: Mapped[str] = mapped_column(String(64))
    geometry: Mapped[dict] = mapped_column(JSONType)
    label: Mapped[str] = mapped_column(String(120))
    note: Mapped[str] = mapped_column(Text, default="", server_default="")
    purpose: Mapped[str] = mapped_column(String(32))
    context: Mapped[dict] = mapped_column(JSONType, default=dict, server_default="{}")
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    review_status: Mapped[str] = mapped_column(String(32), default="UNREVIEWED", server_default="UNREVIEWED")
    soft_deleted: Mapped[bool] = mapped_column(default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default="CURRENT_TIMESTAMP")
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, server_default="CURRENT_TIMESTAMP")
    __table_args__ = (
        CheckConstraint("coordinate_system = 'RAW_PIXEL_EDGE'"),
        CheckConstraint("geometry_version = 'RAW_PIXEL_EDGE_V1'"),
        CheckConstraint("purpose IN ('QA_TEST','RESEARCH_DISCUSSION')"),
        CheckConstraint("review_status = 'UNREVIEWED'"),
        CheckConstraint("revision >= 1"),
        CheckConstraint("width > 0 AND height > 0"),
        Index("ix_research_annotations_case_z", "case_id", "native_z", "soft_deleted"),
    )


class AnnotationOperation(Base):
    __tablename__ = "research_annotation_operations"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_digest: Mapped[str] = mapped_column(String(64))
    annotation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("research_annotations.id"), nullable=True)
    response: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default="CURRENT_TIMESTAMP")


class AnnotationAudit(Base):
    __tablename__ = "research_annotation_audits"

    id: Mapped[uuid.UUID] = uid()
    annotation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("research_annotations.id"), index=True)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(16))
    revision: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default="CURRENT_TIMESTAMP")
    __table_args__ = (CheckConstraint("action IN ('CREATE','UPDATE','DELETE')"),)
