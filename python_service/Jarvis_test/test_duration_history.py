"""
Tests for duration history estimation and three-tier fallback logic.
"""

import sys
from types import SimpleNamespace

# Stub external dependencies
sys.modules['anthropic'] = SimpleNamespace(Anthropic=object)
sys.modules['anthropic.types'] = SimpleNamespace(Message=object)
sys.modules['psycopg'] = SimpleNamespace(Connection=object)
sys.modules['psycopg.rows'] = SimpleNamespace(dict_row=None)
sys.modules['psycopg_pool'] = SimpleNamespace(ConnectionPool=object)


# pydantic is only used by models module which we don't need here
class _StubBaseModel:
    pass
sys.modules['pydantic'] = SimpleNamespace(
    BaseModel=_StubBaseModel,
    Field=lambda *a, **k: None,
    ConfigDict=lambda **k: None,
)


def test_history_tier_exact_match_wins():
    """If exact-title history has enough samples, return it."""
    from classifier import service
    from classifier import duration_history

    # Monkey-patch duration_history to simulate finding exact history
    original = duration_history.estimate_duration_from_history
    duration_history.estimate_duration_from_history = lambda title, tags: (75, "history_exact")
    # Also patch in service (it imports lazily but the import is module-scoped on first call)

    try:
        classification = {
            "tags": [{"tag": "deep_work", "confidence": 0.9}],
            "estimated_duration_minutes": 60,
            "duration_confidence": 0.9,  # LLM confident
        }
        result = service._apply_duration_fallback(classification, title="Подготовить отчёт")
        # History wins over LLM
        assert result["estimated_duration_minutes"] == 75
        assert result["duration_source"] == "history_exact"
    finally:
        duration_history.estimate_duration_from_history = original


def test_history_tier_tag_match():
    """When no exact history, but tag history exists, use it."""
    from classifier import service
    from classifier import duration_history

    original = duration_history.estimate_duration_from_history
    duration_history.estimate_duration_from_history = lambda title, tags: (50, "history_tag:deep_work")

    try:
        classification = {
            "tags": [{"tag": "deep_work", "confidence": 0.9}],
            "estimated_duration_minutes": 60,
            "duration_confidence": 0.3,
        }
        result = service._apply_duration_fallback(classification, title="Новая задача")
        assert result["estimated_duration_minutes"] == 50
        assert result["duration_source"] == "history_tag:deep_work"
    finally:
        duration_history.estimate_duration_from_history = original


def test_history_none_falls_to_llm_when_confident():
    """No history + confident LLM → use LLM."""
    from classifier import service
    from classifier import duration_history

    original = duration_history.estimate_duration_from_history
    duration_history.estimate_duration_from_history = lambda title, tags: None

    try:
        classification = {
            "tags": [{"tag": "deep_work", "confidence": 0.9}],
            "estimated_duration_minutes": 90,
            "duration_confidence": 0.8,
        }
        result = service._apply_duration_fallback(classification, title="X")
        assert result["estimated_duration_minutes"] == 90
        assert result["duration_source"] == "llm"
    finally:
        duration_history.estimate_duration_from_history = original


def test_history_none_falls_to_tag_default():
    """No history + low confidence LLM + has tag → tag default."""
    from classifier import service
    from classifier import duration_history
    from config import settings

    original = duration_history.estimate_duration_from_history
    duration_history.estimate_duration_from_history = lambda title, tags: None

    try:
        classification = {
            "tags": [{"tag": "deep_work", "confidence": 0.9}],
            "estimated_duration_minutes": 15,
            "duration_confidence": 0.1,
        }
        result = service._apply_duration_fallback(classification, title="X")
        assert result["estimated_duration_minutes"] == settings.DEFAULT_DURATION_BY_TAG["deep_work"]
        assert result["duration_source"] == "tag_default:deep_work"
    finally:
        duration_history.estimate_duration_from_history = original


def test_history_none_no_tags_global_fallback():
    """Nothing works → global fallback."""
    from classifier import service
    from classifier import duration_history
    from config import settings

    original = duration_history.estimate_duration_from_history
    duration_history.estimate_duration_from_history = lambda title, tags: None

    try:
        classification = {
            "tags": [],
            "estimated_duration_minutes": 15,
            "duration_confidence": 0.1,
        }
        result = service._apply_duration_fallback(classification, title="123")
        assert result["estimated_duration_minutes"] == settings.DURATION_FALLBACK_MINUTES
        assert result["duration_source"] == "global_fallback"
    finally:
        duration_history.estimate_duration_from_history = original


def test_history_exception_does_not_break():
    """If history lookup throws, fall through to other tiers gracefully."""
    from classifier import service
    from classifier import duration_history
    from config import settings

    original = duration_history.estimate_duration_from_history

    def boom(title, tags):
        raise RuntimeError("DB is down")

    duration_history.estimate_duration_from_history = boom

    try:
        classification = {
            "tags": [{"tag": "meeting", "confidence": 0.9}],
            "estimated_duration_minutes": 45,
            "duration_confidence": 0.8,
        }
        # Should not raise
        result = service._apply_duration_fallback(classification, title="Standup")
        # Falls through to "trust LLM" tier
        assert result["estimated_duration_minutes"] == 45
        assert result["duration_source"] == "llm"
    finally:
        duration_history.estimate_duration_from_history = original


if __name__ == "__main__":
    tests = [
        ("exact history wins",           test_history_tier_exact_match_wins),
        ("tag history",                  test_history_tier_tag_match),
        ("no history → confident LLM",   test_history_none_falls_to_llm_when_confident),
        ("no history → tag default",     test_history_none_falls_to_tag_default),
        ("no history, no tags → global", test_history_none_no_tags_global_fallback),
        ("history exception swallowed",  test_history_exception_does_not_break),
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