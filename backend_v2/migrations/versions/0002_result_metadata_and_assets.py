"""Persist result metadata and normalize heatmap assets.

Revision ID: 0002_result_metadata_and_assets
Revises: 0001_initial_schema
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_result_metadata_and_assets"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    json_default = sa.text("'{}'::jsonb") if dialect == "postgresql" else sa.text("'{}'")
    op.add_column("inference_results", sa.Column("metadata_json", json_type, nullable=False, server_default=json_default))
    op.create_table(
        "assets",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("result_id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.String(length=128), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("layer_kind", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("coordinate_space", sa.String(length=32), nullable=False),
        sa.Column("media_type", sa.String(length=96), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["result_id"], ["inference_results.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("result_id", "asset_id"),
        sa.CheckConstraint("width > 0"),
        sa.CheckConstraint("height > 0"),
        sa.CheckConstraint("size_bytes >= 0"),
        sa.CheckConstraint("media_type IN ('image/png','application/json')"),
        sa.CheckConstraint("coordinate_space IN ('ALGORITHM_224','COMPARISON_14','RAW_PIXEL_EDGE')"),
    )
    op.create_index("ix_assets_result", "assets", ["result_id"])
    op.create_index("ix_assets_retention_until", "assets", ["retention_until"])


def downgrade():
    op.drop_index("ix_assets_retention_until", table_name="assets")
    op.drop_index("ix_assets_result", table_name="assets")
    op.drop_table("assets")
    op.drop_column("inference_results", "metadata_json")
