"""Add revocable, expiring user bearer credentials.

Revision ID: 0003_user_credentials
Revises: 0002_result_metadata_and_assets
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_user_credentials"
down_revision = "0002_result_metadata_and_assets"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_credentials",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=96), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_user_credentials_user_id", "user_credentials", ["user_id"])
    op.create_index("ix_user_credentials_expires_at", "user_credentials", ["expires_at"])
    op.create_index("ix_user_credentials_revoked_at", "user_credentials", ["revoked_at"])
    op.create_index("ix_user_credentials_active", "user_credentials", ["user_id", "expires_at", "revoked_at"])


def downgrade():
    op.drop_index("ix_user_credentials_active", table_name="user_credentials")
    op.drop_index("ix_user_credentials_revoked_at", table_name="user_credentials")
    op.drop_index("ix_user_credentials_expires_at", table_name="user_credentials")
    op.drop_index("ix_user_credentials_user_id", table_name="user_credentials")
    op.drop_table("user_credentials")
