"""Initial frozen Backend v2 schema.

Revision ID: 0001_initial_schema
Revises:
"""
from alembic import op
from sqlalchemy import MetaData

from backend_v2.db.base import Base
import backend_v2.models.entities  # noqa: F401

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    frozen_metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name in {"assets", "user_credentials"}:
            continue
        copied = table.to_metadata(frozen_metadata)
        if table.name == "inference_results":
            copied._columns.remove(copied.c.metadata_json)
    frozen_metadata.create_all(bind=op.get_bind(), checkfirst=False)


def downgrade():
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=False)
