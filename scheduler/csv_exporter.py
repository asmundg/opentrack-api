"""CSV exporter for scheduled track meets.

Exports an updated copy of the input CSV with computed start times.
"""

import csv
from datetime import datetime, timedelta

from .functional_scheduler import SchedulingResult
from .models import EventGroup
from .isonen_parser import parse_event_type, parse_category


def export_schedule_csv(
    result: SchedulingResult,
    original_csv_path: str,
    output_path: str,
    start_hour: int = 9,
    start_minute: int = 0,
) -> None:
    """
    Export an updated copy of the input CSV with computed start times.

    Reads the original Isonen CSV and updates the "Kl." (time) and "Dato" (date)
    columns based on the computed schedule, preserving all other columns.

    Args:
        result: The scheduling result containing the computed schedule
        original_csv_path: Path to the original input CSV
        output_path: Path for the output CSV file
        start_hour: Starting hour for the schedule (24-hour format)
        start_minute: Starting minute for the schedule
    """
    if result.status != "solved":
        raise ValueError(f"Cannot export unsolved schedule: {result.status}")

    # Build mapping from (event_type, category) -> start time
    event_start_times = _build_event_start_times(
        result, start_hour, start_minute
    )

    # Read original CSV and update times
    rows = _read_and_update_csv(original_csv_path, event_start_times)

    # Write updated CSV
    _write_csv(output_path, rows)

    print(f"✅ Schedule CSV exported to: {output_path}")
    print(f"   {len(rows)} entries updated")


def _build_event_start_times(
    result: SchedulingResult,
    start_hour: int,
    start_minute: int,
) -> dict[tuple[str, str], datetime]:
    """Build mapping from (event_type, category) to scheduled start time."""
    base_time = datetime.now().replace(
        hour=start_hour, minute=start_minute, second=0, microsecond=0
    )
    slot_duration = result.slot_duration_minutes

    event_times: dict[tuple[str, str], datetime] = {}

    for slot, slot_events in result.schedule.items():
        for event_info in slot_events:
            if event_info.get("is_start", False):
                event_group: EventGroup = event_info["event"]
                slot_time = base_time + timedelta(minutes=slot * slot_duration)

                # Map each individual event in the group to this start time
                for event in event_group.events:
                    key = (event.event_type.value, event.age_category.value)
                    event_times[key] = slot_time

    return event_times


def _read_and_update_csv(
    csv_path: str,
    event_start_times: dict[tuple[str, str], datetime],
) -> list[dict[str, str]]:
    """Read original CSV and update the time column with scheduled times."""
    updated_rows: list[dict[str, str]] = []

    with open(csv_path, "r", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            # Try to find the scheduled time for this row
            event_name = row.get("Øvelse", "").strip()
            category_name = row.get("Klasse", "").strip()

            if event_name and category_name:
                try:
                    event_type = parse_event_type(event_name)
                    category = parse_category(category_name)
                    key = (event_type.value, category.value)

                    if key in event_start_times:
                        scheduled_time = event_start_times[key]
                        # Update the time column (Kl.)
                        row["Kl."] = scheduled_time.strftime("%H:%M")
                        # Update the date column (Dato)
                        row["Dato"] = scheduled_time.strftime("%d.%m.%Y")
                except ValueError:
                    # Keep original time if we can't parse
                    pass

            updated_rows.append(dict(row))

    return updated_rows


def _write_csv(output_path: str, rows: list[dict[str, str]]) -> None:
    """Write rows to CSV file."""
    if not rows:
        raise ValueError("No rows to write")

    fieldnames = list(rows[0].keys())

    with open(output_path, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
