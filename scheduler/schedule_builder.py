"""Build a SchedulingResult from the agent's event-overview layout.

Each CSV row places a set of (event_type, category) atoms at a time window/venue.
This module turns those rows back into a SchedulingResult (one synthesized
EventGroup per row) so the HTML and athlete CSV can be generated. It does NOT run
the optimizer and does NOT recompute any grouping; the row's start/end window is the
authoritative occupancy.
"""

from datetime import datetime
from typing import Any

from .dtos import EventScheduleRow
from .models import Athlete, Category, Event, EventGroup, EventType
from .types import SchedulingResult
from .event_csv import events_to_slot_assignments


def _is_fifa_event(row: EventScheduleRow) -> bool:
    """Check if a row is a FIFA (non-athletic) event."""
    return row.categories.strip().upper() == Category.fifa.value.upper()


def _window_minutes(row: EventScheduleRow) -> int:
    """Authoritative occupancy of a row: end_time - start_time in minutes."""
    start = datetime.combine(datetime.today(), row.start_time)
    end = datetime.combine(datetime.today(), row.end_time)
    return int((end - start).total_seconds() / 60)


def _fifa_group(row: EventScheduleRow) -> EventGroup:
    """Create a synthetic EventGroup for a FIFA (non-athletic) row."""
    fifa_event = Event(
        id=row.event_group_id,
        event_type=row.event_type,
        age_category=Category.fifa,
        start_time="",
        duration_minutes=_window_minutes(row),
        personnel_required=0,
        priority_weight=0,
    )
    return EventGroup(
        id=row.event_group_id, event_type=row.event_type, events=[fifa_event]
    )


def _row_group(
    row: EventScheduleRow,
    atom_by_key: dict[tuple[EventType, Category], Event],
) -> EventGroup:
    """Synthesize an EventGroup for a row from its (event_type, category) atoms."""
    events: list[Event] = []
    for raw in row.categories.split(','):
        name = raw.strip()
        if not name:
            continue
        atom = atom_by_key.get((row.event_type, Category(name)))
        if atom is None:
            raise ValueError(
                f"Row {row.event_group_id} references {row.event_type.value} {name} "
                f"with no registered athletes"
            )
        events.append(atom)
    return EventGroup(id=row.event_group_id, event_type=row.event_type, events=events)


def build_scheduling_result_from_events(
    rows: list[EventScheduleRow],
    atom_events: list[Event],
    athletes: list[Athlete],
    base_date: datetime,
    slot_duration_minutes: int = 5,
) -> SchedulingResult:
    """Build a SchedulingResult from the agent's layout rows.

    Args:
        rows: event-overview rows with merges and times.
        atom_events: raw (event_type, category) events parsed from the XLSX.
        athletes: athletes from the original parsing.
        base_date: base datetime (date + earliest start) for slot math.

    Returns:
        SchedulingResult mirroring the manual layout.
    """
    slot_assignments = events_to_slot_assignments(
        rows, base_date, slot_duration_minutes
    )

    atom_by_key = {(e.event_type, e.age_category): e for e in atom_events}

    event_groups: list[EventGroup] = []
    for row in rows:
        if _is_fifa_event(row):
            event_groups.append(_fifa_group(row))
        else:
            event_groups.append(_row_group(row, atom_by_key))
    group_by_id = {g.id: g for g in event_groups}

    schedule: dict[int, list[dict[str, Any]]] = {}
    events_per_slot: dict[int, int] = {}

    for row in rows:
        group_id = row.event_group_id
        event_group = group_by_id[group_id]

        start_slot = slot_assignments[group_id]
        window = _window_minutes(row)
        duration_slots = (window + slot_duration_minutes - 1) // slot_duration_minutes
        end_slot = start_slot + duration_slots

        for slot in range(start_slot, end_slot):
            if slot not in schedule:
                schedule[slot] = []
                events_per_slot[slot] = 0

            is_start = (slot == start_slot)
            schedule[slot].append({
                'id': group_id,
                'event': event_group,
                'is_start': is_start,
                'slot': slot,
                'venue': row.venue,
            })
            if is_start:
                events_per_slot[slot] += 1

    total_slots = max(schedule.keys()) + 1 if schedule else 0
    total_duration_minutes = total_slots * slot_duration_minutes
    slots_with_events = len([s for s in events_per_slot.values() if s > 0])

    return SchedulingResult(
        status="solved",
        schedule=schedule,
        total_slots=total_slots,
        total_duration_minutes=total_duration_minutes,
        slot_duration_minutes=slot_duration_minutes,
        events_per_slot=events_per_slot,
        slots_with_events=slots_with_events,
        optimization_stats={
            "manual_schedule": True,
            "total_events": len(rows),
        },
        events=event_groups,
        athletes=athletes,
    )
