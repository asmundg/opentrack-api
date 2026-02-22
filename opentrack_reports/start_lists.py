#!/usr/bin/env python3
# filepath: /Volumes/src/priv/opentrack/start_lists.py
import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime as dt
from datetime import timedelta
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .competitors_by_club import parse_competitors_by_club

# Import required functions from local modules - no fallbacks
from .opentrack_utils import (
    fetch_json_data,
    get_track_event_codes,
    is_track_event,
    process_local_json,
    validate_events,
)


def create_start_lists(
    data: dict[str, Any],
    output_filename: Optional[str] = None,
    event_type: Optional[str] = None,
    events: Optional[list[str]] = None,
    day: Optional[int] = None,
) -> None:
    """
    Create start lists PDF for track events with lane assignments.

    Args:
        data: JSON dictionary of competitor data from OpenTrack
        output_filename: Name of the output PDF file (optional, will be auto-generated if not provided)
        event_type: Type of track event to filter by (optional)
        events: List of event codes to filter by (optional, overrides event_type)
        day: Day number to filter by (optional, e.g., 1, 2, 3)
    """
    # Require raw JSON format from OpenTrack
    if "competitors" not in data or "events" not in data:
        raise TypeError(
            "Data must be a dict with 'competitors' and 'events' keys from OpenTrack JSON"
        )

    # Validate that all events are recognized - fail loudly if not
    print("Validating events...")
    validate_events(data, strict_mode=True)

    # Parse competitor data
    competitors_data = parse_competitors_by_club(data)

    # Extract meeting name from data - require it to be present
    meeting_name = data["fullName"]
    meeting_date = data["date"]

    # Parse the meeting date for better formatting
    formatted_meeting_date = meeting_date
    if meeting_date:
        try:
            parsed_date = dt.strptime(meeting_date, "%Y-%m-%d")
            formatted_meeting_date = parsed_date.strftime("%d %B %Y")
        except ValueError:
            # Keep original format if parsing fails
            formatted_meeting_date = meeting_date

    # Filter events to process - track events only
    events_to_process = []

    for event in data["events"]:
        event_code = event["eventCode"]
        event_id = event["eventId"]

        # Check if this is a track event using centralized function
        if not is_track_event(event_code):
            continue

        # Check if we should include this event based on filters
        if events:
            # Filter by specific event codes
            event_list = events
            if not any(evt_type in event_code for evt_type in event_list):
                continue
        elif event_type:
            # Filter by single event type
            if event_type not in event_code:
                continue

        # Filter by day if specified
        if day is not None:
            event_day = event["day"]
            if event_day != day:
                continue

        events_to_process.append(event)

    if not events_to_process:
        available_events = [
            f"{event['eventCode']} (ID: {event['eventId']})" for event in data["events"]
        ]
        raise ValueError(
            f"No matching track events found. Available events: {available_events}"
        )

    # Generate output filename if not provided
    if output_filename is None:
        safe_meeting_name = meeting_name
        if safe_meeting_name:
            # Replace spaces with underscores and remove special characters
            safe_meeting_name = re.sub(r"[^\w\s-]", "", safe_meeting_name)
            safe_meeting_name = re.sub(r"[\s-]+", "_", safe_meeting_name)

            day_suffix = f"_day{day}" if day is not None else ""

            if len(events_to_process) == 1:
                event_code = events_to_process[0]["eventCode"]
                output_filename = (
                    f"start_lists_{event_code}_{safe_meeting_name}{day_suffix}.pdf"
                )
            else:
                output_filename = (
                    f"start_lists_multiple_{safe_meeting_name}{day_suffix}.pdf"
                )
        else:
            day_suffix = f"_day{day}" if day is not None else ""

            if len(events_to_process) == 1:
                event_code = events_to_process[0]["eventCode"]
                output_filename = f"start_lists_{event_code}{day_suffix}.pdf"
            else:
                output_filename = f"start_lists_multiple{day_suffix}.pdf"

    # Print debug information
    day_filter_text = f" (filtered by day {day})" if day is not None else ""
    print(f"Creating start lists for {len(events_to_process)} events{day_filter_text}:")
    for event in events_to_process:
        event_day = event["day"]
        print(f"  - {event['eventCode']} (ID: {event['eventId']}) - Day {event_day}")
    print(f"Meeting name: {meeting_name}")
    print(f"Output filename: {output_filename}")

    # Create a mapping of bib numbers to competitors
    bib_to_competitor = {}
    for competitor in competitors_data:
        if "bib" in competitor:
            bib_to_competitor[competitor["bib"]] = competitor

    # Initialize the PDF document in portrait orientation (standard for start lists)
    doc = SimpleDocTemplate(
        output_filename,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    # Initialize styles
    styles = getSampleStyleSheet()

    # Create custom styles for start lists
    title_style = ParagraphStyle(
        name="TitleStyle",
        parent=styles["Heading1"],
        fontSize=16,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
        spaceAfter=8,
        spaceBefore=4,
    )

    event_title_style = ParagraphStyle(
        name="EventTitleStyle",
        parent=styles["Heading2"],
        fontSize=14,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
        spaceAfter=6,
        spaceBefore=12,
    )

    heat_title_style = ParagraphStyle(
        name="HeatTitleStyle",
        parent=styles["Heading3"],
        fontSize=12,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
        spaceAfter=6,
        spaceBefore=8,
    )

    lane_style = ParagraphStyle(
        name="LaneStyle",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica",
        leading=14,
        leftIndent=10,
        spaceAfter=2,
    )

    # Create a list to hold the elements that will be built into the PDF
    elements = []

    print("Phase 1: Processing events and grouping by time...")

    # Group events by time (and optionally event type for same-discipline events)
    time_groups = defaultdict(
        lambda: {
            "events": [],
            "time": "",
            "day": 1,
            "all_heats": {},  # heat_id -> list of (lane, bib, competitor_info)
            "heat_names": {},  # heat_id -> heat_name
        }
    )

    for event in events_to_process:
        event_code = event["eventCode"]
        event_id = event["eventId"]
        event_name = event["name"]
        event_day = event["day"]

        print(
            f"Processing event: {event_name} ({event_code}, ID: {event_id}) - Day {event_day}"
        )

        # Extract heat and lane information from units/results
        # Use each unit's scheduledStartTime for grouping (not event-level r1Time)
        for unit in event["units"]:
            heat_id = unit["id"]
            heat_name = unit["heatName"]

            # Get the unit's scheduled start time, fall back to event's r1Time if not present
            unit_time = unit.get("scheduledStartTime") or event.get("r1Time")

            if not unit_time:
                print(
                    f"WARNING: Unit {heat_id} in event {event_code} has no scheduledStartTime, skipping"
                )
                continue

            # Skip units without a proper heat ID
            if not heat_id:
                print(f"WARNING: Unit in event {event_code} missing id field, skipping")
                continue

            # Create time group key using the unit's scheduled start time
            time_key = f"day{event_day}_{unit_time}"

            # Add event info to time group (avoid duplicates)
            event_entry = {"code": event_code, "id": event_id, "name": event_name, "day": event_day}
            if event_entry not in time_groups[time_key]["events"]:
                time_groups[time_key]["events"].append(event_entry)
            time_groups[time_key]["time"] = unit_time
            time_groups[time_key]["day"] = event_day

            # Create unique heat ID that includes event info to avoid conflicts between events
            unique_heat_id = f"{event_code}_{heat_id}"

            if unique_heat_id not in time_groups[time_key]["all_heats"]:
                time_groups[time_key]["all_heats"][unique_heat_id] = []
                # Store both event code and heat name for flexible formatting later
                time_groups[time_key]["heat_names"][unique_heat_id] = {
                    "event_code": event_code,
                    "event_id": event_id,
                    "event_name": event_name,
                    "heat_name": heat_name,
                    "original_heat_id": heat_id,
                }

            for result in unit["results"]:
                if "bib" in result and "lane" in result:
                    lane = result["lane"]
                    bib = result["bib"]

                    # Get competitor info - fail if bib not found
                    if bib not in bib_to_competitor:
                        print(
                            f"ERROR: Competitor with bib {bib} not found in competitor data"
                        )
                        continue
                    competitor_info = bib_to_competitor[bib]

                    time_groups[time_key]["all_heats"][unique_heat_id].append(
                        {
                            "lane": lane,
                            "bib": bib,
                            "competitor": competitor_info,
                            "event_name": event_name,
                            "event_id": event_id,  # Store event_id for PB/SB lookup
                        }
                    )

    print(f"Phase 2: Sorting {len(time_groups)} time groups by chronological order...")

    def sort_time_group_key(time_group_item):
        """Sort time groups purely by day and time"""
        time_key, group_data = time_group_item
        event_time = group_data["time"]
        event_day = group_data["day"]

        # Convert time to minutes since midnight for proper sorting
        try:
            time_parts = event_time.split(":")
            hours = int(time_parts[0])
            minutes = int(time_parts[1])
            minutes_since_midnight = hours * 60 + minutes
        except (ValueError, IndexError):
            minutes_since_midnight = 9999  # Put invalid times at the end

        return (event_day, minutes_since_midnight)

    # Sort time groups by chronological order only
    sorted_time_groups = sorted(time_groups.items(), key=sort_time_group_key)
    print(f"Time groups sorted chronologically (Day, Time):")
    for time_key, group_data in sorted_time_groups:
        event_names = [e["name"] for e in group_data["events"]]
        events_str = " / ".join(event_names)
        print(f"  Day {group_data['day']}, {group_data['time']} - {events_str}")

    for time_key, group_data in sorted_time_groups:
        print(f"\nProcessing time group: {time_key}")
        event_names = [e["name"] for e in group_data["events"]]
        events_str = " / ".join(event_names)
        print(f"  Events: {events_str}")
        print(f"  Time: {group_data['time']}")
        print(f"  Day: {group_data['day']}")
        print(f"  Total heats: {len(group_data['all_heats'])}")

        if len(group_data["all_heats"]) == 0:
            print(f"  No heats in time group {time_key}, skipping")
            continue

        # Calculate the actual event date by combining base date and event day
        event_date_str = formatted_meeting_date
        if meeting_date and group_data["day"]:
            try:
                base_date = dt.strptime(meeting_date, "%Y-%m-%d")
                event_date = base_date + timedelta(days=group_data["day"] - 1)
                event_date_str = event_date.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                event_date_str = formatted_meeting_date

        # For all events (single or merged), just show the meeting info and start time
        # Individual event names will be shown as headers above each table
        elements.append(
            Paragraph(
                f"{meeting_name} - {event_date_str} - STARTTID: {group_data['time']}",
                lane_style,
            )
        )
        elements.append(Spacer(1, 0.3 * cm))

        # Group heats by event code to create separate category sections
        heats_by_event = {}
        for heat_id, heat_competitors in group_data["all_heats"].items():
            heat_info = group_data["heat_names"][heat_id]
            event_code = heat_info["event_code"]
            event_name = heat_info["event_name"]

            if event_code not in heats_by_event:
                heats_by_event[event_code] = {"event_name": event_name, "heats": {}}

            heats_by_event[event_code]["heats"][heat_id] = heat_competitors

        # Sort events by code for consistent ordering
        sorted_events = sorted(heats_by_event.items(), key=lambda x: x[0])

        # Process each event separately to create individual category headers
        for event_code, event_data in sorted_events:
            event_name = event_data["event_name"]

            # Always add category header for each event (whether merged or single)
            category_style = ParagraphStyle(
                name="CategoryStyle",
                parent=heat_title_style,
                fontSize=11,
                fontName="Helvetica-Bold",
                alignment=TA_CENTER,
                spaceAfter=4,
                spaceBefore=6,
            )

            # Process each heat separately to maintain category separation
            # For merged events, sort by lane ranges to ensure natural flow
            # For single events, sort by original heat ID
            def get_heat_sort_key(heat_item):
                heat_id, heat_competitors = heat_item
                heat_info = group_data["heat_names"][heat_id]
                original_heat_id = heat_info["original_heat_id"]

                # Check if this is a merged event (multiple different events in same time slot)
                all_event_names = set()
                for _, competitors in event_data["heats"].items():
                    for comp in competitors:
                        all_event_names.add(comp["event_name"])
                is_merged_event = len(all_event_names) > 1

                if is_merged_event and heat_competitors:
                    # For merged events, sort by the lowest lane number in each heat
                    # This ensures categories flow naturally by lane ranges
                    min_lane = min(
                        int(comp["lane"]) if str(comp["lane"]).isdigit() else 9999
                        for comp in heat_competitors
                    )
                    return (0, min_lane)  # Primary sort by lane range
                else:
                    # For single events, sort by original heat ID
                    try:
                        return (1, int(original_heat_id))  # Secondary sort by heat ID
                    except (ValueError, TypeError):
                        return (1, str(original_heat_id))

            sorted_heats = sorted(event_data["heats"].items(), key=get_heat_sort_key)

            # Debug: Show heat ordering for merged events
            if (
                len(
                    set(
                        comp["event_name"]
                        for _, competitors in event_data["heats"].items()
                        for comp in competitors
                    )
                )
                > 1
            ):
                print(f"  Merged event detected, heat ordering by lane ranges:")
                for heat_id, heat_competitors in sorted_heats:
                    if heat_competitors:
                        heat_info = group_data["heat_names"][heat_id]
                        lanes = [comp["lane"] for comp in heat_competitors]
                        print(
                            f"    {heat_info['event_name']}: lanes {min(lanes)}-{max(lanes)}"
                        )

            for heat_id, heat_competitors in sorted_heats:
                if not heat_competitors:
                    continue

                # Sort competitors by lane number (ensure proper numeric sorting)
                def get_lane_sort_key(competitor_info):
                    lane = competitor_info["lane"]
                    try:
                        # Try to convert to integer for proper numeric sorting
                        return int(lane)
                    except (ValueError, TypeError):
                        # If lane is not a number, put it at the end
                        return 9999

                sorted_competitors = sorted(heat_competitors, key=get_lane_sort_key)

                # Only create a table if this heat has competitors
                if sorted_competitors:
                    # Get the specific event name for this heat/table
                    heat_info = group_data["heat_names"][heat_id]
                    heat_event_name = heat_info["event_name"]
                    heat_event_id = heat_info["event_id"]
                    heat_name = heat_info["heat_name"]

                    # Include heat name when there are multiple heats (e.g. "Race 1 of 2")
                    if heat_name and " of " in heat_name:
                        header_text = f"{heat_event_name} - {heat_name}"
                    else:
                        header_text = heat_event_name

                    # Show the specific event name with heat info as a header above each table
                    elements.append(
                        Paragraph(header_text, category_style)
                    )

                    # Create table data with headers (Norwegian)
                    table_data = [
                        ["Bane", "Nr", "Navn", "Klubb", "Klasse", "PB", "SB"]
                    ]

                    for competitor_info in sorted_competitors:
                        lane = str(competitor_info["lane"])
                        bib = str(competitor_info["bib"])
                        competitor = competitor_info["competitor"]

                        # Format name (don't convert to uppercase, keep original formatting)
                        name = competitor["name"]
                        club = competitor["club"]
                        category = competitor["category"]

                        # Get PB and SB (season best) for this specific event
                        # Look up from the competitor's event-specific data using event_id
                        event_id = competitor_info.get("event_id", "")
                        pb_by_event = competitor.get("pb_by_event", {})
                        sb_by_event = competitor.get("sb_by_event", {})
                        pb = pb_by_event.get(event_id, "")
                        sb = sb_by_event.get(event_id, "")

                        table_data.append([lane, bib, name, club, category, pb, sb])

                    # Create table with styling for this specific heat
                    table = Table(
                        table_data,
                        colWidths=[
                            1.2 * cm,
                            1.2 * cm,
                            5 * cm,
                            4 * cm,
                            2 * cm,
                            1.5 * cm,
                            1.5 * cm,
                        ],
                    )
                    table.setStyle(
                        TableStyle(
                            [
                                # Header row styling
                                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                                ("FONTSIZE", (0, 0), (-1, 0), 9),
                                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                                # Header outline box only
                                ("BOX", (0, 0), (-1, 0), 1, colors.black),
                                # Data rows styling
                                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                                ("FONTSIZE", (0, 1), (-1, -1), 8),
                                (
                                    "ROWBACKGROUNDS",
                                    (0, 1),
                                    (-1, -1),
                                    [colors.beige, colors.white],
                                ),
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                                ("TOPPADDING", (0, 0), (-1, -1), 3),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                            ]
                        )
                    )

                    elements.append(table)
                    elements.append(Spacer(1, 0.4 * cm))

        # Add page break between time groups
        elements.append(PageBreak())

    # Define a function for page numbers
    def add_page_number(canvas, doc):
        page_num = canvas.getPageNumber()
        text = f"Side {page_num}"
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(doc.width + doc.rightMargin - 10, 10, text)
        canvas.restoreState()

    # Build the PDF
    doc.build(elements, onFirstPage=add_page_number, onLaterPages=add_page_number)

    print(f"Start lists saved to {output_filename}")


def detect_track_event(data: dict[str, Any]) -> str:
    """
    Auto-detect a track event from the data.

    Args:
        data: JSON dictionary of competitor data

    Returns:
        Detected event code or '100' as default if none detected
    """
    # Get track event codes from centralized definition
    track_event_codes = get_track_event_codes()

    # First, try to find events that have units with results
    events_with_competitors = set()
    for event in data["events"]:
        event_code = event["eventCode"]

        # Check if this is a track event using centralized function
        if is_track_event(event_code):
            # Check if there are units with results
            for unit in event["units"]:
                if unit["results"]:
                    events_with_competitors.add(event_code)
                    print(f"Detected track event with competitors: {event_code}")
                    break

    # If we found track events with competitors, return the first one
    if events_with_competitors:
        sorted_events = sorted(events_with_competitors)
        print(f"Auto-detected event type: {sorted_events[0]}")
        return sorted_events[0]

    # Fallback: Try to find a suitable track event from the available events
    for event in data["events"]:
        event_code = event["eventCode"]
        if is_track_event(event_code):
            print(f"Auto-detected event type: {event_code}")
            return event_code

    # If we don't find any, return 100 as default
    print("No track events detected, using default event type: 100")
    return "100"


def load_data_from_source(source: str) -> dict[str, Any]:
    """
    Load data from a source which can be a URL or a local file path.

    Args:
        source: URL or file path to the JSON data

    Returns:
        Parsed JSON data
    """
    # Determine if source is a URL or a local file
    if source.startswith(("http://", "https://")):
        return fetch_json_data(source)
    else:
        return process_local_json(source)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate start lists PDF for track events"
    )
    parser.add_argument("source", help="JSON source URL or local file path")
    parser.add_argument(
        "-o",
        "--output",
        help="Output PDF filename (optional, will be auto-generated if not provided)",
    )
    parser.add_argument(
        "-e",
        "--event",
        help="Event type code (optional, will be auto-detected if not specified)",
        action="append",
        dest="events",
    )
    parser.add_argument(
        "--all-events",
        action="store_true",
        help="Process all track events found in the data",
    )
    parser.add_argument(
        "-d",
        "--day",
        type=int,
        help="Filter events by day number (e.g., 1, 2, 3)",
        metavar="N",
    )

    args = parser.parse_args()

    try:
        # Load data from source
        data = load_data_from_source(args.source)

        # Validate events first - fail loudly if unrecognized events found
        print("Pre-validation of all events in dataset...")
        validate_events(data, strict_mode=True)
        print("All events recognized successfully.")

        # Determine which events to process
        events_to_process = None

        if args.all_events:
            # Process all track events using centralized definition
            track_event_codes = get_track_event_codes()
            events_to_process = []

            if "events" in data:
                for event in data["events"]:
                    event_code = event["eventCode"]
                    if (
                        is_track_event(event_code)
                        and event_code not in events_to_process
                    ):
                        events_to_process.append(event_code)

            if not events_to_process:
                print("No track events found in the data")
                sys.exit(1)
        elif args.events:
            # Use the events specified in the arguments
            events_to_process = args.events

        # Create the start lists PDF
        create_start_lists(
            data, output_filename=args.output, events=events_to_process, day=args.day
        )

        print(f"Start lists successfully generated")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
