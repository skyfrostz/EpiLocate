from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, SmallInteger, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend_v2.db.base import Base, utcnow


JSONType = JSON().with_variant(JSONB, "postgresql")


def uid():
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))


def stamp():
    return mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, server_default=text("CURRENT_TIMESTAMP"))


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = uid()
    auth_subject: Mapped[str] = mapped_column(String(255), unique=True)
    role: Mapped[str] = mapped_column(Text, default="USER", server_default="USER")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("TRUE"))
    created_at: Mapped[datetime] = stamp()
    updated_at: Mapped[datetime] = stamp()
    __table_args__ = (CheckConstraint("role IN ('USER','ADMIN')"),)


class UserCredential(Base):
    __tablename__ = "user_credentials"
    id: Mapped[uuid.UUID] = uid()
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(String(96))
    issued_at: Mapped[datetime] = stamp()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    __table_args__ = (Index("ix_user_credentials_active", "user_id", "expires_at", "revoked_at"),)


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[uuid.UUID] = uid()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    anonymous_id: Mapped[str] = mapped_column(String(48))
    created_at: Mapped[datetime] = stamp()
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    __table_args__ = (UniqueConstraint("id", "owner_user_id"), UniqueConstraint("owner_user_id", "anonymous_id"))


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[uuid.UUID] = uid()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    anonymous_id: Mapped[str] = mapped_column(String(48), unique=True)
    status: Mapped[str] = mapped_column(Text, default="CREATED", server_default="CREATED")
    created_at: Mapped[datetime] = stamp()
    updated_at: Mapped[datetime] = stamp()
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    __table_args__ = (ForeignKeyConstraint(["patient_id", "owner_user_id"], ["patients.id", "patients.owner_user_id"]), UniqueConstraint("id", "owner_user_id"), Index("ix_cases_owner_created", "owner_user_id", text("created_at DESC")), CheckConstraint("status IN ('CREATED','READY','EXPIRED','DELETING')"))


class Study(Base):
    __tablename__ = "studies"
    id: Mapped[uuid.UUID] = uid()
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("cases.id"), index=True)
    study_ref: Mapped[str] = mapped_column(String(48))
    created_at: Mapped[datetime] = stamp()
    __table_args__ = (UniqueConstraint("id", "case_id"), UniqueConstraint("case_id", "study_ref"))


class Series(Base):
    __tablename__ = "series"
    id: Mapped[uuid.UUID] = uid()
    study_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("cases.id"), index=True)
    series_ref: Mapped[str] = mapped_column(String(48))
    modality: Mapped[str] = mapped_column(Text, default="CT", server_default="CT")
    created_at: Mapped[datetime] = stamp()
    __table_args__ = (ForeignKeyConstraint(["study_id", "case_id"], ["studies.id", "studies.case_id"]), UniqueConstraint("id", "case_id"), UniqueConstraint("study_id", "series_ref"), CheckConstraint("modality = 'CT'"))


class Slice(Base):
    __tablename__ = "slices"
    id: Mapped[uuid.UUID] = uid()
    series_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("cases.id"), index=True)
    slice_ref: Mapped[str] = mapped_column(String(48))
    ordinal: Mapped[int] = mapped_column(Integer)
    width_px: Mapped[int] = mapped_column(Integer)
    height_px: Mapped[int] = mapped_column(Integer)
    source_sha256: Mapped[str] = mapped_column(String(64))
    staging_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    staging_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = stamp()
    __table_args__ = (ForeignKeyConstraint(["series_id", "case_id"], ["series.id", "series.case_id"]), UniqueConstraint("id", "case_id"), UniqueConstraint("case_id", "slice_ref"), UniqueConstraint("series_id", "ordinal"), CheckConstraint("ordinal >= 0"), CheckConstraint("width_px > 0"), CheckConstraint("height_px > 0"))


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[uuid.UUID] = uid()
    model_id: Mapped[str] = mapped_column(String(96))
    version: Mapped[str] = mapped_column(String(96))
    checkpoint_sha256: Mapped[str] = mapped_column(String(64), index=True)
    preprocessing_version: Mapped[str] = mapped_column(String(128))
    protocol_id: Mapped[str] = mapped_column(String(128))
    lifecycle_state: Mapped[str] = mapped_column(Text, default="ACTIVE", server_default="ACTIVE")
    created_at: Mapped[datetime] = stamp()
    __table_args__ = (UniqueConstraint("model_id", "version"), CheckConstraint("lifecycle_state IN ('ACTIVE','RETIRED')"), CheckConstraint("length(checkpoint_sha256) = 64"))


class WorkerNode(Base):
    __tablename__ = "worker_nodes"
    id: Mapped[uuid.UUID] = uid()
    node_id: Mapped[str] = mapped_column(String(64), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(96))
    supported_models: Mapped[list] = mapped_column(JSONType, default=list, server_default="[]")
    activity_state: Mapped[str] = mapped_column(Text, default="IDLE", server_default="IDLE")
    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = stamp()
    __table_args__ = (CheckConstraint("activity_state IN ('IDLE','RUNNING','ERROR')"),)


