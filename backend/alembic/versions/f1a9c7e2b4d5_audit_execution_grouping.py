"""Group batch-audited pages under one AuditExecution

Revision ID: f1a9c7e2b4d5
Revises: d3e7f4a1b6c2
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f1a9c7e2b4d5'
down_revision: Union[str, None] = 'd3e7f4a1b6c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_executions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conformance_level", sa.String(length=4), nullable=False, server_default="AA"),
        sa.Column("total_pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_executions_project_id", "audit_executions", ["project_id"])

    op.add_column("audit_runs", sa.Column("execution_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_audit_runs_execution_id", "audit_runs", "audit_executions", ["execution_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_audit_runs_execution_id", "audit_runs", ["execution_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_runs_execution_id", table_name="audit_runs")
    op.drop_constraint("fk_audit_runs_execution_id", "audit_runs", type_="foreignkey")
    op.drop_column("audit_runs", "execution_id")

    op.drop_index("ix_audit_executions_project_id", table_name="audit_executions")
    op.drop_table("audit_executions")
