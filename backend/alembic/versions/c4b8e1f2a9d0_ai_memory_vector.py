"""AI memory: ai_memory, ai_memory_updates (requires pgvector extension)

Revision ID: c4b8e1f2a9d0
Revises: 8a2f6c1e9d3b
Create Date: 2026-07-29 20:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from app.config import settings

# revision identifiers, used by Alembic.
revision: str = 'c4b8e1f2a9d0'
down_revision: Union[str, None] = '8a2f6c1e9d3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = settings.AI_EMBEDDING_DIMENSIONS


def upgrade() -> None:
    # Requires the pgvector extension to be installed on the Postgres server.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "ai_memory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("page_type_signature", sa.String(length=128), nullable=False),
        sa.Column("wcag_rule_id", sa.String(length=64), nullable=False),
        sa.Column("pattern_description", sa.Text(), nullable=False),
        sa.Column("outcome_pattern", sa.String(length=20), nullable=False, server_default="mixed"),
        sa.Column("confidence_weight", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("times_seen", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_contradicted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("page_type_signature", "wcag_rule_id", name="uq_ai_memory_signature_rule"),
    )
    # ivfflat requires the table to be non-empty to build well, but Postgres
    # allows creating it on an empty table; ANALYZE after a real workload
    # accumulates is recommended (documented in the README, not automated
    # here to keep this migration idempotent and fast in fresh dev DBs).
    op.execute(
        "CREATE INDEX ix_ai_memory_embedding ON ai_memory "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    op.create_table(
        "ai_memory_updates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ai_memory_id", sa.Integer(), sa.ForeignKey("ai_memory.id", ondelete="CASCADE"), nullable=False),
        sa.Column("audit_run_id", sa.Integer(), sa.ForeignKey("audit_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("confidence_before", sa.Float(), nullable=False),
        sa.Column("confidence_after", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_memory_updates_ai_memory_id", "ai_memory_updates", ["ai_memory_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_memory_updates_ai_memory_id", table_name="ai_memory_updates")
    op.drop_table("ai_memory_updates")

    op.execute("DROP INDEX IF EXISTS ix_ai_memory_embedding")
    op.drop_table("ai_memory")
