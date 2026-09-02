"""HTML grid rendering: an event's row span must match its scheduled window."""

import html
import re

from .html_schedule_generator import generate_html_schedule_table
from .models import Athlete, Category, Event, EventGroup, EventType, Venue
from .types import SchedulingResult


def _event(event_id: str, category: Category, participants: int) -> Event:
    return Event(
        id=event_id,
        event_type=EventType.hj,
        age_category=category,
        start_time="2026-09-02T17:00:00",
        duration_minutes=6,
        personnel_required=1,
        priority_weight=8,
        participants=participants,
    )


def _result() -> SchedulingResult:
    """Two high jump groups, back to back at one venue.

    The first is scheduled a 25-minute window (5 slots) but three athletes in a
    vertical jump are estimated at 32 minutes, as happens whenever a small field
    is entitled to more time per attempt than the layout allotted.
    """
    first = EventGroup(
        id="Hoyde_Rekrutt",
        event_type=EventType.hj,
        events=[_event("hj_rek", Category.g10, 3)],
    )
    second = EventGroup(
        id="Hoyde_11_12",
        event_type=EventType.hj,
        events=[_event("hj_11", Category.g11, 4)],
    )
    assert first.duration_minutes > 25, "fixture must overrun its window"

    schedule: dict[int, list[dict]] = {}
    for slot in range(0, 5):  # 17:00-17:25, the first group's window
        schedule[slot] = [
            {"id": first.id, "event": first, "is_start": slot == 0,
             "slot": slot, "venue": Venue.HIGH_JUMP_AREA}
        ]
    for slot in range(5, 11):  # 17:25-17:55, immediately after
        schedule[slot] = [
            {"id": second.id, "event": second, "is_start": slot == 5,
             "slot": slot, "venue": Venue.HIGH_JUMP_AREA}
        ]

    return SchedulingResult(
        status="solved",
        schedule=schedule,
        total_slots=11,
        total_duration_minutes=55,
        slot_duration_minutes=5,
        events_per_slot={0: 1, 5: 1},
        slots_with_events=2,
        optimization_stats={"manual_schedule": True},
        events=[first, second],
        athletes=[Athlete(name="Someone", events=list(first.events))],
    )


def _rendered_rows(html_text: str) -> str:
    """Visible text of the schedule table, so assertions ignore CSS and markup."""
    body = re.sub(r"<(script|style)\b.*?</\1>", "", html_text, flags=re.S)
    rows = re.findall(r"<tr.*?</tr>", body, re.S)
    return "\n".join(
        " ".join(html.unescape(re.sub(r"<[^>]+>", " ", row)).split()) for row in rows
    )


def test_an_overrunning_estimate_does_not_swallow_the_next_event():
    """The row span comes from the scheduled window, not the duration estimate.

    A span built from the estimate covers 7 slots where only 5 were scheduled,
    so the next group's cell is skipped as covered and vanishes from the grid.
    """
    rendered = _rendered_rows(
        generate_html_schedule_table(_result(), start_hour=17, start_minute=0)
    )
    assert "G11" in rendered, (
        f"the following event was dropped from the rendered grid:\n{rendered}"
    )


def test_each_group_starts_in_its_scheduled_slot():
    rendered = _rendered_rows(
        generate_html_schedule_table(_result(), start_hour=17, start_minute=0)
    )
    assert re.search(r"17:00 .*G-Rekrutt", rendered)
    assert re.search(r"17:25 .*G11", rendered)
