"""
Prompts for event classification.

The prompt is built dynamically because the tag taxonomy lives in the database
and can be edited at runtime. We never hardcode tag lists in the prompt.

Design choices:
  - System prompt is large but stable (gets cached by Anthropic if same across
    requests, which it is for a fixed tag taxonomy + model version).
  - User prompt contains only the variable part: the batch of titles.
  - Output is strict JSON to make parsing reliable.
  - Sparse output: only tags above a confidence threshold are returned -
    saves tokens and keeps the cache compact.
"""

import json
from typing import Iterable


SYSTEM_TEMPLATE = """\
You classify calendar event titles into user-defined tags.

You will receive a list of event titles. For each title, you assign confidence \
scores (0.0 to 1.0) to the tags most relevant to that event. You only output \
tags whose confidence is at least {min_confidence}. Many titles will match \
only one or two tags - that is normal and expected.

# Available tags

The user controls this taxonomy. Use ONLY these tags - do not invent new ones. \
If a title doesn't fit any tag, return an empty array for that title.

{tag_list}

# Rules

1. Confidence reflects how likely the event belongs to that tag, not how \
important the event is.
2. A title can have multiple tags when ambiguous. Example: "Gym with Mike" \
might be {{exercise: 0.85, social: 0.4}}.
3. For non-English titles, classify by meaning. Russian, Turkish, German, etc. \
are all fine.
4. Cryptic titles ("X", "TBD", "meeting") get low confidence on the best guess \
rather than being forced into a category.
5. Tags use the exact names from the list above, no variations.

# Output format

Return ONLY valid JSON, no prose, no markdown fences. The structure is:

{{
  "results": [
    {{
      "title": "<exact title from input>",
      "tags": [
        {{"tag": "<tag_name>", "confidence": <float>}},
        ...
      ]
    }},
    ...
  ]
}}

The order of results MUST match the order of input titles. Include every \
input title in the output, even if its tags array is empty.\
"""


USER_TEMPLATE = """\
Classify these {count} event titles:

{titles_block}

Return the JSON now."""


def format_tag_list(tags: list[dict]) -> str:
    """
    Render tags as a hierarchical bulleted list for the prompt.

    Input: rows from repository.list_tags(), each with name, description,
    parent_name.

    Output example:
        - work: Anything work-related
          - deep_work: Focused, cognitively demanding work
          - meeting: Scheduled meetings, calls, syncs
        - personal: Personal life, outside work
          - exercise: Sports, gym, running
    """
    by_parent: dict[str | None, list[dict]] = {}
    for tag in tags:
        by_parent.setdefault(tag.get("parent_name"), []).append(tag)

    lines: list[str] = []
    for top in by_parent.get(None, []):
        desc = top.get("description") or ""
        lines.append(f"- {top['name']}: {desc}".rstrip(": "))
        for child in by_parent.get(top["name"], []):
            cdesc = child.get("description") or ""
            lines.append(f"  - {child['name']}: {cdesc}".rstrip(": "))
    return "\n".join(lines)


def build_system_prompt(tags: list[dict], min_confidence: float) -> str:
    return SYSTEM_TEMPLATE.format(
        min_confidence=min_confidence,
        tag_list=format_tag_list(tags),
    )


def build_user_prompt(titles: Iterable[str]) -> str:
    titles = list(titles)
    # Number each title so the model can refer to them unambiguously.
    titles_block = "\n".join(
        f"{i + 1}. {json.dumps(t, ensure_ascii=False)}"
        for i, t in enumerate(titles)
    )
    return USER_TEMPLATE.format(count=len(titles), titles_block=titles_block)


# ============================================================================
# Task classification (events have happened; tasks are things to do)
# ============================================================================
#
# Differences from event classification:
#   - Tasks come with optional notes (extra context for the LLM).
#   - We also estimate duration in minutes and our confidence in that estimate.
#   - Semantics: "what kind of task is this" vs events' "what kind of activity
#     happened". Same tag taxonomy, but task wording is forward-looking.

TASK_SYSTEM_TEMPLATE = """\
You classify to-do tasks (with optional notes) into user-defined tags AND \
estimate how long each task takes to complete.

You will receive a numbered list of tasks. For each task you produce:
  1. Tag scores - confidence (0.0-1.0) per tag, sparse (only tags >= {min_confidence}).
  2. estimated_duration_minutes - your best guess in whole minutes.
  3. duration_confidence (0.0-1.0) - how sure you are about the duration.

# Available tags

Use ONLY these tags - do not invent new ones. If nothing fits, return [].

{tag_list}

# Duration guidance (rough anchors, not strict rules)

  - admin/errand:        10-30 min
  - meeting:             30-60 min
  - meal:                30-60 min
  - shallow work:        20-45 min
  - exercise:            45-90 min
  - deep work:           60-120 min
  - learning session:    30-90 min
  - large project task:  120-240 min (split if longer)

If the task is vague ("Прибраться", "Project") your duration_confidence \
should be low (0.2-0.4). If it's specific ("Email John about Q3 budget"), \
confidence is higher (0.7-0.9).

# Rules

1. Use the EXACT tag names from the list. No variations.
2. Tasks in any language are fine - classify by meaning.
3. Notes provide context; weigh them when present.
4. Multiple tags are normal for ambiguous tasks.

# Output format

Return ONLY valid JSON, no prose, no markdown fences:

{{
  "results": [
    {{
      "title": "<exact title from input>",
      "tags": [{{"tag": "<name>", "confidence": <float>}}, ...],
      "estimated_duration_minutes": <int>,
      "duration_confidence": <float>
    }},
    ...
  ]
}}

Output order MUST match input order. Include every input task.\
"""


TASK_USER_TEMPLATE = """\
Classify these {count} tasks:

{task_block}

Return the JSON now."""


def build_task_system_prompt(tags: list[dict], min_confidence: float) -> str:
    return TASK_SYSTEM_TEMPLATE.format(
        min_confidence=min_confidence,
        tag_list=format_tag_list(tags),
    )


def build_task_user_prompt(tasks: list[dict]) -> str:
    """
    Render tasks for the user prompt.
    Each task: {"title": str, "notes": str | None}
    """
    lines = []
    for i, task in enumerate(tasks):
        title = task["title"]
        notes = task.get("notes")
        line = f'{i + 1}. {json.dumps(title, ensure_ascii=False)}'
        if notes:
            # Limit notes length to keep prompt size predictable
            short_notes = notes[:200]
            line += f'\n   Notes: {json.dumps(short_notes, ensure_ascii=False)}'
        lines.append(line)
    return TASK_USER_TEMPLATE.format(count=len(tasks), task_block="\n".join(lines))