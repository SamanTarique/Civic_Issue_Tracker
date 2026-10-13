"""firebase uid and nullable password

Revision ID: 002_firebase
Revises: 001_initial
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa

revision = "002_firebase"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.alter_column("password_hash", existing_type=sa.String(length=255), nullable=True)
        batch.add_column(sa.Column("firebase_uid", sa.String(length=128), nullable=True))
        batch.add_column(
            sa.Column("auth_provider", sa.String(length=32), nullable=False, server_default="password")
        )
        batch.create_index("ix_users_firebase_uid", ["firebase_uid"], unique=True)


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_firebase_uid")
        batch.drop_column("auth_provider")
        batch.drop_column("firebase_uid")
        batch.alter_column("password_hash", existing_type=sa.String(length=255), nullable=False)
