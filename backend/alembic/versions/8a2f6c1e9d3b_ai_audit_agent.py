"""AI audit agent: audit_runs, plan_steps, step_results

Revision ID: 8a2f6c1e9d3b
Revises: 57d1420d2d4b
Create Date: 2026-07-29 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8a2f6c1e9d3b'
down_revision: Union[str, None] = '57d1420d2d4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("crawled_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("conformance_level", sa.String(length=4), nullable=False, server_default="AA"),
        sa.Column("perception", sa.JSON(), nullable=True),
        sa.Column("reflection_summary", sa.Text(), nullable=True),
        sa.Column("reflection_data", sa.JSON(), nullable=True),
        sa.Column("total_steps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_steps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_audit_runs_project_id", "audit_runs", ["project_id"])
    op.create_index("ix_audit_runs_page_id", "audit_runs", ["page_id"])

    op.create_table(
        "plan_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("audit_run_id", sa.Integer(), sa.ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="Accessibility check"),
        sa.Column("wcag_criterion", sa.String(length=32), nullable=False),
        sa.Column("level", sa.String(length=4), nullable=False, server_default="AA"),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=True),
        sa.Column("target_element", sa.JSON(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("reasoning", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_plan_steps_audit_run_id", "plan_steps", ["audit_run_id"])

    op.create_table(
        "step_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_step_id", sa.Integer(), sa.ForeignKey("plan_steps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("is_follow_up", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("follow_up_of_id", sa.Integer(), sa.ForeignKey("step_results.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_step_results_plan_step_id", "step_results", ["plan_step_id"])


def downgrade() -> None:
    op.drop_index("ix_step_results_plan_step_id", table_name="step_results")
    op.drop_table("step_results")

    op.drop_index("ix_plan_steps_audit_run_id", table_name="plan_steps")
    op.drop_table("plan_steps")

    op.drop_index("ix_audit_runs_page_id", table_name="audit_runs")
    op.drop_index("ix_audit_runs_project_id", table_name="audit_runs")
    op.drop_table("audit_runs")
