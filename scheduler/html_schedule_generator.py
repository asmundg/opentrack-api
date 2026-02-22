"""
HTML schedule generator for track meet scheduling.

This module generates HTML tables showing time x venue allocation of events
from a SchedulingResult, providing a visual grid layout of the schedule.
"""

from typing import Any
from .models import Venue, Category, EventGroup, get_venue_for_event
from .functional_scheduler import SchedulingResult


def generate_html_schedule_table(
    result: SchedulingResult,
    start_hour: int = 9,
    start_minute: int = 0,
    title: str = "Track Meet Schedule",
) -> str:
    """
    Generate an HTML table showing time x venue allocation of events.
    
    Args:
        result: The scheduling result containing events, athletes, and schedule
        start_hour: Starting hour for the schedule (24-hour format)
        start_minute: Starting minute for the schedule
        title: Title for the HTML table
        
    Returns:
        Complete HTML string with embedded CSS styling
    """
    # Check if scheduling was successful
    if result.status != "solved" or not result.schedule:
        return _generate_empty_schedule_html(title)

    # Calculate participant counts from the result data
    participants_by_event = _calculate_participants_by_event(result)
    participants_by_category = _calculate_participants_by_category(result)

    # Get all venues that have events scheduled
    venues_used = _get_venues_used_from_schedule(result.schedule)
    venues_ordered = _order_venues(venues_used)

    # Generate time slots
    time_slots = _generate_time_slots_from_result(result, start_hour, start_minute)

    # Build venue allocation grid with spanning events
    venue_grid, spans = _build_venue_grid_with_spans_from_result(
        result, venues_ordered, participants_by_event, participants_by_category
    )
    
    # Generate HTML
    html_content = _generate_html_content(
        title=title,
        time_slots=time_slots,
        venues_ordered=venues_ordered,
        venue_grid=venue_grid,
        spans=spans,
        result=result,
    )
    
    return html_content


def _generate_empty_schedule_html(title: str) -> str:
    """Generate HTML for empty schedule."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .no-events {{ text-align: center; color: #666; font-size: 18px; }}
        </style>
    </head>
    <body>
        <h1>{title}</h1>
        <div class="no-events">Ingen planlagte øvelser</div>
    </body>
    </html>
    """


def _get_venue_for_event_group(event_group: EventGroup, override_venue: Venue | None = None) -> Venue | None:
    """Get the venue for an EventGroup, considering secondary venue assignments.

    Args:
        event_group: The event group to get venue for
        override_venue: If provided, use this venue instead of calculating from event type
                       (used when venue is explicitly set in events CSV)
    """
    if override_venue is not None:
        return override_venue
    first_event = event_group.events[0] if event_group.events else None
    category = first_event.age_category if first_event else None
    return get_venue_for_event(event_group.event_type, category)


def _get_venues_used_from_schedule(schedule: dict[int, list[dict[str, Any]]]) -> set[Venue]:
    """Get all venues that have events scheduled."""
    venues_used: set[Venue] = set()

    for slot_events in schedule.values():
        for event_info in slot_events:
            event_group: EventGroup = event_info['event']
            override_venue = event_info.get('venue')  # From events CSV if available
            venue = _get_venue_for_event_group(event_group, override_venue)
            if venue is not None:
                venues_used.add(venue)

    return venues_used


def _order_venues(venues_used: set[Venue]) -> list[Venue]:
    """Order venues in a logical sequence for display."""
    # Define preferred order for venues
    venue_order = [
        Venue.TRACK,
        Venue.JUMPING_PIT,
        Venue.HIGH_JUMP_AREA,
        Venue.HIGH_JUMP_AREA_2,
        Venue.SHOT_PUT_CIRCLE,
        Venue.SHOT_PUT_CIRCLE_2,
        Venue.THROWING_CIRCLE,
        Venue.JAVELIN_AREA,
    ]

    # Return only venues that are actually used, in preferred order
    return [venue for venue in venue_order if venue in venues_used]


