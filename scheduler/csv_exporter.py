"""CSV exporter for scheduled track meets.

Exports the computed schedule to CSV format compatible with opentrack_admin.
"""

import csv
from datetime import datetime, timedelta

from .functional_scheduler import SchedulingResult
from .models import EventGroup, EventType


# Map EventType to opentrack_admin event codes
EVENT_TYPE_TO_CODE: dict[EventType, str] = {
    EventType.m60: "60m",
    EventType.m100: "100m",
    EventType.m200: "200m",
    EventType.m400: "400m",
    EventType.m800: "800m",
    EventType.m1500: "1500m",
    EventType.m5000: "5000m",
    EventType.m60_hurdles: "60H",
    EventType.m80_hurdles: "80H",
    EventType.m100_hurdles: "100H",
    EventType.sp: "SP",
    EventType.lj: "LJ",
    EventType.tj: "TJ",
    EventType.hj: "HJ",
    EventType.dt: "DT",
    EventType.jt: "JT",
    EventType.ht: "HT",
    EventType.bt: "BT",
    EventType.pv: "PV",
}


# Map Category value to opentrack_admin category format
def _category_to_opentrack(category_value: str) -> str:
    """Convert category value to opentrack_admin format.

    Examples:
        "G-Rekrutt" -> "G-rekrutt"
        "J-Rekrutt" -> "J-rekrutt"
        "G11" -> "G11"
        "J18-19" -> "J18-19"
        "Menn-Senior" -> "M"
        "Kvinner-Senior" -> "W"
    """
    # Handle senior categories
    if category_value in ("Menn-Senior", "MS"):
        return "M"
    if category_value in ("Kvinner-Senior", "KS"):
        return "W"

    # Handle rekrutt - normalize case
    if "rekrutt" in category_value.lower():
        if category_value.startswith("G"):
            return "G-rekrutt"
        elif category_value.startswith("J"):
            return "J-rekrutt"

    # Return as-is for standard categories like G11, J15, etc.
    return category_value


def export_schedule_csv(
    result: SchedulingResult,
    output_path: str,
    start_hour: int = 9,
    start_minute: int = 0,
) -> None:
    """
    Export the scheduled events to CSV format for opentrack_admin.

    Output format (compatible with opentrack_admin parse_schedule_csv):
        category,event,start_time
        J14,LJ,17:00
        G-rekrutt,HJ,17:00
        G11,60m,17:25

    Args:
        result: The scheduling result containing the computed schedule
        output_path: Path for the output CSV file
        start_hour: Starting hour for the schedule (24-hour format)
        start_minute: Starting minute for the schedule
    """
    if result.status != "solved":
        raise ValueError(f"Cannot export unsolved schedule: {result.status}")

    base_time = datetime.now().replace(
        hour=start_hour, minute=start_minute, second=0, microsecond=0
    )
    slot_duration = result.slot_duration_minutes

    rows: list[dict[str, str]] = []

    # Collect all scheduled events
    for slot, slot_events in sorted(result.schedule.items()):
        for event_info in slot_events:
            if event_info.get("is_start", False):
                event_group: EventGroup = event_info["event"]
                slot_time = base_time + timedelta(minutes=slot * slot_duration)
                time_str = slot_time.strftime("%H:%M")

                # Get event code
                event_code = EVENT_TYPE_TO_CODE.get(event_group.event_type)
                if not event_code:
                    continue

                # Create a row for each category in the event group
                for event in event_group.events:
                    category = _category_to_opentrack(event.age_category.value)
                    rows.append({
                        "category": category,
                        "event": event_code,
                        "start_time": time_str,
                    })

    # Sort by time, then by event, then by category
    rows.sort(key=lambda r: (r["start_time"], r["event"], r["category"]))

    # Write CSV
    with open(output_path, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["category", "event", "start_time"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ Schedule CSV exported to: {output_path}")
    print(f"   {len(rows)} events scheduled")