class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[uuid.UUID] = uid()
    public_id: Mapped[str] = mapped_column(String(48), unique=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    protocol_id: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(Text, default="DRAFT", server_default="DRAFT")
    created_at: Mapped[datetime] = stamp()
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    __table_args__ = (CheckConstraint("status IN ('DRAFT','FROZEN','ARCHIVED')"),)


class InferenceJob(Base):
    __tablename__ = "inference_jobs"
    id: Mapped[uuid.UUID] = uid()
    public_id: Mapped[str] = mapped_column(String(48), unique=True)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("cases.id"), index=True)
    slice_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    model_version_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("model_versions.id"), index=True)
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("experiments.id"), nullable=True)
    kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="CREATED", server_default="CREATED")
    request_json: Mapped[dict] = mapped_column(JSONType)
    request_digest: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    attempt_no: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    retry_count: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(SmallInteger, default=3, server_default="3")
    next_attempt_at: Mapped[datetime] = stamp()
    worker_node_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("worker_nodes.id"), nullable=True, index=True)
    lease_expire_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = stamp()
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = stamp()
    __table_args__ = (ForeignKeyConstraint(["case_id", "requested_by_user_id"], ["cases.id", "cases.owner_user_id"]), ForeignKeyConstraint(["slice_id", "case_id"], ["slices.id", "slices.case_id"]), UniqueConstraint("id", "case_id"), UniqueConstraint("requested_by_user_id", "idempotency_key"), Index("ix_jobs_queue", "status", "next_attempt_at", "created_at"), CheckConstraint("kind IN ('PREDICTION','OCCLUSION')"), CheckConstraint("status IN ('CREATED','QUEUED','RUNNING','COMPLETED','FAILED')"), CheckConstraint("attempt_no >= 0 AND attempt_no <= max_attempts"), CheckConstraint("retry_count >= 0 AND retry_count <= 2"), CheckConstraint("max_attempts >= 1 AND max_attempts <= 3"))


class JobAttempt(Base):
    __tablename__ = "job_attempts"
    id: Mapped[uuid.UUID] = uid()
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("inference_jobs.id"))
    attempt_no: Mapped[int] = mapped_column(SmallInteger)
    worker_node_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("worker_nodes.id"), index=True)
    claim_key: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    claim_request_digest: Mapped[str] = mapped_column(String(64))
    lease_token_hash: Mapped[str] = mapped_column(String(64))
    leased_at: Mapped[datetime] = stamp()
    lease_expire_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str] = mapped_column(Text, default="CLAIMED", server_default="CLAIMED")
    failure_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submission_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    accepted_response_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    __table_args__ = (UniqueConstraint("job_id", "attempt_no"), UniqueConstraint("worker_node_id", "claim_key"), Index("ix_attempt_lease", "outcome", "lease_expire_time"), Index("uq_attempt_claimed_job", "job_id", unique=True, postgresql_where=text("outcome = 'CLAIMED'"), sqlite_where=text("outcome = 'CLAIMED'")), CheckConstraint("outcome IN ('CLAIMED','SUCCEEDED','FAILED','EXPIRED')"))


class InferenceResult(Base):
    __tablename__ = "inference_results"
    id: Mapped[uuid.UUID] = uid()
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), unique=True)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("cases.id"), index=True)
    accepted_attempt_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("job_attempts.id"), unique=True)
    model_version_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("model_versions.id"))
    source: Mapped[str] = mapped_column(Text, default="LIVE_CASE", server_default="LIVE_CASE")
    result_json: Mapped[dict] = mapped_column(JSONType)
    metadata_json: Mapped[dict] = mapped_column(JSONType, default=dict, server_default="{}")
    asset_manifest: Mapped[list] = mapped_column(JSONType, default=list, server_default="[]")
    created_at: Mapped[datetime] = stamp()
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    __table_args__ = (ForeignKeyConstraint(["job_id", "case_id"], ["inference_jobs.id", "inference_jobs.case_id"]), CheckConstraint("source = 'LIVE_CASE'"))


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[uuid.UUID] = uid()
    result_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("inference_results.id"))
    asset_id: Mapped[str] = mapped_column(String(128))
    object_key: Mapped[str] = mapped_column(Text)
    layer_kind: Mapped[str] = mapped_column(String(64))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    coordinate_space: Mapped[str] = mapped_column(String(32))
    media_type: Mapped[str] = mapped_column(String(96))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = stamp()
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    __table_args__ = (UniqueConstraint("result_id", "asset_id"), Index("ix_assets_result", "result_id"), CheckConstraint("width > 0"), CheckConstraint("height > 0"), CheckConstraint("size_bytes >= 0"), CheckConstraint("media_type IN ('image/png','application/json')"), CheckConstraint("coordinate_space IN ('ALGORITHM_224','COMPARISON_14','RAW_PIXEL_EDGE')"))


class ApiIdempotency(Base):
    __tablename__ = "api_idempotency"
    id: Mapped[uuid.UUID] = uid()
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    scope: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_digest: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(Text, default="PENDING", server_default="PENDING")
    response_status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    response_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = stamp()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    __table_args__ = (UniqueConstraint("actor_user_id", "scope", "idempotency_key"), CheckConstraint("scope IN ('CASE_CREATE','CASE_UPLOAD')"), CheckConstraint("state IN ('PENDING','COMPLETE')"))