def _generate_time_slots_from_result(
    result: SchedulingResult, start_hour: int, start_minute: int
) -> list[tuple[int, str]]:
    """Generate list of (slot_number, time_string) tuples."""
    time_slots: list[tuple[int, str]] = []
    slot_duration_minutes = result.slot_duration_minutes
    
    # Generate time slots for all slots from 0 to the maximum slot used
    # This ensures we have table rows for all slots that events might span across
    if result.schedule:
        max_slot = max(result.schedule.keys())
        for slot in range(max_slot + 1):
            start_time_minutes = start_hour * 60 + start_minute + slot * slot_duration_minutes
            hours = start_time_minutes // 60
            minutes = start_time_minutes % 60
            time_str = f"{hours}:{minutes:02d}"
            time_slots.append((slot, time_str))
    
    return time_slots


def _get_category_color(category: Category | str) -> str:
    """Get a color for a specific age category based on user's color scheme."""

    # Color scheme:
    # - 10 year olds: yellow/orange
    # - G11/12: light blue
    # - J11/12: light pink
    # - G13/14: dark blue
    # - J13/14: red
    # - G15+: olive
    # - J15+: light green

    category_colors: dict[Category, str] = {
        # 10 year olds - yellow/orange
        Category.g10: "#FFA500",      # Orange
        Category.j10: "#FFD700",      # Gold/Yellow

        # Boys 11/12 - light blue
        Category.g11: "#87CEEB",      # Light sky blue
        Category.g12: "#87CEEB",      # Light sky blue

        # Girls 11/12 - light pink
        Category.j11: "#FFB6C1",      # Light pink
        Category.j12: "#FFB6C1",      # Light pink

        # Boys 13/14 - medium blue
        Category.g13: "#5B9BD5",      # Medium blue
        Category.g14: "#5B9BD5",      # Medium blue

        # Girls 13/14 - red
        Category.j13: "#DC143C",      # Crimson red
        Category.j14: "#DC143C",      # Crimson red

        # Boys 15+ - olive
        Category.g15: "#808000",      # Olive
        Category.g16: "#808000",      # Olive
        Category.g17: "#808000",      # Olive
        Category.g18_19: "#808000",   # Olive
        Category.ms: "#808000",       # Olive (men senior)

        # Girls 15+ - light green
        Category.j15: "#90EE90",      # Light green
        Category.j16: "#90EE90",      # Light green
        Category.j17: "#90EE90",      # Light green
        Category.j18_19: "#90EE90",   # Light green
        Category.ks: "#90EE90",       # Light green (women senior)
    }

    # Special handling for string-based categories (Rekrutt = 10 year olds)
    special_categories: dict[str, str] = {
        "G-Rekrutt": "#FFA500",      # Orange (boys 10)
        "J-Rekrutt": "#FFD700",      # Gold/Yellow (girls 10)
    }

    # Check if it's a string category first
    if isinstance(category, str):
        return special_categories.get(category, "#757575")  # Gray default

    # Otherwise use the Category enum
    return category_colors.get(category, "#757575")  # Gray default


def _get_group_category_color(event_group: EventGroup) -> str:
    """Get a color or gradient for an EventGroup based on its contained events."""
    
    if not event_group.events:
        return "#757575"  # Strong gray for empty groups
    
    # Get all unique categories in the group
    categories = list({event.age_category for event in event_group.events})
    
    # If all events in the group have the same category, use that category's solid color
    if len(categories) == 1:
        return _get_category_color(categories[0])
    
    # For merged categories, create a CSS gradient between the category colors
    if len(categories) == 2:
        # Two-color gradient
        color1 = _get_category_color(categories[0])
        color2 = _get_category_color(categories[1])
        return f"linear-gradient(135deg, {color1} 0%, {color2} 100%)"
    elif len(categories) == 3:
        # Three-color gradient
        color1 = _get_category_color(categories[0])
        color2 = _get_category_color(categories[1])
        color3 = _get_category_color(categories[2])
        return f"linear-gradient(135deg, {color1} 0%, {color2} 50%, {color3} 100%)"
    else:
        # For 4+ categories, use a multi-stop gradient
        colors = [_get_category_color(cat) for cat in categories]
        gradient_stops: list[str] = []
        for i, color in enumerate(colors):
            percentage = i * (100 / (len(colors) - 1)) if len(colors) > 1 else 0
            gradient_stops.append(f"{color} {percentage}%")
        return f"linear-gradient(135deg, {', '.join(gradient_stops)})"


