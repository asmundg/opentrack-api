"""
Constraint validation for manually scheduled events.

This module validates that a manually edited schedule still satisfies all
scheduling constraints without recomputing the schedule. Used when importing
event overview CSVs after manual adjustments.
"""

from collections import defaultdict

from .dtos import EventScheduleRow
from .models import (
    EventGroup,
    Athlete,
    Venue,
    Category,
    get_track_event_order,
    get_category_age_order,
    TRACK_DISTANCE_ORDER,
)


def _is_fifa_event(event_schedule: EventScheduleRow) -> bool:
    """Check if an event is a FIFA (non-athletic) event."""
    return event_schedule.categories.strip().upper() == Category.fifa.value.upper()


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
    # Separate FIFA events (non-athletic, like breaks) from regular events
    # FIFA events are allowed in the schedule but are not validated against event groups
    regular_events = [e for e in events if not _is_fifa_event(e)]

    # Build lookup from event_group_id to EventScheduleRow (regular events only)
    event_schedule_map = {e.event_group_id: e for e in regular_events}

    # Build lookup from event_group_id to EventGroup
    event_group_map = {eg.id: eg for eg in event_groups}

    # Check that all event groups have schedule entries
    missing_groups = set(event_group_map.keys()) - set(event_schedule_map.keys())
    if missing_groups:
        raise ConstraintViolation(
            f"Missing schedule entries for event groups: {', '.join(sorted(missing_groups))}"
        )

    # Check for extra schedule entries (FIFA events are allowed as extras)
    extra_entries = set(event_schedule_map.keys()) - set(event_group_map.keys())
    if extra_entries:
        raise ConstraintViolation(
            f"Schedule contains unknown event groups: {', '.join(sorted(extra_entries))}"
        )

    # Validate venue conflicts (no two events at same venue at same time)
    # Include FIFA events - they still occupy physical space
    _validate_venue_conflicts(events)

    # Validate athlete conflicts (athletes can't compete in overlapping events)
    # Only check regular events - FIFA events have no athletes
    _validate_athlete_conflicts(event_groups, athletes, event_schedule_map)

    # Validate track event ordering constraints (FIFA events are not track events)
    _validate_track_ordering(event_groups, event_schedule_map)

    print("✓ All constraints validated successfully")


def _validate_venue_conflicts(
    events: list[EventScheduleRow],
) -> None:
    """Validate that no two events use the same venue at overlapping times."""

    # Group events by venue and check for time overlaps
    # Use event_group_id as identifier (works for both regular and FIFA events)
    venue_events: dict[Venue, list[tuple[EventScheduleRow, str]]] = defaultdict(list)

    for event_schedule in events:
        # For FIFA events, use the event_group_id directly as the label
        # For regular events, use the event group id
        event_id = event_schedule.event_group_id
        venue_events[event_schedule.venue].append((event_schedule, event_id))

    # Check each venue for overlapping events
    for venue, venue_event_list in venue_events.items():
        # Sort by start time
        venue_event_list.sort(key=lambda x: x[0].start_time)

        # Check consecutive events for overlap
        for i in range(len(venue_event_list) - 1):
            current_event, current_id = venue_event_list[i]
            next_event, next_id = venue_event_list[i + 1]

            # Events overlap if next starts before current ends
            if next_event.start_time < current_event.end_time:
                raise ConstraintViolation(
                    f"Venue conflict at {venue.value}: "
                    f"{current_id} ({current_event.start_time}-{current_event.end_time}) "
                    f"overlaps with {next_id} ({next_event.start_time}-{next_event.end_time})"
                )


def _validate_athlete_conflicts(
    event_groups: list[EventGroup],
    athletes: list[Athlete],
    event_schedule_map: dict[str, EventScheduleRow],
) -> None:
    """Validate that no athlete has overlapping events."""

    # Build mapping from event ID to event group
    event_to_group: dict[str, EventGroup] = {}
    for group in event_groups:
        for event in group.events:
            event_to_group[event.id] = group

    # Check each athlete's schedule
    for athlete in athletes:
        # Get all event groups this athlete participates in (deduplicate by group)
        athlete_groups = []
        seen_group_ids: set[str] = set()
        for event in athlete.events:
            group = event_to_group.get(event.id)
            if group and group.id in event_schedule_map and group.id not in seen_group_ids:
                seen_group_ids.add(group.id)
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

        # If same event type, check age ordering (younger first) - SOFT CONSTRAINT
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
                # Age ordering is a soft constraint - warn but don't fail
                print(
                    f"⚠️  Track age ordering (soft constraint): {current_group.event_type.value} "
                    f"has younger categories ({next_cats}) after older categories ({current_cats})"
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
