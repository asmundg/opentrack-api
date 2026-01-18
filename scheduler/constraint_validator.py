"""
Constraint validation for manually scheduled events.

This module validates that a manually edited schedule still satisfies all
scheduling constraints without recomputing the schedule. Used when importing
event overview CSVs after manual adjustments.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from .dtos import EventScheduleRow
from .models import (
    EventGroup,
    Athlete,
    Venue,
    get_venue_for_event,
    get_track_event_order,
    get_category_age_order,
    is_hurdles_event,
    EventVenueMapping,
    TRACK_DISTANCE_ORDER,
)


class ConstraintViolation(Exception):
    """Raised when a scheduling constraint is violated."""

    pass


def validate_event_schedule(
    events: list[EventScheduleRow],
    event_groups: list[EventGroup],
    athletes: list[Athlete],
    slot_duration_minutes: int = 5,
) -> None:
    """
    Validate that the event schedule satisfies all hard constraints.

    This does NOT recompute the schedule - it only validates the given times.

    Args:
        events: List of event schedule rows with start/end times
        event_groups: List of event groups from the original schedule
        athletes: List of athletes with their events
        slot_duration_minutes: Duration of each time slot

    Raises:
        ConstraintViolation: If any constraint is violated
    """
    # Build lookup from event_group_id to EventScheduleRow
    event_schedule_map = {e.event_group_id: e for e in events}

    # Build lookup from event_group_id to EventGroup
    event_group_map = {eg.id: eg for eg in event_groups}

    # Check that all event groups have schedule entries
    missing_groups = set(event_group_map.keys()) - set(event_schedule_map.keys())
    if missing_groups:
        raise ConstraintViolation(
            f"Missing schedule entries for event groups: {', '.join(sorted(missing_groups))}"
        )

    # Check for extra schedule entries
    extra_entries = set(event_schedule_map.keys()) - set(event_group_map.keys())
    if extra_entries:
        raise ConstraintViolation(
            f"Schedule contains unknown event groups: {', '.join(sorted(extra_entries))}"
        )

    # Validate venue conflicts (no two events at same venue at same time)
    _validate_venue_conflicts(events, event_groups, event_schedule_map, slot_duration_minutes)

    # Validate athlete conflicts (athletes can't compete in overlapping events)
    _validate_athlete_conflicts(events, event_groups, athletes, event_schedule_map, slot_duration_minutes)

    # Validate track event ordering constraints
    _validate_track_ordering(events, event_groups, event_schedule_map)

    print("✓ All constraints validated successfully")


def _validate_venue_conflicts(
    events: list[EventScheduleRow],
    event_groups: list[EventGroup],
    event_schedule_map: dict[str, EventScheduleRow],
    slot_duration_minutes: int,
) -> None:
    """Validate that no two events use the same venue at overlapping times."""

    # Group events by venue and check for time overlaps
    venue_events: dict[Venue, list[tuple[EventScheduleRow, EventGroup]]] = defaultdict(list)

    for event_schedule in events:
        event_group = event_groups[next(
            i for i, eg in enumerate(event_groups) if eg.id == event_schedule.event_group_id
        )]
        venue_events[event_schedule.venue].append((event_schedule, event_group))

    # Check each venue for overlapping events
    for venue, venue_event_list in venue_events.items():
        # Sort by start time
        venue_event_list.sort(key=lambda x: x[0].start_time)

        # Check consecutive events for overlap
        for i in range(len(venue_event_list) - 1):
            current_event, current_group = venue_event_list[i]
            next_event, next_group = venue_event_list[i + 1]

            # Events overlap if next starts before current ends
            if next_event.start_time < current_event.end_time:
                raise ConstraintViolation(
                    f"Venue conflict at {venue.value}: "
                    f"{current_group.id} ({current_event.start_time}-{current_event.end_time}) "
                    f"overlaps with {next_group.id} ({next_event.start_time}-{next_event.end_time})"
                )


def _validate_athlete_conflicts(
    events: list[EventScheduleRow],
    event_groups: list[EventGroup],
    athletes: list[Athlete],
    event_schedule_map: dict[str, EventScheduleRow],
    slot_duration_minutes: int,
) -> None:
    """Validate that no athlete has overlapping events."""

    # Build mapping from event ID to event group
    event_to_group: dict[str, EventGroup] = {}
    for group in event_groups:
        for event in group.events:
            event_to_group[event.id] = group

    # Check each athlete's schedule
    for athlete in athletes:
        # Get all event groups this athlete participates in
        athlete_groups = []
        for event in athlete.events:
            group = event_to_group.get(event.id)
            if group and group.id in event_schedule_map:
                schedule = event_schedule_map[group.id]
                athlete_groups.append((schedule, group))

        if not athlete_groups:
            continue

        # Sort by start time
        athlete_groups.sort(key=lambda x: x[0].start_time)

        # Check consecutive events for overlap
        for i in range(len(athlete_groups) - 1):
            current_schedule, current_group = athlete_groups[i]
            next_schedule, next_group = athlete_groups[i + 1]

            if next_schedule.start_time < current_schedule.end_time:
                raise ConstraintViolation(
                    f"Athlete conflict for {athlete.name}: "
                    f"{current_group.id} ({current_schedule.start_time}-{current_schedule.end_time}) "
                    f"overlaps with {next_group.id} ({next_schedule.start_time}-{next_schedule.end_time})"
                )


def _validate_track_ordering(
    events: list[EventScheduleRow],
    event_groups: list[EventGroup],
    event_schedule_map: dict[str, EventScheduleRow],
) -> None:
    """
    Validate track event ordering constraints.

    Track events must follow a specific order based on:
    1. Distance (60m, 100m, 200m, etc.)
    2. Hurdles come after their base distance
    3. Within same distance, younger categories first
    """

    # Get all track events
    track_events = [
        (event_schedule_map[eg.id], eg)
        for eg in event_groups
        if eg.event_type in TRACK_DISTANCE_ORDER
        and eg.id in event_schedule_map
    ]

    if len(track_events) <= 1:
        return  # No ordering to check

    # Sort by start time
    track_events.sort(key=lambda x: x[0].start_time)

    # Check ordering constraints
    for i in range(len(track_events) - 1):
        current_schedule, current_group = track_events[i]
        next_schedule, next_group = track_events[i + 1]

        current_order = get_track_event_order(current_group.event_type)
        next_order = get_track_event_order(next_group.event_type)

        # If next event is of an earlier distance type, that's a violation
        if next_order < current_order:
            raise ConstraintViolation(
                f"Track event ordering violation: "
                f"{next_group.event_type.value} (order {next_order}) "
                f"cannot come after {current_group.event_type.value} (order {current_order}). "
                f"Track events must follow distance order: {', '.join(e.value for e in TRACK_DISTANCE_ORDER)}"
            )

        # If same event type, check age ordering (younger first)
        if current_group.event_type == next_group.event_type:
            # Get youngest category in each group
            current_youngest = min(
                (get_category_age_order(e.age_category) for e in current_group.events),
                default=99
            )
            next_youngest = min(
                (get_category_age_order(e.age_category) for e in next_group.events),
                default=99
            )

            if next_youngest < current_youngest:
                current_cats = ','.join(e.age_category.value for e in current_group.events)
                next_cats = ','.join(e.age_category.value for e in next_group.events)
                raise ConstraintViolation(
                    f"Track age ordering violation for {current_group.event_type.value}: "
                    f"Younger categories ({next_cats}) cannot come after older categories ({current_cats})"
                )


def validate_and_report(
    events: list[EventScheduleRow],
    event_groups: list[EventGroup],
    athletes: list[Athlete],
    slot_duration_minutes: int = 5,
) -> tuple[bool, list[str]]:
    """
    Validate event schedule and return detailed report.

    Args:
        events: List of event schedule rows
        event_groups: List of event groups
        athletes: List of athletes
        slot_duration_minutes: Duration of each time slot

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors: list[str] = []

    try:
        validate_event_schedule(events, event_groups, athletes, slot_duration_minutes)
        return (True, [])
    except ConstraintViolation as e:
        errors.append(str(e))
        return (False, errors)
