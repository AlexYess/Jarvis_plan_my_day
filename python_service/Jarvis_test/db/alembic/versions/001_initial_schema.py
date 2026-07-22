"""initial schema: tags and event_classifications

Revision ID: 001_initial
Revises:
Create Date: 2026-05-19 00:00:00.000000

Creates the two tables needed for Layer 2:

  tags                  - user-managed taxonomy. The LLM rates events against
                          the tags currently in this table. New tags can be
                          added at runtime without code changes.

  event_classifications - cache of LLM classification results, keyed by
                          normalized event title. Lets us classify each unique
                          title only once, even if it appears 200 times in
                          the calendar.

Both tables use JSONB for the classification payload so adding fields later
(e.g. estimated_duration_minutes) doesn't require a schema migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Initial tag taxonomy. Hierarchy is encoded via parent_name reference;
# resolved to parent_tag_id during seed.
# Format: (name, parent_name_or_None, description)
SEED_TAGS = [
    # Top-level categories
    ("work",           None, "Anything work-related"),
    ("personal",       None, "Personal life, outside work"),
    ("break",          None, "Rest, meals, transitions"),

    # Work subcategories
    ("deep_work",      "work",     "Focused, cognitively demanding work in long blocks"),
    ("shallow_work",   "work",     "Lighter work tasks that don't require deep focus"),
    ("routine",        "work",     "Recurring administrative tasks: email, paperwork, status updates"),
    ("meeting",        "work",     "Scheduled meetings, calls, syncs"),
    ("interview",      "work",     "Job interviews (giving or taking)"),
    ("planning",       "work",     "Planning, strategy, retrospectives"),

    # Personal subcategories
    ("exercise",       "personal", "Sports, gym, running, training"),
    ("learning",       "personal", "Studying, courses, reading"),
    ("social",         "personal", "Time with friends, family, social events"),
    ("hobby",          "personal", "Creative or recreational activities"),
    ("errand",         "personal", "Chores, shopping, appointments"),
    ("health",         "personal", "Doctor visits, medical appointments"),

    # Break subcategories
    ("meal",           "break",    "Breakfast, lunch, dinner"),
    ("commute",        "break",    "Travel to/from a location"),
    ("rest",           "break",    "Naps, downtime, recovery"),
]


def upgrade() -> None:
    # --- tags ---
    op.execute("""
        CREATE TABLE tags (
            id            SERIAL PRIMARY KEY,
            name          VARCHAR(100) NOT NULL UNIQUE,
            description   TEXT,
            parent_tag_id INTEGER REFERENCES tags(id) ON DELETE SET NULL,
            created_at    TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_tags_parent ON tags(parent_tag_id)")

    # --- event_classifications ---
    # title_normalized = lowercase + trim of the event summary.
    # classification stores the sparse tag scores as JSONB:
    #   [{"tag": "meeting", "confidence": 0.85},
    #    {"tag": "deep_work", "confidence": 0.10}]
    # tags_snapshot stores the tag list at classification time, so we can
    # detect stale entries when the taxonomy changes.
    op.execute("""
        CREATE TABLE event_classifications (
            title_normalized VARCHAR(500) PRIMARY KEY,
            title_original   VARCHAR(500) NOT NULL,
            classification   JSONB NOT NULL,
            tags_snapshot    JSONB NOT NULL,
            model_version    VARCHAR(50),
            classified_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    # GIN index lets us query "give me events tagged with X" efficiently.
    op.execute(
        "CREATE INDEX idx_event_class_jsonb "
        "ON event_classifications USING GIN (classification)"
    )

    # --- seed tags ---
    # Insert top-level tags first so the second pass can resolve parent ids.
    for name, parent, description in SEED_TAGS:
        if parent is None:
            op.execute(sa.text("""
                INSERT INTO tags (name, description)
                VALUES (:name, :description)
            """).bindparams(name=name, description=description))

    for name, parent, description in SEED_TAGS:
        if parent is not None:
            op.execute(sa.text("""
                INSERT INTO tags (name, description, parent_tag_id)
                VALUES (
                    :name,
                    :description,
                    (SELECT id FROM tags WHERE name = :parent)
                )
            """).bindparams(name=name, description=description, parent=parent))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS event_classifications")
    op.execute("DROP TABLE IF EXISTS tags")