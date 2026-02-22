"""Parser for Isonen CSV exports to convert registration data to events and athletes."""

import csv
from datetime import datetime
from typing import Any

from .models import Athlete, Category, Event, EventType


def parse_event_type(ovelse: str) -> EventType:
    """Map Norwegian event names from CSV to EventType enum."""
    mapping = {
        "60 meter": EventType.m60,
        "100 meter": EventType.m100,
        "200 meter": EventType.m200,
        "400 meter": EventType.m400,
        "800 meter": EventType.m800,
        "1500 meter": EventType.m1500,
        "5000 meter": EventType.m5000,
        "60 meter hekk": EventType.m60_hurdles,
        "80 meter hekk": EventType.m80_hurdles,
        "100 meter hekk": EventType.m100_hurdles,
        "Kule": EventType.sp,
        "Lengde": EventType.lj,
        "Tresteg": EventType.tj,
        "Høyde": EventType.hj,
        "Diskos": EventType.dt,
        "Spyd": EventType.jt,
        "Slegge": EventType.ht,
        "Liten ball": EventType.bt,
        "Stavsprang": EventType.pv,
    }

    if ovelse not in mapping:
        raise ValueError(f"Unknown event type: {ovelse}")

    return mapping[ovelse]


def parse_category(klasse: str) -> Category:
    """Map Norwegian category names from CSV to Category enum."""
    mapping = {
        "Jenter 6-8 Rekrutt": Category.j10,
        "Jenter 9": Category.j10,
        "Jenter 10": Category.j10,
        "Jenter 11": Category.j11,
        "Jenter 12": Category.j12,
        "Jenter 13": Category.j13,
        "Jenter 14": Category.j14,
        "Jenter 15": Category.j15,
        "Jenter 16": Category.j16,
        "Jenter 17": Category.j17,
        "Jenter 18/19": Category.j18_19,
        "Jenter 18-19": Category.j18_19,
        "Gutter 6-8 Rekrutt": Category.g10,
        "Gutter 9": Category.g10,
        "Gutter 10": Category.g10,
        "Gutter 11": Category.g11,
        "Gutter 12": Category.g12,
        "Gutter 13": Category.g13,
        "Gutter 14": Category.g14,
        "Gutter 15": Category.g15,
        "Gutter 16": Category.g16,
        "Gutter 17": Category.g17,
        "Gutter 18/19": Category.g18_19,
        "Gutter 18-19": Category.g18_19,
        "Kvinner Senior": Category.ks,
        "Menn Senior": Category.ms,  # Fixed the typo
        "Menn senior": Category.ms,  # Handle both variations
        "Kvinner senior": Category.ks,  # Handle both variations
    }

    if klasse not in mapping:
        raise ValueError(f"Unknown category: {klasse}")

    return mapping[klasse]


def _calculate_event_priority(event_type: EventType, category: Category) -> int:
    """Calculate priority weight for events based on type and category."""
    # Track events get higher priority
    track_events = {
        EventType.m60,
        EventType.m100,
        EventType.m200,
        EventType.m400,
        EventType.m800,
        EventType.m1500,
        EventType.m5000,
        EventType.m60_hurdles,
        EventType.m80_hurdles,
        EventType.m100_hurdles,
    }

    base_priority = 10 if event_type in track_events else 8

    # Senior events get slightly higher priority
    if category in {Category.ks, Category.ms}:
        base_priority += 2

    return base_priority


def _calculate_personnel_required(event_type: EventType) -> int:
    """Calculate personnel required based on event type."""
    # Track events need more personnel
    track_events = {
        EventType.m60,
        EventType.m100,
        EventType.m200,
        EventType.m400,
        EventType.m800,
        EventType.m1500,
        EventType.m5000,
        EventType.m60_hurdles,
        EventType.m80_hurdles,
        EventType.m100_hurdles,
    }

    if event_type in track_events:
        return 8
    elif event_type in {EventType.sp, EventType.dt, EventType.ht}:
        return 4
    else:
        return 3


