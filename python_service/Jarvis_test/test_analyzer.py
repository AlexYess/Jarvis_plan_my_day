"""
Verify analyzer logic without requiring pydantic/fastapi installed.
We mock CalendarEventDto with SimpleNamespace - the analyzer only
accesses fields by attribute access, so this works.
"""
import sys
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta

# Stub the models module so analyzer's import succeeds
sys.modules['models'] = SimpleNamespace(CalendarEventDto=object)

from analyzer import analyze_calendar, classify_event, get_event_times


def NS(**kwargs):
    """Build nested SimpleNamespace defaulting all unset fields to None."""
    defaults = dict(
        kind=None, etag=None, id=None, status="confirmed", htmlLink=None,
        created=None, updated=None, summary=None, description=None,
        location=None, colorId=None, creator=None, organizer=None,
        start=None, end=None, endTimeUnspecified=None, recurrence=None,
        recurringEventId=None, originalStartTime=None, transparency=None,
        visibility=None, iCalUID=None, sequence=None, attendees=None,
        attendeesOmitted=None, extendedProperties=None, hangoutLink=None,
        conferenceData=None, gadget=None, anyoneCanAddSelf=None,
        guestsCanInviteOthers=None, guestsCanModify=None,
        guestsCanSeeOtherGuests=None, privateCopy=None, locked=None,
        reminders=None, source=None, workingLocationProperties=None,
        outOfOfficeProperties=None, focusTimeProperties=None,
        attachments=None, birthdayProperties=None, eventType=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def time_range(year, month, day, start_h, end_h, start_m=0, end_m=0):
    s = datetime(year, month, day, start_h, start_m, tzinfo=timezone.utc)
    e = datetime(year, month, day, end_h, end_m, tzinfo=timezone.utc)
    return SimpleNamespace(date=None, dateTime=s, timeZone="UTC"), \
           SimpleNamespace(date=None, dateTime=e, timeZone="UTC")


# Synthetic dataset - 4 weeks of a typical knowledge worker
events = []

# Daily standup 9:00-9:15 (recurring) - Mon to Fri for 4 weeks
base_monday = datetime(2026, 4, 6, tzinfo=timezone.utc)  # Mon Apr 6, 2026
for week in range(4):
    for dow in range(5):  # Mon-Fri
        d = (base_monday + timedelta(days=week * 7 + dow))
        s = SimpleNamespace(date=None,
                            dateTime=d.replace(hour=9, minute=0),
                            timeZone="UTC")
        e = SimpleNamespace(date=None,
                            dateTime=d.replace(hour=9, minute=15),
                            timeZone="UTC")
        events.append(NS(
            id=f"standup-{week}-{dow}",
            summary="Daily Standup",
            start=s, end=e,
            recurrence=["RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"]
                if (week == 0 and dow == 0) else None,
            eventType="default",
        ))

# Random meetings scattered through the weeks
meetings = [
    (4, 6, 11, 12, "Team sync"),
    (4, 7, 14, 15, "1:1 with manager"),
    (4, 8, 10, 11, "Design review"),
    (4, 9, 15, 17, "Quarterly planning"),
    (4, 13, 11, 12, "Team sync"),
    (4, 14, 14, 15, "1:1 with manager"),
    (4, 15, 13, 14, "Customer call"),
    (4, 16, 10, 11, "Design review"),
    (4, 20, 11, 12, "Team sync"),
    (4, 21, 14, 15, "1:1 with manager"),
    (4, 22, 16, 17, "Office hours"),
    (4, 27, 11, 12, "Team sync"),
    (4, 28, 14, 15, "1:1 with manager"),
]
for month, day, start_h, end_h, summary in meetings:
    s, e = time_range(2026, month, day, start_h, end_h)
    events.append(NS(id=f"mtg-{day}-{start_h}", summary=summary,
                     start=s, end=e, eventType="default"))

# Focus time blocks Tue/Thu mornings
for day in (7, 9, 14, 16, 21, 23, 28, 30):
    s, e = time_range(2026, 4, day, 10, 12)
    events.append(NS(id=f"focus-{day}", summary="Deep work",
                     start=s, end=e, eventType="focusTime"))

# Garbage data we should filter out
events.append(NS(id="bday1", summary="Mike's birthday",
                 start=SimpleNamespace(date="2026-04-15", dateTime=None, timeZone=None),
                 end=SimpleNamespace(date="2026-04-15", dateTime=None, timeZone=None),
                 eventType="birthday"))

events.append(NS(id="declined1", summary="Optional meeting",
                 start=time_range(2026, 4, 8, 16, 17)[0],
                 end=time_range(2026, 4, 8, 16, 17)[1],
                 attendees=[SimpleNamespace(
                     id=None, email=None, displayName=None,
                     organizer=None, self_=True, resource=None, optional=None,
                     responseStatus="declined", comment=None, additionalGuests=None,
                 )]))

events.append(NS(id="trans1", summary="Out for lunch",
                 start=time_range(2026, 4, 10, 13, 14)[0],
                 end=time_range(2026, 4, 10, 13, 14)[1],
                 transparency="transparent"))

events.append(NS(id="cancelled1", summary="Cancelled call",
                 start=time_range(2026, 4, 15, 10, 11)[0],
                 end=time_range(2026, 4, 15, 10, 11)[1],
                 status="cancelled"))

# Run the analysis
result = analyze_calendar(events)

import json
print("=" * 70)
print("ANALYSIS RESULT")
print("=" * 70)
print(json.dumps(result, indent=2, default=str))

# Sanity checks
print()
print("=" * 70)
print("SANITY CHECKS")
print("=" * 70)
s = result["summary"]
print(f"Total events received: {s['total_events_received']}")
print(f"Blocking events:       {s['blocking_events']}")
print(f"Filtered (by reason):  {s['filtered_events']}")

assert s["total_events_received"] == len(events), "event count mismatch"
assert s["filtered_events"].get("birthday") == 1
assert s["filtered_events"].get("declined_by_user") == 1
assert s["filtered_events"].get("marked_transparent") == 1
assert s["filtered_events"].get("cancelled") == 1

wh = result["working_hours"]
print(f"Working hours: {wh['typical_start_hour']}-{wh['typical_end_hour']}")
print(f"Active days:   {wh['active_days']}")
assert wh["typical_start_hour"] == 9, f"expected start=9, got {wh['typical_start_hour']}"
assert "saturday" not in wh["active_days"]
assert "sunday" not in wh["active_days"]

print(f"Recurring events found: {len(result['recurring_events'])}")
print(f"Free slot recommendations: {len(result['free_slot_recommendations'])}")

print()
print("Monday heatmap (busy ratio per hour):")
for h, ratio in enumerate(result["availability_heatmap"]["monday"]):
    if ratio > 0:
        bar = "#" * int(ratio * 40)
        print(f"  {h:02d}:00  {ratio:.2f}  {bar}")

print()
print("All checks passed.")
