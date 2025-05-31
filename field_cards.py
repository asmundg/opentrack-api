#!/usr/bin/env python3
# filepath: /Volumes/src/priv/opentrack/field_cards.py
import argparse
import json
import sys
import os
import re
import urllib.request
import urllib.error
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from datetime import datetime

# Import required functions from local modules - no fallbacks
from opentrack_utils import fetch_json_data, process_local_json

def create_field_cards(data, output_filename=None, event_type=None, events=None, day=None):
    """
    Create field cards PDF for field events with wind registration.
    
    Args:
        data: JSON dictionary of competitor data from OpenTrack
        output_filename: Name of the output PDF file (optional, will be auto-generated if not provided)
        event_type: Type of field event to filter by (optional)
        events: List of event codes to filter by (optional, overrides event_type)
        day: Day number to filter by (optional, e.g., 1, 2, 3)
    """
    # Require raw JSON format from OpenTrack
    if not isinstance(data, dict) or 'competitors' not in data or 'events' not in data:
        raise TypeError("Data must be a dict with 'competitors' and 'events' keys from OpenTrack JSON")
    
    # Parse competitor data
    from competitors_by_club import parse_competitors_by_club
    competitors_data = parse_competitors_by_club(data)
    
    # Extract meeting name from data - require it to be present
    meeting_name = data['fullName']
    meeting_date = data.get('date', '')
    
    # Parse the meeting date for better formatting
    formatted_meeting_date = meeting_date
    if meeting_date:
        try:
            from datetime import datetime as dt
            parsed_date = dt.strptime(meeting_date, '%Y-%m-%d')
            formatted_meeting_date = parsed_date.strftime('%d %B %Y')
        except ValueError:
            # Keep original format if parsing fails
            formatted_meeting_date = meeting_date
    
    # Filter events to process
    field_event_codes = ['LJ', 'TJ', 'HJ', 'DT', 'JT', 'SP', 'HT', 'PV', 'BT']
    events_to_process = []
    
    for event in data['events']:
        event_code = event.get('eventCode', '')
        event_id = event.get('eventId', event_code)
        
        # Check if this is a field event
        is_field_event = any(code in event_code for code in field_event_codes)
        if not is_field_event:
            continue
            
        # Check if we should include this event based on filters
        if events:
            # Filter by specific event codes
            event_list = events if isinstance(events, list) else [events]
            if not any(evt_type in event_code for evt_type in event_list):
                continue
        elif event_type:
            # Filter by single event type
            if event_type not in event_code:
                continue
        
        # Filter by day if specified
        if day is not None:
            event_day = event.get('day', 1)
            if event_day != day:
                continue
        
        # Require maxFieldAttempts to be present
        if 'maxFieldAttempts' not in event:
            print(f"WARNING: Event {event_code} (ID: {event_id}) missing 'maxFieldAttempts' field, skipping")
            continue
            
        events_to_process.append(event)
    
    if not events_to_process:
        available_events = [f"{event.get('eventCode', 'Unknown')} (ID: {event.get('eventId', 'N/A')})" for event in data['events']]
        raise ValueError(f"No matching field events found. Available events: {available_events}")
    
    # Generate output filename if not provided
    if output_filename is None:
        import re
        safe_meeting_name = meeting_name
        if safe_meeting_name:
            # Replace spaces with underscores and remove special characters
            safe_meeting_name = re.sub(r'[^\w\s-]', '', safe_meeting_name)
            safe_meeting_name = re.sub(r'[\s-]+', '_', safe_meeting_name)
            
            day_suffix = f"_day{day}" if day is not None else ""
            
            if len(events_to_process) == 1:
                event_code = events_to_process[0]['eventCode']
                output_filename = f"field_cards_{event_code}_{safe_meeting_name}{day_suffix}.pdf"
            else:
                output_filename = f"field_cards_multiple_{safe_meeting_name}{day_suffix}.pdf"
        else:
            day_suffix = f"_day{day}" if day is not None else ""
            
            if len(events_to_process) == 1:
                event_code = events_to_process[0]['eventCode']
                output_filename = f"field_cards_{event_code}{day_suffix}.pdf"
            else:
                output_filename = f"field_cards_multiple{day_suffix}.pdf"
    
    # Print debug information
    day_filter_text = f" (filtered by day {day})" if day is not None else ""
    print(f"Creating field cards for {len(events_to_process)} events{day_filter_text}:")
    for event in events_to_process:
        event_day = event.get('day', 1)
        print(f"  - {event['eventCode']} (ID: {event.get('eventId', 'N/A')}) - Day {event_day} - {event['maxFieldAttempts']} attempts")
    print(f"Meeting name: {meeting_name}")
    print(f"Output filename: {output_filename}")
    
    # Create a mapping of bib numbers to competitors
    bib_to_competitor = {}
    for competitor in competitors_data:
        if 'bib' in competitor:
            bib_to_competitor[competitor['bib']] = competitor
    
    # Initialize the PDF document in landscape orientation
    doc = SimpleDocTemplate(
        output_filename,
        pagesize=landscape(A4),
        rightMargin=0.2*cm,
        leftMargin=0.2*cm,
        topMargin=0.8*cm,
        bottomMargin=0.8*cm
    )
    
    # Get current date
    current_date = datetime.now().strftime("%d %B %Y")
    
    # Initialize styles
    styles = getSampleStyleSheet()
    
    # Create ORIS-style custom styles
    title_style = ParagraphStyle(
        name='TitleStyle',
        parent=styles['Heading1'],
        fontSize=16,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER,
        spaceAfter=8,
        spaceBefore=4
    )
    
    subtitle_style = ParagraphStyle(
        name='SubtitleStyle',
        parent=styles['Heading2'],
        fontSize=12,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER,
        spaceAfter=6,
        spaceBefore=2
    )
    
    event_info_style = ParagraphStyle(
        name='EventInfoStyle',
        parent=styles['Normal'],
        fontSize=10,
        fontName='Helvetica',
        alignment=TA_CENTER,
        spaceAfter=8,
        spaceBefore=2
    )
    
    header_style = ParagraphStyle(
        name='HeaderStyle',
        parent=styles['Normal'],
        fontSize=8,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER,
        leading=9  # Better line spacing for multi-line headers
    )
    
    normal_style = ParagraphStyle(
        name='NormalStyle',
        parent=styles['Normal'],
        fontSize=8,
        fontName='Helvetica',
        leading=9
    )
    
    small_style = ParagraphStyle(
        name='SmallStyle',
        parent=styles['Normal'],
        fontSize=8,
        fontName='Helvetica'
    )
    
    # Create a list to hold the elements that will be built into the PDF
    elements = []
    
    # NEW ARCHITECTURE: Group events by type and time to create combined tables
    from collections import defaultdict
    
    # First pass: group events by type and time, collect bib numbers
    event_groups = defaultdict(lambda: {
        'events': [],
        'time': '',
        'max_attempts': 0,
        'all_bibs': set(),
        'throwing_events': set(),
        'weight_by_competitor': {}  # Store weight by bib number instead of event code
    })
    
    print("Phase 1: Grouping events by type and time...")
    
    for event in events_to_process:
        event_code = event['eventCode']
        event_id = event.get('eventId', event_code)
        event_name = event.get('name', event_code)
        max_attempts = event['maxFieldAttempts']
        event_time = event.get('r1Time', '')
        
        # Determine the base event type (e.g., LJ, SP, HJ)
        base_event_type = None
        field_event_codes = ['LJ', 'TJ', 'HJ', 'DT', 'JT', 'SP', 'HT', 'PV', 'BT']
        for code in field_event_codes:
            if code in event_code:
                base_event_type = code
                break
        
        if not base_event_type:
            print(f"WARNING: Could not determine base event type for {event_code}, skipping")
            continue
        
        # Create group key based on event type and time
        if not event_time:
            print(f"ERROR: Event {event_code} (ID: {event_id}) missing 'r1Time' field, cannot group events without start time")
            continue
        group_key = f"{base_event_type}_{event_time}"
        
        print(f"Processing event: {event_name} ({event_code}, ID: {event_id}) -> Group: {group_key}")
        
        # Add event info to group
        event_groups[group_key]['events'].append({
            'code': event_code,
            'id': event_id,
            'name': event_name,
            'max_attempts': max_attempts,
            'day': event.get('day', 1)  # Capture the day property
        })
        event_groups[group_key]['time'] = event_time
        event_groups[group_key]['max_attempts'] = max(event_groups[group_key]['max_attempts'], max_attempts)
        # Store the day for this group (all events in a group should have the same day)
        if 'day' not in event_groups[group_key]:
            event_groups[group_key]['day'] = event.get('day', 1)
        
        # Extract weight information and collect bibs from units/results in order
        event_bibs_in_order = []
        for unit in event.get('units', []):
            for result in unit.get('results', []):
                # Collect bib numbers for this group in order
                if 'bib' in result:
                    event_groups[group_key]['all_bibs'].add(result['bib'])
                    event_bibs_in_order.append(result['bib'])
                    
                # Extract weight information for throwing events
                if 'weight' in result and base_event_type in ['SP', 'DT', 'HT', 'JT', 'BT']:
                    event_groups[group_key]['throwing_events'].add(base_event_type)
                    # Store weight by competitor bib number for accurate per-competitor lookup
                    competitor_bib = result['bib']
                    event_groups[group_key]['weight_by_competitor'][competitor_bib] = result['weight']
        
        # Store the ordered bibs for this event
        if 'ordered_bibs_by_event' not in event_groups[group_key]:
            event_groups[group_key]['ordered_bibs_by_event'] = []
        event_groups[group_key]['ordered_bibs_by_event'].append({
            'event_code': event_code,
            'event_name': event_name,
            'bibs': event_bibs_in_order
        })
    
    print(f"Phase 2: Processing {len(event_groups)} event groups...")
    
    # Define the preferred order of field events
    event_type_order = ['LJ', 'TJ', 'HJ', 'PV', 'SP', 'DT', 'JT', 'HT', 'BT']
    
    def sort_group_key(group_item):
        """Sort groups first by event type order, then by full datetime (day + time)"""
        group_key, group_data = group_item
        base_event_type = group_key.split('_')[0]
        event_time = group_data['time']
        event_day = group_data.get('day', 1)
        
        # Get the order index for the event type, default to 999 if not found
        type_order = event_type_order.index(base_event_type) if base_event_type in event_type_order else 999
        
        # Convert time to minutes since midnight for proper sorting
        try:
            time_parts = event_time.split(':')
            hours = int(time_parts[0])
            minutes = int(time_parts[1])
            minutes_since_midnight = hours * 60 + minutes
        except (ValueError, IndexError):
            minutes_since_midnight = 9999  # Put invalid times at the end
        
        # Create a comprehensive datetime sort key:
        # (event_type_priority, day, minutes_since_midnight)
        # This ensures events are sorted by type first, then by actual start datetime
        return (type_order, event_day, minutes_since_midnight)
    
    # Second pass: process each group and create combined tables
    sorted_groups = sorted(event_groups.items(), key=sort_group_key)
    print(f"Groups will be processed in this order:")
    for group_key, group_data in sorted_groups:
        base_event_type = group_key.split('_')[0]
        event_day = group_data.get('day', 1)
        print(f"  {group_key} (Event Type: {base_event_type}, Day: {event_day}, Time: {group_data['time']})")
    
    for group_key, group_data in sorted_groups:
        print(f"\nProcessing group: {group_key}")
        print(f"  Events in group: {[e['code'] for e in group_data['events']]}")
        print(f"  Time: {group_data['time']}")
        print(f"  Max attempts: {group_data['max_attempts']}")
        print(f"  Total bibs in group: {sorted(group_data['all_bibs'])}")
        
        # Determine event characteristics
        base_event_type = group_key.split('_')[0]
        has_wind = base_event_type in ['LJ', 'TJ']
        is_throwing = len(group_data['throwing_events']) > 0
        is_high_jump = base_event_type in ['HJ', 'PV']  # Both HJ and PV use height-based layout
        
        # Resolve bib numbers to competitors in proper order
        all_competitors = []
        
        # If we have multiple events, sort by event name (category) and preserve internal order
        if 'ordered_bibs_by_event' in group_data:
            # Sort events by name to get consistent category ordering
            sorted_events = sorted(group_data['ordered_bibs_by_event'], key=lambda x: x['event_name'])
            
            for event_info in sorted_events:
                # Mark the start of a new event category for spacing
                if all_competitors:  # Add separator only if there are already competitors
                    all_competitors.append({'is_separator': True, 'event_name': event_info['event_name']})
                
                for bib in event_info['bibs']:
                    if bib in bib_to_competitor:
                        competitor = bib_to_competitor[bib].copy()
                        competitor['event_name'] = event_info['event_name']  # Track which event this competitor belongs to
                        all_competitors.append(competitor)
        else:
            # Fallback: use all_bibs set (though this shouldn't happen with new logic)
            for bib in sorted(group_data['all_bibs']):
                if bib in bib_to_competitor:
                    competitor = bib_to_competitor[bib].copy()
                    all_competitors.append(competitor)
        
        print(f"  Total competitors resolved: {len([c for c in all_competitors if not (isinstance(c, dict) and c.get('is_separator'))])}")
        
        # Check if this is a merged event group (multiple event categories)
        is_merged_event = 'ordered_bibs_by_event' in group_data and len(group_data['ordered_bibs_by_event']) > 1
        if is_merged_event:
            print(f"  Merged event detected with {len(group_data['ordered_bibs_by_event'])} categories - adding spacing between categories")
        
        if len(all_competitors) == 0:
            print(f"  No competitors in group {group_key}, skipping")
            continue
        
        # Create group header using event names in the same order as competitors
        if 'ordered_bibs_by_event' in group_data and len(group_data['ordered_bibs_by_event']) > 1:
            # Use sorted event names to match the competitor order
            sorted_event_names = [e['event_name'] for e in sorted(group_data['ordered_bibs_by_event'], key=lambda x: x['event_name'])]
            group_header = " / ".join(sorted_event_names)
        else:
            # Single event or fallback
            event_names = [e['name'] for e in group_data['events']]
            if len(event_names) == 1:
                group_header = event_names[0]
            else:
                group_header = " / ".join(event_names)
        
        # Calculate the actual event date by combining base date and event day
        event_date_str = formatted_meeting_date
        if meeting_date and 'day' in group_data:
            try:
                from datetime import datetime as dt, timedelta
                base_date = dt.strptime(meeting_date, '%Y-%m-%d')
                # Day 1 = base date, Day 2 = base date + 1 day, etc.
                event_date = base_date + timedelta(days=group_data['day'] - 1)
                event_date_str = event_date.strftime('%Y-%m-%d')  # Use ISO format like in image
            except (ValueError, TypeError):
                # Keep formatted_meeting_date if parsing fails
                event_date_str = formatted_meeting_date
        
        # ORIS-style event header with professional formatting - match image format
        elements.append(Paragraph(f"{group_header} - {event_date_str if event_date_str else formatted_meeting_date}", subtitle_style))
        elements.append(Paragraph(f"{meeting_name} - START TIME: {group_data['time']}", event_info_style))
        
        # Add wind conditions notice for relevant events
        if has_wind:
            elements.append(Paragraph("<i>Wind measurements required for record purposes</i>", small_style))
        
        # Add High Jump instructions
        if is_high_jump:
            if base_event_type == 'HJ':
                elements.append(Paragraph("<i>High Jump: Each height has 3 columns for attempts. Mark O (cleared), X (missed), or - (passed) in each attempt box.</i>", small_style))
            elif base_event_type == 'PV':
                elements.append(Paragraph("<i>Pole Vault: Each height has 3 columns for attempts. Mark O (cleared), X (missed), or - (passed) in each attempt box.</i>", small_style))
        
        elements.append(Spacer(1, 0.3*cm))
        
        # Don't sort competitors by bib - preserve the order from results
        # all_competitors.sort(key=lambda x: int(x['bib']))  # Removed - preserve original order
        
        if is_high_jump:
            # HIGH JUMP/POLE VAULT SPECIAL LAYOUT
            event_name = "High Jump" if base_event_type == 'HJ' else "Pole Vault"
            print(f"    Creating {event_name} layout with height columns")
            
            # Create blank height columns that judges can fill in
            num_height_columns = 9  # Provide 9 blank height columns
            
            # Create header row for High Jump
            header_row = [
                Paragraph("<b>Order</b>", header_style),
                Paragraph("<b>Bib</b>", header_style),
                Paragraph("<b>Name</b>", header_style),
                Paragraph("<b>Club</b>", header_style),
                Paragraph("<b>Age</b>", header_style)
            ]
            
            # Add blank height columns - judges will fill in the actual heights
            # Each height gets 3 sub-columns for the 3 attempts
            for i in range(num_height_columns):
                # Add a main height header that will span 3 columns
                header_row.append(Paragraph("<b>_____m</b>", header_style))
                # Add two more columns for the 3 attempts (total 3 per height)
                header_row.append("")  # Attempt 2 (will be merged with height header)
                header_row.append("")  # Attempt 3 (will be merged with height header)
            
            # Add final columns
            if base_event_type == 'HJ':
                header_row.append(Paragraph("<b>Best<br/>Height</b>", header_style))
            elif base_event_type == 'PV':
                header_row.append(Paragraph("<b>Best<br/>Height</b>", header_style))
            header_row.append(Paragraph("<b>PB /<br/>Note</b>", header_style))
            header_row.append(Paragraph("<b>Final<br/>Pos</b>", header_style))
            
        else:
            # REGULAR FIELD EVENT LAYOUT
            # Create ORIS-style header row
            header_row = [
                Paragraph("<b>Order</b>", header_style),
                Paragraph("<b>Bib</b>", header_style),
                Paragraph("<b>Name</b>", header_style),
                Paragraph("<b>Club</b>", header_style),
                Paragraph("<b>Age</b>", header_style)
            ]
            
            # Add weight column for throwing events
            if is_throwing:
                header_row.append(Paragraph("<b>Weight</b>", header_style))
            
            # Add columns for each attempt - using ordinal numbers like in the image
            ordinal_suffixes = {1: "st", 2: "nd", 3: "rd"}
            wind_text = " (with wind)" if has_wind else ""
            print(f"    Creating {group_data['max_attempts']} attempt columns{wind_text}")
            for i in range(1, group_data['max_attempts'] + 1):
                suffix = ordinal_suffixes.get(i, "th")
                header_row.append(Paragraph(f"<b>{i}{suffix}<br/>Trial</b>", header_style))
                if has_wind:
                    header_row.append(Paragraph("<b>Wind</b>", header_style))  # Wind column for LJ/TJ
            
            # Add columns for best result and final position
            header_row.append(Paragraph(f"<b>Best<br/>of {group_data['max_attempts']}</b>", header_style))
            header_row.append(Paragraph("<b>PB /<br/>Note</b>", header_style))
            header_row.append(Paragraph("<b>Final<br/>Pos</b>", header_style))
        
        # Create data for the table
        table_data = [header_row]
        
        # Add rows for each competitor
        competitor_counter = 0  # Counter for actual competitors (excluding separators)
        spacing_rows = []  # Track which rows are spacing rows (0-indexed from table_data)
        category_end_rows = []  # Track the last row of each category for bottom border
        
        for item in all_competitors:
            # Handle category separator
            if isinstance(item, dict) and item.get('is_separator'):
                # Mark the previous row as the end of a category (if there was a previous row)
                if len(table_data) > 1:  # > 1 because table_data[0] is the header
                    category_end_rows.append(len(table_data) - 1)
                
                # Create an empty spacing row with increased padding
                num_columns = len(header_row)
                spacing_row = [""] * num_columns
                table_data.append(spacing_row)
                spacing_rows.append(len(table_data) - 1)  # Track this row index for special styling
                continue
            
            # Handle normal competitor
            competitor = item
            competitor_counter += 1
            
            name_parts = competitor['name'].split()
            if len(name_parts) > 1:
                last_name = name_parts[-1]
                first_name = " ".join(name_parts[:-1])
                formatted_name = f"{last_name.upper()}, {first_name}"
            else:
                formatted_name = competitor['name'].upper()
            
            row = [
                str(competitor_counter),  # Order/Position
                competitor['bib'],
                Paragraph(formatted_name, normal_style),
                Paragraph(competitor['club'], normal_style),
                Paragraph(competitor['category'], normal_style)
            ]
            
            if is_high_jump:
                # HIGH JUMP/POLE VAULT ROW LAYOUT
                # Add empty cells for each height (3 attempts per height)
                for i in range(num_height_columns):
                    row.append("")  # Attempt 1
                    row.append("")  # Attempt 2
                    row.append("")  # Attempt 3
                
                # Add empty cells for best height, PB/Note, and final position
                row.append("")  # Best Height
                row.append("")  # PB/Note
                row.append("")  # Final Position
                
            else:
                # REGULAR FIELD EVENT ROW LAYOUT
                # Add weight column for throwing events
                if is_throwing:
                    # Look up weight for this specific competitor by bib number
                    competitor_bib = competitor['bib']
                    weight = group_data['weight_by_competitor'].get(competitor_bib, "")
                    if weight:
                        weight_text = f"{weight}kg"
                    else:
                        weight_text = ""
                    row.append(Paragraph(weight_text, normal_style))
                
                # Add empty cells for results and wind measurements
                for _ in range(group_data['max_attempts']):
                    row.append("")  # Result
                    if has_wind:
                        row.append("")  # Wind/SB
                
                # Add empty cells for best result, PB/Note, and final position
                row.append("")  # Best of N
                row.append("")  # PB/Note
                row.append("")  # Final Position
            
            table_data.append(row)
        
        # Mark the last row as a category end if this is a merged event
        if is_merged_event and len(table_data) > 1:  # > 1 because table_data[0] is the header
            category_end_rows.append(len(table_data) - 1)
        
        # Calculate column widths to use the full width of the page
        available_width = doc.width
        
        # Fixed columns for competitor details - adjusted for new layout
        order_width = 1.0 * cm  # Order - wider to prevent wrapping
        bib_width = 0.8 * cm
        name_width = 3.2 * cm  
        club_width = 2.8 * cm
        age_width = 1.0 * cm  # Age - wider to prevent wrapping
        weight_width = 1.2 * cm if (is_throwing and not is_high_jump) else 0  # Weight - not used in HJ/PV
        best_width = 1.2 * cm  # Best result
        pb_note_width = 1.3 * cm  # PB/Note
        final_pos_width = 1.1 * cm  # Final Pos - wider for better word wrapping
        
        if is_high_jump:
            # HIGH JUMP/POLE VAULT COLUMN LAYOUT
            # Calculate fixed width total (no weight column for HJ/PV)
            fixed_width = order_width + bib_width + name_width + club_width + age_width + best_width + pb_note_width + final_pos_width
            
            # Calculate space for height columns (3 attempts per height)
            remaining_width = available_width - fixed_width
            total_height_columns = num_height_columns * 3  # 3 attempts per height
            attempt_width = remaining_width / total_height_columns  # Distribute evenly among all attempt columns
            
            # Create column widths list
            col_widths = [order_width, bib_width, name_width, club_width, age_width]
            for _ in range(num_height_columns):
                # Add 3 attempt columns for each height
                col_widths.append(attempt_width)  # Attempt 1
                col_widths.append(attempt_width)  # Attempt 2
                col_widths.append(attempt_width)  # Attempt 3
            col_widths.extend([best_width, pb_note_width, final_pos_width])
            
        else:
            # REGULAR FIELD EVENT COLUMN LAYOUT
            # Calculate fixed width total
            fixed_width = order_width + bib_width + name_width + club_width + age_width + weight_width + best_width + pb_note_width + final_pos_width
            
            # Calculate space for attempts - fixed width for both trial and wind boxes
            remaining_width = available_width - fixed_width
            
            if has_wind:
                # Fixed width for both trial and wind columns
                result_width = 1.5 * cm  # Fixed width for trial boxes
                wind_width = 1.0 * cm    # Fixed width for wind columns
            else:
                # Only result columns, no wind columns - use fixed width
                result_width = 1.5 * cm  # Fixed width for trial boxes
            
            # Create column widths list
            col_widths = [order_width, bib_width, name_width, club_width, age_width]
            if is_throwing:
                col_widths.append(weight_width)
            
            for _ in range(group_data['max_attempts']):
                col_widths.append(result_width)  # Result column
                if has_wind:
                    col_widths.append(wind_width)    # Wind column
            col_widths.extend([best_width, pb_note_width, final_pos_width])
        
        # Create the table
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        
        # ORIS-style table styling with professional appearance
        table_style = TableStyle([
            # Horizontal lines only - no vertical separators in contestant details
            ('LINEABOVE', (0, 0), (-1, 0), 2, colors.black),  # Thick line at top of table
            ('LINEBELOW', (0, 0), (-1, 0), 2, colors.black),  # Thick line under header
            ('LINEBELOW', (0, 1), (-1, -1), 1, colors.black),  # Horizontal lines between rows
            
            # Header styling - more professional like the image
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.85, 0.85, 0.85)),  # Slightly darker gray header
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Font sizes - increased for better readability
            ('FONTSIZE', (0, 0), (-1, 0), 8),  # Header font size
            ('FONTSIZE', (0, 1), (-1, -1), 8),  # Body font size  
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # Header font
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),      # Body font
            
            # Padding for better readability with 8pt font
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            
            # Row height for better appearance
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.98, 0.98, 0.98)]),  # Alternate row colors
            
            # Alignment for data cells
            ('ALIGN', (0, 1), (1, -1), 'CENTER'),  # Order and Bib centered
            ('ALIGN', (2, 1), (2, -1), 'LEFT'),    # Name left-aligned
            ('ALIGN', (3, 1), (3, -1), 'LEFT'),    # Club left-aligned  
            ('ALIGN', (4, 1), (4, -1), 'CENTER'),  # Age centered
        ])
        
        # Adjust alignment based on event type and whether weight column exists
        if is_high_jump:
            # Height columns (starting after age)
            heights_start_col = 5
            
            # Add cell spanning for High Jump height headers
            for height_idx in range(num_height_columns):
                start_col = heights_start_col + (height_idx * 3)
                end_col = start_col + 2  # Span across 3 columns
                table_style.add('SPAN', (start_col, 0), (end_col, 0))  # Merge header cells
            # All height columns centered
            total_height_cols = num_height_columns * 3  # 3 attempts per height
            heights_end_col = heights_start_col + total_height_cols - 1
            table_style.add('ALIGN', (heights_start_col, 1), (heights_end_col, -1), 'CENTER')
            
            # Final columns start after height columns
            final_results_start = heights_start_col + total_height_cols
            
        elif is_throwing:
            # Weight column centered
            table_style.add('ALIGN', (5, 1), (5, -1), 'CENTER')
            # Result and wind columns (starting after weight)
            trials_start_col = 6
            # Final results start after trial columns
            final_results_start = trials_start_col + (group_data['max_attempts'] * (2 if has_wind else 1))
            
        else:
            # Result and wind columns (starting after age)
            trials_start_col = 5
            # Final results start after trial columns
            final_results_start = trials_start_col + (group_data['max_attempts'] * (2 if has_wind else 1))
        
        # Add vertical separators for table borders and trial/result columns
        # Vertical line at the left edge of the table (before first column)
        table_style.add('LINEBEFORE', (0, 0), (0, -1), 1, colors.black)
        
        if is_high_jump:
            # HIGH JUMP/POLE VAULT VERTICAL LINES
            # Vertical line before first height column
            table_style.add('LINEBEFORE', (heights_start_col, 0), (heights_start_col, -1), 1, colors.black)
            
            # Vertical lines between height groups and within height groups
            for height_idx in range(num_height_columns):
                base_col = heights_start_col + (height_idx * 3)
                
                # Add vertical line before each height group (except the first one)
                if height_idx > 0:
                    table_style.add('LINEBEFORE', (base_col, 0), (base_col, -1), 1, colors.black)
                
                # Add vertical lines between attempts within each height (lighter lines)
                table_style.add('LINEBEFORE', (base_col + 1, 0), (base_col + 1, -1), 0.5, colors.gray)
                table_style.add('LINEBEFORE', (base_col + 2, 0), (base_col + 2, -1), 0.5, colors.gray)
            
        else:
            # REGULAR FIELD EVENT VERTICAL LINES
            # Vertical line before first trial column
            table_style.add('LINEBEFORE', (trials_start_col, 0), (trials_start_col, -1), 1, colors.black)
            
            # Vertical lines between trial columns
            for trial_num in range(group_data['max_attempts']):
                col_idx = trials_start_col + trial_num * (2 if has_wind else 1)
                if trial_num > 0:  # Don't add line before first trial (already added above)
                    table_style.add('LINEBEFORE', (col_idx, 0), (col_idx, -1), 1, colors.black)
                if has_wind:
                    # Add thin divider between trial and wind column
                    table_style.add('LINEAFTER', (col_idx, 0), (col_idx, -1), 0.5, colors.gray)
                    # Add line after wind column (except for the last wind column)
                    if trial_num < group_data['max_attempts'] - 1:
                        table_style.add('LINEAFTER', (col_idx + 1, 0), (col_idx + 1, -1), 1, colors.black)
        
        # Vertical line before final result columns (Best, PB/Note, Final Pos)
        table_style.add('LINEBEFORE', (final_results_start, 0), (final_results_start, -1), 1, colors.black)
        
        # Vertical lines between final result columns
        table_style.add('LINEBEFORE', (final_results_start + 1, 0), (final_results_start + 1, -1), 1, colors.black)
        table_style.add('LINEBEFORE', (final_results_start + 2, 0), (final_results_start + 2, -1), 1, colors.black)
        
        # Vertical line at the right edge of the table (after last column)
        table_style.add('LINEAFTER', (-1, 0), (-1, -1), 1, colors.black)
        
        # Center align all trial and result columns
        if not is_high_jump:
            table_style.add('ALIGN', (trials_start_col, 1), (-1, -1), 'CENTER')  # All remaining columns centered
        
        # Add light shading to the 3 rightmost columns (Best, PB/Note, Final Pos)
        table_style.add('BACKGROUND', (final_results_start, 1), (-1, -1), colors.Color(0.95, 0.95, 0.95))  # Light gray for final columns
        
        # Add special styling for spacing rows between event categories
        for spacing_row_idx in spacing_rows:
            # Make spacing rows much narrower to reduce whitespace
            table_style.add('TOPPADDING', (0, spacing_row_idx), (-1, spacing_row_idx), 1)
            table_style.add('BOTTOMPADDING', (0, spacing_row_idx), (-1, spacing_row_idx), 1)
            # Add cross-hatch-like pattern using distinctive background and borders
            table_style.add('BACKGROUND', (0, spacing_row_idx), (-1, spacing_row_idx), colors.Color(0.85, 0.85, 0.85))  # Medium gray background
            # Create visual cross-hatch effect with subtle borders
            table_style.add('LINEABOVE', (0, spacing_row_idx), (-1, spacing_row_idx), 0.5, colors.Color(0.6, 0.6, 0.6))
            table_style.add('LINEBELOW', (0, spacing_row_idx), (-1, spacing_row_idx), 0.5, colors.Color(0.6, 0.6, 0.6))
            # Add alternating vertical lines to create cross-hatch visual effect
            for col_idx in range(0, len(header_row), 3):  # Every 3rd column gets a subtle line
                if col_idx < len(header_row):
                    table_style.add('LINEBEFORE', (col_idx, spacing_row_idx), (col_idx, spacing_row_idx), 0.3, colors.Color(0.7, 0.7, 0.7))
        
        # Add solid bottom line to the last contestant row in each category for merged events
        for category_end_row_idx in category_end_rows:
            # Add a thicker bottom border to clearly outline each contestant group
            table_style.add('LINEBELOW', (0, category_end_row_idx), (-1, category_end_row_idx), 2, colors.black)
        
        table.setStyle(table_style)
        elements.append(table)
        
        # Add a page break after each group table
        # The signature area is now handled by the page template
        elements.append(PageBreak())
    
    # Define a function for page numbers and signature area
    def add_page_number_and_signature(canvas, doc, signature_elements=None):
        page_num = canvas.getPageNumber()
        text = f"Page {page_num}"
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        
        # Calculate position for signature area - snap to bottom of page
        sig_y_position = 0.5*cm  # Position very close to bottom edge of page
        
        # Position the page number above the signature area
        canvas.drawRightString(doc.width + doc.rightMargin - 2, sig_y_position + 4*cm, text)
        
        # Add signature area at bottom if provided
        if signature_elements:
            
            canvas.setFont("Helvetica-Bold", 10)
            # Use the correct ReportLab method for centered text
            center_x = doc.leftMargin + doc.width/2
            # ReportLab uses drawCentredText (British spelling)
            try:
                canvas.drawCentredText(center_x, sig_y_position + 3*cm, "OFFICIALS")
            except AttributeError:
                # Fallback to manual centering if method doesn't exist
                text_width = canvas.stringWidth("OFFICIALS", "Helvetica-Bold", 10)
                canvas.drawString(center_x - text_width/2, sig_y_position + 3*cm, "OFFICIALS")
            
            canvas.setFont("Helvetica", 8)
            # Actual start and End fields
            canvas.drawString(doc.leftMargin, sig_y_position + 2.5*cm, "Actual start: ____________________________")
            canvas.drawString(doc.leftMargin + doc.width/2, sig_y_position + 2.5*cm, "End: ____________________________")
            
            # Judge and Technical Delegate signatures
            canvas.drawString(doc.leftMargin, sig_y_position + 1.5*cm, "Judge: ____________________________")
            canvas.drawString(doc.leftMargin + doc.width/2, sig_y_position + 1.5*cm, "Technical Delegate: ____________________________")
            
            # Timestamp
            timestamp = datetime.now().strftime("Last changed: %a %b %d %H:%M:%S %Y")
            canvas.setFont("Helvetica-Oblique", 8)
            canvas.drawString(doc.leftMargin, sig_y_position + 0.5*cm, timestamp)
        
        canvas.restoreState()
    
    # Build the PDF with signature on every page
    doc.build(elements, 
              onFirstPage=lambda canvas, doc: add_page_number_and_signature(canvas, doc, True),
              onLaterPages=lambda canvas, doc: add_page_number_and_signature(canvas, doc, True))
    
    print(f"Field cards saved to {output_filename}")