def _build_venue_grid_with_spans_from_result(
    result: SchedulingResult,
    venues_ordered: list[Venue],
    participants_by_event: dict[str, int],
    participants_by_category: dict[str, int],
) -> tuple[dict[int, dict[Venue, list[dict[str, Any]]]], dict[tuple[int, Venue], dict[str, Any]]]:
    """
    Build a grid of slot -> venue -> list of events, plus span information for multi-slot events.

    Returns:
        Tuple of (venue_grid, spans) where:
        - venue_grid: Dictionary mapping slot number to venue to list of event_info dicts
        - spans: Dictionary mapping (slot, venue) to span information for multi-slot events
    """
    venue_grid: dict[int, dict[Venue, list[dict[str, Any]]]] = {}
    spans: dict[tuple[int, Venue], dict[str, Any]] = {}

    # Track which events we've already processed to avoid duplicates
    processed_events: set[str] = set()
    schedule = result.schedule
    slot_duration_minutes = result.slot_duration_minutes

    # Initialize venue grid for all slots from 0 to max slot
    # This ensures we have venue entries for all slots that events might span across
    if schedule:
        max_slot = max(schedule.keys())
        for slot in range(max_slot + 1):
            venue_grid[slot] = {venue: [] for venue in venues_ordered}

    # Process events and populate the grid
    for slot in sorted(schedule.keys()):
        for event_info in schedule[slot]:
            event_group: EventGroup = event_info['event']
            override_venue = event_info.get('venue')  # From events CSV if available
            venue = _get_venue_for_event_group(event_group, override_venue)

            if venue is not None and venue in venue_grid[slot]:
                # Only process each event once (at its starting slot)
                if event_info['is_start'] and event_group.id not in processed_events:
                    processed_events.add(event_group.id)

                    # Calculate span duration for this event
                    event_duration_slots = _calculate_event_slots(event_group, slot_duration_minutes)
                    participant_count = participants_by_event.get(event_group.id, 0)

                    # Get per-category counts for this event group
                    category_counts: dict[str, int] = {}
                    for sub_event in event_group.events:
                        count = participants_by_category.get(sub_event.id, 0)
                        category_counts[sub_event.age_category.value] = count

                    # For EventGroup, get a representative color based on the contained events
                    category_color = _get_group_category_color(event_group)

                    # Create enhanced event info
                    enhanced_event_info = {
                        'event': event_group,
                        'is_start': True,
                        'slot_offset': 0,
                        'participant_count': participant_count,
                        'category_counts': category_counts,
                        'duration_slots': event_duration_slots,
                        'category_color': category_color,
                    }

                    venue_grid[slot][venue].append(enhanced_event_info)

                    # Store span information
                    spans[(slot, venue)] = {
                        'event_id': event_group.id,
                        'rowspan': event_duration_slots,
                        'event_info': enhanced_event_info,
                    }

    return venue_grid, spans


def _calculate_event_slots(event: Any, slot_duration_minutes: int) -> int:
    """Calculate how many slots an event spans."""
    return (event.duration_minutes + slot_duration_minutes - 1) // slot_duration_minutes


def _calculate_participants_by_event(result: SchedulingResult) -> dict[str, int]:
    """Calculate the number of participants for each event group from athlete data."""
    participants_by_event: dict[str, int] = {}

    # Create mapping from individual event IDs to group IDs
    event_to_group: dict[str, str] = {}
    for event_group in result.events:
        for event in event_group.events:
            event_to_group[event.id] = event_group.id

    # Count how many athletes are registered for events in each group
    for athlete in result.athletes:
        counted_groups: set[str] = set()  # Avoid double counting if athlete has multiple events in same group
        for event in athlete.events:
            group_id = event_to_group.get(event.id)
            if group_id and group_id not in counted_groups:
                if group_id not in participants_by_event:
                    participants_by_event[group_id] = 0
                participants_by_event[group_id] += 1
                counted_groups.add(group_id)

    return participants_by_event


def _calculate_participants_by_category(result: SchedulingResult) -> dict[str, int]:
    """Calculate the number of participants for each individual event (by category)."""
    participants_by_category: dict[str, int] = {}

    # Initialize all events with 0
    for event_group in result.events:
        for event in event_group.events:
            participants_by_category[event.id] = 0

    # Count athletes per individual event
    for athlete in result.athletes:
        for event in athlete.events:
            if event.id in participants_by_category:
                participants_by_category[event.id] += 1

    return participants_by_category


