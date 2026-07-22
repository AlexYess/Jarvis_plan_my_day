"""
High-level classifier service.

This is what endpoints call. It orchestrates the full flow:

  1. Normalize and deduplicate input titles.
  2. Hit the cache (event_classifications table) for known titles.
  3. Send only unknown titles to the LLM, in chunks.
  4. Persist new classifications.
  5. Return the combined view: {original_title: [tag_obj, ...]}.

The service is stateless except for the LLMClassifier instance, which is
created once at module load to reuse the HTTP connection.
"""

import logging
from typing import Iterable, Optional

from classifier import repository as repo
from classifier.llm_client import LLMClassifier
from config import settings

logger = logging.getLogger(__name__)


# Shared LLM client. Constructed lazily on first use so tests / health checks
# don't need the API key to be set.
_llm_client: LLMClassifier | None = None


def _get_llm() -> LLMClassifier:
    global _llm_client
    if _llm_client is None:
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set; classifier cannot call the LLM"
            )
        _llm_client = LLMClassifier()
    return _llm_client


def classify_events(
    titles: Iterable[str],
    force_refresh: bool = False,
) -> dict[str, list[dict]]:
    """
    Classify a list of event titles, using the cache aggressively.

    Args:
        titles: raw event summaries (any case, with duplicates ok).
        force_refresh: if True, ignore cache and re-classify everything.

    Returns:
        {original_title: [{"tag": str, "confidence": float}, ...]}
        Multiple input titles that normalize to the same string get the same
        result (the cache key is the normalized form).
    """
    # 1. Normalize + dedupe. Map normalized -> the first original we saw,
    #    so we can return results keyed by what the caller actually passed.
    normalized_to_original: dict[str, str] = {}
    originals_per_normalized: dict[str, list[str]] = {}

    for title in titles:
        if not isinstance(title, str) or not title.strip():
            continue
        norm = repo.normalize_title(title)
        normalized_to_original.setdefault(norm, title)
        originals_per_normalized.setdefault(norm, []).append(title)

    if not normalized_to_original:
        return {}

    unique_normalized = list(normalized_to_original.keys())
    logger.info(
        "classify_events: %d titles -> %d unique normalized",
        sum(len(v) for v in originals_per_normalized.values()),
        len(unique_normalized),
    )

    # 2. Load tag taxonomy. Done once - the LLM call needs the names and
    #    the current set is used to detect stale cache entries.
    tags = repo.list_tags()
    current_tag_names = sorted(t["name"] for t in tags)
    current_tag_set = set(current_tag_names)

    # 3. Try the cache for everything.
    cached: dict[str, dict] = {}
    if not force_refresh:
        cached = repo.get_classifications_bulk(unique_normalized)

    # 4. Decide which titles need LLM. A cached entry is reusable only when
    #    its tags_snapshot matches the current taxonomy - otherwise the
    #    classification was made against a different vocabulary.
    cache_hits: dict[str, list[dict]] = {}
    needs_llm: list[str] = []

    for norm in unique_normalized:
        row = cached.get(norm)
        if not row:
            needs_llm.append(norm)
            continue
        snapshot = set(row.get("tags_snapshot") or [])
        if snapshot != current_tag_set:
            logger.debug("Cache stale for '%s' (taxonomy changed); re-classifying", norm)
            needs_llm.append(norm)
            continue
        cache_hits[norm] = row["classification"]

    logger.info(
        "Cache: %d hits, %d misses, %d to LLM",
        len(cache_hits), len(needs_llm), len(needs_llm),
    )

    # 5. Call the LLM only for misses. We send the ORIGINAL title (better
    #    capitalization/punctuation for the model) but cache by normalized.
    new_classifications: dict[str, list[dict]] = {}
    if needs_llm:
        # Use original form for LLM input; map back via normalized.
        originals_for_llm = [normalized_to_original[n] for n in needs_llm]
        llm_results = _get_llm().classify_titles(originals_for_llm, tags)

        # Build records for upsert, keyed by normalized.
        upsert_rows: list[dict] = []
        for norm, original in zip(needs_llm, originals_for_llm):
            tag_list = llm_results.get(original, [])
            new_classifications[norm] = tag_list
            upsert_rows.append({
                "title_normalized": norm,
                "title_original": original,
                "classification": tag_list,
            })

        repo.upsert_classifications(
            upsert_rows,
            tags_snapshot=current_tag_names,
            model_version=settings.LLM_MODEL,
        )

    # 6. Build the final response: every original title -> tags.
    output: dict[str, list[dict]] = {}
    for norm, originals in originals_per_normalized.items():
        tag_list = cache_hits.get(norm) or new_classifications.get(norm, [])
        for original in originals:
            output[original] = tag_list

    return output


# ---------------------------------------------------------------------------
# Task classification - same pattern as events, but tasks carry notes
# and we also extract duration estimates.
# ---------------------------------------------------------------------------

