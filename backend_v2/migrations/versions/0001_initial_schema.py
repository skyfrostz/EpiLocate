"""Initial frozen Backend v2 schema.

Revision ID: 0001_initial_schema
Revises:
"""
from alembic import op

from backend_v2.db.base import Base
import backend_v2.models.entities  # noqa: F401

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=False)


def downgrade():
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=False)