def _generate_html_content(
    title: str,
    time_slots: list[tuple[int, str]],
    venues_ordered: list[Venue],
    venue_grid: dict[int, dict[Venue, list[dict[str, Any]]]],
    spans: dict[tuple[int, Venue], dict[str, Any]],
    result: SchedulingResult,
) -> str:
    """Generate the complete HTML content with spanning event blocks."""
    # Track which cells should be skipped due to rowspan
    skip_cells: set[tuple[int, Venue]] = set()
    
    # Generate table rows
    table_rows = ""
    for slot, time_str in time_slots:
        row_cells = f'<td class="time-cell">{time_str}</td>'
        
        for venue in venues_ordered:
            # Skip this cell if it's covered by a rowspan from above
            if (slot, venue) in skip_cells:
                continue
                
            events_in_venue = venue_grid.get(slot, {}).get(venue, [])
            
            if events_in_venue and (slot, venue) in spans:
                # This is a spanning event
                span_info = spans[(slot, venue)]
                event_info = span_info['event_info']
                rowspan = span_info['rowspan']
                
                # Mark future cells as skipped
                for future_slot in range(slot + 1, slot + rowspan):
                    skip_cells.add((future_slot, venue))
                
                cell_content = _format_spanning_event_cell(event_info)
                rowspan_attr = f' rowspan="{rowspan}"' if rowspan > 1 else ""
                cell_class = "venue-cell has-events spanning-event"
                
                row_cells += f'<td class="{cell_class}"{rowspan_attr}>{cell_content}</td>'
            else:
                # Empty cell or non-spanning event
                cell_class = "venue-cell"
                if events_in_venue:
                    cell_class += " has-events"
                    cell_content = _format_venue_cell_content(events_in_venue)
                else:
                    cell_content = ""
                
                row_cells += f'<td class="{cell_class}">{cell_content}</td>'
        
        table_rows += f'<tr>{row_cells}</tr>\n'
    
    # Generate venue headers
    venue_headers = '<th class="time-header">Tid</th>'
    for venue in venues_ordered:
        venue_headers += f'<th class="venue-header">{_format_venue_name(venue)}</th>'
    
    # Complete HTML document
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <meta charset="utf-8">
    <style>
        {_get_css_styles()}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <div class="schedule-info">
            <p><strong>Total varighet:</strong> {result.total_duration_minutes} minutter</p>
            <p><strong>Antall tidsluker:</strong> {result.total_slots}</p>
            <p><strong>Tidsluke:</strong> {result.slot_duration_minutes} minutter</p>
        </div>
        <table class="schedule-table">
            <thead>
                <tr>{venue_headers}</tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
        <div class="legend">
            <h3>Tegnforklaring</h3>
            <div class="legend-item">
                <span class="legend-block" style="display: inline-block; width: 20px; height: 20px; background: linear-gradient(135deg, #FFA500 0%, #FFD700 100%); border-radius: 3px; margin-right: 8px; border: 1px solid #ccc;"></span> 10 &aring;r (Rekrutt) &ndash; Gul/Oransje
            </div>
            <div class="legend-item">
                <span class="legend-block" style="display: inline-block; width: 20px; height: 20px; background: #87CEEB; border-radius: 3px; margin-right: 8px; border: 1px solid #ccc;"></span> G11/G12 &ndash; Lysbl&aring;
            </div>
            <div class="legend-item">
                <span class="legend-block" style="display: inline-block; width: 20px; height: 20px; background: #FFB6C1; border-radius: 3px; margin-right: 8px; border: 1px solid #ccc;"></span> J11/J12 &ndash; Lysrosa
            </div>
            <div class="legend-item">
                <span class="legend-block" style="display: inline-block; width: 20px; height: 20px; background: #5B9BD5; border-radius: 3px; margin-right: 8px; border: 1px solid #ccc;"></span> G13/G14 &ndash; Bl&aring;
            </div>
            <div class="legend-item">
                <span class="legend-block" style="display: inline-block; width: 20px; height: 20px; background: #DC143C; border-radius: 3px; margin-right: 8px; border: 1px solid #ccc;"></span> J13/J14 &ndash; R&oslash;d
            </div>
            <div class="legend-item">
                <span class="legend-block" style="display: inline-block; width: 20px; height: 20px; background: #808000; border-radius: 3px; margin-right: 8px; border: 1px solid #ccc;"></span> G15+ / Menn Senior &ndash; Oliven
            </div>
            <div class="legend-item">
                <span class="legend-block" style="display: inline-block; width: 20px; height: 20px; background: #90EE90; border-radius: 3px; margin-right: 8px; border: 1px solid #ccc;"></span> J15+ / Kvinner Senior &ndash; Lysegr&oslash;nn
            </div>
            <div class="legend-item">
                <span class="legend-block" style="display: inline-block; width: 20px; height: 20px; background: linear-gradient(135deg, #87CEEB 0%, #FFB6C1 100%); border-radius: 3px; margin-right: 8px; border: 1px solid #ccc;"></span> Gradient = sammensl&aring;tte klasser
            </div>
        </div>
    </div>
