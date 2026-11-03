"""Independent human research ROI storage after the linear K8 display head."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_r168_roi_annotations"
down_revision = "0006_formal_k8_display"
branch_labels = None
depends_on = None


def j():
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade():
    op.create_table(
        "research_annotations",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("source_image_id", sa.String(128), nullable=False),
        sa.Column("source_asset_sha256", sa.String(64), nullable=False),
        sa.Column("native_z", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("coordinate_system", sa.String(32), nullable=False),
        sa.Column("geometry_version", sa.String(64), nullable=False),
        sa.Column("geometry", j(), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("context", j(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("review_status", sa.String(32), nullable=False, server_default="UNREVIEWED"),
        sa.Column("soft_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("coordinate_system = 'RAW_PIXEL_EDGE'"),
        sa.CheckConstraint("geometry_version = 'RAW_PIXEL_EDGE_V1'"),
        sa.CheckConstraint("purpose IN ('QA_TEST','RESEARCH_DISCUSSION')"),
        sa.CheckConstraint("review_status = 'UNREVIEWED'"),
        sa.CheckConstraint("revision >= 1"),
        sa.CheckConstraint("width > 0 AND height > 0"),
    )
    op.create_index("ix_research_annotations_case_z", "research_annotations", ["case_id", "native_z", "soft_deleted"])
    op.create_table(
        "research_annotation_operations",
        sa.Column("owner_user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_id", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("annotation_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("response", j(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["annotation_id"], ["research_annotations.id"]),
        sa.PrimaryKeyConstraint("owner_user_id", "operation_id"),
    )
    op.create_table(
        "research_annotation_audits",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("annotation_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", j(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["annotation_id"], ["research_annotations.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("action IN ('CREATE','UPDATE','DELETE')"),
    )


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM research_annotations LIMIT 1)")).scalar():
        raise RuntimeError("Preserve ROI records before downgrade")
    op.drop_table("research_annotation_audits")
    op.drop_table("research_annotation_operations")
    op.drop_index("ix_research_annotations_case_z", table_name="research_annotations")
    op.drop_table("research_annotations")
