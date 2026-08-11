"""plan_steps: element_type, manual_status_override, defect_status

Revision ID: d3e7f4a1b6c2
Revises: c4b8e1f2a9d0
Create Date: 2026-08-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd3e7f4a1b6c2'
down_revision: Union[str, None] = 'c4b8e1f2a9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS: this environment's DB got these columns applied by hand
    # ahead of the migration (blocked on an unrelated pgvector gap in
    # c4b8e1f2a9d0 upstream of this revision) - keep upgrade() idempotent so
    # it still no-ops cleanly once that's resolved and this migration runs
    # for real through Alembic.
    op.execute(
        "ALTER TABLE plan_steps ADD COLUMN IF NOT EXISTS element_type VARCHAR(80) NOT NULL DEFAULT 'General Page'"
    )
    op.execute("ALTER TABLE plan_steps ADD COLUMN IF NOT EXISTS manual_status_override VARCHAR(20)")
    op.execute(
        "ALTER TABLE plan_steps ADD COLUMN IF NOT EXISTS defect_status VARCHAR(20) NOT NULL DEFAULT 'Open'"
    )
    # Drop the server defaults once existing rows are backfilled - new rows
    # always supply these explicitly via the ORM, matching the convention
    # already used by every other status column in this table.
    op.execute("ALTER TABLE plan_steps ALTER COLUMN element_type DROP DEFAULT")
    op.execute("ALTER TABLE plan_steps ALTER COLUMN defect_status DROP DEFAULT")


def downgrade() -> None:
    op.drop_column("plan_steps", "defect_status")
    op.drop_column("plan_steps", "manual_status_override")
    op.drop_column("plan_steps", "element_type")
