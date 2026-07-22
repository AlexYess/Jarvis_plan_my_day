"""
Repository layer for tags and event classifications.
All raw SQL lives here so service code stays storage-agnostic.

Pattern: each function opens its own connection from the pool via the
context manager. Transactions auto-commit on successful exit.
"""

import json
import logging
from typing import Optional

from psycopg.rows import dict_row

from db.connection import get_connection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_title(title: str) -> str:
    """
    Normalize event titles for cache lookup.
    Keeps cache hits high across "Daily Standup", "daily standup", " Daily  Standup ".
    """
    return " ".join(title.lower().split())


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

def list_tags() -> list[dict]:
    """Return all tags with their parent name resolved for convenience."""
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT
                    t.id,
                    t.name,
                    t.description,
                    p.name AS parent_name,
                    t.created_at
                FROM tags t
                LEFT JOIN tags p ON p.id = t.parent_tag_id
                ORDER BY COALESCE(p.name, t.name), t.name
            """)
            return cur.fetchall()


def get_tag_names() -> list[str]:
    """Just the tag names - what the LLM needs."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM tags ORDER BY name")
            return [row[0] for row in cur.fetchall()]


def add_tag(
    name: str,
    description: Optional[str] = None,
    parent_name: Optional[str] = None,
) -> dict:
    """
    Insert a new tag. Raises if name conflicts.
    parent_name is resolved to parent_tag_id; pass None for a top-level tag.
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                INSERT INTO tags (name, description, parent_tag_id)
                VALUES (
                    %(name)s,
                    %(description)s,
                    (SELECT id FROM tags WHERE name = %(parent)s)
                )
                RETURNING id, name, description, parent_tag_id, created_at
            """, {"name": name, "description": description, "parent": parent_name})
            return cur.fetchone()


def delete_tag(name: str) -> bool:
    """Remove a tag. Children get parent_tag_id = NULL (ON DELETE SET NULL)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tags WHERE name = %s", (name,))
            return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Event classifications
# ---------------------------------------------------------------------------

def get_classification(title_normalized: str) -> Optional[dict]:
    """
    Fetch a cached classification for a normalized title.
    Returns None if not yet classified.
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT
                    title_normalized,
                    title_original,
                    classification,
                    tags_snapshot,
                    model_version,
                    duration_stats,
                    classified_at,
                    updated_at
                FROM event_classifications
                WHERE title_normalized = %s
            """, (title_normalized,))
            return cur.fetchone()


def get_classifications_bulk(title_normalized_list: list[str]) -> dict[str, dict]:
    """
    Fetch many classifications at once. Returns {title_normalized: row}.
    Missing titles simply aren't in the result.
    """
    if not title_normalized_list:
        return {}
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT
                    title_normalized,
                    title_original,
                    classification,
                    tags_snapshot,
                    model_version,
                    classified_at
                FROM event_classifications
                WHERE title_normalized = ANY(%s)
            """, (title_normalized_list,))
            return {row["title_normalized"]: row for row in cur.fetchall()}


def upsert_classifications(
    items: list[dict],
    tags_snapshot: list[str],
    model_version: str,
) -> int:
    """
    Insert or update classifications in bulk.
    Each item: {"title_normalized", "title_original", "classification": [...]}
    Returns rowcount.
    """
    if not items:
        return 0

    snapshot_json = json.dumps(tags_snapshot)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany("""
                INSERT INTO event_classifications (
                    title_normalized, title_original, classification,
                    tags_snapshot, model_version
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (title_normalized) DO UPDATE SET
                    title_original = EXCLUDED.title_original,
                    classification = EXCLUDED.classification,
                    tags_snapshot  = EXCLUDED.tags_snapshot,
                    model_version  = EXCLUDED.model_version,
                    updated_at     = NOW()
            """, [
                (
                    item["title_normalized"],
                    item["title_original"],
                    json.dumps(item["classification"]),
                    snapshot_json,
                    model_version,
                )
                for item in items
            ])
            logger.info(
                "Upserted %d classifications (model=%s, tags=%d)",
                len(items), model_version, len(tags_snapshot),
            )
            return cur.rowcount


def invalidate_stale_classifications(current_tags: list[str]) -> int:
    """
    Delete classifications whose tags_snapshot differs from the current tag set.
    Call this after the tag taxonomy changes - cached entries based on the old
    taxonomy may be misleading.
    """
    current_set_json = json.dumps(sorted(current_tags))
    with get_connection() as conn:
        with conn.cursor() as cur:
            # We compare normalized JSON (sorted) for set-equality.
            cur.execute("""
                DELETE FROM event_classifications
                WHERE (
                    SELECT jsonb_agg(value ORDER BY value)
                    FROM jsonb_array_elements_text(tags_snapshot)
                )::text <> %s::text
            """, (current_set_json,))
            deleted = cur.rowcount
            if deleted > 0:
                logger.info(
                    "Invalidated %d stale classifications (tag set changed)",
                    deleted,
                )
            return deleted


# ---------------------------------------------------------------------------
# Task classifications - parallel cache for to-do items
# ---------------------------------------------------------------------------
# Same shape as event_classifications but distinct table. Lets the two
# evolve independently and keeps queries cleaner.