</body>
</html>"""
    
    return html_content


def _format_spanning_event_cell(event_info: dict[str, Any]) -> str:
    """Format the content of a cell containing a spanning event."""
    event = event_info['event']
    participant_count = event_info.get('participant_count', 0)
    category_counts = event_info.get('category_counts', {})
    duration_slots = event_info.get('duration_slots', 1)
    category_color = event_info.get('category_color', '#757575')

    # Check if this is a FIFA (non-athletic) event - skip participant counts
    is_fifa = (
        len(event.events) == 1
        and event.events[0].age_category == Category.fifa
    )

    # Format event name with per-category athlete counts
    categories_line = ""  # Only used for multi-category events
    if len(event.events) == 1:
        # Single event in group - show specific category with count (skip for FIFA)
        single_event = event.events[0]
        category_bold = f"<strong>{single_event.age_category.value}</strong>"
        if is_fifa:
            event_name = f"{event.event_type.value} {category_bold}"
        else:
            count = category_counts.get(single_event.age_category.value, 0)
            event_name = f"{event.event_type.value} {category_bold}({count})"
    else:
        # Multiple events in group - show categories with counts summary
        # Format: "G17 / G18-19 / J16 / J17 (2+1+1+2)"
        sorted_events = sorted(event.events, key=lambda x: x.age_category.value)
        category_names = [f"<strong>{e.age_category.value}</strong>" for e in sorted_events]
        counts = [str(category_counts.get(e.age_category.value, 0)) for e in sorted_events]
        categories_str = " / ".join(category_names)
        counts_str = "+".join(counts)
        event_name = f"{event.event_type.value}"
        # Put categories on separate line for readability
        categories_line = f"{categories_str} ({counts_str})"

    # Duration text - skip participant count for FIFA events
    if is_fifa:
        duration_text = f"{event.duration_minutes}min"
    else:
        duration_text = f"{event.duration_minutes}min • {participant_count} totalt"

    # Calculate the height based on number of slots (40px per slot from CSS + borders)
    calculated_height = duration_slots * 40 + (duration_slots - 1) * 1  # 1px for borders

    # Handle both solid colors and gradients
    if category_color.startswith("linear-gradient"):
        background_style = f"background: {category_color}"
    else:
        background_style = f"background-color: {category_color}"

    # Build the HTML content
    if len(event.events) == 1:
        return f"""<div class="spanning-event-block" style="{background_style}; min-height: {calculated_height}px;">
        <div class="event-title">{event_name}</div>
        <div class="event-duration">{duration_text}</div>
    </div>"""
    else:
        return f"""<div class="spanning-event-block" style="{background_style}; min-height: {calculated_height}px;">
        <div class="event-title">{event_name}</div>
        <div class="event-categories">{categories_line}</div>
        <div class="event-duration">{duration_text}</div>
    </div>"""


def _format_venue_cell_content(events_in_venue: list[dict[str, Any]]) -> str:
    """Format the content of a venue cell."""
    if not events_in_venue:
        return ""
    
    event_descriptions: list[str] = []
    for event_info in events_in_venue:
        event = event_info['event']
        event_name = f"{event.event_type.value} {event.age_category.value}"
        
        if event_info['is_start']:
            emoji = "🟢"
            description = f"{emoji} {event_name}"
        else:
            emoji = "🔵"
            slot_num = event_info['slot_offset'] + 1
            description = f"{emoji} {event_name} (slot {slot_num})"
        
        event_descriptions.append(f'<div class="event-item">{description}</div>')
    
    return "".join(event_descriptions)


def _format_venue_name(venue: Venue) -> str:
    """Format venue name for display (Norwegian)."""
    venue_names = {
        Venue.TRACK: "Løp",
        Venue.JUMPING_PIT: "Lengde",
        Venue.HIGH_JUMP_AREA: "Høyde",
        Venue.HIGH_JUMP_AREA_2: "Høyde 2",
        Venue.SHOT_PUT_CIRCLE: "Kule",
        Venue.SHOT_PUT_CIRCLE_2: "Kule 2",
        Venue.THROWING_CIRCLE: "Kast",
        Venue.JAVELIN_AREA: "Spyd",
    }
    return venue_names.get(venue, venue.value.replace("_", " ").title())


def _get_css_styles() -> str:
    """Return CSS styles for the HTML table."""
    return """
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        h1 {
            color: #333;
            text-align: center;
            margin-bottom: 20px;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }
        
        .schedule-info {
            background-color: #f9f9f9;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            border-left: 4px solid #4CAF50;
        }
        
        .schedule-info p {
            margin: 5px 0;
            color: #555;
        }
        
        .schedule-table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
            font-size: 14px;
        }
        
        .schedule-table th,
        .schedule-table td {
            border: 1px solid #ddd;
            padding: 4px;
            text-align: left;
            vertical-align: top;
            height: 40px; /* Ensure consistent row height */
        }
        
        .schedule-table td.spanning-event {
            height: auto; /* Allow spanning cells to expand */
        }
        
        .time-header,
        .venue-header {
            background-color: #4CAF50;
            color: white;
            font-weight: bold;
            text-align: center;
            position: sticky;
            top: 0;
            z-index: 10;
            padding: 12px 8px;
        }
        
        .time-cell {
            background-color: #f8f9fa;
            font-weight: bold;
            text-align: center;
            min-width: 60px;
            color: #555;
            padding: 8px 4px;
        }
        
        .venue-cell {
            min-width: 150px;
            max-width: 200px;
            background-color: #fafafa;
            padding: 2px;
        }
        
        .venue-cell.has-events {
            background-color: #fff;
        }
        
        .venue-cell.spanning-event {
            padding: 0;
            vertical-align: top;
            position: relative;
            height: auto; /* Allow cell to expand to full rowspan */
        }
        
        .spanning-event-block {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            width: 100%;
            height: 100%;
            padding: 8px;
            border-radius: 4px;
            border: 2px solid #4CAF50;
            box-sizing: border-box;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            text-align: center;
        }
        
        .event-title {
            font-weight: bold;
            font-size: 13px;
            line-height: 1.2;
            margin-bottom: 2px;
            color: #333;
        }

        .event-categories {
            font-size: 11px;
            line-height: 1.3;
            margin-bottom: 2px;
            color: #333;
        }

        .event-duration {
            font-size: 10px;
            color: #555;
            font-style: italic;
        }
        
        .event-item {
            margin: 2px 0;
            padding: 4px 6px;
            background-color: #e8f5e8;
            border-radius: 3px;
            font-size: 12px;
            line-height: 1.3;
            border-left: 2px solid #4CAF50;
        }
        
        .legend {
            background-color: #f9f9f9;
            padding: 15px;
            border-radius: 5px;
            border-left: 4px solid #2196F3;
        }
        
        .legend h3 {
            margin-top: 0;
            color: #333;
        }
        
        .legend-item {
            margin: 8px 0;
            display: flex;
            align-items: center;
        }
        
        .legend-block,
        .legend-participants,
        .legend-colors {
            margin-right: 10px;
            font-size: 16px;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            
            .schedule-table {
                font-size: 12px;
            }
            
            .schedule-table th,
            .schedule-table td {
                padding: 2px;
            }
            
            .event-title {
                font-size: 11px;
            }
            
            .event-duration {
                font-size: 9px;
            }
            
            .spanning-event-block {
                min-height: 40px;
                padding: 4px;
            }
        }
    """


def save_html_schedule(
    result: SchedulingResult,
    file_path: str,
    start_hour: int = 9,
    start_minute: int = 0,
    title: str = "Track Meet Schedule",
) -> None:
    """
    Save HTML schedule to a file.
    
    Args:
        result: The scheduling result containing events, athletes, and schedule
        file_path: Path where to save the HTML file
        start_hour: Starting hour for the schedule (24-hour format)
        start_minute: Starting minute for the schedule
        title: Title for the HTML table
    """
    html_content = generate_html_schedule_table(
        result=result,
        start_hour=start_hour,
        start_minute=start_minute,
        title=title,
    )
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
