"""photo quality columns

Revision ID: 004_photo_check
Revises: 003_dept_dup
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa

revision = "004_photo_check"
down_revision = "003_dept_dup"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("issues") as batch:
        batch.add_column(sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("issue_photos") as batch:
        batch.add_column(sa.Column("dhash", sa.String(length=16), nullable=True))
        batch.create_index("ix_issue_photos_dhash", ["dhash"])


def downgrade():
    with op.batch_alter_table("issue_photos") as batch:
        batch.drop_index("ix_issue_photos_dhash")
        batch.drop_column("dhash")
    with op.batch_alter_table("issues") as batch:
        batch.drop_column("needs_review")
