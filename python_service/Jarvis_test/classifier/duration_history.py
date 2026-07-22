"""
Duration history accumulator and lookup.

Two concerns live here:

  1. When /analyze receives a batch of events, accumulate per-title duration
     stats into the event_classifications cache. The cache becomes the source
     of truth for "how long does this kind of event usually take for THIS user".

  2. When /classify/tasks needs a duration, look up history first - exact
     match by normalized title, then by top tag, then fall back to LLM/defaults.

Why this matters:
  Generic defaults ("deep_work = 60 min") are average across all users.
  Real user data is far more accurate. After a month of use, history should
  dominate over the LLM's guess.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from analyzer import classify_event, get_event_times, _event_weight
from classifier import repository as repo
from models import CalendarEventDto

logger = logging.getLogger(__name__)


# When merging new events into existing stats, how much weight does new data get?
# 1.0 = replace, 0.0 = ignore new data. Around 0.5 means averaged but with bias
# toward the latest run. We use streaming aggregation that's exact, not weighted,
# but recency is built into the per-event weights themselves.

# Minimum sample size to use exact-title history with confidence.
MIN_EXACT_HISTORY_COUNT = 2
# Minimum sample size to use tag-based history.
MIN_TAG_HISTORY_COUNT = 5


# ---------------------------------------------------------------------------
# Accumulation (called from /analyze)
# ---------------------------------------------------------------------------

def accumulate_duration_stats(events: list[CalendarEventDto]) -> int:
    """
    Walk events, compute per-title duration stats, merge into existing
    classification records in event_classifications.

    Returns the number of titles updated.

    The stats stored per title:
      {
        "count": int,
        "median_minutes": float,        # exact median (computed from samples)
        "weighted_avg_minutes": float,  # time-weighted avg
        "last_seen": "YYYY-MM-DD"
      }

    We rebuild stats from scratch on each call (not streaming) because the
    full event set comes in every /analyze - we'd rather have correct numbers
    than try to do online updates.
    """
    today = datetime.now(timezone.utc).date()

    # Group events by normalized title, collect durations + weights
    by_title: dict[str, list[tuple[float, float, "date"]]] = {}
    # entries: (duration_minutes, weight, event_date)

    for event in events:
        is_blocking, _ = classify_event(event)
        if not is_blocking:
            continue
        times = get_event_times(event)
        if not times:
            continue
        title = (event.summary or "").strip()
        if not title:
            continue

        start, end = times
        duration_min = (end - start).total_seconds() / 60.0
        if duration_min <= 0 or duration_min > 12 * 60:
            # Skip degenerate or absurdly long events
            continue

        weight = _event_weight(start.date(), today)
        norm = repo.normalize_title(title)
        by_title.setdefault(norm, []).append((duration_min, weight, start.date()))

    if not by_title:
        return 0

    # Compute stats per title
    stats_by_title: dict[str, dict] = {}
    for norm, samples in by_title.items():
        durations = [d for d, _, _ in samples]
        weights = [w for _, w, _ in samples]
        last_seen = max(date for _, _, date in samples)

        # Median - exact, no weighting
        sorted_d = sorted(durations)
        n = len(sorted_d)
        median = sorted_d[n // 2] if n % 2 else (sorted_d[n // 2 - 1] + sorted_d[n // 2]) / 2

        # Weighted average
        total_weight = sum(weights)
        if total_weight > 0:
            weighted_avg = sum(d * w for d, w in zip(durations, weights)) / total_weight
        else:
            weighted_avg = median  # fallback

        stats_by_title[norm] = {
            "count": n,
            "median_minutes": round(median, 1),
            "weighted_avg_minutes": round(weighted_avg, 1),
            "last_seen": last_seen.isoformat(),
        }

    # Merge into existing classification records
    updated = repo.merge_duration_stats(stats_by_title)
    logger.info("Accumulated duration stats for %d unique titles", len(stats_by_title))
    return updated


# ---------------------------------------------------------------------------
# Lookup (called from /classify/tasks)
# ---------------------------------------------------------------------------

def estimate_duration_from_history(
    title: str,
    tags: list[dict],
) -> Optional[tuple[int, str]]:
    """
    Try to estimate duration from accumulated history.

    Args:
        title: original task title.
        tags: classification tags from LLM, sorted by confidence desc.

    Returns:
        (duration_minutes, source) if confident, else None.
        source is one of: "history_exact", "history_tag".
    """
    # Tier 1: exact title match
    norm = repo.normalize_title(title)
    record = repo.get_classification(norm)
    if record:
        stats = record.get("duration_stats")
        if stats and stats.get("count", 0) >= MIN_EXACT_HISTORY_COUNT:
            duration = int(round(stats["weighted_avg_minutes"]))
            logger.info(
                "Duration from exact history for '%s': %d min (n=%d)",
                title, duration, stats["count"],
            )
            return (duration, "history_exact")

    # Tier 2: by top tag, aggregated across all events with that tag
    if tags:
        top_tag = tags[0]["tag"]
        aggregated = repo.get_duration_stats_by_tag(top_tag)
        if aggregated and aggregated.get("count", 0) >= MIN_TAG_HISTORY_COUNT:
            duration = int(round(aggregated["weighted_avg_minutes"]))
            logger.info(
                "Duration from tag history for '%s' (tag=%s): %d min (n=%d)",
                title, top_tag, duration, aggregated["count"],
            )
            return (duration, f"history_tag:{top_tag}")

    return None