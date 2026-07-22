"""
Calendar analysis - Layer 1 (structural analysis) from the architecture.

Extracts deterministic signals from raw calendar events:
  - availability heatmap [day_of_week x hour]
  - typical working hours
  - average event durations by type
  - recurring events as fixed constraints
  - free slot recommendations within working hours

Designed to be robust to noisy / incomplete calendar data:
  - filters out non-blocking events (declined, transparent, OOO markers, birthdays)
  - normalizes timezones
  - handles all-day vs timed events differently
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple

from models import CalendarEventDto


DAYS_OF_WEEK = [
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
]

# Tunable thresholds for slot detection
ACTIVE_HOUR_THRESHOLD = 0.15   # > 15% busy ratio = "active" hour (was 0.05; too noisy)
FREE_HOUR_THRESHOLD = 0.20     # < 20% busy ratio = "consistently free" hour

# Time-weighting for events. Recent events should dominate the heatmap
# because they reflect the user's *current* routine (timezone, job, lifestyle).
# Future events are confirmed plans, weighted higher than any past statistic.
RECENCY_HALF_LIFE_DAYS = 60.0  # weight halves every 60 days into the past
FUTURE_EVENT_WEIGHT = 2.0      # future events count 2x a "today" event

# TODO: adapt thresholds and decay speed to sample size.
#   - Few weeks of data: lower ACTIVE_HOUR_THRESHOLD (any signal is precious),
#     slower decay (don't burn the only data we have).
#   - Years of data: keep current values or even faster decay.
#   Heuristic: detect period length from min/max event date, scale half-life
#   to e.g. min(60, period_days / 6) and threshold to max(0.05, 0.15 * recency_factor).
#
# TODO: pattern consistency boost.
#   Events that repeat at the same weekday-hour for many weeks (e.g. daily
#   standup at 9:00 for 6 months) should get an extra weight multiplier,
#   independent of recency. A one-off at 9:00 last week shouldn't look as
#   strong as 26 standups at 9:00 over half a year.
#   Implementation idea: group events by normalized title + weekday + hour,
#   count distinct dates the pattern occurred, apply boost = log1p(streak).


# ---------------------------------------------------------------------------
# Filtering: which events represent real busy time?
# ---------------------------------------------------------------------------

def classify_event(event: CalendarEventDto) -> Tuple[bool, Optional[str]]:
    """
    Returns (is_blocking, filter_reason).
    is_blocking == True means the event occupies real time on the user's schedule.
    """
    if event.status == "cancelled":
        return False, "cancelled"

    # Birthdays and working-location markers don't actually occupy work time
    if event.eventType == "birthday":
        return False, "birthday"
    if event.eventType == "workingLocation":
        return False, "working_location_marker"

    # transparency=transparent means "show as free"
    if event.transparency == "transparent":
        return False, "marked_transparent"

    # User declined the meeting => not actually attending
    if event.attendees:
        for a in event.attendees:
            if a.self_ and a.responseStatus == "declined":
                return False, "declined_by_user"

    # All-day events: useful info but not for hourly heatmap
    if event.start and event.start.date and not event.start.dateTime:
        return False, "all_day"

    if not event.start or not event.start.dateTime:
        return False, "no_start_time"
    if not event.end or not event.end.dateTime:
        return False, "no_end_time"

    return True, None


def get_event_times(event: CalendarEventDto) -> Optional[Tuple[datetime, datetime]]:
    """Return (start, end) as timezone-aware datetimes, or None if missing."""
    if not (event.start and event.start.dateTime
            and event.end and event.end.dateTime):
        return None
    start = event.start.dateTime
    end = event.end.dateTime
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if end <= start:
        return None
    return start, end


# ---------------------------------------------------------------------------
# Availability heatmap
# ---------------------------------------------------------------------------

def _event_weight(event_date, today) -> float:
    """
    Compute the weight of an event based on how far it is from today.

    - Future events: fixed high weight (they are confirmed plans).
    - Today: weight 1.0.
    - Past events: exponential decay with RECENCY_HALF_LIFE_DAYS.

    Example with half_life=60:
      today      -> 1.0
      30d ago    -> 0.71
      60d ago    -> 0.50
      180d ago   -> 0.125
      365d ago   -> 0.016
    """
    days_diff = (event_date - today).days
    if days_diff >= 0:
        return FUTURE_EVENT_WEIGHT
    return 0.5 ** (abs(days_diff) / RECENCY_HALF_LIFE_DAYS)


def build_availability_heatmap(
    events: List[CalendarEventDto],
) -> Dict[str, List[float]]:
    """
    Build a 7x24 matrix: busy_ratio[day_of_week][hour] in [0, 1].

    Each event contributes weighted minutes to its [weekday, hour] bucket.
    The denominator is also weighted: sum of weights of all calendar days of
    that weekday in the period. This keeps the ratio interpretable as
    "proportion of recent occurrences of this weekday-hour that were busy".

    Time-weighting:
      - Future events get FUTURE_EVENT_WEIGHT (confirmed plans dominate).
      - Past events decay exponentially with RECENCY_HALF_LIFE_DAYS.
        This makes the user's current routine (recent timezone, job, lifestyle)
        dominate over old patterns from 6+ months ago.

    Walking minute-by-hour-bucket correctly handles events that span multiple
    hours.
    """
    busy_weighted_minutes = [[0.0] * 24 for _ in range(7)]
    all_event_dates: list = []
    today = datetime.now(timezone.utc).date()

    for event in events:
        is_blocking, _ = classify_event(event)
        if not is_blocking:
            continue
        times = get_event_times(event)
        if not times:
            continue
        start, end = times

        all_event_dates.append(start.date())
        all_event_dates.append(end.date())

        weight = _event_weight(start.date(), today)

        # Bucket weighted event minutes into [day_of_week, hour] slots
        cur = start
        while cur < end:
            next_hour = (cur + timedelta(hours=1)).replace(
                minute=0, second=0, microsecond=0
            )
            chunk_end = min(next_hour, end)
            minutes = (chunk_end - cur).total_seconds() / 60.0
            busy_weighted_minutes[cur.weekday()][cur.hour] += minutes * weight
            cur = chunk_end

    # Build the denominator: sum of day-weights per weekday across the period.
    # Each calendar day in the period contributes its own time-weight,
    # so the ratio stays comparable to the old unweighted version.
    dow_weight_sum = [0.0] * 7
    if all_event_dates:
        period_start = min(all_event_dates)
        period_end = max(all_event_dates)
        d = period_start
        while d <= period_end:
            dow_weight_sum[d.weekday()] += _event_weight(d, today)
            d += timedelta(days=1)

    heatmap: Dict[str, List[float]] = {}
    for dow_idx, day_name in enumerate(DAYS_OF_WEEK):
        denom = max(dow_weight_sum[dow_idx], 1e-9)
        heatmap[day_name] = [
            round(min(busy_weighted_minutes[dow_idx][h] / (60.0 * denom), 1.0), 3)
            for h in range(24)
        ]
    return heatmap


# ---------------------------------------------------------------------------
# Working hours detection
# ---------------------------------------------------------------------------

def _longest_active_run(
    hours: List[float], threshold: float
) -> Optional[Tuple[int, int]]:
    """
    Find the longest contiguous run of consecutive hours above the threshold.
    Returns (start_hour, end_hour) where end is exclusive, or None.

    Why this beats min/max of active hours:
      - User has a 6am call once a week → busy_ratio at 6:00 = 0.15
      - Heavy 9-17 work → busy_ratio = 0.5+
      - Occasional 19:30 event → busy_ratio at 19:00 = 0.18
      - min/max: 6 to 20 (wrong - includes outliers)
      - longest run: 9 to 18 (right - captures the actual workday)
    """
    best_run: Optional[Tuple[int, int]] = None
    best_len = 0
    cur_start: Optional[int] = None

    for h in range(24):
        if hours[h] > threshold:
            if cur_start is None:
                cur_start = h
        else:
            if cur_start is not None:
                run_len = h - cur_start
                if run_len > best_len:
                    best_len = run_len
                    best_run = (cur_start, h)
                cur_start = None

    # Trailing run that goes up to hour 23
    if cur_start is not None:
        run_len = 24 - cur_start
        if run_len > best_len:
            best_run = (cur_start, 24)

    return best_run


def detect_working_hours(heatmap: Dict[str, List[float]]) -> Dict[str, Any]:
    """
    Per day of week, find the longest contiguous run of active hours.
    Then take the median start/end across days that have meaningful activity.

    A "meaningful" day must have at least 3 contiguous active hours -
    otherwise it's noise.
    """
    per_day_spans: List[Tuple[int, int]] = []
    active_days: List[str] = []

    for day in DAYS_OF_WEEK:
        hours = heatmap[day]
        run = _longest_active_run(hours, ACTIVE_HOUR_THRESHOLD)
        if run and (run[1] - run[0]) >= 3:
            active_days.append(day)
            per_day_spans.append(run)

    if not per_day_spans:
        return {
            "typical_start_hour": None,
            "typical_end_hour": None,
            "active_days": [],
        }

    starts = sorted(s for s, _ in per_day_spans)
    ends = sorted(e for _, e in per_day_spans)
    return {
        "typical_start_hour": starts[len(starts) // 2],
        "typical_end_hour": ends[len(ends) // 2],
        "active_days": active_days,
    }


# ---------------------------------------------------------------------------
# Event statistics by type
# ---------------------------------------------------------------------------

def calculate_event_stats(events: List[CalendarEventDto]) -> Dict[str, Any]:
    """Per-type and overall: count + average duration."""
    by_type: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {"count": 0, "total_minutes": 0.0}
    )
    total_count = 0
    total_minutes = 0.0

    for event in events:
        is_blocking, _ = classify_event(event)
        if not is_blocking:
            continue
        times = get_event_times(event)
        if not times:
            continue
        start, end = times
        duration_min = (end - start).total_seconds() / 60.0
        # Skip degenerate events
        if duration_min <= 0 or duration_min > 24 * 60:
            continue

        t = event.eventType or "default"
        by_type[t]["count"] += 1
        by_type[t]["total_minutes"] += duration_min
        total_count += 1
        total_minutes += duration_min

    by_type_out = {
        t: {
            "count": int(d["count"]),
            "average_duration_minutes": round(d["total_minutes"] / d["count"], 1),
        }
        for t, d in by_type.items() if d["count"]
    }

    return {
        "total_count": total_count,
        "average_duration_minutes": (
            round(total_minutes / total_count, 1) if total_count else 0.0
        ),
        "by_type": by_type_out,
    }


# ---------------------------------------------------------------------------
# Recurring events as fixed constraints
# ---------------------------------------------------------------------------

def find_recurring_events(events: List[CalendarEventDto]) -> List[Dict[str, Any]]:
    """Pull out events with RRULEs - they're hard constraints on the schedule."""
    out = []
    seen = set()
    for event in events:
        if not event.recurrence:
            continue
        if event.id in seen:
            continue
        seen.add(event.id)
        times = get_event_times(event)
        if not times:
            continue
        start, end = times
        duration_min = (end - start).total_seconds() / 60.0
        out.append({
            "id": event.id,
            "summary": event.summary or "Untitled",
            "day": DAYS_OF_WEEK[start.weekday()],
            "start_hour": start.hour,
            "start_minute": start.minute,
            "duration_minutes": round(duration_min),
            "rrule": event.recurrence,
        })
    return out


