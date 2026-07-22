"""add duration_stats column to event_classifications

Revision ID: 003_duration_stats_column
Revises: 002_task_classifications
Create Date: 2026-06-09 18:00:00.000000

In Part 1.5 we tried to embed duration_stats inside the existing JSONB
`classification` field, but that field is already a JSON array (tag list).
jsonb_set doesn't accept a key path on an array - hence the bug.

Cleaner: separate column. Faster lookups, clearer schema, no data migration
needed because old rows just get NULL until /analyze populates them.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "003_duration_stats_column"
down_revision: Union[str, None] = "002_task_classifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE event_classifications
        ADD COLUMN IF NOT EXISTS duration_stats JSONB
    """)
    # GIN index for "find titles with duration data" queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_event_class_duration_stats
        ON event_classifications USING GIN (duration_stats)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_event_class_duration_stats")
    op.execute("ALTER TABLE event_classifications DROP COLUMN IF EXISTS duration_stats")