def _calculate_event_duration(
    event_type: EventType, category: Category, participant_count: int
) -> int:
    """Calculate event duration based on type, category, and participant count."""
    from .models import EventCategoryDurationOverride, EventDuration

    # Check for specific overrides first
    override_key = (event_type, category)
    if override_key in EventCategoryDurationOverride:
        base_duration = EventCategoryDurationOverride[override_key]
    else:
        base_duration = EventDuration[event_type]

    # For field events, duration scales with participant count
    field_events = {
        EventType.sp,
        EventType.dt,
        EventType.jt,
        EventType.ht,
        EventType.bt,
        EventType.lj,
        EventType.tj,
        EventType.hj,
        EventType.pv,
    }

    if event_type in field_events:
        # Scale duration based on participant count
        # For field events, multiply base duration by participant count
        scaled_duration = base_duration * max(1, participant_count)

        # Add setup time for jumping events
        jumping_events = {EventType.hj, EventType.pv}
        if event_type in jumping_events:
            scaled_duration += 5  # 5 minutes setup time

        return min(scaled_duration, 60)  # Cap at 60 minutes

    # Track events: multiply by number of heats (max 8 per heat)
    heats = -(-max(1, participant_count) // 8)  # ceil division
    return base_duration * heats


def parse_isonen_csv(csv_file_path: str) -> tuple[list[Event], list[Athlete]]:
    """
    Parse an Isonen CSV export and return events and athletes.

    Args:
        csv_file_path: Path to the CSV file

    Returns:
        Tuple of (events, athletes)

    Raises:
        ValueError: If CSV contains invalid data that cannot be parsed
        FileNotFoundError: If CSV file doesn't exist
    """
    events: dict[str, Event] = {}
    athletes_data: dict[str, dict[str, Any]] = {}

    try:
        with open(csv_file_path, "r", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)

            for row in reader:
                # Extract athlete info
                first_name = row["Fornavn"].strip()
                last_name = row["Etternavn"].strip()
                athlete_name = f"{first_name} {last_name}"

                # Skip if no name
                if not first_name and not last_name:
                    continue

                # Extract event info
                event_name = row["Øvelse"].strip()
                category_name = row["Klasse"].strip()
                date_str = row["Dato"].strip()
                time_str = row["Kl."].strip()

                # Skip if missing essential event data
                if not event_name or not category_name:
                    continue

                try:
                    event_type = parse_event_type(event_name)
                    category = parse_category(category_name)
                except ValueError as e:
                    print(f"Warning: Skipping row due to parsing error: {e}")
                    continue

                # Create unique event ID
                event_id = f"{event_type.value}_{category.value}"

                # Parse datetime
                try:
                    # Combine date and time into ISO format
                    if date_str and time_str:
                        event_datetime = datetime.strptime(
                            f"{date_str} {time_str}", "%d.%m.%Y %H:%M"
                        )
                        start_time = event_datetime.isoformat()
                    else:
                        # Default to a reasonable time if not specified
                        start_time = (
                            datetime.now()
                            .replace(hour=9, minute=0, second=0, microsecond=0)
                            .isoformat()
                        )
                except ValueError:
                    # Fallback if datetime parsing fails
                    start_time = (
                        datetime.now()
                        .replace(hour=9, minute=0, second=0, microsecond=0)
                        .isoformat()
                    )

                # Track athlete-event relationships
                if athlete_name not in athletes_data:
                    athletes_data[athlete_name] = {"events": []}
                athletes_data[athlete_name]["events"].append(event_id)

                # Create or update event (count participants)
                if event_id not in events:
                    events[event_id] = Event(
                        id=event_id,
                        event_type=event_type,
                        age_category=category,
                        start_time=start_time,
                        duration_minutes=0,  # Will be calculated later
                        personnel_required=_calculate_personnel_required(event_type),
                        priority_weight=_calculate_event_priority(event_type, category),
                    )

    except FileNotFoundError:
        raise FileNotFoundError(f"CSV file not found: {csv_file_path}")
    except UnicodeDecodeError:
        raise ValueError(
            f"Could not decode CSV file. Please ensure it's UTF-8 encoded: {csv_file_path}"
        )

    if not events:
        raise ValueError("No valid events found in CSV file")

    # Calculate participant counts and update durations
    event_participant_counts: dict[str, int] = {}
    for athlete_data in athletes_data.values():
        for event_id in athlete_data["events"]:
            event_participant_counts[event_id] = (
                event_participant_counts.get(event_id, 0) + 1
            )

    # Update event durations based on participant counts
    for event_id, event in events.items():
        participant_count = event_participant_counts.get(event_id, 1)
        event.duration_minutes = _calculate_event_duration(
            event.event_type, event.age_category, participant_count
        )

    # Create athlete objects with references to event objects
    athletes: list[Athlete] = []
    for athlete_name, athlete_data in athletes_data.items():
        athlete_events: list[Event] = []
        for event_id in athlete_data["events"]:
            if event_id in events:
                athlete_events.append(events[event_id])

        if athlete_events:  # Only create athlete if they have valid events
            athletes.append(Athlete(name=athlete_name, events=athlete_events))

    events_list = list(events.values())

    print(
        f"Parsed {len(events_list)} unique events and {len(athletes)} athletes from CSV"
    )

    return events_list, athletes