# ---------------------------------------------------------------------------
# Free slot recommendations
# ---------------------------------------------------------------------------

def find_free_slots(
    heatmap: Dict[str, List[float]],
    working_hours: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Within typical working hours, find consecutive hours that are usually free.
    Returns slots sorted by free-ness (lowest busy ratio first).
    """
    if working_hours["typical_start_hour"] is None:
        return []

    start_h: int = working_hours["typical_start_hour"]
    end_h: int = working_hours["typical_end_hour"]
    slots: List[Dict[str, Any]] = []

    for day in working_hours["active_days"]:
        hours = heatmap[day]
        slot_start: Optional[int] = None
        for h in range(start_h, end_h):
            is_free = hours[h] < FREE_HOUR_THRESHOLD
            if is_free and slot_start is None:
                slot_start = h
            elif not is_free and slot_start is not None:
                _emit(slots, day, slot_start, h, hours)
                slot_start = None
        if slot_start is not None:
            _emit(slots, day, slot_start, end_h, hours)

    slots.sort(key=lambda s: s["average_busy_ratio"])
    return slots


def _emit(slots, day, start, end, hours):
    if end - start < 1:
        return
    avg = sum(hours[start:end]) / (end - start)
    slots.append({
        "day": day,
        "start_hour": start,
        "end_hour": end,
        "duration_hours": end - start,
        "average_busy_ratio": round(avg, 3),
    })


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def analyze_calendar(events: List[CalendarEventDto]) -> Dict[str, Any]:
    """Run the full analysis pipeline and return the aggregated result."""
    blocking_count = 0
    filtered_reasons: Dict[str, int] = defaultdict(int)
    all_starts: List[datetime] = []

    for event in events:
        is_blocking, reason = classify_event(event)
        if is_blocking:
            blocking_count += 1
        else:
            filtered_reasons[reason or "unknown"] += 1
        times = get_event_times(event)
        if times:
            all_starts.append(times[0])

    date_range: Optional[Dict[str, str]] = None
    if all_starts:
        date_range = {
            "from": min(all_starts).isoformat(),
            "to": max(all_starts).isoformat(),
        }

    heatmap = build_availability_heatmap(events)
    working_hours = detect_working_hours(heatmap)
    event_stats = calculate_event_stats(events)
    recurring = find_recurring_events(events)
    free_slots = find_free_slots(heatmap, working_hours)

    return {
        "summary": {
            "total_events_received": len(events),
            "blocking_events": blocking_count,
            "filtered_events": dict(filtered_reasons),
            "date_range": date_range,
        },
        "availability_heatmap": heatmap,
        "working_hours": working_hours,
        "event_stats": event_stats,
        "recurring_events": recurring,
        "free_slot_recommendations": free_slots,
    }