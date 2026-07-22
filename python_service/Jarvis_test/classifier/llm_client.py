"""
Anthropic client wrapper for batched event classification.

Responsibilities:
  - Chunk a long list of titles into batches (LLM_BATCH_SIZE per request).
  - Parse strict-JSON responses; recover from minor formatting issues
    (markdown fences, leading/trailing text).
  - Validate that every input title got a result.
  - Filter tags by confidence threshold and against the known tag set.
"""

import json
import logging
import re
from typing import Optional

from anthropic import Anthropic
from anthropic.types import Message

from config import settings
from classifier.prompts import (
    build_system_prompt, build_user_prompt,
    build_task_system_prompt, build_task_user_prompt,
)


logger = logging.getLogger(__name__)


# Each request has fixed overhead (system prompt). Output scales with batch
# size: ~50 output tokens per title in worst case. 30 titles => ~1500 out
# tokens, comfortable margin against the limit.
_MAX_TOKENS_PER_REQUEST = 4096


class ClassificationError(Exception):
    """Raised when the LLM response can't be parsed or is malformed."""


class LLMClassifier:
    """Stateful wrapper - reuse across requests for connection efficiency."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.client = Anthropic(api_key=api_key or settings.ANTHROPIC_API_KEY)
        self.model = model or settings.LLM_MODEL

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def classify_titles(
        self,
        titles: list[str],
        tags: list[dict],
        min_confidence: Optional[float] = None,
        batch_size: Optional[int] = None,
    ) -> dict[str, list[dict]]:
        """
        Classify a list of event titles against the given tag taxonomy.

        Returns: {title: [{"tag": str, "confidence": float}, ...]}

        Titles missing from the response are returned with an empty tag list
        rather than raising - one bad title shouldn't kill the whole batch.
        """
        if not titles:
            return {}

        min_conf = min_confidence if min_confidence is not None else settings.LLM_MIN_CONFIDENCE
        bs = batch_size or settings.LLM_BATCH_SIZE
        valid_tag_names = {t["name"] for t in tags}

        system_prompt = build_system_prompt(tags, min_conf)
        result: dict[str, list[dict]] = {}

        for chunk_start in range(0, len(titles), bs):
            chunk = titles[chunk_start:chunk_start + bs]
            logger.info(
                "Classifying chunk %d/%d (%d titles)",
                chunk_start // bs + 1,
                (len(titles) + bs - 1) // bs,
                len(chunk),
            )
            try:
                chunk_result = self._classify_chunk(chunk, system_prompt, valid_tag_names, min_conf)
                result.update(chunk_result)
            except ClassificationError as exc:
                logger.error("Chunk failed, skipping: %s", exc)
                # Fill missing titles with empty results so the caller knows
                # we tried but couldn't classify them.
                for t in chunk:
                    result.setdefault(t, [])

        return result

    # -----------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------

    def _classify_chunk(
        self,
        titles: list[str],
        system_prompt: str,
        valid_tag_names: set[str],
        min_confidence: float,
    ) -> dict[str, list[dict]]:
        user_prompt = build_user_prompt(titles)

        message: Message = self.client.messages.create(
            model=self.model,
            max_tokens=_MAX_TOKENS_PER_REQUEST,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        logger.info(
            "LLM call: in=%d out=%d tokens",
            message.usage.input_tokens,
            message.usage.output_tokens,
        )

        text = "".join(
            block.text for block in message.content if block.type == "text"
        )
        parsed = _parse_json_response(text)
        return _validate_and_normalize(parsed, titles, valid_tag_names, min_confidence)


# ---------------------------------------------------------------------------
# Response parsing helpers (module-level so they can be unit-tested)
# ---------------------------------------------------------------------------

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL)


def _parse_json_response(text: str) -> dict:
    """
    Extract JSON from the model response, tolerating:
      - Markdown code fences ```json ... ```
      - Leading/trailing prose
    """
    text = text.strip()

    # 1. Try direct parse - happiest path when the model obeyed instructions.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Try extracting from a markdown code fence.
    match = _JSON_BLOCK_RE.search(text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Try locating the outermost { ... } block.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ClassificationError(f"Could not parse JSON: {exc}; raw: {text[:200]}")

    raise ClassificationError(f"No JSON found in response: {text[:200]}")


def _validate_and_normalize(
    parsed: dict,
    input_titles: list[str],
    valid_tag_names: set[str],
    min_confidence: float,
) -> dict[str, list[dict]]:
    """
    Validate the model's output and normalize it to {title: [tag_obj, ...]}.

    - Drops tags not in the taxonomy (model hallucinations).
    - Drops tags below min_confidence.
    - Clamps confidence to [0, 1].
    - Sorts tags by confidence descending.
    - Fills missing input titles with empty lists.
    """
    results = parsed.get("results")
    if not isinstance(results, list):
        raise ClassificationError(f"Expected 'results' list, got: {type(results)}")

    by_title: dict[str, list[dict]] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        raw_tags = item.get("tags", [])
        if not isinstance(title, str) or not isinstance(raw_tags, list):
            continue

        cleaned: list[dict] = []
        for tag_obj in raw_tags:
            if not isinstance(tag_obj, dict):
                continue
            tag_name = tag_obj.get("tag")
            conf = tag_obj.get("confidence")
            if not isinstance(tag_name, str) or not isinstance(conf, (int, float)):
                continue
            if tag_name not in valid_tag_names:
                logger.debug("Dropping unknown tag '%s' for title '%s'", tag_name, title)
                continue
            conf = max(0.0, min(1.0, float(conf)))
            if conf < min_confidence:
                continue
            cleaned.append({"tag": tag_name, "confidence": round(conf, 3)})

        cleaned.sort(key=lambda x: -x["confidence"])
        by_title[title] = cleaned

    # Fill in any titles the model dropped silently.
    for t in input_titles:
        by_title.setdefault(t, [])

    return by_title


# ---------------------------------------------------------------------------
# Task classification (extension of LLMClassifier above)
# ---------------------------------------------------------------------------
# We monkey-patch a method onto the class to keep the existing API tidy.
# Functions live at module level for testability.

def _classify_tasks(
    self: LLMClassifier,
    tasks: list[dict],
    tags: list[dict],
    min_confidence: Optional[float] = None,
    batch_size: Optional[int] = None,
) -> dict[str, dict]:
    """
    Classify a list of task objects.

    Each task: {"title": str, "notes": str | None}
    Returns: {title: {"tags": [...], "estimated_duration_minutes": int,
                      "duration_confidence": float}}
    """
    if not tasks:
        return {}

    min_conf = min_confidence if min_confidence is not None else settings.LLM_MIN_CONFIDENCE
    bs = batch_size or settings.LLM_BATCH_SIZE
    valid_tag_names = {t["name"] for t in tags}

    system_prompt = build_task_system_prompt(tags, min_conf)
    result: dict[str, dict] = {}

    for chunk_start in range(0, len(tasks), bs):
        chunk = tasks[chunk_start:chunk_start + bs]
        logger.info(
            "Classifying task chunk %d/%d (%d tasks)",
            chunk_start // bs + 1,
            (len(tasks) + bs - 1) // bs,
            len(chunk),
        )
        try:
            chunk_result = _classify_task_chunk(
                self, chunk, system_prompt, valid_tag_names, min_conf
            )
            result.update(chunk_result)
        except ClassificationError as exc:
            logger.error("Task chunk failed: %s", exc)
            # Fill misses with empty result so the caller knows we tried
            for t in chunk:
                result.setdefault(t["title"], {
                    "tags": [],
                    "estimated_duration_minutes": settings.DURATION_FALLBACK_MINUTES,
                    "duration_confidence": 0.0,
                })

    return result


def _classify_task_chunk(
    classifier: LLMClassifier,
    tasks: list[dict],
    system_prompt: str,
    valid_tag_names: set[str],
    min_confidence: float,
) -> dict[str, dict]:
    user_prompt = build_task_user_prompt(tasks)

    message = classifier.client.messages.create(
        model=classifier.model,
        max_tokens=_MAX_TOKENS_PER_REQUEST,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    logger.info(
        "LLM task call: in=%d out=%d tokens",
        message.usage.input_tokens,
        message.usage.output_tokens,
    )

    text = "".join(b.text for b in message.content if b.type == "text")
    parsed = _parse_json_response(text)
    return _validate_and_normalize_tasks(
        parsed, [t["title"] for t in tasks], valid_tag_names, min_confidence
    )


def _validate_and_normalize_tasks(
    parsed: dict,
    input_titles: list[str],
    valid_tag_names: set[str],
    min_confidence: float,
) -> dict[str, dict]:
    """
    Same idea as _validate_and_normalize but also extracts duration.

    Output shape per title:
      {
        "tags": [{"tag": str, "confidence": float}, ...],
        "estimated_duration_minutes": int,
        "duration_confidence": float,
      }
    """
    results = parsed.get("results")
    if not isinstance(results, list):
        raise ClassificationError(f"Expected 'results' list, got: {type(results)}")

    by_title: dict[str, dict] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        if not isinstance(title, str):
            continue

        # Tags - same filtering as events
        raw_tags = item.get("tags", []) if isinstance(item.get("tags"), list) else []
        cleaned_tags: list[dict] = []
        for tag_obj in raw_tags:
            if not isinstance(tag_obj, dict):
                continue
            name = tag_obj.get("tag")
            conf = tag_obj.get("confidence")
            if not isinstance(name, str) or not isinstance(conf, (int, float)):
                continue
            if name not in valid_tag_names:
                continue
            conf = max(0.0, min(1.0, float(conf)))
            if conf < min_confidence:
                continue
            cleaned_tags.append({"tag": name, "confidence": round(conf, 3)})
        cleaned_tags.sort(key=lambda x: -x["confidence"])

        # Duration - validate and apply sensible bounds
        duration = item.get("estimated_duration_minutes")
        if not isinstance(duration, (int, float)) or duration <= 0:
            duration = settings.DURATION_FALLBACK_MINUTES
        else:
            # Clamp to [5 minutes, 8 hours] to catch obvious bugs
            duration = int(max(5, min(480, duration)))

        dur_conf = item.get("duration_confidence")
        if not isinstance(dur_conf, (int, float)):
            dur_conf = 0.0
        dur_conf = max(0.0, min(1.0, float(dur_conf)))

        by_title[title] = {
            "tags": cleaned_tags,
            "estimated_duration_minutes": duration,
            "duration_confidence": round(dur_conf, 3),
        }

    # Fill missing titles
    for t in input_titles:
        by_title.setdefault(t, {
            "tags": [],
            "estimated_duration_minutes": settings.DURATION_FALLBACK_MINUTES,
            "duration_confidence": 0.0,
        })

    return by_title


# Attach to the class so callers can do client.classify_tasks(...)
LLMClassifier.classify_tasks = _classify_tasks