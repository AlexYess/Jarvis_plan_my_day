"""task classifications table

Revision ID: 002_task_classifications
Revises: 001_initial
Create Date: 2026-05-21 00:00:00.000000

Mirrors the structure of event_classifications but lives separately because:
  - Task classifications include estimated_duration_minutes (events don't).
  - Tasks come from a different source (Google Tasks) with different volume
    and lifecycle (created, completed, deleted).
  - Keeps the schemas independent so they can evolve at different rates.

The classification JSONB has shape:
  {
    "tags": [{"tag": "deep_work", "confidence": 0.85}, ...],
    "estimated_duration_minutes": 90,
    "duration_confidence": 0.7
  }
"""
from typing import Sequence, Union

from alembic import op


revision: str = "002_task_classifications"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE task_classifications (
            title_normalized VARCHAR(500) PRIMARY KEY,
            title_original   VARCHAR(500) NOT NULL,
            classification   JSONB NOT NULL,
            tags_snapshot    JSONB NOT NULL,
            model_version    VARCHAR(50),
            classified_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX idx_task_class_jsonb "
        "ON task_classifications USING GIN (classification)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS task_classifications")