def get_task_classification(title_normalized: str) -> Optional[dict]:
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT
                    title_normalized,
                    title_original,
                    classification,
                    tags_snapshot,
                    model_version,
                    classified_at,
                    updated_at
                FROM task_classifications
                WHERE title_normalized = %s
            """, (title_normalized,))
            return cur.fetchone()


def get_task_classifications_bulk(title_normalized_list: list[str]) -> dict[str, dict]:
    if not title_normalized_list:
        return {}
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT
                    title_normalized,
                    title_original,
                    classification,
                    tags_snapshot,
                    model_version,
                    classified_at
                FROM task_classifications
                WHERE title_normalized = ANY(%s)
            """, (title_normalized_list,))
            return {row["title_normalized"]: row for row in cur.fetchall()}


def upsert_task_classifications(
    items: list[dict],
    tags_snapshot: list[str],
    model_version: str,
) -> int:
    """
    Each item: {"title_normalized", "title_original", "classification": {...}}
    classification is the full dict including tags, duration, duration_confidence.
    """
    if not items:
        return 0

    snapshot_json = json.dumps(tags_snapshot)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany("""
                INSERT INTO task_classifications (
                    title_normalized, title_original, classification,
                    tags_snapshot, model_version
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (title_normalized) DO UPDATE SET
                    title_original = EXCLUDED.title_original,
                    classification = EXCLUDED.classification,
                    tags_snapshot  = EXCLUDED.tags_snapshot,
                    model_version  = EXCLUDED.model_version,
                    updated_at     = NOW()
            """, [
                (
                    item["title_normalized"],
                    item["title_original"],
                    json.dumps(item["classification"]),
                    snapshot_json,
                    model_version,
                )
                for item in items
            ])
            logger.info(
                "Upserted %d task classifications (model=%s)",
                len(items), model_version,
            )
            return cur.rowcount


def invalidate_stale_task_classifications(current_tags: list[str]) -> int:
    """Same logic as for events; drops entries with mismatching tag snapshot."""
    current_set_json = json.dumps(sorted(current_tags))
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM task_classifications
                WHERE (
                    SELECT jsonb_agg(value ORDER BY value)
                    FROM jsonb_array_elements_text(tags_snapshot)
                )::text <> %s::text
            """, (current_set_json,))
            deleted = cur.rowcount
            if deleted > 0:
                logger.info("Invalidated %d stale task classifications", deleted)
            return deleted


# ---------------------------------------------------------------------------
# Duration stats (Layer 3 Part 1.5)
# ---------------------------------------------------------------------------
# Stored inside event_classifications.classification JSONB as:
#   {"tags": [...], "duration_stats": {count, median_minutes, ...}}
# No schema migration needed - JSONB lets us extend the payload.

def merge_duration_stats(stats_by_title: dict[str, dict]) -> int:
    """
    Persist duration stats per normalized title.

    Uses the dedicated duration_stats column added in migration 003.
    If the title doesn't have a classification record yet, we create a stub
    with empty tags so the next /classify/events call fills them in.
    """
    if not stats_by_title:
        return 0

    affected = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            for norm, stats in stats_by_title.items():
                cur.execute("""
                    INSERT INTO event_classifications
                        (title_normalized, title_original, classification,
                         tags_snapshot, model_version, duration_stats)
                    VALUES (
                        %(norm)s,
                        %(norm)s,
                        '[]'::jsonb,
                        '[]'::jsonb,
                        'history_only',
                        %(stats)s::jsonb
                    )
                    ON CONFLICT (title_normalized) DO UPDATE SET
                        duration_stats = EXCLUDED.duration_stats,
                        updated_at     = NOW()
                """, {"norm": norm, "stats": json.dumps(stats)})
                affected += cur.rowcount

    logger.info("Merged duration stats for %d titles", len(stats_by_title))
    return affected


def get_duration_stats_by_tag(tag_name: str) -> Optional[dict]:
    """
    Aggregate duration stats across all events that have the given tag with
    confidence >= 0.5. Returns dict with count + weighted_avg, or None.

    Note: classification is a JSON ARRAY of {tag, confidence} objects -
    NOT a dict. We iterate via jsonb_array_elements.
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT duration_stats
                FROM event_classifications
                WHERE duration_stats IS NOT NULL
                  AND EXISTS (
                      SELECT 1
                      FROM jsonb_array_elements(classification) AS t
                      WHERE t->>'tag' = %s
                        AND (t->>'confidence')::float >= 0.5
                  )
            """, (tag_name,))
            rows = cur.fetchall()

    if not rows:
        return None

    total_count = 0
    weighted_sum = 0.0
    all_avgs: list[float] = []

    for row in rows:
        stats = row["duration_stats"]
        if not stats:
            continue
        count = stats.get("count", 0)
        avg = stats.get("weighted_avg_minutes")
        if count <= 0 or avg is None:
            continue
        total_count += count
        weighted_sum += avg * count
        all_avgs.append(avg)

    if total_count == 0:
        return None

    sorted_avgs = sorted(all_avgs)
    n = len(sorted_avgs)
    median_of_means = (
        sorted_avgs[n // 2] if n % 2
        else (sorted_avgs[n // 2 - 1] + sorted_avgs[n // 2]) / 2
    )

    return {
        "count": total_count,
        "weighted_avg_minutes": round(weighted_sum / total_count, 1),
        "median_of_means_minutes": round(median_of_means, 1),
        "title_count": n,
    }