def detect_field_event(data):
    """
    Auto-detect a field event from the data.
    
    Args:
        data: JSON dictionary of competitor data
        
    Returns:
        Detected event code or 'LJ' as default if none detected
    """
    # Common field event codes
    field_event_codes = ['LJ', 'TJ', 'HJ', 'DT', 'JT', 'SP', 'HT', 'PV']
    
    # First, try to find events that have units with results
    events_with_competitors = set()
    for event in data.get('events', []):
        event_code = event.get('eventCode', '')
        
        # Check if this is a field event
        is_field_event = False
        for code in field_event_codes:
            if code in event_code:
                is_field_event = True
                break
                
        if is_field_event:
            # Check if there are units with results
            for unit in event.get('units', []):
                if unit.get('results', []):
                    events_with_competitors.add(event_code)
                    print(f"Detected field event with competitors: {event_code}")
                    break
    
    # If we found field events with competitors, return the first one
    if events_with_competitors:
        # Sort to ensure consistent results
        sorted_events = sorted(events_with_competitors)
        print(f"Auto-detected event type: {sorted_events[0]}")
        return sorted_events[0]
    
    # Fallback: Try to find a suitable field event from the available events
    for event in data.get('events', []):
        event_code = event.get('eventCode', '')
        for code in field_event_codes:
            if code in event_code:
                print(f"Auto-detected event type: {code}")
                return code
    
    # If we don't find any, return LJ as default
    print("No field events detected, using default event type: LJ")
    return 'LJ'

