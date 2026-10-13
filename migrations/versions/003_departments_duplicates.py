"""departments, demo flag, supporters, duplicate marker

Revision ID: 003_dept_dup
Revises: 002_firebase
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa

revision = "003_dept_dup"
down_revision = "002_firebase"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("department", sa.String(length=32), nullable=True))
    with op.batch_alter_table("issues") as batch:
        batch.add_column(
            sa.Column("possible_duplicate", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.create_index("ix_issues_lat", ["lat"])
        batch.create_index("ix_issues_lng", ["lng"])
    op.create_table(
        "issue_supporters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("issue_id", sa.Integer(), sa.ForeignKey("issues.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("issue_id", "user_id", name="uq_issue_supporter"),
    )
    op.create_index("ix_issue_supporters_issue_id", "issue_supporters", ["issue_id"])
    op.create_index("ix_issue_supporters_user_id", "issue_supporters", ["user_id"])


def downgrade():
    op.drop_index("ix_issue_supporters_user_id", table_name="issue_supporters")
    op.drop_index("ix_issue_supporters_issue_id", table_name="issue_supporters")
    op.drop_table("issue_supporters")
    with op.batch_alter_table("issues") as batch:
        batch.drop_index("ix_issues_lng")
        batch.drop_index("ix_issues_lat")
        batch.drop_column("is_demo")
        batch.drop_column("possible_duplicate")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("department")
