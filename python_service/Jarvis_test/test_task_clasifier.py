"""
Tests for task classification - response parsing and duration fallback logic.
No real LLM calls; validates the validation/normalization step.
"""

import sys
from types import SimpleNamespace

# Stub external dependencies that aren't needed for these unit tests
sys.modules['anthropic'] = SimpleNamespace(Anthropic=object)
sys.modules['anthropic.types'] = SimpleNamespace(Message=object)
sys.modules['psycopg'] = SimpleNamespace(Connection=object)
sys.modules['psycopg.rows'] = SimpleNamespace(dict_row=None)
sys.modules['psycopg_pool'] = SimpleNamespace(ConnectionPool=object)

# Now safe to import
from classifier.llm_client import _validate_and_normalize_tasks
from classifier.service import _apply_duration_fallback
from config import settings


def test_task_parse_basic():
    parsed = {
        "results": [
            {
                "title": "Подготовить отчёт",
                "tags": [{"tag": "deep_work", "confidence": 0.9}],
                "estimated_duration_minutes": 90,
                "duration_confidence": 0.8,
            }
        ]
    }
    result = _validate_and_normalize_tasks(
        parsed, ["Подготовить отчёт"], {"deep_work", "routine"}, 0.05
    )
    assert result["Подготовить отчёт"]["tags"][0]["tag"] == "deep_work"
    assert result["Подготовить отчёт"]["estimated_duration_minutes"] == 90
    assert result["Подготовить отчёт"]["duration_confidence"] == 0.8


def test_task_duration_clamped():
    """Garbage durations get clamped to sane bounds."""
    parsed = {
        "results": [
            {"title": "A", "tags": [], "estimated_duration_minutes": 99999, "duration_confidence": 0.5},
            {"title": "B", "tags": [], "estimated_duration_minutes": -10,   "duration_confidence": 0.5},
            {"title": "C", "tags": [], "estimated_duration_minutes": "not_a_number", "duration_confidence": 0.5},
        ]
    }
    result = _validate_and_normalize_tasks(parsed, ["A", "B", "C"], {"any"}, 0.05)
    assert result["A"]["estimated_duration_minutes"] == 480     # capped at 8 hours
    # invalid durations → fallback
    assert result["B"]["estimated_duration_minutes"] == settings.DURATION_FALLBACK_MINUTES
    assert result["C"]["estimated_duration_minutes"] == settings.DURATION_FALLBACK_MINUTES


def test_task_missing_fills_defaults():
    """Task LLM dropped silently → return a default-shaped entry."""
    parsed = {"results": []}
    result = _validate_and_normalize_tasks(parsed, ["X"], {"work"}, 0.05)
    assert result["X"]["tags"] == []
    assert result["X"]["estimated_duration_minutes"] == settings.DURATION_FALLBACK_MINUTES
    assert result["X"]["duration_confidence"] == 0.0


def test_duration_fallback_low_confidence_uses_tag_default():
    """When LLM is uncertain, use the per-tag default duration."""
    classification = {
        "tags": [{"tag": "deep_work", "confidence": 0.8}],
        "estimated_duration_minutes": 15,         # LLM guessed
        "duration_confidence": 0.2,               # but low confidence
    }
    result = _apply_duration_fallback(classification)
    # Should override LLM with deep_work default (60 min)
    expected = settings.DEFAULT_DURATION_BY_TAG["deep_work"]
    assert result["estimated_duration_minutes"] == expected
    assert result["duration_source"] == "tag_default:deep_work"


def test_duration_fallback_high_confidence_keeps_llm():
    """When LLM is confident, trust its estimate."""
    classification = {
        "tags": [{"tag": "deep_work", "confidence": 0.8}],
        "estimated_duration_minutes": 90,
        "duration_confidence": 0.85,   # above threshold
    }
    result = _apply_duration_fallback(classification)
    assert result["estimated_duration_minutes"] == 90
    assert "duration_source" not in result


def test_duration_fallback_no_tags():
    """No tags + low confidence → global fallback."""
    classification = {
        "tags": [],
        "estimated_duration_minutes": 15,
        "duration_confidence": 0.1,
    }
    result = _apply_duration_fallback(classification)
    assert result["estimated_duration_minutes"] == settings.DURATION_FALLBACK_MINUTES
    assert result["duration_source"] == "global_fallback"


def test_duration_fallback_unknown_tag():
    """Top tag missing from DEFAULT_DURATION_BY_TAG → global fallback."""
    classification = {
        "tags": [{"tag": "uncategorized_tag", "confidence": 0.8}],
        "estimated_duration_minutes": 15,
        "duration_confidence": 0.1,
    }
    result = _apply_duration_fallback(classification)
    assert result["estimated_duration_minutes"] == settings.DURATION_FALLBACK_MINUTES
    assert result["duration_source"] == "global_fallback"


if __name__ == "__main__":
    tests = [
        ("parse basic",                    test_task_parse_basic),
        ("duration clamped",               test_task_duration_clamped),
        ("missing fills defaults",         test_task_missing_fills_defaults),
        ("low conf → tag default",         test_duration_fallback_low_confidence_uses_tag_default),
        ("high conf → keep LLM",           test_duration_fallback_high_confidence_keeps_llm),
        ("no tags → global fallback",      test_duration_fallback_no_tags),
        ("unknown tag → global fallback",  test_duration_fallback_unknown_tag),
    ]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS: {name}")
        except Exception as e:
            print(f"FAIL: {name}: {e}")
            failures += 1
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)