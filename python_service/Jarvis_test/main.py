"""
FastAPI service for calendar analysis.

Layer 1: structural analysis (heatmap, working hours, free slots).
Layer 2: tag taxonomy management; classification endpoints added in Part 2.
"""

import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, List

from fastapi import FastAPI, HTTPException
from psycopg.errors import UniqueViolation

from analyzer import analyze_calendar
from classifier import repository as repo
from classifier import service as classifier_service
from config import settings
from db.connection import init_pool, close_pool
from models import (
    PatternAnalysisRequest,
    TagDto,
    CreateTagRequest,
    ClassifyEventsRequest,
    ClassifyTasksRequest,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("calendar_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the DB pool on startup, close on shutdown."""
    init_pool()
    logger.info("Service starting up")
    yield
    close_pool()
    logger.info("Service shut down")


app = FastAPI(
    title="Calendar Analysis Service",
    description=(
        "Analyzes Google Calendar events to extract scheduling patterns. "
        "Layer 1: structural analysis. Layer 2: LLM-based event tagging."
    ),
    version="0.3.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Layer 1: structural analysis (unchanged)
# ---------------------------------------------------------------------------

@app.post("/analyze")
async def analyze(request: PatternAnalysisRequest) -> Dict[str, Any]:
    logger.info(
        "Received %d events for analysis (userId=%s)",
        len(request.events), request.userId,
    )
    try:
        result = analyze_calendar(request.events)
    except Exception as exc:
        logger.exception("Analysis failed")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}")

    result["userId"] = request.userId
    logger.info(
        "Analysis complete for userId=%s: %d blocking, %d filtered",
        request.userId,
        result["summary"]["blocking_events"],
        sum(result["summary"]["filtered_events"].values()),
    )

    # Enrich with tag classification: get all unique event titles from
    # blocking events and classify them. The cache means this is cheap
    # after the first run.
    titles = _extract_unique_titles(request.events)
    if titles:
        try:
            classifications = classifier_service.classify_events(titles)
            result["classifications"] = classifications
            logger.info("Enriched with %d classifications", len(classifications))
        except Exception as exc:
            # Classification failure shouldn't break the whole analyze call -
            # Layer 1 results are still useful on their own.
            logger.exception("Classification failed; returning Layer 1 only")
            result["classification_error"] = str(exc)

    # Accumulate duration statistics into event_classifications cache.
    # This is what makes /classify/tasks able to use real user history
    # instead of generic LLM guesses.
    try:
        from classifier.duration_history import accumulate_duration_stats
        updated = accumulate_duration_stats(request.events)
        result["duration_stats_updated"] = updated
        logger.info("Duration stats updated for %d titles", updated)
    except Exception as exc:
        logger.exception("Duration accumulation failed; not blocking response")
        result["duration_stats_error"] = str(exc)

    return result


def _extract_unique_titles(events) -> list[str]:
    """Pull unique non-empty summaries from blocking events."""
    from analyzer import classify_event  # local import to avoid cycle
    seen = set()
    titles: list[str] = []
    for ev in events:
        is_blocking, _ = classify_event(ev)
        if not is_blocking:
            continue
        s = (ev.summary or "").strip()
        if not s or s.lower() in seen:
            continue
        seen.add(s.lower())
        titles.append(s)
    return titles


# ---------------------------------------------------------------------------
# Layer 2: event classification
# ---------------------------------------------------------------------------

@app.post("/classify/events")
async def classify_events(request: ClassifyEventsRequest) -> Dict[str, Any]:
    """
    Classify a batch of event titles against the current tag taxonomy.
    Uses the cache aggressively - only unseen titles hit the LLM.

    Returns: {title: [{"tag": str, "confidence": float}, ...]}
    """
    try:
        results = classifier_service.classify_events(
            request.titles,
            force_refresh=request.force_refresh,
        )
    except RuntimeError as exc:
        # API key missing / config issue
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Classification failed")
        raise HTTPException(status_code=500, detail=f"Classification failed: {exc}")

    return {"classifications": results, "count": len(results)}


@app.post("/classify/tasks")
async def classify_tasks(request: ClassifyTasksRequest) -> Dict[str, Any]:
    """
    Classify a batch of Google Tasks against the current tag taxonomy.
    Returns tags + estimated duration per task.

    Returns: {classifications: {title: {tags, estimated_duration_minutes,
                                        duration_confidence}}}
    """
    # We only need title + notes for classification - drop the rest
    task_dicts = [
        {"title": t.title, "notes": t.notes}
        for t in request.tasks
        if t.title  # skip tasks without titles
    ]

    try:
        results = classifier_service.classify_tasks(
            task_dicts,
            force_refresh=request.force_refresh,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Task classification failed")
        raise HTTPException(status_code=500, detail=f"Task classification failed: {exc}")

    return {"classifications": results, "count": len(results)}


# ---------------------------------------------------------------------------
# Layer 2: tag taxonomy management
# ---------------------------------------------------------------------------

@app.get("/tags", response_model=List[TagDto])
async def list_tags():
    """List all tags in the taxonomy."""
    return repo.list_tags()


@app.post("/tags", response_model=TagDto, status_code=201)
async def create_tag(request: CreateTagRequest):
    """
    Add a new tag. The next classification run will consider it.
    Existing classifications are not auto-recomputed; call
    POST /tags/invalidate-cache if you want to force re-classification.
    """
    try:
        row = repo.add_tag(
            name=request.name,
            description=request.description,
            parent_name=request.parent_name,
        )
    except UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail=f"Tag '{request.name}' already exists",
        )

    # Resolve parent name for the response
    parent_name = None
    if row.get("parent_tag_id"):
        for tag in repo.list_tags():
            if tag["id"] == row["parent_tag_id"]:
                parent_name = tag["name"]
                break

    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "parent_name": parent_name,
        "created_at": row["created_at"],
    }


@app.delete("/tags/{name}", status_code=204)
async def delete_tag(name: str):
    """Delete a tag. Child tags become top-level (parent_tag_id = NULL)."""
    if not repo.delete_tag(name):
        raise HTTPException(status_code=404, detail=f"Tag '{name}' not found")


@app.post("/tags/invalidate-cache")
async def invalidate_classifications():
    """
    Drop cached classifications whose tag snapshot differs from the current
    taxonomy. Call after adding/removing tags if you want stale entries
    re-classified on the next analyze call.
    """
    current = repo.get_tag_names()
    deleted = repo.invalidate_stale_classifications(current)
    return {"invalidated": deleted}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.SERVICE_HOST,
        port=settings.SERVICE_PORT,
        reload=True,
    )