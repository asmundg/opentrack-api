"""
Event overview CSV import/export for manual scheduling workflow.

This module handles the event overview CSV which contains start/end times
for each event group. This allows for manual adjustments between the initial
automated scheduling and final output generation.
"""

import csv
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

from .dtos import EventScheduleRow
from .models import EventGroup, get_venue_for_event
from .types import SchedulingResult


def result_to_event_schedule_rows(
    result: SchedulingResult,
    base_date: datetime,
    slot_duration_minutes: int = 5,
) -> list[EventScheduleRow]:
    """
    Convert a SchedulingResult to a list of EventScheduleRow objects.

    Args:
        result: The scheduling result from the optimizer
        base_date: Base datetime for the schedule (date + start time)
        slot_duration_minutes: Duration of each time slot in minutes

    Returns:
        List of EventScheduleRow objects sorted by start time
    """
    rows: list[EventScheduleRow] = []

    # Extract event groups and their assigned slots from the schedule
    for slot, events_in_slot in result.schedule.items():
        for event_info in events_in_slot:
            # Only process the start of each event, not continuations
            if not event_info.get('is_start', False):
                continue

            event_group_id = event_info['id']

            # Find the corresponding EventGroup
            event_group = next(
                (eg for eg in result.events if eg.id == event_group_id),
                None
            )
            if not event_group:
                continue

            # Calculate start and end times
            start_datetime = base_date + timedelta(minutes=slot * slot_duration_minutes)
            duration = event_group.duration_minutes
            end_datetime = start_datetime + timedelta(minutes=duration)

            # Get venue (use first event's category for venue determination)
            venue = get_venue_for_event(
                event_group.event_type,
                event_group.events[0].age_category if event_group.events else None
            )

            # Format categories as comma-separated list
            categories_str = ','.join(
                sorted(set(event.age_category.value for event in event_group.events))
            )

            row = EventScheduleRow(
                event_group_id=event_group_id,
                event_type=event_group.event_type,
                categories=categories_str,
                venue=venue,
                start_time=start_datetime.time(),
                end_time=end_datetime.time(),
                duration_minutes=duration,
            )
            rows.append(row)

    # Sort by start time, then by event type
    rows.sort(key=lambda r: (r.start_time, r.event_type.value))
    return rows


def export_event_overview_csv(
    result: SchedulingResult,
    output_path: Path,
    base_date: datetime,
    slot_duration_minutes: int = 5,
) -> None:
    """
    Export event overview CSV with start/end times for each event group.

    This CSV can be manually edited to adjust event times before regenerating
    the final schedule and athlete overview.

    Args:
        result: The scheduling result from the optimizer
        output_path: Path to write the CSV file
        base_date: Base datetime for the schedule (date + start time)
        slot_duration_minutes: Duration of each time slot in minutes
    """
    rows = result_to_event_schedule_rows(result, base_date, slot_duration_minutes)

    # Write to CSV
    with output_path.open('w', newline='', encoding='utf-8') as f:
        fieldnames = [
            'event_group_id',
            'event_type',
            'categories',
            'venue',
            'start_time',
            'end_time',
            'duration_minutes',
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            writer.writerow(row.to_csv_dict())

    print(f"✓ Event overview CSV exported to {output_path}")
    print(f"  Total events: {len(rows)}")
    print(f"  You can now manually edit event times and use 'schedule-from-events' to regenerate outputs")


def import_event_overview_csv(csv_path: Path) -> list[EventScheduleRow]:
    """
    Import and validate event overview CSV.

    Args:
        csv_path: Path to the event overview CSV file

    Returns:
        List of validated EventScheduleRow objects

    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If CSV is invalid or fails validation
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Event overview CSV not found: {csv_path}")

    rows: list[EventScheduleRow] = []

    with csv_path.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError("CSV file is empty or has no header")

        # Validate required columns
        required_columns = {
            'event_group_id',
            'event_type',
            'categories',
            'venue',
            'start_time',
            'end_time',
            'duration_minutes',
        }
        missing_columns = required_columns - set(reader.fieldnames)
        if missing_columns:
            raise ValueError(
                f"Missing required columns in CSV: {', '.join(missing_columns)}"
            )

        for line_num, row_dict in enumerate(reader, start=2):  # Start at 2 (header is 1)
            try:
                row = EventScheduleRow.from_csv_dict(row_dict)
                rows.append(row)
            except (ValueError, KeyError) as e:
                raise ValueError(
                    f"Validation error on line {line_num}: {e}"
                ) from e

    if not rows:
        raise ValueError("Event overview CSV contains no data rows")

    print(f"✓ Imported {len(rows)} events from {csv_path}")

    return rows


def events_to_slot_assignments(
    events: list[EventScheduleRow],
    base_date: datetime,
    slot_duration_minutes: int = 5,
) -> dict[str, int]:
    """
    Convert event times to slot assignments.

    Args:
        events: List of event schedule rows with times
        base_date: Base datetime for the schedule
        slot_duration_minutes: Duration of each time slot

    Returns:
        Dictionary mapping event_group_id to slot number

    Raises:
        ValueError: If event times don't align with slot boundaries
    """
    assignments: dict[str, int] = {}

    for event in events:
        # Calculate slot number from start time
        start_datetime = datetime.combine(base_date.date(), event.start_time)
        minutes_from_start = int((start_datetime - base_date).total_seconds() / 60)

        if minutes_from_start < 0:
            raise ValueError(
                f"Event {event.event_group_id} starts before base time: "
                f"{event.start_time} < {base_date.time()}"
            )

        # Check if start time aligns with slot boundaries
        if minutes_from_start % slot_duration_minutes != 0:
            raise ValueError(
                f"Event {event.event_group_id} start time {event.start_time} "
                f"does not align with {slot_duration_minutes}-minute slot boundaries. "
                f"Expected start times at: :00, :05, :10, :15, etc."
            )

        slot = minutes_from_start // slot_duration_minutes
        assignments[event.event_group_id] = slot

    return assignments
