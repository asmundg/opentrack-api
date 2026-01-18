"""
Build SchedulingResult from manually edited event schedule.

This module converts a manually edited event overview CSV back into a
SchedulingResult that can be used to generate HTML and athlete CSV outputs.
"""

from datetime import datetime
from typing import Any

from .dtos import EventScheduleRow
from .models import EventGroup, Athlete, Category, Event
from .types import SchedulingResult
from .event_csv import events_to_slot_assignments


def _is_fifa_event(event_schedule: EventScheduleRow) -> bool:
    """Check if an event is a FIFA (non-athletic) event."""
    return event_schedule.categories.strip().upper() == Category.fifa.value.upper()


def _create_fifa_event_group(event_schedule: EventScheduleRow) -> EventGroup:
    """Create a synthetic EventGroup for a FIFA (non-athletic) event."""
    # Create a minimal Event for the FIFA category
    fifa_event = Event(
        id=event_schedule.event_group_id,
        event_type=event_schedule.event_type,
        age_category=Category.fifa,
        start_time="",  # Will be set by scheduling
        duration_minutes=event_schedule.duration_minutes,
        personnel_required=0,
        priority_weight=0,
    )

    return EventGroup(
        id=event_schedule.event_group_id,
        event_type=event_schedule.event_type,
        events=[fifa_event],
    )


def build_scheduling_result_from_events(
    events: list[EventScheduleRow],
    event_groups: list[EventGroup],
    athletes: list[Athlete],
    base_date: datetime,
    slot_duration_minutes: int = 5,
) -> SchedulingResult:
    """
    Build a SchedulingResult from manually scheduled events.

    This does NOT run the optimizer - it takes the event times as-is and
    constructs a SchedulingResult that can be used to generate outputs.

    Args:
        events: List of manually scheduled events with times
        event_groups: List of event groups from original parsing
        athletes: List of athletes from original parsing
        base_date: Base datetime for the schedule
        slot_duration_minutes: Duration of each time slot

    Returns:
        SchedulingResult with the manual schedule
    """
    # Convert event times to slot assignments
    slot_assignments = events_to_slot_assignments(
        events, base_date, slot_duration_minutes
    )

    # Build event_group_map for lookup (includes original event groups)
    event_group_map = {eg.id: eg for eg in event_groups}

    # Create synthetic EventGroups for FIFA events
    fifa_event_groups: list[EventGroup] = []
    for event_schedule in events:
        if _is_fifa_event(event_schedule):
            fifa_group = _create_fifa_event_group(event_schedule)
            event_group_map[fifa_group.id] = fifa_group
            fifa_event_groups.append(fifa_group)

    # Build schedule dictionary
    schedule: dict[int, list[dict[str, Any]]] = {}
    events_per_slot: dict[int, int] = {}

    # Track which slots each event group occupies
    event_slot_ranges: dict[str, tuple[int, int]] = {}

    for event_schedule in events:
        group_id = event_schedule.event_group_id
        event_group = event_group_map.get(group_id)

        if not event_group:
            raise ValueError(f"Unknown event group ID: {group_id}")

        start_slot = slot_assignments[group_id]
        duration_slots = (event_schedule.duration_minutes + slot_duration_minutes - 1) // slot_duration_minutes
        end_slot = start_slot + duration_slots

        event_slot_ranges[group_id] = (start_slot, end_slot)

        # Add event to each slot it occupies
        for slot in range(start_slot, end_slot):
            if slot not in schedule:
                schedule[slot] = []
                events_per_slot[slot] = 0

            # Mark the first slot as the start
            is_start = (slot == start_slot)

            schedule[slot].append({
                'id': group_id,
                'event': event_group,
                'is_start': is_start,
                'slot': slot,
                'venue': event_schedule.venue,  # Preserve venue from CSV
            })

            if is_start:
                events_per_slot[slot] += 1

    # Calculate statistics
    total_slots = max(schedule.keys()) + 1 if schedule else 0
    total_duration_minutes = total_slots * slot_duration_minutes
    slots_with_events = len([s for s in events_per_slot.values() if s > 0])

    # Combine original event groups with FIFA event groups for the result
    all_event_groups = list(event_groups) + fifa_event_groups

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
            "total_events": len(events),
        },
        events=all_event_groups,
        athletes=athletes,
    )