def load_data_from_source(source):
    """
    Load data from a source which can be a URL or a local file path.
    
    Args:
        source: URL or file path to the JSON data
        
    Returns:
        Parsed JSON data
    """
    # Determine if source is a URL or a local file
    if source.startswith(('http://', 'https://')):
        return fetch_json_data(source)
    else:
        return process_local_json(source)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate field cards PDF for athletic events')
    parser.add_argument('source', help='JSON source URL or local file path')
    parser.add_argument('-o', '--output', help='Output PDF filename (optional, will be auto-generated if not provided)')
    parser.add_argument('-e', '--event', help='Event type code (optional, will be auto-detected if not specified)',
                        action='append', dest='events')
    parser.add_argument('--all-events', action='store_true', help='Process all field events found in the data')
    parser.add_argument('-d', '--day', type=int, help='Filter events by day number (e.g., 1, 2, 3)', metavar='N')
    
    args = parser.parse_args()
    
    try:
        # Load data from source
        data = load_data_from_source(args.source)
        
        # Determine which events to process
        events_to_process = None
        
        if args.all_events:
            # Process all field events
            field_event_codes = ['LJ', 'TJ', 'HJ', 'DT', 'JT', 'SP', 'HT', 'PV']
            events_to_process = []
            
            if isinstance(data, dict) and 'events' in data:
                for event in data['events']:
                    event_code = event.get('eventCode', '')
                    for code in field_event_codes:
                        if code in event_code and event_code not in events_to_process:
                            events_to_process.append(event_code)
                            break
            
            if not events_to_process:
                print("No field events found in the data")
                sys.exit(1)
        elif args.events:
            # Use the events specified in the arguments
            events_to_process = args.events
        
        # Create the field cards PDF with automatic parameter detection
        create_field_cards(
            data, 
            output_filename=args.output, 
            events=events_to_process,
            day=args.day
        )
        
        print(f"Field cards successfully generated")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