def classify_tasks(
    tasks: list[dict],
    force_refresh: bool = False,
) -> dict[str, dict]:
    """
    Classify task objects, using the cache aggressively.

    Args:
        tasks: list of {"title": str, "notes": str | None} from Google Tasks.
               Other TaskDto fields are ignored at this layer - we only need
               text for classification.
        force_refresh: ignore cache and re-classify everything.

    Returns:
        {original_title: {"tags": [...],
                          "estimated_duration_minutes": int,
                          "duration_confidence": float}}

    Note: cache key is the normalized TITLE only. Two tasks with the same
    title but different notes share the same classification. If this becomes
    a problem, we can extend the cache key to include hash(notes).
    """
    # 1. Dedupe by normalized title. We keep the first task's notes seen,
    #    on the assumption that within one user's list, the same title
    #    usually means the same task type.
    normalized_to_task: dict[str, dict] = {}
    originals_per_normalized: dict[str, list[str]] = {}

    for task in tasks:
        title = task.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        norm = repo.normalize_title(title)
        if norm not in normalized_to_task:
            normalized_to_task[norm] = {
                "title": title,
                "notes": task.get("notes"),
            }
        originals_per_normalized.setdefault(norm, []).append(title)

    if not normalized_to_task:
        return {}

    unique_normalized = list(normalized_to_task.keys())
    logger.info(
        "classify_tasks: %d tasks -> %d unique normalized",
        sum(len(v) for v in originals_per_normalized.values()),
        len(unique_normalized),
    )

    # 2. Load tag taxonomy
    tags = repo.list_tags()
    current_tag_names = sorted(t["name"] for t in tags)
    current_tag_set = set(current_tag_names)

    # 3. Cache lookup
    cached: dict[str, dict] = {}
    if not force_refresh:
        cached = repo.get_task_classifications_bulk(unique_normalized)

    # 4. Filter cache hits by tag snapshot freshness
    cache_hits: dict[str, dict] = {}
    needs_llm: list[str] = []

    for norm in unique_normalized:
        row = cached.get(norm)
        if not row:
            needs_llm.append(norm)
            continue
        snapshot = set(row.get("tags_snapshot") or [])
        if snapshot != current_tag_set:
            needs_llm.append(norm)
            continue
        cache_hits[norm] = row["classification"]

    logger.info(
        "Task cache: %d hits, %d misses",
        len(cache_hits), len(needs_llm),
    )

    # 5. LLM call for misses
    new_classifications: dict[str, dict] = {}
    if needs_llm:
        tasks_for_llm = [normalized_to_task[n] for n in needs_llm]
        llm_results = _get_llm().classify_tasks(tasks_for_llm, tags)

        upsert_rows: list[dict] = []
        for norm, task in zip(needs_llm, tasks_for_llm):
            classification = llm_results.get(task["title"], {
                "tags": [],
                "estimated_duration_minutes": settings.DURATION_FALLBACK_MINUTES,
                "duration_confidence": 0.0,
            })
            classification = _apply_duration_fallback(classification, title=task["title"])
            new_classifications[norm] = classification
            upsert_rows.append({
                "title_normalized": norm,
                "title_original": task["title"],
                "classification": classification,
            })

        repo.upsert_task_classifications(
            upsert_rows,
            tags_snapshot=current_tag_names,
            model_version=settings.LLM_MODEL,
        )

    # 6. Build final response
    output: dict[str, dict] = {}
    for norm, originals in originals_per_normalized.items():
        cls = cache_hits.get(norm) or new_classifications.get(norm, {
            "tags": [],
            "estimated_duration_minutes": settings.DURATION_FALLBACK_MINUTES,
            "duration_confidence": 0.0,
        })
        for original in originals:
            output[original] = cls

    return output


def _apply_duration_fallback(classification: dict, title: Optional[str] = None) -> dict:
    """
    Resolve final duration using a three-tier fallback:

      Tier 1: History from the user's calendar
              - exact normalized title match in event_classifications
              - or aggregate of events with same top tag
      Tier 2: LLM's estimate, if LLM was confident
      Tier 3: Per-tag default (DEFAULT_DURATION_BY_TAG)
      Tier 4: Global fallback (DURATION_FALLBACK_MINUTES)

    History wins when available because user-specific patterns beat
    population averages.
    """
    # Tier 1: history (skipped if title not provided, e.g. unit tests)
    if title:
        from classifier.duration_history import estimate_duration_from_history
        try:
            historical = estimate_duration_from_history(
                title, classification.get("tags", [])
            )
        except Exception:
            # If history lookup fails (DB issue), fall through to other tiers.
            logger.exception("History lookup failed; falling back")
            historical = None

        if historical is not None:
            duration, source = historical
            classification["estimated_duration_minutes"] = duration
            classification["duration_source"] = source
            return classification

    # Tier 2: trust the LLM if it was confident
    dur_conf = classification.get("duration_confidence", 0.0)
    if dur_conf >= settings.DURATION_CONFIDENCE_THRESHOLD:
        classification["duration_source"] = "llm"
        return classification

    # Tier 3 + 4: tag-default or global fallback
    tags = classification.get("tags", [])
    if not tags:
        classification["estimated_duration_minutes"] = settings.DURATION_FALLBACK_MINUTES
        classification["duration_source"] = "global_fallback"
        return classification

    top_tag = tags[0]["tag"]
    default_min = settings.DEFAULT_DURATION_BY_TAG.get(top_tag)
    if default_min is not None:
        classification["estimated_duration_minutes"] = default_min
        classification["duration_source"] = f"tag_default:{top_tag}"
    else:
        classification["estimated_duration_minutes"] = settings.DURATION_FALLBACK_MINUTES
        classification["duration_source"] = "global_fallback"

    return classification